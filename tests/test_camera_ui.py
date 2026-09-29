"""Tk update-poller tests with a fake scheduler and view callbacks."""

import threading
import unittest

from camera_ui import TkCameraUpdatePoller


class FakeRoot:
    def __init__(self):
        self.callbacks = {}
        self.cancelled = set()
        self.next_id = 0
        self.after_calls = []
        self.cancel_calls = []

    def after(self, interval_ms, callback):
        self.next_id += 1
        callback_id = f"after-{self.next_id}"
        self.callbacks[callback_id] = callback
        self.after_calls.append((interval_ms, callback_id))
        return callback_id

    def after_cancel(self, callback_id):
        self.cancel_calls.append(callback_id)
        self.cancelled.add(callback_id)

    def run(self, callback_id, *, even_if_cancelled=False):
        callback = self.callbacks.pop(callback_id)
        if even_if_cancelled or callback_id not in self.cancelled:
            callback()


class FakeCameraService:
    def __init__(self):
        self.update = None

    def take_latest_ui_update(self):
        update = self.update
        self.update = None
        return update


class CameraUiPollerTests(unittest.TestCase):
    def test_delivers_latest_frame_and_status_from_one_tk_timer(self):
        root = FakeRoot()
        camera = FakeCameraService()
        callback_threads = []
        frames = []
        statuses = []
        identities = []

        def on_frame(frame):
            callback_threads.append(threading.get_ident())
            frames.append(frame)

        def on_status(status):
            callback_threads.append(threading.get_ident())
            statuses.append(status)

        poller = TkCameraUpdatePoller(
            root, camera, on_frame, on_status,
            interval_ms=40, on_identity=identities.append,
        )
        self.assertTrue(poller.start())
        self.assertTrue(poller.start())
        self.assertEqual(len(root.after_calls), 1)
        self.assertEqual(root.after_calls[0][0], 40)

        latest_frame = object()
        identity_update = {"identity": object(), "frame_id": 42, "captured_monotonic": 2.5}
        camera.update = {"frame": latest_frame, "status": "Camera running.", **identity_update}
        first_timer = root.after_calls[0][1]
        root.run(first_timer)

        self.assertEqual(frames, [latest_frame])
        self.assertEqual(statuses, ["Camera running."])
        self.assertEqual(identities, [{"frame": latest_frame, "status": "Camera running.", **identity_update}])
        self.assertEqual(callback_threads, [threading.get_ident()] * 2)
        self.assertEqual(len(root.after_calls), 2)

    def test_close_cancels_timer_and_late_callback_cannot_touch_view(self):
        root = FakeRoot()
        camera = FakeCameraService()
        destroyed = False
        calls = []

        def on_frame(frame):
            if destroyed:
                raise AssertionError("frame callback touched a destroyed view")
            calls.append(("frame", frame))

        def on_status(status):
            if destroyed:
                raise AssertionError("status callback touched a destroyed view")
            calls.append(("status", status))

        poller = TkCameraUpdatePoller(root, camera, on_frame, on_status)
        poller.start()
        pending_id = root.after_calls[0][1]
        pending_callback = root.callbacks[pending_id]
        poller.close()
        destroyed = True

        self.assertEqual(root.cancel_calls, [pending_id])
        pending_callback()
        self.assertEqual(calls, [])
        self.assertFalse(poller.start())
        self.assertEqual(len(root.after_calls), 1)

    def test_close_tolerates_a_root_already_destroying(self):
        class DestroyingRoot(FakeRoot):
            def after_cancel(self, callback_id):
                raise RuntimeError("Tcl interpreter is being destroyed")

        root = DestroyingRoot()
        poller = TkCameraUpdatePoller(
            root, FakeCameraService(), lambda frame: None, lambda status: None
        )
        poller.start()
        poller.close()
        poller.close()

        self.assertFalse(poller.start())

    def test_rejects_invalid_poll_interval(self):
        for interval in (0, -1, 1.5, True):
            with self.subTest(interval=interval):
                with self.assertRaises(ValueError):
                    TkCameraUpdatePoller(
                        FakeRoot(), FakeCameraService(), lambda _: None,
                        lambda _: None, interval_ms=interval
                    )


if __name__ == "__main__":
    unittest.main()
