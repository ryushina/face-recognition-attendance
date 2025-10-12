import tkinter as tk
from tkinter import ttk
import cv2
from PIL import Image, ImageTk
import threading
import time
from datetime import datetime
import os
import csv
from ultralytics import YOLO
import ttkbootstrap as tb
from ttkbootstrap.constants import *
from ttkbootstrap import Style
from ttkbootstrap.widgets import Button

import cv2, time, threading, os
from datetime import datetime
from camera_service import CameraService
# ------------------- MODEL -------------------
class AppModel:
    def __init__(self):
        self.data = "Hello, MVC with DI!"


# ------------------- VIEW -------------------
class AppView:
    def __init__(self, root, controller):
        self.controller = controller
        self.root = root
        # Configure root grid
        for c in range(12):
            root.columnconfigure(c, weight=1, uniform="cols", minsize=100)
        root.rowconfigure(0, weight=0)  # header
        root.rowconfigure(1, weight=1)  # main
        root.rowconfigure(2, weight=0)  # footer

        # HEADER
        self.header = tb.Label(root, text="HEADER", anchor="center")
        self.header.grid(row=0, column=0, columnspan=12, sticky="nsew")

        # SIDEBAR
        self.sidebar = tb.Frame(root)
        self.sidebar.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=2, pady=2)

        # Login Button (Register button removed per request)
        self.btn_login = tb.Button(self.sidebar, text="Login", command=self.on_login_click)
        self.btn_login.pack(pady=10, padx=10, fill="x")

        # MAIN CONTENT (Camera window)
        self.main_content = tb.Label(root)
        self.main_content.grid(row=1, column=3, columnspan=6, sticky="nsew", padx=2, pady=2)

        # PROFILE (now holds registration form)
        self.profile = tb.Frame(root)
        self.profile.grid(row=1, column=9, columnspan=3, sticky="nsew", padx=2, pady=2)
        self.profile.columnconfigure(0, weight=1)
        self._build_profile_buttons(self.profile)

    def _build_profile_buttons(self,parent):
        for widget in self.profile.winfo_children():
            widget.destroy()
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)
        profile_button_container = tb.Frame(parent)
        profile_button_container.grid(row=0, column=0, sticky="nsew")
        profile_button_container.columnconfigure(0, weight=1)
        btn_register_student = Button(
            profile_button_container,
            text="Register Student",
            bootstyle=SUCCESS,
            command=lambda: self._show_register_student_form(self.profile)
        )
        btn_register_student.grid(row=0,column=0,sticky="ew",padx=8,pady=8)
        btn_register_teacher = Button(
            profile_button_container,
            text="Register Teacher",
#command=lambda: self._show_register_student_form(self.profile)
        )
        btn_register_teacher.grid(row=1, column=0, sticky="ew", padx=8, pady=8)
        profile_button_container.rowconfigure(0, weight=0)
        profile_button_container.rowconfigure(1, weight=0)
        profile_button_container.rowconfigure(2, weight=1)

        return profile_button_container

    def _show_register_student_form(self, parent):
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

        # ---- Buttons ----
        self.btn_submit = tb.Button(self.register_student_form, text="Submit", bootstyle="success",
                                    command=self.on_submit)
        self.btn_submit.grid(row=13, column=0, pady=(10, 4), sticky="ew")

        self.btn_cancel = tb.Button(self.register_student_form, text="Cancel", bootstyle="secondary",
                                    command=self.on_cancel)
        self.btn_cancel.grid(row=14, column=0, pady=(0, 0), sticky="ew")
        for i in range(15):  # rows 0 to 14 = content rows
            self.register_student_form.rowconfigure(i, weight=0)
        self.register_student_form.rowconfigure(15, weight=1)

        return self.register_student_form

    def on_register_submit(self):
        pass

    def on_login_click(self):
        """Handles login button click and logs data to log.txt"""
        if self.controller:
            self.controller.handle_login()

    # ------------------- Camera Update -------------------
    def update_camera_frame(self, frame_bgr):
        """Display a camera frame inside the main_content."""
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb)

        # Resize to fit container
        w = self.main_content.winfo_width() or 640
        h = self.main_content.winfo_height() or 480
        img = img.resize((w, h))
        imgtk = ImageTk.PhotoImage(image=img)
        self.main_content.imgtk = imgtk  # prevent garbage collection
        self.main_content.configure(image=imgtk)


class AppController:
    def __init__(self, model, view, camera_service):
        self.model = model
        self.view = view
        self.camera_service = camera_service

        # ensure users.txt exists with header
        self._ensure_users_file()

    def fetch_data(self):
        self.model.data = "Data fetched from Model!"
        print(self.model.data)

    def start_camera(self):
        self.camera_service.start()

    def stop_camera(self):
        self.camera_service.stop()

    def handle_login(self):
        """Logs current time and a dummy person to log.txt"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        name = "Rustan C. Lacanilo"
        log_entry = f"{current_time} - {name}\n"
        with open("log.txt", "a", encoding="utf-8") as log_file:
            log_file.write(log_entry)
        print(f"Login recorded: {log_entry.strip()}")

    # ---------- Registration ----------
    def _ensure_users_file(self):
        path = "users.txt"
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["user_id", "first_name", "last_name", "photo_dir"])  # header

    def handle_register(self, payload: dict):
        """
        Append a dummy user record to users.txt
        CSV columns: user_id, first_name, last_name, photo_dir
        """
        user_id = payload.get("user_id", "").strip()
        first_name = payload.get("first_name", "").strip()
        last_name = payload.get("last_name", "").strip()
        photo_dir = payload.get("photo_dir", "").strip()

        # basic validation
        if not user_id:
            return False, "User ID is required."
        if not first_name or not last_name:
            return False, "First and Last Name are required."
        if not photo_dir:
            return False, "Photo directory is required."

        try:
            with open("users.txt", "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([user_id, first_name, last_name, photo_dir])
            return True, f"Registered: {user_id} - {first_name} {last_name}"
        except Exception as e:
            return False, f"Failed to register: {e}"


# ------------------- MAIN APP -------------------
class App:
    def __init__(self):
        self.root = tb.Window(themename="flatly")
        self.root.title("MVC with Camera Face Detection")
        self.root.geometry("1200x600")
        try:
            self.root.state('zoomed')
        except tk.TclError:
            pass

        model = AppModel()
        view = AppView(self.root, controller=None)
        camera_service = CameraService(view)
        controller = AppController(model, view, camera_service)
        view.controller = controller

        self.root.after(200, controller.start_camera)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.controller = controller

    def on_close(self):
        self.controller.stop_camera()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
