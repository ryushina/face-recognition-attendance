import cv2, time, threading, os
import logging
from datetime import datetime
from pathlib import Path
import math
from config import AppConfig


_UI_UPDATE_UNSET = object()


class DetectorInitializationError(RuntimeError):
    """Raised when neither the requested detector nor its fallback is usable."""


class CameraService:
    def __init__(self, camera_index=None, detector=None,
                 yolo_model_path=None, yolo_conf=None, config=None,
                 stop_timeout_seconds=2.0, recognition_service=None):
        self.config = config or AppConfig.from_environment()
        self.camera_index = (
            self.config.camera_index if camera_index is None else camera_index
        )
        # Thread-safe last frame + boxes
        self._last_frame_lock = threading.Lock()
        self._last_frame_bgr = None
        self._last_boxes = []
        self._last_frame_id = None
        self._last_frame_captured_monotonic = None
        self._next_frame_id = 0
        self.last_captured_frame_id = None
        self.is_face_detected = False
        self._ui_update_lock = threading.Lock()
        self._latest_ui_update = None

        self._state_lock = threading.Lock()
        self._stop_event = threading.Event()
        self.running = False
        self.thread = None
        self.cap = None
        self.camera_error = None
        self.stop_timeout_seconds = float(stop_timeout_seconds)
        if (
            not math.isfinite(self.stop_timeout_seconds)
            or self.stop_timeout_seconds <= 0
        ):
            raise ValueError("stop_timeout_seconds must be a finite positive number.")

        # --- Detector selection ---
        requested_detector = (detector or self.config.detector).strip().lower()
        if requested_detector not in {"yolo", "haar"}:
            raise DetectorInitializationError(
                f"Unsupported face detector {requested_detector!r}. "
                "Choose 'yolo' or 'haar'."
            )
        self.detector = requested_detector
        configured_model_path = (
            Path(yolo_model_path).expanduser()
            if yolo_model_path is not None
            else self.config.model_path
        )
        if not configured_model_path.is_absolute():
            configured_model_path = self.config.app_dir / configured_model_path
        self.yolo_model_path = configured_model_path.resolve()
        self.yolo = None
        self.yolo_conf = float(
            self.config.yolo_confidence if yolo_conf is None else yolo_conf
        )
        self.frame_interval_seconds = self.config.frame_interval_seconds
        self.capture_max_age_seconds = self.config.capture_max_age_seconds
        self.capture_min_face_size_pixels = (
            self.config.capture_min_face_size_pixels
        )
        self.capture_min_blur_score = self.config.capture_min_blur_score
        self.capture_brightness_min = self.config.capture_brightness_min
        self.capture_brightness_max = self.config.capture_brightness_max
        self.recognition_service = recognition_service

        if self.recognition_service is not None:
            self.detector_status = "Recognition: OpenCV YuNet + SFace active."
            return

        yolo_error = None
        if self.detector == "yolo":
            try:
                if not self.yolo_model_path.is_file():
                    raise FileNotFoundError(
                        f"Face detector weights not found at '{self.yolo_model_path}'. "
                        "Set ATTENDANCE_MODEL_PATH to the model file."
                    )
                from ultralytics import YOLO
                self.yolo = YOLO(str(self.yolo_model_path))
            except Exception as exc:
                yolo_error = str(exc)
                self.detector = "haar"

        if self.detector != "yolo":
            cascade_path = (
                Path(cv2.data.haarcascades)
                / "haarcascade_frontalface_default.xml"
            )
            try:
                if not cascade_path.is_file():
                    raise FileNotFoundError(
                        f"OpenCV Haar cascade not found at '{cascade_path}'."
                    )
                cascade = cv2.CascadeClassifier(str(cascade_path))
                if cascade.empty():
                    raise RuntimeError(
                        f"OpenCV could not load the Haar cascade at '{cascade_path}'."
                    )
            except Exception as exc:
                details = f" Haar fallback failed: {exc}"
                if yolo_error:
                    details = f" YOLO initialization also failed: {yolo_error}." + details
                raise DetectorInitializationError(
                    f"No face detector could be initialized.{details}"
                ) from exc

            self.face_cascade = cascade
            if yolo_error:
                self.detector_status = (
                    "Face detector: Haar active. "
                    f"YOLO could not initialize: {yolo_error}"
                )
            elif requested_detector == "haar":
                self.detector_status = "Face detector: Haar active (configured)."
            else:
                self.detector_status = "Face detector: Haar active."
        else:
            self.detector_status = "Face detector: YOLO active."

    def start(self):
        """Open the camera and start one capture worker, returning success."""
        with self._state_lock:
            if self.running:
                return True

            if self.thread is not None and self.thread.is_alive():
                message = (
                    "The previous camera worker is still stopping; "
                    "wait before restarting the camera."
                )
                self.camera_error = message
                capture = None
            else:
                self.thread = None
                self._stop_event.clear()
                self._clear_frame_state()
                self.camera_error = None
                self._publish_ui_update(
                    frame=None, status="Opening camera...", identity=None,
                    frame_id=None, captured_monotonic=None,
                )

                capture = None
                message = None
                try:
                    capture = cv2.VideoCapture(self.camera_index)
                    if capture is None or not capture.isOpened():
                        message = (
                            f"Could not open camera index {self.camera_index}. "
                            "Check that the camera is connected and available."
                        )
                except Exception as exc:
                    message = f"Could not open camera index {self.camera_index}: {exc}"

                if message is None:
                    self.cap = capture
                    self.running = True
                    try:
                        worker = threading.Thread(
                            target=self._capture_loop,
                            args=(capture,),
                            daemon=True,
                            name="attendance-camera",
                        )
                        self.thread = worker
                        self._publish_ui_update(status="Camera running.")
                        worker.start()
                    except Exception as exc:
                        self.running = False
                        self.thread = None
                        self.cap = None
                        message = f"Could not start the camera worker: {exc}"

                if message is not None and capture is not None:
                    self.cap = None
                    try:
                        capture.release()
                    except Exception:
                        pass

                if message is not None:
                    self.running = False
                    self.camera_error = message

        if message is not None:
            self._report_camera_error(message)
            return False
        return True

    def stop(self):
        """Request a stop and wait briefly without releasing an active read."""
        with self._state_lock:
            self.running = False
            self._stop_event.set()
            worker = self.thread

        self._clear_frame_state()
        self._publish_ui_update(
            frame=None, status="Camera stopped.", identity=None,
            frame_id=None, captured_monotonic=None,
        )
        if worker is None or worker is threading.current_thread():
            return True

        worker.join(timeout=self.stop_timeout_seconds)
        if worker.is_alive():
            message = (
                "Camera worker did not stop before the shutdown timeout. "
                "It still owns the camera; wait for it to exit before restarting."
            )
            self._report_camera_error(message)
            return False
        return True

    # -------------------- Core loop --------------------
    def _capture_loop(self, capture):
        """Capture until stopped or a camera, detector, or display error occurs."""
        error = None
        try:
            while not self._stop_event.is_set():
                try:
                    ret, frame = capture.read()
                    acquired_monotonic = time.monotonic()
                except Exception as exc:
                    error = f"Camera read failed: {exc}"
                    break

                if self._stop_event.is_set():
                    break
                if not ret or frame is None:
                    error = (
                        f"Camera index {self.camera_index} returned no frame. "
                        "Check the connection and restart the camera."
                    )
                    break

                self._next_frame_id += 1
                frame_id = self._next_frame_id

                try:
                    match_result = None
                    if self.recognition_service is not None:
                        detections = self.recognition_service.detect(frame)
                        boxes = [detection.box for detection in detections]
                        if not detections:
                            from recognition_service import MatchResult
                            match_result = MatchResult("unknown", message="No face detected.", reason="no_face")
                        elif len(detections) > 1:
                            from recognition_service import MatchResult
                            match_result = MatchResult("ambiguous", message="Multiple faces detected.", reason="multiple_faces")
                        else:
                            embedding = self.recognition_service.extract(frame, detections[0])
                            match_result = self.recognition_service.match(embedding)
                    else:
                        boxes = self._detect_faces(frame)
                    frame_snapshot = frame.copy()
                    if self._stop_event.is_set():
                        break

                    # Store the image and detection result together.
                    with self._last_frame_lock:
                        if self._stop_event.is_set():
                            break
                        self._last_frame_bgr = frame_snapshot
                        self._last_boxes = list(boxes)
                        self._last_frame_id = frame_id
                        self._last_frame_captured_monotonic = acquired_monotonic
                        self.is_face_detected = bool(boxes)

                    for (x, y, w, h) in boxes:
                        side = min(w, h)
                        cx, cy = x + w // 2, y + h // 2
                        x1, y1 = cx - side // 2, cy - side // 2
                        x2, y2 = x1 + side, y1 + side
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

                    self._publish_ui_update(
                        frame=frame.copy(), identity=match_result,
                        frame_id=frame_id, captured_monotonic=acquired_monotonic,
                    )
                except Exception as exc:
                    if not self._stop_event.is_set():
                        error = f"Camera frame processing failed: {exc}"
                    break

                if self._stop_event.wait(self.frame_interval_seconds):
                    break
        finally:
            self._clear_frame_state()
            try:
                capture.release()
            except Exception as exc:
                if error is None:
                    error = f"Could not release camera index {self.camera_index}: {exc}"

            with self._state_lock:
                if self.cap is capture:
                    self.cap = None
                self.running = False

            if error is not None:
                self._report_camera_error(error)

    def _publish_ui_update(
        self, *, frame=_UI_UPDATE_UNSET, status=_UI_UPDATE_UNSET,
        identity=_UI_UPDATE_UNSET, frame_id=_UI_UPDATE_UNSET,
        captured_monotonic=_UI_UPDATE_UNSET,
    ):
        """Merge an update into one bounded slot for the Tk thread to consume."""
        with self._ui_update_lock:
            update = dict(self._latest_ui_update or {})
            if frame is not _UI_UPDATE_UNSET:
                update["frame"] = frame
            if status is not _UI_UPDATE_UNSET:
                update["status"] = status
            if identity is not _UI_UPDATE_UNSET:
                update["identity"] = identity
            if frame_id is not _UI_UPDATE_UNSET:
                update["frame_id"] = frame_id
            if captured_monotonic is not _UI_UPDATE_UNSET:
                update["captured_monotonic"] = captured_monotonic
            self._latest_ui_update = update

    def take_latest_ui_update(self):
        """Return and clear the most recent frame/status update atomically."""
        with self._ui_update_lock:
            update = self._latest_ui_update
            self._latest_ui_update = None
            return update

    def _clear_frame_state(self):
        """Discard the cached frame and face result together."""
        with self._last_frame_lock:
            self._last_frame_bgr = None
            self._last_boxes = []
            self._last_frame_id = None
            self._last_frame_captured_monotonic = None
            self.is_face_detected = False

    def _report_camera_error(self, message):
        """Save a readable last error and make it visible to the operator."""
        self.camera_error = message
        logging.getLogger("face_attendance.camera").error("%s", message)
        self._publish_ui_update(frame=None, status=message, identity=None)

    # -------------------- Detection --------------------
    def _detect_faces(self, frame_bgr):
        """
        Return list of face boxes as (x, y, w, h).
        """
        if self.yolo is not None:
            results = self.yolo.predict(frame_bgr, conf=self.yolo_conf, verbose=False)
            boxes = []
            if results and len(results) > 0:
                r = results[0]
                if r.boxes is not None:
                    for b in r.boxes:
                        x1, y1, x2, y2 = [int(v) for v in b.xyxy[0].tolist()]
                        w, h = x2 - x1, y2 - y1
                        if w >= 20 and h >= 20:
                            boxes.append((x1, y1, w, h))
            return boxes

        # Haar fallback
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.2, 5, minSize=(50, 50))
        return [(int(x), int(y), int(w), int(h)) for (x, y, w, h) in faces]

    # -------------------- Capture API --------------------
    def capture_face(
        self, save_dir, filename_prefix="face", padding_ratio=0.25, min_size=None
    ):
        """
        Save one fresh, suitable face from the latest frame into save_dir.
        Returns: (True, saved_path) or (False, reason).
        """
        # Snapshot the image, detection, ID, and acquisition time together.
        with self._last_frame_lock:
            if self._last_frame_bgr is None:
                return False, "No frame available yet."
            frame = self._last_frame_bgr.copy()
            boxes = list(self._last_boxes)
            frame_id = self._last_frame_id
            acquired_monotonic = self._last_frame_captured_monotonic

        if frame_id is None or acquired_monotonic is None:
            return False, "The camera frame has no capture metadata. Wait for a fresh frame."
        frame_age = time.monotonic() - acquired_monotonic
        if frame_age < 0 or frame_age > self.capture_max_age_seconds:
            return False, "The camera frame is stale. Wait for a fresh frame and try again."

        if not boxes:
            return False, "No face detected. Look at the camera and try again."
        if len(boxes) != 1:
            return False, "More than one face detected. Make sure only one person is in frame."

        try:
            if len(boxes[0]) != 4:
                raise ValueError("expected four box coordinates")
            x, y, w, h = (int(value) for value in boxes[0])
        except (TypeError, ValueError, OverflowError):
            return False, "Face detection returned invalid bounds. Reposition and try again."

        try:
            frame_height, frame_width = frame.shape[:2]
        except (AttributeError, TypeError, ValueError):
            return False, "The camera frame has invalid dimensions. Restart the camera and try again."

        if w <= 0 or h <= 0:
            return False, "Face detection returned an empty box. Reposition and try again."
        if x < 0 or y < 0 or x + w > frame_width or y + h > frame_height:
            return False, "The detected face is clipped by the frame edge. Move back into view."

        required_min_size = (
            self.capture_min_face_size_pixels if min_size is None else min_size
        )
        try:
            required_min_size = int(required_min_size)
        except (TypeError, ValueError, OverflowError):
            return False, "Minimum face size must be a positive pixel count."
        if required_min_size <= 0:
            return False, "Minimum face size must be a positive pixel count."
        if min(w, h) < required_min_size:
            return False, (
                f"Face is too small ({min(w, h)} px). Move closer until it is at least "
                f"{required_min_size} px tall and wide."
            )

        try:
            padding_ratio = float(padding_ratio)
        except (TypeError, ValueError, OverflowError):
            return False, "Capture padding must be a number between 0 and 1."
        if not math.isfinite(padding_ratio) or not 0 <= padding_ratio <= 1:
            return False, "Capture padding must be a number between 0 and 1."

        pad_x = int(round(w * padding_ratio))
        pad_y = int(round(h * padding_ratio))
        x1, y1 = x - pad_x, y - pad_y
        x2, y2 = x + w + pad_x, y + h + pad_y
        if x1 < 0 or y1 < 0 or x2 > frame_width or y2 > frame_height:
            return False, "Face is too close to the frame edge for padding. Move toward the center."

        face_roi = frame[y:y + h, x:x + w]
        try:
            grayscale_face = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
            blur_score = float(
                cv2.Laplacian(grayscale_face, cv2.CV_64F).var()
            )
            brightness = float(grayscale_face.mean())
        except Exception as exc:
            return False, f"Could not check face image quality: {exc}. Try again."

        if not math.isfinite(blur_score) or not math.isfinite(brightness):
            return False, "Could not measure face image quality. Improve the lighting and try again."
        if blur_score < self.capture_min_blur_score:
            return False, (
                f"Face image is blurry (sharpness {blur_score:.1f}). Hold still and try again."
            )
        if brightness < self.capture_brightness_min:
            return False, "Face is too dark. Add light and face the camera directly."
        if brightness > self.capture_brightness_max:
            return False, "Face is too bright. Reduce glare and try again."

        crop = frame[y1:y2, x1:x2]
        try:
            crop_height, crop_width = crop.shape[:2]
        except (AttributeError, TypeError, ValueError):
            return False, "Could not create the padded face crop. Move into the frame and retry."
        if crop_height != y2 - y1 or crop_width != x2 - x1:
            return False, "The padded face crop was clipped. Move toward the center and retry."

        ts = datetime.now().strftime("%Y%m%d_%H%M%S%f")[:-3]
        fpath = os.path.join(save_dir, f"{filename_prefix}_f{frame_id}_{ts}.jpg")

        if not os.path.isdir(save_dir):
            try:
                os.makedirs(save_dir, exist_ok=True)
            except Exception as exc:
                return False, f"Failed to create capture directory: {exc}"

        try:
            if not cv2.imwrite(fpath, crop):
                return False, "Could not write the captured image. Check disk space and permissions."
        except Exception as e:
            return False, f"Could not save the captured image: {e}"

        self.last_captured_frame_id = frame_id
        return True, fpath

    # Optional helper if you ever want to block until a face appears.
    def wait_for_face(self, timeout=None):
        """
        Block until a face is detected, or timeout (seconds) expires.
        Returns True if seen; False otherwise.
        """
        end = None if timeout is None else (time.time() + timeout)
        while True:
            if self.is_face_detected:
                return True
            if end is not None and time.time() > end:
                return False
            time.sleep(0.05)

