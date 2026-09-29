"""Bounded camera-update polling on the Tk event loop."""


class TkCameraUpdatePoller:
    """Poll the camera service's latest update and call UI callbacks on Tk's thread."""

    def __init__(
        self,
        root,
        camera_service,
        on_frame,
        on_status,
        interval_ms=33,
        on_identity=None,
    ):
        if isinstance(interval_ms, bool) or not isinstance(interval_ms, int) or interval_ms <= 0:
            raise ValueError("interval_ms must be a positive integer.")

        self.root = root
        self.camera_service = camera_service
        self.on_frame = on_frame
        self.on_status = on_status
        self.on_identity = on_identity
        self.interval_ms = interval_ms
        self._after_id = None
        self._closed = False

    def start(self):
        """Start periodic polling. Repeated calls do not add extra timers."""
        if self._closed:
            return False
        if self._after_id is None:
            self._schedule_next()
        return not self._closed

    def close(self):
        """Cancel the pending Tk timer and prevent any later UI delivery."""
        if self._closed:
            return

        self._closed = True
        after_id = self._after_id
        self._after_id = None
        if after_id is not None:
            try:
                self.root.after_cancel(after_id)
            except Exception:
                # The root may already be partway through Tcl destruction.
                pass

    def _schedule_next(self):
        if self._closed or self._after_id is not None:
            return
        try:
            self._after_id = self.root.after(self.interval_ms, self._poll)
        except Exception:
            # A destroyed root cannot accept another callback.
            self._closed = True

    def _poll(self):
        self._after_id = None
        if self._closed:
            return

        update = self.camera_service.take_latest_ui_update()
        if update:
            if "frame" in update:
                self.on_frame(update["frame"])
            if "status" in update:
                self.on_status(update["status"])
            if self.on_identity is not None and "identity" in update:
                self.on_identity(update)

        self._schedule_next()
