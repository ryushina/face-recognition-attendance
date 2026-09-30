"""Local staff access and atomic kiosk preferences; no camera or GUI imports."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class StaffAccessError(ValueError):
    pass


def read_json(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Expected settings object")
        return value
    except FileNotFoundError:
        return {}
    except (ValueError, OSError) as exc:
        raise StaffAccessError(f"Cannot read {Path(path).name}. Ask the administrator to repair it.") from exc


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + secrets.token_hex(6) + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def save_preferences(data_dir, timezone_name, camera_index):
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise ValueError("Choose a valid school timezone, such as Asia/Manila.") from exc
    if not isinstance(camera_index, int) or camera_index < 0:
        raise ValueError("Camera number must be zero or greater.")
    write_json(Path(data_dir) / "kiosk-settings.json", {
        "timezone": timezone_name, "camera_index": camera_index,
        "daily_policy_confirmed": True,
    })


class StaffAccess:
    """Protect in-app staff operations; OS file access remains an admin boundary."""

    def __init__(self, data_dir, *, clock=time.monotonic, wall_clock=time.time):
        self.path = Path(data_dir) / "staff-access.json"
        self._clock = clock
        self._wall_clock = wall_clock
        self._until = 0.0

    @property
    def configured(self):
        # An invalid existing file must never reopen first-time setup.
        return self.path.exists()

    @property
    def unlocked(self):
        return self._until > self._clock()

    def touch(self):
        if self.unlocked:
            self._until = self._clock() + 300

    def lock(self):
        self._until = 0.0

    def require(self):
        if not self.unlocked:
            raise StaffAccessError("Staff session is locked. Sign in again.")

    @staticmethod
    def _digest(password, salt):
        return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1, dklen=32).hex()

    def create(self, password):
        if self.configured:
            raise StaffAccessError("Staff access is already configured. Sign in instead.")
        if not isinstance(password, str) or not 10 <= len(password) <= 1024:
            raise StaffAccessError("Use a staff password with 10 to 1024 characters.")
        salt = secrets.token_bytes(16)
        value = {"salt": salt.hex(), "digest": self._digest(password, salt), "failures": 0, "blocked_until": 0}
        # Exclusive creation prevents a second setup window from replacing it.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("x", encoding="utf-8") as stream:
            json.dump(value, stream)
        self._until = self._clock() + 300

    def sign_in(self, password):
        if not isinstance(password, str) or len(password) > 1024:
            raise StaffAccessError("Enter your staff password.")
        value = read_json(self.path)
        try:
            if self._wall_clock() < float(value["blocked_until"]):
                raise StaffAccessError("Too many attempts. Wait 30 seconds before trying again.")
            salt = bytes.fromhex(value["salt"])
            if len(salt) != 16 or len(value["digest"]) != 64:
                raise ValueError("Invalid credential data")
            matched = hmac.compare_digest(self._digest(password, salt), value["digest"])
            failures = int(value["failures"])
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, StaffAccessError):
                raise
            raise StaffAccessError("Staff access needs administrator repair.") from exc
        if not matched:
            failures += 1
            value["failures"] = failures % 5
            value["blocked_until"] = self._wall_clock() + 30 if failures >= 5 else 0
            write_json(self.path, value)
            raise StaffAccessError("Password not recognized. Try again.")
        value.update(failures=0, blocked_until=0)
        write_json(self.path, value)
        self._until = self._clock() + 300

    def change_password(self, current_password, new_password):
        """Rotate the staff credential after verifying the current password."""
        self.require()
        if not isinstance(new_password, str) or not 10 <= len(new_password) <= 1024:
            raise StaffAccessError("Use a new staff password with 10 to 1024 characters.")
        self.sign_in(current_password)
        if new_password == current_password:
            raise StaffAccessError("Choose a different password from the current one.")
        salt = secrets.token_bytes(16)
        value = {
            "salt": salt.hex(),
            "digest": self._digest(new_password, salt),
            "failures": 0,
            "blocked_until": 0,
        }
        write_json(self.path, value)
        self._until = self._clock() + 300
