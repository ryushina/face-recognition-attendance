from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import tempfile
import threading
import unittest
from pathlib import Path

from attendance_service import AttendanceError, AttendanceService, TimezoneConfigError
from database import Database
from recognition_service import MODEL_VERSION
from recognition_evidence import StableRecognition
from repositories import StudentRepository


class AttendanceServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.database = Database(self.root / "attendance.sqlite3")
        self.database.initialize()
        self.repository = StudentRepository(self.database, self.root)
        self.sample = self.root / "sample.jpg"
        self.sample.write_bytes(b"fixture")
        self.repository.create_student("0007", "Lin", "Tan", [self.sample])
        connection = self.database.connect()
        try:
            connection.execute("UPDATE students SET enrollment_status = 'ready'")
            connection.commit()
        finally:
            connection.close()
        self.current = [datetime(2026, 1, 1, 15, 59, tzinfo=timezone.utc)]
        self.service = AttendanceService(
            self.database, "Asia/Manila", clock=lambda: self.current[0]
        )

    @staticmethod
    def evidence(student_id="0007", frame_id=12, **overrides):
        fields = dict(
            student_id=student_id, display_name="Lin Tan", score=0.91,
            model_version=MODEL_VERSION, frame_id=frame_id,
            captured_monotonic=10.0, consecutive_frames=3,
        )
        fields.update(overrides)
        return StableRecognition(**fields)

    def test_once_per_local_day_persists_across_service_restart(self):
        first = self.service.record(self.evidence())
        self.assertEqual(first.status, "recorded")
        self.assertEqual(first.attendance_date, "2026-01-01")
        self.assertEqual(first.occurred_at_utc, "2026-01-01T15:59:00.000Z")

        restarted = AttendanceService(
            Database(self.database.path), "Asia/Manila", clock=lambda: self.current[0]
        )
        duplicate = restarted.record(self.evidence(frame_id=99))
        self.assertEqual(duplicate.status, "already_recorded")
        self.assertEqual(duplicate.attendance_id, first.attendance_id)

        self.current[0] = datetime(2026, 1, 1, 16, 1, tzinfo=timezone.utc)
        next_day = restarted.record(self.evidence(frame_id=100))
        self.assertEqual(next_day.status, "recorded")
        self.assertEqual(next_day.attendance_date, "2026-01-02")

    def test_concurrent_duplicates_cannot_insert_twice(self):
        barrier = threading.Barrier(2)

        def write(frame_id):
            service = AttendanceService(
                Database(self.database.path), "Asia/Manila", clock=lambda: self.current[0]
            )
            barrier.wait(timeout=2)
            return service.record(self.evidence(frame_id=frame_id))

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(write, (1, 2)))
        self.assertEqual(sorted(result.status for result in results), ["already_recorded", "recorded"])
        connection = self.database.connect()
        try:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM attendance").fetchone()[0], 1)
        finally:
            connection.close()

    def test_timezone_and_evidence_are_required(self):
        for value in (None, "Mars/Olympus"):
            with self.subTest(timezone=value), self.assertRaises(TimezoneConfigError):
                AttendanceService(self.database, value)
        naive = AttendanceService(self.database, "UTC", clock=lambda: datetime(2026, 1, 1))
        with self.assertRaisesRegex(AttendanceError, "timezone-aware"):
            naive.record(self.evidence())
        with self.assertRaisesRegex(AttendanceError, "incompatible"):
            self.service.record(self.evidence(model_version="old-model"))
        with self.assertRaisesRegex(AttendanceError, "ready"):
            self.service.record(self.evidence(student_id="missing"))


if __name__ == "__main__":
    unittest.main()
