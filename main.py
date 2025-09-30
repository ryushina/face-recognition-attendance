import tkinter as tk
from tkinter import ttk
from view import AppView


class AppModel:
    def __init__(self):
        self.data = "Hello, MVC with DI!"

class AppController:
    def __init__(self, model, view):
        self.model = model
        self.view = view

    def fetch_data(self):
        # Simulate data fetching
        self.model.data = "Data fetched from Model!"
        self.view.update_label(self.model.data)

class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("MVC Tkinter Example with DI")
        self.root.geometry("1200x600")  # Initial window size
        self.root.state('zoomed')  # Start maximized
        for c in range(12):
            self.root.columnconfigure(c, weight=1, uniform="cols")
        self.root.rowconfigure(0, weight=0)  # header
        self.root.rowconfigure(1, weight=1)  # main area expands
        self.root.rowconfigure(2, weight=0)  # footer
        # Dependency Injection
        model = AppModel()
        # Controller is injected into the View
        view = AppView(self.root, controller=None)
        controller = AppController(model, view)

        # Circular dependency fix
        view.controller = controller

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()