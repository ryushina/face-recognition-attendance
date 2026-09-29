"""Camera lifecycle tests using fake capture devices and a fake OpenCV module."""

import importlib
import os
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from config import AppConfig


class FakeFrame:
    def __init__(self, width=640, height=480, *, brightness=128, blur_score=200):
        self.shape = (height, width, 3)
        self.brightness = brightness
        self.blur_score = blur_score

    def copy(self):
        return FakeFrame(
            self.shape[1], self.shape[0],
            brightness=self.brightness, blur_score=self.blur_score
        )

    def __getitem__(self, slices):
        y_slice, x_slice = slices
        return FakeFrame(
            x_slice.stop - x_slice.start,
            y_slice.stop - y_slice.start,
            brightness=self.brightness,
            blur_score=self.blur_score,
        )


class FakeGrayImage:
    def __init__(self, image):
        self.image = image
        self.blur_score = image.blur_score

    def mean(self):
        return self.image.brightness


class FakeLaplacian:
    def __init__(self, image):
        self.image = image

    def var(self):
        return self.image.blur_score


class FakeCapture:
    def __init__(self, *, opened=True, read_result=(False, None), block_read=False):
        self.opened = opened
        self.read_result = read_result
        self.block_read = block_read
        self.read_started = threading.Event()
        self.allow_read = threading.Event()
        self.read_active = threading.Event()
        self.release_count = 0
        self.released_during_read = False

    def isOpened(self):
        return self.opened

    def read(self):
        self.read_active.set()
        self.read_started.set()
        try:
            if self.block_read and not self.allow_read.wait(timeout=5):
                raise RuntimeError("test read timed out")
            if isinstance(self.read_result, Exception):
                raise self.read_result
            return self.read_result
        finally:
            self.read_active.clear()

    def release(self):
        self.released_during_read = self.released_during_read or self.read_active.is_set()
        self.release_count += 1
        self.opened = False


class CameraHarness:
    def __init__(
        self, testcase, captures, *, capture_error=None,
        write_result=True, write_error=None
    ):
        self.testcase = testcase
        self.temporary_directory = tempfile.TemporaryDirectory()
        testcase.addCleanup(self.temporary_directory.cleanup)
        root = Path(self.temporary_directory.name)
        self.devices = list(captures)
        self.opened_indices = []
        self.capture_error = capture_error
        self.write_result = write_result
        self.write_error = write_error
        self.written_images = []

        cascade_dir = root / "cascades"
        cascade_dir.mkdir()
        (cascade_dir / "haarcascade_frontalface_default.xml").touch()

        fake_cv2 = types.ModuleType("cv2")
        fake_cv2.data = types.SimpleNamespace(haarcascades=str(cascade_dir) + os.sep)
        fake_cv2.COLOR_BGR2GRAY = 6
        fake_cv2.CV_64F = 6
        fake_cv2.VideoCapture = self.open_camera
        fake_cv2.cvtColor = lambda image, code: FakeGrayImage(image)
        fake_cv2.Laplacian = lambda image, depth: FakeLaplacian(image)
        fake_cv2.imwrite = self.write_image
        fake_cv2.rectangle = lambda *args, **kwargs: None
        fake_cv2.CascadeClassifier = lambda path: types.SimpleNamespace(
            empty=lambda: False
        )
        self.fake_cv2 = fake_cv2

    def write_image(self, path, image):
        self.written_images.append((path, image))
        if self.write_error is not None:
            raise self.write_error
        return self.write_result

    def open_camera(self, index):
        self.opened_indices.append(index)
        if self.capture_error is not None:
            raise self.capture_error
        if not self.devices:
            raise AssertionError("Unexpected camera open")
        return self.devices.pop(0)

    def make_service(
        self, *, stop_timeout=0.5, config_values=None, recognition_service=None
    ):
        previous = sys.modules.pop("camera_service", None)
        try:
            with patch.dict(
                sys.modules, {"cv2": self.fake_cv2, "ultralytics": None}
            ):
                module = importlib.import_module("camera_service")
                settings = {"ATTENDANCE_CAMERA_INDEX": "2"}
                settings.update(config_values or {})
                config = AppConfig.from_environment(settings)
                return module.CameraService(
                    detector="haar", config=config,
                    stop_timeout_seconds=stop_timeout,
                    recognition_service=recognition_service,
                )
        finally:
            sys.modules.pop("camera_service", None)
            if previous is not None:
                sys.modules["camera_service"] = previous


class CameraLifecycleTests(unittest.TestCase):
    def wait_for_worker(self, service, worker):
        self.assertIsNotNone(worker)
        worker.join(timeout=2)
        self.assertFalse(worker.is_alive(), "camera worker did not exit")

    def cache_capture_frame(
        self, service, *, frame=None, boxes=None, frame_id=1, age_seconds=0.0
    ):
        frame = FakeFrame() if frame is None else frame
        boxes = [(100, 80, 100, 120)] if boxes is None else boxes
        with service._last_frame_lock:
            service._last_frame_bgr = frame
            service._last_boxes = list(boxes)
            service._last_frame_id = frame_id
            service._last_frame_captured_monotonic = time.monotonic() - age_seconds
            service.is_face_detected = bool(boxes)

    def test_open_failure_reports_error_and_releases_device(self):
        device = FakeCapture(opened=False)
        harness = CameraHarness(self, [device])
        service = harness.make_service()

        with patch("builtins.print"):
            started = service.start()

        self.assertFalse(started)
        self.assertFalse(service.running)
        self.assertIsNone(service.thread)
        self.assertIsNone(service.cap)
        self.assertIn("camera index 2", service.camera_error)
        self.assertEqual(harness.opened_indices, [2])
        self.assertEqual(device.release_count, 1)

    def test_video_capture_exception_is_reported_without_starting_worker(self):
        harness = CameraHarness(self, [], capture_error=RuntimeError("device busy"))
        service = harness.make_service()

        with patch("builtins.print"):
            started = service.start()

        self.assertFalse(started)
        self.assertIsNone(service.thread)
        self.assertIsNone(service.cap)
        self.assertIn("device busy", service.camera_error)

    def test_failed_frame_read_clears_state_releases_device_and_allows_restart(self):
        first = FakeCapture()
        second = FakeCapture()
        harness = CameraHarness(self, [first, second])
        service = harness.make_service()

        self.assertTrue(service.start())
        first_worker = service.thread
        self.wait_for_worker(service, first_worker)

        self.assertFalse(service.running)
        self.assertIsNone(service.cap)
        self.assertIsNone(service._last_frame_bgr)
        self.assertEqual(service._last_boxes, [])
        self.assertFalse(service.is_face_detected)
        self.assertIn("returned no frame", service.camera_error)
        self.assertEqual(first.release_count, 1)

        self.assertTrue(service.start())
        second_worker = service.thread
        self.assertIsNot(first_worker, second_worker)
        self.wait_for_worker(service, second_worker)
        self.assertEqual(harness.opened_indices, [2, 2])
        self.assertEqual(second.release_count, 1)

    def test_read_exception_stops_worker_and_clears_cached_face(self):
        device = FakeCapture(read_result=RuntimeError("USB disconnected"))
        harness = CameraHarness(self, [device])
        service = harness.make_service()

        with service._last_frame_lock:
            service._last_frame_bgr = FakeFrame()
            service._last_boxes = [(1, 2, 3, 4)]
            service.is_face_detected = True

        self.assertTrue(service.start())
        worker = service.thread
        self.wait_for_worker(service, worker)

        self.assertFalse(service.running)
        self.assertFalse(service.is_face_detected)
        self.assertIsNone(service._last_frame_bgr)
        self.assertIn("USB disconnected", service.camera_error)
        self.assertEqual(device.release_count, 1)

    def test_detection_exception_stops_worker_and_releases_capture(self):
        device = FakeCapture(read_result=(True, FakeFrame()))
        harness = CameraHarness(self, [device])
        service = harness.make_service()

        def fail_detection(frame):
            raise RuntimeError("inference failed")

        service._detect_faces = fail_detection
        self.assertTrue(service.start())
        worker = service.thread
        self.wait_for_worker(service, worker)

        self.assertFalse(service.running)
        self.assertFalse(service.is_face_detected)
        self.assertIsNone(service._last_frame_bgr)
        self.assertIn("inference failed", service.camera_error)
        self.assertEqual(device.release_count, 1)

    def test_stop_waits_for_read_without_releasing_device_or_spawning_second_worker(self):
        blocked = FakeCapture(
            read_result=(True, FakeFrame()), block_read=True
        )
        next_device = FakeCapture()
        harness = CameraHarness(self, [blocked, next_device])
        service = harness.make_service(stop_timeout=0.05)
        self.assertTrue(service.start())
        worker = service.thread
        self.assertTrue(blocked.read_started.wait(timeout=1))

        with service._last_frame_lock:
            service._last_frame_bgr = FakeFrame()
            service._last_boxes = [(1, 2, 3, 4)]
            service.is_face_detected = True

        start_time = time.monotonic()
        with patch("builtins.print"):
            stopped = service.stop()
        elapsed = time.monotonic() - start_time

        self.assertFalse(stopped)
        self.assertLess(elapsed, 0.5)
        self.assertFalse(service.running)
        self.assertFalse(service.is_face_detected)
        self.assertIsNone(service._last_frame_bgr)
        self.assertFalse(blocked.released_during_read)
        self.assertEqual(blocked.release_count, 0)
        self.assertIn("shutdown timeout", service.camera_error)

        with patch("builtins.print"):
            self.assertFalse(service.start())
        self.assertEqual(harness.opened_indices, [2])
        self.assertIs(service.thread, worker)

        blocked.allow_read.set()
        self.wait_for_worker(service, worker)
        self.assertEqual(blocked.release_count, 1)
        self.assertFalse(blocked.released_during_read)
        self.assertFalse(service.is_face_detected)

        self.assertTrue(service.start())
        new_worker = service.thread
        self.wait_for_worker(service, new_worker)
        self.assertEqual(harness.opened_indices, [2, 2])
        self.assertEqual(next_device.release_count, 1)

    def test_capture_after_stop_does_not_save_or_create_directory(self):
        device = FakeCapture()
        harness = CameraHarness(self, [device])
        service = harness.make_service()
        service._clear_frame_state()
        save_dir = Path(harness.temporary_directory.name) / "no-capture"

        saved, message = service.capture_face(save_dir)

        self.assertFalse(saved)
        self.assertIn("No frame available", message)
        self.assertFalse(save_dir.exists())

    def test_ui_update_slot_keeps_only_latest_frame_and_pending_status(self):
        harness = CameraHarness(self, [])
        service = harness.make_service()
        first_frame = object()
        latest_frame = object()

        service._publish_ui_update(status="Camera running.")
        service._publish_ui_update(frame=first_frame)
        service._publish_ui_update(frame=latest_frame)

        self.assertEqual(
            service.take_latest_ui_update(),
            {"frame": latest_frame, "status": "Camera running."},
        )
        self.assertIsNone(service.take_latest_ui_update())

    def test_recognition_worker_publishes_identity_with_capture_frame_metadata(self):
        from recognition_service import MatchResult

        class BlockingAfterFrame:
            def __init__(self):
                self.read_count = 0
                self.next_read_started = threading.Event()
                self.allow_exit = threading.Event()
                self.released = False

            def isOpened(self):
                return True

            def read(self):
                self.read_count += 1
                if self.read_count == 1:
                    return True, FakeFrame()
                self.next_read_started.set()
                self.allow_exit.wait(2)
                return False, None

            def release(self):
                self.released = True

        class Detection:
            box = (100, 80, 100, 120)

        class Recognition:
            def __init__(self):
                self.detect_calls = 0

            def detect(self, frame):
                self.detect_calls += 1
                return (Detection(),)

            def extract(self, frame, detection):
                return object()

            def match(self, embedding):
                return MatchResult("recognized", "0007", "Lin Tan", 0.9, 0.1)

        device = BlockingAfterFrame()
        harness = CameraHarness(self, [device])
        recognition = Recognition()
        service = harness.make_service(recognition_service=recognition)
        self.assertIn("YuNet + SFace", service.detector_status)
        self.assertTrue(service.start())
        self.assertTrue(device.next_read_started.wait(1))
        update = service.take_latest_ui_update()
        self.assertEqual(update["identity"].student_id, "0007")
        self.assertEqual(update["frame_id"], 1)
        self.assertGreater(update["captured_monotonic"], 0)
        self.assertEqual(recognition.detect_calls, 1)
        device.allow_exit.set()
        self.wait_for_worker(service, service.thread)

    def test_capture_requires_a_fresh_single_face_of_sufficient_size(self):
        invalid_cases = (
            {
                "name": "stale frame",
                "age_seconds": 5,
                "expected": "stale",
            },
            {"name": "no face", "boxes": [], "expected": "No face detected"},
            {
                "name": "multiple faces",
                "boxes": [(100, 80, 100, 120), (300, 80, 100, 120)],
                "expected": "More than one face",
            },
            {
                "name": "small face",
                "boxes": [(100, 80, 60, 70)],
                "expected": "too small",
            },
            {
                "name": "out-of-bounds face",
                "boxes": [(600, 80, 100, 120)],
                "expected": "clipped by the frame edge",
            },
            {
                "name": "face lacks padding at edge",
                "boxes": [(5, 80, 100, 120)],
                "expected": "too close to the frame edge",
            },
            {
                "name": "blurry face",
                "frame": FakeFrame(blur_score=10),
                "expected": "blurry",
            },
            {
                "name": "dark face",
                "frame": FakeFrame(brightness=20),
                "expected": "too dark",
            },
            {
                "name": "bright face",
                "frame": FakeFrame(brightness=250),
                "expected": "too bright",
            },
        )

        for case in invalid_cases:
            with self.subTest(case=case["name"]):
                harness = CameraHarness(self, [])
                service = harness.make_service()
                self.cache_capture_frame(
                    service,
                    frame=case.get("frame"),
                    boxes=case.get("boxes"),
                    age_seconds=case.get("age_seconds", 0),
                )
                save_dir = Path(harness.temporary_directory.name) / "rejected"

                saved, message = service.capture_face(save_dir)

                self.assertFalse(saved)
                self.assertIn(case["expected"], message)
                self.assertEqual(harness.written_images, [])
                self.assertFalse(save_dir.exists())
                self.assertIsNone(service.last_captured_frame_id)

    def test_capture_saves_unstretched_padded_crop_with_frame_id(self):
        harness = CameraHarness(self, [])
        service = harness.make_service()
        self.cache_capture_frame(service, frame_id=42)
        save_dir = Path(harness.temporary_directory.name) / "accepted"

        saved, path = service.capture_face(save_dir)

        self.assertTrue(saved, path)
        self.assertIn("_f42_", Path(path).name)
        self.assertEqual(service.last_captured_frame_id, 42)
        self.assertEqual(len(harness.written_images), 1)
        written_path, crop = harness.written_images[0]
        self.assertEqual(written_path, path)
        # 25% margin around the original 100x120 box yields 150x180 pixels.
        self.assertEqual(crop.shape, (180, 150, 3))
        self.assertTrue(save_dir.is_dir())

    def test_write_failure_does_not_mark_a_frame_as_captured(self):
        for failure in ("false", "exception"):
            with self.subTest(failure=failure):
                harness = CameraHarness(
                    self,
                    [],
                    write_result=False if failure == "false" else True,
                    write_error=(
                        OSError("disk unavailable") if failure == "exception" else None
                    ),
                )
                service = harness.make_service()
                self.cache_capture_frame(service, frame_id=7)
                save_dir = Path(harness.temporary_directory.name) / "write-failure"

                saved, message = service.capture_face(save_dir)

                self.assertFalse(saved)
                self.assertIn("write" if failure == "false" else "disk unavailable", message)
                self.assertIsNone(service.last_captured_frame_id)
                self.assertEqual(len(harness.written_images), 1)

    def test_capture_uses_acquisition_time_and_increasing_frame_ids(self):
        class StopAfterTwoFrames:
            def __init__(self):
                self.service = None
                self.read_count = 0
                self.observed_frame_id = None
                self.observed_captured_at = None
                self.release_count = 0

            def isOpened(self):
                return True

            def read(self):
                self.read_count += 1
                if self.read_count <= 2:
                    return True, FakeFrame()
                self.observed_frame_id = self.service._last_frame_id
                self.observed_captured_at = (
                    self.service._last_frame_captured_monotonic
                )
                self.service._stop_event.set()
                return False, None

            def release(self):
                self.release_count += 1

        device = StopAfterTwoFrames()
        harness = CameraHarness(self, [device])
        service = harness.make_service()
        device.service = service
        inference_started = []

        def detect(_frame):
            inference_started.append(time.monotonic())
            return [(100, 80, 100, 120)]

        service._detect_faces = detect
        self.assertTrue(service.start())
        worker = service.thread
        self.wait_for_worker(service, worker)

        self.assertEqual(device.observed_frame_id, 2)
        self.assertIsNotNone(device.observed_captured_at)
        self.assertEqual(len(inference_started), 2)
        self.assertLessEqual(device.observed_captured_at, inference_started[-1])
        self.assertEqual(device.release_count, 1)


if __name__ == "__main__":
    unittest.main()
