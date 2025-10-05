from ultralytics import YOLO
import cv2, time, threading, os
from datetime import datetime


class CameraService:
    def __init__(self, view, camera_index=0, detector="yolo",
                 yolo_model_path="yolov8n-face-lindevs.pt", yolo_conf=0.40):
        self.view = view
        self.camera_index = camera_index
        self.cap = cv2.VideoCapture(self.camera_index)
        self.running = False
        self.thread = None

        # Thread-safe last frame + boxes
        self._last_frame_lock = threading.Lock()
        self._last_frame_bgr = None
        self._last_boxes = []

        # Public face-present flag
        self.is_face_detected = False

        # --- Detector selection ---
        self.detector = detector.lower()
        self.yolo = None
        self.yolo_conf = float(yolo_conf)

        if self.detector == "yolo":
            try:
                from ultralytics import YOLO  # import here to avoid module error on machines without it
                self.yolo = YOLO(yolo_model_path)
            except Exception as e:
                print(f"[CameraService] YOLO load failed: {e}. Falling back to Haar.")
                self.detector = "haar"

        if self.detector != "yolo":
            self.face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )

    def start(self):
        """Start the camera in a background thread."""
        if self.running:
            return
        self.is_face_detected = False            # reset on (re)start
        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop the camera and release resources."""
        self.running = False
        if self.cap.isOpened():
            self.cap.release()

    # -------------------- Core loop --------------------
    def _capture_loop(self):
        """Continuously capture frames and update the view."""
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.05)
                continue

            # Detect faces on this frame
            boxes = self._detect_faces(frame)

            # Update shared state atomically
            with self._last_frame_lock:
                self._last_frame_bgr = frame.copy()
                self._last_boxes = list(boxes)
                self.is_face_detected = bool(boxes)

            # Draw overlays after storing
            for (x, y, w, h) in boxes:
                side = min(w, h)
                cx, cy = x + w // 2, y + h // 2
                x1, y1 = cx - side // 2, cy - side // 2
                x2, y2 = x1 + side, y1 + side
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

            # Update the UI safely from main thread
            self.view.main_content.after(0, lambda f=frame: self.view.update_camera_frame(f))
            time.sleep(0.03)  # ~30 FPS cap

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
    def capture_face(self, save_dir, filename_prefix="face", padding_ratio=0.15, min_size=40):
        """
        Save the largest detected face from the latest frame into save_dir.
        Returns: (True, saved_path) or (False, reason).
        """
        # Gate early using the live flag (prevents useless disk writes/UI calls)
        if not self.is_face_detected:
            return False, "No face detected right now. Please face the camera and try again."

        if not os.path.isdir(save_dir):
            try:
                os.makedirs(save_dir, exist_ok=True)
            except Exception as e:
                return False, f"Failed to create directory: {e}"

        # Use the last frame and boxes captured together
        with self._last_frame_lock:
            if self._last_frame_bgr is None:
                return False, "No frame available yet."
            frame = self._last_frame_bgr.copy()
            boxes = list(self._last_boxes)

        # Double-check (safety): if boxes empty (race), run detection once more
        if not boxes:
            boxes = self._detect_faces(frame)
            if not boxes:
                return False, "No face detected."

        largest = max(boxes, key=lambda b: b[2] * b[3])
        x, y, w, h = largest

        side = int(min(w, h))
        cx, cy = x + w // 2, y + h // 2
        side = max(side, min_size)

        pad = int(side * float(padding_ratio))
        side_padded = side + 2 * pad

        x1 = max(0, cx - side_padded // 2)
        y1 = max(0, cy - side_padded // 2)
        x2 = min(frame.shape[1], x1 + side_padded)
        y2 = min(frame.shape[0], y1 + side_padded)

        crop = frame[y1:y2, x1:x2]
        side_final = max(128, min(crop.shape[0], crop.shape[1]))
        crop_square = cv2.resize(crop, (side_final, side_final), interpolation=cv2.INTER_AREA)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S%f")[:-3]
        fpath = os.path.join(save_dir, f"{filename_prefix}_{ts}.jpg")

        try:
            if not cv2.imwrite(fpath, crop_square):
                return False, "Failed to write image."
        except Exception as e:
            return False, f"Save error: {e}"

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

