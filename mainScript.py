import os
import time
import cv2
import pyautogui
import threading
from datetime import datetime
import numpy as np
import mss
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import zipfile
import shutil
import subprocess
MAX_FOLDER_SIZE_MB = 100

config = {
    "userid": None,
    "file_time": None,
    "save_path": None
}

config_lock = threading.Lock()
config_updated = threading.Event()  # Event to notify config changes


def get_folder_size_mb(folder):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(folder):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)
    return total_size / (1024 * 1024)

def zip_and_cleanup(folder_path, start_time, end_time):
    parent_dir = os.path.dirname(folder_path)
    zipped_name = f"{start_time} : {end_time}"
    zipped_path = os.path.join(parent_dir, zipped_name)

    os.rename(folder_path, zipped_path)  # Rename before zipping
    shutil.make_archive(zipped_path, 'zip', zipped_path)
    shutil.rmtree(zipped_path)  # Remove the folder after zipping

def compress_and_remove(filepath):
    """Transcode the video to MP4 using ffmpeg and remove the original .avi."""
    winrar_path = r"C:\Program Files\WinRAR\rar.exe"  # Adjust if necessary
    output_rar = filepath.replace(".avi", ".rar")
    filename = os.path.basename(filepath)

    # Run the WinRAR command to compress the file
    command = [winrar_path, 'a', output_rar, filename]

    try:
        subprocess.run(command, check=True,
                       cwd=os.path.dirname(filepath))  # Set the working directory to the file's folder

        print(f"File successfully compressed: {output_rar}")
        os.remove(filepath)  # Delete the original file after compression
    except subprocess.CalledProcessError as e:
        print(f"Error compressing file {filepath}: {e}")


# Function to read configuration from conf_info.txt
def read_config():
    try:
        with open("conf_info.txt", "r") as file:
            lines = file.readlines()
            return lines[0].strip(), int(lines[1].strip()), lines[2].strip()
    except Exception as e:
        print(f"Error reading config: {e}")
        return None, None, None


# Config watcher using Watchdog (replaces polling for efficiency)
class ConfigHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith("conf_info.txt"):
            print("Configuration file updated. Reloading settings...")
            new_userid, new_file_time, new_save_path = read_config()
            with config_lock:
                config["userid"] = new_userid
                config["file_time"] = new_file_time
                config["save_path"] = new_save_path
            config_updated.set()  # Notify recording threads to update


# Function to get monitor index based on cursor position
def get_monitor_for_cursor(monitors, mouse_x, mouse_y):
    for i, monitor in enumerate(monitors[1:], start=1):
        if (monitor["left"] <= mouse_x < monitor["left"] + monitor["width"] and
                monitor["top"] <= mouse_y < monitor["top"] + monitor["height"]):
            return i
    return None  # Cursor is outside all known monitors

def record_screen(monitor_id, scale_factor=1.0):
    """Records the screen for a specific monitor with optional scaling and cursor overlay."""
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")  # Lower CPU usage
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

    # Load and resize cursor image
    cursor = cv2.imread("cursor.png", cv2.IMREAD_UNCHANGED)
    if cursor is None:
        print("Cursor image not found. Skipping cursor overlay.")
        cursor_enabled = False
    else:
        cursor_enabled = True
        cursor = cv2.resize(cursor, (20, 20))
        cursor_h, cursor_w = cursor.shape[:2]

    out = None
    frame_count = 0
    last_cursor_pos = (-1, -1)
    next_frame_time = time.time()

    while True:
        file_time = config["file_time"]
        save_path = config["save_path"]
        username = config["userid"]

        if frame_count == 0 or frame_count >= int(file_time * 60 * fps):
            if out:
                out.release()
                compress_and_remove(video_file)
            current_time = datetime.now().strftime("%d-%m-%Y_%H-%M-%S")
            video_file = os.path.join(f"{save_path}/Monitor_{monitor_id}", f"recording_{current_time}.avi")
            os.makedirs(os.path.dirname(video_file), exist_ok=True)
            out = cv2.VideoWriter(video_file, fourcc, fps, (output_width, output_height))
            frame_count = 0
            next_frame_time = time.time()

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
                roi = frame[mouse_y_relative:mouse_y_relative + cursor_h,
                            mouse_x_relative:mouse_x_relative + cursor_w]

                cursor_rgb = cursor[:, :, :3]
                cursor_alpha = cursor[:, :, 3] / 255.0

                for c in range(3):
                    roi[:, :, c] = (cursor_alpha * cursor_rgb[:, :, c] +
                                    (1 - cursor_alpha) * roi[:, :, c])

        # Resize frame to scaled output size
        if scale_factor != 1.0:
            frame = cv2.resize(frame, (output_width, output_height))

        out.write(frame)
        frame_count += 1

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


def monitor_config():
    """Starts a thread that listens for config file changes dynamically."""
    event_handler = ConfigHandler()
    observer = Observer()
    observer.schedule(event_handler, path=".", recursive=False)
    observer.start()


def run_scan(monitor_id, scale_factor=1.0):
    """Runs the screen recording process for a given monitor with adjustable scaling."""
    while True:
        with config_lock:
            userid, file_time, save_path = config["userid"], config["file_time"], config["save_path"]

        if not all([userid, file_time, save_path]):
            print("Invalid configuration. Retrying...")
            time.sleep(5)
            continue

        print(f"Starting screen recording for Monitor {monitor_id} at {scale_factor*100:.0f}% resolution. Files saved to {save_path}/{monitor_id} every {file_time} minutes.")
        record_screen(monitor_id, scale_factor)


def main():
    global config
    config["userid"], config["file_time"], config["save_path"] = read_config()

    monitor_config()

    scale_factor = 0.8  # Change this value to control output resolution

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


if __name__ == "__main__":
    main()