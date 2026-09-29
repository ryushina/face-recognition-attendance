import tempfile
import threading
import time
import unittest
from pathlib import Path

from database import Database
from enrollment_indexer import EnrollmentIndexer
from recognition_service import (
    FaceEmbedding,
    MODEL_VERSION,
    PREPROCESSING_ID,
)
from repositories import StudentRepository


def embedding(first=1.0):
    vector = (first,) + (0.0,) * 127
    return FaceEmbedding(vector, (0, 0, 100, 100), 0.99)


class FakeRecognition:
    def __init__(self, fail_on=None):
        self.fail_on = fail_on
        self.calls = 0
        self.call_thread = None

    def extract_single(self, image):
        self.calls += 1
        self.call_thread = threading.get_ident()
        if self.fail_on == self.calls:
            raise ValueError("synthetic image rejection")
        return embedding()


class EnrollmentIndexerTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.database = Database(self.root / "attendance.sqlite3")
        self.database.initialize()
        self.repository = StudentRepository(self.database, self.root)

    def create_student(self, count=2):
        paths = []
        for index in range(count):
            path = self.root / f"face-{index}.jpg"
            path.write_bytes(b"fixture image")
            paths.append(path)
        return self.repository.create_student("0007", "Lin", "Tan", paths)

    def test_index_publishes_complete_versioned_gallery_and_survives_restart(self):
        self.create_student()
        service = FakeRecognition()
        indexer = EnrollmentIndexer(
            self.repository, service, self.root,
            image_reader=lambda path: str(path),
        )

        result = indexer.index_student("0007")

        self.assertEqual(result.indexed_samples, 2)
        self.assertIsNone(result.error)
        student = self.repository.get_student("0007")
        self.assertEqual(student.enrollment_status, "ready")
        self.assertTrue(all(len(sample.embedding) == 512 for sample in student.samples))
        self.assertTrue(all(sample.embedding_dimension == 128 for sample in student.samples))
        gallery = self.repository.load_compatible_gallery(MODEL_VERSION, PREPROCESSING_ID)
        self.assertEqual(len(gallery), 1)
        self.assertEqual(len(gallery[0]["embeddings"]), 2)

        reopened = Database(self.database.path)
        reopened.initialize()
        restored = StudentRepository(reopened, self.root).load_compatible_gallery(
            MODEL_VERSION, PREPROCESSING_ID
        )
        self.assertEqual(restored, gallery)

    def test_failed_partial_index_stays_failed_and_publishes_no_gallery(self):
        self.create_student()
        indexer = EnrollmentIndexer(
            self.repository, FakeRecognition(fail_on=2), self.root,
            image_reader=lambda path: str(path),
        )

        result = indexer.index_student("0007")

        self.assertIn("synthetic image rejection", result.error)
        student = self.repository.get_student("0007")
        self.assertEqual(student.enrollment_status, "failed")
        self.assertIn("synthetic image rejection", student.enrollment_error)
        self.assertTrue(all(sample.embedding is None for sample in student.samples))
        self.assertEqual(
            self.repository.load_compatible_gallery(MODEL_VERSION, PREPROCESSING_ID), []
        )
        self.assertTrue(all(Path(self.root / sample.image_path).is_file() for sample in student.samples))

    def test_incomplete_or_incompatible_ready_student_is_not_published(self):
        self.create_student()
        indexer = EnrollmentIndexer(
            self.repository, FakeRecognition(), self.root,
            image_reader=lambda path: str(path),
        )
        indexer.index_student("0007")
        connection = self.database.connect()
        try:
            connection.execute(
                "UPDATE face_samples SET embedding_preprocessing_id = 'other' "
                "WHERE sample_id = (SELECT MIN(sample_id) FROM face_samples)"
            )
            connection.commit()
        finally:
            connection.close()
        self.assertEqual(
            self.repository.load_compatible_gallery(MODEL_VERSION, PREPROCESSING_ID), []
        )

    def test_submit_runs_indexing_on_a_worker_and_returns_result_to_poller(self):
        self.create_student(count=1)
        service = FakeRecognition()
        indexer = EnrollmentIndexer(
            self.repository, service, self.root,
            image_reader=lambda path: str(path),
        )
        owner_thread = threading.get_ident()

        self.assertTrue(indexer.submit("0007"))
        self.assertFalse(indexer.submit("another"))
        deadline = time.monotonic() + 2
        result = None
        while time.monotonic() < deadline and result is None:
            result = indexer.poll_result()
            if result is None:
                time.sleep(0.01)
        self.assertIsNotNone(result)
        self.assertEqual(result.indexed_samples, 1)
        self.assertNotEqual(service.call_thread, owner_thread)


if __name__ == "__main__":
    unittest.main()
