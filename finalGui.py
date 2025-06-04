import customtkinter as ctk
from tkinter import messagebox, filedialog, PhotoImage
import mss
import os
import ast
import datetime
import threading
import pyaudio
import wave
from PIL import Image, ImageTk
import tkinter as tk
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__() # Load and set the PNG icon
        icon_image = Image.open("app_logo.png")  # Replace with the path to your PNG icon
        self.icon_photo = ImageTk.PhotoImage(icon_image)
        self.tk.call('wm', 'iconphoto', self._w, self.icon_photo)
        self.title("A New Hope")
        self.geometry("600x500")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.frames = {}
        self.create_frames()
        self.show_frame("Home")

    # def set_icon(self, icon_path):
    #     # Load the image using Pillow
    #     img = Image.open(icon_path)
    #
    #     # Convert it to a Tkinter-compatible PhotoImage
    #     tk_icon = ImageTk.PhotoImage(img)
    #
    #     # Set the window's icon
    #     self.tk.call('wm', 'iconphoto', self._w, tk_icon)


    def create_frames(self):
        self.frames["Home"] = HomeFrame(self)
        self.frames["Recorder"] = RecorderFrame(self)
        self.frames["Config"] = ConfigFrame(self)

        for frame in self.frames.values():
            frame.grid(row=0, column=0, sticky="nsew")

    def show_frame(self, name):
        frame = self.frames[name]
        frame.tkraise()


class HomeFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        container = ctk.CTkFrame(self)
        container.pack(expand=True, fill="both", padx=20, pady=20)

        self.title_label = ctk.CTkLabel(container, text="A New Hope", font=("Helvetica", 32, "bold"))
        self.title_label.pack(pady=40)
        ctk.CTkButton(container, text="🎤 Microphone Recorder", command=lambda: master.show_frame("Recorder")).pack(pady=20)
        ctk.CTkButton(container, text="⚙️ Configuration Tool", command=lambda: master.show_frame("Config")).pack(pady=20)

    def change_title_color(self):
        original_color = self.title_label.cget("text_color")
        self.title_label.configure(text_color="yellow")
        self.after(2000, lambda: self.title_label.configure(text_color=original_color))


class RecorderFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.master = master
        self.recording = False

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        container = ctk.CTkFrame(self)
        container.pack(expand=True, fill="both", padx=20, pady=20)

        self.label = ctk.CTkLabel(container, text="Press to Start/Stop Recording 🎤", font=ctk.CTkFont(size=16))
        self.label.pack(pady=20)

        self.button = ctk.CTkButton(container, text="🎤", command=self.click_handle, width=80, height=40, font=ctk.CTkFont(size=20))
        self.button.pack(pady=10)

        self.status = ctk.CTkLabel(container, text="Status: Idle", text_color="gray")
        self.status.pack(pady=10)

        ctk.CTkButton(container, text="⬅ Back to Home", command=lambda: master.show_frame("Home")).pack(pady=10)

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
            self.master.frames["Home"].change_title_color()  # Trigger the Easter egg

    def start_recording(self):
        start = datetime.datetime.now()
        file_name = start.strftime("%Y%m%d%H%M%S")
        if not os.path.exists('C:/sound_files'):
            os.mkdir('C:/sound_files')
        file_path = f'C:/sound_files/{file_name}.wav'
        audio = pyaudio.PyAudio()
        stream = audio.open(format=pyaudio.paInt16, channels=1, rate=44100, input=True, frames_per_buffer=1024)
        frames = []


        while self.recording:
            data = stream.read(1024)
            frames.append(data)

            elapsed = datetime.datetime.now() - start
            secs = elapsed.total_seconds()
            h = int(secs // 3600)
            m = int((secs % 3600) // 60)
            s = int(secs % 60)
            self.label.configure(text=f"{h:02d}:{m:02d}:{s:02d}")

        stream.stop_stream()
        stream.close()
        audio.terminate()

        sound_file = wave.open(file_path, 'wb')
        sound_file.setnchannels(1)
        sound_file.setsampwidth(audio.get_sample_size(pyaudio.paInt16))
        sound_file.setframerate(44100)
        sound_file.writeframes(b''.join(frames))
        sound_file.close()


class ConfigFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        container = ctk.CTkFrame(self)
        container.pack(expand=True, fill="both", padx=20, pady=20)

        ctk.CTkLabel(container, text="Configuration", font=("Helvetica", 24, "bold")).pack(pady=20)

        self.userid_entry = self._labeled_entry(container, "User ID:")
        self.file_time_entry = self._labeled_entry(container, "File length (in minutes):")
        self.path_entry = self._labeled_entry(container, "Save path:")

        browse_button = ctk.CTkButton(container, text="Browse", command=self.browse_folder)
        browse_button.pack(pady=(5, 15))

        enter_button = ctk.CTkButton(container, text="Save Configuration",
                                     command=self.confirm_config)
        enter_button.pack(pady=(10, 5))

        ctk.CTkButton(container, text="⬅ Back to Home", command=lambda: master.show_frame("Home")).pack(pady=5)

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
        userid = self.userid_entry.get()
        file_time = self.file_time_entry.get()
        file_path = self.path_entry.get()
        response = messagebox.askyesno("Confirm Configuration", f"User ID: {userid}\nFile Length: {file_time}\nPath: {file_path}")
        if response:
            self.save_config(userid, file_time, file_path)

    def save_config(self, userid, file_time, file_path):
        try:
            file_time = int(file_time)
            existing_paths = []

            if os.path.exists("conf_info.txt"):
                with open("conf_info.txt", "r") as file:
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

            with open("conf_info.txt", "w") as file:
                file.write(f"{userid}\n{file_time}\n{existing_paths}\n")

            self.create_monitor_subfolders(file_path)
            messagebox.showinfo("Success", "Configuration saved.")
        except ValueError:
            messagebox.showerror("Error", "File length must be an integer.")

    def load_existing_config(self):
        if os.path.exists("conf_info.txt"):
            with open("conf_info.txt", "r") as file:
                lines = file.readlines()
                if len(lines) >= 2:
                    self.userid_entry.insert(0, lines[0].strip())
                    self.file_time_entry.insert(0, lines[1].strip())

    def create_monitor_subfolders(self, base_path):
        with mss.mss() as sct:
            for i in range(1, len(sct.monitors)):
                folder_path = os.path.join(base_path, str(i))
                os.makedirs(folder_path, exist_ok=True)


if __name__ == "__main__":
    app = App()
    app.mainloop()
