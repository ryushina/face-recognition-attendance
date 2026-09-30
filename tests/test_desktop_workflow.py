"""One temporary-data integration path through enrollment, recognition, and history."""

from datetime import datetime, timezone
import tempfile
import unittest
from pathlib import Path

from attendance_service import AttendanceService
from config import AppConfig
from database import Database
from enrollment_indexer import EnrollmentIndexer
from main import AppController, AppModel
from recognition_service import EMBEDDING_DIMENSION, RecognitionService
from repositories import StudentRepository


VECTOR = [1.0] + [0.0] * (EMBEDDING_DIMENSION - 1)
FACE_ROW = [100, 80, 100, 120, *range(10), 0.99]


class SyntheticFrame:
    shape = (480, 640, 3)


class SyntheticDetector:
    def setInputSize(self, size):
        self.input_size = size

    def detect(self, frame):
        return None, [FACE_ROW]


class SyntheticRecognizer:
    def alignCrop(self, frame, row):
        return (frame, row)

    def feature(self, aligned):
        return VECTOR


class FakeCamera:
    running = True

    def stop(self):
        self.running = False
        return True


class FakeView:
    def __init__(self):
        self.mode = []
        self.indexing = []
        self.results = []

    def update_attendance_mode(self, active, message):
        self.mode.append((active, message))

    def update_enrollment_status(self, result):
        self.indexing.append(result)

    def update_attendance_progress(self, count, required, result):
        pass

    def update_attendance_result(self, result, name):
        self.results.append((result.status, name))

    def update_identity_status(self, result):
        pass


def make_recognition_service():
    return RecognitionService(
        detector=SyntheticDetector(), recognizer=SyntheticRecognizer(),
        minimum_similarity=0.5, minimum_margin=0.08,
    )


class DesktopWorkflowTests(unittest.TestCase):
    def test_enroll_restart_recognize_record_and_export(self):
        with tempfile.TemporaryDirectory() as folder:
            data_dir = Path(folder) / "data"
            data_dir.mkdir()
            backup_dir = Path(folder) / "exports"
            backup_dir.mkdir()
            config = AppConfig.from_environment({
                "ATTENDANCE_DATA_DIR": str(data_dir),
                "ATTENDANCE_TIMEZONE": "Asia/Manila",
            })
            database = Database(data_dir / "attendance.sqlite3")
            database.initialize()
            repository = StudentRepository(database, data_dir)
            recognition = make_recognition_service()
            indexer = EnrollmentIndexer(
                repository, recognition, data_dir,
                image_reader=lambda _path: SyntheticFrame(),
            )
            enrollment_view = FakeView()
            enrollment_controller = AppController(
                AppModel(), enrollment_view, FakeCamera(), config=config,
                student_repository=repository, recognition_service=recognition,
                enrollment_indexer=indexer,
            )
            session = enrollment_controller.begin_enrollment()
            details = {
                "user_id": "0017", "first_name": "Zoë, \"Z\"",
                "middle_name": "", "last_name": "李",
                "guardian_fullname": "", "guardian_phone": "",
            }
            for index in range(3):
                def save_sample(directory, number=index):
                    target = Path(directory)
                    target.mkdir(parents=True, exist_ok=True)
                    image = target / f"capture-{number}.jpg"
                    image.write_bytes(f"synthetic capture {number}".encode())
                    return True, str(image)

                self.assertTrue(session.capture(save_sample, details)[0])
            self.assertTrue(enrollment_controller.handle_register(details)[0])
            indexer._thread.join(timeout=5)
            self.assertFalse(indexer._thread.is_alive())
            result = enrollment_controller.poll_indexing()
            self.assertIsNone(result.error)
            self.assertEqual(len(recognition._gallery), 1)

            # Reopen storage and the model service as a fresh application process would.
            restarted_database = Database(data_dir / "attendance.sqlite3")
            restarted_repository = StudentRepository(restarted_database, data_dir)
            restarted_recognition = make_recognition_service()
            self.assertEqual(restarted_repository.list_students()[0].enrollment_status, "ready")
            fixed_now = datetime(2026, 6, 1, 1, 0, tzinfo=timezone.utc)
            attendance = AttendanceService(
                restarted_database, "Asia/Manila", clock=lambda: fixed_now
            )
            camera = FakeCamera()
            view = FakeView()
            monotonic = [50.0]
            controller = AppController(
                AppModel(), view, camera, config=config,
                student_repository=restarted_repository,
                recognition_service=restarted_recognition,
                attendance_service=attendance,
                monotonic_clock=lambda: monotonic[0],
            )
            self.assertEqual(len(restarted_recognition._gallery), 1)
            self.assertTrue(controller.start_attendance())

            embedding = restarted_recognition.extract_single(SyntheticFrame())
            matched = restarted_recognition.match(embedding)
            self.assertEqual(matched.status, "recognized")
            for frame_id in (1, 2, 3):
                controller.handle_identity_update({
                    "identity": matched, "frame_id": frame_id,
                    "captured_monotonic": monotonic[0],
                })
            self.assertEqual(view.results, [("recorded", "Zoë, \"Z\" 李")])

            records = controller.get_attendance_history("2026-06-01", "0017")
            self.assertEqual(len(records), 1)
            csv_path = controller.export_attendance_history(
                backup_dir / "history.csv", "2026-06-01", "0017"
            )
            self.assertTrue(csv_path.is_file())
            self.assertIn("2026-06-01", csv_path.read_text(encoding="utf-8-sig"))

            # A second fresh controller sees the stored index and daily duplicate rule.
            final_database = Database(data_dir / "attendance.sqlite3")
            final_repository = StudentRepository(final_database, data_dir)
            final_service = AttendanceService(
                final_database, "Asia/Manila", clock=lambda: fixed_now
            )
            final_view = FakeView()
            final_controller = AppController(
                AppModel(), final_view, FakeCamera(), config=config,
                student_repository=final_repository,
                recognition_service=make_recognition_service(),
                attendance_service=final_service,
                monotonic_clock=lambda: monotonic[0],
            )
            self.assertTrue(final_controller.start_attendance())
            final_match = final_controller.recognition_service.match(embedding)
            for frame_id in (10, 11, 12):
                final_controller.handle_identity_update({
                    "identity": final_match, "frame_id": frame_id,
                    "captured_monotonic": monotonic[0],
                })
            self.assertEqual(final_view.results, [("already_recorded", "Zoë, \"Z\" 李")])
            self.assertEqual(len(final_controller.get_attendance_history()), 1)


if __name__ == "__main__":
    unittest.main()
