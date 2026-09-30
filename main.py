import tkinter as tk
import time
import logging
from logging.handlers import RotatingFileHandler
from kiosk_view import KioskView as AppView
import ttkbootstrap as tb
from camera_service import CameraService
from camera_ui import TkCameraUpdatePoller
from config import AppConfig
from enrollment_session import EnrollmentSession
from database import Database
from enrollment_service import submit_enrollment
from repositories import StudentRepository
from enrollment_indexer import EnrollmentIndexer, IndexingResult
from student_photo_review import PhotoReviewer
from recognition_service import RecognitionService
from attendance_service import AttendanceError, AttendanceService, TimezoneConfigError
from attendance_repository import AttendanceHistoryError, AttendanceRepository
from attendance_export import export_attendance_csv
from recognition_evidence import RecognitionEvidenceTracker
from kiosk_settings import StaffAccess, read_json, save_preferences
from kiosk_flow import KioskFlow
from dataclasses import replace
import os


def configure_application_logging(data_dir):
    """Keep operational logs bounded and avoid repeated handler installation."""
    logger = logging.getLogger("face_attendance")
    logger.setLevel(logging.INFO)
    if not any(getattr(handler, "_attendance_handler", False) for handler in logger.handlers):
        handler = RotatingFileHandler(
            data_dir / "application.log", maxBytes=1_000_000, backupCount=3,
            encoding="utf-8",
        )
        handler._attendance_handler = True
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"
        ))
        logger.addHandler(handler)
    return logger
# ------------------- MODEL -------------------
class AppModel:
    def __init__(self):
        self.data = "Hello, MVC with DI!"


# ------------------- VIEW -------------------


class AppController:
    def __init__(
        self, model, view, camera_service, config=None, student_repository=None,
        recognition_service=None, enrollment_indexer=None, attendance_service=None,
        monotonic_clock=None, staff_access=None,
    ):
        self.model = model
        self.view = view
        self.camera_service = camera_service
        self.config = config or AppConfig.from_environment()
        self.staff_access = staff_access
        self.gallery_size = 0
        self.enrollment_session = None
        self.enrollment_replacement_id = None
        self.photo_reviewer = None
        self.student_repository = student_repository
        self.recognition_service = recognition_service
        self.enrollment_indexer = enrollment_indexer
        self.attendance_service = attendance_service
        self.attendance_repository = None
        self.attendance_error = None
        self.attendance_active = False
        self._attendance_started_at = None
        self._monotonic_clock = monotonic_clock or time.monotonic
        self.database = None
        self._identity_tracker = RecognitionEvidenceTracker(
            required_frames=self.config.stable_identity_frames,
            window_seconds=self.config.identity_evidence_window_seconds,
            max_age_seconds=self.config.identity_max_age_seconds,
        )
        self.logger = logging.getLogger("face_attendance")
        self.storage_error = None
        self._pending_index_ids = []
        if self.student_repository is None:
            try:
                self.config.ensure_data_directory()
                self.database = Database.from_config(self.config)
                self.database.initialize()
                self.student_repository = StudentRepository(
                    self.database, self.config.data_dir
                )
            except Exception as exc:
                self.storage_error = str(exc)
        if self.student_repository is not None:
            self.database = self.student_repository.database
            self.attendance_repository = AttendanceRepository(self.database)
        if self.attendance_service is None:
            if not self.config.attendance_timezone:
                self.attendance_error = (
                    "Set ATTENDANCE_TIMEZONE to the school's IANA timezone to enable attendance."
                )
            elif self.database is None:
                self.attendance_error = self.storage_error or "Student storage is unavailable."
            else:
                try:
                    self.attendance_service = AttendanceService(
                        self.database, self.config.attendance_timezone
                    )
                except TimezoneConfigError as exc:
                    self.attendance_error = str(exc)
        if self.attendance_service is not None and self.database is not None:
            self.attendance_repository = AttendanceRepository(self.database)
        self._update_attendance_view(False, self.attendance_error or "Attendance is paused.")
        if (
            self.enrollment_indexer is None
            and self.student_repository is not None
            and self.recognition_service is not None
        ):
            self.enrollment_indexer = EnrollmentIndexer(
                self.student_repository,
                self.recognition_service,
                self.config.data_dir,
            )
        try:
            self.reload_gallery()
            self._queue_unindexed_students()
        except Exception as exc:
            self.logger.exception("Could not initialize the recognition gallery")
            if hasattr(self.view, "update_operator_status"):
                self.view.update_operator_status(
                    f"Recognition gallery is unavailable: {exc}"
                )

    def fetch_data(self):
        self.model.data = "Data fetched from Model!"
        print(self.model.data)

    def require_staff(self):
        if self.staff_access is not None:
            self.staff_access.require()

    def apply_kiosk_settings(self, timezone_name, camera_index):
        self.require_staff()
        if self.database is None:
            raise ValueError("Storage is unavailable. Repair it before saving setup.")
        for name, wanted in (("ATTENDANCE_TIMEZONE", timezone_name), ("ATTENDANCE_CAMERA_INDEX", str(camera_index))):
            if name in os.environ and os.environ[name] != wanted:
                raise ValueError(f"{name} overrides this setting. Remove that launch override, restart, and try again.")
        service = AttendanceService(self.database, timezone_name)
        if camera_index < 0:
            raise ValueError("Camera number must be zero or greater.")
        if not self.stop_camera():
            raise ValueError("The old camera is still stopping. Wait and try again.")
        save_preferences(self.config.data_dir, timezone_name, camera_index)
        self.config = replace(self.config, attendance_timezone=timezone_name, camera_index=camera_index)
        self.attendance_service = service
        self.attendance_error = None
        if self.camera_service is not None:
            self.camera_service.camera_index = camera_index
        self.start_camera()

    def kiosk_ready(self):
        try:
            policy = read_json(self.config.data_dir / "kiosk-settings.json")
        except ValueError:
            return False
        return bool(
            self.staff_access and self.staff_access.configured
            and policy.get("daily_policy_confirmed")
            and policy.get("timezone") == self.config.attendance_timezone
            and self.attendance_service and self.recognition_service
            and self.student_repository and self.gallery_size > 0
        )

    def retry_indexing(self):
        self.require_staff()
        self._queue_unindexed_students()

    def start_camera(self):
        if self.camera_service is None:
            self.pause_attendance("Attendance paused because recognition is unavailable.")
            return False
        try:
            started = self.camera_service.start()
        except Exception:
            self.logger.exception("Could not start the camera")
            self.pause_attendance("Attendance paused because the camera could not start.")
            return False
        if not started:
            self.pause_attendance("Attendance paused because the camera could not start.")
        return started

    def stop_camera(self):
        self.pause_attendance("Attendance paused because the camera stopped.")
        self._identity_tracker.reset()
        if self.camera_service is None:
            return True
        return self.camera_service.stop()

    def toggle_camera(self):
        if self.camera_service is None:
            if hasattr(self.view, "update_camera_status"):
                self.view.update_camera_status("Unavailable until recognition models are configured.")
            return False
        if getattr(self.camera_service, "running", False):
            return self.stop_camera()
        self._identity_tracker.reset()
        return self.start_camera()

    def _update_attendance_view(self, active, message):
        if hasattr(self.view, "update_attendance_mode"):
            self.view.update_attendance_mode(active, message)

    def start_attendance(self):
        """Enable daily attendance only when storage, timezone, and camera are ready."""
        if self.attendance_service is None:
            self._update_attendance_view(False, self.attendance_error or "Attendance is unavailable.")
            return False
        if self.camera_service is None or not getattr(self.camera_service, "running", True):
            self._update_attendance_view(False, "Start the camera before starting attendance.")
            return False
        self._identity_tracker.reset()
        self._attendance_started_at = self._monotonic_clock()
        self.attendance_active = True
        self._update_attendance_view(True, "Attendance is active; hold still for recognition.")
        return True

    def pause_attendance(self, message="Attendance is paused."):
        self.attendance_active = False
        self._attendance_started_at = None
        self._identity_tracker.reset()
        self._update_attendance_view(False, message)

    def toggle_attendance(self):
        if self.attendance_active:
            self.pause_attendance()
            return False
        return self.start_attendance()

    def get_attendance_history(self, attendance_date=None, student_id=None):
        self.require_staff()
        if self.attendance_repository is None:
            raise AttendanceHistoryError(self.attendance_error or self.storage_error or "Attendance storage is unavailable.")
        return self.attendance_repository.list_records(
            attendance_date=attendance_date, student_id=student_id
        )

    def export_attendance_history(self, destination, attendance_date=None, student_id=None):
        self.require_staff()
        records = self.get_attendance_history(attendance_date, student_id)
        return export_attendance_csv(records, destination)

    def reload_gallery(self):
        if self.recognition_service is None or self.student_repository is None:
            return 0
        gallery = self.student_repository.load_compatible_gallery(
            self.recognition_service.model_version,
            self.recognition_service.preprocessing_id,
        )
        self.gallery_size = self.recognition_service.set_gallery(gallery)
        return self.gallery_size

    def _queue_unindexed_students(self):
        if (
            self.student_repository is None
            or self.enrollment_indexer is None
            or self.recognition_service is None
        ):
            return
        compatible_ids = {
            entry["student_id"]
            for entry in self.student_repository.load_compatible_gallery(
                self.recognition_service.model_version,
                self.recognition_service.preprocessing_id,
            )
        }
        self._pending_index_ids = [
            student.student_id
            for student in self.student_repository.list_students()
            if student.student_id not in compatible_ids and student.samples
        ]
        self._start_next_index()

    def _start_next_index(self):
        if self.enrollment_indexer is None:
            return
        if self.enrollment_indexer._thread is not None and self.enrollment_indexer._thread.is_alive():
            return
        if self._pending_index_ids:
            self.enrollment_indexer.submit(self._pending_index_ids.pop(0))

    def poll_indexing(self):
        """Consume one worker result on Tk's thread and publish gallery changes."""
        if self.enrollment_indexer is None:
            return None
        result = self.enrollment_indexer.poll_result()
        if result is None:
            self._start_next_index()
            return None
        try:
            self.reload_gallery()
        except Exception as exc:
            self.logger.exception("Could not refresh recognition gallery")
            if hasattr(self.view, "update_enrollment_status"):
                self.view.update_enrollment_status(IndexingResult(
                    result.student_id, 0,
                    f"Indexing finished but the gallery could not refresh: {exc}",
                ))
            self._start_next_index()
            return result
        self._start_next_index()
        try:
            current = self.student_repository.get_student(result.student_id)
        except Exception:
            current = None
            self.logger.exception("Could not verify the latest enrollment state")
        if current is not None and current.enrollment_status == "indexing":
            # A finished worker result can remain queued while a newer job for
            # this student has already started. Never announce the older result.
            return result
        if hasattr(self.view, "update_enrollment_status"):
            self.view.update_enrollment_status(result)
        return result

    def handle_identity_update(self, update):
        result = update.get("identity")
        if result is None:
            self._identity_tracker.reset()
            if self.attendance_active:
                self.pause_attendance(
                    "Attendance paused because the camera feed stopped."
                )
            if hasattr(self.view, "update_identity_status"):
                self.view.update_identity_status(None)
            return None

        if hasattr(self.view, "update_identity_status"):
            self.view.update_identity_status(result)
        if not self.attendance_active:
            return None
        try:
            camera_available = (
                self.camera_service is not None
                and getattr(self.camera_service, "running", True)
            )
            if not camera_available:
                self.pause_attendance(
                    "Attendance paused because the camera feed stopped."
                )
                if hasattr(self.view, "update_identity_status"):
                    self.view.update_identity_status(None)
                return None
            frame_id = update.get("frame_id")
            captured_at = update.get("captured_monotonic")
            if (
                self._attendance_started_at is None
                or captured_at is None
                or captured_at < self._attendance_started_at
            ):
                self._identity_tracker.reset()
                return None
            stable = self._identity_tracker.observe(
                result,
                frame_id=frame_id,
                captured_monotonic=captured_at,
                now_monotonic=self._monotonic_clock(),
                camera_available=True,
                enabled=self.attendance_active,
            )
            if stable is None:
                if hasattr(self.view, "update_attendance_progress"):
                    self.view.update_attendance_progress(
                        self._identity_tracker.progress,
                        self._identity_tracker.required_frames,
                        result,
                    )
                return None
            attendance = self.attendance_service.record(stable)
            if hasattr(self.view, "update_attendance_result"):
                self.view.update_attendance_result(attendance, stable.display_name)
            return attendance
        except AttendanceError as exc:
            self.logger.exception("Attendance record could not be saved")
            self.pause_attendance(f"Attendance paused: {exc}")
            if hasattr(self.view, "update_identity_status"):
                self.view.update_identity_status(None)
            return None
        except Exception as exc:
            self.logger.exception("Unexpected attendance processing failure")
            self.pause_attendance(f"Attendance paused after an error: {exc}")
            if hasattr(self.view, "update_identity_status"):
                self.view.update_identity_status(None)
            return None

    # ---------- Registration ----------
    def list_student_records(self):
        self.require_staff()
        if self.student_repository is None:
            raise ValueError("Student storage is unavailable.")
        return self.student_repository.list_students()

    def get_student_record(self, student_id):
        self.require_staff()
        if self.student_repository is None:
            raise ValueError("Student storage is unavailable.")
        student = self.student_repository.get_student(student_id)
        if student is None:
            raise ValueError("Student was not found. Refresh the list.")
        return student

    def _require_idle_indexing(self):
        worker = getattr(self.enrollment_indexer, "_thread", None)
        if self._pending_index_ids or (worker is not None and worker.is_alive()):
            raise ValueError("Recognition preparation is running. Wait before changing records.")

    @staticmethod
    def student_form_details(student):
        return {"user_id": student.student_id, "first_name": student.first_name,
            "middle_name": student.middle_name or "", "last_name": student.last_name,
            "guardian_fullname": student.guardian_full_name or "",
            "guardian_phone": student.guardian_phone or ""}

    def _refresh_edited_gallery(self):
        try:
            self.reload_gallery()
        except Exception:
            self.logger.exception("Saved student changes but could not refresh recognition")
            if self.recognition_service is not None:
                self.recognition_service.set_gallery(())
            self.gallery_size = 0
            self.pause_attendance("Student changes were saved, but recognition could not refresh. Restart before check-in.")

    def update_student_record(self, original_id, details):
        self.require_staff()
        self._require_idle_indexing()
        self.get_student_record(original_id)
        self.pause_attendance("Attendance paused while editing student records.")
        student = self.student_repository.update_student(original_id,
            details.get("user_id", ""), details.get("first_name", ""), details.get("last_name", ""),
            middle_name=details.get("middle_name") or None,
            guardian_full_name=details.get("guardian_fullname") or None,
            guardian_phone=details.get("guardian_phone") or None)
        self._refresh_edited_gallery()
        return student

    def begin_photo_replacement(self, student_id):
        self.require_staff()
        self._require_idle_indexing()
        student = self.get_student_record(student_id)
        self.cancel_enrollment()
        session = self.begin_enrollment()
        self.enrollment_replacement_id = student.student_id
        session.update_details(self.student_form_details(student))
        return session

    def review_student_photos(self, student_id):
        self.require_staff()
        student = self.get_student_record(student_id)
        self.pause_attendance("Attendance paused for photo review.")
        if self.photo_reviewer is None:
            self.photo_reviewer = PhotoReviewer(self.config, self.recognition_service)
        return self.photo_reviewer.submit(student)

    def poll_photo_review(self):
        result = self.photo_reviewer.poll_result() if self.photo_reviewer else None
        if result is not None and hasattr(self.view, "update_photo_review"):
            self.view.update_photo_review(result)
        return result

    def begin_enrollment(self):
        self.require_staff()
        self.pause_attendance("Attendance paused for student enrollment.")
        self.enrollment_replacement_id = None
        self.enrollment_session = EnrollmentSession(self.config.data_dir)
        return self.enrollment_session

    def update_enrollment_details(self, payload: dict):
        self.require_staff()
        if self.enrollment_session is None:
            return False
        return self.enrollment_session.update_details(payload)

    def cancel_enrollment(self):
        self.enrollment_replacement_id = None
        if self.enrollment_session is None:
            return True
        cancelled = self.enrollment_session.cancel()
        self.enrollment_session = None
        self.pause_attendance("Enrollment closed; attendance remains paused.")
        return cancelled

    @staticmethod
    def _slugify_segment(value: str, fallback: str) -> str:
        """Return a filesystem-friendly, lowercase string."""
        value = (value or "").strip()
        if not value:
            value = fallback
        value = value.replace(" ", "_")
        cleaned = "".join(ch for ch in value if ch.isalnum() or ch in ("-", "_"))
        cleaned = cleaned.strip("_-").lower()
        return cleaned or fallback

    def handle_capture_image(self, payload: dict):
        """
        Capture the current student's face image into assets/<student_folder>.
        """
        self.require_staff()
        if not isinstance(payload, dict):
            return False, "Invalid data supplied."
        if self.enrollment_session is None:
            self.begin_enrollment()
        prefix_value = payload.get("first_name", "").strip() or "face"
        filename_prefix = self._slugify_segment(prefix_value, "face")
        def capture(session_dir):
            if self.camera_service is None:
                return False, "Image capture is unavailable because face detection failed to initialize."
            return self.camera_service.capture_face(
                session_dir, filename_prefix=filename_prefix
            )

        success, result = self.enrollment_session.capture(capture, payload)
        if success:
            return True, f"Image saved to {result}"
        return False, result

    def handle_register(self, payload: dict):
        """Persist the active student enrollment in the local SQLite database."""
        self.require_staff()
        if self.enrollment_replacement_id is not None:
            return self._save_replacement_photos()
        if self.storage_error and self.student_repository is None:
            return False, f"Student storage is unavailable: {self.storage_error}"
        result = submit_enrollment(
            self.enrollment_session,
            self.student_repository,
            payload,
        )
        if result[0]:
            self._pending_index_ids.append(payload.get("user_id", "").strip())
            self._start_next_index()
        return result

    def _save_replacement_photos(self):
        self.require_staff()
        session = self.enrollment_session
        if session is None or session.submitted:
            return False, "No unsaved replacement photos are available."
        if session.student_id != self.enrollment_replacement_id:
            return False, "The student changed. Cancel and reopen their record."
        try:
            self._require_idle_indexing()
            self.student_repository.replace_student_samples(self.enrollment_replacement_id, tuple(session.sample_paths))
        except Exception as exc:
            return False, str(exc)
        session.mark_submitted()
        self._refresh_edited_gallery()
        self._pending_index_ids.append(self.enrollment_replacement_id)
        self._start_next_index()
        return True, "Replacement photos saved. Recognition preparation is pending."


# ------------------- MAIN APP -------------------
class App:
    def __init__(self):
        config = AppConfig.from_environment()
        config.ensure_data_directory()
        logger = configure_application_logging(config.data_dir)

        self.root = tb.Window(themename="flatly")
        self.root.title("Face Recognition Attendance")
        self.root.geometry("1100x650")
        self.root.minsize(800, 480)

        model = AppModel()
        view = AppView(self.root, controller=None)
        detector_error = None
        recognition_service = None
        try:
            recognition_service = RecognitionService.from_config(config)
            camera_service = CameraService(
                config=config,
                recognition_service=recognition_service,
            )
        except Exception as exc:
            camera_service = None
            detector_error = str(exc)
            logger.exception("Face recognition could not be initialized")

        controller = AppController(
            model, view, camera_service, config=config,
            recognition_service=recognition_service,
            staff_access=StaffAccess(config.data_dir),
        )
        self.logger = logger
        view.controller = controller
        self.kiosk = KioskFlow(controller, view.show_kiosk, controller.kiosk_ready)
        view.attach(controller, controller.staff_access, self.kiosk)
        if camera_service is None:
            view.update_detector_status(f"Detector unavailable: {detector_error}")
            view.update_camera_status("Unavailable until a face detector is configured.")

        self._closing = False
        self._camera_start_after_id = None
        self.camera_update_poller = None
        if camera_service is not None:
            view.update_detector_status(camera_service.detector_status)
            self.camera_update_poller = TkCameraUpdatePoller(
                self.root,
                camera_service,
                view.update_camera_frame,
                view.update_camera_status,
                on_identity=self._on_camera_identity,
            )
            self.camera_update_poller.start()
            if config.camera_autostart:
                self._camera_start_after_id = self.root.after(200, self._start_camera)
            else:
                view.update_camera_status("Stopped; start the camera when ready.")
        if controller.attendance_error:
            logger.info("Attendance mode unavailable: %s", controller.attendance_error)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self._background_poll_after_id = self.root.after(200, self._poll_background)

        self.controller = controller

    def on_close(self):
        if self._closing:
            return

        self._closing = True
        if self._camera_start_after_id is not None:
            try:
                self.root.after_cancel(self._camera_start_after_id)
            except tk.TclError:
                pass
            self._camera_start_after_id = None
        if self._background_poll_after_id is not None:
            try:
                self.root.after_cancel(self._background_poll_after_id)
            except tk.TclError:
                pass
            self._background_poll_after_id = None

        if self.camera_update_poller is not None:
            self.camera_update_poller.close()
        try:
            self.controller.stop_camera()
        finally:
            self.root.destroy()

    def _start_camera(self):
        self._camera_start_after_id = None
        if not self._closing:
            self.controller.start_camera()

    def _on_camera_identity(self, update):
        self.controller.view.update_recognition_test(update)
        self.kiosk.receive(update)

    def _poll_background(self):
        self._background_poll_after_id = None
        if self._closing:
            return
        try:
            self.controller.poll_indexing()
            self.controller.poll_photo_review()
            self.controller.view.tick()
            self.kiosk.tick()
        except Exception as exc:
            self.logger.exception("Background enrollment processing failed")
            if hasattr(self.controller.view, "update_enrollment_status"):
                self.controller.view.update_enrollment_status(IndexingResult(
                    "", 0, f"Background processing failed: {exc}"
                ))
        if not self._closing:
            try:
                self._background_poll_after_id = self.root.after(
                    200, self._poll_background
                )
            except tk.TclError:
                self._closing = True

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
