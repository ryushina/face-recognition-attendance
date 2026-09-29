"""OpenCV YuNet detection and SFace alignment/embedding extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
import threading


YUNET_FILE = "face_detection_yunet_2023mar.onnx"
SFACE_FILE = "face_recognition_sface_2021dec.onnx"
YUNET_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
SFACE_SHA256 = "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"
EMBEDDING_DIMENSION = 128
PREPROCESSING_ID = "opencv-face-recognizer-sf-aligncrop-bgr-float32-l2-v1"
MODEL_VERSION = f"yunet:{YUNET_FILE}:{YUNET_SHA256};sface:{SFACE_FILE}:{SFACE_SHA256}"


class RecognitionError(RuntimeError):
    """Base error for model setup, input, and feature extraction failures."""


class NoFaceDetected(RecognitionError):
    """The image does not contain a detectable face."""


class MultipleFacesDetected(RecognitionError):
    """A single-face operation received an image with more than one face."""


@dataclass(frozen=True)
class FaceDetection:
    """One YuNet detection and its original row for OpenCV landmark alignment."""

    box: tuple[int, int, int, int]
    landmarks: tuple[float, ...]
    score: float
    raw_row: object = field(repr=False, compare=False)


@dataclass(frozen=True)
class FaceEmbedding:
    """A validated, unit-normalized SFace feature tied to its model version."""

    vector: tuple[float, ...]
    box: tuple[int, int, int, int]
    detector_score: float
    model_version: str = MODEL_VERSION
    preprocessing_id: str = PREPROCESSING_ID


@dataclass(frozen=True)
class MatchResult:
    """Identity decision; similarity scores are not probabilities."""

    status: str
    student_id: str | None = None
    display_name: str | None = None
    score: float | None = None
    runner_up_score: float | None = None
    model_version: str = MODEL_VERSION
    message: str = ""


def _as_list(value):
    if hasattr(value, "tolist"):
        value = value.tolist()
    return value


def _frame_dimensions(frame) -> tuple[int, int]:
    try:
        shape = frame.shape
        height, width = int(shape[0]), int(shape[1])
    except (AttributeError, IndexError, TypeError, ValueError, OverflowError) as exc:
        raise RecognitionError("Input must be a non-empty BGR image array.") from exc
    if height <= 0 or width <= 0 or len(shape) < 3 or int(shape[2]) != 3:
        raise RecognitionError("Input must be a non-empty three-channel BGR image.")
    return width, height


def _vector_values(value) -> list[float]:
    values = _as_list(value)
    if not isinstance(values, (list, tuple)):
        raise RecognitionError("SFace returned a feature with an invalid shape.")
    if len(values) == 1 and isinstance(_as_list(values[0]), (list, tuple)):
        values = _as_list(values[0])
    try:
        return [float(component) for component in values]
    except (TypeError, ValueError, OverflowError) as exc:
        raise RecognitionError("SFace returned a non-numeric feature.") from exc


class RecognitionService:
    """Load the selected models once and expose an injectable, UI-free interface."""

    def __init__(
        self,
        model_dir: str | Path | None = None,
        *,
        cv2_module=None,
        detector=None,
        recognizer=None,
        minimum_similarity: float = 0.50,
        minimum_margin: float = 0.08,
    ):
        model_directory = Path(model_dir or Path(__file__).resolve().parent / "models")
        self.detector_path = (model_directory / YUNET_FILE).expanduser().resolve()
        self.recognizer_path = (model_directory / SFACE_FILE).expanduser().resolve()
        self._model_lock = threading.RLock()
        self.model_version = MODEL_VERSION
        self.preprocessing_id = PREPROCESSING_ID
        self.minimum_similarity = float(minimum_similarity)
        self.minimum_margin = float(minimum_margin)
        if not 0.0 <= self.minimum_similarity <= 1.0:
            raise ValueError("minimum_similarity must be between 0 and 1.")
        if not 0.0 <= self.minimum_margin <= 2.0:
            raise ValueError("minimum_margin must be between 0 and 2.")
        self._gallery = ()

        if detector is not None and recognizer is not None:
            self._cv2 = cv2_module
            self.detector = detector
            self.recognizer = recognizer
            return

        for path in (self.detector_path, self.recognizer_path):
            try:
                if not path.is_file() or path.stat().st_size <= 0:
                    raise FileNotFoundError("file is missing or empty")
            except OSError as exc:
                raise RecognitionError(
                    f"Recognition model is unavailable at '{path}': {exc}"
                ) from exc

        try:
            if cv2_module is None:
                import cv2 as cv2_module
            if not hasattr(cv2_module, "FaceDetectorYN") or not hasattr(
                cv2_module, "FaceRecognizerSF"
            ):
                raise RuntimeError(
                    "OpenCV face APIs are missing; install the pinned "
                    "opencv-contrib-python requirement."
                )
            self._cv2 = cv2_module
            self.detector = cv2_module.FaceDetectorYN.create(
                str(self.detector_path), "", (320, 320), 0.9, 0.3, 5000
            )
            self.recognizer = cv2_module.FaceRecognizerSF.create(
                str(self.recognizer_path), ""
            )
        except Exception as exc:
            raise RecognitionError(
                f"Could not load YuNet/SFace models from '{model_directory}': {exc}"
            ) from exc

    @classmethod
    def from_config(cls, config):
        """Load the model files from the application-owned models directory."""
        return cls(
            Path(config.app_dir) / "models",
            minimum_similarity=getattr(config, "recognition_minimum_similarity", 0.50),
            minimum_margin=getattr(config, "recognition_minimum_margin", 0.08),
        )

    def detect(self, frame) -> tuple[FaceDetection, ...]:
        """Return all valid YuNet boxes and landmarks for an OpenCV BGR frame."""
        width, height = _frame_dimensions(frame)
        with self._model_lock:
            try:
                self.detector.setInputSize((width, height))
                detection_result = self.detector.detect(frame)
            except Exception as exc:
                raise RecognitionError(f"YuNet face detection failed: {exc}") from exc

        try:
            rows = detection_result[1]
        except (IndexError, TypeError) as exc:
            raise RecognitionError("YuNet returned a malformed detection result.") from exc
        if rows is None:
            return ()
        rows = _as_list(rows)
        if not isinstance(rows, (list, tuple)):
            raise RecognitionError("YuNet returned detections in an invalid format.")

        faces = []
        for row in rows:
            raw_values = _as_list(row)
            if not isinstance(raw_values, (list, tuple)) or len(raw_values) != 15:
                raise RecognitionError("YuNet returned a face row with an invalid dimension.")
            try:
                values = [float(value) for value in raw_values]
            except (TypeError, ValueError, OverflowError) as exc:
                raise RecognitionError("YuNet returned non-numeric face data.") from exc
            if not all(math.isfinite(value) for value in values):
                raise RecognitionError("YuNet returned non-finite face data.")
            x, y, box_width, box_height = values[:4]
            x1, y1 = int(round(x)), int(round(y))
            x2, y2 = int(round(x + box_width)), int(round(y + box_height))
            if (
                box_width <= 0
                or box_height <= 0
                or x1 < 0
                or y1 < 0
                or x2 > width
                or y2 > height
            ):
                raise RecognitionError("YuNet returned face bounds outside the image.")
            landmarks = tuple(values[4:14])
            faces.append(
                FaceDetection(
                    (x1, y1, x2 - x1, y2 - y1),
                    landmarks,
                    values[14],
                    row,
                )
            )
        return tuple(faces)

    def extract(self, frame, face: FaceDetection) -> FaceEmbedding:
        """Align one previously detected face and return a normalized 128-vector."""
        _frame_dimensions(frame)
        if not isinstance(face, FaceDetection):
            raise RecognitionError("A YuNet face detection is required for alignment.")
        with self._model_lock:
            try:
                aligned = self.recognizer.alignCrop(frame, face.raw_row)
                raw_feature = self.recognizer.feature(aligned)
            except Exception as exc:
                raise RecognitionError(f"SFace feature extraction failed: {exc}") from exc

        values = _vector_values(raw_feature)
        if len(values) != EMBEDDING_DIMENSION:
            raise RecognitionError(
                f"SFace feature must contain {EMBEDDING_DIMENSION} values; got {len(values)}."
            )
        if not all(math.isfinite(value) for value in values):
            raise RecognitionError("SFace returned non-finite feature values.")
        norm = math.sqrt(sum(value * value for value in values))
        if not math.isfinite(norm) or norm <= 0:
            raise RecognitionError("SFace returned a zero-length feature.")
        normalized = tuple(value / norm for value in values)
        return FaceEmbedding(normalized, face.box, face.score)

    def extract_single(self, frame) -> FaceEmbedding:
        """Convenience path for enrollment images, which must contain one face."""
        faces = self.detect(frame)
        if not faces:
            raise NoFaceDetected("No face was found in the image.")
        if len(faces) > 1:
            raise MultipleFacesDetected(
                f"Expected one face for enrollment; found {len(faces)}."
            )
        return self.extract(frame, faces[0])

    def analyze_frame(self, frame) -> tuple[FaceEmbedding, ...]:
        """Extract features for every detected face in a live frame."""
        faces = self.detect(frame)
        return tuple(self.extract(frame, face) for face in faces)

    def set_gallery(self, gallery) -> int:
        """Atomically replace the in-memory gallery with fully compatible entries."""
        prepared = []
        for person in gallery:
            student_id = str(person.get("student_id", "")).strip()
            vectors = tuple(person.get("embeddings", ()))
            if not student_id or not vectors:
                continue
            normalized = []
            for raw in vectors:
                values = tuple(float(value) for value in raw)
                if (
                    len(values) != EMBEDDING_DIMENSION
                    or not all(math.isfinite(value) for value in values)
                    or not math.isclose(math.sqrt(sum(value * value for value in values)), 1.0, abs_tol=0.02)
                ):
                    normalized = []
                    break
                normalized.append(values)
            if normalized:
                prepared.append((student_id, str(person.get("name", "")), tuple(normalized)))
        with self._model_lock:
            self._gallery = tuple(prepared)
        return len(prepared)

    def match(self, embedding: FaceEmbedding) -> MatchResult:
        """Return recognized, unknown, or ambiguous based on student-level scores."""
        if not isinstance(embedding, FaceEmbedding):
            return MatchResult("unknown", message="Invalid face embedding.")
        if (
            embedding.model_version != MODEL_VERSION
            or embedding.preprocessing_id != PREPROCESSING_ID
            or len(embedding.vector) != EMBEDDING_DIMENSION
            or not all(math.isfinite(value) for value in embedding.vector)
        ):
            return MatchResult("unknown", message="Embedding version or data is incompatible.")
        with self._model_lock:
            gallery = self._gallery
        if not gallery:
            return MatchResult("unknown", message="Recognition gallery is empty.")

        candidates = []
        for student_id, name, samples in gallery:
            best = max(sum(a * b for a, b in zip(embedding.vector, sample)) for sample in samples)
            candidates.append((best, student_id, name))
        candidates.sort(reverse=True)
        top_score, student_id, name = candidates[0]
        runner_up = candidates[1][0] if len(candidates) > 1 else None
        if top_score < self.minimum_similarity:
            return MatchResult(
                "unknown", score=top_score, runner_up_score=runner_up,
                message="Best match is below the provisional similarity threshold.",
            )
        if runner_up is not None and top_score - runner_up < self.minimum_margin:
            return MatchResult(
                "ambiguous", score=top_score, runner_up_score=runner_up,
                message="Top student matches are too close to distinguish.",
            )
        return MatchResult(
            "recognized", student_id, name, top_score, runner_up,
        )

    def recognize_frame(self, frame) -> MatchResult:
        """Detect and classify a live frame without touching UI or storage."""
        faces = self.detect(frame)
        if not faces:
            return MatchResult("unknown", message="No face detected.")
        if len(faces) > 1:
            return MatchResult("ambiguous", message="Multiple faces detected.")
        return self.match(self.extract(frame, faces[0]))
