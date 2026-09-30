"""Opt-in Tk layout/integration checks using synthetic data, never a camera."""

import logging
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kiosk_flow import SCREENS, KioskScreen


@unittest.skipUnless(os.environ.get("ATTENDANCE_RUN_GUI_TESTS") == "1", "Opt-in Tk display checks")
class KioskUiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {"ATTENDANCE_DATA_DIR": self.temp.name, "ATTENDANCE_CAMERA_AUTOSTART": "false", "ATTENDANCE_TIMEZONE": "Asia/Manila"})
        self.env.start()
        self.addCleanup(self.env.stop)
        from main import App
        self.app = App()
        self.app.root.after_cancel(self.app._background_poll_after_id)
        self.app._background_poll_after_id = None
        if self.app.camera_update_poller:
            self.app.camera_update_poller.close()
        self.view = self.app.controller.view
        self.addCleanup(self.close)

    def close(self):
        self.app.root.update_idletasks()
        self.app.on_close()
        logger = logging.getLogger("face_attendance")
        for handler in list(logger.handlers):
            if getattr(handler, "_attendance_handler", False):
                logger.removeHandler(handler)
                handler.close()

    def assert_inside(self, widget):
        root = self.app.root
        left = widget.winfo_rootx() - root.winfo_rootx()
        top = widget.winfo_rooty() - root.winfo_rooty()
        self.assertGreaterEqual(left, 0)
        self.assertGreaterEqual(top, 0)
        self.assertLessEqual(left + widget.winfo_width(), root.winfo_width())
        self.assertLessEqual(top + widget.winfo_height(), root.winfo_height())

    def test_every_student_state_fits_small_window_and_errors_stay_private(self):
        for scaling in (96 / 72, 120 / 72, 144 / 72):
            self.app.root.tk.call("tk", "scaling", scaling)
            for size in ("800x480", "1100x650"):
                self.app.root.geometry(size)
                screens = dict(SCREENS)
                screens["recorded"] = KioskScreen("recorded", "You're checked in, " + "W" * 30, "You can step aside for the next student.", 3, "Attendance saved at 07:42 AM")
                screens["duplicate"] = KioskScreen("recorded", "You're already checked in today", "You can step aside for the next student.", 3, "Attendance saved at 07:42 AM")
                for name, screen in screens.items():
                    with self.subTest(scaling=scaling, size=size, state=name):
                        self.view.show_kiosk(screen)
                        self.view.update_camera_status("technical exception " * 300)
                        self.app.root.update()
                        for widget in (self.view.title, self.view.instruction, self.view.detail, self.view.help_button, self.view.staff_button, *self.view.steps):
                            self.assert_inside(widget)
                        self.assertNotIn("technical exception", self.view.instruction.cget("text"))

    def test_staff_lock_closes_history_and_preserves_main_actions(self):
        self.app.root.geometry("800x480")
        self.app.controller.staff_access.create("Synthetic staff test password")
        self.view._enter_staff()
        self.app.root.update()
        self.assert_inside(self.view.return_button)
        self.view.open_attendance_history()
        self.app.root.update()
        self.assertTrue(self.view.windows[-1].winfo_exists())
        self.app.controller.staff_access.lock()
        self.view.tick()
        self.app.root.update()
        self.assertFalse(self.view.staff_mode)
        self.assertEqual(self.view.windows, [])
        self.assert_inside(self.view.staff_button)

    def test_enrollment_steps_and_disabled_capture_without_camera(self):
        self.app.controller.staff_access.create("Synthetic staff test password")
        self.view._enter_staff()
        self.view.begin_enrollment()
        self.view.entries["user_id"].insert(0, "synthetic-1")
        self.view.entries["first_name"].insert(0, "Test")
        self.view.entries["last_name"].insert(0, "Student")
        self.app.controller.update_enrollment_details({key: entry.get() for key, entry in self.view.entries.items()})
        self.view._enrollment_photos()
        self.view.tick()
        self.app.root.update()
        self.assertIn("disabled", self.view.capture_button.state())
        self.assertEqual(self.app.controller.enrollment_session.accepted_count, 0)
        self.assertFalse(self.app.controller.camera_service.running)

    def test_guided_enrollment_reaches_ready_and_kiosk_records(self):
        import numpy as np
        import cv2
        import time
        from enrollment_indexer import EnrollmentIndexer
        from kiosk_settings import save_preferences
        from recognition_service import MatchResult
        from tests.test_desktop_workflow import SyntheticFrame, make_recognition_service

        controller = self.app.controller
        controller.staff_access.create("Synthetic staff test password")
        controller.recognition_service = make_recognition_service()
        controller.enrollment_indexer = EnrollmentIndexer(controller.student_repository, controller.recognition_service, controller.config.data_dir, image_reader=lambda path: SyntheticFrame())
        self.view._enter_staff()
        self.view.begin_enrollment()
        controller.update_enrollment_details({"user_id": "synthetic-2", "first_name": "Test", "last_name": "Student"})
        self.view._enrollment_photos()

        def synthetic_capture(directory, **kwargs):
            target = Path(directory)
            target.mkdir(parents=True, exist_ok=True)
            photo = target / f"synthetic-{controller.enrollment_session.accepted_count}.jpg"
            cv2.imwrite(str(photo), np.full((100, 100, 3), 120, dtype=np.uint8))
            return True, str(photo)
        controller.camera_service.capture_face = synthetic_capture
        for _ in range(3):
            self.view.capture()
        self.view._enrollment_review()
        self.view.save_student()
        controller.enrollment_indexer._thread.join(timeout=5)
        controller.poll_indexing()
        self.assertEqual(controller.gallery_size, 1)
        self.assertEqual(controller.student_repository.get_student("synthetic-2").enrollment_status, "ready")
        self.assertIn("Student ready", self.view.staff_note.cget("text"))
        save_preferences(controller.config.data_dir, "Asia/Manila", 0)
        def fake_start():
            controller.camera_service.running = True
            return True
        controller.camera_service.start = fake_start
        self.view.leave_staff(True)
        for frame_id in range(1, 6):
            self.app.kiosk.receive({"identity": MatchResult("recognized", "synthetic-2", "Test Student", .95), "frame_id": frame_id, "captured_monotonic": time.monotonic()})
        self.app.root.update()
        self.assertEqual(self.app.kiosk.screen.state, "recorded")
        self.assertIn("You're checked in", self.view.title.cget("text"))
        self.assertFalse(controller.staff_access.unlocked)

        # Leaving while the confirmation is visible must reset the real Tk
        # screen when that confirmation ends, without another exit gesture.
        confirmation_end = self.app.kiosk.hold_until
        clock = [confirmation_end - 3]
        self.app.kiosk.clock = lambda: clock[0]
        controller._monotonic_clock = lambda: clock[0]
        for frame_id, elapsed in enumerate((.2, .9, 1.6, 2.3, 2.9), 6):
            clock[0] = confirmation_end - 3 + elapsed
            self.app.kiosk.receive({"identity": MatchResult("unknown", reason="no_face"), "frame_id": frame_id, "captured_monotonic": clock[0]})
        clock[0] = confirmation_end
        self.app.kiosk.tick()
        self.app.root.update()
        self.assertEqual(self.view.title.cget("text"), "Look at the camera")
        for frame_id in range(11, 14):
            self.app.kiosk.receive({"identity": MatchResult("recognized", "synthetic-2", "Test Student", .95), "frame_id": frame_id, "captured_monotonic": clock[0]})
        self.app.root.update()
        self.assertIn("already checked in", self.view.title.cget("text"))

    def test_live_recognition_diagnostics_are_private_and_do_not_record_attendance(self):
        import time
        from recognition_service import MatchResult

        controller = self.app.controller
        controller.staff_access.create("Synthetic staff test password")
        self.view._enter_staff()
        self.view.diagnostics()
        controller.camera_service.running = True
        camera = controller.camera_service
        self.app.root.geometry("800x480")
        cases = (
            (MatchResult("unknown", reason="no_face"), "No usable face"),
            (MatchResult("ambiguous", reason="multiple_faces"), "Multiple faces"),
            (MatchResult("unknown", reason="gallery_empty"), "No students loaded"),
            (MatchResult("unknown", score=.31, runner_up_score=.1, reason="below_similarity"), "Best similarity: 0.310 / required: 0.500"),
            (MatchResult("ambiguous", score=.8, runner_up_score=.76, reason="insufficient_margin"), "Separation: 0.040 / required: 0.080"),
            (MatchResult("recognized", "private-test", "Private Test Student", .95), "Matched: Private Test Student"),
        )
        for frame_id, (result, expected) in enumerate(cases, 1):
            update = {"identity": result, "frame_id": frame_id, "captured_monotonic": time.monotonic(), "frame": object()}
            self.app._on_camera_identity(update)
            self.app.root.update()
            self.assertIn(expected, self.view._recognition_test_label.cget("text"))
            self.assertFalse(controller.attendance_active)
            self.assertEqual(controller.get_attendance_history(), [])
            self.assertNotIn("Private Test Student", self.view.title.cget("text"))
            self.assertEqual(len(self.view._recognition_test_update), 2)

        captured = self.view._recognition_test_update[1]
        with patch("kiosk_view.time.monotonic", return_value=captured + 2):
            self.view.tick()
        self.assertIn("stale", self.view._recognition_test_label.cget("text"))
        self.assertIsNone(self.view._recognition_test_update)

        camera.running = False
        self.view.tick()
        self.assertIn("Camera unavailable", self.view._recognition_test_label.cget("text"))
        controller.staff_access.lock()
        self.view.tick()
        self.app._on_camera_identity({"identity": cases[-1][0], "frame_id": 100, "captured_monotonic": time.monotonic()})
        self.assertIsNone(self.view._recognition_test_label)
        self.assertIsNone(self.view._recognition_test_update)
        self.assertFalse(self.view.staff_mode)
