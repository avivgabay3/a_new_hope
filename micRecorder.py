import threading
from datetime import time
import datetime
import customtkinter as ctk
import pyaudio
import wave
import ffmpeg
import os
# Set theme and appearance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class Recorder:
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("Microphone Recorder")
        self.root.geometry("300x200")

        self.label = ctk.CTkLabel(master=self.root, text="Press to Start/Stop Recording 🎤", font=ctk.CTkFont(size=16))
        self.label.pack(pady=20)

        self.button = ctk.CTkButton(master=self.root, text="🎤", command=self.click_handle, width=80, height=40, font=ctk.CTkFont(size=20))
        self.button.pack(pady=10)

        self.status = ctk.CTkLabel(master=self.root, text="Status: Idle", text_color="gray")
        self.status.pack(pady=10)
        self.recording = False
        self.root.mainloop()

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


    def start_recording(self):
        audio = pyaudio.PyAudio()
        stream = audio.open(format=pyaudio.paInt16,channels=1,rate=44100,input=True,frames_per_buffer=1024)
        frames = []
        start = datetime.datetime.now()
        file_name = start.datetime.strftime("%Y%m%d%H%M%S")
        file_path = f'{file_name}.wav'
        while self.recording:
            data = stream.read(1024)
            frames.append(data)

            passed = time.time() - start
            secs = passed % 60
            mins = passed // 60
            hours = mins // 60
            self.label.configure(text=f"{int(hours):02d}:{int(mins):02d}:{int(secs):02d}")


        # if we reached the end of the recording, terminate and save to an appropriate file
        stream.stop_stream()
        stream.close()
        audio.terminate()

        sound_file = wave.open(file_path, 'wb')
        sound_file.setnchannels(1)  # Mono
        sound_file.setsampwidth(audio.get_sample_size(pyaudio.paInt16))  # 16-bit
        sound_file.setframerate(44100)
        sound_file.writeframes(b''.join(frames))
        sound_file.close()

def get_audio_files(audio_folder):
    """Get all the audio files from the folder sorted by timestamp."""
    audio_files = []
    for file in os.listdir(audio_folder):
        if file.endswith(".wav"):
            timestamp_str = file.split(".wav")[0]  # Extract timestamp from filename
            timestamp = datetime.datetime.strptime(timestamp_str, "%Y%m%d%H%M%S")
            audio_files.append((file, timestamp))
    audio_files.sort(key=lambda x: x[1])  # Sort by timestamp
    return audio_files


def convert_video_filename_to_datetime(video_filename):
    """Helper function to convert the video filename to a datetime object."""
    try:
        # Assuming the filename format is 'recording_dd-mm-yyyy_hh-mm-ss'
        base_name = os.path.basename(video_filename)
        date_str = base_name.split("_")[1:]  # Get 'dd-mm-yyyy_hh-mm-ss'
        date_str = " ".join(date_str).replace("-", ":")  # Replace '-' with ':' for proper time formatting

        # Convert to datetime object
        video_datetime = datetime.datetime.strptime(date_str, "%d:%m:%Y %H:%M:%S")
        return video_datetime
    except Exception as e:
        print(f"Error parsing video filename: {e}")
        return None

def create_video_with_audio(video_file, audio_folder, output_file, file_time):
    """Insert audio into video file at the appropriate times."""
    audio_files = get_audio_files(audio_folder)

    # Convert video filename to datetime object for comparison
    video_start_time = convert_video_filename_to_datetime(video_file)
    if not video_start_time:
        print(f"Error: Unable to parse the video filename {video_file}")
        return

    # Initialize the video stream with FFmpeg
    video_stream = ffmpeg.input(video_file)

    # Process each audio file and match it to the correct timestamp in the video
    audio_streams = []
    for audio_file, audio_time in audio_files:
        # Calculate the offset (in seconds) where this audio file should start in the video
        start_time = (audio_time - video_start_time).total_seconds()
        if start_time < 0:
            continue  # Skip if the audio is before the video

        audio_stream = ffmpeg.input(os.path.join(audio_folder, audio_file))
        audio_stream = audio_stream.filter('atempo', 1.0)  # Adjust audio speed if needed
        audio_streams.append({'input': audio_stream, 'start': start_time})

    # Combine video and audio
    video_with_audio = video_stream
    for stream in audio_streams:
        video_with_audio = video_with_audio.output(stream['input'], output_file, shortest=None, vcodec='copy', acodec='libmp3lame', ss=stream['start'])

    # Execute FFmpeg command to merge video and audio
    ffmpeg.run(video_with_audio)


def main():
    video_path = 'C:/Users/user/Documents/Monitor_2/recording_29-04-2025_08-51-46.avi'
    audio_folder = 'C:/sound_files/'
    output_file = 'test.avi'
    create_video_with_audio(video_path, audio_folder, output_file, datetime.datetime.now())


if __name__ == '__main__':
    main()
