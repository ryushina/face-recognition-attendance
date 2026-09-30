"""Portable backup and separate-directory restore checks."""

from datetime import datetime, timezone
import json
import tempfile
import unittest
from pathlib import Path

from attendance_repository import AttendanceRepository
from attendance_service import AttendanceService
from database import Database
from recognition_evidence import StableRecognition
from recognition_service import MODEL_VERSION, PREPROCESSING_ID
from repositories import StudentRepository
from scripts.backup_data import BackupError, create_backup, restore_backup


VECTOR = (1.0,) + (0.0,) * 127


class BackupDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "live-data"
        self.source.mkdir()
        self.database = Database(self.source / "attendance.sqlite3")
        self.database.initialize()
        self.repository = StudentRepository(self.database, self.source)
        self.sample_paths = []
        for number in range(3):
            path = self.source / "assets" / "enrollment_sessions" / "session" / f"face-{number}.jpg"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"fixture image {number}".encode())
            self.sample_paths.append(path)
        self.repository.create_student("0012", "Nia", "O'Connor", self.sample_paths)
        samples = self.repository.begin_indexing("0012")
        embeddings = {
            sample.sample_id: type("Embedding", (), {
                "vector": VECTOR,
                "model_version": MODEL_VERSION,
                "preprocessing_id": PREPROCESSING_ID,
            })()
            for sample in samples
        }
        self.repository.complete_indexing("0012", embeddings)
        attendance = AttendanceService(
            self.database, "Asia/Manila",
            clock=lambda: datetime(2026, 1, 1, 16, 5, tzinfo=timezone.utc),
        )
        attendance.record(StableRecognition(
            "0012", "Nia O'Connor", 0.91, MODEL_VERSION,
            frame_id=8, captured_monotonic=5.0, consecutive_frames=3,
        ))

    def test_backup_restore_retains_students_embeddings_attendance_and_photos(self):
        backup = create_backup(self.source, self.root / "backup")
        manifest = json.loads((backup / "backup_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["samples"]), 3)
        self.assertEqual(manifest["schema_version"], 3)
        self.assertIn(MODEL_VERSION, manifest["stored_embedding_model_versions"])

        restored_path = restore_backup(backup, self.root / "restored")
        restored_database = Database(restored_path / "attendance.sqlite3")
        restored_students = StudentRepository(restored_database, restored_path)
        student = restored_students.get_student("0012")
        self.assertEqual(student.enrollment_status, "ready")
        self.assertEqual(len(student.samples), 3)
        self.assertTrue(all(
            (restored_path / sample.image_path).is_file() for sample in student.samples
        ))
        gallery = restored_students.load_compatible_gallery(MODEL_VERSION, PREPROCESSING_ID)
        self.assertEqual([entry["student_id"] for entry in gallery], ["0012"])
        records = AttendanceRepository(restored_database).list_records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].student_name, "Nia O'Connor")
        self.assertEqual(records[0].timezone_name, "Asia/Manila")

        original = self.repository.get_student("0012")
        self.assertEqual(len(original.samples), 3)
        self.assertTrue(all(path.is_file() for path in self.sample_paths))

    def test_restore_refuses_any_existing_destination(self):
        backup = create_backup(self.source, self.root / "backup")
        occupied = self.root / "occupied"
        occupied.mkdir()
        marker = occupied / "keep.txt"
        marker.write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(BackupError, "already exists"):
            restore_backup(backup, occupied)
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_corrupt_sample_is_rejected_without_creating_restore_destination(self):
        backup = create_backup(self.source, self.root / "backup")
        sample = next((backup / "samples").iterdir())
        sample.write_bytes(b"corrupt")
        destination = self.root / "restore-should-not-exist"
        with self.assertRaisesRegex(BackupError, "missing or corrupt"):
            restore_backup(backup, destination)
        self.assertFalse(destination.exists())

    def test_backup_reports_a_missing_referenced_sample(self):
        self.sample_paths[0].unlink()
        with self.assertRaisesRegex(BackupError, "missing, empty"):
            create_backup(self.source, self.root / "backup")
        self.assertFalse((self.root / "backup").exists())


if __name__ == "__main__":
    unittest.main()
