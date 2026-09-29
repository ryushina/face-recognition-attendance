"""Fresh-frame state for turning repeated recognition results into evidence."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class StableRecognition:
    student_id: str
    display_name: str
    score: float | None
    model_version: str
    frame_id: int
    captured_monotonic: float
    consecutive_frames: int


class RecognitionEvidenceTracker:
    """Require distinct fresh frames with one identity within a bounded window."""

    def __init__(self, required_frames=3, window_seconds=2.0, max_age_seconds=1.0):
        if isinstance(required_frames, bool) or not isinstance(required_frames, int) or required_frames < 1:
            raise ValueError("required_frames must be a positive integer.")
        if not math.isfinite(window_seconds) or window_seconds <= 0:
            raise ValueError("window_seconds must be finite and positive.")
        if not math.isfinite(max_age_seconds) or max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be finite and positive.")
        self.required_frames = required_frames
        self.window_seconds = float(window_seconds)
        self.max_age_seconds = float(max_age_seconds)
        self.reset()

    def reset(self):
        self._student_id = None
        self._name = ""
        self._score = None
        self._model_version = ""
        self._first_capture = None
        self._last_capture = None
        self._last_frame_id = None
        self._count = 0

    def observe(
        self,
        result,
        *,
        frame_id,
        captured_monotonic,
        now_monotonic,
        camera_available=True,
        enabled=True,
    ) -> StableRecognition | None:
        """Consume one frame result. None means it cannot authorize an action."""
        if not enabled or not camera_available:
            self.reset()
            return None
        try:
            capture_time = float(captured_monotonic)
            now = float(now_monotonic)
            identifier = int(frame_id)
        except (TypeError, ValueError, OverflowError):
            self.reset()
            return None
        if (
            isinstance(frame_id, bool)
            or not math.isfinite(capture_time)
            or not math.isfinite(now)
            or identifier < 0
            or capture_time > now
            or now - capture_time > self.max_age_seconds
        ):
            self.reset()
            return None

        status = getattr(result, "status", None)
        student_id = getattr(result, "student_id", None)
        if status != "recognized" or not student_id:
            self.reset()
            return None

        if self._last_frame_id is not None and identifier <= self._last_frame_id:
            # An old or repeated inference result must never count twice.
            return None

        if self._student_id is not None and student_id != self._student_id:
            self.reset()
        if self._first_capture is not None and (
            capture_time < self._last_capture
            or capture_time - self._first_capture > self.window_seconds
        ):
            self.reset()

        if self._student_id is None:
            self._student_id = str(student_id)
            self._name = str(getattr(result, "display_name", None) or student_id)
            self._model_version = str(getattr(result, "model_version", ""))
            self._first_capture = capture_time
        self._score = getattr(result, "score", None)
        self._last_capture = capture_time
        self._last_frame_id = identifier
        self._count += 1
        if self._count < self.required_frames:
            return None
        return StableRecognition(
            self._student_id,
            self._name,
            self._score,
            self._model_version,
            identifier,
            capture_time,
            self._count,
        )
