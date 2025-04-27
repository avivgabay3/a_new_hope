import os
import subprocess
import datetime

def rarFiles(folder_path):
    winrar_path = r"C:\Program Files\WinRAR\rar.exe"  # Adjust if necessary

    if not os.path.exists(winrar_path):
        print("WinRAR not found at the specified path.")
        return

    for filename in os.listdir(folder_path):
        if filename.lower().endswith(".avi"):
            avi_path = os.path.join(folder_path, filename)
            rar_path = avi_path.replace(".avi", ".rar")

            command = [winrar_path, 'a', rar_path, filename]
            try:
                subprocess.run(command, cwd=folder_path, check=True)
                print(f"Compressed: {filename} -> {os.path.basename(rar_path)}")

                # Delete the original AVI after successful compression
                os.remove(avi_path)
                print(f"Deleted original: {filename}")

            except subprocess.CalledProcessError as e:
                print(f"Failed to compress {filename}: {e}")



def cleanupFolder(folder_path, age_threshold_days=14):
    rar_files = [
        f for f in os.listdir(folder_path)
        if f.lower().endswith(".rar") and f.startswith("recording_")
    ]

    if not rar_files:
        print("No RAR files found for cleanup.")
        return

    def extract_datetime(filename):
        try:
            timestamp_str = filename.replace("recording_", "").replace(".rar", "")
            return datetime.datetime.strptime(timestamp_str, "%d-%m-%Y_%H-%M-%S")
        except ValueError:
            return None

    # Parse timestamps
    file_times = {
        f: extract_datetime(f)
        for f in rar_files
    }

    # Filter out files with invalid datetime
    file_times = {f: t for f, t in file_times.items() if t is not None}

    if not file_times:
        print("No valid RAR filenames to parse.")
        return

    # Find the most recent timestamp
    latest_time = max(file_times.values())
    print(f"Latest file time: {latest_time}")

    threshold = datetime.timedelta(days=age_threshold_days)

    for filename, file_time in file_times.items():
        if latest_time - file_time > threshold:
            file_path = os.path.join(folder_path, filename)
            try:
                os.remove(file_path)
                print(f"Deleted old file: {filename}")
            except Exception as e:
                print(f"Failed to delete {filename}: {e}")

def main():
    random_path = r'C:\Users\user\Desktop\Monitor_1'
    rarFiles(random_path)
    cleanupFolder(random_path, 8)

if __name__ == '__main__':
    main()