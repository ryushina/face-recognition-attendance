"""Threaded enrollment-photo indexing for the local recognition gallery."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import queue
import threading

from recognition_service import FaceEmbedding


@dataclass(frozen=True)
class IndexingResult:
    student_id: str
    indexed_samples: int
    error: str | None = None


class EnrollmentIndexer:
    """Read saved samples and publish an all-or-nothing compatible student index."""

    def __init__(self, repository, recognition_service, data_dir, *, image_reader=None):
        self.repository = repository
        self.recognition_service = recognition_service
        self.data_dir = Path(data_dir).resolve()
        self.image_reader = image_reader
        self._lock = threading.Lock()
        self._results = queue.Queue()
        self._thread = None

    def index_student(self, student_id: str) -> IndexingResult:
        """Index synchronously; production callers should use submit()."""
        try:
            samples = self.repository.begin_indexing(student_id)
            if not samples:
                message = "No saved face samples are available to index."
                self.repository.fail_indexing(student_id, message)
                return IndexingResult(student_id, 0, message)
            embeddings = {}
            for sample in samples:
                image_path = Path(sample.image_path)
                if not image_path.is_absolute():
                    image_path = self.data_dir / image_path
                image = self._read_image(image_path)
                if image is None:
                    raise ValueError(f"Saved face image is missing or unreadable: {sample.image_path}")
                embedding = self.recognition_service.extract_single(image)
                if not isinstance(embedding, FaceEmbedding):
                    raise ValueError("Recognition service returned an invalid embedding.")
                embeddings[sample.sample_id] = embedding
            count = self.repository.complete_indexing(student_id, embeddings)
            return IndexingResult(student_id, count)
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            try:
                self.repository.fail_indexing(student_id, message)
            except Exception as persist_exc:
                message = f"{message}; could not save indexing status: {persist_exc}"
            return IndexingResult(student_id, 0, message)

    def submit(self, student_id: str) -> bool:
        """Start one bounded worker; results are consumed by the Tk poller."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._thread = threading.Thread(
                target=self._index_worker,
                args=(student_id,),
                daemon=True,
                name="attendance-enrollment-indexer",
            )
            self._thread.start()
            return True

    def poll_result(self):
        """Return one completed result without blocking."""
        try:
            return self._results.get_nowait()
        except queue.Empty:
            return None

    def _index_worker(self, student_id):
        self._results.put(self.index_student(student_id))

    def _read_image(self, path):
        if self.image_reader is not None:
            return self.image_reader(path)
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError("OpenCV is required to index saved face images.") from exc
        return cv2.imread(str(path))
