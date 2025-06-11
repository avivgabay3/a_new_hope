import os
import wave
import threading
import subprocess
import customtkinter as ctk
import pyaudio
# START OF SCRIPT
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
import signal
import sys
from tqdm import tqdm
import atexit

config = {
    "userid": None,
    "file_time": None,
    "save_path": [None]
}

shared_state = {
    "fps": 5,
    "start_time": None,
    "duration": 60,  # in seconds
}

recording_started_event = threading.Event()
config_lock = threading.Lock()
config_updated = threading.Event()
terminate_program = threading.Event()

open_writers = {}
video_paths = {}

def compress_and_remove(filepath):
    winrar_path = r"C:\Program Files\WinRAR\rar.exe"
    output_rar = filepath.replace(".avi", ".rar")
    filename = os.path.basename(filepath)

    command = [winrar_path, 'a', output_rar, filename]
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
    try:
        with open('C:/Users/user/PycharmProjects/a_new_hope/conf_info.txt', 'r') as f:
            lines = f.readlines()
            for i in range(0, len(lines), 3):
                user_id = lines[i].strip()
                minutes = int(lines[i + 1].strip())
                paths = ast.literal_eval(lines[i + 2].strip())
            return user_id, minutes, paths
    except Exception as e:
        print(f"Error reading config: {e}")
        return None, None, None

class ConfigHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith("conf_info.txt"):
            print("Configuration file updated. Reloading settings...")
            new_userid, new_file_time, new_save_path = read_config()
            with config_lock:
                config["userid"] = new_userid
                config["file_time"] = new_file_time
                config["save_path"] = new_save_path
            config_updated.set()

def get_monitor_for_cursor(monitors, mouse_x, mouse_y):
    for i, monitor in enumerate(monitors[1:], start=1):
        if (monitor["left"] <= mouse_x < monitor["left"] + monitor["width"] and
                monitor["top"] <= mouse_y < monitor["top"] + monitor["height"]):
            return i
    return None

def record_screen(monitor_id, save_path, scale_factor=1.0):
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    fps = 5.0
    sct = mss.mss()
    monitors = sct.monitors
    if monitor_id >= len(monitors):
        print(f"Invalid monitor_id {monitor_id}, using first monitor.")
        monitor_id = 1

    monitor = monitors[monitor_id]
    screen_width, screen_height = monitor["width"], monitor["height"]
    output_width = int(screen_width * scale_factor)
    output_height = int(screen_height * scale_factor)

    cursor = cv2.imread("C:/Users/user/PycharmProjects/a_new_hope/cursor.png", cv2.IMREAD_UNCHANGED)
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
        recording_started_event.set()  # signal GUI once
        print(f'recording event set')
        while not terminate_program.is_set():
            with config_lock:
                file_time = config["file_time"]
                username = config["userid"]
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
        print(f"Error on monitor {monitor_id}: {e}")
        if out:
            out.release()
            compress_and_remove_if_exists(video_paths.get(monitor_id, ""))
        pbar.close()

    finally:
        if monitor_id in open_writers:
            open_writers[monitor_id].release()
            del open_writers[monitor_id]
        if monitor_id in video_paths:
            compress_and_remove_if_exists(video_paths[monitor_id])
            del video_paths[monitor_id]
        pbar.close()

def monitor_config():
    config_file_path = r"C:\Users\user\PycharmProjects\a_new_hope\conf_info.txt"
    directory = os.path.dirname(config_file_path)

    event_handler = ConfigHandler()
    observer = Observer()
    observer.schedule(event_handler, path=".", recursive=False)
    observer.start()

def run_scan(monitor_id, scale_factor=1.0):
    while not terminate_program.is_set():
        with config_lock:
            userid, file_time, save_paths = config["userid"], config["file_time"], config["save_path"]

        if not all([userid, file_time, save_paths]):
            print("Invalid configuration. Retrying...")
            time.sleep(5)
            continue

        save_path = save_paths[-1]
        print(f"Starting screen recording for Monitor {monitor_id} at {scale_factor*100:.0f}% resolution.")
        record_screen(monitor_id, save_path, scale_factor)

def signal_handler(sig, frame):
    print("\nGracefully stopping... Please wait.")
    terminate_program.set()

    for monitor_id, writer in open_writers.items():
        try:
            writer.release()
            compress_and_remove_if_exists(video_paths.get(monitor_id, ""))
        except Exception as e:
            print(f"Error during signal cleanup for monitor {monitor_id}: {e}")
    open_writers.clear()
    video_paths.clear()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def cleanup_on_exit():
    if not terminate_program.is_set():
        terminate_program.set()
    for monitor_id, writer in open_writers.items():
        try:
            writer.release()
            compress_and_remove_if_exists(video_paths.get(monitor_id, ""))
        except Exception as e:
            print(f"Cleanup error on exit for monitor {monitor_id}: {e}")

atexit.register(cleanup_on_exit)

def mainRecording():
    global config
    config["userid"], config["file_time"], config["save_path"] = read_config()
    monitor_config()

    scale_factor = 0.8

    with mss.mss() as sct:
        monitors = sct.monitors
        num_monitors = len(monitors) - 1

        threads = []
        for i in range(1, num_monitors + 1):
            thread = threading.Thread(target=run_scan, args=(i, scale_factor), daemon=True)
            thread.start()
            threads.append(thread)

        for thread in threads:
            thread.join()


# -------------- GUI Frames ------------------

class HomeFrame(ctk.CTkFrame):
    def __init__(self, master, controller):
        super().__init__(master)
        self.controller = controller
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        container = ctk.CTkFrame(self)
        container.pack(expand=True, fill="both", padx=20, pady=20)

        self.title_label = ctk.CTkLabel(container, text="A New Hope", font=("Helvetica", 32, "bold"))
        self.title_label.pack(pady=40)

        ctk.CTkButton(container, text="🎤 Microphone Recorder", command=lambda: controller.show_frame("Recorder")).pack(pady=20)
        ctk.CTkButton(container, text="⚙️ Configuration Tool", command=lambda: controller.show_frame("Config")).pack(pady=20)
        ctk.CTkButton(container, text="⬅ Back to Main Menu", command=lambda: controller.show_frame("MainMenu")).pack(pady=20)

    def change_title_color(self):
        original_color = self.title_label.cget("text_color")
        self.title_label.configure(text_color="yellow")
        self.after(2000, lambda: self.title_label.configure(text_color=original_color))


class RecorderFrame(ctk.CTkFrame):
    def __init__(self, master, controller):
        super().__init__(master)
        self.controller = controller
        self.recording = False

        container = ctk.CTkFrame(self)
        container.pack(expand=True, fill="both", padx=20, pady=20)

        self.label = ctk.CTkLabel(container, text="Press to Start/Stop Recording 🎤", font=ctk.CTkFont(size=16))
        self.label.pack(pady=20)

        self.button = ctk.CTkButton(container, text="🎤", command=self.click_handle, width=80, height=40,
                                    font=ctk.CTkFont(size=20))
        self.button.pack(pady=10)

        self.status = ctk.CTkLabel(container, text="Status: Idle", text_color="gray")
        self.status.pack(pady=10)

        ctk.CTkButton(container, text="⬅ Back to Home", command=lambda: controller.show_frame("Home")).pack(pady=10)

    def click_handle(self):
        if self.recording:
            self.recording = False
            self.status.configure(text="Status: Idle...", text_color="gray")
            self.button.configure(text_color="black")
        else:
            self.recording = True
            self.status.configure(text="Status: Recording", text_color="green")
            self.button.configure(text_color="gray")
            threading.Thread(target=self.start_recording).start()
            self.controller.frames["Home"].change_title_color()

    def start_recording(self):
        CHUNK = 1024
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 44100

        audio = pyaudio.PyAudio()
        stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
        frames = []

        while self.recording:
            data = stream.read(CHUNK)
            frames.append(data)

        stream.stop_stream()
        stream.close()
        audio.terminate()

        output_dir = os.path.join(os.path.expanduser("~"), "sound_files")
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        file_path = os.path.join(output_dir, f"recording_{timestamp}.wav")

        with wave.open(file_path, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(audio.get_sample_size(FORMAT))
            wf.setframerate(RATE)
            wf.writeframes(b''.join(frames))


class ConfigFrame(ctk.CTkFrame):
    def __init__(self, master, controller):
        super().__init__(master)
        ctk.CTkLabel(self, text="Configuration Tool", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=20)
        ctk.CTkLabel(self, text="(This is a placeholder for your settings)").pack(pady=10)
        ctk.CTkButton(self, text="⬅ Back to Home", command=lambda: controller.show_frame("Home")).pack(pady=20)


class MonitorFrame(ctk.CTkFrame):
    def __init__(self, master, controller):
        super().__init__(master)
        self.controller = controller
        ctk.CTkLabel(self, text="Recording Monitor", font=("Helvetica", 24, "bold")).pack(pady=20)

        self.progressbar = ctk.CTkProgressBar(self)
        self.progressbar.pack(pady=10)
        self.progressbar.set(0)

        ctk.CTkButton(self, text="⬅ Back to Main Menu", command=lambda: controller.show_frame("MainMenu")).pack(pady=20)

    def on_show(self):
        print('in on_show')
        self.wait_for_recording_start()

    def wait_for_recording_start(self):
        print('in wait_for_recording_start')
        def checker():
            recording_started_event.wait()
            print('event recognized by wait_for_recording_start')
            start_time = shared_state["start_time"]
            duration = config["file_time"] * 60

            self.after(0, self.animate_progress, start_time, duration)
            recording_started_event.clear()
            self.wait_for_recording_start()

        threading.Thread(target=checker, daemon=True).start()


    def animate_progress(self, start_time, duration):
        def update():
            elapsed = (datetime.now() - start_time).total_seconds()
            progress = min(1.0, elapsed / duration)
            self.progressbar.set(progress)
            if progress < 1.0:
                self.after(100, update)

        update()


class MainMenuFrame(ctk.CTkFrame):
    def __init__(self, master, controller):
        super().__init__(master)
        self.controller = controller

        ctk.CTkLabel(self, text="Welcome", font=("Helvetica", 32, "bold")).pack(pady=40)

        ctk.CTkButton(self, text="Video Recording Settings", width=300,
                      command=lambda: controller.show_frame("Home")).pack(pady=20)

        ctk.CTkButton(self, text="Recording Monitor", width=300,
                      command=lambda: controller.show_frame("Monitor")).pack(pady=20)


# ------------- Check avi files --------------

def checkAviExists(directory):
    winrar_path = r"C:\Program Files\WinRAR\rar.exe"
    """
        Compresses each .avi file in the given directory into a .rar archive using WinRAR,
        and deletes the original .avi file after successful compression.

        Args:
            directory (str): Path to the directory to scan.
            winrar_path (str): Path to the WinRAR executable.
        """
    if not os.path.isdir(directory):
        raise ValueError(f"Invalid directory: {directory}")

    for filename in os.listdir(directory):
        if filename.lower().endswith('.avi'):
            filepath = os.path.join(directory, filename)
            output_rar = filepath.replace('.avi', '.rar')

            command = [winrar_path, 'a', output_rar, filename]
            try:
                subprocess.run(command, check=True, cwd=directory)
                print(f"File successfully compressed: {output_rar}")
                os.remove(filepath)
                print(f"Original file deleted: {filepath}")
            except subprocess.CalledProcessError as e:
                print(f"Error compressing file {filepath}: {e}")


# ------------- Main App Controller ----------------

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Unified Recorder GUI")
        self.geometry("700x550")
        self.frames = {}

        for F, name in [
            (MainMenuFrame, "MainMenu"),
            (HomeFrame, "Home"),
            (RecorderFrame, "Recorder"),
            (ConfigFrame, "Config"),
            (MonitorFrame, "Monitor"),
        ]:
            frame = F(self, self)
            frame.grid(row=0, column=0, sticky="nsew")
            self.frames[name] = frame

        self.show_frame("MainMenu")

    def show_frame(self, name):
        print('in show_frame', name)
        frame = self.frames[name]
        frame.tkraise()
        # ✅ Call on_show() if the frame has it
        if hasattr(frame, "on_show"):
            print('in show_frame - hasattr')
            frame.on_show()


def checkBeforeStart():
    with open('C:/Users/user/PycharmProjects/a_new_hope/conf_info.txt', 'r') as f:
        line = f.readlines()[2]
        sys_args = ast.literal_eval(line.strip())  # Convert string to list
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
    checkBeforeStart()
    recording_thread = threading.Thread(target=mainRecording)
    recording_thread.start()
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("C:/Users/user/Downloads/red.json")
    app = App()
    app.mainloop()
