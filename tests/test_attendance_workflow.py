"""Controller-level guardrails for the operator attendance workflow."""

from datetime import datetime, timezone
import tempfile
import unittest
from pathlib import Path

from attendance_service import AttendanceError, AttendanceService
from config import AppConfig
from database import Database
from main import AppController, AppModel
from recognition_service import MODEL_VERSION, MatchResult
from repositories import StudentRepository


class FakeCamera:
    running = True

    def stop(self):
        self.running = False
        return True

    def start(self):
        self.running = True
        return True


class FakeView:
    def __init__(self):
        self.mode = []
        self.identity = []
        self.progress = []
        self.results = []

    def update_attendance_mode(self, active, message):
        self.mode.append((active, message))

    def update_identity_status(self, result):
        self.identity.append(result)

    def update_attendance_progress(self, count, required, result):
        self.progress.append((count, required, result))

    def update_attendance_result(self, attendance, display_name):
        self.results.append((attendance, display_name))


class AttendanceWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = AppConfig.from_environment({
            "ATTENDANCE_DATA_DIR": str(self.root),
            "ATTENDANCE_TIMEZONE": "Asia/Manila",
            "ATTENDANCE_STABLE_IDENTITY_FRAMES": "3",
        })
        self.database = Database(self.root / "attendance.sqlite3")
        self.database.initialize()
        self.repository = StudentRepository(self.database, self.root)
        self.sample = self.root / "sample.jpg"
        self.sample.write_bytes(b"test image")
        self.repository.create_student("0007", "Mí", "O'Neil", [self.sample])
        connection = self.database.connect()
        try:
            connection.execute("UPDATE students SET enrollment_status = 'ready'")
            connection.commit()
        finally:
            connection.close()
        self.now = [20.0]
        self.view = FakeView()
        self.camera = FakeCamera()
        self.service = AttendanceService(
            self.database,
            "Asia/Manila",
            clock=lambda: datetime(2026, 2, 1, 1, 0, tzinfo=timezone.utc),
        )
        self.controller = AppController(
            AppModel(), self.view, self.camera, config=self.config,
            student_repository=self.repository, attendance_service=self.service,
            monotonic_clock=lambda: self.now[0],
        )
        self.match = MatchResult(
            "recognized", "0007", "Mí O'Neil", 0.91,
            model_version=MODEL_VERSION,
        )

    def send(self, frame_id, captured=None, result=None):
        captured = self.now[0] if captured is None else captured
        return self.controller.handle_identity_update({
            "identity": self.match if result is None else result,
            "frame_id": frame_id,
            "captured_monotonic": captured,
        })

    def test_stale_queued_frame_cannot_authorize_attendance(self):
        self.assertTrue(self.controller.start_attendance())
        self.send(1, captured=19.9)
        self.send(2)
        self.assertEqual(self.view.results, [])

    def test_three_distinct_frames_record_once_and_pause_blocks_writes(self):
        self.assertTrue(self.controller.start_attendance())
        self.send(1)
        self.send(2)
        self.assertEqual(self.view.results, [])
        recorded = self.send(3)
        self.assertEqual(recorded.status, "recorded")
        duplicate = self.send(4)
        self.assertEqual(duplicate.status, "already_recorded")
        self.assertEqual(len(self.view.results), 2)

        self.controller.pause_attendance()
        self.send(5)
        connection = self.database.connect()
        try:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM attendance").fetchone()[0], 1
            )
        finally:
            connection.close()

    def test_unknown_multiple_face_and_camera_loss_reset_candidate(self):
        self.assertTrue(self.controller.start_attendance())
        self.send(1)
        self.send(2, result=MatchResult("ambiguous", message="multiple faces"))
        self.send(3)
        self.send(4)
        self.camera.running = False
        self.send(5)
        self.assertFalse(self.controller.attendance_active)
        self.camera.running = True
        self.assertTrue(self.controller.start_attendance())
        self.send(6)
        self.send(7)
        self.assertEqual(self.view.results, [])
        self.send(8)
        self.assertEqual(self.view.results[0][0].status, "recorded")

    def test_enrollment_pauses_attendance_until_operator_restarts_it(self):
        self.assertTrue(self.controller.start_attendance())
        self.controller.begin_enrollment()
        self.assertFalse(self.controller.attendance_active)
        self.send(1)
        self.assertEqual(self.view.results, [])
        self.assertTrue(self.controller.cancel_enrollment())

    def test_timezone_or_camera_missing_keeps_attendance_paused(self):
        camera = FakeCamera()
        config = AppConfig.from_environment({"ATTENDANCE_DATA_DIR": str(self.root)})
        view = FakeView()
        unavailable = AppController(
            AppModel(), view, camera, config=config,
            student_repository=self.repository,
        )
        self.assertFalse(unavailable.start_attendance())
        self.assertIn("ATTENDANCE_TIMEZONE", view.mode[-1][1])

        self.camera.running = False
        self.assertFalse(self.controller.start_attendance())
        self.assertIn("Start the camera", self.view.mode[-1][1])

    def test_camera_control_stops_and_restarts_with_attendance_paused(self):
        self.assertTrue(self.controller.start_attendance())
        self.assertTrue(self.controller.toggle_camera())
        self.assertFalse(self.camera.running)
        self.assertFalse(self.controller.attendance_active)
        self.assertTrue(self.controller.toggle_camera())
        self.assertTrue(self.camera.running)
        self.assertFalse(self.controller.attendance_active)

    def test_storage_failure_pauses_and_never_reports_success(self):
        class FailingService:
            def record(self, evidence):
                raise AttendanceError("simulated read-only database")

        view = FakeView()
        failing = AppController(
            AppModel(), view, FakeCamera(), config=self.config,
            student_repository=self.repository, attendance_service=FailingService(),
            monotonic_clock=lambda: self.now[0],
        )
        self.assertTrue(failing.start_attendance())
        for frame_id in (1, 2, 3):
            failing.handle_identity_update({
                "identity": self.match, "frame_id": frame_id,
                "captured_monotonic": self.now[0],
            })
        self.assertFalse(failing.attendance_active)
        self.assertEqual(view.results, [])
        self.assertIn("simulated read-only", view.mode[-1][1])


if __name__ == "__main__":
    unittest.main()
