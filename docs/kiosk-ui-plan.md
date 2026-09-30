# Guided student attendance kiosk

Status: the SFace correction and the core guided Tk kiosk/staff workflow are implemented locally. Programmatic Tk checks cover layout, staff locking, and synthetic enrollment-to-attendance. The interactive preview illustrates the design; it is not a camera session. Physical-camera validation and first-time-user evaluation remain open.

Implementation record (2026-09-30): `kiosk_view.py` supplies the student screen and staff flow, `kiosk_flow.py` handles fresh-frame gating and confirmation/departure, and `kiosk_settings.py` supplies persistent preferences and local staff access. The core of K1-K5 below is present. Remaining refinements include separate prompts for clipped/small faces, readiness details for each setup prerequisite, field-specific validation placement, and a fully structured camera error catalogue. K6 is partly verified with deterministic Tk checks; visual and hardware evaluation are still required.

Student record maintenance is implemented locally in `student_records_view.py` and `StudentRepository`: staff can search/edit a saved record, inspect its sample thumbnails, review face detection, size, blur, brightness, and model processing for every sample, and stage a replacement photo set. Save atomically switches the active sample references while preserving the student and attendance row. The old image files are retained. Replacement recognition must finish before the student is shown as ready.

## Confirmed direction

The user selected **students check themselves in at a kiosk**. Design the default screen for a student approaching the camera without instructions from a developer. Staff manage setup, enrollment, attendance history, and recovery in a protected area.

### Next step after live recognition failures

The staff **Live recognition check** is now implemented in Diagnostics, with a **Test recognition** action after successful enrollment preparation. First confirm every expected student was saved and loaded, then observe new camera scans to distinguish unusable faces, low similarity, and insufficient separation. Stored-photo consistency alone cannot validate recognition on new images. Keep thresholds unchanged until fresh positive and negative examples have been reviewed.

Recommended sequence: **capture varied clear photos -> save and prepare -> test a fresh scan with staff -> open kiosk**. The test currently shows individual frame matches; it does not persist a verified-enrollment flag or measure recognition accuracy. A future improvement can guide pose/lighting corrections and let staff replace poor samples for an existing student without duplicate registration.

QR is optional and not implemented. If a fallback is needed, propose **scan student QR (or enter LRN) -> compare the face only with that student's saved samples -> save attendance after a stable accepted match**. A QR identifies a record; it should not automatically create attendance on this face-verification path. Use an opaque revocable token rather than guardian details in the code. Expire/cancel the selected identity between students. QR can remove competition between identities, but it cannot repair a poor face image; staff assistance remains necessary for failed verification. Validate the recognition cause before adding QR as a required step for every student.

Reference: [NIST's face-verification evaluation](https://pages.nist.gov/frvt/html/frvt11.html) describes the effect of image quality, lighting, and camera angle on false non-matches. This is background guidance, not validation of this app.

Keep Python, Tkinter/ttkbootstrap, the local database, and the existing offline recognition pipeline. Plan against the existing 800x480 minimum and the Windows desktop size. Raspberry Pi performance and its actual display are still unverified. Keep a staff member available during the pilot while recognition accuracy and spoof resistance remain unevaluated.

## What the screenshot revealed

- SFace alignment received a Python list because `RecognitionService.detect()` converted the full YuNet array with `tolist()`. OpenCV requires a NumPy row. Preserve the native detector row through validation and alignment.
- Reproduced the exact error with actual OpenCV/SFace, synthetic pixels, and supplied landmarks. This needed no camera or person's image. The new regression covers the real binding; fake recognizers alone had accepted the wrong type.
- The long, unwrapped error label can increase the grid's requested width and push controls outside the visible window. Error content must not determine the screen width.
- The heading says the models are active even when the camera has failed. Model loading and readiness for attendance are separate states.
- Registration, camera management, and the unavailable teacher feature compete with the student's task. The empty camera area gives no next step.

## Student journey

1. Approach a ready kiosk. The main instruction says **Look at the camera**, with a live preview and a positioning outline.
2. Follow one instruction at a time: move into view, come closer, or hold still. Multiple people in view prompts **One person at a time**.
3. Wait for **You're checked in** and the recorded time. A match alone must never display attendance success.
4. Step aside. The screen clears the student's name and rearms for the next person after the confirmation and face departure.

There are no student Start Camera, Start Attendance, registration, export, or history controls. A small **Need help?** action explains how to seek a nearby staff member; it does not silently send a notification.

## Screen arrangement and visual rules

- Header: **Student check-in**, the configured school-local date/time, and a truthful readiness label. A small **Staff access** action opens the protected staff entry screen.
- Main area: a large camera preview and one prominent instruction/result. The preview has a visible placeholder while opening or unavailable; it never becomes an unexplained blank area.
- Footer: **1 Look at the camera -> 2 Hold still -> 3 Wait for confirmation**. Highlight the current step using text and shape as well as color.
- Success: confirmation plus the student's first name and recorded time, shown briefly. Do not expose the roster, LRN, guardian details, previous students, or a face gallery.
- Retain a restrained teal accent with adequate text contrast. Use generous spacing, short labels, a clear heading hierarchy, keyboard focus, and touch targets around 44 pixels. Essential instructions should use at least 18-pixel text at the baseline size, with headings around 28 pixels.
- At 800x480, retain the camera and next instruction with a compact header/footer. At larger sizes, enlarge useful content instead of leaving most of the screen empty. The student screen requires no scrolling.
- Staff forms may scroll vertically. Their next action and validation message remain reachable. Wrap long messages within their parent; avoid long labels expanding uniform grid columns.
- Camera-preview mirroring is presentation-only if enabled. Detection, landmarks, and captured pixels must stay in one consistent coordinate system.

## Kiosk states and language

| State | Student message | Required behavior |
| --- | --- | --- |
| Setup incomplete | Check-in is not ready. Please see staff. | Staff can see the exact missing setup item. Attendance stays disabled. |
| Opening | Getting the camera ready... | Give a visible waiting state and a bounded startup timeout. |
| Ready / no face | Look at the camera. Stand inside the outline. | Ready requires fresh frames, working models, a usable gallery, configured timezone, writable storage, and enabled attendance. |
| Face partly outside / too small | Move into the outline / Move a little closer. | Keep the preview alive. Reject unusable detections and stale evidence. |
| Checking | Hold still while we check you in. | Require stable evidence from distinct, fresh frames. Do not show scores or frame counts. |
| Saving | Saving your attendance... | No success until the database confirms the write. |
| Recorded | You're checked in, Maya. You can step aside. | Use the actual saved timestamp. Maya is fictional preview text. |
| Duplicate | You're already checked in today. You can step aside. | No second record; show the stored check-in time only when available. |
| Unknown / ambiguous | We couldn't recognize you. Face the camera and try again, or ask staff. | No attendance record; allow a fresh attempt. |
| Multiple faces | One person at a time, please. | Reset recognition evidence; no attendance record. |
| Staff paused | Check-in is paused. Please see staff. | Never imply recognition is recording attendance. |
| Camera / recognition failure | Check-in is temporarily unavailable. Please see staff. | Invalidate stale results and pause attendance. Staff see the cause and a relevant recovery action. |
| Storage failure | We couldn't save your attendance. Please see staff. | No success indication; prevent automatic repeated writes until recovery is checked. |

Proposed confirmation duration: 3 seconds, adjustable after usability checks. Clear the name after that duration even if the person remains, then prompt them to step aside. Rearm only after the view has cleared for fresh observations; do not flash between success and duplicate messages for a stationary student. A different arriving person must provide new evidence. Camera failure clears evidence and pending UI timers immediately.

## Staff area

Use explicit staff authentication before configuration, enrollment, history, exports, or diagnostics. Proposed default: a locally configured staff password with protected credential storage, bounded attempts, and automatic relocking. Do not ship a default password or treat a hidden button as authentication. Device-level kiosk lockdown is a separate installation task.

### First-time setup

1. Create staff access and select the camera. Show a working preview and a **Test camera** action.
2. Choose the school's timezone explicitly and confirm the displayed date/time. Do not infer the school timezone from the developer machine. Explain the current one-record-per-student-per-local-day rule.
3. Check recognition models, writable data storage, and enrollment readiness. Show **Ready**, **Needs setup**, or **Needs attention** with a concrete next action for each item.
4. Open the student kiosk only when these checks pass. Persist settings locally; normal users should not need PowerShell environment variables. Explicit environment overrides may remain for development and should be visible to staff.

### Guided enrollment

1. **Student details:** label LRN as **Learner Reference Number (LRN)**, mark required fields, and show field errors beside their inputs while keeping entered values.
2. **Face photos:** show the preview, framing guidance, accepted-photo thumbnails, and **0 of 3 photos accepted**. Guide small changes in pose; do not claim pose validation until implemented. Enable capture only with a fresh usable frame. Explain rejection directly, such as **Photo is blurry. Hold still and try again.** Retakes affect only the draft session.
3. **Review and save:** confirm student details and photos, then display **Preparing recognition...**. Show **Ready for check-in** only after successful indexing and gallery reload. If preparation fails, preserve the saved record and offer a safe retry without duplicate registration.

Attendance pauses while enrollment is active. Returning to the kiosk checks readiness again and requires fresh evidence. Cancel is explicit about unsaved draft work.

### Daily operations and recovery

- Staff can pause/resume the kiosk, enroll a student, view/filter history, and export records. Remove the inactive teacher-registration button.
- Diagnostics show a concise cause, a relevant action such as **Reconnect camera and retry**, and expandable technical details. Retain full exceptions in rotating logs rather than the student screen.
- Publish structured status/error codes from camera and recognition services. The view maps them to audience-appropriate text instead of classifying raw exception strings.
- Preserve safe camera ownership on retry: wait for the old worker to release the device, then start one new worker. Keep the error screen visible until readiness is restored.
- If storage is unavailable, guide staff to the existing alternate attendance procedure. Do not mark an unsaved event successful or silently invent a manual attendance entry.

## Implementation order

| Step | Work | Completion check |
| --- | --- | --- |
| K1 | Correct the native SFace row handoff. | Type regression and real SFace alignment/feature test pass with synthetic pixels. Implemented locally. |
| K2 | Introduce explicit kiosk states, bounded message layout, and friendly error/recovery text. | Inject long exceptions, camera loss, and storage failure: actions remain visible and attendance fails safely. |
| K3 | Replace the default three-column management layout with the student screen and automatic guided check-in. | Success follows a database result; confirmations clear; next student starts with fresh evidence. |
| K4 | Build protected staff access and persistent setup. | Student mode cannot expose records or change settings; missing setup prevents a ready state. Required before public use. |
| K5 | Move enrollment into the three-step staff flow and retain history/export. | A new operator enrolls a test student without developer commands; partial failure preserves data. |
| K6 | Validate desktop usability and the complete camera workflow. | Record real results at the intended display/camera, plus recovery and first-time-user checks below. |

Reuse the current database/repositories, camera worker, enrollment session/indexer, evidence tracker, and attendance service. Expected implementation locations are `view.py`, `main.py`, `camera_ui.py`, `camera_service.py`, and configuration/status helpers as needed. Keep identity and database rules outside the view. Add tests for state transitions, access boundaries, retries, and data integrity; use visual inspection for layout and typography.

## Acceptance checklist

- [ ] Student can walk up and complete check-in with no menu navigation or verbal coaching.
- [ ] At least three first-time testers understand when attendance is saved, already recorded, or unsuccessful. Record observed confusion and revise the copy.
- [ ] All student states fit at 800x480 and 1100x650; check intended Windows DPI settings, including 125% and 150%. Check actual kiosk scaling before deployment.
- [ ] An arbitrarily long diagnostic message never hides the main instruction, help, or staff recovery controls.
- [ ] Multiple faces, unknown identity, partial face, stale frame, paused camera, and failed writes never display success or create attendance.
- [ ] Success is readable, clears personal information, and resets correctly for the next student. A restart cannot create a duplicate daily record.
- [ ] Staff access protects enrollment, history, export, settings, and logs; management sessions relock.
- [ ] Missing models, wrong camera, disconnect, indexing failure, and storage failure have tested recovery paths.
- [ ] Enroll -> restart -> recognize -> save -> repeat scan -> history/export -> backup/restore is exercised using authorized test material and isolated records.
- [ ] Do not mark the desktop or recognition validation complete based only on synthetic/model-API tests. Actual camera, recognition accuracy, and the target display still require recorded checks.

## Remaining deployment inputs

The school timezone and attendance policy, target display/camera/Pi details, staff credential recovery process, and any non-English student copy need local decisions before deployment. These do not block the UI state and layout implementation. The proposal uses English and a staff-assisted pilot as its working defaults.
