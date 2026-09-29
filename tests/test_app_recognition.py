"""Controller-level recognition and enrollment-gallery refresh checks."""

import tempfile
import unittest
from pathlib import Path

from config import AppConfig
from database import Database
from enrollment_indexer import IndexingResult
from main import AppController, AppModel
from recognition_service import (
    FaceEmbedding, MODEL_VERSION, PREPROCESSING_ID,
)
from repositories import StudentRepository


VECTOR = (1.0,) + (0.0,) * 127


class FakeRecognition:
    model_version = MODEL_VERSION
    preprocessing_id = PREPROCESSING_ID

    def __init__(self):
        self.gallery = []

    def set_gallery(self, gallery):
        self.gallery = list(gallery)
        return len(self.gallery)


class InlineIndexer:
    """Only for this controller test; production indexing is threaded."""
    _thread = None

    def __init__(self, repository):
        self.repository = repository
        self.results = []

    def submit(self, student_id):
        samples = self.repository.begin_indexing(student_id)
        embeddings = {
            sample.sample_id: FaceEmbedding(VECTOR, (0, 0, 100, 100), 0.99)
            for sample in samples
        }
        count = self.repository.complete_indexing(student_id, embeddings)
        self.results.append(IndexingResult(student_id, count))
        return True

    def poll_result(self):
        return self.results.pop(0) if self.results else None


class FakeView:
    def __init__(self):
        self.identity = []
        self.indexing = []

    def update_identity_status(self, result):
        self.identity.append(result)

    def update_enrollment_status(self, result):
        self.indexing.append(result)


class AppRecognitionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.root.mkdir(exist_ok=True)
        self.config = AppConfig.from_environment({"ATTENDANCE_DATA_DIR": str(self.root)})
        self.database = Database(self.root / "attendance.sqlite3")
        self.database.initialize()
        self.repository = StudentRepository(self.database, self.root)

    def test_enrollment_indexes_and_refreshes_live_gallery_without_restart(self):
        view = FakeView()
        recognition = FakeRecognition()
        indexer = InlineIndexer(self.repository)
        controller = AppController(
            AppModel(), view, None, config=self.config,
            student_repository=self.repository,
            recognition_service=recognition,
            enrollment_indexer=indexer,
        )
        session = controller.begin_enrollment()
        payload = {
            "user_id": "0008", "first_name": "Mia", "middle_name": "",
            "last_name": "Diaz", "guardian_fullname": "Ana Diaz",
            "guardian_phone": "1",
        }
        for sample_no in range(3):
            def capture(folder, number=sample_no):
                folder = Path(folder)
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / f"new-{number}.jpg"
                path.write_bytes(b"fixture image")
                return True, str(path)

            success, message = session.capture(capture, payload)
            self.assertTrue(success, message)

        self.assertTrue(controller.handle_register(payload)[0])
        self.assertEqual(recognition.gallery, [])
        result = controller.poll_indexing()

        self.assertEqual(result.indexed_samples, 3)
        self.assertEqual([person["student_id"] for person in recognition.gallery], ["0008"])
        self.assertEqual(view.indexing, [result])

    def test_identity_result_is_delivered_to_view_on_controller_thread(self):
        view = FakeView()
        controller = AppController(AppModel(), view, None, config=self.config,
                                   student_repository=self.repository)
        result = object()
        controller.handle_identity_update({"identity": result, "frame_id": 1})
        self.assertEqual(view.identity, [result])


if __name__ == "__main__":
    unittest.main()
