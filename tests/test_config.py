"""Tests for side-effect-free, working-directory-independent app settings."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import config
from config import AppConfig, ConfigError


class AppConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name).resolve()

    def load_config(self, environ=None):
        with patch.object(config, "APP_DIR", self.root):
            return AppConfig.from_environment(environ or {})

    def test_defaults_use_application_directory_without_creating_data(self):
        settings = self.load_config()

        self.assertEqual(settings.app_dir, self.root)
        self.assertEqual(settings.data_dir, self.root / "data")
        self.assertEqual(settings.users_file, self.root / "data" / "users.txt")
        self.assertEqual(settings.log_file, self.root / "data" / "log.txt")
        self.assertEqual(settings.photos_dir, self.root / "data" / "assets")
        self.assertEqual(settings.model_path, self.root / "yolov8n-face-lindevs.pt")
        self.assertEqual(settings.camera_index, 0)
        self.assertEqual(settings.detector, "yolo")
        self.assertEqual(settings.yolo_confidence, 0.40)
        self.assertEqual(settings.frame_interval_seconds, 0.03)
        self.assertEqual(settings.capture_max_age_seconds, 1.0)
        self.assertEqual(settings.capture_min_face_size_pixels, 80)
        self.assertEqual(settings.capture_min_blur_score, 50.0)
        self.assertEqual(settings.capture_brightness_min, 40.0)
        self.assertEqual(settings.capture_brightness_max, 220.0)
        self.assertEqual(settings.recognition_minimum_similarity, 0.50)
        self.assertEqual(settings.recognition_minimum_margin, 0.08)
        self.assertEqual(settings.stable_identity_frames, 3)
        self.assertEqual(settings.identity_evidence_window_seconds, 2.0)
        self.assertEqual(settings.identity_max_age_seconds, 1.0)
        self.assertIsNone(settings.attendance_timezone)
        self.assertFalse(settings.data_dir.exists())

    def test_default_paths_are_independent_of_current_working_directory(self):
        with tempfile.TemporaryDirectory() as another_directory:
            original_directory = Path.cwd()
            try:
                os.chdir(another_directory)
                settings = self.load_config()
            finally:
                os.chdir(original_directory)

        self.assertEqual(settings.data_dir, self.root / "data")
        self.assertEqual(settings.model_path, self.root / "yolov8n-face-lindevs.pt")
        self.assertFalse(settings.data_dir.exists())

    def test_relative_overrides_resolve_from_application_directory(self):
        settings = self.load_config(
            {
                "ATTENDANCE_DATA_DIR": "school-data",
                "ATTENDANCE_MODEL_PATH": "models/custom-face.pt",
            }
        )

        self.assertEqual(settings.data_dir, self.root / "school-data")
        self.assertEqual(
            settings.model_path, self.root / "models" / "custom-face.pt"
        )
        self.assertFalse(settings.data_dir.exists())

    def test_absolute_path_overrides_are_preserved(self):
        external_data = self.root.parent / "external-data"
        external_model = self.root.parent / "custom-face.pt"

        settings = self.load_config(
            {
                "ATTENDANCE_DATA_DIR": str(external_data),
                "ATTENDANCE_MODEL_PATH": str(external_model),
            }
        )

        self.assertEqual(settings.data_dir, external_data.resolve())
        self.assertEqual(settings.model_path, external_model.resolve())
        self.assertFalse(external_data.exists())

    def test_camera_and_processing_settings_can_be_overridden(self):
        settings = self.load_config(
            {
                "ATTENDANCE_CAMERA_INDEX": "2",
                "ATTENDANCE_DETECTOR": " Haar ",
                "ATTENDANCE_YOLO_CONFIDENCE": "0.65",
                "ATTENDANCE_FRAME_INTERVAL_SECONDS": "0.1",
            }
        )

        self.assertEqual(settings.camera_index, 2)
        self.assertEqual(settings.detector, "haar")
        self.assertEqual(settings.yolo_confidence, 0.65)
        self.assertEqual(settings.frame_interval_seconds, 0.1)

    def test_invalid_settings_report_the_setting_name(self):
        invalid_settings = (
            ("ATTENDANCE_CAMERA_INDEX", "webcam"),
            ("ATTENDANCE_CAMERA_INDEX", "-1"),
            ("ATTENDANCE_DETECTOR", "unknown"),
            ("ATTENDANCE_YOLO_CONFIDENCE", "nan"),
            ("ATTENDANCE_YOLO_CONFIDENCE", "1.1"),
            ("ATTENDANCE_FRAME_INTERVAL_SECONDS", "0"),
            ("ATTENDANCE_FRAME_INTERVAL_SECONDS", "infinity"),
            ("ATTENDANCE_CAPTURE_MAX_AGE_SECONDS", "0"),
            ("ATTENDANCE_CAPTURE_MAX_AGE_SECONDS", "nan"),
            ("ATTENDANCE_CAPTURE_MIN_FACE_SIZE_PIXELS", "1.5"),
            ("ATTENDANCE_CAPTURE_MIN_FACE_SIZE_PIXELS", "0"),
            ("ATTENDANCE_CAPTURE_MIN_BLUR_SCORE", "-1"),
            ("ATTENDANCE_CAPTURE_BRIGHTNESS_MIN", "256"),
            ("ATTENDANCE_CAPTURE_BRIGHTNESS_MAX", "20"),
            ("ATTENDANCE_MINIMUM_SIMILARITY", "1.1"),
            ("ATTENDANCE_MINIMUM_MARGIN", "3"),
            ("ATTENDANCE_STABLE_IDENTITY_FRAMES", "0"),
            ("ATTENDANCE_IDENTITY_EVIDENCE_WINDOW_SECONDS", "0"),
        )

        for name, value in invalid_settings:
            with self.subTest(name=name, value=value):
                with self.assertRaisesRegex(ConfigError, name):
                    self.load_config({name: value})

    def test_capture_quality_settings_can_be_overridden(self):
        settings = self.load_config(
            {
                "ATTENDANCE_CAPTURE_MAX_AGE_SECONDS": "2.5",
                "ATTENDANCE_CAPTURE_MIN_FACE_SIZE_PIXELS": "96",
                "ATTENDANCE_CAPTURE_MIN_BLUR_SCORE": "35.5",
                "ATTENDANCE_CAPTURE_BRIGHTNESS_MIN": "30",
                "ATTENDANCE_CAPTURE_BRIGHTNESS_MAX": "230",
            }
        )

        self.assertEqual(settings.capture_max_age_seconds, 2.5)
        self.assertEqual(settings.capture_min_face_size_pixels, 96)
        self.assertEqual(settings.capture_min_blur_score, 35.5)
        self.assertEqual(settings.capture_brightness_min, 30.0)
        self.assertEqual(settings.capture_brightness_max, 230.0)

    def test_recognition_and_timezone_settings_can_be_overridden(self):
        settings = self.load_config(
            {
                "ATTENDANCE_MINIMUM_SIMILARITY": "0.63",
                "ATTENDANCE_MINIMUM_MARGIN": "0.12",
                "ATTENDANCE_STABLE_IDENTITY_FRAMES": "4",
                "ATTENDANCE_IDENTITY_EVIDENCE_WINDOW_SECONDS": "3.5",
                "ATTENDANCE_IDENTITY_MAX_AGE_SECONDS": "0.75",
                "ATTENDANCE_TIMEZONE": "Asia/Manila",
            }
        )
        self.assertEqual(settings.recognition_minimum_similarity, 0.63)
        self.assertEqual(settings.recognition_minimum_margin, 0.12)
        self.assertEqual(settings.stable_identity_frames, 4)
        self.assertEqual(settings.identity_evidence_window_seconds, 3.5)
        self.assertEqual(settings.identity_max_age_seconds, 0.75)
        self.assertEqual(settings.attendance_timezone, "Asia/Manila")

    def test_brightness_limits_must_be_ordered(self):
        with self.assertRaisesRegex(ConfigError, "BRIGHTNESS_MIN.*less than"):
            self.load_config(
                {
                    "ATTENDANCE_CAPTURE_BRIGHTNESS_MIN": "90",
                    "ATTENDANCE_CAPTURE_BRIGHTNESS_MAX": "90",
                }
            )

    def test_data_directory_is_created_only_when_requested(self):
        settings = self.load_config(
            {"ATTENDANCE_DATA_DIR": "nested/school-data"}
        )
        self.assertFalse(settings.data_dir.exists())

        settings.ensure_data_directory()

        self.assertTrue(settings.data_dir.is_dir())

    def test_unusable_data_path_has_a_helpful_error(self):
        blocking_file = self.root / "regular-file"
        blocking_file.write_text("not a directory", encoding="utf-8")
        settings = self.load_config(
            {"ATTENDANCE_DATA_DIR": str(blocking_file / "records")}
        )

        with self.assertRaisesRegex(ConfigError, "ATTENDANCE_DATA_DIR"):
            settings.ensure_data_directory()


if __name__ == "__main__":
    unittest.main()
