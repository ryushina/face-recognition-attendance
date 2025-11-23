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
from view import AppView
import ttkbootstrap as tb
from ttkbootstrap.constants import *
from ttkbootstrap import Style
import cv2, time, threading, os
from datetime import datetime
from camera_service import CameraService
# ------------------- MODEL -------------------
class AppModel:
    def __init__(self):
        self.data = "Hello, MVC with DI!"


# ------------------- VIEW -------------------


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

    @staticmethod
    def _slugify_segment(value: str, fallback: str) -> str:
        """Return a filesystem-friendly, lowercase string."""
        value = (value or "").strip()
        if not value:
            value = fallback
        value = value.replace(" ", "_")
        cleaned = "".join(ch for ch in value if ch.isalnum() or ch in ("-", "_"))
        cleaned = cleaned.strip("_-").lower()
        return cleaned or fallback

    def handle_capture_image(self, payload: dict):
        """
        Capture the current student's face image into assets/<student_folder>.
        """
        if not isinstance(payload, dict):
            return False, "Invalid data supplied."

        lrn = payload.get("user_id", "").strip()
        first_name = payload.get("first_name", "").strip()
        last_name = payload.get("last_name", "").strip()

        if not lrn:
            return False, "LRN is required before capturing an image."

        folder_parts = [
            self._slugify_segment(lrn, "student"),
            self._slugify_segment(first_name, "") if first_name else "",
            self._slugify_segment(last_name, "") if last_name else "",
        ]
        folder_parts = [part for part in folder_parts if part]
        folder_name = "_".join(folder_parts) or "student"

        assets_root = "assets"
        try:
            os.makedirs(assets_root, exist_ok=True)
        except Exception as e:
            return False, f"Unable to create assets directory: {e}"

        student_dir = os.path.join(assets_root, folder_name)

        filename_prefix = self._slugify_segment(first_name or lrn, "face")
        success, result = self.camera_service.capture_face(student_dir, filename_prefix=filename_prefix)
        if success:
            payload["photo_dir"] = student_dir
            return True, f"Image saved to {result}"
        return False, result

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
