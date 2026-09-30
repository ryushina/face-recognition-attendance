import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
import cv2
from PIL import Image, ImageTk
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import ttkbootstrap as tb
from ttkbootstrap.constants import *
from ttkbootstrap.dialogs import Messagebox

# ------------------- VIEW -------------------
class AppView:
    def __init__(self, root, controller):
        self.controller = controller
        self.root = root
        # Configure root grid
        for c in range(12):
            root.columnconfigure(c, weight=1, uniform="cols", minsize=0)
        root.rowconfigure(0, weight=0)  # header
        root.rowconfigure(1, weight=1)  # main
        root.rowconfigure(2, weight=0)  # footer
        root.rowconfigure(3, weight=0)
        root.rowconfigure(4, weight=0)

        # HEADER
        self.header = tb.Label(
            root, text="Face detector: initializing", anchor="center"
        )
        self.header.grid(row=0, column=0, columnspan=12, sticky="nsew")

        # SIDEBAR
        self.sidebar = tb.Frame(root)
        self.sidebar.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=2, pady=2)

        self.btn_attendance = tb.Button(
            self.sidebar, text="Start Attendance", bootstyle=SUCCESS,
            command=self.on_login_click,
        )
        self.btn_attendance.pack(pady=(10, 5), padx=8, fill="x")
        self.btn_camera = tb.Button(
            self.sidebar, text="Start Camera", command=self.on_camera_click,
        )
        self.btn_camera.pack(pady=5, padx=8, fill="x")
        self.btn_history = tb.Button(
            self.sidebar, text="Attendance History", command=self.open_attendance_history,
        )
        self.btn_history.pack(pady=5, padx=8, fill="x")

        # MAIN CONTENT (Camera window)
        self.main_content = tb.Label(root, anchor="center")
        self.main_content.grid(row=1, column=3, columnspan=6, sticky="nsew", padx=2, pady=2)

        self.camera_status = tb.Label(
            root, text="Camera: waiting to start", anchor="center"
        )
        self.camera_status.grid(
            row=2, column=3, columnspan=6, sticky="ew", padx=2, pady=(0, 2)
        )
        self.identity_status = tb.Label(
            root, text="Recognition: waiting for camera", anchor="center"
        )
        self.identity_status.grid(
            row=3, column=3, columnspan=6, sticky="ew", padx=2, pady=(0, 2)
        )
        self.operator_status = tb.Label(root, text="", anchor="w")
        self.operator_status.grid(
            row=4, column=0, columnspan=12, sticky="ew", padx=6, pady=(0, 2)
        )

        # PROFILE (now holds registration form)
        self.profile = tb.Frame(root)
        self.profile.grid(row=1, column=9, columnspan=3, sticky="nsew", padx=2, pady=2)
        self.profile.columnconfigure(0, weight=1)
        self.profile.rowconfigure(0, weight=1)
        self.profile_canvas = tk.Canvas(self.profile, highlightthickness=0)
        self.profile_scrollbar = tb.Scrollbar(
            self.profile, orient="vertical", command=self.profile_canvas.yview
        )
        self.profile_canvas.configure(yscrollcommand=self.profile_scrollbar.set)
        self.profile_canvas.grid(row=0, column=0, sticky="nsew")
        self.profile_scrollbar.grid(row=0, column=1, sticky="ns")
        self.profile_content = tb.Frame(self.profile_canvas)
        self._profile_window = self.profile_canvas.create_window(
            (0, 0), window=self.profile_content, anchor="nw"
        )
        self.profile_content.bind("<Configure>", self._update_profile_scroll_region)
        self.profile_canvas.bind("<Configure>", self._resize_profile_content)
        self._build_profile_buttons(self.profile_content)

    def _build_profile_buttons(self,parent):
        for widget in parent.winfo_children():
            widget.destroy()
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)
        profile_button_container = tb.Frame(parent)
        profile_button_container.grid(row=0, column=0, sticky="nsew")
        profile_button_container.columnconfigure(0, weight=1)
        btn_register_student = tb.Button(
            profile_button_container,
            text="Register Student",
            bootstyle=SUCCESS,
            command=lambda: self._show_register_student_form(self.profile_content)
        )
        btn_register_student.grid(row=0,column=0,sticky="ew",padx=8,pady=8)
        btn_register_teacher = tb.Button(
            profile_button_container,
            text="Teacher registration unavailable",
            state="disabled",
        )
        btn_register_teacher.grid(row=1, column=0, sticky="ew", padx=8, pady=8)
        profile_button_container.rowconfigure(0, weight=0)
        profile_button_container.rowconfigure(1, weight=0)
        profile_button_container.rowconfigure(2, weight=1)

        return profile_button_container

    def _update_profile_scroll_region(self, _event=None):
        self.profile_canvas.configure(scrollregion=self.profile_canvas.bbox("all"))

    def _resize_profile_content(self, event):
        self.profile_canvas.itemconfigure(self._profile_window, width=event.width)

    def _show_register_student_form(self, parent):
        if self.controller:
            self.controller.begin_enrollment()
        # Clear parent
        for widget in parent.winfo_children():
            widget.destroy()

        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        # ---- Container frame ----
        self.register_student_form = tb.Frame(parent, padding=15)
        self.register_student_form.grid(row=0, column=0, sticky="nsew")
        self.register_student_form.columnconfigure(0, weight=1)

        # ---- Heading ----
        self.lbl_heading = tb.Label(
            self.register_student_form,
            text="Student Registration Form",
            font=("Segoe UI", 14, "bold"),
            bootstyle="inverse-primary",
            anchor="center",
            padding=(6, 8)
        )
        self.lbl_heading.grid(row=0, column=0, pady=(0, 12), sticky="ew")

        # ---- Fields ----
        self.lbl_lrn = tb.Label(self.register_student_form, text="LRN:")
        self.lbl_lrn.grid(row=1, column=0, pady=(6, 0), sticky="w")
        self.entry_lrn = tb.Entry(self.register_student_form)
        self.entry_lrn.grid(row=2, column=0, pady=(0, 6), sticky="ew")
        self.entry_lrn.bind("<KeyRelease>", self._on_enrollment_form_change)

        self.lbl_firstname = tb.Label(self.register_student_form, text="First Name:")
        self.lbl_firstname.grid(row=3, column=0, pady=(6, 0), sticky="w")
        self.entry_firstname = tb.Entry(self.register_student_form)
        self.entry_firstname.grid(row=4, column=0, pady=(0, 6), sticky="ew")

        self.lbl_middlename = tb.Label(self.register_student_form, text="Middle Name:")
        self.lbl_middlename.grid(row=5, column=0, pady=(6, 0), sticky="w")
        self.entry_middlename = tb.Entry(self.register_student_form)
        self.entry_middlename.grid(row=6, column=0, pady=(0, 6), sticky="ew")

        self.lbl_lastname = tb.Label(self.register_student_form, text="Last Name:")
        self.lbl_lastname.grid(row=7, column=0, pady=(6, 0), sticky="w")
        self.entry_lastname = tb.Entry(self.register_student_form)
        self.entry_lastname.grid(row=8, column=0, pady=(0, 6), sticky="ew")

        self.lbl_guardian_fullname = tb.Label(self.register_student_form, text="Guardian Full Name:")
        self.lbl_guardian_fullname.grid(row=9, column=0, pady=(6, 0), sticky="w")
        self.entry_guardian_fullname = tb.Entry(self.register_student_form)
        self.entry_guardian_fullname.grid(row=10, column=0, pady=(0, 6), sticky="ew")

        self.lbl_guardian_phone = tb.Label(self.register_student_form, text="Guardian Phone Number:")
        self.lbl_guardian_phone.grid(row=11, column=0, pady=(6, 0), sticky="w")
        self.entry_guardian_phone = tb.Entry(self.register_student_form)
        self.entry_guardian_phone.grid(row=12, column=0, pady=(0, 6), sticky="ew")

        self.btn_capture = tb.Button(
            self.register_student_form,
            text="Capture Image",
            bootstyle="success",
            command=self.on_capture_image
        )
        self.btn_capture.grid(row=13, column=0, pady=(10, 4), sticky="ew")

        self.capture_status = tb.Label(
            self.register_student_form,
            text="Accepted captures: 0 — vary pose and lighting",
        )
        self.capture_status.grid(row=14, column=0, sticky="ew")

        self.btn_submit = tb.Button(
            self.register_student_form,
            text="Submit",
            bootstyle="success",
            command=self.on_submit
        )
        self.btn_submit.grid(row=15, column=0, pady=(10, 4), sticky="ew")

        self.btn_cancel = tb.Button(self.register_student_form, text="Cancel", bootstyle="secondary",
                                    command=self.on_cancel)
        self.btn_cancel.grid(row=16, column=0, pady=(0, 0), sticky="ew")
        for i in range(17):
            self.register_student_form.rowconfigure(i, weight=0)
        self.register_student_form.rowconfigure(16, weight=1)

        return self.register_student_form
    def _collect_student_form_data(self):
        return {
            "user_id": self.entry_lrn.get().strip(),
            "first_name": self.entry_firstname.get().strip(),
            "middle_name": self.entry_middlename.get().strip(),
            "last_name": self.entry_lastname.get().strip(),
            "guardian_fullname": self.entry_guardian_fullname.get().strip(),
            "guardian_phone": self.entry_guardian_phone.get().strip(),
        }

    def on_capture_image(self):
        if not self.controller:
            return
        payload = self._collect_student_form_data()
        success, message = self.controller.handle_capture_image(payload)
        session = self.controller.enrollment_session
        count = session.accepted_count if session else 0
        status = f"Accepted captures: {count} — vary pose and lighting"
        if not success:
            status += f" — Capture error: {message}"
        self.capture_status.configure(text=status)

    def _on_enrollment_form_change(self, _event=None):
        if self.controller:
            self.controller.update_enrollment_details(self._collect_student_form_data())

    def on_submit(self):
        if not self.controller:
            return
        success, message = self.controller.handle_register(
            self._collect_student_form_data()
        )
        if success:
            Messagebox.show_info("Student Registered", message)
            self.operator_status.configure(text="Enrollment saved; recognition indexing is pending.")
            self.on_cancel()
        else:
            self.capture_status.configure(text=message)
            Messagebox.show_warning("Registration Not Saved", message)

    def on_cancel(self):
        if self.controller:
            self.controller.cancel_enrollment()
        self._build_profile_buttons(self.profile_content)

    def on_register_submit(self):
        pass

    def on_login_click(self):
        """Toggle the explicit daily attendance mode."""
        if self.controller:
            self.controller.toggle_attendance()

    def on_camera_click(self):
        if self.controller:
            self.controller.toggle_camera()

    def update_attendance_mode(self, active, message):
        self.btn_attendance.configure(
            text="Pause Attendance" if active else "Start Attendance",
            bootstyle="danger" if active else SUCCESS,
        )
        self.operator_status.configure(text=message)

    def update_attendance_progress(self, count, required, result):
        if result is not None and getattr(result, "status", None) == "recognized":
            self.operator_status.configure(
                text=f"Hold still for attendance: {count}/{required} distinct frames."
            )

    def update_attendance_result(self, attendance, display_name):
        if attendance.status == "recorded":
            message = (
                f"Attendance recorded for {display_name} on "
                f"{attendance.attendance_date} ({attendance.timezone_name})."
            )
        else:
            message = (
                f"{display_name} was already recorded on "
                f"{attendance.attendance_date}."
            )
        self.operator_status.configure(text=message)

    def update_operator_status(self, message):
        self.operator_status.configure(text=message)

    def open_attendance_history(self):
        window = tk.Toplevel(self.root)
        window.title("Attendance History")
        window.geometry("720x430")
        window.minsize(600, 330)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)

        filters = tb.Frame(window, padding=8)
        filters.grid(row=0, column=0, sticky="ew")
        date_value = ""
        timezone_name = getattr(
            getattr(self.controller, "config", None), "attendance_timezone", None
        )
        if timezone_name:
            try:
                date_value = datetime.now(ZoneInfo(timezone_name)).date().isoformat()
            except (ZoneInfoNotFoundError, ValueError):
                pass
        tb.Label(filters, text="Local date (YYYY-MM-DD)").grid(row=0, column=0, padx=4)
        date_entry = tb.Entry(filters, width=14)
        date_entry.insert(0, date_value)
        date_entry.grid(row=0, column=1, padx=4)
        tb.Label(filters, text="Student ID").grid(row=0, column=2, padx=4)
        student_entry = tb.Entry(filters, width=14)
        student_entry.grid(row=0, column=3, padx=4)

        table_frame = tb.Frame(window, padding=(8, 0, 8, 4))
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        columns = ("date", "time", "student_id", "student_name", "similarity")
        table = ttk.Treeview(table_frame, columns=columns, show="headings")
        for column, title, width in (
            ("date", "Local date", 95), ("time", "Local time", 160),
            ("student_id", "Student ID", 100), ("student_name", "Student", 180),
            ("similarity", "Similarity", 90),
        ):
            table.heading(column, text=title)
            table.column(column, width=width, anchor="w")
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=table.yview)
        table.configure(yscrollcommand=scrollbar.set)
        table.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        status = tb.Label(window, text="", anchor="w")
        status.grid(row=2, column=0, sticky="ew", padx=8)

        def current_filter():
            return date_entry.get().strip() or None, student_entry.get().strip() or None

        def refresh():
            for item in table.get_children():
                table.delete(item)
            try:
                selected_date, selected_id = current_filter()
                records = self.controller.get_attendance_history(selected_date, selected_id)
                for record in records:
                    table.insert("", "end", values=(
                        record.attendance_date, record.occurred_at_local,
                        record.student_id, record.student_name,
                        f"{record.similarity:.3f}",
                    ))
                status.configure(text=f"{len(records)} attendance record(s).")
            except Exception as exc:
                status.configure(text=f"Could not load attendance history: {exc}")

        def export():
            destination = filedialog.asksaveasfilename(
                parent=window, title="Export attendance", defaultextension=".csv",
                filetypes=(("CSV files", "*.csv"), ("All files", "*.*")),
            )
            if not destination:
                return
            try:
                selected_date, selected_id = current_filter()
                path = self.controller.export_attendance_history(
                    destination, selected_date, selected_id
                )
                status.configure(text=f"Exported attendance to {path}")
            except Exception as exc:
                status.configure(text=f"Could not export attendance: {exc}")

        actions = tb.Frame(window, padding=8)
        actions.grid(row=3, column=0, sticky="ew")
        tb.Button(actions, text="Refresh", command=refresh).pack(side="left", padx=(0, 6))
        tb.Button(actions, text="Export CSV", command=export).pack(side="left")
        refresh()
        return window

    def update_detector_status(self, message):
        """Show the active face detector and any fallback explanation."""
        self.header.configure(text=message)

    def update_camera_status(self, message):
        """Show camera startup, running, stopped, or error status."""
        self.camera_status.configure(text=f"Camera: {message}")
        camera_service = getattr(self.controller, "camera_service", None)
        if camera_service is None:
            self.btn_camera.configure(text="Camera unavailable", state="disabled")
        else:
            running = getattr(camera_service, "running", False)
            self.btn_camera.configure(
                text="Stop Camera" if running else "Start Camera", state="normal"
            )

    def update_identity_status(self, result):
        if result is None:
            message = "Recognition: waiting for camera"
        elif result.status == "recognized":
            score = "" if result.score is None else f" (similarity {result.score:.3f})"
            message = f"Recognized: {result.display_name or result.student_id}{score}"
        elif result.status == "ambiguous":
            message = "Recognition: ambiguous — " + (result.message or "multiple candidates")
        elif result.status == "unknown":
            message = "Recognition: unknown — " + (result.message or "no matching student")
        else:
            message = "Recognition: error — " + (getattr(result, "message", "unavailable"))
        self.identity_status.configure(text=message)

    def update_enrollment_status(self, result):
        if result.error:
            message = f"Indexing failed for {result.student_id}: {result.error}"
        else:
            message = (
                f"Student {result.student_id} recognition ready; "
                f"indexed {result.indexed_samples} sample(s)."
            )
        self.operator_status.configure(text=message)

    # ------------------- Camera Update -------------------
    def update_camera_frame(self, frame_bgr):
        """Display a camera frame inside the main_content."""
        if frame_bgr is None:
            self.main_content.configure(image="")
            self.main_content.imgtk = None
            return

        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb)

        # Resize to fit container
        w = self.main_content.winfo_width() or 640
        h = self.main_content.winfo_height() or 480
        img.thumbnail((w, h), Image.Resampling.LANCZOS)
        imgtk = ImageTk.PhotoImage(image=img)
        self.main_content.imgtk = imgtk  # prevent garbage collection
        self.main_content.configure(image=imgtk)
