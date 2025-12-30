"""
Fully self-contained version of the ScanOT2 main application.

Use this exact file content when you need a clean copy of the app (for example
when rebuilding the executable on another PC). The code resolves resources at
runtime with `resource_path` so it will work both in development and in the
PyInstaller-built EXE without any hard-coded machine-specific paths.
"""

import logging
import os
import shutil
import sys
import threading
from pathlib import Path
import customtkinter as ctk
import time
import cv2
import pyautogui
from datetime import datetime
import numpy as np
import mss
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import subprocess
import ast
from tqdm import tqdm
from tkinter import messagebox, filedialog, PhotoImage
from pystray import Icon, MenuItem, Menu
from PIL import Image
IS_FROZEN = getattr(sys, "frozen", False)
RESOURCE_BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
APP_DIR = Path(sys.executable).resolve().parent if IS_FROZEN else Path(__file__).resolve().parent
LOG_FILE = APP_DIR / "mainApp.log"


def setup_logging() -> None:
    """Log to a file beside the executable to capture startup/runtime errors when windowed."""
    try:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
        )
    except Exception:
        # Fall back quietly if the log file cannot be created
        logging.basicConfig(level=logging.INFO)
    logging.info("Logging initialized. Frozen=%s, app dir=%s, resource base=%s", IS_FROZEN, APP_DIR, RESOURCE_BASE)


def resource_path(*parts: str) -> Path:
    """Resolve bundled resources when frozen, or project files when running from source."""
    return RESOURCE_BASE.joinpath(*parts)


def find_winrar_executable() -> str | None:
    """Return a usable WinRAR/`rar` executable if one is installed."""
    candidates = [
        shutil.which("rar"),
        Path(os.environ.get("ProgramFiles", "")) / "WinRAR" / "rar.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "WinRAR" / "rar.exe",
    ]

    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    return None


CONFIG_TEMPLATE = resource_path("conf_info.txt")
CONFIG_FILE = APP_DIR / "conf_info.txt"
CURSOR_FILE = resource_path("cursor.png")
THEME_FILE = resource_path("red.json")
WINRAR_PATH = find_winrar_executable()

config = {
    "fps": 5,
    "file_time": None,
    "save_path": [None],
    "resolution": 80,
}


def ensure_config_file():
    """
    Guarantee a writable config beside the executable (or script).

    When frozen, the bundled config inside _MEIPASS is read-only/temporary, so copy
    it next to the EXE the first time; otherwise create a default file.
    """
    if CONFIG_FILE.exists():
        return

    try:
        if CONFIG_TEMPLATE.exists():
            CONFIG_FILE.write_text(CONFIG_TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            CONFIG_FILE.write_text("5\n60\n[]\n80\n", encoding="utf-8")
    except Exception:
        logging.exception("Failed to create writable conf_info.txt")

shared_state = {
    "fps": 5,
    "start_time": None,
    "duration": 60,  # in seconds
    "monitor_id": 0,
}

recording_started_event = threading.Event()
config_lock = threading.Lock()
config_updated = threading.Event()
terminate_program = threading.Event()

open_writers = {}
video_paths = {}

def compress_and_remove(filepath):
    if not WINRAR_PATH:
        print("WinRAR/rar executable not found; skipping compression.")
        return

    output_rar = filepath.replace(".avi", ".rar")
    filename = os.path.basename(filepath)

    command = [WINRAR_PATH, "a", output_rar, filename]
    try:
        subprocess.run(command, check=True, cwd=os.path.dirname(filepath))
        print(f"File successfully compressed: {output_rar}")
        os.remove(filepath)
    except subprocess.CalledProcessError as e:
        print(f"Error compressing file {filepath}: {e}")

def compress_and_remove_if_exists(filepath):
    """Used for emergency cleanup — if the file exists, compress it."""
    if os.path.exists(filepath):
        print(f"Compressing leftover file: {filepath}")
        compress_and_remove(filepath)

def read_config():
    ensure_config_file()

    try:
        with CONFIG_FILE.open('r') as f:
            lines = f.readlines()
            for i in range(0, len(lines), 4):
                fps = lines[i].strip()
                minutes = int(lines[i + 1].strip())
                paths = ast.literal_eval(lines[i + 2].strip())
                res = int(lines[i + 3].strip()) / 100
            return fps, minutes, paths, res
    except Exception as e:
        logging.exception("Error reading config")
        return None, None, None, None

class ConfigHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith("conf_info.txt"):
            print("Configuration file updated. Reloading settings...")
            new_fps, new_file_time, new_save_path, new_resolution = read_config()
            with config_lock:
                config["fps"] = new_fps
                config["file_time"] = new_file_time
                config["save_path"] = new_save_path
                config["resolution"] = new_resolution
            config_updated.set()

def get_monitor_for_cursor(monitors, mouse_x, mouse_y):
    for i, monitor in enumerate(monitors[1:], start=1):
        if (monitor["left"] <= mouse_x < monitor["left"] + monitor["width"] and
                monitor["top"] <= mouse_y < monitor["top"] + monitor["height"]):
            return i
    return None

def record_screen(monitor_id, save_path):
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    sct = mss.mss()
    monitors = sct.monitors
    if monitor_id >= len(monitors):
        print(f"Invalid monitor_id {monitor_id}, using first monitor.")
        monitor_id = 1
    scale_factor = config["resolution"]
    fps = int(config["fps"])
    monitor = monitors[monitor_id]
    screen_width, screen_height = monitor["width"], monitor["height"]
    output_width = int(screen_width * scale_factor)
    output_height = int(screen_height * scale_factor)

    cursor = cv2.imread(str(CURSOR_FILE), cv2.IMREAD_UNCHANGED)
    cursor_enabled = cursor is not None
    if cursor_enabled:
        cursor = cv2.resize(cursor, (20, 20))
        cursor_h, cursor_w = cursor.shape[:2]

    out = None
    frame_count = 0
    last_cursor_pos = (-1, -1)
    next_frame_time = time.time()

    file_time = config["file_time"]
    total_frames = int(file_time * 60 * fps)
    pbar = tqdm(total=total_frames, desc=f"Monitor {monitor_id}", position=monitor_id, leave=True)

    try:
        shared_state["start_time"] = datetime.now()
        shared_state["monitor_id"] = monitor_id
        recording_started_event.set()  # signal GUI once
        print(f'recording event set')
        while not terminate_program.is_set():
            with config_lock:
                pass
            if frame_count == 0 or frame_count >= total_frames:
                if out:
                    out.release()
                    compress_and_remove(video_file)
                    pbar.close()
                    recording_started_event.clear()
                    print(f'recording event cleared')
                    break
                current_time = datetime.now().strftime("%d-%m-%Y_%H-%M-%S")
                video_file = os.path.join(f"{save_path}/Monitor_{monitor_id}", f"recording_{current_time}.avi")
                os.makedirs(os.path.dirname(video_file), exist_ok=True)
                out = cv2.VideoWriter(video_file, fourcc, fps, (output_width, output_height))
                if not out.isOpened():
                    logging.error("VideoWriter failed to open for %s (fps=%s, size=%sx%s)", video_file, fps, output_width, output_height)
                    messagebox.showerror(
                        "Recording error",
                        "Unable to start recording. Please verify the save path is writable and codecs are available (see mainApp.log).",
                    )
                    terminate_program.set()
                    break
                logging.info("Recording started on monitor %s -> %s", monitor_id, video_file)
                open_writers[monitor_id] = out
                video_paths[monitor_id] = video_file
                frame_count = 0
                next_frame_time = time.time()
                pbar.reset()

            screenshot = sct.grab(monitor)
            frame = np.array(screenshot)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

            mouse_x, mouse_y = pyautogui.position()
            current_monitor_id = get_monitor_for_cursor(sct.monitors, mouse_x, mouse_y)

            if cursor_enabled and current_monitor_id == monitor_id and (mouse_x, mouse_y) != last_cursor_pos:
                last_cursor_pos = (mouse_x, mouse_y)
                monitor_left, monitor_top = monitor["left"], monitor["top"]
                mouse_x_relative, mouse_y_relative = mouse_x - monitor_left, mouse_y - monitor_top

                if 0 <= mouse_x_relative + cursor_w <= screen_width and 0 <= mouse_y_relative + cursor_h <= screen_height:
                    roi = frame[mouse_y_relative:mouse_y_relative + cursor_h, mouse_x_relative:mouse_x_relative + cursor_w]

                    cursor_rgb = cursor[:, :, :3]
                    cursor_alpha = cursor[:, :, 3] / 255.0

                    for c in range(3):
                        roi[:, :, c] = (cursor_alpha * cursor_rgb[:, :, c] +
                                        (1 - cursor_alpha) * roi[:, :, c])
            # --- Overlay current time in top right ---
            timestamp = datetime.now().strftime("%H:%M:%S")
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.7
            font_color = (255, 255, 255)  # White
            thickness = 2

            # Calculate size so we can align right
            (text_w, text_h), _ = cv2.getTextSize(timestamp, font, font_scale, thickness)

            # Optional: shadow for visibility
            shadow_color = (0, 0, 0)
            cv2.putText(frame, timestamp,
                        (screen_width - text_w - 10 + 2, text_h + 10 + 2),
                        font, font_scale, shadow_color, thickness, cv2.LINE_AA)

            # Main text
            cv2.putText(frame, timestamp,
                        (screen_width - text_w - 10, text_h + 10),
                        font, font_scale, font_color, thickness, cv2.LINE_AA)

            if scale_factor != 1.0:
                frame = cv2.resize(frame, (output_width, output_height))

            out.write(frame)
            frame_count += 1
            pbar.update(1)

            next_frame_time += 1 / fps
            sleep_duration = next_frame_time - time.time()
            if sleep_duration > 0:
                time.sleep(sleep_duration)
            else:
                next_frame_time = time.time()

            if config_updated.is_set():
                config_updated.clear()
                print(f"Monitor {monitor_id} updating config dynamically...")
                continue

    except Exception as e:
        logging.exception("Error on monitor %s", monitor_id)
        if out:
            out.release()
        pbar.close()


def monitor_config():
    event_handler = ConfigHandler()
    observer = Observer()
    observer.schedule(event_handler, path=str(CONFIG_FILE.parent), recursive=False)
    observer.start()

def run_scan(monitor_id):
    while not terminate_program.is_set():
        with config_lock:
            fps, file_time, save_paths, scale_factor = config["fps"], config["file_time"], config["save_path"], config["resolution"]

        if not all([fps, file_time, save_paths, scale_factor]):
            print("Invalid configuration. Retrying...")
            time.sleep(5)
            continue
        save_path = save_paths[-1]
        logging.info(
            "Preparing recording | monitor=%s fps=%s duration_min=%s scale=%.0f%% path=%s",
            monitor_id,
            fps,
            file_time,
            scale_factor * 100,
            save_path,
        )
        record_screen(monitor_id, save_path)


def mainRecording():
    global config
    config["fps"], config["file_time"], config["save_path"], config["resolution"] = read_config()
    monitor_config()

    with mss.mss() as sct:
        monitors = sct.monitors
        num_monitors = len(monitors) - 1

        threads = []
        for i in range(1, num_monitors + 1):
            thread = threading.Thread(target=run_scan, args=(i,), daemon=True)
            thread.start()
            threads.append(thread)

        for thread in threads:
            thread.join()


# -------------- GUI Frames ------------------

class HomeFrame(ctk.CTkFrame):
    def __init__(self, master, controller):
        super().__init__(master)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        container = ctk.CTkFrame(self)
        container.pack(expand=True, fill="both", padx=20, pady=20)

        ctk.CTkLabel(container, text="Configuration", font=("Helvetica", 24, "bold")).pack(pady=20)

        self.fps_entry = self._labeled_entry(container, "FPS:")
        self.file_time_entry = self._labeled_entry(container, "File length (in minutes):")
        self.path_entry = self._labeled_entry(container, "Save path:")
        self.res_entry = self._labeled_entry(container, "Resolution (0-100, When higher value means higher resolution):")

        browse_button = ctk.CTkButton(container, text="Browse", command=self.browse_folder)
        browse_button.pack(pady=(5, 15))

        enter_button = ctk.CTkButton(container, text="Save Configuration",
                                     command=self.confirm_config)
        enter_button.pack(pady=(10, 5))

        ctk.CTkButton(container, text="⬅ Back to Home", command=lambda: master.show_frame("MainMenu")).pack(pady=5)

        self.load_existing_config()

    def _labeled_entry(self, parent, label):
        ctk.CTkLabel(parent, text=label, anchor="w").pack(fill="x")
        entry = ctk.CTkEntry(parent)
        entry.pack(pady=5)
        return entry

    def browse_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.path_entry.delete(0, ctk.END)
            self.path_entry.insert(0, path)

    def confirm_config(self):
        fps = int(self.fps_entry.get())
        file_time = self.file_time_entry.get()
        file_path = self.path_entry.get()
        resolution = self.res_entry.get()
        response = messagebox.askyesno("Confirm Configuration",
                                       f"FPS: {fps}\n\nFile Length: {file_time}\n\nPath: {file_path}\n\nResolution: {resolution}")
        if response:
            self.save_config(fps, file_time, file_path, resolution)

    def save_config(self, fps, file_time, file_path, res):
        try:
            file_time = int(file_time)
            existing_paths = []

            if CONFIG_FILE.exists():
                with CONFIG_FILE.open("r") as file:
                    lines = file.readlines()
                if len(lines) >= 3:
                    try:
                        existing_paths = ast.literal_eval(lines[2].strip())
                        if not isinstance(existing_paths, list):
                            existing_paths = []
                    except Exception:
                        pass

            if file_path in existing_paths:
                existing_paths.remove(file_path)
            existing_paths.append(file_path)

            with CONFIG_FILE.open("w") as file:
                file.write(f"{fps}\n{file_time}\n{existing_paths}\n{res}\n")

            self.create_monitor_subfolders(file_path)
            messagebox.showinfo("Success", "Configuration saved.")
        except ValueError:
            messagebox.showerror("Error", "File length or Resolution are invalid.")

    def load_existing_config(self):
        if CONFIG_FILE.exists():
            with CONFIG_FILE.open("r") as file:
                lines = file.readlines()
                if len(lines) >= 3:
                    self.fps_entry.insert(0, lines[0].strip())
                    self.file_time_entry.insert(0, lines[1].strip())
                    self.res_entry.insert(0, lines[3].strip())

    def create_monitor_subfolders(self, base_path):
        with mss.mss() as sct:
            for i in range(1, len(sct.monitors)):
                folder_path = os.path.join(base_path, str(i))
                os.makedirs(folder_path, exist_ok=True)

class WelcomeFrame(ctk.CTkFrame):
    def __init__(self, master, controller):
        super().__init__(master)
        self.controller = controller

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(self, text= "Welcome to ScanOT2!", font=("Helvetica", 32, "bold"))
        title.grid(row=0, column=0, pady=(40, 20), sticky="n")

        description = (
            "ScanOT2 is a designated screen recording app developed by the Cyber OT team.\n"
            "This tool was developed for stand alone control PCs, in order to better investigate occurrences out in the \nfield, and help keep track of past events.\n\n"
            "The features available in this new and updated version include:\n\n"
            "- Configuration of video recording settings dynamically (Resolution, FPS, and more)\n\n"
            "- Monitoring of ongoing recordings\n\n"
            "- Automatic managing and compression of your screen recordings\n\n"
            "Get started by clicking the button below."
        )
        ctk.CTkLabel(self, text=description, justify="left", font=("Helvetica", 14)).grid(
            row=1, column=0, padx=50, sticky="n"
        )

        ctk.CTkButton(self, text="Continue", width=200, command=lambda: controller.show_frame("MainMenu")).grid(
            row=2, column=0, pady=(30, 20)
        )


class MonitorFrame(ctk.CTkFrame):
    def __init__(self, master, controller):
        super().__init__(master)
        self.controller = controller
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Recording Status", font=("Helvetica", 24, "bold")).pack(pady=(30, 10))

        self.monitor_widgets = {}  # Dict to store widgets per monitor

        # Create a container for all progress bars
        self.progress_container = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_container.pack(fill="both", expand=True, padx=50)

        # --- Back Button ---
        ctk.CTkButton(self, text="⬅ Back to Main Menu", command=lambda: controller.show_frame("MainMenu")).pack(pady=20)

    def on_show(self):
        print('in on_show')
        self.wait_for_recording_start()

    def wait_for_recording_start(self):
        print('in wait_for_recording_start')

        def checker():
            while True:
                recording_started_event.wait()
                print('event recognized by wait_for_recording_start')
                monitor_id = shared_state["monitor_id"]  # You'll need to store which monitor started
                start_time = shared_state["start_time"]
                duration = config["file_time"] * 60
                self.after(0, self.start_monitor_progress, monitor_id, start_time, duration)
                recording_started_event.clear()

        threading.Thread(target=checker, daemon=True).start()

    def start_monitor_progress(self, monitor_id, start_time, duration):
        if monitor_id not in self.monitor_widgets:
            self.create_monitor_widgets(monitor_id)

        self.animate_progress(monitor_id, start_time, duration)

    def create_monitor_widgets(self, monitor_id):
        frame = ctk.CTkFrame(self.progress_container, fg_color="transparent")
        frame.pack(fill="x", pady=10)

        title = ctk.CTkLabel(frame, text=f"Monitor {monitor_id}", font=("Helvetica", 16, "bold"))
        title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))

        progressbar = ctk.CTkProgressBar(frame, height=20)
        progressbar.grid(row=1, column=0, sticky="ew", padx=(0, 10))
        frame.grid_columnconfigure(0, weight=1)

        percent_label = ctk.CTkLabel(frame, text="0%")
        percent_label.grid(row=1, column=1)

        time_left_label = ctk.CTkLabel(frame, text="Time left: --:--")
        time_left_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=(5, 0))

        self.monitor_widgets[monitor_id] = {
            "progressbar": progressbar,
            "percent_label": percent_label,
            "time_left_label": time_left_label
        }

    def animate_progress(self, monitor_id, start_time, duration):
        widgets = self.monitor_widgets[monitor_id]

        def update():
            elapsed = (datetime.now() - start_time).total_seconds()
            progress = min(1.0, elapsed / duration)
            percent = int(progress * 100)
            time_left = max(0, int(duration - elapsed))
            minutes, seconds = divmod(time_left, 60)

            widgets["progressbar"].set(progress)
            widgets["percent_label"].configure(text=f"{percent}%")
            widgets["time_left_label"].configure(text=f"Time left: {minutes:02d}:{seconds:02d}")

            if progress < 1.0:
                self.after(100, update)

        update()

class MainMenuFrame(ctk.CTkFrame):
    def __init__(self, master, controller):
        super().__init__(master)
        self.controller = controller

        # Row 4 absorbs extra space (pushes everything up slightly)
        self.grid_rowconfigure(4, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Top label with more bottom padding
        ctk.CTkLabel(self, text="ScanOT2", font=("Helvetica", 32, "bold")).grid(
            row=0, column=0, pady=(40, 20), sticky="n"
        )

        # First button with more bottom padding
        ctk.CTkButton(self, text="Video Recording Settings", width=300,
                      command=lambda: controller.show_frame("Home")).grid(
            row=1, column=0, pady=(0, 15)
        )

        # Second button with standard padding
        ctk.CTkButton(self, text="Current Recording Status", width=300,
                      command=lambda: controller.show_frame("Monitor")).grid(
            row=2, column=0, pady=(0, 0)
        )


# ------------- Main App Controller ----------------

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.protocol("WM_DELETE_WINDOW", self.hide_window)  # Hide instead of closing
        self.title("ScanOT2")
        self.geometry("900x550")
        self.minsize(500, 400)

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.frames = {}
        for F, name in [
            (MainMenuFrame, "MainMenu"),
            (HomeFrame, "Home"),
            (MonitorFrame, "Monitor"),
            (WelcomeFrame, "Welcome"),
        ]:
            frame = F(self, self)
            frame.grid(row=0, column=0, sticky="nsew")
            self.frames[name] = frame

        self.show_frame("Welcome")

        # Start system tray icon in background thread
        threading.Thread(target=self.create_tray_icon, daemon=True).start()

    def hide_window(self):
        """Hide the window instead of closing it."""
        self.withdraw()

    def show_window(self, icon=None, item=None):
        """Show the hidden window."""
        self.after(0, self.deiconify)

    def on_quit(self, icon, item):
        """Exit the application completely."""
        icon.stop()
        self.after(0, self.destroy)

    def create_tray_icon(self):
        """Create and run the system tray icon."""
        icon_path = resource_path("icon.png")
        if not icon_path.exists():
            # Fallback simple image if no icon file exists
            img = Image.new('RGB', (64, 64), color=(0, 122, 204))
        else:
            img = Image.open(icon_path)

        menu = Menu(
            MenuItem("Show", self.show_window),
            MenuItem("Exit", self.on_quit)
        )

        self.tray_icon = Icon("ScanOT2", img, "ScanOT2", menu)
        self.tray_icon.run()

    def show_frame(self, name):
        print('in show_frame', name)
        frame = self.frames[name]
        frame.tkraise()
        if hasattr(frame, "on_show"):
            print('in show_frame - hasattr')
            frame.on_show()



# ------------- Check avi files --------------

def checkAviExists(directory):
    """
        Compresses each .avi file in the given directory into a .rar archive using WinRAR,
        and deletes the original .avi file after successful compression.

        Args:
            directory (str): Path to the directory to scan.
            Requires WinRAR/`rar` to be available on the machine.
        """
    if not WINRAR_PATH:
        print("WinRAR/rar executable not found; skipping compression.")
        return

    if not os.path.isdir(directory):
        raise ValueError(f"Invalid directory: {directory}")

    for filename in os.listdir(directory):
        if filename.lower().endswith('.avi'):
            filepath = os.path.join(directory, filename)
            output_rar = filepath.replace('.avi', '.rar')

            command = [WINRAR_PATH, 'a', output_rar, filename]
            try:
                subprocess.run(command, check=True, cwd=directory)
                print(f"File successfully compressed: {output_rar}")
                os.remove(filepath)
                print(f"Original file deleted: {filepath}")
            except subprocess.CalledProcessError as e:
                print(f"Error compressing file {filepath}: {e}")


def checkBeforeStart():
    ensure_config_file()
    with CONFIG_FILE.open('r') as f:
        line = f.readlines()[2]
        sys_args = ast.literal_eval(line.strip())  # Convert string to list
        if not sys_args:
            return
        last_path = sys_args[-1]
    i = 1
    while True:
        curr_path = os.path.join(last_path, f'monitor_{i}')
        if os.path.exists(curr_path):
            checkAviExists(curr_path)
            i += 1
        else:
            break

# ------------------- Run App -------------------

if __name__ == "__main__":
    setup_logging()

    try:
        rar_thread = threading.Thread(target=checkBeforeStart)
        rar_thread.start()
        recording_thread = threading.Thread(target=mainRecording)
        recording_thread.start()
        ctk.set_appearance_mode("dark")
        if THEME_FILE.exists():
            ctk.set_default_color_theme(str(THEME_FILE))
        app = App()
        app.mainloop()
    except Exception:
        logging.exception("Fatal error during application startup")
