"""Application configuration and paths, independent of the launch directory."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


APP_DIR = Path(__file__).resolve().parent


class ConfigError(ValueError):
    """Raised when the application environment has invalid settings."""


def _resolve_from_app_dir(value: str | None, default: Path) -> Path:
    path = Path(value).expanduser() if value else default
    if not path.is_absolute():
        path = APP_DIR / path
    return path.resolve()


def _positive_float(env: Mapping[str, str], name: str, default: float) -> float:
    value = env.get(name, str(default))
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name} must be a number; got {value!r}.") from exc
    if not math.isfinite(result) or result <= 0:
        raise ConfigError(f"{name} must be a finite number greater than zero.")
    return result


def _non_negative_float(
    env: Mapping[str, str], name: str, default: float
) -> float:
    value = env.get(name, str(default))
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name} must be a number; got {value!r}.") from exc
    if not math.isfinite(result) or result < 0:
        raise ConfigError(f"{name} must be a finite number zero or greater.")
    return result


def _positive_int(env: Mapping[str, str], name: str, default: int) -> int:
    value = env.get(name, str(default))
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name} must be an integer; got {value!r}.") from exc
    if result <= 0:
        raise ConfigError(f"{name} must be a positive integer.")
    return result


@dataclass(frozen=True)
class AppConfig:
    """Validated runtime settings. Loading config never creates files or devices."""

    app_dir: Path
    data_dir: Path
    model_path: Path
    camera_index: int
    detector: str
    yolo_confidence: float
    frame_interval_seconds: float
    capture_max_age_seconds: float
    capture_min_face_size_pixels: int
    capture_min_blur_score: float
    capture_brightness_min: float
    capture_brightness_max: float
    recognition_minimum_similarity: float
    recognition_minimum_margin: float
    stable_identity_frames: int
    identity_evidence_window_seconds: float
    identity_max_age_seconds: float
    attendance_timezone: str | None

    @property
    def users_file(self) -> Path:
        return self.data_dir / "users.txt"

    @property
    def log_file(self) -> Path:
        return self.data_dir / "log.txt"

    @property
    def photos_dir(self) -> Path:
        return self.data_dir / "assets"

    def ensure_data_directory(self) -> None:
        """Create the writable data directory when application startup needs it."""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ConfigError(
                f"Cannot create application data directory '{self.data_dir}'. "
                "Choose a writable location with ATTENDANCE_DATA_DIR."
            ) from exc
        if not self.data_dir.is_dir():
            raise ConfigError(
                f"Application data path '{self.data_dir}' is not a directory. "
                "Choose a writable directory with ATTENDANCE_DATA_DIR."
            )

    @classmethod
    def from_environment(
        cls, environ: Mapping[str, str] | None = None
    ) -> AppConfig:
        """Load settings, resolving relative paths from the application directory."""
        env = os.environ if environ is None else environ

        data_dir = _resolve_from_app_dir(
            env.get("ATTENDANCE_DATA_DIR"), APP_DIR / "data"
        )
        model_path = _resolve_from_app_dir(
            env.get("ATTENDANCE_MODEL_PATH"), APP_DIR / "yolov8n-face-lindevs.pt"
        )

        camera_value = env.get("ATTENDANCE_CAMERA_INDEX", "0")
        try:
            camera_index = int(camera_value)
        except (TypeError, ValueError) as exc:
            raise ConfigError(
                f"ATTENDANCE_CAMERA_INDEX must be a non-negative integer; "
                f"got {camera_value!r}."
            ) from exc
        if camera_index < 0:
            raise ConfigError("ATTENDANCE_CAMERA_INDEX must be non-negative.")

        detector = env.get("ATTENDANCE_DETECTOR", "yolo").strip().lower()
        if detector not in {"yolo", "haar"}:
            raise ConfigError(
                "ATTENDANCE_DETECTOR must be 'yolo' or 'haar'; "
                f"got {detector!r}."
            )

        confidence = _positive_float(
            env, "ATTENDANCE_YOLO_CONFIDENCE", 0.40
        )
        if confidence > 1:
            raise ConfigError("ATTENDANCE_YOLO_CONFIDENCE must not exceed 1.")

        frame_interval = _positive_float(
            env, "ATTENDANCE_FRAME_INTERVAL_SECONDS", 0.03
        )
        capture_max_age = _positive_float(
            env, "ATTENDANCE_CAPTURE_MAX_AGE_SECONDS", 1.0
        )
        capture_min_face_size = _positive_int(
            env, "ATTENDANCE_CAPTURE_MIN_FACE_SIZE_PIXELS", 80
        )
        capture_min_blur = _non_negative_float(
            env, "ATTENDANCE_CAPTURE_MIN_BLUR_SCORE", 50.0
        )
        capture_brightness_min = _non_negative_float(
            env, "ATTENDANCE_CAPTURE_BRIGHTNESS_MIN", 40.0
        )
        capture_brightness_max = _non_negative_float(
            env, "ATTENDANCE_CAPTURE_BRIGHTNESS_MAX", 220.0
        )
        for name, brightness in (
            ("ATTENDANCE_CAPTURE_BRIGHTNESS_MIN", capture_brightness_min),
            ("ATTENDANCE_CAPTURE_BRIGHTNESS_MAX", capture_brightness_max),
        ):
            if brightness > 255:
                raise ConfigError(f"{name} must not exceed 255.")
        if capture_brightness_min >= capture_brightness_max:
            raise ConfigError(
                "ATTENDANCE_CAPTURE_BRIGHTNESS_MIN must be less than "
                "ATTENDANCE_CAPTURE_BRIGHTNESS_MAX."
            )

        recognition_similarity = _non_negative_float(
            env, "ATTENDANCE_MINIMUM_SIMILARITY", 0.50
        )
        recognition_margin = _non_negative_float(
            env, "ATTENDANCE_MINIMUM_MARGIN", 0.08
        )
        if recognition_similarity > 1:
            raise ConfigError("ATTENDANCE_MINIMUM_SIMILARITY must not exceed 1.")
        if recognition_margin > 2:
            raise ConfigError("ATTENDANCE_MINIMUM_MARGIN must not exceed 2.")
        stable_identity_frames = _positive_int(
            env, "ATTENDANCE_STABLE_IDENTITY_FRAMES", 3
        )
        evidence_window = _positive_float(
            env, "ATTENDANCE_IDENTITY_EVIDENCE_WINDOW_SECONDS", 2.0
        )
        identity_max_age = _positive_float(
            env, "ATTENDANCE_IDENTITY_MAX_AGE_SECONDS", 1.0
        )
        timezone_value = env.get("ATTENDANCE_TIMEZONE", "").strip() or None

        return cls(
            app_dir=APP_DIR,
            data_dir=data_dir,
            model_path=model_path,
            camera_index=camera_index,
            detector=detector,
            yolo_confidence=confidence,
            frame_interval_seconds=frame_interval,
            capture_max_age_seconds=capture_max_age,
            capture_min_face_size_pixels=capture_min_face_size,
            capture_min_blur_score=capture_min_blur,
            capture_brightness_min=capture_brightness_min,
            capture_brightness_max=capture_brightness_max,
            recognition_minimum_similarity=recognition_similarity,
            recognition_minimum_margin=recognition_margin,
            stable_identity_frames=stable_identity_frames,
            identity_evidence_window_seconds=evidence_window,
            identity_max_age_seconds=identity_max_age,
            attendance_timezone=timezone_value,
        )
