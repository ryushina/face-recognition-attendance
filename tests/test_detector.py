"""Detector selection tests with fake OpenCV, camera, and YOLO dependencies."""

import importlib
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from config import AppConfig


class FakeCascade:
    def __init__(self, empty=False):
        self.is_empty = empty

    def empty(self):
        return self.is_empty


class FakeCapture:
    def __init__(self, index, calls):
        self.index = index
        calls.append(index)


class DetectorFixtures:
    def __init__(
        self,
        testcase,
        *,
        haar_empty=False,
        yolo_loader=None,
        weights_exist=True,
        ultralytics_available=True,
    ):
        self.testcase = testcase
        self.temporary_directory = tempfile.TemporaryDirectory()
        testcase.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

        cascade_dir = self.root / "opencv-data"
        cascade_dir.mkdir()
        cascade_path = cascade_dir / "haarcascade_frontalface_default.xml"
        cascade_path.write_text("fake fixture", encoding="utf-8")

        self.camera_indices = []
        self.cascade_paths = []
        self.model_paths = []
        self.haar_empty = haar_empty
        self.yolo_loader = yolo_loader or self.default_yolo_loader

        self.fake_cv2 = types.ModuleType("cv2")
        self.fake_cv2.data = types.SimpleNamespace(
            haarcascades=str(cascade_dir) + os.sep
        )
        self.fake_cv2.VideoCapture = lambda index: FakeCapture(index, self.camera_indices)

        def load_cascade(path):
            self.cascade_paths.append(path)
            return FakeCascade(empty=self.haar_empty)

        self.fake_cv2.CascadeClassifier = load_cascade

        model_file = self.root / "face-model.pt"
        if weights_exist:
            model_file.write_bytes(b"fake weights")
        self.model_file = model_file

        self.fake_ultralytics = types.ModuleType("ultralytics")
        self.fake_ultralytics.YOLO = self.yolo_loader
        self.ultralytics_module = (
            self.fake_ultralytics if ultralytics_available else None
        )

    def default_yolo_loader(self, path):
        self.model_paths.append(path)
        return object()

    def construct(self, detector):
        previous = sys.modules.pop("camera_service", None)
        try:
            with patch.dict(
                sys.modules,
                {
                    "cv2": self.fake_cv2,
                    "ultralytics": self.ultralytics_module,
                },
            ):
                module = importlib.import_module("camera_service")
                settings = AppConfig.from_environment(
                    {"ATTENDANCE_MODEL_PATH": str(self.model_file)}
                )
                return module.CameraService(detector=detector, config=settings)
        finally:
            sys.modules.pop("camera_service", None)
            if previous is not None:
                sys.modules["camera_service"] = previous


class DetectorSelectionTests(unittest.TestCase):
    def test_haar_selection_does_not_import_or_load_yolo(self):
        fixtures = DetectorFixtures(self, ultralytics_available=False)
        service = fixtures.construct("haar")

        self.assertEqual(service.detector, "haar")
        self.assertEqual(service.detector_status, "Face detector: Haar active (configured).")
        self.assertEqual(fixtures.model_paths, [])
        self.assertEqual(len(fixtures.cascade_paths), 1)
        self.assertEqual(fixtures.camera_indices, [])
        self.assertIsNone(service.cap)

    def test_yolo_selection_loads_configured_weights_without_loading_haar(self):
        fixtures = DetectorFixtures(self)
        service = fixtures.construct("yolo")

        self.assertEqual(service.detector, "yolo")
        self.assertEqual(service.detector_status, "Face detector: YOLO active.")
        self.assertEqual(fixtures.model_paths, [str(fixtures.model_file.resolve())])
        self.assertEqual(fixtures.cascade_paths, [])

    def test_missing_ultralytics_uses_haar_and_reports_the_error(self):
        fixtures = DetectorFixtures(self, ultralytics_available=False)
        service = fixtures.construct("yolo")

        self.assertEqual(service.detector, "haar")
        self.assertIn("Face detector: Haar active", service.detector_status)
        self.assertIn("YOLO could not initialize", service.detector_status)
        self.assertIn("ultralytics", service.detector_status)
        self.assertEqual(len(fixtures.cascade_paths), 1)

    def test_missing_weights_reports_path_and_uses_haar(self):
        fixtures = DetectorFixtures(
            self, weights_exist=False, ultralytics_available=False
        )
        service = fixtures.construct("yolo")

        self.assertEqual(service.detector, "haar")
        self.assertIn(str(fixtures.model_file), service.detector_status)
        self.assertIn("ATTENDANCE_MODEL_PATH", service.detector_status)
        self.assertEqual(fixtures.model_paths, [])

    def test_yolo_initialization_error_is_explained_when_haar_is_loaded(self):
        def failing_loader(path):
            raise RuntimeError("test model initialization failure")

        fixtures = DetectorFixtures(self, yolo_loader=failing_loader)
        service = fixtures.construct("yolo")

        self.assertEqual(service.detector, "haar")
        self.assertIn("test model initialization failure", service.detector_status)
        self.assertIn("Haar active", service.detector_status)

    def test_unavailable_haar_raises_before_opening_camera(self):
        fixtures = DetectorFixtures(self, haar_empty=True)
        with self.assertRaisesRegex(
            RuntimeError, "could not load the Haar cascade"
        ):
            fixtures.construct("haar")

        self.assertEqual(fixtures.camera_indices, [])

    def test_failure_of_both_detectors_reports_both_errors_before_opening_camera(self):
        def failing_loader(path):
            raise RuntimeError("test YOLO failure")

        fixtures = DetectorFixtures(
            self, haar_empty=True, yolo_loader=failing_loader
        )
        with self.assertRaisesRegex(RuntimeError, "No face detector") as caught:
            fixtures.construct("yolo")

        self.assertIn("test YOLO failure", str(caught.exception))
        self.assertIn("could not load the Haar cascade", str(caught.exception))
        self.assertEqual(fixtures.camera_indices, [])

    def test_invalid_detector_fails_before_opening_camera(self):
        fixtures = DetectorFixtures(self)
        with self.assertRaisesRegex(RuntimeError, "Unsupported face detector"):
            fixtures.construct("unknown")

        self.assertEqual(fixtures.camera_indices, [])


if __name__ == "__main__":
    unittest.main()
