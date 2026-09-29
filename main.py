import tkinter as tk
from tkinter import ttk
import cv2
from PIL import Image, ImageTk
import threading
import time
from datetime import datetime
from view import AppView
import ttkbootstrap as tb
from ttkbootstrap.constants import *
from ttkbootstrap import Style
import cv2, time, threading, os
from datetime import datetime
from camera_service import CameraService, DetectorInitializationError
from camera_ui import TkCameraUpdatePoller
from config import AppConfig
from enrollment_session import EnrollmentSession
from database import Database
from enrollment_service import submit_enrollment
from repositories import StudentRepository
from enrollment_indexer import EnrollmentIndexer
from recognition_service import RecognitionService
# ------------------- MODEL -------------------
class AppModel:
    def __init__(self):
        self.data = "Hello, MVC with DI!"


# ------------------- VIEW -------------------


class AppController:
    def __init__(
        self, model, view, camera_service, config=None, student_repository=None,
        recognition_service=None, enrollment_indexer=None,
    ):
        self.model = model
        self.view = view
        self.camera_service = camera_service
        self.config = config or AppConfig.from_environment()
        self.enrollment_session = None
        self.student_repository = student_repository
        self.recognition_service = recognition_service
        self.enrollment_indexer = enrollment_indexer
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
        self.reload_gallery()
        self._queue_unindexed_students()

    def fetch_data(self):
        self.model.data = "Data fetched from Model!"
        print(self.model.data)

    def start_camera(self):
        if self.camera_service is None:
            return False
        return self.camera_service.start()

    def stop_camera(self):
        if self.camera_service is None:
            return True
        return self.camera_service.stop()

    def handle_login(self):
        """Logs current time and a dummy person to log.txt"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        name = "Rustan C. Lacanilo"
        log_entry = f"{current_time} - {name}\n"
        with self.config.log_file.open("a", encoding="utf-8") as log_file:
            log_file.write(log_entry)
        print(f"Login recorded: {log_entry.strip()}")

    def reload_gallery(self):
        if self.recognition_service is None or self.student_repository is None:
            return 0
        gallery = self.student_repository.load_compatible_gallery(
            self.recognition_service.model_version,
            self.recognition_service.preprocessing_id,
        )
        return self.recognition_service.set_gallery(gallery)

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
        self.reload_gallery()
        self._start_next_index()
        if hasattr(self.view, "update_enrollment_status"):
            self.view.update_enrollment_status(result)
        return result

    def handle_identity_update(self, update):
        result = update.get("identity")
        if hasattr(self.view, "update_identity_status"):
            self.view.update_identity_status(result)

    # ---------- Registration ----------
    def begin_enrollment(self):
        self.enrollment_session = EnrollmentSession(self.config.data_dir)
        return self.enrollment_session

    def update_enrollment_details(self, payload: dict):
        if self.enrollment_session is None:
            return False
        return self.enrollment_session.update_details(payload)

    def cancel_enrollment(self):
        if self.enrollment_session is None:
            return True
        cancelled = self.enrollment_session.cancel()
        self.enrollment_session = None
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


# ------------------- MAIN APP -------------------
class App:
    def __init__(self):
        config = AppConfig.from_environment()
        config.ensure_data_directory()

        self.root = tb.Window(themename="flatly")
        self.root.title("MVC with Camera Face Detection")
        self.root.geometry("1200x600")
        try:
            self.root.state('zoomed')
        except tk.TclError:
            pass

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

        controller = AppController(
            model, view, camera_service, config=config,
            recognition_service=recognition_service,
        )
        view.controller = controller
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
                on_identity=controller.handle_identity_update,
            )
            self.camera_update_poller.start()
            self._camera_start_after_id = self.root.after(200, self._start_camera)

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

    def _poll_background(self):
        self._background_poll_after_id = None
        if self._closing:
            return
        self.controller.poll_indexing()
        self._background_poll_after_id = self.root.after(200, self._poll_background)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
