"""Student-facing check-in state, independent of Tk and physical devices."""

from dataclasses import dataclass
import time


@dataclass(frozen=True)
class KioskScreen:
    state: str
    title: str
    instruction: str
    step: int = 0
    detail: str = ""


SCREENS = {
    "setup": KioskScreen("setup", "Check-in is not ready", "Please ask a staff member to complete setup."),
    "paused": KioskScreen("paused", "Check-in is paused", "Please see a staff member for help."),
    "opening": KioskScreen("opening", "Getting the camera ready", "Please wait a moment."),
    "ready": KioskScreen("ready", "Look at the camera", "Stand inside the outline, with one person in view.", 1),
    "checking": KioskScreen("checking", "Hold still for a moment", "Wait for confirmation before you leave.", 2),
    "unknown": KioskScreen("unknown", "We couldn't recognize you", "Face the camera and try again, or ask a staff member.", 1, "Attendance has not been recorded."),
    "multiple": KioskScreen("multiple", "One person at a time", "Please let the person ahead finish checking in.", 1),
    "unavailable": KioskScreen("unavailable", "Check-in is unavailable", "Please see a staff member. The camera needs attention.", detail="Attendance has not been recorded."),
    "save_error": KioskScreen("save_error", "We couldn't save attendance", "Please see a staff member to record your attendance.", detail="Attendance has not been recorded."),
    "depart": KioskScreen("depart", "Please step aside", "Move completely out of the camera view.", 3),
}


class KioskFlow:
    def __init__(self, controller, show, ready, *, clock=time.monotonic):
        self.controller, self.show, self.ready = controller, show, ready
        self.clock = clock
        self.requested = True
        self.in_staff = False
        self.last_capture = None
        self.last_frame = None
        self.started = clock()
        self.hold_until = None
        self.clear_since = None
        self.departure_confirmed = False
        self.screen = None
        self._set("setup")

    def _set(self, state):
        screen = SCREENS[state] if isinstance(state, str) else state
        if screen != self.screen:
            self.screen = screen
            self.show(screen)

    def suspend(self, state="paused"):
        self.requested = False
        self._reset_confirmation()
        self.controller.pause_attendance()
        self._set(state)

    def resume(self):
        self.requested = True
        self._reset_confirmation()
        self.last_capture = self.last_frame = None
        self.started = self.clock()
        self.controller.pause_attendance()
        self._set("opening" if self.ready() else "setup")

    def _reset_confirmation(self):
        self.hold_until = self.clear_since = None
        self.departure_confirmed = False

    def _observe_departure(self, no_face, captured):
        # Watch while confirmation is visible, and remember a completed exit
        # even if the next student arrives before the message finishes.
        if self.departure_confirmed:
            return
        if not no_face:
            self.clear_since = None
        elif self.clear_since is None:
            self.clear_since = captured
        elif captured - self.clear_since >= 0.6:
            self.departure_confirmed = True

    def receive(self, update):
        result = update.get("identity")
        camera = self.controller.camera_service
        now = self.clock()
        if result is None:
            if self.last_capture is not None or getattr(camera, "camera_error", None):
                self.suspend("unavailable")
            return
        captured = update.get("captured_monotonic")
        frame_id = update.get("frame_id")
        if captured is None or frame_id is None or not 0 <= now - captured <= self.controller.config.identity_max_age_seconds:
            self.controller._identity_tracker.reset()
            self.clear_since = None
            return
        if frame_id == self.last_frame:
            return
        if self.last_capture is not None and captured - self.last_capture > self.controller.config.identity_max_age_seconds:
            self.clear_since = None
        self.last_frame = frame_id
        self.last_capture = captured
        if self.in_staff or not self.requested:
            return
        if not self.ready():
            self.controller.pause_attendance()
            self._set("setup")
            return
        if not getattr(camera, "running", False):
            self.suspend("unavailable")
            return
        no_face = getattr(result, "reason", "") == "no_face"
        if self.hold_until is not None:
            self.controller._identity_tracker.reset()
            self._observe_departure(no_face, captured)
            if now < self.hold_until:
                return
            if not self.departure_confirmed:
                self._set("depart")
                return
            self._reset_confirmation()
        if not self.controller.attendance_active:
            if not self.controller.start_attendance():
                self._set("setup")
                return
        if no_face:
            self._set("ready")
        elif getattr(result, "reason", "") == "multiple_faces":
            self._set("multiple")
        elif result.status == "recognized":
            self._set("checking")
        else:
            self._set("unknown")
        attendance = self.controller.handle_identity_update(update)
        if attendance is not None:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            stamp = datetime.fromisoformat(attendance.occurred_at_utc.replace("Z", "+00:00"))
            local_time = stamp.astimezone(ZoneInfo(attendance.timezone_name)).strftime("%I:%M %p")
            first_name = (result.display_name or "").split(" ")[0][:30]
            title = ("You're checked in" + (f", {first_name}" if first_name else "")) if attendance.status == "recorded" else "You're already checked in today"
            self._set(KioskScreen("recorded", title, "You can step aside for the next student.", 3, f"Attendance saved at {local_time}"))
            self._reset_confirmation()
            self.hold_until = now + 3.0
            self.controller._identity_tracker.reset()
        elif not self.controller.attendance_active:
            self.suspend("save_error")

    def tick(self):
        now = self.clock()
        if self.in_staff or not self.requested:
            return
        if not self.ready():
            self.controller.pause_attendance()
            self._set("setup")
        elif getattr(self.controller.camera_service, "camera_error", None):
            self.suspend("unavailable")
        elif self.last_capture is not None and now - self.last_capture > self.controller.config.identity_max_age_seconds:
            self.suspend("unavailable")
        elif self.last_capture is None:
            if now - self.started > 10:
                self.suspend("unavailable")
            else:
                self._set("opening")
        elif self.hold_until is not None and now >= self.hold_until:
            if self.departure_confirmed:
                self._reset_confirmation()
                self._set("ready")
            else:
                self._set("depart")
