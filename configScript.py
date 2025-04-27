import numpy as np
import customtkinter as ctk
import tkinter as ttk
from tkinter import messagebox, filedialog
import mss
import os
"""
In this script, we will ask the user to enter all the wanted parameters for the main script,
i.e name of operator (for log info), time length for each file, and desired path to save the files.
As the main script will run as soon as the OS boots, this confighuration will only need to happen once.
This will be written to a .txt file which the main script will read out of, but the script will have the option
to change that file during runtime dynamically.
"""


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")
# help function
def create_monitor_subfolders(base_path):
    with mss.mss() as sct:
        num_monitors = len(sct.monitors) - 1  # Ignore the first entry (full virtual screen)

    for i in range(1, num_monitors + 1):  # Number subfolders from 1 to num_monitors
        folder_path = os.path.join(base_path, str(i))
        os.makedirs(folder_path, exist_ok=True)  # Create folder if it doesn't exist

    print(f"Created {num_monitors} subfolders in {base_path}")

def save_configuration(userid, file_time, file_path, root):
    """Function to save configuration details to a text file."""
    try:
        # Convert file_time to integer
        file_time = int(file_time)

        # Open the file and write the details
        with open("conf_info.txt", "w") as file:
            file.write(f"{userid}\n")
            file.write(f"{file_time}\n")
            file.write(f"{file_path}\n")

        # Show success message
        messagebox.showinfo("Success", "Configuration successfully saved to conf file")
        create_monitor_subfolders(file_path)
        root.destroy() # If all the credentials are correct, close the gui and terminate the script
    except ValueError:
        # Handle the case where file_time is not a valid integer
        messagebox.showerror("Error", "Please enter a valid number for the file length.")


def confirm_signup(userid, file_time, file_path,root):
    """Function to show a confirmation pop-up when signing up."""
    response = messagebox.askyesno("Confirm Configuration", f"Are you sure all the info entered is correct?\n\n"
                                                            f"User ID: {userid}\n"
                                                            f"File Length: {file_time}\n"
                                                            f"Save Path: {file_path}")
    if response:  # If user clicks "Yes"
        save_configuration(userid, file_time, file_path,root)  # Save the configuration
    else:  # If user clicks "No"
        messagebox.showwarning("Cancelled", "Please check your information again.")


def browse_folder(entry):
    """Function to open a folder selection dialog."""
    folder_selected = filedialog.askdirectory()  # Open the folder selection dialog
    if folder_selected:  # If a folder is selected
        entry.delete(0, ctk.END)  # Clear the entry
        entry.insert(0, folder_selected)  # Insert the selected folder path into the entry


def mainGui():
    root = ctk.CTk()
    root.title("Configuration File")
    root.geometry("400x500")  # Adjusted height to accommodate the new field

    # Create a frame for centering the content
    frame = ctk.CTkFrame(root, corner_radius=15)
    frame.pack(pady=40, padx=30, fill="both", expand=True)

    label = ctk.CTkLabel(frame, text="Configuration", font=("Helvetica", 24, "bold"))
    label.pack(pady=(20, 10))

    # User ID field
    userid_label = ctk.CTkLabel(frame, text="User ID:", anchor="w")
    userid_label.pack(fill="x", padx=20)
    userid_entry = ctk.CTkEntry(frame, width=250, height=35)
    userid_entry.pack(pady=5)

    # Desired file length field
    file_time_label = ctk.CTkLabel(frame, text="Desired file length (in minutes):", anchor="w")
    file_time_label.pack(fill="x", padx=20)
    file_time_entry = ctk.CTkEntry(frame, width=250, height=35)
    file_time_entry.pack(pady=5)

    # Path selection field
    path_label = ctk.CTkLabel(frame, text="Save path:", anchor="w")
    path_label.pack(fill="x", padx=20)
    path_entry = ctk.CTkEntry(frame, width=250, height=35)
    path_entry.pack(pady=5)

    # Browse button for selecting the path
    browse_button = ctk.CTkButton(frame, text="Browse", corner_radius=10, height=35,
                                  command=lambda: browse_folder(path_entry))
    browse_button.pack(pady=(10, 20))

    # Enter button to confirm the info
    enter_button = ctk.CTkButton(frame, text="Enter", corner_radius=10, height=40,
                                 command=lambda: confirm_signup(userid_entry.get(), file_time_entry.get(),
                                                                path_entry.get(), root))
    enter_button.pack(pady=(10, 10))

    root.mainloop()


def main():
    mainGui()


if __name__ == "__main__":
    main()