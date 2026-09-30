"""Staff student list, editing form, and saved-photo review for the kiosk."""

from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from PIL import Image, ImageTk
import ttkbootstrap as tb


class StudentRecordsView:
    def _student_details_dirty(self):
        entries = getattr(self, "_student_entries", {})
        original = getattr(self, "_student_original", {})
        return bool(entries) and any(entry.get().strip() != original.get(key, "") for key, entry in entries.items())

    def _confirm_student_navigation(self):
        if self._student_details_dirty() and not messagebox.askyesno(
            "Discard detail edits?", "Leave this student without saving your detail edits?", parent=self.root):
            return False
        session = self.controller.enrollment_session
        return not (session and not session.submitted) or messagebox.askyesno(
            "Discard enrollment draft?", "Leave this enrollment and discard its unsaved photos and details?", parent=self.root)

    def student_records(self):
        if not self._navigate():
            return
        try:
            students = self.controller.list_student_records()
        except Exception as exc:
            self.staff_note.configure(text=str(exc))
            return
        self._text("Student records", font=("Segoe UI", 19, "bold"))
        self._text(f"{len(students)} saved students. Search by name or LRN, then open a record.")
        search = tb.Entry(self.staff_content)
        search.pack(fill="x", pady=(0, 8))
        table_frame = tb.Frame(self.staff_content)
        table_frame.pack(fill="x")
        table_frame.columnconfigure(0, weight=1)
        table = tb.Treeview(table_frame, columns=("lrn", "status"), show="tree headings", height=5)
        table.heading("#0", text="Name")
        table.heading("lrn", text="LRN")
        table.heading("status", text="Preparation")
        table.column("#0", width=110, minwidth=70)
        table.column("lrn", width=75, minwidth=50)
        table.column("status", width=90, minwidth=70)
        scrollbar = tb.Scrollbar(table_frame, orient="vertical", command=table.yview)
        table.configure(yscrollcommand=scrollbar.set)
        table.grid(row=0, column=0, sticky="ew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._student_table = table
        ids = {}

        def populate(_event=None):
            table.delete(*table.get_children())
            ids.clear()
            query = search.get().strip().casefold()
            for index, student in enumerate(students):
                name = " ".join(filter(None, (student.first_name, student.middle_name, student.last_name)))
                if query and query not in f"{name} {student.student_id}".casefold():
                    continue
                key = str(index)
                ids[key] = student.student_id
                table.insert("", "end", iid=key, text=name, values=(student.student_id, student.enrollment_status))

        def open_selected(_event=None):
            selected = table.selection()
            if selected:
                self.open_student_record(ids[selected[0]])
            else:
                self.staff_note.configure(text="Select a student from the list first.")

        search.bind("<KeyRelease>", populate)
        table.bind("<Double-1>", open_selected)
        table.bind("<Return>", open_selected)
        populate()
        tb.Button(self.staff_content, text="Open selected student", command=open_selected, bootstyle="success").pack(fill="x", pady=8)
        tb.Button(self.staff_content, text="Enroll new student", command=self.begin_enrollment).pack(fill="x", pady=4)
        self.staff_note.configure(text="Student records and photos are visible only while staff access is unlocked.")

    def open_student_record(self, student_id):
        if not self._navigate():
            return
        try:
            student = self.controller.get_student_record(student_id)
            self._render_student_record(student)
        except Exception as exc:
            self.staff_note.configure(text=str(exc))

    def _render_student_record(self, student):
        self._clear_content()
        self._editing_student_id = student.student_id
        self._student_original = self.controller.student_form_details(student)
        self._student_entries = {}
        self._text("Edit student", font=("Segoe UI", 19, "bold"))
        self._text(f"Recognition preparation: {student.enrollment_status}\nSaved photos: {len(student.samples)}")
        if student.enrollment_error:
            self._text(student.enrollment_error, bootstyle="danger")
        self._text("Fields marked * are required. LRN corrections keep this student's attendance linked to the record.")
        for key, label in (("user_id", "LRN *"), ("first_name", "First name *"), ("middle_name", "Middle name"),
                           ("last_name", "Last name *"), ("guardian_fullname", "Guardian full name"), ("guardian_phone", "Guardian phone")):
            self._text(label)
            entry = tb.Entry(self.staff_content)
            entry.insert(0, self._student_original[key])
            entry.pack(fill="x", pady=(0, 8))
            self._student_entries[key] = entry
        tb.Button(self.staff_content, text="Save student details", command=self.save_student_details, bootstyle="success").pack(fill="x", pady=8)
        self._text("Saved face photos", font=("Segoe UI", 17, "bold"))
        self._text("Check that every photo shows the correct student. Image checks cover face size, blur, lighting, and model processing; they do not guarantee a live match.")
        tb.Button(self.staff_content, text="Check photo quality", command=self.check_student_photos).pack(fill="x", pady=6)
        for number, sample in enumerate(student.samples, 1):
            self._text(f"Photo {number}", font=("Segoe UI", 13, "bold"))
            path = self._sample_path(sample)
            try:
                with Image.open(path) as source:
                    thumbnail = source.copy()
                thumbnail.thumbnail((180, 130))
                photo = ImageTk.PhotoImage(thumbnail)
                self._thumbs.append(photo)
                tb.Label(self.staff_content, image=photo).pack(anchor="w", pady=4)
                tb.Button(self.staff_content, text=f"View photo {number}", bootstyle="secondary-outline",
                          command=lambda saved=sample: self.open_saved_photo(saved)).pack(anchor="w", pady=4)
            except (OSError, ValueError):
                self._text("Photo preview unavailable. Check quality for details.", bootstyle="warning")
            self._photo_review_labels[sample.sample_id] = self._text("Not checked in this session.")
        tb.Button(self.staff_content, text="Retake face photos", command=lambda: self.retake_student_photos(student.student_id)).pack(fill="x", pady=8)
        tb.Button(self.staff_content, text="Test live recognition", command=self.diagnostics).pack(fill="x", pady=4)
        tb.Button(self.staff_content, text="Back to student list", command=self.student_records, bootstyle="secondary-outline").pack(fill="x", pady=4)
        self.staff_note.configure(text="Save detail edits before leaving. Use Check photo quality to assess saved images.")

    def save_student_details(self):
        self.access.require()
        values = {key: entry.get().strip() for key, entry in self._student_entries.items()}
        original_id = self._editing_student_id
        if values["user_id"] != original_id and not messagebox.askyesno(
            "Correct this student's LRN?", f"Change LRN {original_id} to {values['user_id']}? Existing attendance will remain linked to this student.", parent=self.root):
            return
        try:
            student = self.controller.update_student_record(original_id, values)
            self._render_student_record(student)
            self.staff_note.configure(text="Student details saved. Attendance history is preserved.")
        except Exception as exc:
            self.staff_note.configure(text=str(exc))

    def check_student_photos(self):
        self.access.require()
        try:
            started = self.controller.review_student_photos(self._editing_student_id)
            if started:
                for label in self._photo_review_labels.values():
                    label.configure(text="Checking image...", bootstyle="secondary")
                self.staff_note.configure(text="Checking saved photos. Attendance remains paused.")
            else:
                self.staff_note.configure(text="A photo check is already running. Wait, then try again.")
        except Exception as exc:
            self.staff_note.configure(text=str(exc))

    def update_photo_review(self, result):
        if not (self.staff_mode and self.access.unlocked and result.student_id == self._editing_student_id):
            return
        if {check.sample_id for check in result.checks} != set(self._photo_review_labels):
            return
        for check in result.checks:
            style = {"pass": "success", "replace": "danger", "unchecked": "warning"}[check.status]
            self._photo_review_labels[check.sample_id].configure(text=check.message, bootstyle=style)
        passed = sum(check.status == "pass" for check in result.checks)
        self.staff_note.configure(text=f"{passed} of {len(result.checks)} photos pass current checks. Review the results below; test a fresh live scan next.")

    def retake_student_photos(self, student_id):
        if not self._navigate():
            return
        try:
            self.controller.begin_photo_replacement(student_id)
            self.pending_student = None
            self._enrollment_photos()
            self.staff_note.configure(text="Capture three new photos. The saved photo set changes only when you review and save.")
        except Exception as exc:
            self.staff_note.configure(text=str(exc))

    def _sample_path(self, sample):
        path = Path(sample.image_path)
        return path if path.is_absolute() else self.controller.config.data_dir / path

    def open_saved_photo(self, sample):
        self.access.require()
        try:
            with Image.open(self._sample_path(sample)) as source:
                photo = source.copy()
            photo.thumbnail((640, 480))
            window = tk.Toplevel(self.root)
            window.title("Enrolled photo - staff only")
            window.transient(self.root)
            window._photo = ImageTk.PhotoImage(photo)
            tb.Label(window, image=window._photo).pack(padx=12, pady=12)
            tb.Button(window, text="Close", command=window.destroy).pack(pady=(0, 12))
            self.windows.append(window)
        except (OSError, ValueError) as exc:
            self.staff_note.configure(text=f"Could not open photo: {exc}")
