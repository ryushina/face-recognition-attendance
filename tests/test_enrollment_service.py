"""SQLite integration checks for student enrollment submission."""

import tempfile
import unittest
from pathlib import Path

from database import Database
from enrollment_service import MIN_ENROLLMENT_SAMPLES, submit_enrollment
from enrollment_session import EnrollmentSession
from repositories import (
    DuplicateStudentError,
    StudentRepository,
    StudentRepositoryError,
)


class EnrollmentServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.data_dir = Path(self.temporary_directory.name)
        self.database = Database(self.data_dir / "attendance.sqlite3")
        self.database.initialize()
        self.repository = StudentRepository(self.database, self.data_dir)
        self.session = EnrollmentSession(self.data_dir)
        self.details = {
            "user_id": "000123",
            "first_name": "Ana",
            "middle_name": "María",
            "last_name": "Santos",
            "guardian_fullname": "José Santos",
            "guardian_phone": "+63 900 123 4567",
        }
        self.capture_samples()

    def capture_samples(self):
        for index in range(MIN_ENROLLMENT_SAMPLES):
            def capture(folder, sample_index=index):
                path = Path(folder) / f"capture-{sample_index}.jpg"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(f"sample-{sample_index}".encode())
                return True, str(path)

            success, _ = self.session.capture(capture, self.details)
            self.assertTrue(success)

    def test_submit_persists_all_fields_and_samples_for_reopen_query(self):
        reopened = Database(self.database.path)
        reopened.initialize()
        repository_after_restart = StudentRepository(reopened, self.data_dir)

        success, message = submit_enrollment(
            self.session, self.repository, self.details
        )

        self.assertTrue(success)
        self.assertIn("pending", message)
        self.assertTrue(self.session.submitted)
        student = repository_after_restart.get_student("000123")
        self.assertEqual(student.student_id, "000123")
        self.assertEqual(student.first_name, "Ana")
        self.assertEqual(student.middle_name, "María")
        self.assertEqual(student.last_name, "Santos")
        self.assertEqual(student.guardian_full_name, "José Santos")
        self.assertEqual(student.guardian_phone, "+63 900 123 4567")
        self.assertEqual(student.enrollment_status, "pending")
        self.assertEqual(len(student.samples), MIN_ENROLLMENT_SAMPLES)
        self.assertTrue(all(Path(s.image_path).is_absolute() is False for s in student.samples))
        self.assertTrue(all((self.data_dir / sample.image_path).is_file() for sample in student.samples))

    def test_minimum_sample_count_and_duplicate_submit_are_enforced(self):
        one_sample_session = EnrollmentSession(self.data_dir)
        one_sample_session.sample_paths = self.session.sample_paths[:2]
        success, message = submit_enrollment(
            one_sample_session, self.repository, self.details
        )
        self.assertFalse(success)
        self.assertIn("at least 3", message)

        success, _ = submit_enrollment(self.session, self.repository, self.details)
        self.assertTrue(success)
        success, message = submit_enrollment(self.session, self.repository, self.details)
        self.assertFalse(success)
        self.assertIn("already been submitted", message)

    def test_duplicate_student_gives_clear_error_and_preserves_pending_samples(self):
        self.repository.create_student(
            "000123", "Existing", "Student", self.session.sample_paths
        )
        files_before = tuple(path.read_bytes() for path in self.session.sample_paths)

        success, message = submit_enrollment(
            self.session, self.repository, self.details
        )

        self.assertFalse(success)
        self.assertIn("already registered", message)
        self.assertFalse(self.session.submitted)
        self.assertEqual(tuple(path.read_bytes() for path in self.session.sample_paths), files_before)

    def test_database_write_failure_keeps_session_samples_retryable(self):
        class FailingRepository:
            def create_student(self, **_kwargs):
                raise StudentRepositoryError("database is read-only")

        paths = tuple(self.session.sample_paths)
        contents = tuple(path.read_bytes() for path in paths)

        success, message = submit_enrollment(
            self.session, FailingRepository(), self.details
        )

        self.assertFalse(success)
        self.assertIn("database is read-only", message)
        self.assertFalse(self.session.submitted)
        self.assertEqual(tuple(self.session.sample_paths), paths)
        self.assertEqual(tuple(path.read_bytes() for path in paths), contents)
        self.assertTrue(all(path.is_file() for path in paths))

    def test_cancel_after_success_preserves_samples(self):
        success, _ = submit_enrollment(self.session, self.repository, self.details)
        self.assertTrue(success)
        paths = tuple(self.session.sample_paths)

        self.assertFalse(self.session.cancel())
        self.assertTrue(all(path.is_file() for path in paths))


if __name__ == "__main__":
    unittest.main()
