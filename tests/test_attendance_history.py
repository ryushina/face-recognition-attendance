"""Attendance history filters and CSV encoding checks."""

import csv
from datetime import datetime, timezone
import tempfile
import unittest
from pathlib import Path

from attendance_export import export_attendance_csv
from attendance_repository import AttendanceHistoryError, AttendanceRepository
from attendance_service import AttendanceService
from database import Database
from recognition_evidence import StableRecognition
from recognition_service import MODEL_VERSION
from repositories import StudentRepository


class AttendanceHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = Database(self.root / "attendance.sqlite3")
        self.database.initialize()
        self.students = StudentRepository(self.database, self.root)
        sample = self.root / "sample.jpg"
        sample.write_bytes(b"fixture")
        self.students.create_student("0008", "Zoë, \"Z\"", "李", [sample])
        connection = self.database.connect()
        try:
            connection.execute("UPDATE students SET enrollment_status = 'ready'")
            connection.commit()
        finally:
            connection.close()
        self.service = AttendanceService(
            self.database, "Asia/Manila",
            clock=lambda: datetime(2026, 1, 1, 16, 2, tzinfo=timezone.utc),
        )
        self.service.record(StableRecognition(
            "0008", "Zoë, \"Z\" 李", 0.876, MODEL_VERSION,
            frame_id=31, captured_monotonic=8.0, consecutive_frames=3,
        ))
        self.repository = AttendanceRepository(self.database)

    def test_history_includes_local_time_and_supports_date_and_student_filters(self):
        records = self.repository.list_records(
            attendance_date="2026-01-02", student_id="0008"
        )
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.student_name, "Zoë, \"Z\" 李")
        self.assertEqual(record.occurred_at_local, "2026-01-02T00:02:00+08:00")
        self.assertEqual(self.repository.list_records(attendance_date="2026-01-01"), [])
        self.assertEqual(self.repository.list_records(student_id="missing"), [])

    def test_invalid_date_is_reported(self):
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            self.repository.list_records(attendance_date="2026-1-2")

    def test_csv_quotes_unicode_and_commas_and_keeps_empty_exports_valid(self):
        output = self.root / "exports" / "daily.csv"
        export_attendance_csv(self.repository.list_records(attendance_date="2026-01-02"), output)
        with output.open("r", encoding="utf-8-sig", newline="") as source:
            rows = list(csv.DictReader(source))
        self.assertEqual(rows[0]["student_name"], "Zoë, \"Z\" 李")
        self.assertEqual(rows[0]["student_id"], "0008")

        empty = self.root / "empty.csv"
        export_attendance_csv([], empty)
        with empty.open("r", encoding="utf-8-sig", newline="") as source:
            self.assertEqual(list(csv.DictReader(source)), [])

    def test_export_write_error_is_reported(self):
        destination = self.root / "directory"
        destination.mkdir()
        with self.assertRaises(IsADirectoryError):
            export_attendance_csv([], destination)


if __name__ == "__main__":
    unittest.main()
