"""Student repository validation, persistence, and rollback tests."""

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from database import Database
from repositories import (
    DuplicateStudentError,
    StudentRepository,
    StudentRepositoryError,
    StudentValidationError,
)


class StudentRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.data_dir = self.root / "data"
        self.data_dir.mkdir()
        self.image_dir = self.data_dir / "assets"
        self.image_dir.mkdir()
        self.database = Database(self.data_dir / "attendance.sqlite3")
        self.database.initialize()
        self.repository = StudentRepository(self.database, self.data_dir)

    def make_sample(self, name="face.jpg", contents=b"image bytes"):
        path = self.image_dir / name
        path.write_bytes(contents)
        return path

    def create(self, student_id="00123456", sample_paths=None, **overrides):
        return self.repository.create_student(
            student_id=student_id,
            first_name=overrides.pop("first_name", "Ana"),
            last_name=overrides.pop("last_name", "Santos"),
            sample_paths=(sample_paths if sample_paths is not None else [self.make_sample()]),
            **overrides,
        )

    def test_create_get_list_and_samples_preserve_all_registration_fields(self):
        sample_a = self.make_sample("a.jpg")
        sample_b = self.make_sample("b.jpg")
        created = self.create(
            sample_paths=[sample_a, sample_b],
            middle_name="María",
            guardian_full_name="José Santos",
            guardian_phone="+63 900 123 4567 ext. 2",
        )

        loaded = self.repository.get_student("00123456")
        students = self.repository.list_students()
        samples = self.repository.get_samples("00123456")

        self.assertEqual(created.student_id, "00123456")
        self.assertEqual(loaded.first_name, "Ana")
        self.assertEqual(loaded.middle_name, "María")
        self.assertEqual(loaded.last_name, "Santos")
        self.assertEqual(loaded.guardian_full_name, "José Santos")
        self.assertEqual(loaded.guardian_phone, "+63 900 123 4567 ext. 2")
        self.assertEqual(loaded.enrollment_status, "pending")
        self.assertEqual(len(loaded.created_at), len("2026-09-29T00:00:00.000Z"))
        self.assertEqual([student.student_id for student in students], ["00123456"])
        self.assertEqual(len(loaded.samples), 2)
        self.assertEqual(len(samples), 2)
        self.assertEqual(samples[0].image_path, "assets/a.jpg")
        self.assertEqual(samples[1].image_path, "assets/b.jpg")

    def test_optional_fields_can_be_empty_and_missing_student_returns_none(self):
        student = self.create(
            student_id="0007",
            middle_name=None,
            guardian_full_name=None,
            guardian_phone=None,
        )

        self.assertEqual(student.student_id, "0007")
        self.assertIsNone(student.middle_name)
        self.assertIsNone(student.guardian_full_name)
        self.assertIsNone(student.guardian_phone)
        self.assertIsNone(self.repository.get_student("absent"))

    def test_duplicate_student_id_returns_a_clear_error_without_partial_rows(self):
        sample = self.make_sample()
        self.create(sample_paths=[sample])
        second_sample = self.make_sample("second.jpg")

        with self.assertRaisesRegex(DuplicateStudentError, "already registered"):
            self.create(sample_paths=[second_sample])

        self.assertEqual(len(self.repository.list_students()), 1)
        self.assertEqual(len(self.repository.get_samples("00123456")), 1)

    def test_blank_required_fields_are_rejected_before_database_write(self):
        sample = self.make_sample()
        invalid_records = (
            {"student_id": "  "},
            {"first_name": "\t"},
            {"last_name": ""},
        )
        for values in invalid_records:
            with self.subTest(values=values):
                arguments = {
                    "student_id": "valid-id",
                    "first_name": "Ana",
                    "last_name": "Santos",
                    "sample_paths": [sample],
                }
                arguments.update(values)
                with self.assertRaises(StudentValidationError):
                    self.repository.create_student(**arguments)

        self.assertEqual(self.repository.list_students(), [])

    def test_nonexistent_directory_and_empty_sample_files_are_rejected(self):
        missing = self.image_dir / "missing.jpg"
        with self.assertRaisesRegex(StudentValidationError, "does not exist"):
            self.create(sample_paths=[missing])

        with self.assertRaisesRegex(StudentValidationError, "not a file"):
            self.create(sample_paths=[self.image_dir])

        empty = self.make_sample("empty.jpg", contents=b"")
        with self.assertRaisesRegex(StudentValidationError, "is empty"):
            self.create(sample_paths=[empty])

        with self.assertRaisesRegex(StudentValidationError, "At least one"):
            self.create(sample_paths=[])

        self.assertEqual(self.repository.list_students(), [])

    def test_duplicate_sample_path_constraint_rolls_back_student_insert(self):
        sample = self.make_sample()
        self.create(student_id="first", sample_paths=[sample])

        with self.assertRaisesRegex(StudentRepositoryError, "already linked"):
            self.create(student_id="second", sample_paths=[sample])

        self.assertIsNone(self.repository.get_student("second"))
        self.assertEqual([item.student_id for item in self.repository.list_students()], ["first"])

    def test_relative_sample_paths_resolve_from_data_directory(self):
        sample = self.make_sample("relative.jpg")
        stored = self.create(sample_paths=[Path("assets") / sample.name])

        self.assertEqual(stored.samples[0].image_path, "assets/relative.jpg")
        self.assertTrue((self.data_dir / stored.samples[0].image_path).is_file())

    def test_create_returns_committed_record_without_a_post_commit_read(self):
        sample = self.make_sample()
        with patch.object(
            self.repository,
            "get_student",
            side_effect=AssertionError("unexpected post-commit read"),
        ):
            student = self.create(sample_paths=[sample])

        self.assertEqual(student.student_id, "00123456")
        self.assertEqual(len(student.samples), 1)

    def test_sql_like_identifier_is_stored_as_data(self):
        student_id = "0001'); DROP TABLE students; --"
        student = self.create(student_id=student_id)

        self.assertEqual(self.repository.get_student(student_id).student_id, student_id)
        self.assertEqual(len(self.repository.list_students()), 1)


if __name__ == "__main__":
    unittest.main()
