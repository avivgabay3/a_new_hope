import os
import subprocess
import datetime
import mss
import ast

#NOT IN USE, rar each file after processing

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


def get_monitor_folders():
    with open('C:/Users/user/PycharmProjects/a_new_hope/conf_info.txt', 'r') as f:
        folders_path_str = f.readlines()[-2].strip()
    folders_path = ast.literal_eval(folders_path_str)
    with mss.mss() as sct:
        monitors = sct.monitors
        num_monitors = len(monitors) - 1
    all_folders = []
    for folder in folders_path:
        for i in range(1, num_monitors + 1):
            all_folders.append(os.path.normpath(os.path.join(folder, f'monitor_{i}')))
    return all_folders



def get_file_size(file_path):
    return os.path.getsize(file_path) / (1024 * 1024)  # in MB

def log_message(message, log_file='cleanup_log.txt'):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, 'a') as log:
        log.write(f"[{timestamp}] {message}\n")


def cleanupAllFolders(target_size_mb=500, max_size_mb=1000, log_file='cleanup_log.txt'):
    folder_paths = get_monitor_folders()
    all_files = []

    for folder_path in folder_paths:
        try:
            rar_files = [
                f for f in os.listdir(folder_path)
                if f.lower().endswith(".rar") and f.startswith("recording_")
            ]
            for filename in rar_files:
                file_path = os.path.join(folder_path, filename)
                file_size = get_file_size(file_path)
                creation_time = os.path.getctime(file_path)
                all_files.append((file_path, file_size, creation_time))

        except Exception as e:
            error_msg = f"Error reading folder {folder_path}: {e}"
            print(error_msg)
            log_message(error_msg, log_file)

    all_files.sort(key=lambda f: f[2])
    total_size = sum(file[1] for file in all_files)

    print(f"Total size before cleanup: {total_size:.2f} MB")
    log_message(f"Total size before cleanup: {total_size:.2f} MB", log_file)

    if total_size > max_size_mb:
        log_message(f"Total storage exceeds {max_size_mb} MB. Starting cleanup.", log_file)

        for file_path, file_size, _ in all_files:
            try:
                os.remove(file_path)
                total_size -= file_size
                msg = f"Deleted {file_path} ({file_size:.2f} MB). Current total size: {total_size:.2f} MB"
                print(msg)
                log_message(msg, log_file)

                if total_size <= target_size_mb:
                    log_message(f"Total storage reduced to {total_size:.2f} MB. Cleanup complete.", log_file)
                    break
            except Exception as e:
                error_msg = f"Failed to delete {file_path}: {e}"
                print(error_msg)
                log_message(error_msg, log_file)

    log_message(f"Total storage after cleanup: {total_size:.2f} MB", log_file)

    if total_size <= target_size_mb:
        log_message(f"Total storage is now under the target size of {target_size_mb} MB.", log_file)
    else:
        log_message(f"Total storage is still above the target size of {target_size_mb} MB.", log_file)


def main():
    #my_folders = get_monitor_folders()
    #print(my_folders)
    cleanupAllFolders(1000, 3000)
    #random_path = r'C:\Users\user\Documents\Monitor_1'
    #rarFiles(random_path)
    #cleanupFolder(random_path, 20, 30)

if __name__ == '__main__':
    main()