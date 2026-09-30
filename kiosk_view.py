"""Guided student kiosk and staff-only setup/enrollment for the Tk desktop app."""

import tkinter as tk
import math
import time
from tkinter import messagebox
from datetime import datetime
from zoneinfo import ZoneInfo, available_timezones
import cv2
from PIL import Image, ImageTk
import ttkbootstrap as tb

from view import AppView as HistoryView
from student_records_view import StudentRecordsView


class KioskView(StudentRecordsView):
    def __init__(self, root, controller=None):
        self.root, self.controller = root, controller
        self.access = self.flow = None
        self.staff_mode = False
        self.windows = []
        self.raw_camera = "Camera has not started."
        self.raw_detector = "Models are loading."
        self.raw_operator = ""
        self.enrollment_step = 0
        self.pending_student = None
        self.entries = {}
        self._last_clock = ""
        self._last_state = None
        self._last_frame = None
        self._photo = None
        self._thumbs = []
        self._recognition_test_label = None
        self._recognition_test_update = None
        self._student_entries = {}
        self._student_original = {}
        self._editing_student_id = None
        self._photo_review_labels = {}
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        header = tb.Frame(root, padding=(20, 12))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        tb.Label(header, text="Student check-in", font=("Segoe UI", -24, "bold")).grid(row=0, column=0, sticky="w")
        self.clock_label = tb.Label(header, text="School time needs setup", bootstyle="secondary")
        self.clock_label.grid(row=1, column=0, sticky="w")
        self.staff_button = tb.Button(header, text="Staff access", bootstyle="secondary-outline", command=self.staff_login)
        self.staff_button.grid(row=0, column=1, rowspan=2, padx=(12, 0))

        body = tb.Frame(root, padding=(16, 0, 16, 0))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=11, uniform="body")
        body.columnconfigure(1, weight=10, uniform="body")
        body.rowconfigure(0, weight=1)
        body.grid_propagate(False)
        self.preview = tk.Canvas(body, background="#e8f0ed", highlightthickness=0)
        self.preview.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        self.preview.bind("<Configure>", lambda event: self._draw_preview())
        self.prompt = tb.Frame(body, padding=(8, 12))
        self.prompt.grid(row=0, column=1, sticky="nsew")
        self.prompt.columnconfigure(0, weight=1)
        self.prompt.rowconfigure(0, weight=1)
        self.prompt.rowconfigure(6, weight=1)
        self.badge = tb.Label(self.prompt, text="Setup needed", bootstyle="secondary", width=1)
        self.badge.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.title = self._wrapped(self.prompt, "Check-in is not ready", font=("Segoe UI", -30, "bold"))
        self.title.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        self.instruction = self._wrapped(self.prompt, "Please ask a staff member to complete setup.", font=("Segoe UI", -18))
        self.instruction.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        self.detail = self._wrapped(self.prompt, "", font=("Segoe UI", -16, "bold"), bootstyle="success")
        self.detail.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        self.help_button = tb.Button(self.prompt, text="Need help?", bootstyle="secondary-outline", command=self.help)
        self.help_button.grid(row=5, column=0, sticky="w")

        self.staff_panel = tb.Frame(body)
        self.staff_panel.columnconfigure(0, weight=1)
        self.staff_panel.rowconfigure(1, weight=1)
        nav = tb.Frame(self.staff_panel)
        nav.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        for i, (label, command) in enumerate((("Setup", self.setup), ("Students", self.student_records), ("Enroll student", self.begin_enrollment), ("History", self.open_attendance_history), ("Diagnostics", self.diagnostics))):
            nav.columnconfigure(i % 2, weight=1)
            tb.Button(nav, text=label, command=command, bootstyle="secondary-outline").grid(row=i // 2, column=i % 2, sticky="ew", padx=2, pady=2)
        scroller = tb.Frame(self.staff_panel)
        scroller.grid(row=1, column=0, sticky="nsew")
        scroller.columnconfigure(0, weight=1)
        scroller.rowconfigure(0, weight=1)
        self.staff_canvas = tk.Canvas(scroller, highlightthickness=0)
        self.staff_canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = tb.Scrollbar(scroller, orient="vertical", command=self.staff_canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.staff_canvas.configure(yscrollcommand=scrollbar.set)
        self.staff_content = tb.Frame(self.staff_canvas, padding=(4, 2, 12, 8))
        self.staff_content.columnconfigure(0, weight=1)
        self._staff_window = self.staff_canvas.create_window((0, 0), window=self.staff_content, anchor="nw")
        self.staff_canvas.bind("<Configure>", lambda event: self.staff_canvas.itemconfigure(self._staff_window, width=event.width))
        self.staff_content.bind("<Configure>", lambda event: self.staff_canvas.configure(scrollregion=self.staff_canvas.bbox("all")))
        self.staff_note = self._wrapped(self.staff_panel, "", bootstyle="secondary")
        self.staff_note.grid(row=2, column=0, sticky="ew", pady=6)
        self.return_button = tb.Button(self.staff_panel, text="Lock and open student kiosk", bootstyle="success", command=lambda: self.leave_staff(True))
        self.return_button.grid(row=3, column=0, sticky="ew", pady=(0, 4))
        tb.Button(self.staff_panel, text="Lock and keep paused", bootstyle="secondary-outline", command=lambda: self.leave_staff(False)).grid(row=4, column=0, sticky="ew")

        footer = tb.Frame(root, padding=(20, 10))
        footer.grid(row=2, column=0, sticky="ew")
        self.steps = []
        for i, text in enumerate(("1  Look at the camera", "2  Hold still", "3  Wait for confirmation")):
            footer.columnconfigure(i, weight=1, uniform="steps")
            label = self._wrapped(footer, text, font=("Segoe UI", -15), bootstyle="secondary")
            label.grid(row=0, column=i, sticky="ew", padx=(0, 8))
            self.steps.append(label)
        self._draw_preview()
        self.root.bind("<Configure>", self._resize_type, add="+")

    def _resize_type(self, event):
        if event.widget is self.root:
            large = event.width >= 1000 and event.height >= 600
            self.title.configure(font=("Segoe UI", -38 if large else -30, "bold"))
            self.instruction.configure(font=("Segoe UI", -22 if large else -18))

    @staticmethod
    def _wrapped(parent, text, **kwargs):
        label = tb.Label(parent, text=text, width=1, anchor="w", justify="left", **kwargs)
        label.bind("<Configure>", lambda event: label.configure(wraplength=max(40, event.width - 4)))
        return label

    def attach(self, controller, access, flow):
        self.controller, self.access, self.flow = controller, access, flow
        self.root.bind_all("<KeyPress>", lambda event: access.touch(), add="+")
        self.root.bind_all("<ButtonPress>", lambda event: access.touch(), add="+")
        self.root.bind_all("<MouseWheel>", self._scroll, add="+")

    def _scroll(self, event):
        if self.staff_mode and event.widget.winfo_toplevel() is self.root:
            self.access.touch()
            self.staff_canvas.yview_scroll(-int(event.delta / 120), "units")

    def show_kiosk(self, screen):
        self._last_state = screen
        self.title.configure(text=screen.title)
        self.instruction.configure(text=screen.instruction)
        self.detail.configure(text=screen.detail, bootstyle="success" if screen.state == "recorded" else "secondary")
        self.badge.configure(text={"ready": "Ready for check-in", "recorded": "Attendance saved", "checking": "Checking your identity"}.get(screen.state, "Please follow the instructions"))
        for index, label in enumerate(self.steps, 1):
            label.configure(bootstyle="success" if index == screen.step else "secondary")

    def help(self):
        messagebox.showinfo("Check-in help", "Look at the camera with your whole face visible. Wait until the screen confirms your attendance.\n\nIf it doesn't work, ask a nearby staff member. This button does not send a message.", parent=self.root)

    def staff_login(self):
        if self.staff_mode:
            self.leave_staff(False)
            return
        if any(window.winfo_exists() for window in self.windows):
            return
        window = tk.Toplevel(self.root)
        window.title("Staff access")
        window.geometry("440x350")
        window.transient(self.root)
        self.windows.append(window)
        panel = tb.Frame(window, padding=24)
        panel.pack(fill="both", expand=True)
        creating = not self.access.configured
        tb.Label(panel, text="Set up staff access" if creating else "Staff sign-in", font=("Segoe UI", 18, "bold")).pack(anchor="w", pady=(0, 12))
        tb.Label(panel, text="Password (10+ characters)" if creating else "Staff password").pack(anchor="w")
        password = tb.Entry(panel, show="●")
        password.pack(fill="x", pady=(3, 10))
        confirm = None
        if creating:
            tb.Label(panel, text="Confirm password").pack(anchor="w")
            confirm = tb.Entry(panel, show="●")
            confirm.pack(fill="x", pady=3)
        error = self._wrapped(panel, "First-time setup must be completed by staff." if creating else "Staff sessions lock after 5 minutes of inactivity.")
        error.pack(fill="x", pady=10)

        def submit():
            try:
                if creating:
                    if password.get() != confirm.get():
                        raise ValueError("The passwords do not match.")
                    self.access.create(password.get())
                else:
                    self.access.sign_in(password.get())
                password.delete(0, "end")
                if confirm is not None:
                    confirm.delete(0, "end")
                window.destroy()
                self._enter_staff()
            except (ValueError, OSError) as exc:
                error.configure(text=str(exc))
        tb.Button(panel, text="Create staff access" if creating else "Sign in", command=submit, bootstyle="success").pack(fill="x")
        password.bind("<Return>", lambda event: submit())
        password.focus_set()

    def _enter_staff(self):
        self.access.require()
        self.flow.suspend()
        self.flow.in_staff = True
        self.staff_mode = True
        self.prompt.grid_remove()
        self.staff_panel.grid(row=0, column=1, sticky="nsew")
        self.staff_button.configure(text="Lock staff area")
        self.setup()

    def leave_staff(self, resume=False, *, confirm=True):
        if resume and not self.access.unlocked:
            self.leave_staff(False, confirm=confirm)
            return
        if resume and not self.controller.kiosk_ready():
            self.staff_note.configure(text="Complete setup and enroll at least one recognition-ready student first.")
            return
        if confirm and not self._confirm_student_navigation():
            return
        self.controller.cancel_enrollment()
        self.enrollment_step = 0
        self.entries.clear()
        self._clear_content()
        for window in self.windows:
            if window.winfo_exists():
                window.destroy()
        self.windows.clear()
        self.access.lock()
        self.staff_mode = False
        self.flow.in_staff = False
        self.staff_panel.grid_remove()
        self.prompt.grid()
        self.staff_button.configure(text="Staff access")
        if resume:
            self.controller.start_camera()
            self.flow.resume()
        else:
            self.flow.suspend()

    def _clear_content(self):
        self._student_entries = {}
        self._student_original = {}
        self._editing_student_id = None
        self._photo_review_labels = {}
        self._recognition_test_label = None
        self._recognition_test_update = None
        for widget in self.staff_content.winfo_children():
            widget.destroy()
        self._thumbs.clear()
        self.staff_canvas.yview_moveto(0)

    def _navigate(self):
        self.access.require()
        if not self._confirm_student_navigation():
            return False
        self.controller.cancel_enrollment()
        self.enrollment_step = 0
        self.entries.clear()
        self._clear_content()
        return True

    def _text(self, text, **kwargs):
        label = self._wrapped(self.staff_content, text, **kwargs)
        label.pack(fill="x", pady=(0, 10))
        return label

    def setup(self):
        if not self._navigate():
            return
        self._text("Kiosk setup", font=("Segoe UI", 19, "bold"))
        self._text("1. Choose the camera\n2. Confirm the school time\n3. Enroll a student, then open the kiosk")
        self._text("Camera number (usually 0)")
        camera = tb.Spinbox(self.staff_content, from_=0, to=20)
        camera.insert(0, str(self.controller.config.camera_index))
        camera.pack(fill="x", pady=(0, 10))
        self._text("School timezone")
        zone = tb.Combobox(self.staff_content, values=sorted(available_timezones()))
        zone.set(self.controller.config.attendance_timezone or "")
        zone.pack(fill="x", pady=(0, 8))
        example = self._text("Choose or type an IANA timezone, e.g. Asia/Manila.")

        def show_time(_event=None):
            try:
                example.configure(text="School time: " + datetime.now(ZoneInfo(zone.get().strip())).strftime("%d %b %Y, %I:%M %p"))
            except (ValueError, KeyError):
                example.configure(text="Choose a valid timezone from the list.")
        zone.bind("<<ComboboxSelected>>", show_time)
        zone.bind("<FocusOut>", show_time)
        confirmed = tk.BooleanVar(value=False)
        tb.Checkbutton(self.staff_content, text="I confirm the displayed school time", variable=confirmed).pack(anchor="w", pady=6)
        self._text("Attendance records each student once per school-local calendar day. Saving confirms this rule for this kiosk.")

        def save():
            try:
                if not confirmed.get():
                    raise ValueError("Confirm the school time before saving.")
                self.controller.apply_kiosk_settings(zone.get().strip(), int(camera.get()))
                show_time()
                self.staff_note.configure(text="Settings saved. Check the preview, then enroll a student or open the kiosk.")
            except (ValueError, OSError) as exc:
                self.staff_note.configure(text=str(exc))
        tb.Button(self.staff_content, text="Save setup and test camera", command=save, bootstyle="success").pack(fill="x", pady=8)
        self._text(f"Students ready for recognition: {self.controller.gallery_size}")
        self.staff_note.configure(text="Attendance is paused. Staff access locks after 5 idle minutes; unsaved drafts are discarded.")

    def begin_enrollment(self):
        if not self._navigate():
            return
        self.controller.begin_enrollment()
        self.pending_student = None
        self._enrollment_details()

    def _enrollment_details(self, values=None):
        values = values or (self.controller.enrollment_session.form_details if self.controller.enrollment_session else {})
        self._clear_content()
        self.enrollment_step = 1
        self._text("1 of 3 · Student details", font=("Segoe UI", 18, "bold"))
        self._text("Fields marked * are required.")
        self.entries = {}
        for key, label in (("user_id", "Learner Reference Number (LRN) *"), ("first_name", "First name *"), ("middle_name", "Middle name"), ("last_name", "Last name *"), ("guardian_fullname", "Guardian full name"), ("guardian_phone", "Guardian phone number")):
            self._text(label)
            entry = tb.Entry(self.staff_content)
            entry.insert(0, values.get(key, ""))
            entry.pack(fill="x", pady=(0, 10))
            self.entries[key] = entry
        error = self._text("", bootstyle="danger")

        def next_step():
            values = {key: entry.get().strip() for key, entry in self.entries.items()}
            missing = [label for key, label in (("user_id", "LRN"), ("first_name", "first name"), ("last_name", "last name")) if not values[key]]
            if missing:
                error.configure(text="Enter " + ", ".join(missing) + " to continue.")
                self.staff_canvas.yview_moveto(1)
                return
            self.controller.update_enrollment_details(values)
            self._enrollment_photos()
        tb.Button(self.staff_content, text="Next: face photos", command=next_step, bootstyle="success").pack(fill="x")
        self.staff_note.configure(text="Complete the student's details, then capture three clear photos.")

    def _enrollment_photos(self):
        self._clear_content()
        self.enrollment_step = 2
        self._text("2 of 3 · Face photos", font=("Segoe UI", 18, "bold"))
        replacement = self.controller.enrollment_replacement_id
        if replacement:
            self._text(f"Retaking photos for LRN {replacement}. Save the new set to replace the current photos.")
        self._text("Keep the whole face centered. Capture a clear front view, then small changes in head angle.")
        count = self.controller.enrollment_session.accepted_count
        self._text(f"{count} of 3 photos accepted", font=("Segoe UI", 16, "bold"))
        thumbs = tb.Frame(self.staff_content)
        thumbs.pack(fill="x", pady=8)
        for path in self.controller.enrollment_session.sample_paths[-3:]:
            try:
                with Image.open(path) as source:
                    thumb = source.copy()
                thumb.thumbnail((70, 70))
                photo = ImageTk.PhotoImage(thumb)
                self._thumbs.append(photo)
                tb.Label(thumbs, image=photo).pack(side="left", padx=3)
            except OSError:
                self._text("A photo preview is unavailable.")
        self.capture_button = tb.Button(self.staff_content, text="Capture photo", bootstyle="success", command=self.capture)
        self.capture_button.pack(fill="x", pady=6)
        if count:
            tb.Button(self.staff_content, text="Retake last photo", bootstyle="secondary-outline", command=self.retake).pack(fill="x", pady=4)
        tb.Button(self.staff_content, text="Next: review and save", command=self._enrollment_review, state="normal" if count >= 3 else "disabled").pack(fill="x", pady=6)
        if replacement:
            tb.Button(self.staff_content, text="Cancel retake and return to record", command=lambda: self.open_student_record(replacement), bootstyle="secondary-outline").pack(fill="x")
        else:
            tb.Button(self.staff_content, text="Back to details", command=self._enrollment_details, bootstyle="secondary-outline").pack(fill="x")

    def capture(self):
        self.access.require()
        success, message = self.controller.handle_capture_image(self.controller.enrollment_session.form_details)
        if success:
            self._enrollment_photos()
            self.staff_note.configure(text="Photo accepted. Use a slightly different angle for the next one.")
        else:
            self.staff_note.configure(text=message)

    def retake(self):
        self.access.require()
        session = self.controller.enrollment_session
        if session and not session.submitted and session.sample_paths:
            path = session.sample_paths[-1]
            if session._is_owned_path(path.resolve()):
                path.unlink(missing_ok=True)
                session.sample_paths.pop()
        self._enrollment_photos()

    def _enrollment_review(self):
        self.access.require()
        self._clear_content()
        self.enrollment_step = 3
        self._text("3 of 3 · Review and save", font=("Segoe UI", 18, "bold"))
        session = self.controller.enrollment_session
        for key, label in (("user_id", "LRN"), ("first_name", "First name"), ("middle_name", "Middle name"), ("last_name", "Last name"), ("guardian_fullname", "Guardian"), ("guardian_phone", "Phone")):
            self._text(f"{label}: {session.form_details.get(key) or '—'}")
        self._text(f"{session.accepted_count} accepted photos")
        replacing = self.controller.enrollment_replacement_id is not None
        if replacing:
            self._text("Saving replaces this student's active photo set and rebuilds recognition. Attendance history stays with the student.")
        tb.Button(self.staff_content, text="Save replacement photos" if replacing else "Save student", bootstyle="success", command=self.save_student).pack(fill="x", pady=8)
        tb.Button(self.staff_content, text="Back to photos", bootstyle="secondary-outline", command=self._enrollment_photos).pack(fill="x")

    def save_student(self):
        success, message = self.controller.handle_register(self.controller.enrollment_session.form_details)
        self.staff_note.configure(text=message)
        if success:
            self.pending_student = self.controller.enrollment_session.student_id
            self._clear_content()
            self.enrollment_step = 4
            self._text("Preparing recognition...", font=("Segoe UI", 18, "bold"))
            self._text("The student is saved. Keep the app open while the photos are prepared for check-in.")

    def diagnostics(self):
        if not self._navigate():
            return
        self._text("Camera and recognition", font=("Segoe UI", 18, "bold"))
        repository = self.controller.student_repository
        if repository is not None:
            try:
                students = repository.list_students()
                self._text(f"Saved students: {len(students)}\nReady in the recognition gallery: {self.controller.gallery_size}")
            except Exception:
                self._text("Student records could not be read. Check storage diagnostics.")
        self._text("Live recognition check", font=("Segoe UI", 16, "bold"))
        self._text("Have each enrolled student face the camera. Confirm the matched name is correct. This checks individual frames; it does not save attendance.")
        self._recognition_test_label = self._text("Waiting for a fresh camera result.")
        self._recognition_test_update = None
        self._text("Similarity is a comparison score, not a probability. Check fresh scans before changing thresholds.")
        self._text("Check the camera connection, close other camera apps, then retry. Attendance stays paused until you open the student kiosk.")

        def retry():
            self.access.require()
            if not self.controller.stop_camera():
                self.staff_note.configure(text="Camera is still stopping. Wait and retry.")
                return
            started = self.controller.start_camera()
            self.staff_note.configure(text="Camera opening. Check the preview." if started else "Camera could not start. See technical details below.")
        tb.Button(self.staff_content, text="Retry camera", command=retry).pack(fill="x", pady=6)
        tb.Button(self.staff_content, text="Retry pending recognition setup", command=self.controller.retry_indexing).pack(fill="x", pady=6)
        self._text("Technical details (for staff)")
        details = tk.Text(self.staff_content, height=7, wrap="word", font=("Consolas", 10))
        details.pack(fill="x")
        details.insert("1.0", "\n\n".join((self.raw_camera, self.raw_detector, self.raw_operator)))
        details.configure(state="disabled")
        self._text(f"Full log: {self.controller.config.data_dir / 'application.log'}")

    def update_recognition_test(self, update):
        label = self._recognition_test_label
        if not (self.staff_mode and self.access.unlocked and label is not None and label.winfo_exists()):
            self._recognition_test_update = None
            return
        # Keep only the result needed for this private panel, never a frame.
        self._recognition_test_update = (update.get("identity"), update.get("captured_monotonic"))
        self._render_recognition_test()

    def _render_recognition_test(self):
        label = self._recognition_test_label
        if not (self.staff_mode and self.access.unlocked and label is not None and label.winfo_exists()):
            self._recognition_test_update = None
            return
        camera = self.controller.camera_service
        if camera is None or not camera.running or camera.camera_error:
            self._recognition_test_update = None
            label.configure(text="Camera unavailable. Use Retry camera below.")
            return
        if self._recognition_test_update is None:
            label.configure(text="Waiting for a fresh camera result.")
            return
        result, captured = self._recognition_test_update
        age = time.monotonic() - captured if isinstance(captured, (int, float)) else float("inf")
        if not math.isfinite(age) or not 0 <= age <= self.controller.config.identity_max_age_seconds:
            self._recognition_test_update = None
            label.configure(text="Camera result is missing or stale. Wait for fresh frames or retry the camera.")
            return
        if result is None:
            label.configure(text="No recognition result. Check the camera and model details below.")
            return
        messages = {
            "no_face": "No usable face detected. Center the whole face and check the lighting.",
            "multiple_faces": "Multiple faces detected. Test one student at a time.",
            "gallery_empty": "No students loaded for recognition. Finish saving and preparing enrollment.",
            "below_similarity": "Match below the required similarity. Check pose and lighting, then compare with the enrollment photos.",
            "insufficient_margin": "Two students match too closely. Check the enrollment records and test each student separately.",
            "invalid_embedding": "Face feature could not be used. Check model diagnostics.",
            "incompatible_embedding": "Face feature is incompatible with the loaded model. Check model diagnostics.",
        }
        if result.status == "recognized":
            message = f"Matched: {result.display_name or result.student_id}\nLRN: {result.student_id}\nConfirm this is the student in front of the camera."
        else:
            message = messages.get(result.reason, result.message or "No accepted identity match.")
        score = result.score
        if score is not None and math.isfinite(score):
            config = self.controller.config
            message += f"\nBest similarity: {score:.3f} / required: {config.recognition_minimum_similarity:.3f}"
            runner_up = result.runner_up_score
            if runner_up is not None and math.isfinite(runner_up):
                message += f"\nSeparation: {score - runner_up:.3f} / required: {config.recognition_minimum_margin:.3f}"
        label.configure(text=message)

    def open_attendance_history(self):
        self.access.require()
        window = HistoryView.open_attendance_history(self)
        self.windows.append(window)

    def tick(self):
        if self.staff_mode and not self.access.unlocked:
            self.leave_staff(False, confirm=False)
        self._render_recognition_test()
        zone = self.controller.config.attendance_timezone
        text = datetime.now(ZoneInfo(zone)).strftime("%A, %d %B · %I:%M %p") if zone and self.controller.attendance_service else "School time needs setup"
        if text != self._last_clock:
            self.clock_label.configure(text=text)
            self._last_clock = text
        if self.staff_mode and self.enrollment_step == 2:
            camera = self.controller.camera_service
            available = False
            if camera is not None:
                import time
                with camera._last_frame_lock:
                    captured = camera._last_frame_captured_monotonic
                    available = bool(camera.running and captured is not None and time.monotonic() - captured <= camera.capture_max_age_seconds and len(camera._last_boxes) == 1)
            self.capture_button.configure(state="normal" if available else "disabled")

    def update_detector_status(self, message):
        self.raw_detector = message

    def update_camera_status(self, message):
        self.raw_camera = message
        if self.staff_mode:
            camera = self.controller.camera_service
            self.staff_note.configure(text="Camera running. Follow the preview instructions." if camera and camera.running else "Camera is stopped. Open Diagnostics to retry.")

    def update_attendance_mode(self, active, message):
        self.raw_operator = message

    def update_identity_status(self, result):
        pass  # The kiosk flow owns student prompts; raw match details stay private.

    def update_attendance_progress(self, count, required, result):
        pass

    def update_attendance_result(self, attendance, display_name):
        pass

    def update_operator_status(self, message):
        self.raw_operator = message

    def update_enrollment_status(self, result):
        self.raw_operator = result.error or f"Student {result.student_id} is ready for check-in."
        if not self.staff_mode:
            return
        if result.student_id == self.pending_student and self.enrollment_step == 4:
            self._clear_content()
            replacing = self.controller.enrollment_replacement_id == result.student_id
            heading = "Recognition needs attention" if result.error else ("Student photos updated" if replacing else "Ready for check-in")
            instruction = "The student is saved. Retry preparation or see Diagnostics." if result.error else ("Replacement photos are ready. Check them and test a fresh scan." if replacing else "Recognition is ready. Open the student kiosk to check in.")
            self._text(heading, font=("Segoe UI", 18, "bold"))
            self._text(instruction)
            if result.error:
                tb.Button(self.staff_content, text="Retry preparation", command=self.controller.retry_indexing).pack(fill="x", pady=6)
                if replacing:
                    tb.Button(self.staff_content, text="Back to student record", command=lambda: self.open_student_record(result.student_id)).pack(fill="x", pady=6)
            else:
                if replacing:
                    tb.Button(self.staff_content, text="Back to student record", command=lambda: self.open_student_record(result.student_id)).pack(fill="x", pady=6)
                    tb.Button(self.staff_content, text="Test recognition", command=self.diagnostics, bootstyle="success").pack(fill="x", pady=6)
                else:
                    tb.Button(self.staff_content, text="Test recognition", command=self.diagnostics, bootstyle="success").pack(fill="x", pady=6)
                    tb.Button(self.staff_content, text="Enroll another student", command=self.begin_enrollment).pack(fill="x", pady=6)
        self.staff_note.configure(text="Recognition preparation failed. Open Diagnostics for details." if result.error else "Student ready for check-in.")

    def update_camera_frame(self, frame_bgr):
        self._last_frame = frame_bgr
        self._draw_preview()

    def _draw_preview(self):
        width, height = max(self.preview.winfo_width(), 1), max(self.preview.winfo_height(), 1)
        self.preview.delete("all")
        if self._last_frame is None:
            self._photo = None
            self.preview.create_text(width // 2, height // 2, text="Camera preview\nWaiting for camera", justify="center", fill="#47635a", width=max(width - 30, 1), font=("Segoe UI", 16))
            return
        source = Image.fromarray(cv2.cvtColor(self._last_frame, cv2.COLOR_BGR2RGB))
        source.thumbnail((width, height), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(source)
        self.preview.create_image(width // 2, height // 2, image=self._photo)
        # Display-only framing guide; detection always uses original pixels.
        oval_width = min(source.width * .48, source.height * .55)
        oval_height = min(source.height * .80, source.width * .8)
        self.preview.create_oval(width / 2 - oval_width / 2, height / 2 - oval_height / 2, width / 2 + oval_width / 2, height / 2 + oval_height / 2, outline="#17bb99", width=3)
