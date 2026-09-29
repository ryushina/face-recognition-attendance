# Face Recognition Attendance

A local Python desktop prototype for face detection, student photo capture, and attendance. The current code can detect faces and capture face crops; face identity matching and working attendance registration are still to be implemented. See [PLAN.md](PLAN.md) for the implementation tasks.

## Development target

The development target is 64-bit CPython 3.12 on Windows. The Python 3.12.10 source passed a syntax check. Dependency installation and imports of the full application have not yet been verified in a clean environment. Live GUI and camera operation have not been tested. A Raspberry Pi installation is future work; see task T26 in the plan.

## Set up on Windows

Open PowerShell in the repository directory and run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

The small set of packages used by the desktop app is pinned in `requirements.txt`. It installs to the project virtual environment and does not change system Python. CPython 3.12.10 on Windows installed the pins successfully. Raspberry Pi package compatibility is still unverified.

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

The current startup code selects camera index `0` and attempts to start the camera automatically. Connect and make the intended camera available before launching. Camera permission, live preview, and detector performance depend on the computer and camera; this command alone does not verify them.

## Configuration

Settings are optional environment variables. Relative paths resolve from the application directory, never the shell's current directory.

| Variable | Default | Meaning |
| --- | --- | --- |
| `ATTENDANCE_DATA_DIR` | `data/` in the application directory | Writable directory for the SQLite database, enrollment captures, and logs. |
| `ATTENDANCE_MODEL_PATH` | `yolov8n-face-lindevs.pt` in the application directory | Legacy optional YOLO face detector weights. |
| `ATTENDANCE_CAMERA_INDEX` | `0` | OpenCV camera index; must be a non-negative integer. |
| `ATTENDANCE_DETECTOR` | `yolo` | Current detector selection: `yolo` or `haar`. |
| `ATTENDANCE_YOLO_CONFIDENCE` | `0.40` | YOLO detection confidence, greater than zero and at most one. |
| `ATTENDANCE_FRAME_INTERVAL_SECONDS` | `0.03` | Delay between processed camera frames, greater than zero. |
| `ATTENDANCE_CAPTURE_MAX_AGE_SECONDS` | `1.0` | Maximum age of a camera frame when an enrollment photo is requested. |
| `ATTENDANCE_CAPTURE_MIN_FACE_SIZE_PIXELS` | `80` | Minimum width and height of the detected face in the original camera frame. |
| `ATTENDANCE_CAPTURE_MIN_BLUR_SCORE` | `50.0` | Minimum variance-of-Laplacian score measured on the original face pixels. |
| `ATTENDANCE_CAPTURE_BRIGHTNESS_MIN` | `40.0` | Minimum mean grayscale brightness of the detected face, from 0 to 255. |
| `ATTENDANCE_CAPTURE_BRIGHTNESS_MAX` | `220.0` | Maximum mean grayscale brightness of the detected face, from 0 to 255. |

For example, in PowerShell, set `$env:ATTENDANCE_CAMERA_INDEX = "1"` before launching to select camera index 1. Set `$env:ATTENDANCE_DATA_DIR` to an absolute path to keep writable data elsewhere. The data directory is created when the application starts; merely importing the configuration does not create directories or open a camera.

Enrollment freshness and image-quality defaults are provisional starting values, not calibrated thresholds. Captures retain the original pixels and a padded face crop; the app does not enlarge a small face to make it appear higher quality.

## Local data and Git

The application stores student records in `attendance.sqlite3` and logs in `log.txt` under `data/` by default. Enrollment captures go under `data/assets/enrollment_sessions/` in per-enrollment UUID folders. These locations follow `ATTENDANCE_DATA_DIR` when configured. Student Submit requires at least three accepted captures; saved students remain pending until recognition indexing is implemented.

Several of these files are already tracked by Git. Ignore rules do not untrack existing files or remove them from repository history. Existing root-level `users.txt` and `log.txt` remain untouched; new runtime writes go to the configured data directory. T09 covers an explicit, reviewed import of legacy user records. Existing log entries come from placeholder code and must not be treated as verified attendance. Back up real face photos, databases, and attendance records; avoid adding them to Git.

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
