"""Non-destructive legacy importer tests using fixture CSVs and databases."""

import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from database import Database
from scripts.import_legacy import LegacyImportError, run_import


@contextmanager
def closing_transaction(connection_factory):
    connection = connection_factory()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


class LegacyImporterTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.source = self.root / "users.txt"
        self.database_path = self.root / "data" / "attendance.sqlite3"
        self.database = Database(self.database_path)
        self.photo_root = self.root / "legacy-photos"
        self.photo_root.mkdir()

    def write_source(self, rows):
        self.source.write_text(
            "user_id,first_name,last_name,photo_dir\n" + rows,
            encoding="utf-8",
        )

    def test_default_preview_reports_missing_images_without_creating_database(self):
        self.write_source("00123,Ana,Santos,missing/person\n")
        original = self.source.read_bytes()

        report = run_import(self.source, self.database, photo_root=self.photo_root)

        self.assertTrue(report.dry_run)
        self.assertEqual(len(report.results), 1)
        self.assertEqual(report.results[0].status, "would-import")
        self.assertIn("Photo directory is missing", report.results[0].message)
        self.assertEqual(report.results[0].sample_count, 0)
        self.assertFalse(self.database_path.exists())
        self.assertEqual(self.source.read_bytes(), original)

    def test_reports_malformed_duplicate_and_missing_photo_rows(self):
        existing_photos = self.photo_root / "student"
        existing_photos.mkdir()
        (existing_photos / "face.jpg").write_bytes(b"image")
        (existing_photos / "notes.txt").write_text("ignore", encoding="utf-8")
        self.write_source(
            "00123,Ana,Santos,student\n"
            "00123,Duplicate,Student,student\n"
            ",Missing,ID,student\n"
            "00456,Noor,Ali,does-not-exist\n"
            "00789,Extra,Column,student,unexpected\n"
        )

        report = run_import(self.source, self.database, photo_root=self.photo_root)

        self.assertEqual(
            [result.status for result in report.results],
            ["would-import", "duplicate-source", "malformed", "would-import", "malformed"],
        )
        self.assertEqual(report.results[0].sample_count, 1)
        self.assertIn("Photo directory is missing", report.results[3].message)
        self.assertIn("Missing required field", report.results[2].message)
        self.assertIn("more values", report.results[4].message)
        self.assertFalse(self.database_path.exists())

    def test_apply_is_explicit_and_repeated_import_skips_existing_id(self):
        image_dir = self.photo_root / "student"
        image_dir.mkdir()
        sample = image_dir / "face.jpg"
        sample.write_bytes(b"fixture-image")
        self.source.write_text(
            "user_id,first_name,middle_name,last_name,guardian_fullname,guardian_phone,photo_dir\n"
            "000123,Ana,María,Santos,José Santos,+63 900 123 4567,student\n",
            encoding="utf-8",
        )
        original = self.source.read_bytes()

        first_report = run_import(
            self.source,
            self.database,
            photo_root=self.photo_root,
            data_dir=self.database_path.parent,
            apply=True,
        )
        second_report = run_import(
            self.source,
            self.database,
            photo_root=self.photo_root,
            data_dir=self.database_path.parent,
            apply=True,
        )

        self.assertFalse(first_report.dry_run)
        self.assertEqual(first_report.results[0].status, "imported")
        self.assertEqual(second_report.results[0].status, "already-exists")
        self.assertEqual(self.source.read_bytes(), original)
        with closing_transaction(self.database.connect) as connection:
            student = connection.execute(
                "SELECT student_id, first_name, middle_name, last_name, "
                "guardian_full_name, guardian_phone, enrollment_status "
                "FROM students"
            ).fetchone()
            samples = connection.execute("SELECT image_path FROM face_samples").fetchall()
        self.assertEqual(student["student_id"], "000123")
        self.assertEqual(student["first_name"], "Ana")
        self.assertEqual(student["middle_name"], "María")
        self.assertEqual(student["last_name"], "Santos")
        self.assertEqual(student["guardian_full_name"], "José Santos")
        self.assertEqual(student["guardian_phone"], "+63 900 123 4567")
        self.assertEqual(student["enrollment_status"], "pending")
        self.assertEqual(len(samples), 1)
        self.assertEqual(Path(samples[0]["image_path"]), sample.resolve())

    def test_missing_photo_directory_can_import_pending_student_without_samples(self):
        self.write_source("0099,Noor,Ali,old-photos/noor\n")

        report = run_import(
            self.source,
            self.database,
            photo_root=self.photo_root,
            data_dir=self.database_path.parent,
            apply=True,
        )

        self.assertEqual(report.results[0].status, "imported")
        self.assertEqual(report.results[0].sample_count, 0)
        self.assertIn("Photo directory is missing", report.results[0].message)
        with closing_transaction(self.database.connect) as connection:
            student = connection.execute(
                "SELECT enrollment_status FROM students WHERE student_id = ?", ("0099",)
            ).fetchone()
            sample_count = connection.execute(
                "SELECT COUNT(*) FROM face_samples"
            ).fetchone()[0]
        self.assertEqual(student["enrollment_status"], "pending")
        self.assertEqual(sample_count, 0)

    def test_invalid_header_is_reported_without_writing(self):
        self.source.write_text("name,grade\nAna,3\n", encoding="utf-8")

        with self.assertRaisesRegex(LegacyImportError, "must have"):
            run_import(self.source, self.database, photo_root=self.photo_root)

        self.assertFalse(self.database_path.exists())


if __name__ == "__main__":
    unittest.main()
