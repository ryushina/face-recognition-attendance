import json
import tempfile
import unittest
from pathlib import Path

from config import AppConfig
from kiosk_settings import StaffAccess, StaffAccessError, save_preferences


class KioskSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.now = [100.0]
        self.access = StaffAccess(self.path, clock=lambda: self.now[0], wall_clock=lambda: self.now[0])

    def test_password_is_hashed_setup_is_exclusive_and_session_expires(self):
        self.access.create("example password")
        self.assertNotIn("example password", self.access.path.read_text())
        with self.assertRaises(StaffAccessError):
            self.access.create("another password")
        self.assertTrue(self.access.unlocked)
        self.now[0] += 301
        with self.assertRaises(StaffAccessError):
            self.access.require()
        self.access.sign_in("example password")
        self.assertTrue(self.access.unlocked)
        self.now[0] += 250
        self.access.touch()
        self.now[0] += 100
        self.assertTrue(self.access.unlocked)
        self.access.lock()
        self.assertFalse(self.access.unlocked)

    def test_failed_attempt_limit_survives_reopening(self):
        self.access.create("example password")
        self.access.lock()
        for _ in range(5):
            with self.assertRaises(StaffAccessError):
                self.access.sign_in("wrong password")
        reopened = StaffAccess(self.path, clock=lambda: self.now[0], wall_clock=lambda: self.now[0])
        with self.assertRaisesRegex(StaffAccessError, "Wait 30"):
            reopened.sign_in("example password")
        self.now[0] += 31
        reopened.sign_in("example password")
        self.assertTrue(reopened.unlocked)

    def test_corrupt_credentials_fail_closed(self):
        self.access.path.write_text("broken")
        self.assertTrue(self.access.configured)
        with self.assertRaises(StaffAccessError):
            self.access.sign_in("password")
        with self.assertRaises(StaffAccessError):
            self.access.create("replacement password")

    def test_settings_reload_and_explicit_environment_wins(self):
        save_preferences(self.path, "Asia/Manila", 2)
        config = AppConfig.from_environment({"ATTENDANCE_DATA_DIR": str(self.path)})
        self.assertEqual(config.attendance_timezone, "Asia/Manila")
        self.assertEqual(config.camera_index, 2)
        overridden = AppConfig.from_environment({"ATTENDANCE_DATA_DIR": str(self.path), "ATTENDANCE_CAMERA_INDEX": "0"})
        self.assertEqual(overridden.camera_index, 0)
        saved = json.loads((self.path / "kiosk-settings.json").read_text())
        self.assertTrue(saved["daily_policy_confirmed"])
        with self.assertRaises(ValueError):
            save_preferences(self.path, "invalid/timezone", 0)
        self.assertEqual(json.loads((self.path / "kiosk-settings.json").read_text()), saved)
