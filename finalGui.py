"""Unified desktop UI and application lifecycle for A New Hope."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageTk

from app_config import AppConfig, ConfigStore, resource_path
from recording_service import AudioRecordingService, RecordingError, ScreenRecordingService
from tray_icon import TrayIcon


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("A New Hope")
        self.geometry("720x590")
        self.minsize(660, 540)
        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self._quitting = False
        self._hidden_notice_shown = False
        self._ui_queue: queue.Queue[tuple[object, tuple]] = queue.Queue()

        self.store = ConfigStore()
        self.config = self.store.load()
        self.screen_recorder = ScreenRecordingService(self._service_event)
        self.audio_recorder = AudioRecordingService(self._service_event)
        self._set_window_icon()
        self._build_ui()
        self._load_settings_into_form()

        self.tray = TrayIcon(
            resource_path("app_icon.png"),
            on_show=lambda: self._enqueue(self.show_window),
            on_start=lambda: self._enqueue(self.start_screen_recording),
            on_stop=lambda: self._enqueue(self.stop_screen_recording),
            on_open_folder=lambda: self._enqueue(self.open_recordings_folder),
            on_quit=lambda: self._enqueue(self.quit_application),
            is_recording=lambda: self.screen_recorder.is_recording,
        )
        if self.tray.start():
            self.tray_status.configure(text="Tray: ready", text_color="#69c779")
        else:
            detail = self.tray.error or "pystray is unavailable"
            self.tray_status.configure(text=f"Tray unavailable: {detail}", text_color="#e3a64b")

        self.after(100, self._drain_ui_queue)
        self.after(250, self._update_screen_progress)
        self.after(250, self._update_audio_timer)
        if self.config.start_recording_on_launch:
            self.after(500, self.start_screen_recording)

    def _set_window_icon(self) -> None:
        try:
            image = Image.open(resource_path("app_icon.png"))
            self._icon_photo = ImageTk.PhotoImage(image)
            self.iconphoto(True, self._icon_photo)
        except Exception:
            self._icon_photo = None

    def _build_ui(self) -> None:
        header = ctk.CTkFrame(self, corner_radius=0, fg_color=("#e9eef6", "#16202d"))
        header.pack(fill="x")
        ctk.CTkLabel(
            header, text="A New Hope", font=ctk.CTkFont(size=27, weight="bold")
        ).pack(side="left", padx=24, pady=18)
        self.header_status = ctk.CTkLabel(header, text="Idle", text_color="#9aa7b8")
        self.header_status.pack(side="right", padx=24)

        self.tabs = ctk.CTkTabview(self, corner_radius=12)
        self.tabs.pack(fill="both", expand=True, padx=18, pady=16)
        dashboard = self.tabs.add("Screen recording")
        audio = self.tabs.add("Microphone")
        settings = self.tabs.add("Settings")
        self._build_dashboard(dashboard)
        self._build_audio(audio)
        self._build_settings(settings)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=24, pady=(0, 12))
        self.tray_status = ctk.CTkLabel(footer, text="Tray: starting…", text_color="#9aa7b8")
        self.tray_status.pack(side="left")
        ctk.CTkButton(
            footer,
            text="Quit application",
            width=125,
            fg_color="#7f3340",
            hover_color="#9b4050",
            command=self.quit_application,
        ).pack(side="right")

    def _build_dashboard(self, parent) -> None:
        card = ctk.CTkFrame(parent)
        card.pack(fill="x", padx=22, pady=(18, 10))
        ctk.CTkLabel(card, text="SCREEN CAPTURE", text_color="#8fa1b8").pack(pady=(16, 3))
        self.screen_status = ctk.CTkLabel(
            card, text="Not recording", font=ctk.CTkFont(size=25, weight="bold")
        )
        self.screen_status.pack(pady=2)
        self.screen_timer = ctk.CTkLabel(
            card, text="Session 00:00:00", font=ctk.CTkFont(size=28, weight="bold")
        )
        self.screen_timer.pack(pady=(4, 2))
        self.segment_progress = ctk.CTkProgressBar(card, width=480, height=12)
        self.segment_progress.set(0)
        self.segment_progress.pack(pady=(8, 4))
        self.segment_progress_label = ctk.CTkLabel(
            card,
            text="Current file 00:00:00 / 00:15:00 • Segment 1 • 0%",
            text_color="#9aa7b8",
        )
        self.segment_progress_label.pack(pady=(0, 6))
        self.screen_detail = ctk.CTkLabel(
            card,
            text="Press Start when you are ready.",
            text_color="#9aa7b8",
            wraplength=560,
        )
        self.screen_detail.pack(pady=(2, 10))

        controls = ctk.CTkFrame(card, fg_color="transparent")
        controls.pack(pady=(0, 16))
        self.start_screen_button = ctk.CTkButton(
            controls,
            text="Start recording",
            width=160,
            height=42,
            command=self.start_screen_recording,
        )
        self.start_screen_button.pack(side="left", padx=7)
        self.stop_screen_button = ctk.CTkButton(
            controls,
            text="Stop recording",
            width=160,
            height=42,
            state="disabled",
            fg_color="#7f3340",
            hover_color="#9b4050",
            command=self.stop_screen_recording,
        )
        self.stop_screen_button.pack(side="left", padx=7)

        self.output_label = ctk.CTkLabel(parent, text="", text_color="#9aa7b8", wraplength=580)
        self.output_label.pack(pady=(8, 6))
        ctk.CTkButton(
            parent,
            text="Open recordings folder",
            width=190,
            command=self.open_recordings_folder,
        ).pack(pady=7)

    def _build_audio(self, parent) -> None:
        card = ctk.CTkFrame(parent)
        card.pack(fill="x", padx=22, pady=(28, 14))
        ctk.CTkLabel(card, text="MICROPHONE", text_color="#8fa1b8").pack(pady=(22, 5))
        self.audio_timer = ctk.CTkLabel(
            card, text="00:00:00", font=ctk.CTkFont(size=35, weight="bold")
        )
        self.audio_timer.pack(pady=6)
        self.audio_status = ctk.CTkLabel(card, text="Not recording", text_color="#9aa7b8")
        self.audio_status.pack(pady=(0, 18))

        controls = ctk.CTkFrame(card, fg_color="transparent")
        controls.pack(pady=(0, 24))
        self.start_audio_button = ctk.CTkButton(
            controls, text="Start microphone", width=160, command=self.start_audio_recording
        )
        self.start_audio_button.pack(side="left", padx=7)
        self.stop_audio_button = ctk.CTkButton(
            controls,
            text="Stop microphone",
            width=160,
            state="disabled",
            fg_color="#7f3340",
            hover_color="#9b4050",
            command=self.stop_audio_recording,
        )
        self.stop_audio_button.pack(side="left", padx=7)

        self.audio_output_label = ctk.CTkLabel(
            parent, text="", text_color="#9aa7b8", wraplength=580
        )
        self.audio_output_label.pack(pady=10)

    def _build_settings(self, parent) -> None:
        form = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=28, pady=18)
        form.grid_columnconfigure(1, weight=1)

        self.user_id_entry = self._settings_entry(form, 0, "User ID")
        self.segment_entry = self._settings_entry(form, 1, "File length (minutes)")

        ctk.CTkLabel(form, text="Recordings folder", anchor="w").grid(
            row=2, column=0, sticky="w", padx=(0, 14), pady=9
        )
        self.path_entry = ctk.CTkEntry(form)
        self.path_entry.grid(row=2, column=1, sticky="ew", pady=9)
        ctk.CTkButton(form, text="Browse", width=76, command=self.browse_folder).grid(
            row=2, column=2, padx=(8, 0), pady=9
        )

        self.fps_entry = self._settings_entry(form, 3, "Frame rate (FPS)")
        self.scale_entry = self._settings_entry(form, 4, "Resolution (%)")
        self.auto_start_switch = ctk.CTkSwitch(
            form, text="Start screen recording when the app opens"
        )
        self.auto_start_switch.grid(row=5, column=0, columnspan=3, sticky="w", pady=(18, 12))

        ctk.CTkButton(form, text="Save settings", height=40, command=self.save_settings).grid(
            row=6, column=0, columnspan=3, pady=18
        )
        self.settings_note = ctk.CTkLabel(
            form,
            text="Settings are stored in your user profile, not beside the executable.",
            text_color="#9aa7b8",
            wraplength=560,
        )
        self.settings_note.grid(row=7, column=0, columnspan=3, pady=5)

    @staticmethod
    def _settings_entry(parent, row: int, label: str):
        ctk.CTkLabel(parent, text=label, anchor="w").grid(
            row=row, column=0, sticky="w", padx=(0, 14), pady=9
        )
        entry = ctk.CTkEntry(parent)
        entry.grid(row=row, column=1, columnspan=2, sticky="ew", pady=9)
        return entry

    def _load_settings_into_form(self) -> None:
        values = (
            (self.user_id_entry, self.config.user_id),
            (self.segment_entry, self.config.segment_minutes),
            (self.path_entry, self.config.output_path),
            (self.fps_entry, self.config.fps),
            (self.scale_entry, self.config.scale_percent),
        )
        for entry, value in values:
            entry.delete(0, tk.END)
            entry.insert(0, str(value))
        if self.config.start_recording_on_launch:
            self.auto_start_switch.select()
        else:
            self.auto_start_switch.deselect()
        self.output_label.configure(text=f"Saving to: {self.config.output_path}")
        self._reset_screen_progress()

    def _config_from_form(self) -> AppConfig:
        try:
            return AppConfig(
                user_id=self.user_id_entry.get().strip(),
                segment_minutes=int(self.segment_entry.get()),
                output_path=self.path_entry.get().strip(),
                fps=int(self.fps_entry.get()),
                scale_percent=int(self.scale_entry.get()),
                start_recording_on_launch=bool(self.auto_start_switch.get()),
            )
        except ValueError as exc:
            raise ValueError(
                "File length, frame rate, and resolution must be whole numbers."
            ) from exc

    def save_settings(self) -> None:
        try:
            updated = self._config_from_form()
            self.store.save(updated)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Settings not saved", str(exc), parent=self)
            return

        was_recording = self.screen_recorder.is_recording
        self.config = updated
        self.output_label.configure(text=f"Saving to: {self.config.output_path}")
        self.settings_note.configure(text="Settings saved.", text_color="#69c779")
        if not was_recording:
            self._reset_screen_progress()
        if was_recording:
            self.screen_detail.configure(text="Restarting recording with the new settings…")

            def restart() -> None:
                self.screen_recorder.stop()
                try:
                    self.screen_recorder.start(self.config)
                except RecordingError as exc:
                    self._enqueue(self._show_screen_error, str(exc))

            threading.Thread(target=restart, name="settings-restart", daemon=True).start()

    def browse_folder(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.path_entry.get() or str(Path.home()))
        if selected:
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, selected)

    def start_screen_recording(self) -> None:
        if self._quitting or self.screen_recorder.is_recording:
            return
        self._reset_screen_progress()
        self.screen_status.configure(text="Starting…", text_color="#e3a64b")
        self.screen_detail.configure(text="Requesting display access and preparing the video files.")
        self.start_screen_button.configure(state="disabled")

        def start() -> None:
            try:
                self.screen_recorder.start(self.config)
            except RecordingError as exc:
                self._enqueue(self._show_screen_error, str(exc))
            except Exception as exc:
                self._enqueue(self._show_screen_error, f"Unexpected startup error: {exc}")

        threading.Thread(target=start, name="screen-start", daemon=True).start()

    def stop_screen_recording(self) -> None:
        if not self.screen_recorder.is_recording:
            return
        self.screen_status.configure(text="Stopping…", text_color="#e3a64b")
        self.stop_screen_button.configure(state="disabled")
        threading.Thread(target=self.screen_recorder.stop, name="screen-stop", daemon=True).start()

    def start_audio_recording(self) -> None:
        if self._quitting or self.audio_recorder.is_recording:
            return
        self.audio_status.configure(text="Starting…", text_color="#e3a64b")
        self.start_audio_button.configure(state="disabled")
        try:
            self.audio_recorder.start(self.config)
        except RecordingError as exc:
            self._show_audio_error(str(exc))

    def stop_audio_recording(self) -> None:
        if not self.audio_recorder.is_recording:
            return
        self.audio_status.configure(text="Stopping…", text_color="#e3a64b")
        self.stop_audio_button.configure(state="disabled")
        threading.Thread(target=self.audio_recorder.stop, name="audio-stop", daemon=True).start()

    def _service_event(self, event: str, message: str) -> None:
        self._enqueue(self._handle_service_event, event, message)

    def _handle_service_event(self, event: str, message: str) -> None:
        if self._quitting:
            return
        if event == "screen_started":
            if not self.screen_recorder.is_recording:
                return
            self.screen_status.configure(text="Recording", text_color="#69c779")
            self.screen_detail.configure(text=message)
            self.header_status.configure(text="Screen recording", text_color="#69c779")
            self.start_screen_button.configure(state="disabled")
            self.stop_screen_button.configure(state="normal")
            self.tray.notify(message)
        elif event == "screen_stopped":
            self.screen_status.configure(
                text="Not recording", text_color=("#1f2a38", "#f2f4f8")
            )
            self.screen_detail.configure(text=message)
            self.header_status.configure(text="Idle", text_color="#9aa7b8")
            self.start_screen_button.configure(state="normal")
            self.stop_screen_button.configure(state="disabled")
            self._reset_screen_progress()
            self.tray.notify(message)
        elif event == "screen_file":
            self.screen_detail.configure(text=f"Saved: {message}")
        elif event == "screen_error":
            self._show_screen_error(message)
        elif event == "audio_started":
            self.audio_status.configure(text="Recording", text_color="#69c779")
            self.start_audio_button.configure(state="disabled")
            self.stop_audio_button.configure(state="normal")
        elif event == "audio_stopped":
            self.audio_status.configure(text="Not recording", text_color="#9aa7b8")
            self.audio_timer.configure(text="00:00:00")
            self.start_audio_button.configure(state="normal")
            self.stop_audio_button.configure(state="disabled")
        elif event == "audio_file":
            self.audio_output_label.configure(text=f"Saved: {message}")
        elif event == "audio_error":
            self._show_audio_error(message)
        self.tray.refresh()

    def _show_screen_error(self, message: str) -> None:
        is_still_recording = self.screen_recorder.is_recording
        self.screen_status.configure(
            text="Recording with an error" if is_still_recording else "Recording error",
            text_color="#ef6b73",
        )
        self.screen_detail.configure(text=message)
        self.start_screen_button.configure(state="disabled" if is_still_recording else "normal")
        self.stop_screen_button.configure(
            state="normal" if is_still_recording else "disabled"
        )
        if not is_still_recording:
            self._reset_screen_progress()
        self.show_window()
        messagebox.showerror("Screen recording error", message, parent=self)

    def _show_audio_error(self, message: str) -> None:
        self.audio_status.configure(text="Microphone error", text_color="#ef6b73")
        self.start_audio_button.configure(state="normal")
        self.stop_audio_button.configure(state="disabled")
        self.show_window()
        messagebox.showerror("Microphone error", message, parent=self)

    @staticmethod
    def _format_elapsed(total_seconds: float) -> str:
        seconds = max(0, int(total_seconds))
        hours, remainder = divmod(seconds, 3_600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _reset_screen_progress(self) -> None:
        duration = self.config.segment_minutes * 60
        self.screen_timer.configure(text="Session 00:00:00")
        self.segment_progress.set(0)
        self.segment_progress_label.configure(
            text=(
                f"Current file 00:00:00 / {self._format_elapsed(duration)} "
                "• Segment 1 • 0%"
            )
        )

    def _update_screen_progress(self) -> None:
        if not self._quitting:
            progress = self.screen_recorder.progress()
            if progress is not None:
                percent = min(100, int(progress.fraction * 100))
                self.screen_timer.configure(
                    text=f"Session {self._format_elapsed(progress.session_seconds)}"
                )
                self.segment_progress.set(progress.fraction)
                self.segment_progress_label.configure(
                    text=(
                        f"Current file {self._format_elapsed(progress.segment_seconds)} / "
                        f"{self._format_elapsed(progress.segment_duration_seconds)} "
                        f"• Segment {progress.segment_number} • {percent}%"
                    )
                )
            self.after(250, self._update_screen_progress)

    def _update_audio_timer(self) -> None:
        if not self._quitting:
            if self.audio_recorder.is_recording and self.audio_recorder.started_at is not None:
                seconds = max(0, int(time.monotonic() - self.audio_recorder.started_at))
                hours, remainder = divmod(seconds, 3_600)
                minutes, seconds = divmod(remainder, 60)
                self.audio_timer.configure(text=f"{hours:02d}:{minutes:02d}:{seconds:02d}")
            self.after(250, self._update_audio_timer)

    def hide_to_tray(self) -> None:
        if self._quitting:
            return
        if self.tray.available:
            self.withdraw()
            if not self._hidden_notice_shown:
                self.tray.notify("A New Hope is still running. Use the tray menu to reopen or quit.")
                self._hidden_notice_shown = True
        else:
            # Without a working tray, iconifying keeps the application recoverable.
            self.iconify()

    def show_window(self) -> None:
        if self._quitting:
            return
        self.deiconify()
        self.lift()
        try:
            self.focus_force()
        except tk.TclError:
            pass

    def open_recordings_folder(self) -> None:
        try:
            folder = self.config.output_dir
            folder.mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(str(folder))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as exc:
            self.show_window()
            messagebox.showerror("Could not open folder", str(exc), parent=self)

    def quit_application(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        self.header_status.configure(text="Shutting down…", text_color="#e3a64b")
        self.start_screen_button.configure(state="disabled")
        self.stop_screen_button.configure(state="disabled")
        self.start_audio_button.configure(state="disabled")
        self.stop_audio_button.configure(state="disabled")
        self.tray.stop()

        def shutdown() -> None:
            self.audio_recorder.stop()
            self.screen_recorder.stop()
            self._enqueue(self.destroy)

        threading.Thread(target=shutdown, name="app-shutdown", daemon=True).start()

    def _enqueue(self, callback, *args) -> None:
        self._ui_queue.put((callback, args))

    def _drain_ui_queue(self) -> None:
        try:
            while True:
                callback, args = self._ui_queue.get_nowait()
                callback(*args)
        except queue.Empty:
            pass
        try:
            if self.winfo_exists():
                self.after(100, self._drain_ui_queue)
        except tk.TclError:
            pass


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
