"""Staff-only password and record maintenance screens for the desktop kiosk."""

import tkinter as tk

import ttkbootstrap as tb


class StaffMaintenanceView:
    def staff_maintenance(self):
        if not self._navigate():
            return
        try:
            counts = self.controller.get_maintenance_counts()
        except Exception as exc:
            self.staff_note.configure(text=str(exc))
            return

        self._text("Staff maintenance", font=("Segoe UI", 19, "bold"))
        self._text(
            f"Current records: {counts['students']} students and "
            f"{counts['attendance']} attendance events."
        )
        self._text("Change the staff password used to unlock this area.")
        tb.Button(
            self.staff_content, text="Change staff password",
            command=self._change_staff_password, bootstyle="secondary-outline",
        ).pack(fill="x", pady=(0, 12))

        self._text("Clear attendance history", font=("Segoe UI", 15, "bold"))
        self._text(
            "This removes every saved check-in while keeping all student records and photos. "
            "You will need the current staff password to continue."
        )
        tb.Button(
            self.staff_content, text="Clear attendance history",
            command=lambda: self._show_sensitive_confirmation(
                title="Clear attendance history",
                warning=(f"This permanently deletes {counts['attendance']} attendance events. "
                         "Student records and photos stay in place."),
                required_text="CLEAR ATTENDANCE",
                operation=self.controller.clear_attendance_records,
                success=self._attendance_cleared,
                button_text="Clear attendance permanently",
            ), bootstyle="warning",
        ).pack(fill="x", pady=(0, 16))

        self._text("Reset all student records", font=("Segoe UI", 15, "bold"))
        self._text(
            "This removes every student, attendance event, and app-managed enrollment photo. "
            "It keeps the staff password, kiosk setup, backups, and exported files."
        )
        tb.Button(
            self.staff_content, text="Reset all student records",
            command=lambda: self._show_sensitive_confirmation(
                title="Reset all student records",
                warning=(f"This permanently deletes {counts['students']} student records, "
                         f"{counts['attendance']} attendance events, and their saved enrollment photos. "
                         "The staff password and kiosk setup remain."),
                required_text="RESET ALL RECORDS",
                operation=self.controller.reset_all_student_records,
                success=self._all_records_reset,
                button_text="Reset all records permanently",
            ), bootstyle="danger",
        ).pack(fill="x", pady=(0, 12))
        self.staff_note.configure(
            text="Sensitive actions require the current staff password and an exact confirmation phrase."
        )

    def _change_staff_password(self):
        self.access.require()
        window = tk.Toplevel(self.root)
        window.title("Change staff password")
        window.geometry("440x370")
        window.transient(self.root)
        self.windows.append(window)
        panel = tb.Frame(window, padding=22)
        panel.pack(fill="both", expand=True)
        tb.Label(panel, text="Change staff password", font=("Segoe UI", 17, "bold")).pack(anchor="w", pady=(0, 10))
        fields = []
        for label in ("Current password", "New password (10+ characters)", "Confirm new password"):
            tb.Label(panel, text=label).pack(anchor="w")
            entry = tb.Entry(panel, show="*")
            entry.pack(fill="x", pady=(2, 8))
            fields.append(entry)
        current, new, confirm = fields
        error = tb.Label(panel, text="The current password is required. Forgotten passwords need local administrator recovery.", wraplength=390, justify="left")
        error.pack(fill="x", pady=(2, 10))

        def submit():
            if new.get() != confirm.get():
                error.configure(text="The new passwords do not match.", bootstyle="danger")
                return
            try:
                self.controller.change_staff_password(current.get(), new.get())
            except Exception as exc:
                error.configure(text=str(exc), bootstyle="danger")
                return
            for entry in fields:
                entry.delete(0, "end")
            window.destroy()
            self.staff_note.configure(text="Staff password changed. Keep the new password with authorized staff.")

        tb.Button(panel, text="Save new password", command=submit, bootstyle="success").pack(fill="x")
        current.bind("<Return>", lambda _event: new.focus_set())
        new.bind("<Return>", lambda _event: confirm.focus_set())
        confirm.bind("<Return>", lambda _event: submit())
        def close():
            for entry in fields:
                if entry.winfo_exists():
                    entry.delete(0, "end")
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", close)
        window.grab_set()
        current.focus_set()

    def _show_sensitive_confirmation(
        self, *, title, warning, required_text, operation, success, button_text,
    ):
        self.access.require()
        window = tk.Toplevel(self.root)
        window.title(title)
        window.geometry("500x390")
        window.transient(self.root)
        self.windows.append(window)
        panel = tb.Frame(window, padding=22)
        panel.pack(fill="both", expand=True)
        tb.Label(panel, text=title, font=("Segoe UI", 17, "bold")).pack(anchor="w", pady=(0, 8))
        tb.Label(panel, text=warning, wraplength=450, justify="left", bootstyle="danger").pack(fill="x", pady=(0, 12))
        tb.Label(panel, text=f"Type {required_text} to confirm:").pack(anchor="w")
        phrase = tb.Entry(panel)
        phrase.pack(fill="x", pady=(2, 10))
        tb.Label(panel, text="Current staff password:").pack(anchor="w")
        password = tb.Entry(panel, show="*")
        password.pack(fill="x", pady=(2, 10))
        error = tb.Label(panel, text="This action cannot be undone from the app.", wraplength=450, justify="left")
        error.pack(fill="x", pady=(0, 10))

        def submit():
            if phrase.get().strip() != required_text:
                error.configure(text=f"Enter the exact phrase: {required_text}", bootstyle="danger")
                return
            try:
                result = operation(password.get())
            except Exception as exc:
                error.configure(text=str(exc), bootstyle="danger")
                password.delete(0, "end")
                password.focus_set()
                return
            phrase.delete(0, "end")
            password.delete(0, "end")
            window.destroy()
            success(result)

        buttons = tb.Frame(panel)
        buttons.pack(fill="x")
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)

        def close():
            if password.winfo_exists():
                password.delete(0, "end")
            window.destroy()

        tb.Button(buttons, text="Cancel", command=close, bootstyle="secondary-outline").grid(row=0, column=0, sticky="ew", padx=(0, 4))
        tb.Button(buttons, text=button_text, command=submit, bootstyle="danger").grid(row=0, column=1, sticky="ew", padx=(4, 0))
        window.protocol("WM_DELETE_WINDOW", close)
        window.grab_set()
        phrase.focus_set()

    def _attendance_cleared(self, count):
        self.staff_maintenance()
        self.staff_note.configure(text=f"Attendance history cleared. Deleted {count} events; student records remain.")

    def _all_records_reset(self, result):
        self.staff_maintenance()
        note = (f"All student records were reset: {result['students']} students, "
                f"{result['attendance']} attendance events, "
                f"{result['removed_photos']} managed photos removed. Kiosk setup and staff password remain.")
        if result["photo_cleanup_pending"]:
            note += f" {result['photo_cleanup_pending']} photo files need local cleanup."
        self.staff_note.configure(text=note)
