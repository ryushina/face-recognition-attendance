# Implementation plan for Luna

Plan and execution record. T01-T12, T14-T16, T18-T20, and T22-T23 are complete. T13, T17, T21, and T24 remain in progress pending the checks recorded below. T25-T30 remain TODO.

UI direction update: the user selected student self-service at a kiosk. The core guided screen, protected staff area, persistent setup, three-step enrollment, and staff maintenance controls are implemented locally; see [docs/kiosk-ui-plan.md](docs/kiosk-ui-plan.md) and [the operator guide](docs/kiosk-user-guide.md). Programmatic Tk layout and workflow checks pass for the kiosk and enrollment flow; new maintenance actions still need verification. Existing visual/hardware validation remains open. The reproduced SFace array-to-list handoff bug is fixed locally and has a real OpenCV/SFace API regression using synthetic pixels.

## Working assumptions

- Preserve the Python, Tkinter/ttkbootstrap desktop application and Windows development support.
- Operate offline during enrollment and attendance. Downloads are setup actions, never a surprise at runtime.
- Use SQLite locally. Keep face images and model files on disk, with references and model metadata in the database.
- Start with student attendance. Teacher registration, guardian notifications, class schedules, time-out, cloud synchronization, and a web interface are later features.
- Proposed first attendance rule: one record per student per configured local calendar day. This is a draft assumption, not a confirmed school policy. If the user chooses time-in/time-out or class sessions, revise T18-T20 before implementing them.
- Proposed interaction: the operator starts/pauses attendance mode. A fresh, stable recognized identity records attendance automatically in that mode. Enrollment pauses attendance.
- The school timezone must be configured explicitly before real attendance collection. Do not infer it from the development computer.
- Raspberry Pi model, RAM, OS/Python version, display resolution, camera type, and expected number of students are not yet supplied. Hardware-dependent tasks must record these before claiming compatibility or speed.
- Recognition thresholds and enrollment quality thresholds are provisional until evaluated on suitable held-out data. Similarity scores are not probabilities.
- This plan targets a supervised pilot. Resistance to printed-photo or phone-screen impersonation is not implemented in the current code and is not implied by face matching.

## Repository baseline

- `main.py`: app startup, controller, placeholder model, CSV registration writer, hardcoded attendance logger.
- `view.py`: desktop UI, student form, camera display. Submit is empty, teacher registration has no handler, and capture state is discarded.
- `camera_service.py`: YOLO/Haar detection, background capture, face crops. No identity recognition; restart and stale-frame problems exist.
- `requirements.txt`: pinned packages, but the active Python used during review did not have several required dependencies installed.
- `users.txt` and `log.txt` are tracked by Git. The existing user record points to a missing photo directory. Existing attendance entries were produced by a hardcoded name; do not silently migrate them as verified attendance.
- There is no README or automated test suite at this baseline.
- Syntax checks passed. Isolated checks reproduced duplicate registration, discarded form fields, missing-photo acceptance, lost capture state, camera restart failure, and stale face-present state after read failure. No live GUI, recognition, or Pi performance validation was performed.

## How to execute

Use the two batch prompts in `LUNA_PROMPTS.md` for the remaining work. Task IDs remain the progress checklist; they do not require separate user prompts. Within an authorized batch, follow dependencies, run each task's checks, update this file, and continue automatically. Stop at the batch boundary or a genuine external blocker. A request selecting just one task still stops after that task. Read current source rather than relying on old line numbers.

States: `TODO`, `IN PROGRESS`, `DONE`, `BLOCKED`. A task is `DONE` only when its stated checks have run successfully. If code is implemented but a required hardware/manual check is unavailable, leave the task unfinished and record the remaining check. An external prerequisite may block one task without blocking independent tasks.

Each task should have one reviewable purpose. Avoid a whole-app rewrite, speculative abstractions, and unrelated upgrades. Expected files below are guidance, not rigid limits. Add tests for data integrity, camera state, identity decisions, and attendance behavior; use inspection or a smoke check for simple documentation and styling changes.

Use fakes and temporary directories for automated tests. Do not capture real faces, access the camera, mutate existing records, or install services just to run an ordinary unit test. Real camera checks are explicit manual/hardware validation steps. Preserve existing work and original data.

## Shared design agreements

- `config.py`: resolve application/model/data paths and validate configuration. Writable data must not depend on the shell's current directory.
- `database.py` / `repositories.py`: SQLite schema and parameterized storage operations. Keep database code independent of GUI and model imports. Use connections in their owning threads.
- `CameraService`: owns the capture lifecycle and produces timestamped results. UI widgets are updated by the Tk thread through a bounded latest-result handoff.
- Enrollment state: a stable session ID owns its pending photos. Changing a student's identity invalidates previously captured samples. Cancel may clean only files belonging to that unfinished session.
- `recognition_service.py`: model loading, consistent preprocessing, embedding extraction, identity decisions. Version embeddings with the model and preprocessing so incompatible vectors are never compared.
- `attendance_service.py`: validates recognition evidence and applies attendance rules. Database uniqueness survives app restarts; an in-memory cooldown alone is insufficient.
- Camera freshness uses a monotonic capture timestamp and frame ID, carried through inference. Attendance stores a UTC event timestamp and a local attendance date derived from the configured timezone.
- Keep enrollment and attendance modes separate. An unknown, ambiguous, stale, failed, or multiple-face result cannot authorize attendance.

## Simplified remaining work: two implementation prompts

Planning revision requested 2026-09-29: prioritize a simple working application and minimize repeated prompts. This changes execution grouping, not recorded test results. T12-T30 have not been implemented by this planning update.

The first usable outcome is: launch -> enroll with three suitable captures -> recognize the enrolled student -> record attendance once per local day -> view/export history -> restart without losing data. Keep the existing Python desktop UI, local SQLite database, and offline runtime. Use one primary recognition pipeline selected in T12. Implement the existing daily attendance draft as the development default; a real installation still needs its school timezone explicitly configured and its policy confirmed.

| Batch | Tasks | Result | Execution boundary |
| --- | --- | --- | --- |
| 1: Working desktop app | T12-T24, plus necessary setup and existing enrollment integration fixes | Recognition, daily attendance, basic history/export, usable existing UI, simple diagnostics and backup, complete workflow verification | Continue through the desktop tasks automatically; stop before Pi work. |
| 2: Raspberry Pi and supervised validation | T25-T30 | The same application installed and checked on the chosen Pi and camera, with measured performance and evaluated recognition | Requires the actual target and authorized evaluation inputs; stop after the recorded pilot results. |

### Batch 1 checkpoints (one prompt, no approval between checkpoints)

1. **Make the development app runnable.** Close the outstanding clean-environment/import check from T01 using an isolated Python 3.12 environment. The last app import failed because `cv2` was missing. Install only justified dependencies, provision the chosen official models during setup, and verify actual imports/model loading. Review the existing enrollment transaction and file lifecycle before integration: saved images must remain protected after any cleanup or identity edit, including when a read after database commit fails. Fix demonstrated problems with focused regressions.
2. **Recognize enrolled students: T12-T17.** Select one pipeline, implement alignment and embeddings, store/reload the gallery, reject unknown/ambiguous matches, require fresh consistent evidence, and show the result in the existing preview. A real model loading/extraction check is separate from stub tests. Suitable test images must be available and authorized; do not use the user's stored faces implicitly.
3. **Record and show attendance: T18-T22.** Implement the draft daily uniqueness rule in SQLite. Replace dummy Login logging with Start/Pause Attendance, suspend it during enrollment, and add a basic history table and CSV export. Keep the current form and preview usable on a small display. Use clear status text and standard rotating logs.
4. **Verify recovery and the full workflow: T23-T24.** Provide a simple explicit backup/restore command or stopped-app procedure, restoring to a separate directory. Test the complete workflow with temporary data and record real GUI/model/camera checks separately. Fix failures before claiming the desktop checkpoint complete.

Keep implementation small: reuse the existing modules; use small functions/classes where needed; keep model loading and inference outside Tk callbacks; avoid extra frameworks, detector stacks, or a new plugin architecture. Teacher features, cloud services, notifications, dashboards, and time-in/time-out remain later work. Backup needs no extra UI, and performance tuning waits for a measured bottleneck.

### Batch 2 prerequisites and sequence

Supply the Pi model/RAM, OS/Python, camera type, display resolution, school timezone, expected student count, and access to the actual device together. Authorized enrollment/tuning/evaluation captures or participants are also required for recognition evaluation. These are external inputs, not reasons to invent compatibility or accuracy results.

Execute T25 -> T26 -> T27 -> T28 -> T29 -> T30, checking dependencies and the desktop state first. Reuse OpenCV for a USB camera; add Picamera2 only for a selected CSI camera that needs it. Verify installation and offline startup before tuning. Measure first, adjust only a demonstrated bottleneck, evaluate thresholds on separate tuning/evaluation data, and then verify desktop autostart and the supervised pilot on that Pi.

Missing hardware or manual checks stay explicitly open. Continue only independent selected work with satisfied dependencies. One batch prompt authorizes continued work; it cannot supply missing hardware, evaluation data, or access. If interrupted, resume the same batch from this file's records rather than restarting completed tasks.

## Phase A: reproducible setup and camera reliability

### T01 — Document and verify the development setup

Status: DONE. Dependencies: none. Completed 2026-09-29.

Scope: add a short README with the current workflow, virtual-environment setup, the supported/tested Python version, installation commands, and launch command. Review the existing pins before changing any. Add ignore rules for future runtime databases, photos, logs, caches, and local environments. Explain that ignore rules do not untrack existing files; preserve those files and Git history.

Done when: setup commands match the repo; syntax checks run; dependency import checks are either verified in an isolated environment or explicitly recorded as outstanding. A full environment verification remains required before desktop integration testing. No unsupported claim that the app runs on Pi.

Expected files: `README.md`, `.gitignore`, dependency files only if evidence justifies a change.

### T02 — Centralize configuration and filesystem paths

Status: DONE. Dependencies: T01. Completed 2026-09-29.

Scope: add a small configuration module for model paths, writable data directory, camera source, detector choice, and configurable processing/freshness settings. Resolve bundled assets from the project/module location and writable paths from explicit configuration. Use these paths in existing capture and persistence code. Keep old data available for the later importer.

Done when: starting from a different working directory resolves the same model and data paths; an unwritable directory or missing model produces a useful error; imports do not create directories or open a camera. Verify with temporary directories.

Expected files: `config.py`, `main.py`, `camera_service.py`, focused tests.

### T03 — Make detector loading and fallback reliable

Status: DONE. Dependencies: T02. Completed 2026-09-29.

Scope: remove unused unconditional Ultralytics imports from application modules. Load it only when YOLO is selected. Verify Haar availability, expose which detector is active, and surface model initialization errors. Keep fallback behavior explicit. Never download missing weights silently at runtime.

Done when: the Haar path works with Ultralytics absent; YOLO-load failure is visible; unavailable Haar resources produce a controlled failure. Fake imports/model loaders are sufficient for error-path tests.

Expected files: `main.py`, `view.py`, `camera_service.py`.

### T04 — Repair camera start, stop, and failure state

Status: DONE. Dependencies: T03. Completed 2026-09-29.

Scope: open the camera on start, report failed opens, release it through coordinated worker shutdown, and reopen on restart. Clear cached frames, boxes, and face flags on stop/read failure. Handle inference exceptions without leaving a false running state. Keep only one worker active; use a bounded stop strategy and do not release a device concurrently with an active read.

Done when: repeated start/stop/start works with a fake device; a failed read or inference cannot leave a capturable old face; failed open and stop during capture are handled; no second worker starts while the previous one is still terminating.

Expected files: `camera_service.py`, lifecycle tests.

### T05 — Move UI delivery onto the Tk thread

Status: DONE. Dependencies: T04. Completed 2026-09-29.

Scope: have the worker publish the latest frame/status to a bounded queue or protected slot. Have a Tk-owned timer poll it and update widgets. Ensure close cancels timers, stops processing, and cannot deliver frames into destroyed widgets. Display camera and detector errors.

Done when: worker code makes no widget/Tk calls; delayed rendering does not accumulate an unbounded frame backlog; closing during detection is controlled. Use fake view/scheduler checks plus a manual GUI check when the environment is available.

Expected files: `camera_service.py`, `view.py`, `main.py`.

### T06 — Validate enrollment captures

Status: DONE. Dependencies: T05. Completed 2026-09-29.

Scope: timestamp frames at acquisition and attach an increasing frame ID. Reject stale frames, zero or multiple faces, and faces whose original pixels are too small. Preserve the full face box and useful padding for later landmark alignment; validate bounds, avoid stretching clipped crops, and add configurable blur/brightness checks. Keep messages actionable. Do not treat enlargement as added image quality.

Done when: synthetic frame tests cover stale/multiple/no-face cases, small and edge-clipped faces, and write failure. Rejected images do not become accepted samples. Record provisional quality settings without claiming they are calibrated.

Expected files: `camera_service.py`, configuration, focused capture tests.

Phase A checkpoint: camera errors are visible, restart is safe, the UI remains responsive, and only fresh, suitable single-face samples can be captured.

## Phase B: reliable student enrollment

### T07 — Create the SQLite student schema

Status: DONE. Dependencies: T02. Completed 2026-09-29.

Scope: add versioned schema initialization for students and face samples. Store a unique student/LRN identifier as text, all current name/guardian fields, creation time, and enrollment status. A sample belongs to one student and references a local image. Enable foreign keys on every connection. Keep recognition and attendance tables for their own tasks.

Done when: initialization is repeatable; leading-zero IDs are retained; uniqueness and foreign keys are enforced; rollback is verified using a temporary database. No existing CSV is overwritten.

Expected files: `database.py`, schema tests.

### T08 — Add student validation and repository operations

Status: DONE. Dependencies: T07. Completed 2026-09-29.

Scope: implement create/get/list students and associated samples with parameterized SQL. Require student ID, first/last names, and existing valid sample files. Preserve optional middle/guardian fields; avoid inventing LRN or phone-format policy. Save student/sample rows in one transaction and translate duplicate/write errors into useful results.

Done when: duplicate IDs, blank required fields, nonexistent samples, Unicode names, leading-zero IDs, and transaction rollback are covered. No partial student is stored if sample persistence fails.

Expected files: `repositories.py`, repository/validation tests.

### T09 — Add a non-destructive legacy user importer

Status: DONE. Dependencies: T08. Completed 2026-09-29.

Scope: provide an explicit importer with dry-run output for `users.txt`. Report malformed records, duplicates, and missing image directories. Valid legacy details may be retained as pending enrollment, never recognition-ready without samples. Preserve source files. Keep `log.txt` as legacy data rather than treating hardcoded entries as verified attendance.

Done when: fixture import is repeatable without duplicates; missing images are reported; original inputs are unchanged; importing a sample twice has a clear result. Do not import the user's real files automatically.

Expected files: `scripts/import_legacy.py`, importer tests, README instructions.

### T10 — Retain a student enrollment session

Status: DONE. Dependencies: T06, T08. Completed 2026-09-29.

Scope: keep pending capture paths/count and form details in an explicit session. Use a stable session folder instead of a name-derived identity. Show accepted sample count and capture errors. Reset samples when the student ID changes. Cancel and submit must distinguish pending from saved samples.

Done when: capture then collect form data retains the sample references; changing identity cannot reuse another person's samples; cancel affects only files owned by the current unfinished session; capture failure adds no sample. Attendance mode is paused during enrollment once that mode exists.

Expected files: `view.py`, `main.py`, small enrollment-state module if needed.

### T11 — Connect student Submit to persistent registration

Status: DONE. Dependencies: T10. Completed 2026-09-29.

Scope: implement Submit using the repository and the session's accepted samples. Save all form fields, prevent repeated submission, and give clear success/duplicate/write-error feedback. Configure a provisional minimum of three accepted captures; vary pose/lighting during guided enrollment. Keep saved files in stable locations and pending samples retryable after a database failure. Remove the active CSV-write path.

Done when: register -> close -> reopen -> query retains all fields and samples; failed submit loses neither original data nor pending captures; cancel after a successful submit cannot delete saved samples. Students are pending recognition indexing until T14 succeeds.

Expected files: `main.py`, `view.py`, enrollment integration tests.

Phase B checkpoint: a student can be enrolled once with linked photos, duplicate IDs are rejected, and enrollment survives restart.

## Phase C: face identity recognition

### T12 — Select and document a local recognition pipeline

Status: DONE. Dependencies: T11. Completed 2026-09-29.

Scope: make a bounded technical decision using official model documentation and a small local loading smoke check. Evaluate OpenCV YuNet + SFace as the initial candidate: recognition needs consistent landmark alignment, which the current YOLO box-only result does not supply. Choose one primary recognition pipeline; avoid running two detectors for every frame without evidence. Record exact weight sources, model/preprocessing identifiers, checksums, required packages, and licenses. Runtime remains offline.

Done when: `docs/recognition-decision.md` defines the chosen pipeline, inputs/outputs, setup, failure behavior, and known limits. A local smoke check is documented; absent models/data are recorded as outstanding. Pi suitability remains provisional until T27-T28. Haar/YOLO detection alone must never be called identity recognition.

Expected files: `docs/recognition-decision.md`, model setup instructions/manifest, dependency changes only as needed.

### T13 — Implement aligned embedding extraction

Status: IN PROGRESS. Dependencies: T12. Started 2026-09-29.

Scope: load the selected models once, obtain the needed landmarks, align the face, and produce a validated normalized numeric embedding using one preprocessing path for enrollment and live input. Handle missing/corrupt weights, no face, multiple faces, and invalid output. Expose a small injectable interface independent of Tk and SQLite.

Done when: invalid input fails clearly; vectors have the expected dimension and finite values; a provided suitable local image can be processed consistently; no UI or network side effects occur on import. Model-stub tests alone do not establish real extraction accuracy.

Expected files: `recognition_service.py`, focused extraction tests.

### T14 — Persist versioned enrollment embeddings

Status: DONE. Dependencies: T13 implementation interface; real-image check remains open under T13. Completed 2026-09-29.

Scope: add a schema migration and repository support for sample embeddings with model/preprocessing version, dimension, and encoding. Index saved student samples off the Tk thread. Mark a student ready only after the required samples index successfully. Reload the gallery on startup and support an explicit rebuild after model/preprocessing changes. Avoid unsafe pickle loading.

Done when: gallery state survives restart; incompatible/corrupt vectors are rejected; indexing failure leaves a clear pending/failed state; incomplete or mixed-version indexes are not published to recognition. Re-indexing does not duplicate students or erase photos.

Expected files: schema/repository modules, recognition service, enrollment status UI.

### T15 — Match identities and reject unknown/ambiguous faces

Status: DONE. Dependencies: T14. Completed 2026-09-29.

Scope: compare a live embedding to the enrollment gallery and return a typed result: recognized, unknown, or ambiguous. Aggregate samples by student before comparing the best and runner-up identities. Apply configurable minimum similarity and separation from the next student. Handle an empty gallery and incompatible vectors. Keep thresholds provisional for T28.

Done when: synthetic embeddings verify correct grouping, empty gallery, low-score rejection, ambiguous nearest students, and incompatible data. Results include the model version and score used; scores are never labelled probabilities.

Expected files: recognition matching logic and focused tests.

### T16 — Require a fresh, consistent identity across frames

Status: DONE. Dependencies: T15. Completed 2026-09-29.

Scope: add a small state machine that requires a configurable number of consistent results from distinct frames within a time window. Track the original capture time through inference. Reset on unknown/ambiguous/multiple-face results, identity change, camera loss, mode change, or timeout. Reprocessing the same frame cannot count as new evidence.

Done when: deterministic tests with an injected clock cover identity switching, duplicate frame IDs, slow/stale inference, interruptions, and timeout. A previously recognized person cannot remain eligible after disappearing.

Expected files: recognition state module and tests.

### T17 — Show live recognition in the desktop application

Status: IN PROGRESS. Dependencies: T05, T16. Implementation complete; manual GUI/authorized-image check remains open.

Scope: integrate the pipeline into the bounded worker/UI handoff. Show recognized student, unknown, ambiguous, processing, and error states. Load models/gallery once, avoid inference inside Tk callbacks, and refresh the gallery after successful enrollment indexing. Keep captured-frame freshness intact through display and processing.

Done when: fake pipeline integration checks pass; enrollment refresh is visible without restart; failures clear the prior identity; a manual GUI/real-model check is recorded separately from automated tests. Do not record attendance in this task.

Expected files: `camera_service.py`, `main.py`, `view.py`.

Phase C checkpoint: an enrolled student can be recognized after restart, and unknown/ambiguous/stale results cannot be treated as an identity.

## Phase D: valid attendance and basic operator workflows

### T18 — Implement the attendance database and rule

Status: DONE. Dependencies: T08, draft daily attendance rule adopted for development. Completed 2026-09-29.

Scope: add attendance schema/service for the chosen rule. For the draft daily rule, use a database unique constraint on student ID + local attendance date. Store the UTC timestamp, configured timezone, student reference, and recognition metadata needed to explain the event. Use an injected clock and reject unconfigured/invalid timezone. Keep SQLite access in the owning thread.

Done when: repeated and concurrent record attempts cannot create duplicates; next local day can create a new record; UTC/local-date boundaries and invalid identities are tested; the rule still holds after reopening the database. If the school policy changed, revise this task before implementing its schema.

Expected files: database migration, `attendance_service.py`, attendance tests.

### T19 — Replace the hardcoded Login behavior

Status: DONE. Dependencies: T17, T18. Completed 2026-09-29.

Scope: make the attendance-mode control start/pause recording. Pass only fresh, stable recognition evidence to the attendance service. Show recorded/already recorded/unknown/error feedback. Pause attendance and clear evidence on enrollment entry, camera loss, or mode changes. Remove the hardcoded name and active text-log attendance writer.

Done when: an eligible identity creates exactly one durable record; repeated frames and app restart do not duplicate it; paused mode, enrollment, unknown/multiple faces, stale queued results, and camera failure create none. Simulated storage failure must not display success.

Expected files: `main.py`, `view.py`, integration tests.

### T20 — Add attendance history and CSV export

Status: DONE. Dependencies: T19. Completed 2026-09-29.

Scope: add a basic history table with date/student filtering and an explicit CSV export action. Display configured local time and student details. Handle empty results, canceled export, and write errors. Query SQLite through the repository.

Done when: displayed and exported records agree for the selected filters; names containing Unicode, commas, or quotes export correctly; an empty day is clear; exports do not overwrite the database or source photos.

Expected files: `view.py`, query/export logic, export tests.

### T21 — Make the existing UI usable on a small display

Status: IN PROGRESS. Implementation complete; manual 800x480 visual check remains open.

Scope: replace placeholder labels, preserve camera image aspect ratio, and make the long enrollment form scrollable. Remove the rigid 1200-pixel minimum where it blocks smaller displays. Clearly disable or label teacher registration as unavailable until implemented. Check capture/submit/mode buttons and status text at a provisional 800x480 and the eventual target resolution.

Done when: required controls remain accessible without clipping; preview does not stretch faces; camera/registration/attendance status is understandable. Use manual visual checks rather than tests that mirror widget layout.

Expected files: `view.py`, limited window setup in `main.py`.

### T22 — Surface operational failures and record diagnostics

Status: DONE. Dependencies: T19. Completed 2026-09-29.

Scope: add bounded/rotating diagnostic logs and useful user-facing errors for camera, inference, and storage failures. Avoid logging face arrays, embeddings, full guardian details, or per-frame noise. Ensure failed writes and worker crashes clear success/identity state. Keep this separate from attendance records.

Done when: injected read-only/disk-write/model failures show useful status and never false attendance success; log retention is bounded; diagnostic output contains no biometric payloads. Do not fill the real disk to simulate failure.

Expected files: logging setup and existing service error paths.

### T23 — Provide a verified backup and restore procedure

Status: DONE. Dependencies: T14, T18. Completed 2026-09-29.

Scope: implement an explicit local backup command/procedure for a consistent SQLite snapshot plus referenced samples and configuration/model-version metadata. Use SQLite's backup mechanism or a documented stopped-app backup. Restore into a separate data directory first, validate references/schema, and never overwrite the current data directory automatically.

Done when: fixture backup can be restored and retains enrollment, embeddings, and attendance; missing files/corrupt backup are reported; paths remain portable to another data directory. Models may be restored from their documented checksummed sources instead of duplicated in every backup.

Expected files: backup utility, restore instructions, a round-trip test.

### T24 — Verify the complete desktop workflow

Status: IN PROGRESS. Automated end-to-end checks complete; manual desktop checks remain open.

Scope: add a focused end-to-end integration test using temporary data, fake capture/model results, and an injected clock. Verify enrollment -> indexing -> restart -> recognition -> attendance -> history/export. Record a separate manual desktop checklist using actual models and camera when available. Fix failures within this workflow before marking the checkpoint complete.

Done when: duplicate enrollment, unknown faces, repeated frames, restart deduplication, enrollment-mode suppression, camera disconnect, and storage failure are covered. Automated checks and manual results are listed separately; a real-model/camera check is not invented when hardware/data are absent.

Expected files: integration tests, `docs/desktop-validation.md`.

Phase D checkpoint: the desktop MVP records one valid attendance event, survives restart, shows history, and can recover data from a backup.

## Phase E: Raspberry Pi validation and supervised pilot

Run the setup/benchmark work as soon as the selected recognition pipeline and a Pi are available; it need not wait for UI polishing. Code can be prepared without hardware, but device-dependent completion claims require the actual device.

### T25 — Add the selected Pi camera backend

Status: TODO. Dependencies: T04, T06; camera type is required for device verification.

Scope: keep the OpenCV backend for USB cameras. If the target is a CSI Pi camera module, add a Picamera2 adapter with the same start/read/stop and timestamp semantics. Make its imports platform-specific and optional on Windows. Document/test the capture color format against the recognition preprocessing contract.

Done when: fake backend contract checks pass and the chosen camera opens, captures, disconnects/stops, and restarts on the Pi. If using USB only, verify that path and mark the Picamera2 implementation not applicable rather than adding an unused dependency.

Expected files: camera adapter module, configuration, hardware instructions.

### T26 — Create reproducible Pi setup instructions

Status: TODO. Dependencies: T12; actual target hardware for install verification.

Scope: record the Pi model/RAM, 64-bit OS, Python version, camera, display, and cooling. Verify a compatible set of packages and required OS libraries in an isolated environment. Include Tk/display support, camera permissions, model provisioning, a writable data directory, and explicit timezone configuration. If Picamera2 uses OS packages, explain the environment setup needed to access them.

Done when: install/import/startup checks run on the stated Pi environment; the UI and model initialize offline after setup; commands are repeatable. Keep environment-specific dependencies separate where necessary and avoid claiming the existing Windows pins work on ARM without checking.

Expected files: `docs/raspberry-pi-setup.md`, platform dependency files if needed.

### T27 — Measure and tune the complete pipeline on Pi

Status: TODO. Dependencies: T17, T25, T26; actual Pi and representative gallery size.

Scope: measure camera-to-decision latency, processing/display rates, memory, CPU, and temperature for the chosen pipeline. Record input size, gallery size, model versions, and warmup. Optimize one measured bottleneck at a time through resolution, processing frequency, thread settings, or an appropriate supported runtime. If retaining YOLO, evaluate NCNN only if needed; do not replace the model blindly.

Done when: reproducible before/after measurements and the selected settings are recorded; frame backlog remains bounded; recognition accuracy is rechecked after preprocessing/model/runtime changes. Agree on an acceptable decision-latency target from the intended workflow. No desktop benchmark is presented as a Pi result.

Expected files: small benchmark tool, `docs/pi-benchmark.md`, evidence-backed config changes.

### T28 — Evaluate recognition and calibrate thresholds

Status: TODO. Dependencies: T15-T17 and selected runtime; T27 for the final Pi configuration.

Scope: use suitable user-provided/authorized evaluation captures, separating enrollment, threshold-tuning, and final evaluation images. Include enrolled people under varied conditions and people absent from the gallery. Measure false matches, false rejections, ambiguous results, and decision latency. Choose thresholds using tuning data and report performance on held-out data. Check printed-photo/phone-screen behavior and record limitations.

Done when: results include sample counts, conditions, thresholds, and model/preprocessing version; known and unknown cases are both evaluated; no claim of liveness/anti-spoofing is made without an implemented, validated mechanism. Lack of evaluation data is an explicit blocker, not permission to invent accuracy or use a published threshold as proven local accuracy.

Expected files: small evaluation tool, `docs/recognition-evaluation.md`, calibrated configuration.

### T29 — Configure desktop autostart and recovery

Status: TODO. Dependencies: T24, T26, T27; actual Pi graphical session.

Scope: prepare an autostart mechanism appropriate for this Tk application and the target desktop session. Set interpreter, paths, writable data location, and bounded restart/logging behavior explicitly. Handle camera-not-ready startup and avoid multiple app instances. Document clock/timezone setup, graceful shutdown, and how to disable autostart. Do not assume a headless system service can display Tk windows.

Done when: reboot starts one working application in the target desktop session; a recoverable crash can restart without duplicate attendance or database damage; disabling autostart works. Prepare files first. When assigned this task for an identified Pi, install and verify them there; do not activate Pi autostart on the development workstation.

Expected files: `deploy/` launcher/autostart assets, deployment instructions.

### T30 — Run the supervised on-device pilot checklist

Status: TODO. Dependencies: T25-T29; actual device, operator, and evaluation participants.

Scope: verify enroll -> restart -> recognize -> record -> repeat scan -> unknown face -> history/export -> backup/restore. Exercise camera loss/recovery, mode changes, graceful shutdown, reboot, and simulated storage errors. Run a sustained session and record memory/temperature/latency trends. Verify time remains correct across the intended online/offline boot conditions.

Done when: `docs/pilot-results.md` contains actual outcomes, hardware/software identifiers, remaining limitations, and failures with follow-up task IDs. Unsupervised use is not claimed ready merely because a supervised demo passed. Any failed acceptance check remains open.

Expected files: pilot checklist/results and narrowly scoped fixes justified by failures.

Phase E checkpoint: the actual Pi reliably performs the intended workflow with measured speed, evaluated matching behavior, persistent data, and documented remaining limits.

## Later work, outside the first MVP

- Teacher registration and roles.
- Class/session attendance, late/absent rules, and time-in/time-out if selected.
- Student record correction, deactivation, and supervised attendance corrections with history.
- Guardian notifications only after a communication channel and sending policy are specified.
- A separately evaluated liveness/anti-spoofing mechanism if unattended operation is required.
- Cloud sync, remote dashboards, and fleet management only if required.

## Task completion record

For each completed or blocked task, append a short entry here:

```text
Task: Txx
State: DONE / BLOCKED / IN PROGRESS
Changes:
Verification commands and actual results:
Manual/hardware checks still outstanding:
Decisions or deviations:
Next eligible task:
```

```text
Task: T01
State: DONE
Changes: Added Windows/Python 3.12 setup and current-prototype limits to README.md; ignored future virtual environments, generated face/data directories, databases, exports, and logs; converted requirements.txt to plain UTF-8 without changing its 34 pins so pip can read it.
Verification commands and actual results: Python 3.12.10 and Python 3.14.1 both parsed the three application files successfully. pip 25.0.1 on Python 3.12 parsed all 34 requirements without installing packages. Confirmed decoded requirement lines and pins match HEAD exactly. Confirmed example environment, cache, photo, database, CSV, and log paths match the ignore rules. `git diff --check` reported no whitespace errors. Confirmed users.txt, log.txt, and model weights remain tracked; their sizes are unchanged at 74, 252, and 6,281,321 bytes respectively.
Manual/hardware checks still outstanding: The active global Python 3.12 environment contains only 3 requirements at their pinned versions; 8 installed package versions differ and 23 requirements are missing. A clean virtual-environment installation, full application import, desktop GUI, and live camera are therefore not verified. No hardware checks were required or claimed for T01.
Decisions or deviations: Kept every dependency pin unchanged. Corrected requirements.txt's UTF-16 encoding after a standard UTF-8 read raised `UnicodeDecodeError`. Did not install packages or alter globally installed Python. Ignore rules do not remove already tracked data from Git.
Next eligible task: T02
```

```text
Task: T02
State: DONE
Changes: Added side-effect-free `AppConfig` with repository-root model paths; configurable/default writable data, CSV, log and photo paths; and validated camera, detector, confidence, and processing-interval settings. Routed controller registration, capture and log writes through the selected data directory. The camera receives the same settings, uses the configured model, camera and processing interval, and reports the exact missing model path. Documented all six environment variables. Added eight standard-library configuration tests.
Verification commands and actual results: `python -B -m unittest discover -s tests -p 'test_config.py' -v` and `py -3.14 -B -m unittest discover -s tests -p 'test_config.py' -v`: all eight tests passed under both interpreters. Syntax checks passed with Python 3.12.10 for `config.py`, `main.py`, `camera_service.py`, and the configuration tests. Isolated integration smoke using temporary directories and a fake camera: capture paths, CSV registration, and logging followed the configured directory from another working directory. The tracked root `users.txt` and `log.txt` remained byte-for-byte unchanged. A separate isolated smoke used a fake camera and fake YOLO loader: missing weights produced the configured path and `ATTENDANCE_MODEL_PATH` instruction, with the existing Haar fallback selected. Verified each documented variable appears in README and `git diff --check` reported no whitespace errors.
Manual/hardware checks still outstanding: The real GUI, USB/CSI camera, trained YOLO inference, and Raspberry Pi were not run. Full application imports remain unavailable in the global interpreter pending the clean dependency environment from T01.
Decisions or deviations: Relative overrides resolve from the source/application directory; absolute data/model overrides remain absolute. The default writable location is `data/`; captures go under `data/assets/`, and saved `photo_dir` references are relative to the configured data directory. Creating the data directory happens at app startup or an explicit write, never while importing configuration. No camera or model was used in tests.
Next eligible task: T03
```

```text
Task: T03
State: DONE
Changes: Removed module-level Ultralytics imports from the application. Import YOLO only when the selected detector is YOLO; show active detector and fallback reason in the app header. Check YOLO weights exist before loading. Verify the Haar XML file exists and that OpenCV can load its cascade. Raise a descriptive startup error when no detector works, and do not open the camera until detector initialization succeeds. Added fake-dependency detector tests.
Verification commands and actual results: `python -B -m unittest discover -s tests -v` and `py -3.14 -B -m unittest discover -s tests -v`: all 16 configuration and detector tests passed under Python 3.12.10 and Python 3.14.1. Syntax checks passed for changed and test Python files. Verified no Python module has a module-level Ultralytics import. Fake dependencies verified Haar startup without Ultralytics, successful YOLO startup with configured weights, fallbacks for missing Ultralytics, missing model weights and YOLO load errors, active-detector and fallback status, and errors for unusable Haar or invalid detector before any camera open. `git diff --check` reported no whitespace errors.
Manual/hardware checks still outstanding: The real GUI status label, installed OpenCV Haar cascade, YOLO dependencies/weights and inference, and physical camera were not exercised. The global Python environment remains incomplete as recorded in T01.
Decisions or deviations: Delayed camera acquisition until detector initialization succeeds so a detector configuration error does not open the camera. Failure of both detectors raises a descriptive `DetectorInitializationError`. No camera hardware or real model weights were used in tests.
Next eligible task: T04
```

```text
Task: T04
State: DONE
Changes: Moved camera opening to `start()` and reopening to each restart. Failed opens and worker startup errors are reported and clean up the device. The capture worker owns release; stop clears cached frames, boxes, and face state immediately, waits up to a bounded timeout, and blocks restart while an old worker is still alive. Read, frame-processing, and inference errors stop the worker, clear stale capture state, and release the camera. Added seven lifecycle tests with fake devices and updated the detector test to assert camera construction remains side-effect free.
Verification commands and actual results: `python -B -m unittest discover -s tests -v` and `py -3.14 -B -m unittest discover -s tests -v`: all 23 tests passed under Python 3.12 and Python 3.14. The lifecycle checks cover failed open, VideoCapture exception, failed/throwing reads, inference failure, safe stop during a blocked read, prevention of a second worker before exit, restart after termination, and capture rejection after stop. Syntax parsing passed for `camera_service.py` and all three test files. `git diff --check` reported no whitespace errors.
Manual/hardware checks still outstanding: The real Tk GUI and physical camera were not exercised. No camera or model hardware validation is claimed.
Decisions or deviations: A worker that remains blocked in the camera backend past the two-second stop timeout retains camera ownership; `stop()` returns failure and restart is refused until that worker exits. This avoids releasing a device during an active read or starting overlapping workers. Updated the existing T03 detector test because its former expectation that service construction opens a camera conflicts with T04's start-time acquisition.
Next eligible task: T05
```

```text
Task: T05
State: DONE
Changes: Replaced camera-worker widget callbacks with a locked, single-slot latest frame/status handoff. Added `TkCameraUpdatePoller` to poll on Tk's event loop and update the preview/status widgets there. Added a separate camera status label, shows detector initialization failures in the header, and made app shutdown cancel the polling and delayed-start timers before stopping capture and destroying the root. Added poller and bounded-slot tests.
Verification commands and actual results: `python -B -m unittest discover -s tests -v` and `py -3.14 -B -m unittest discover -s tests -v`: all 28 tests passed under Python 3.12 and Python 3.14. Fake scheduler/view callback tests verified a single recurring timer, latest-frame delivery on the polling thread, status delivery, timer cancellation, and that a queued callback cannot touch a destroyed view. The camera handoff test verified repeated frames replace the prior frame while retaining pending status. Syntax parsing passed for all nine application and test Python files. Reviewed `camera_service.py`; it contains no Tk scheduling or widget calls. `git diff --check` reported no whitespace errors.
Manual/hardware checks still outstanding: The desktop GUI and physical camera were not exercised. `python -B -c "import main"` could not load the app because the active Python environment lacks `cv2` (`ModuleNotFoundError`); no package installation was attempted. The fake scheduler tests do not substitute for a live Tk render/close check.
Decisions or deviations: Kept the detector label separate from camera runtime status so fallback details remain visible while camera errors change. If detector initialization fails completely, the app leaves the error visible and disables camera capture rather than silently exiting during construction. Added `camera_ui.py` to isolate the scheduler poller for standard-library-only tests.
Next eligible task: T06
```

```text
Task: T06
State: DONE
Changes: Timestamped each valid frame at camera acquisition with a strictly increasing frame ID. Enrollment capture now rejects stale frames, zero or multiple faces, invalid/out-of-frame boxes, faces smaller than the configured original-pixel minimum, padded crops that would cross a frame edge, and faces failing configurable blur or brightness checks. Saves the unresized face box plus proportional context padding, tags the filename with the frame ID, and only marks a frame captured after a successful image write. Added capture-quality configuration and documented its provisional defaults.
Verification commands and actual results: `python -B -m unittest discover -s tests -v` and `py -3.14 -B -m unittest discover -s tests -v`: all 34 tests passed under Python 3.12 and Python 3.14. Synthetic frame checks cover stale, missing, multiple, too-small, out-of-bounds, padding-clipped, blurry, too-dark, and too-bright captures; rejected cases do not write an image or create an output directory. Accepted crop dimensions confirm the original padded pixels are retained without resizing. Separate checks cover increasing frame IDs, acquisition timestamps, configuration validation, and both false-return and exception write failures. Syntax parsing passed for all nine application and test Python files. `git diff --check` reported no whitespace errors.
Manual/hardware checks still outstanding: Capture quality thresholds have not been calibrated against real faces or the eventual camera. The physical camera, installed OpenCV quality operators, and live enrollment GUI were not tested. Synthetic checks do not establish recognition quality or suitability for deployment.
Decisions or deviations: Defaults are provisional: 1-second maximum frame age, 80-pixel minimum face width and height, variance-of-Laplacian minimum 50, and mean grayscale range 40–220. The crop uses proportional horizontal and vertical padding around the original detector box and remains at source resolution for later landmark alignment. A crop is rejected when the full margin does not fit rather than silently clipping facial context. All five settings can be overridden with `ATTENDANCE_CAPTURE_*` environment variables.
Next eligible task: T07
```

```text
Task: T07
State: DONE
Changes: Added `Database` with version 1 initialization recorded through SQLite `PRAGMA user_version`. The schema stores text student IDs, all current name and guardian fields, a UTC creation time, and a default pending enrollment status. Face samples reference one student and a local image path; foreign keys cascade on student deletion and an index supports student sample lookup. Every new connection enables and verifies foreign-key enforcement. `Database.from_config()` resolves `attendance.sqlite3` inside the configured data directory without creating directories or opening a connection at import time.
Verification commands and actual results: `python -B -m unittest discover -s tests -v` and `py -3.14 -B -m unittest discover -s tests -v`: all 42 tests passed under Python 3.12 and Python 3.14. Temporary-database checks verified repeatable initialization, version tracking, retention of leading zeroes and Unicode fields, duplicate-ID rejection, foreign-key enforcement on separate connections, sample ownership and cascade deletion, rollback of partial schema creation and version changes, and refusal to alter a database marked with a newer schema version. `Database.from_config()` was checked not to create the configured data directory. Syntax parsing passed for all eleven application and test Python files. `git diff --check` reported no whitespace errors. `git status --short -- users.txt log.txt` showed no changes to either legacy file.
Manual/hardware checks still outstanding: None are required for schema-only T07. The application does not yet use this schema for registration; that integration is T08-T11. No existing legacy records were imported or rewritten.
Decisions or deviations: Used SQLite's built-in `user_version` for schema versioning. Kept recognition embedding and attendance tables out of this initial schema so their later tasks own those decisions. Sample image paths are stored as text and are intended to be relative to the configured data directory; file existence and path validation are T08 responsibilities.
Next eligible task: T08
```

```text
Task: T08
State: DONE
Changes: Added `StudentRepository` operations to create students with sample rows, load one student, list students, and list associated samples. Required ID and names are validated; optional middle and guardian details are retained. Sample inputs resolve from the configured data directory when relative and must be readable non-empty files. Student and sample inserts use parameterized SQL in one transaction. Added clear validation, duplicate-ID, constraint, and database-write errors.
Verification commands and actual results: `python -B -m unittest discover -s tests -v` and `py -3.14 -B -m unittest discover -s tests -v`: all 50 tests passed under Python 3.12 and Python 3.14. New temporary-database tests cover blank required values, nonexistent/directory/empty sample paths, Unicode and leading-zero IDs, optional fields, get/list/sample reads, SQL-like IDs treated as data, duplicate IDs, and transaction rollback when a sample constraint fails. `git diff --check` reported no whitespace errors.
Manual/hardware checks still outstanding: None for repository validation; the application does not use the repository in Submit until T11.
Decisions or deviations: Repository creation normally requires at least one valid sample. A narrowly scoped `allow_empty_samples` option is available for T09's pending legacy records, which may have no usable images. Absolute sample paths outside the data directory are retained as absolute local paths; paths inside it are stored relative to the directory.
Next eligible task: T09
```

```text
Task: T09
State: DONE
Changes: Added `scripts/import_legacy.py` with a read-only dry run by default and an explicit `--apply` option. It reports malformed rows, repeated source IDs, IDs already present in SQLite, and missing photo directories; valid rows are imported as pending students with any existing sample file references. It never reads or imports `log.txt`. Documented preview and explicit import commands in README.
Verification commands and actual results: `python -B -m unittest discover -s tests` and `py -3.14 -B -m unittest discover -s tests`: all 55 tests passed under Python 3.12 and Python 3.14. Tests cover missing photo paths, malformed and duplicate rows, explicit apply, repeat-import results, optional Unicode/guardian fields, pending rows without samples, source preservation, and dry-run avoiding database creation. `python -B scripts/import_legacy.py` previewed the repository's actual `users.txt`: one row would be pending with zero samples because `photos/user_0001` is missing; no database was created or written. AST syntax parsing passed for 15 Python files; `git diff --check` passed. `users.txt` and `log.txt` remain unchanged.
Manual/hardware checks still outstanding: None for the importer; no live data import was performed. The real record was only previewed, as required. Legacy attendance in `log.txt` remains unverified and untouched.
Decisions or deviations: The command defaults to a dry run and only initializes/writes the selected database with `--apply`. Missing image folders do not prevent retaining a student as pending, which supports legacy rows without usable photos. Source rows are never modified.
Next eligible task: T10
```

```text
Task: T10
State: DONE
Changes: Added `EnrollmentSession` to own a UUID-based capture directory, accepted paths/count, current form details, and capture errors. The controller now creates a session for student enrollment and captures only into that session. The form refreshes session details as the student ID changes, displays accepted capture count and failures, and Cancel removes only tracked session-owned sample files. Changing the ID clears those samples; submitted sessions are protected from cancellation cleanup for T11.
Verification commands and actual results: `python -B -m unittest discover -s tests -p 'test_enrollment_session.py' -v`: all six state tests passed. Full `python -B -m unittest discover -s tests` and `py -3.14 -B -m unittest discover -s tests`: all 61 tests passed under Python 3.12 and Python 3.14. Coverage verifies stable session paths and form retention, capture success/failure, ID change clearing, outside-path rejection, cancel ownership, and submitted-file protection. AST syntax parsing passed for 17 Python files; `git diff --check` passed.
Manual/hardware checks still outstanding: The Tk enrollment form and real camera capture were not exercised because this environment lacks the application GUI dependencies and no live camera validation was performed. Synthetic session tests do not validate face capture quality.
Decisions or deviations: A UUID directory is retained across student-ID edits within one attempt, while accepted image references are cleared. Cancel leaves any untracked content in that session folder untouched. No attendance mode exists yet, so there was no attendance state to pause.
Next eligible task: T11
```

```text
Task: T11
State: DONE
Changes: Connected Submit to the SQLite student repository through an enrollment service. It validates the provisional three-image minimum, persists all student and guardian fields and accepted sample references with pending enrollment status, prevents repeat submission, and reports duplicate, validation, unavailable-storage, and write errors. Successful sessions are marked submitted so Cancel cannot remove their images; failures leave pending images retryable. Removed the active `users.txt` registration writer and its startup header creation. Added enrollment storage details to README.
Verification commands and actual results: `python -B -m unittest discover -s tests` and `py -3.14 -B -m unittest discover -s tests`: all 66 tests passed under Python 3.12 and Python 3.14. Enrollment integration tests verify the three-capture minimum, all fields and sample rows after reopening the database, pending indexing status, duplicate and repeated-submit rejection, retryable files after database errors, and cancel after success preserving saved images. `python -B scripts/import_legacy.py` again previewed the root `users.txt` without creating a database or changing input. AST syntax parsing passed for 19 Python files. `git diff --check` passed.
Manual/hardware checks still outstanding: The GUI, real camera capture, and operator-visible message boxes were not exercised. `python -B -c "import main"` fails because `cv2` is not installed in the active Python environment. Automated integration used actual temporary SQLite databases and fixture image files; it does not claim camera or GUI validation. Recognition indexing remains future work (T14), and all newly registered students stay pending.
Decisions or deviations: Kept successful captures in their UUID enrollment-session folder, which gives the database stable file paths and avoids a post-submit move that could fail. The minimum of three is provisional. No package installation or migration/import of the real legacy row was performed.
Next eligible task: T12
```

```text
Task: T12
State: DONE
Changes: Selected OpenCV YuNet 2023mar for face boxes and five landmarks, followed by OpenCV SFace 2021dec `alignCrop`/`feature` on CPU. Added the model decision, version/checksum/license record and an explicit setup-only downloader with pinned OpenCV Zoo commits and SHA-256 verification. Reduced base requirements to the packages required for the Tk/OpenCV application and selected contrib face APIs. Added local model ignores and documented model provisioning.
Verification commands and actual results: Created an isolated CPython 3.12.10 `.venv` and installed `numpy==2.2.6`, `opencv-contrib-python==4.12.0.88`, `Pillow==11.3.0`, and `ttkbootstrap==1.19.0` successfully. `python scripts/download_models.py` verified both local artifacts: YuNet 232,589 bytes, SHA-256 `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`; SFace 38,696,353 bytes, SHA-256 `0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79`. OpenCV 4.12.0 instantiated `FaceDetectorYN` and `FaceRecognizerSF` successfully. `.venv` `import main` passed.
Manual/hardware checks still outstanding: No face image, live camera, attendance data, or Raspberry Pi was used for this selection/load smoke check. Pi compatibility/performance and real extraction checks belong to later tasks.
Decisions or deviations: Pinned YuNet to OpenCV Zoo commit `f12e12798e8314f7c074a6656816c048dcc95b7a` and SFace to `ba91a3b91d00d76e86540d4013f944bd6b514e39`; the downloader stages files before checksum verification and never runs from the application. OpenCV Zoo labels YuNet MIT and SFace Apache-2.0, while SFace weight training-data provenance and license scope remain questioned in upstream issue 313; document this and resolve before school distribution/deployment. No recognition threshold or accuracy claim is adopted.
Next eligible task: T13
```

```text
Task: T13
State: IN PROGRESS
Changes: Added a Tk/SQLite-independent YuNet/SFace service with one landmark-alignment path, validated 128-value finite L2-normalized embeddings, explicit empty/multiple-face errors, and injectable OpenCV/model interfaces. Added synthetic service tests. The service reads the pinned model files, loads each model once, and makes no import-time UI or network calls.
Verification commands and actual results: `.venv\Scripts\python.exe -B -m unittest discover -s tests -p 'test_recognition_service.py' -v`: all seven tests passed. Using the actual pinned OpenCV 4.12.0 models, YuNet loaded and ran on a synthetic 640x480 blank frame, returning zero detections. No real-person image was processed.
Manual/hardware checks still outstanding: User confirmed no authorized face test image is available. A suitable authorized volunteer image is required to verify actual SFace alignment/extraction and consistent output. Camera and Pi validation remain later work.
Decisions or deviations: Continue downstream implementation with synthetic embeddings, but keep T13 open until a suitable image can exercise the real extraction path. No stored legacy photo or other person's image was used.
Next eligible task: T14 (implementation can proceed using validated synthetic vectors; T13 real extraction remains open).
```

```text
Task: T14
State: DONE
Changes: Migrated SQLite schema v1 to v2 with embedding BLOB, dimension, model/preprocessing IDs, and bounded enrollment error. Added transactional repository methods and an off-Tk enrollment indexer. A student becomes ready only when all saved samples produce valid normalized, same-version vectors; incomplete or incompatible gallery rows are excluded. Re-indexing updates sample rows without moving/deleting image files.
Verification commands and actual results: `.venv\Scripts\python.exe -B -m unittest discover -s tests -p 'test_database.py' -v`: 9 passed, including v1 migration retaining the original student and photo reference. `... -p 'test_repository.py' -v`: 9 passed. `... -p 'test_enrollment_indexer.py' -v`: 4 passed, including restart reload, partial failure, incompatible versions, retryable images, and proof extraction ran on a worker thread. No legacy record was imported.
Manual/hardware checks still outstanding: Actual image indexing depends on the T13 authorized-image check; this task's durable encoding and publish rules used synthetic features. Live GUI, camera, and Pi remain open.
Decisions or deviations: Used explicit little-endian float32 (512-byte) encoding for 128 values; no pickle or model inference at app import. Real SFace feature output has not been verified against an authorized face image.
Next eligible task: T15
```

```text
Task: T15
State: DONE
Changes: Added typed recognized/unknown/ambiguous matching. Samples are aggregated by best cosine similarity per student; compatible model/preprocessing and 128-value normalized vectors are required. Added configurable provisional minimum score and student-to-student margin (defaults 0.50 and 0.08), and labels scores as similarity, not probability.
Verification commands and actual results: `.venv\Scripts\python.exe -B -m unittest discover -s tests -p 'test_recognition_service.py' -v`: 9 passed. Synthetic tests cover a student's best sample, correct identity, empty gallery, low score, near-tied identities, and incompatible versions. Thresholds remain uncalibrated.
Manual/hardware checks still outstanding: Authorized-image accuracy and threshold calibration remain open for T28; real model extraction remains outstanding under T13.
Decisions or deviations: Stored defaults are provisional and configurable through `ATTENDANCE_MINIMUM_SIMILARITY` and `ATTENDANCE_MINIMUM_MARGIN`; no published score is claimed as local performance.
Next eligible task: T16
```

```text
Task: T16
State: DONE
Changes: Added a deterministic evidence tracker requiring three distinct recognized frame IDs by default inside a two-second window. It rejects stale/future evidence and resets on unknown/ambiguous result, identity change, camera loss, pause, and evidence timeout.
Verification commands and actual results: `.venv\Scripts\python.exe -B -m unittest discover -s tests -p 'test_recognition_evidence.py' -v`: 4 passed, covering identity change, duplicate/out-of-order IDs, slow/stale inference, timeout, pause and camera interruption.
Manual/hardware checks still outstanding: Real camera cadence/freshness will be checked when an authorized camera test is available; actual camera validation remains open.
Decisions or deviations: `observe()` is called on the Tk poller with the acquisition frame ID/time and current monotonic time; no image or feature data is retained in the tracker.
Next eligible task: T17
```

```text
Task: T13 follow-up
State: IN PROGRESS
Changes: Added the Windows `tzdata` runtime dependency and verified the actual pinned YuNet and SFace OpenCV objects load from the provisioned ONNX files. The real-model blank-frame smoke check completed without touching a camera or person image.
Verification commands and actual results: `.venv\Scripts\python.exe -m pip install tzdata==2026.4` succeeded. `.venv\Scripts\python.exe -c "import numpy as np; from recognition_service import RecognitionService; service=RecognitionService('models'); print(len(service.detect(np.zeros((480,640,3),dtype=np.uint8))))"` printed `0`. Full synthetic extraction, normalization, error, and matching checks remain in the automated suite.
Manual/hardware checks still outstanding: Real SFace extraction from a suitable authorized face image and live camera verification.
Decisions or deviations: Selected the current pinned `tzdata==2026.4` because Windows may not provide an IANA timezone database; school dates remain disabled until `ATTENDANCE_TIMEZONE` is configured.
Next eligible task: T17 integration (real-image check remains open).
```

```text
Task: T17
State: IN PROGRESS
Changes: Connected camera-worker identity results and their original frame IDs/timestamps to the existing Tk-thread poller and controller. Recognition results refresh on enrollment indexing; loss/error results clear the old identity. Added explicit attendance-mode status and progress integration.
Verification commands and actual results: `python -m unittest discover -s tests` covers poller thread delivery, gallery refresh, unknown/ambiguous states, camera loss, and the complete synthetic desktop path. Actual model loading on a synthetic blank frame passed.
Manual/hardware checks still outstanding: No GUI was opened and no authorized face image or camera participant was available. The manual checklist is in `docs/desktop-validation.md`.
Decisions or deviations: Keep automatic startup behavior for the configured camera. Do not claim real-person recognition from model loading or synthetic embeddings.
Next eligible task: T18.
```

```text
Task: T18
State: DONE
Changes: Added schema v3 with UTC event time, school-local date and timezone, similarity/model version, and frame evidence metadata. The unique student/date constraint and immediate write transaction enforce the adopted draft daily rule across restarts and concurrent calls.
Verification commands and actual results: `python -m unittest discover -s tests` passed timezone-boundary, next-local-day, invalid-zone, evidence rejection, persistence, and concurrent duplicate tests after adding the pinned Windows `tzdata` package.
Manual/hardware checks still outstanding: The school's attendance policy and timezone must be confirmed before collecting real attendance.
Decisions or deviations: The plan's draft once-per-local-day rule is the development behavior. No school policy is asserted.
Next eligible task: T19.
```

```text
Task: T19
State: DONE
Changes: Replaced placeholder hardcoded Login logging with Start/Pause Attendance. Only stable, fresh, distinct-frame recognized results reach SQLite. Enrollment, camera loss, stale queued results, unknown/multiple faces, and failed writes suppress or pause attendance; failed writes never show success.
Verification commands and actual results: `tests/test_attendance_workflow.py` covers stale frames, three-frame evidence, paused mode, enrollment, unknown/multiple faces, camera loss, timezone/camera readiness, duplicate suppression, and simulated storage failure.
Manual/hardware checks still outstanding: Operator feedback and camera behavior need the desktop checks in `docs/desktop-validation.md`.
Decisions or deviations: Repeated stable results rely on the database unique constraint for durable deduplication; attendance pauses when the camera feed or storage fails.
Next eligible task: T20.
```

```text
Task: T20
State: DONE
Changes: Added date/student-filtered attendance history with local event time, student details, and explicit UTF-8 CSV export. Empty history and export/write errors are visible in the UI; canceled file selection leaves data untouched.
Verification commands and actual results: `tests/test_attendance_history.py` verifies local-time conversion, filters, invalid dates, empty exports, and Unicode/comma/quote-safe CSV. The synthetic end-to-end workflow compares the persisted history and exported CSV.
Manual/hardware checks still outstanding: Visual review of the history window remains on the desktop checklist.
Decisions or deviations: History defaults to today's configured school-local date; clearing the date shows all recent records.
Next eligible task: T21.
```

```text
Task: T21
State: IN PROGRESS
Changes: Replaced placeholder Login UI with attendance controls and a history window; added camera start/stop/restart controls and `ATTENDANCE_CAMERA_AUTOSTART` for display-only review; disabled teacher registration with an explicit unavailable label; made the enrollment panel scrollable; removed the 1200-pixel grid minimum; capped the preview image with aspect ratio preserved; set an 800x480 minimum window size.
Verification commands and actual results: Source compiles and automated controller/export checks pass. `ATTENDANCE_CAMERA_AUTOSTART=false` keeps the camera stopped while the app opens; the default remains automatic startup. The native UI bridge returned no open windows and had no desktop-control surface, so the layout could not be inspected.
Manual/hardware checks still outstanding: Open the app at 800x480 and inspect clipping and scroll behavior as recorded in `docs/desktop-validation.md`.
Decisions or deviations: Kept a compact three-panel layout, with a vertical scrollbar for the enrollment form.
Next eligible task: T22.
```

```text
Task: T22
State: DONE
Changes: Added a standard rotating application log at `data/application.log`, with three retained 1 MB files. Model initialization, camera errors, background indexing/gallery failures, and attendance storage failures produce bounded diagnostics without frame arrays or embeddings.
Verification commands and actual results: `tests/test_diagnostics.py` confirms the rotating handler configuration, single-handler setup, and file output. Attendance storage failure tests confirm the UI pauses without reporting success. The Windows app process launched with `ATTENDANCE_CAMERA_AUTOSTART=false` and an isolated temporary data directory.
Manual/hardware checks still outstanding: Confirm the operator can locate the configured log file during desktop validation.
Decisions or deviations: Kept per-frame success and identity output out of diagnostic logs.
Next eligible task: T23.
```

```text
Task: T23
State: DONE
Changes: Added `scripts/backup_data.py` with explicit `backup` and `restore` commands. Backup uses SQLite's online snapshot, copies all referenced samples into portable paths, rewrites only the backup copy, and records database/sample checksums plus schema, model, preprocessing, and timezone metadata. Restore validates integrity, foreign keys, checksums, and sample paths, and refuses every existing destination.
Verification commands and actual results: `tests/test_backup_data.py` restores enrollment samples, compatible embeddings, and attendance into a separate temporary directory, and rejects missing/corrupt photos and existing destinations without changing source data.
Manual/hardware checks still outstanding: Back up and restore a copy of the intended pilot database before using real records.
Decisions or deviations: Model files are recovered through the documented pinned, checksummed setup command rather than copied into each data backup.
Next eligible task: T24.
```

```text
Task: T24
State: IN PROGRESS
Changes: Added a synthetic end-to-end integration test for enrollment, asynchronous indexing, process-style restart, gallery reload, recognition, stable attendance, history/CSV export, and duplicate suppression after another restart. Added `docs/desktop-validation.md` to separate automated results from real desktop/model/camera checks.
Verification commands and actual results: `.venv\Scripts\python.exe -m unittest discover -s tests`: all 111 tests passed. `.venv\Scripts\python.exe -m compileall -q .`, `import main`, and `git diff --check` passed. Actual models load; the blank-frame check returns zero faces. No user image or camera was used.
Manual/hardware checks still outstanding: T13 real-face extraction, T17 GUI/authorized-image behavior, T21 800x480 layout, configured timezone/policy confirmation, and the desktop checklist remain open. The Batch 1 desktop checkpoint is not complete until these are reviewed.
Decisions or deviations: Use only temporary synthetic images, database fixtures, and fake camera frames in this environment.
Next eligible task: Complete the authorized manual desktop checks; stop before T25.
```

## Technical references to recheck when implementing

- [OpenCV face detection, alignment, feature extraction, and matching](https://docs.opencv.org/4.12.0/d0/dd4/tutorial_dnn_face.html)
- [Raspberry Pi camera software and Picamera2](https://www.raspberrypi.com/documentation/computers/camera_software.html)
- [Ultralytics Raspberry Pi deployment](https://docs.ultralytics.com/guides/raspberry-pi/)

These references establish candidate APIs and deployment approaches. They do not verify this repository's accuracy, package compatibility, or performance.
