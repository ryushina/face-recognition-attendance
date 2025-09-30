import tkinter as tk
from tkinter import ttk

class AppView:
    def __init__(self, root, controller):
        self.controller = controller
        self.header=ttk.Label(root, text="HEADER", background="lightblue", anchor="center").grid(
    row=0, column=0, columnspan=12, sticky="nsew"
)

# MAIN CONTENT: Sidebar + Main Content + Profile
        self.sidebar = ttk.Label(root, text="SIDEBAR", background="lightgreen").grid(
    row=1, column=0, columnspan=3, sticky="nsew", padx=2, pady=2
)
        self.main_content=ttk.Label(root, text="MAIN CONTENT", background="lightyellow").grid(
    row=1, column=3, columnspan=6, sticky="nsew", padx=2, pady=2
)
        self.profile=ttk.Label(root, text="PROFILE", background="lightpink").grid(
    row=1, column=9, columnspan=3, sticky="nsew", padx=2, pady=2
)

# FOOTER
        self.footer=ttk.Label(root, text="FOOTER", background="lightgray", anchor="center").grid(
    row=2, column=0, columnspan=12, sticky="nsew"
)

    def on_button_click(self):
        self.controller.fetch_data()

    def update_label(self, text):
        self.label.config(text=text)
