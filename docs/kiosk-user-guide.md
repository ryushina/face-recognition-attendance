# Using the attendance kiosk

## For students

1. Wait until the screen says **Look at the camera**.
2. Stand with your whole face inside the outline. Only one student should be in view.
3. Hold still and wait for **You're checked in**. Your attendance is saved only when that confirmation appears.
4. Move completely out of the camera view for about a second so the next student can check in. You can leave as soon as confirmation appears; the screen returns to **Look at the camera** after the confirmation ends and your departure is detected.

**Already checked in today** means your record is saved; you can leave. **We couldn't recognize you** means no attendance was saved: center your face and try again, then ask staff if needed. If the kiosk is paused or unavailable, ask staff. **Need help?** displays guidance; it does not call or message anyone.

## For staff

Open **Staff access**. The first run creates a staff password; later runs ask for it. Keep this password with the responsible staff, and finish setup before leaving the station available to students.

In **Setup**, select the camera number (usually 0), choose the school's timezone, and confirm the displayed date/time. **Save setup and test camera** also confirms the current rule: one attendance record per student per local calendar day. Camera/timezone preferences persist across restarts.

In **Enroll student**:

1. Enter the LRN, first name, and last name. Middle name and guardian information are optional. Continue to face photos.
2. Use an authorized participant. Capture three clear photos, with small changes in head angle. The button is disabled until a fresh frame with one face is available. Improve centering, distance, sharpness, or lighting when the app explains a rejection. **Retake last photo** removes only the latest unsaved capture.
3. Review the details and save. Wait for **Ready for check-in**. If preparation fails, use **Retry preparation**; do not register the same student again.
4. Choose **Test recognition** and have the student face the camera again. Confirm the matched name is correct. Repeat with small, natural changes of position at the intended check-in spot before opening the kiosk.

Open **Students** to find a saved record by name or LRN. Staff can correct student or guardian details, inspect the saved face photos, and run **Check photo quality**. The check reports whether each stored image has one detectable face, adequate face size, sharpness and brightness, and can be processed by the current model. A passing stored photo is not proof of a live match; use **Test live recognition** afterward.

If a photo needs replacement, choose **Retake face photos**, capture at least three new images, and review/save the complete set. The existing set remains active until staff save. Recognition preparation then runs again; the student's attendance history stays attached to the record. Detail edits and unsaved replacement photos prompt before they are discarded.

Choose **Lock and open student kiosk** when the preview works and at least one student is ready. Attendance is paused while staff tools are open. Choose **Lock and keep paused** when the station should not record attendance. Explicitly locking or navigating away prompts before discarding unsaved changes. Staff access automatically locks after five idle minutes, closes private windows, and discards any unfinished draft.

**History** shows records for a selected school-local date and optional student ID. Clear filters to view all matching records. **Export CSV** exports the displayed filter's records to your chosen file.

Open **Maintenance** to change the staff password, clear attendance history, or reset student records. Changing the password requires the current password and a new password of at least 10 characters. Clearing history keeps student profiles and face photos. **Students -> open a record -> Delete student and attendance** removes only that student, their attendance events, and linked app-managed enrollment photos. **Reset all student records** removes all student profiles, their attendance events, and linked app-managed enrollment photos. Destructive actions show what will be removed and require both the current staff password and the exact confirmation phrase. A reset keeps the staff password, camera/timezone setup, backups, and exported files. These app controls do not delete backup copies. Forgotten staff passwords require local administrator recovery.

## Checking a recognition failure

Open **Staff access -> Diagnostics -> Live recognition check**. The same live recognition pipeline continues while attendance is paused. This view shows individual frame results, the number of saved students, and the number loaded in the recognition gallery. It never saves attendance or new photos. A match here is a diagnostic observation, not a completed check-in or a measured accuracy result.

- **No usable face:** center the whole face and check lighting/distance.
- **Match below required similarity:** compare the current pose/lighting with enrollment, and read the best similarity alongside the required value.
- **Two students match too closely:** inspect the enrollment records for mix-ups and test each student separately. The separation value is the difference between the best two student scores.
- **No students loaded:** finish saving/preparing the enrollment. Captured draft photos alone do not create a saved student.
- **Matched:** staff should confirm the displayed name/LRN belongs to the person being tested.

Scores are similarities, not probabilities. Do not lower thresholds merely to accept a rejected student: test fresh scans from enrolled and unenrolled volunteers before choosing new values. Diagnostics clears the last result when frames become stale and clears private results when staff lock the screen.

## If something goes wrong

| Screen or problem | Action |
| --- | --- |
| Check-in is not ready | Staff: finish Setup, prepare at least one enrolled student, and check Diagnostics if models failed to load. |
| Camera unavailable or stopped | Staff: reconnect the camera, close another app using it, then open Diagnostics and choose Retry camera. If necessary, correct the camera number in Setup. |
| Capture photo is disabled | Wait for the preview, center one face, and ensure only one person is visible. Use Diagnostics if the camera is stopped. |
| Photo rejected | Follow the capture message. Hold still for blur, adjust lighting, or move away from the frame edge. |
| Recognition preparation failed | The student's record is saved. Retry preparation and read staff Diagnostics for the cause. |
| Attendance could not be saved | Staff: check the data drive/storage error in Diagnostics. Use the school's alternate attendance process until the problem is resolved. |
| A setting is overridden | A launch environment variable conflicts with the saved preference. Ask the person who starts the app to remove that override and restart. |
| Staff password not accepted | Retry carefully. After five incorrect attempts, wait 30 seconds. Staff can change a known password in Maintenance; forgotten credentials need local administrator recovery. |

Technical details stay in staff Diagnostics and `application.log`. Share only the relevant error text for troubleshooting; do not send student records or face photos unnecessarily.
