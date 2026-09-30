"""Run isolated Tk checks without opening the camera or using existing records."""

import os
from pathlib import Path
import subprocess
import sys


def main():
    project = Path(__file__).resolve().parents[1]
    environment = dict(os.environ, ATTENDANCE_RUN_GUI_TESTS="1")
    cases = (
        "test_every_student_state_fits_small_window_and_errors_stay_private",
        "test_staff_lock_closes_history_and_preserves_main_actions",
        "test_enrollment_steps_and_disabled_capture_without_camera",
        "test_guided_enrollment_reaches_ready_and_kiosk_records",
        "test_live_recognition_diagnostics_are_private_and_do_not_record_attendance",
    )
    for case in cases:
        result = subprocess.run(
            [sys.executable, "-m", "unittest", f"tests.test_kiosk_ui.KioskUiTests.{case}"],
            cwd=project, env=environment,
        )
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
