"""Enrollment session ownership, identity reset, and capture state tests."""

import tempfile
import unittest
from pathlib import Path

from enrollment_session import EnrollmentSession


class EnrollmentSessionTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.data_dir = Path(self.temporary_directory.name)

    def save_capture(self, folder):
        path = Path(folder) / "sample.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"face")
        return True, str(path)

    def test_capture_retains_form_and_sample_under_stable_session_folder(self):
        session = EnrollmentSession(self.data_dir)
        details = {
            "user_id": "00123",
            "first_name": "Ana",
            "middle_name": "Maria",
            "last_name": "Santos",
            "guardian_fullname": "Parent",
            "guardian_phone": "123",
        }

        success, _ = session.capture(self.save_capture, details)

        self.assertTrue(success)
        self.assertEqual(session.accepted_count, 1)
        self.assertEqual(session.form_details, details)
        self.assertEqual(session.student_id, "00123")
        self.assertIn("enrollment_sessions", session.session_dir.parts)
        self.assertEqual(session.sample_paths[0].parent, session.session_dir)

    def test_changing_student_id_deletes_only_tracked_session_samples(self):
        session = EnrollmentSession(self.data_dir)
        session.capture(self.save_capture, {"user_id": "first"})
        unrelated = self.data_dir / "assets" / "another-student.jpg"
        unrelated.parent.mkdir(parents=True, exist_ok=True)
        unrelated.write_bytes(b"keep")
        old_folder = session.session_dir

        changed = session.update_details({"user_id": "second", "first_name": "Bea"})

        self.assertTrue(changed)
        self.assertEqual(session.accepted_count, 0)
        self.assertFalse((old_folder / "sample.jpg").exists())
        self.assertTrue(unrelated.exists())
        self.assertEqual(session.session_dir, old_folder)
        self.assertEqual(session.form_details["first_name"], "Bea")

    def test_failed_capture_adds_no_sample_and_exposes_error(self):
        session = EnrollmentSession(self.data_dir)
        session.update_details({"user_id": "00123"})

        success, message = session.capture(
            lambda _folder: (False, "No face detected"),
            {"user_id": "00123", "first_name": "Ana"},
        )

        self.assertFalse(success)
        self.assertEqual(session.accepted_count, 0)
        self.assertEqual(session.capture_errors, [message])
        self.assertIn("No face detected", message)

    def test_cancel_removes_owned_pending_files_but_keeps_unowned_folder_content(self):
        session = EnrollmentSession(self.data_dir)
        session.capture(self.save_capture, {"user_id": "00123"})
        untracked = session.session_dir / "operator-note.txt"
        untracked.write_text("keep", encoding="utf-8")

        self.assertTrue(session.cancel())

        self.assertFalse((session.session_dir / "sample.jpg").exists())
        self.assertTrue(untracked.exists())
        self.assertEqual(session.accepted_count, 0)

    def test_submitted_session_cancel_cannot_delete_saved_samples(self):
        session = EnrollmentSession(self.data_dir)
        session.capture(self.save_capture, {"user_id": "00123"})
        saved_path = session.sample_paths[0]
        session.mark_submitted()

        self.assertFalse(session.cancel())
        self.assertTrue(saved_path.exists())

    def test_submitted_identity_edit_or_capture_cannot_remove_saved_samples(self):
        session = EnrollmentSession(self.data_dir)
        session.capture(self.save_capture, {"user_id": "00123"})
        saved_path = session.sample_paths[0]
        session.mark_submitted()

        self.assertFalse(session.update_details({"user_id": "changed"}))
        session.clear_samples()
        success, _ = session.capture(
            self.save_capture, {"user_id": "changed"}
        )

        self.assertFalse(success)
        self.assertEqual(session.student_id, "00123")
        self.assertEqual(session.sample_paths, [saved_path])
        self.assertTrue(saved_path.is_file())

    def test_capture_outside_session_is_not_accepted_or_deleted(self):
        session = EnrollmentSession(self.data_dir)
        external = self.data_dir / "external.jpg"
        external.write_bytes(b"keep")

        success, message = session.capture(
            lambda _folder: (True, str(external)), {"user_id": "00123"}
        )

        self.assertFalse(success)
        self.assertIn("outside this enrollment session", message)
        self.assertEqual(session.accepted_count, 0)
        self.assertTrue(external.exists())


if __name__ == "__main__":
    unittest.main()
