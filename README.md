# Face Recognition Attendance

A local Python desktop application for face enrollment, recognition, and attendance. It keeps student records, face samples, recognition embeddings, and daily attendance in a local SQLite database. See [PLAN.md](PLAN.md) for implementation status and validation limits.

## Development target

The development target is 64-bit CPython 3.12 on Windows. The pinned dependencies and model API checks pass. The guided Tk kiosk has programmatic layout and workflow checks; physical-camera operation, visual inspection, and real recognition accuracy remain unverified. A Raspberry Pi installation is future work; see task T26 in the plan.

## Set up on Windows

Open PowerShell in the repository directory and run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

The packages used by the desktop app are pinned in `requirements.txt`. The `tzdata` package supplies IANA timezone rules on Windows. It installs to the project virtual environment and does not change system Python. Raspberry Pi package compatibility is still unverified.

After installing packages, provision the selected OpenCV face models once:

```powershell
python scripts/download_models.py
```

The setup script downloads pinned OpenCV Zoo artifacts and verifies their SHA-256 checksums. The application does not download models when it runs. See [the recognition decision](docs/recognition-decision.md) for sources, versions, preprocessing, and known model-license questions.

## Start the application

With the virtual environment active, run:

```powershell
python main.py
```

The app opens on the student check-in screen. Camera index `0` is the initial default; saved setup or a launch override can select another camera. By default the app starts the camera automatically. Students see setup guidance until staff complete the following steps.

### First run: staff setup

1. Choose **Staff access** and create a password of at least 10 characters. Staff should provision this before making the kiosk available to students. There is no default password.
2. In **Setup**, choose the camera number and the school's timezone. Confirm the displayed school date/time and the once-per-day attendance rule. Choose **Save setup and test camera**.
3. Choose **Enroll student**. Complete **Student details -> Face photos -> Review and save**. Capture at least three accepted photos; the capture button enables when a fresh single-face frame is available. A failed capture explains what to change.
4. After saving, wait for **Ready for check-in**, then choose **Test recognition**. Have the student face the camera again and confirm the correct name appears in the staff-only live check. Prepared enrollment means the stored samples are usable; it does not prove live recognition accuracy. If preparation fails, retry it or open **Diagnostics**.
5. Choose **Lock and open student kiosk**. Students look at the camera, hold still, and wait for the saved-attendance confirmation. They do not need to press a start button.

The kiosk clears the student's name after three seconds and rearms after the camera has seen no face for at least 0.6 seconds. It watches for departure during the confirmation, so a student can step away immediately after seeing success. If a face is still visible, **Please step aside** asks them to move completely out of the camera view. Unknown people, multiple faces, stale frames, and failed writes never show attendance success. A returning student sees **You're already checked in today**.

Staff can reopen **Staff access** for setup, **Students** (edit details and inspect or replace saved face photos), enrollment, history/CSV export, camera recovery, or diagnostics. Photo quality review checks face detection, face size, sharpness, brightness, and current model processing; follow it with **Test live recognition**. **Lock and keep paused** prevents check-ins. Staff sessions lock after five minutes of inactivity and close private windows. Explicitly leaving with unsaved edits or enrollment photos asks staff before discarding them. See [the operator guide](docs/kiosk-user-guide.md).

Existing installs need this staff setup once. Afterward, launch the app normally and it enables check-in when configuration, enrollment, and fresh camera frames are ready. A camera or saving failure pauses attendance until staff check the cause and reopen the kiosk.

## Configuration

The staff Setup screen saves camera/timezone preferences in `kiosk-settings.json` under the selected data directory. Explicit environment variables override saved values; remove a conflicting override before changing it in the app. Relative paths resolve from the application directory, never the shell's current directory.

| Variable | Default | Meaning |
| --- | --- | --- |
| `ATTENDANCE_DATA_DIR` | `data/` in the application directory | Writable directory for the SQLite database, enrollment captures, and logs. |
| `ATTENDANCE_MODEL_PATH` | `yolov8n-face-lindevs.pt` in the application directory | Legacy optional YOLO face detector weights. |
| `ATTENDANCE_CAMERA_INDEX` | `0` | OpenCV camera index; must be a non-negative integer. |
| `ATTENDANCE_CAMERA_AUTOSTART` | `true` | Open the selected camera when the app starts; set to `false` to review the app without starting capture. |
| `ATTENDANCE_DETECTOR` | `yolo` | Legacy standalone detector selection. The kiosk uses YuNet + SFace. |
| `ATTENDANCE_YOLO_CONFIDENCE` | `0.40` | YOLO detection confidence, greater than zero and at most one. |
| `ATTENDANCE_FRAME_INTERVAL_SECONDS` | `0.03` | Delay between processed camera frames, greater than zero. |
| `ATTENDANCE_CAPTURE_MAX_AGE_SECONDS` | `1.0` | Maximum age of a camera frame when an enrollment photo is requested. |
| `ATTENDANCE_CAPTURE_MIN_FACE_SIZE_PIXELS` | `80` | Minimum width and height of the detected face in the original camera frame. |
| `ATTENDANCE_CAPTURE_MIN_BLUR_SCORE` | `50.0` | Minimum variance-of-Laplacian score measured on the original face pixels. |
| `ATTENDANCE_CAPTURE_BRIGHTNESS_MIN` | `40.0` | Minimum mean grayscale brightness of the detected face, from 0 to 255. |
| `ATTENDANCE_CAPTURE_BRIGHTNESS_MAX` | `220.0` | Maximum mean grayscale brightness of the detected face, from 0 to 255. |
| `ATTENDANCE_TIMEZONE` | saved staff setting, otherwise unset | School IANA timezone override; for example, `Asia/Manila`. Staff must still confirm setup. |
| `ATTENDANCE_MINIMUM_SIMILARITY` | `0.50` | Provisional recognition similarity threshold; not a probability or calibrated accuracy measure. |
| `ATTENDANCE_MINIMUM_MARGIN` | `0.08` | Provisional minimum separation from the next student's score. |

For example, in PowerShell, set `$env:ATTENDANCE_CAMERA_INDEX = "1"` before launching to select camera index 1. Set `$env:ATTENDANCE_DATA_DIR` to an absolute path to keep writable data elsewhere. The data directory is created when the application starts; merely importing the configuration does not create directories or open a camera.

Enrollment freshness and image-quality defaults are provisional starting values, not calibrated thresholds. Captures retain the original pixels and a padded face crop; the app does not enlarge a small face to make it appear higher quality.

## Local data and Git

The application stores student records, samples, embeddings, and attendance in `attendance.sqlite3` under `data/` by default. Enrollment captures go under `data/assets/enrollment_sessions/` in per-enrollment UUID folders. Bounded diagnostic logs go to `data/application.log` with three rotated files. These locations follow `ATTENDANCE_DATA_DIR` when configured. Recognition preparation runs in the background. `staff-access.json` contains a salted password hash and retry-limit state, never the plain password. Access control protects the app's staff tools; administrators with OS file access remain trusted.

Create a portable backup with `python scripts/backup_data.py backup --source-dir data --destination backups/pilot-2026-09-29`. Restore it first into a new directory with `python scripts/backup_data.py restore --backup-dir backups/pilot-2026-09-29 --destination data-restored`; restore refuses to replace any existing directory. Backups include a consistent SQLite snapshot, referenced sample images, checksums, and model/configuration metadata. Model weights remain restorable from their pinned checksummed sources.

A restore does not copy the staff credential or arm the kiosk. Complete staff access and camera/timezone setup for the restored installation. Password recovery and device lockdown remain administrator procedures; the app does not offer a student-accessible password reset.

## Developer verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe scripts/check_kiosk_ui.py
```

The first command runs headless checks and skips five opt-in Tk tests. The second runs those five in separate processes with temporary databases, synthetic images, and camera autostart disabled. It opens test windows but never opens a physical camera. It checks bounds at 800x480/1100x650, staff locking, private recognition diagnostics, and synthetic enrollment-to-attendance. These checks do not replace the [manual validation checklist](docs/desktop-validation.md).

Several legacy files are already tracked by Git. Ignore rules do not untrack existing files or remove them from repository history. Existing root-level `users.txt` and `log.txt` remain untouched; new application logs and writes go to the configured data directory. T09 covers an explicit, reviewed import of legacy user records. Existing log entries come from placeholder code and must not be treated as verified attendance. Keep face photos, databases, exports, and backups out of Git.

## Previewing legacy users

The root `users.txt` is legacy CSV input. Preview it without changing the database:

```powershell
python scripts/import_legacy.py --dry-run
```

The command defaults to a dry run even if `--dry-run` is omitted. It reports malformed rows, duplicate IDs, existing SQLite records, and missing or empty photo folders. It does not read `log.txt`, create the database, or modify source records. Relative photo folders are resolved from the legacy CSV's directory.

After reviewing the preview and choosing to import those records, run:

```powershell
python scripts/import_legacy.py --apply
```

This explicit command writes eligible students to the configured SQLite database. Imported students remain pending enrollment; missing or unusable photos do not make a student ready for recognition. Repeating the command reports existing IDs and skips them. Use `--source`, `--photo-root`, or `--database` to select fixture or alternate paths. Legacy attendance in `log.txt` is never imported or treated as verified.

## Raspberry Pi

Pi hardware, operating system, package compatibility, recognition performance, and camera support have not been tested. Follow the Raspberry Pi tasks in `PLAN.md` after choosing the Pi model, camera, and display. Do not treat the Windows dependency pins as a verified Raspberry Pi setup.
