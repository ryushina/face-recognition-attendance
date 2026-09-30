"""Read-only checks of saved face photos, run outside the Tk event loop."""

from dataclasses import dataclass
import math
from pathlib import Path
import queue
import threading

import cv2


@dataclass(frozen=True)
class PhotoCheck:
    sample_id: int
    status: str
    message: str


@dataclass(frozen=True)
class PhotoReview:
    student_id: str
    checks: tuple[PhotoCheck, ...]


def check_photo(sample, config, recognition, *, image_reader=cv2.imread):
    path = Path(sample.image_path)
    if not path.is_absolute():
        path = config.data_dir / path
    image = image_reader(str(path))
    if image is None:
        return PhotoCheck(sample.sample_id, "replace", "File is missing or unreadable. Retake this photo.")
    if recognition is None:
        return PhotoCheck(sample.sample_id, "unchecked", "Face checks unavailable. Repair model setup in Diagnostics.")
    faces = recognition.detect(image)
    if not faces:
        return PhotoCheck(sample.sample_id, "replace", "No usable face detected. Retake with the whole face centered.")
    if len(faces) != 1:
        return PhotoCheck(sample.sample_id, "replace", "Multiple faces detected. Retake with only this student in view.")
    x, y, w, h = faces[0].box
    height, width = image.shape[:2]
    if min(w, h) <= 0 or x < 0 or y < 0 or x + w > width or y + h > height:
        return PhotoCheck(sample.sample_id, "replace", "Face is clipped or invalid. Retake centered.")
    gray = cv2.cvtColor(image[y:y+h, x:x+w], cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())
    if not math.isfinite(sharpness) or not math.isfinite(brightness):
        return PhotoCheck(sample.sample_id, "unchecked", "Image measurements are invalid. Retake this photo.")
    issues = []
    if min(w, h) < config.capture_min_face_size_pixels:
        issues.append("Face is too small; move closer")
    if sharpness < config.capture_min_blur_score:
        issues.append("Image is blurry; hold still")
    if brightness < config.capture_brightness_min:
        issues.append("Face is too dark; add light")
    if brightness > config.capture_brightness_max:
        issues.append("Face is too bright; reduce glare")
    measurements = f"Face {w} x {h} px; sharpness {sharpness:.1f}; brightness {brightness:.1f}."
    if issues:
        return PhotoCheck(sample.sample_id, "replace", ". ".join(issues) + ".\n" + measurements)
    # Exercise alignment and feature extraction without saving a new embedding.
    recognition.extract(image, faces[0])
    return PhotoCheck(sample.sample_id, "pass", "Passes current image checks. Test a fresh live scan next.\n" + measurements)


class PhotoReviewer:
    def __init__(self, config, recognition):
        self.config, self.recognition = config, recognition
        self._thread = None
        self._results = queue.Queue()

    def submit(self, student):
        if self._thread is not None and self._thread.is_alive():
            return False
        self._thread = threading.Thread(target=self._run, args=(student,), daemon=True, name="attendance-photo-review")
        self._thread.start()
        return True

    def _run(self, student):
        checks = []
        for sample in student.samples:
            try:
                checks.append(check_photo(sample, self.config, self.recognition))
            except Exception as exc:
                checks.append(PhotoCheck(sample.sample_id, "unchecked", f"Could not complete image checks: {str(exc)[:250]}"))
        self._results.put(PhotoReview(student.student_id, tuple(checks)))

    def poll_result(self):
        try:
            return self._results.get_nowait()
        except queue.Empty:
            return None
