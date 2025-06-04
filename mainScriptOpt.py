# START OF SCRIPT
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
        while not terminate_program.is_set():
            with config_lock:
                file_time = config["file_time"]
                username = config["userid"]

            if frame_count == 0 or frame_count >= total_frames:
                if out:
                    out.release()
                    compress_and_remove(video_file)
                    pbar.close()
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

def main():
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

if __name__ == "__main__":
    main()
# END OF SCRIPT
