# Desktop validation

Automated checks use temporary databases, synthetic images, and deterministic model outputs. They verify data handling and workflow behavior; they do not measure recognition accuracy or camera performance.

## Completed on 2026-09-29

- The Windows CPython 3.12 virtual environment has every pinned dependency installed, including `tzdata` for IANA timezone handling.
- Both pinned YuNet and SFace ONNX files load through OpenCV 4.12.0. YuNet processed a synthetic blank 640×480 frame and returned zero faces. No person's image was used.
- Reproduced and fixed the native SFace `face_box` type error. A test now passes NumPy detector output through the service into actual SFace alignment and feature extraction using synthetic pixels and supplied landmarks. It checks a finite normalized 128-value feature; this is an API integration check, not a real-face accuracy result. This test explicitly skips when the pinned SFace model has not been provisioned.
- The full unit and integration suite passes. The end-to-end fixture covers three-image enrollment, background indexing, reopening SQLite and the recognition gallery, stable synthetic matching, daily attendance, history, CSV export, and duplicate suppression after another restart.
- Out-of-frame YuNet candidates are discarded for that frame instead of terminating the camera worker; a regression test checks that the preview and worker continue.
- Backup and restore were exercised with temporary student samples, embeddings, and attendance. Restore retained the gallery and event in a separate directory and rejected an existing destination and a corrupt image.

## Guided kiosk checks on 2026-09-30

- The regular suite passes 130 tests; five Tk-specific tests are skipped there and run separately with `python scripts/check_kiosk_ui.py`.
- The Tk checks use isolated temporary data and no physical camera. They measure widget bounds for every student state (including long names and errors) at 800x480 and 1100x650 while exercising Tk scaling settings corresponding to 100%, 125%, and 150%. This is a programmatic layout check, not a visual screenshot review or a verified Windows DPI/device configuration.
- Staff session locking closes private history windows. Capture remains disabled without a fresh single-face frame. The synthetic guided flow saves three images, indexes the student, locks staff access, and displays confirmation only after actual SQLite attendance storage.
- Native desktop/browser automation was unavailable in this session, so no direct screenshot-based inspection or physical camera operation is claimed.

### Recognition troubleshooting

Added a staff-only live recognition check reached through Diagnostics or the post-enrollment **Test recognition** button. It observes the existing pipeline without writing attendance or additional images, distinguishes low similarity from insufficient separation and missing usable faces, and shows saved/gallery counts. Synthetic Tk checks exercise every diagnostic outcome, stale-camera clearing, and clearing private results on staff lock; no attendance is written. Matching thresholds remain unchanged. Fresh participant scans are still needed to identify the reported live rejection cause.

### Departure reset regression

The user reported the kiosk staying on **Please step aside** during live testing. A deterministic reproduction found that empty frames during the three-second confirmation were ignored: stepping away and returning during that interval left the kiosk waiting for another departure. The flow now observes and remembers departure during confirmation. Tests cover early departure/return, an empty view at confirmation expiry, brief detection loss, and a stalled feed after departure. The Tk enrollment/check-in check also verifies the actual label returns to **Look at the camera** and a repeat scan shows the existing attendance. This fixes the reproduced timing case; the reported physical-camera case still needs a restart and retest.

## Manual checks still open

- [ ] Visually inspect the guided student screen and staff setup/enrollment/history at 800×480 and the intended Windows DPI setting. Check that all guidance, actions, scrolling, and capture thumbnails remain readable.
- [ ] Have first-time students complete check-in from the screen instructions, and first-time staff complete setup/enrollment without developer coaching.
- [ ] On the intended computer, check the connected camera's startup, preview, disconnect, stop, and restart behavior.
- [ ] Move an authorized test participant partly outside the camera view, confirm the camera keeps running, then center them and confirm detection resumes.
- [ ] With authorized test participants or images, check real YuNet/SFace extraction, live identity display, enrollment indexing from actual captures, unknown-person rejection, and stable-frame attendance.
- [ ] Set the school's IANA timezone and confirm the displayed local date and one-record-per-day rule against the school's approved attendance policy.
- [ ] Back up and restore a copy of the intended pilot data into a new directory before using the workflow with real records.

Do not use existing legacy photos or records as recognition test material without authorization. Record participant consent, camera/model versions, settings, observed failures, and the test date when completing these checks. Raspberry Pi installation, speed, and accuracy remain under T25–T30.
