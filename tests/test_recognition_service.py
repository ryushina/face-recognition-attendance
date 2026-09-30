"""Injected model tests for aligned, normalized face feature extraction."""

import math
import tempfile
import unittest
from pathlib import Path
import types

import numpy as np

from recognition_service import (
    EMBEDDING_DIMENSION,
    MODEL_VERSION,
    PREPROCESSING_ID,
    FaceDetection,
    FaceEmbedding,
    MultipleFacesDetected,
    NoFaceDetected,
    RecognitionError,
    RecognitionService,
)


class FakeFrame:
    shape = (480, 640, 3)


def face_row(x=100, y=80, width=100, height=120, score=0.99):
    return [x, y, width, height, *range(10), score]


class FakeDetector:
    def __init__(self, rows=None):
        self.rows = rows
        self.input_sizes = []

    def setInputSize(self, size):
        self.input_sizes.append(size)

    def detect(self, frame):
        return None, self.rows


class FakeRecognizer:
    def __init__(self, feature=None):
        self.raw_feature = feature or [1.0] * EMBEDDING_DIMENSION
        self.aligned_rows = []
        self.feature_inputs = []

    def alignCrop(self, frame, row):
        self.aligned_rows.append(row)
        return "aligned-face"

    def feature(self, aligned):
        self.feature_inputs.append(aligned)
        return self.raw_feature


class RecognitionServiceTests(unittest.TestCase):
    def make_service(self, rows=None, feature=None):
        detector = FakeDetector(rows)
        recognizer = FakeRecognizer(feature)
        return (
            RecognitionService(detector=detector, recognizer=recognizer),
            detector,
            recognizer,
        )

    def test_detection_uses_image_size_and_preserves_five_landmarks(self):
        row = face_row()
        service, detector, _recognizer = self.make_service([row])

        faces = service.detect(FakeFrame())

        self.assertEqual(detector.input_sizes, [(640, 480)])
        self.assertEqual(len(faces), 1)
        self.assertEqual(faces[0].box, (100, 80, 100, 120))
        self.assertEqual(faces[0].landmarks, tuple(float(x) for x in range(10)))
        self.assertIs(faces[0].raw_row, row)

    def test_feature_is_aligned_finite_and_unit_normalized(self):
        row = face_row()
        service, _detector, recognizer = self.make_service([row])
        frame = FakeFrame()

        embedding = service.extract_single(frame)

        self.assertIs(recognizer.aligned_rows[0], row)
        self.assertEqual(recognizer.feature_inputs, ["aligned-face"])
        self.assertEqual(len(embedding.vector), EMBEDDING_DIMENSION)
        self.assertAlmostEqual(
            math.sqrt(sum(value * value for value in embedding.vector)), 1.0
        )
        self.assertTrue(all(math.isfinite(value) for value in embedding.vector))
        self.assertEqual(embedding.model_version, MODEL_VERSION)
        self.assertEqual(embedding.preprocessing_id, PREPROCESSING_ID)

    def test_numpy_detection_row_keeps_its_type_for_opencv_alignment(self):
        rows = np.asarray([face_row()], dtype=np.float32)
        service, _detector, recognizer = self.make_service(rows)

        face = service.detect(FakeFrame())[0]
        service.extract(FakeFrame(), face)

        aligned_row = recognizer.aligned_rows[0]
        self.assertIsInstance(aligned_row, np.ndarray)
        self.assertEqual(aligned_row.dtype, np.float32)
        self.assertEqual(aligned_row.shape, (15,))
        np.testing.assert_array_equal(aligned_row, rows[0])

    def test_native_detection_row_can_align_and_extract_with_real_sface(self):
        model_path = (
            Path(__file__).resolve().parents[1]
            / "models" / "face_recognition_sface_2021dec.onnx"
        )
        if not model_path.is_file():
            self.skipTest("Provision the pinned SFace model to run the native API check.")
        import cv2

        # Synthetic pixels and supplied landmarks test the actual OpenCV API
        # contract without accessing a camera or a person's image.
        frame = np.zeros((160, 160, 3), dtype=np.uint8)
        rows = np.asarray([
            [30, 20, 100, 120, 55, 60, 105, 60, 80, 85, 60, 110, 100, 110, 0.99]
        ], dtype=np.float32)
        service = RecognitionService(
            detector=FakeDetector(rows),
            recognizer=cv2.FaceRecognizerSF.create(str(model_path), ""),
        )

        embedding = service.extract_single(frame)

        self.assertEqual(len(embedding.vector), EMBEDDING_DIMENSION)
        self.assertTrue(all(math.isfinite(value) for value in embedding.vector))
        self.assertAlmostEqual(sum(value * value for value in embedding.vector), 1.0)

    def test_no_face_and_multiple_face_images_are_rejected_for_enrollment(self):
        no_face, _detector, _recognizer = self.make_service(None)
        multiple, _detector, _recognizer = self.make_service(
            [face_row(), face_row(x=300)]
        )

        with self.assertRaises(NoFaceDetected):
            no_face.extract_single(FakeFrame())
        with self.assertRaises(MultipleFacesDetected):
            multiple.extract_single(FakeFrame())

    def test_out_of_frame_candidate_is_ignored_for_that_frame(self):
        outside_rows = (
            face_row(x=-1),
            face_row(x=600, width=100),
            face_row(y=470, height=20),
            face_row(width=0),
        )
        for row in outside_rows:
            with self.subTest(row=row[:4]):
                service, _detector, _recognizer = self.make_service([row])
                self.assertEqual(service.detect(FakeFrame()), ())

        # If one candidate is unusable, fail closed rather than recognize a
        # different candidate from the same ambiguous frame.
        service, _detector, _recognizer = self.make_service(
            [face_row(), face_row(x=-1)]
        )
        self.assertEqual(service.detect(FakeFrame()), ())

    def test_malformed_and_nonfinite_detection_rows_fail(self):
        cases = (
            face_row()[:-1],
            [*face_row()[:14], float("nan")],
        )
        for row in cases:
            with self.subTest(row=row[:4]):
                service, _detector, _recognizer = self.make_service([row])
                with self.assertRaises(RecognitionError):
                    service.detect(FakeFrame())

    def test_invalid_feature_dimensions_nonfinite_and_zero_vectors_fail(self):
        cases = (
            [1.0] * (EMBEDDING_DIMENSION - 1),
            [float("nan")] + [1.0] * (EMBEDDING_DIMENSION - 1),
            [0.0] * EMBEDDING_DIMENSION,
        )
        for feature in cases:
            with self.subTest(feature_length=len(feature)):
                service, _detector, _recognizer = self.make_service(
                    [face_row()], feature
                )
                with self.assertRaises(RecognitionError):
                    service.extract_single(FakeFrame())

    def test_wrong_image_shape_is_rejected(self):
        service, _detector, _recognizer = self.make_service([face_row()])
        for frame in (None, types.SimpleNamespace(shape=(20, 20)),
                      types.SimpleNamespace(shape=(20, 20, 4))):
            with self.subTest(frame=frame):
                with self.assertRaises(RecognitionError):
                    service.detect(frame)

    def test_missing_models_and_api_errors_have_actionable_messages(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(RecognitionError, "face_detection_yunet"):
                RecognitionService(model_dir=folder, cv2_module=object())

        with tempfile.TemporaryDirectory() as folder:
            model_dir = Path(folder)
            (model_dir / "face_detection_yunet_2023mar.onnx").write_bytes(b"model")
            (model_dir / "face_recognition_sface_2021dec.onnx").write_bytes(b"model")
            with self.assertRaisesRegex(RecognitionError, "opencv-contrib-python"):
                RecognitionService(model_dir=model_dir, cv2_module=types.SimpleNamespace())

    def test_matching_groups_best_sample_per_student_and_rejects_unknown_or_ambiguous(self):
        service = RecognitionService(
            detector=object(), recognizer=object(), minimum_similarity=0.5,
            minimum_margin=0.08,
        )
        x = (1.0,) + (0.0,) * 127
        y = (0.0, 1.0) + (0.0,) * 126
        near = (0.99, (1.0 - 0.99 ** 2) ** 0.5) + (0.0,) * 126
        service.set_gallery([
            {"student_id": "a", "name": "Student A", "embeddings": [y, x]},
            {"student_id": "b", "name": "Student B", "embeddings": [y]},
        ])
        query = FaceEmbedding(x, (0, 0, 10, 10), 1.0)
        result = service.match(query)
        self.assertEqual(result.status, "recognized")
        self.assertEqual(result.student_id, "a")
        self.assertAlmostEqual(result.score, 1.0)
        self.assertLess(result.runner_up_score, 0.08)

        service.set_gallery([{"student_id": "a", "embeddings": [y]}])
        self.assertEqual(service.match(query).status, "unknown")
        self.assertEqual(service.match(query).reason, "below_similarity")
        service.set_gallery([
            {"student_id": "a", "embeddings": [x]},
            {"student_id": "b", "embeddings": [near]},
        ])
        ambiguous = service.match(query)
        self.assertEqual(ambiguous.status, "ambiguous")
        self.assertEqual(ambiguous.reason, "insufficient_margin")
        self.assertIn("close", ambiguous.message)

    def test_empty_and_incompatible_gallery_inputs_are_unknown(self):
        service = RecognitionService(detector=object(), recognizer=object())
        vector = (1.0,) + (0.0,) * 127
        query = FaceEmbedding(vector, (0, 0, 10, 10), 1.0)
        self.assertEqual(service.match(query).status, "unknown")
        self.assertEqual(service.match(query).reason, "gallery_empty")
        service.set_gallery([{"student_id": "x", "embeddings": [vector]}])
        incompatible = FaceEmbedding(
            vector, (0, 0, 10, 10), 1.0,
            model_version="another-model",
            preprocessing_id=PREPROCESSING_ID,
        )
        self.assertEqual(service.match(incompatible).status, "unknown")
        self.assertEqual(service.match(incompatible).reason, "incompatible_embedding")
        self.assertEqual(service.match(query).model_version, MODEL_VERSION)


if __name__ == "__main__":
    unittest.main()
