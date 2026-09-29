# Copy-paste prompts for Luna

Use the two batch prompts below for the remaining work. Each prompt authorizes all tasks in that batch and overrides the former one-task-per-session restriction. The single-task template remains available for a deliberately narrow follow-up. Select Luna in your coding environment; writing a model name inside the prompt does not itself switch the active model.

The task definitions and acceptance checks live in `PLAN.md`. Source code is authoritative about the current implementation; the plan records intended behavior and progress. Update the plan when the user changes a requirement.

## Batch 1 prompt: finish the working desktop app

```text
Work in E:\face-recognition-attendance.

Implement Batch 1 from PLAN.md: T12-T24 in dependency order, including
the setup and necessary enrollment integration fixes in its checkpoints.
Read applicable AGENTS.md, PLAN.md, LUNA_PROMPTS.md, and current source first.

The goal is a simple working desktop application: enroll -> recognize ->
record attendance once per local day -> view/export history -> restart
without losing data. Keep the existing Python/Tkinter UI and SQLite.
Use one primary local recognition pipeline selected and verified in T12.
Adopt the plan's draft daily attendance rule for implementation. Require an
explicit school timezone for real attendance; use explicit test settings
in automated checks. Keep later product features outside this batch.

This overrides one-task-per-session restrictions. Continue automatically
through the batch's checkpoints without asking me to say "next".
Keep tasks small internally, update PLAN.md after each task, and use those
records to resume if the session is interrupted.

Resolve the missing development dependencies in an isolated environment.
You may install justified packages there and download the selected official
model artifacts during setup; record sources, versions, checksums, and
licenses. Runtime must stay offline. Avoid unrelated package upgrades.

Implement, run acceptance checks, and fix failures. Verify actual model
loading and a real GUI launch when available. Use temporary data for tests.
Real face/camera checks require available authorized test inputs; report
missing inputs together and keep their checks open. Do not claim real
recognition, camera accuracy, or GUI validation from mocks.

Keep the UI basic: registration, camera/status, Start/Pause Attendance,
history, and CSV export. Use simple rotating logs and an explicit local
backup/restore command or stopped-app procedure, with no extra backup UI.
Fix demonstrated integration/data-preservation problems in existing code
as needed. Preserve all user data and unrelated changes. Do not auto-import
legacy records, commit, push, deploy, or spawn sub-agents.

If blocked, record why and continue only independent selected tasks with
satisfied dependencies. Keep incomplete manual checks visible; do not
mark the whole desktop checkpoint complete from automated tests alone.

Finish with task states, files changed, what actually runs, verification,
remaining blockers, and the exact next action. Stop before T25.
```

## Batch 2 prompt: run and verify on the Raspberry Pi

Use this when the target device and test inputs are available. Fill these
details in the same prompt to avoid a separate hardware questionnaire.

```text
Work from E:\face-recognition-attendance and the identified target Pi.
Implement Batch 2 from PLAN.md: T25-T30 in dependency order. Read applicable
AGENTS.md, PLAN.md, LUNA_PROMPTS.md, current source, and desktop results first.

Target Pi model/RAM and OS/Python: [fill in]
Camera type/model and display resolution: [fill in]
School timezone, daily attendance policy, and expected student count: [fill in]
Pi access/on-device workspace: [fill in]
Available authorized test participants or evaluation captures: [fill in]

Continue automatically through the selected tasks, updating PLAN.md after
each. Keep the existing application and the verified desktop pipeline.
Use the selected camera backend; add Picamera2 only if the chosen CSI camera
requires it. Verify setup/offline startup, measure the full pipeline, tune
only demonstrated bottlenecks, and evaluate known/unknown matching with
separate tuning and evaluation data.

Prepare and inspect deployment files before installing them on the
identified Pi. This batch authorizes setup and desktop autostart on that Pi,
then reboot/recovery and a supervised pilot when participants are available.
Do not activate autostart on the Windows development workstation.

Preserve existing data; use separate validation data and backup/restore
locations. Avoid unrelated refactoring, upgrades, commits, pushes, and
sub-agents. Do not auto-import real legacy records.

If a prerequisite is missing, record the blocker and continue only selected
independent work with satisfied dependencies. Never replace device tests
or evaluation with mock-based completion claims. Report missing inputs
together. Finish with task states, files changed, actual device results,
remaining limitations, and follow-up actions. Stop after this batch.
```

If a batch needs resuming, use: `Resume Batch 1 (or Batch 2) from PLAN.md
under its LUNA_PROMPTS.md batch instructions. Continue from the recorded
state, preserve prior work, and stop at that batch's boundary.`

## Shared single-task implementation prompt (optional)

Replace `T01` with the task ID you want to execute. This prompt works in a new session in the same repository.

```text
Work in E:\face-recognition-attendance.

Implement task T01 from PLAN.md. Read any applicable AGENTS.md, then the
plan's working assumptions, shared design agreements, selected task,
dependencies, and completion records. Inspect the relevant current source.
Use LUNA_PROMPTS.md for the task-specific emphasis.

Implement only this task and the integration changes necessary to make it
work. Preserve the existing Python/Tkinter application, Windows development
support, offline runtime, and existing user data. Use the plan's draft defaults
unless a later user instruction changes them; record assumptions explicitly.

Keep the change small and reviewable. Do not implement later tasks, rewrite
the app, upgrade unrelated packages, or commit/push. Activate deployment only
when the selected task includes it on an identified target. Do not spawn
other agents. Resolve ordinary implementation details yourself. If a
required product decision or external resource is truly missing, identify it
and complete any independent work within this task.

Run the task's relevant checks. Use temporary data and fake camera/model/clock
dependencies for automated tests; add meaningful regression tests for behavior
and data integrity. Do not add tests solely for cosmetic or documentation edits.
Do not claim camera, model accuracy, or Raspberry Pi verification based on mocks.
Preserve original users.txt, log.txt, photos, and databases. Use an isolated
environment for dependency setup rather than changing global Python packages.

Fix failures within this task. Update its state and append actual evidence to
PLAN.md. Mark DONE only when the required checks pass; distinguish code that
is implemented from manual/hardware validation that is still outstanding.

Finish with: task ID/state, changes, files changed, checks and actual results,
remaining limitations, and the next eligible task ID. Stop after this task.
```

## Task-specific emphasis

The shared prompt plus one line below is enough; detailed scope and completion checks are in `PLAN.md`.

| ID | Add this instruction to the shared prompt |
| --- | --- |
| T01 | Verify and document setup; add runtime-data ignore rules; preserve already tracked data. |
| T02 | Centralize paths/configuration and prove launch-directory independence without import side effects. |
| T03 | Make Ultralytics optional for Haar; surface active detector/load errors without runtime downloads. |
| T04 | Fix camera lifecycle and stale state; verify start/stop/start and read/inference failures with fake devices. |
| T05 | Use a bounded worker-to-Tk handoff; cancel timers safely and keep all widget calls on the Tk thread. |
| T06 | Accept only fresh, suitable single-face crops; validate original resolution, crop bounds, and write errors. |
| T07 | Add versioned SQLite students/sample schema with unique text IDs and enforced foreign keys. |
| T08 | Add parameterized student/sample repository operations with full-field preservation and transactional validation. |
| T09 | Build a dry-run legacy user importer; preserve originals and flag missing samples; do not trust old hardcoded attendance. |
| T10 | Persist enrollment-session capture state; invalidate samples when student identity changes; cancel only session-owned pending files. |
| T11 | Wire Submit to SQLite registration; save all fields/samples once, retain retryable captures on error, and show pending indexing. |
| T12 | Choose/document one local recognition pipeline, exact model artifacts and preprocessing; record a real loading smoke check. |
| T13 | Implement consistent landmark alignment and validated embeddings behind a small injectable interface. |
| T14 | Persist/version enrollment embeddings; index off the Tk thread and publish only compatible, complete gallery data. |
| T15 | Match by student rather than individual sample; reject low scores, ambiguity, and incompatible vectors. |
| T16 | Require consistent identity on distinct fresh frames; reset evidence on unknown, identity change, camera loss, or timeout. |
| T17 | Integrate live identity/status display without blocking Tk; refresh gallery after enrollment; do not record attendance yet. |
| T18 | Implement the adopted attendance rule with persistent uniqueness and explicit timezone; verify restart and date boundaries. |
| T19 | Replace hardcoded Login logging with attendance mode gated by fresh stable evidence; enrollment and paused mode record nothing. |
| T20 | Show attendance history with date/student filters and a matching, correctly encoded CSV export. |
| T21 | Make enrollment/status controls accessible on small screens; preserve preview aspect ratio and label unavailable teacher functionality. |
| T22 | Add bounded diagnostics and clear operational errors; never show success after failed writes or log biometric payloads. |
| T23 | Back up and restore consistent database/sample data into a separate directory; verify a fixture round trip. |
| T24 | Test the desktop workflow through restart, recognition, deduplication, history/export, and failure cases; separate real-camera checks. |
| T25 | Implement/verify the selected USB or Picamera2 backend with consistent color format, freshness, and lifecycle semantics. |
| T26 | Verify installation on the actual specified Pi/OS/Python/camera/display combination and document repeatable offline startup. |
| T27 | Benchmark the whole pipeline on the actual Pi; tune a measured bottleneck and record before/after evidence. |
| T28 | Calibrate matching on tuning data and evaluate separately on held-out known/unknown people; report spoofing limitations honestly. |
| T29 | Prepare and verify desktop-session autostart and recovery on Pi; avoid duplicate processes and preserve data/time configuration. |
| T30 | Run the actual supervised Pi pilot checklist; record observed outcomes and leave failed or unavailable checks open. |

## Short continuation prompt

Use in the same Luna session after reviewing a completed task. Change the ID each time.

```text
Implement T02 from PLAN.md under the same constraints. Check the latest source
and dependency states first. Complete only T02, run its relevant verification,
update PLAN.md with actual results, and stop. Do not mark unavailable manual
or hardware checks as passed.
```

## Independent review prompt

Use after a task or phase checkpoint when you want a review before proceeding. This is a separate optional action, not an approval requirement imposed by the plan.

```text
Review the implementation of T01 in E:\face-recognition-attendance against
PLAN.md. Read the current code and diff, trace the affected behavior, and run
relevant existing checks using temporary data. Check acceptance criteria,
data preservation, thread lifecycle where relevant, and regression risks.

Do not implement the next task or modify application code during this review.
Report concrete findings by severity with file/line references, unverified
acceptance criteria, and whether the next dependent task can proceed. If there
are no findings, say so and list the limits of the verification performed.
```

## Suggested checkpoints

- After T06: camera lifecycle, freshness, capture validation, and Tk responsiveness.
- After T11: complete enrollment and persistence across restart.
- After T17: identity recognition and reliable unknown/ambiguous rejection paths.
- After T24: complete desktop attendance workflow and recovery checks.
- After T30: measured and evaluated operation on the actual Pi.

Keep hardware-dependent tasks open when the Pi or evaluation data are unavailable. Continue an independent eligible task rather than inventing a result or repeatedly retrying a missing external prerequisite.

The scoped task, acceptance-check, and persistent progress-record structure follows [OpenAI's guidance on milestone plans and durable project memory](https://developers.openai.com/blog/run-long-horizon-tasks-with-codex). The specific task boundaries and software decisions here are based on this repository.
