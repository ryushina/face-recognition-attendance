from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from attendance_service import AttendanceError, AttendanceService
from config import AppConfig
from database import Database
from kiosk_flow import KioskFlow
from kiosk_settings import StaffAccess, StaffAccessError
from main import AppController, AppModel
from recognition_service import MatchResult
from repositories import StudentRepository
from tests.test_attendance_workflow import FakeCamera, FakeView


class KioskFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        config = AppConfig.from_environment({"ATTENDANCE_DATA_DIR": str(self.path), "ATTENDANCE_TIMEZONE": "Asia/Manila"})
        self.database = Database(self.path / "attendance.sqlite3")
        self.database.initialize()
        repo = StudentRepository(self.database, self.path)
        sample = self.path / "synthetic.jpg"
        sample.write_bytes(b"synthetic")
        repo.create_student("17", "Maya", "Test", [sample], enrollment_status="ready")
        self.clock = [50.0]
        self.controller = AppController(AppModel(), FakeView(), FakeCamera(), config=config, student_repository=repo,
            attendance_service=AttendanceService(self.database, "Asia/Manila", clock=lambda: datetime(2026, 9, 29, tzinfo=timezone.utc)), monotonic_clock=lambda: self.clock[0])
        self.screens = []
        self.ready = True
        self.flow = KioskFlow(self.controller, self.screens.append, lambda: self.ready, clock=lambda: self.clock[0])
        self.match = MatchResult("recognized", "17", "Maya Test", 0.95)
        self.frame = 0

    def send(self, result=None, age=0):
        self.frame += 1
        self.flow.receive({"identity": result or self.match, "frame_id": self.frame, "captured_monotonic": self.clock[0] - age})

    def record(self):
        for _ in range(3):
            self.send()
        self.assertEqual(self.flow.screen.state, "recorded")

    def test_success_is_saved_and_held_until_fresh_face_departure(self):
        self.send()
        self.assertEqual(self.flow.screen.state, "checking")
        self.send()
        self.assertEqual(self.controller.get_attendance_history(), [])
        self.send()
        self.assertEqual(self.flow.screen.state, "recorded")
        self.assertEqual(len(self.controller.get_attendance_history()), 1)
        for _ in range(5):
            self.send()
        self.assertEqual(len(self.controller.view.results), 1)
        self.clock[0] += 3.1
        self.send()
        self.flow.tick()
        self.assertEqual(self.flow.screen.state, "depart")
        self.assertNotIn("Maya", self.flow.screen.title)
        no_face = MatchResult("unknown", reason="no_face")
        self.send(no_face)
        self.clock[0] += .7
        self.send(no_face)
        self.assertEqual(self.flow.screen.state, "ready")
        for _ in range(3):
            self.send()
        self.assertIn("already", self.flow.screen.title)
        self.assertEqual(len(self.controller.get_attendance_history()), 1)

    def test_stale_frames_unknown_and_multiple_faces_never_succeed(self):
        for _ in range(4):
            self.send(age=5)
        self.assertFalse(self.controller.attendance_active)
        self.send(MatchResult("unknown"))
        self.assertEqual(self.flow.screen.state, "unknown")
        self.send(MatchResult("ambiguous", reason="multiple_faces"))
        self.assertEqual(self.flow.screen.state, "multiple")
        self.assertEqual(self.controller.get_attendance_history(), [])

    def test_departure_during_confirmation_is_remembered_when_student_returns(self):
        self.record()
        no_face = MatchResult("unknown", reason="no_face")
        for elapsed in (.2, .9):
            self.clock[0] = 50 + elapsed
            self.send(no_face)
            self.assertEqual(self.flow.screen.state, "recorded")
        for elapsed in (1.2, 2.0, 2.8):
            self.clock[0] = 50 + elapsed
            self.send()
            self.flow.tick()
            self.assertEqual(self.flow.screen.state, "recorded")
        self.assertEqual(len(self.controller.view.results), 1)

        self.clock[0] = 53.1
        self.send()
        self.assertEqual(self.flow.screen.state, "checking")
        self.assertEqual(len(self.controller.view.results), 1)
        self.send()
        self.send()
        self.assertIn("already", self.flow.screen.title)
        self.assertEqual(len(self.controller.get_attendance_history()), 1)

    def test_empty_view_during_confirmation_returns_directly_to_ready(self):
        self.record()
        no_face = MatchResult("unknown", reason="no_face")
        for elapsed in (.2, .9, 1.6, 2.3, 2.9):
            self.clock[0] = 50 + elapsed
            self.send(no_face)
        self.clock[0] = 53.0
        self.flow.tick()
        self.assertEqual(self.flow.screen.state, "ready")
        self.assertNotIn("depart", [screen.state for screen in self.screens])
        self.assertEqual(len(self.controller.view.results), 1)

    def test_brief_detection_loss_does_not_count_as_departure(self):
        self.record()
        self.clock[0] = 50.2
        self.send(MatchResult("unknown", reason="no_face"))
        self.clock[0] = 50.4
        self.send()
        for elapsed in (1.0, 2.0, 3.1, 4.0):
            self.clock[0] = 50 + elapsed
            self.send()
            self.flow.tick()
        self.assertEqual(self.flow.screen.state, "depart")
        self.assertEqual(len(self.controller.view.results), 1)

    def test_camera_stall_after_early_departure_still_requires_staff_recovery(self):
        self.record()
        no_face = MatchResult("unknown", reason="no_face")
        for elapsed in (.2, .9):
            self.clock[0] = 50 + elapsed
            self.send(no_face)
        self.clock[0] = 53.1
        self.flow.tick()
        self.assertEqual(self.flow.screen.state, "unavailable")
        self.assertFalse(self.controller.attendance_active)

    def test_camera_loss_clears_confirmation_and_requires_staff_resume(self):
        self.record()
        self.controller.camera_service.running = False
        self.flow.receive({"identity": None})
        self.assertEqual(self.flow.screen.state, "unavailable")
        self.assertFalse(self.controller.attendance_active)
        self.controller.camera_service.running = True
        self.send()
        self.assertEqual(self.flow.screen.state, "unavailable")
        self.flow.resume()
        self.send()
        self.assertEqual(self.flow.screen.state, "checking")

    def test_stalled_feed_pauses_in_tick_and_clears_name(self):
        self.record()
        self.clock[0] += 2
        self.flow.tick()
        self.assertEqual(self.flow.screen.state, "unavailable")
        self.assertFalse(self.controller.attendance_active)

    def test_storage_failure_never_shows_success(self):
        def fail(_evidence):
            raise AttendanceError("disk full")
        self.controller.attendance_service.record = fail
        for _ in range(3):
            self.send()
        self.assertEqual(self.flow.screen.state, "save_error")
        self.assertFalse(self.flow.requested)
        self.assertFalse(any(screen.state == "recorded" for screen in self.screens))

    def test_staff_and_incomplete_setup_block_automatic_attendance(self):
        self.ready = False
        self.send()
        self.assertEqual(self.flow.screen.state, "setup")
        self.ready = True
        self.flow.in_staff = True
        for _ in range(4):
            self.send()
        self.assertFalse(self.controller.attendance_active)
        self.assertEqual(self.controller.get_attendance_history(), [])

    def test_staff_operations_require_current_session(self):
        self.controller.staff_access = StaffAccess(self.path)
        for operation in (self.controller.get_attendance_history, self.controller.begin_enrollment, self.controller.retry_indexing,
                          lambda: self.controller.handle_register({}), lambda: self.controller.handle_capture_image({}),
                          lambda: self.controller.apply_kiosk_settings("Asia/Manila", 0)):
            with self.assertRaises(StaffAccessError):
                operation()
        self.controller.staff_access.create("staff password for test")
        self.assertEqual(self.controller.get_attendance_history(), [])
        self.controller.staff_access.lock()
        with self.assertRaises(StaffAccessError):
            self.controller.export_attendance_history(self.path / "blocked.csv")
        self.assertFalse((self.path / "blocked.csv").exists())
