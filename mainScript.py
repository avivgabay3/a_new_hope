import os
import time
import cv2
import pyautogui
import threading
from datetime import datetime
import numpy as np
import mss

# Function to read configuration from conf_info.txt
def read_config():
    try:
        with open("conf_info.txt", "r") as file:
            lines = file.readlines()
            userid = lines[0].strip()
            file_time = int(lines[1].strip())  # File length in minutes
            save_path = lines[2].strip()
            return userid, file_time, save_path
    except Exception as e:
        print(f"Error reading config: {e}")
        return None, None, None


def get_monitor_for_cursor(monitors, mouse_x, mouse_y):
    """
    Returns the monitor index that contains the cursor.
    If the cursor is outside all monitors, return None.
    """
    for i, monitor in enumerate(monitors[1:], start=1):  # Skip index 0, as it's the full display region
        if (monitor["left"] <= mouse_x < monitor["left"] + monitor["width"] and
            monitor["top"] <= mouse_y < monitor["top"] + monitor["height"]):
            return i  # Return the correct monitor index
    return None  # Cursor is outside all known monitors


def record_screen(file_time, save_path, monitor_id):  # Default to first monitor
    # Initialize the video writer
    fourcc = cv2.VideoWriter_fourcc(*"XVID")
    fps = 10.0  # Frame rate
    frames_per_file = int(file_time * 60 * fps)  # Frames per file (length in minutes)

    # Create the initial video file
    current_time = datetime.now().strftime("%d-%m-%Y_%H-%M-%S")
    video_file = os.path.join(save_path, f"recording_{current_time}.avi")

    # Set up the video writer for the selected monitor resolution
    with mss.mss() as sct:
        monitors = sct.monitors  # Get all connected monitors
        if monitor_id >= len(monitors):  # Ensure the monitor_id is valid
            print(f"Invalid monitor_id {monitor_id}, using the first monitor.")
            monitor_id = 1  # Fallback to the first monitor

        monitor = monitors[monitor_id]  # Select the monitor based on monitor_id
        screen_width, screen_height = monitor["width"], monitor["height"]

        out = cv2.VideoWriter(video_file, fourcc, fps, (screen_width, screen_height))

    frame_count = 0
    last_time = time.time()

    with mss.mss() as sct:
        monitor = sct.monitors[monitor_id]  # Select the monitor based on monitor_id

        while True:
            # Capture the screen for the selected monitor
            screenshot = sct.grab(monitor)
            frame = np.array(screenshot)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)  # Convert BGRA to BGR

            # Get the global mouse position
            mouse_x, mouse_y = pyautogui.position()
            # Determine which monitor currently contains the cursor
            current_monitor_id = get_monitor_for_cursor(sct.monitors, mouse_x, mouse_y)

            if current_monitor_id == monitor_id:
                # Adjust the mouse position relative to the selected monitor
                monitor_left = monitor["left"]
                monitor_top = monitor["top"]
                mouse_x_relative = mouse_x - monitor_left
                mouse_y_relative = mouse_y - monitor_top

                # Load cursor image with alpha channel (RGBA)
                cursor = cv2.imread("cursor.png", cv2.IMREAD_UNCHANGED)  # Ensure it's a PNG with alpha transparency
                cursor = cv2.resize(cursor, (20, 20))  # Resize cursor to fit

                # Check if the cursor fits within the frame
                if cursor is not None:
                    cursor_h, cursor_w = cursor.shape[:2]

                    # Check if the cursor is within the bounds of the screen
                    if 0 <= mouse_x_relative + cursor_w <= screen_width and 0 <= mouse_y_relative + cursor_h <= screen_height:
                        # Split the cursor into its RGB and alpha channels
                        cursor_rgb = cursor[:, :, :3]  # RGB part
                        cursor_alpha = cursor[:, :, 3]  # Alpha channel

                        # Define the region of interest (ROI) on the screen where the cursor will be placed
                        roi = frame[mouse_y_relative:mouse_y_relative + cursor_h,
                              mouse_x_relative:mouse_x_relative + cursor_w]

                        # Blend the cursor onto the frame using the alpha channel (transparency handling)
                        for c in range(0, 3):  # Iterate through RGB channels
                            roi[:, :, c] = (cursor_alpha / 255.0 * cursor_rgb[:, :, c] +
                                            (1 - cursor_alpha / 255.0) * roi[:, :, c])

            # Write the frame to the video
            out.write(frame)
            frame_count += 1

            # If we've recorded enough frames for one file, stop and start a new file
            if frame_count >= frames_per_file:
                out.release()  # Release the current video file
                break

            # Sleep for the correct time to maintain FPS
            elapsed_time = time.time() - last_time
            sleep_time = max(1 / fps - elapsed_time, 0)  # Ensure we don't get a negative sleep time
            time.sleep(sleep_time)
            last_time = time.time()  # Update last_time after the sleep

    print("Screen recording finished.")


# Function to monitor the config file for changes
def monitor_config():
    last_mtime = os.path.getmtime("conf_info.txt")

    while True:
        current_mtime = os.path.getmtime("conf_info.txt")

        if current_mtime != last_mtime:
            print("Config file updated. Reloading...")
            userid, file_time, save_path = read_config()
            if userid and file_time and save_path:
                print(f"New Config - User ID: {userid}, File Length: {file_time} minutes, Save Path: {save_path}")
                last_mtime = current_mtime
            else:
                print("Error reloading configuration.")

        time.sleep(5)  # Check for updates every 5 seconds


def run_scan(monitor_id):
    while True:
        # Read initial config
        userid, file_time, save_path = read_config()
        if not all([userid, file_time, save_path]):
            print("Error: Invalid configuration.")
            return
        print(f"Starting screen recording. Files will be saved to {save_path}/{monitor_id} with {file_time} minute splits.")
        record_screen(file_time, f'{save_path}/{monitor_id}', monitor_id)


# Main function to start recording
def main():
    with mss.mss() as sct:
        monitors = sct.monitors
        num_monitors = len(monitors) - 1
        threads = []
        for i in  range(1, num_monitors + 1):
            thread = threading.Thread(target=run_scan, args=(i,), daemon=True)
            thread.start()
            threads.append(thread)

        for thread in threads:
            thread.join()

if __name__ == "__main__":
    main()
