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

        # Configure root grid
        for c in range(12):
            root.columnconfigure(c, weight=1, uniform="cols")
        root.rowconfigure(0, weight=0)  # header
        root.rowconfigure(1, weight=1)  # main
        root.rowconfigure(2, weight=0)  # footer

        # HEADER
        self.header = tk.Label(root, text="HEADER", bg="lightblue", anchor="center")
        self.header.grid(row=0, column=0, columnspan=12, sticky="nsew")

        # SIDEBAR
        self.sidebar = tk.Frame(root, bg="lightgreen")
        self.sidebar.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=2, pady=2)

        # Login Button (Register button removed per request)
        self.btn_login = ttk.Button(self.sidebar, text="Login", command=self.on_login_click)
        self.btn_login.pack(pady=10, padx=10, fill="x")

        # MAIN CONTENT (Camera window)
        self.main_content = tk.Label(root, bg="black")
        self.main_content.grid(row=1, column=3, columnspan=4, sticky="nsew", padx=2, pady=2)

        # PROFILE (now holds registration form)
        self.profile = tk.Frame(root, bg="lightpink")
        self.profile.grid(row=1, column=7, columnspan=5, sticky="nsew", padx=2, pady=2)

        self._build_registration_form(self.profile)

        # FOOTER
        self.footer = tk.Label(root, text="FOOTER", bg="lightgray", anchor="center")
        self.footer.grid(row=2, column=0, columnspan=12, sticky="nsew")

    # ------------------- UI Builders -------------------
    def _build_registration_form(self, parent):
        # Title
        title = tk.Label(parent, text="Register User", bg="lightpink", font=("Segoe UI", 11, "bold"))
        title.pack(padx=10, pady=(10, 6), anchor="w")

        form = tk.Frame(parent, bg="lightpink")
        form.pack(fill="x", padx=10)

        # User ID
        tk.Label(form, text="User ID:", bg="lightpink").grid(row=0, column=0, sticky="w")
        self.entry_user_id = ttk.Entry(form)
        self.entry_user_id.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=4)

        # First Name
        tk.Label(form, text="First Name:", bg="lightpink").grid(row=1, column=0, sticky="w")
        self.entry_first_name = ttk.Entry(form)
        self.entry_first_name.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=4)

        # Middle Name
        tk.Label(form, text="First Name:", bg="lightpink").grid(row=2, column=0, sticky="w")
        self.entry_middle_name = ttk.Entry(form)
        self.entry_middle_name.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=4)

        # Last Name
        tk.Label(form, text="Last Name:", bg="lightpink").grid(row=3, column=0, sticky="w")
        self.entry_last_name = ttk.Entry(form)
        self.entry_last_name.grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=4)


        # Make second column stretch
        #form.columnconfigure(1, weight=1)

        # Register Button
        self.btn_register_profile = ttk.Button(
            parent,
            text="Register",
            command=self.on_register_submit
        )
        self.btn_register_profile.pack(padx=10, pady=10, fill="x")

        # Status label
        self.register_status = tk.Label(parent, text="", bg="lightpink", fg="darkgreen", anchor="w", justify="left")
        self.register_status.pack(fill="x", padx=10, pady=(0, 10))

    # ------------------- Button Handlers -------------------
    def on_register_submit(self):
        """Collects form fields and delegates to controller to persist."""
        if not self.controller:
            return
        payload = {
            "user_id": self.entry_user_id.get().strip(),
            "first_name": self.entry_first_name.get().strip(),
            "last_name": self.entry_last_name.get().strip(),
            "photo_dir": self.entry_photo_dir.get().strip(),
        }
        ok, msg = self.controller.handle_register(payload)
        self.register_status.configure(text=msg, fg=("darkgreen" if ok else "darkred"))

        if ok:
            # Clear fields except photo_dir (keep as template)
            self.entry_user_id.delete(0, tk.END)
            self.entry_first_name.delete(0, tk.END)
            self.entry_last_name.delete(0, tk.END)

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


# ------------------- CONTROLLER -------------------
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
        self.root = tk.Tk()
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

        # Start camera after window is ready
        self.root.after(200, controller.start_camera)

        # Ensure proper shutdown
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.controller = controller

    def on_close(self):
        self.controller.stop_camera()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
