"""Threaded screen and microphone recording services."""

from __future__ import annotations

import threading
import time
import wave
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from app_config import AppConfig, resource_path, safe_filename


EventCallback = Callable[[str, str], None]


class RecordingError(RuntimeError):
    pass


@dataclass(frozen=True)
class ScreenRecordingProgress:
    session_seconds: float
    segment_seconds: float
    segment_duration_seconds: int
    segment_number: int

    @property
    def fraction(self) -> float:
        if self.segment_duration_seconds <= 0:
            return 0.0
        return min(1.0, self.segment_seconds / self.segment_duration_seconds)


def _missing_dependency(exc: ModuleNotFoundError) -> RecordingError:
    package = exc.name or "a required package"
    return RecordingError(
        f"Missing dependency '{package}'. Install the packages in requirements.txt and try again."
    )


class ScreenRecordingService:
    """Record each connected monitor into timestamped AVI segments."""

    def __init__(self, on_event: EventCallback | None = None) -> None:
        self._on_event = on_event or (lambda _event, _message: None)
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._threads: list[threading.Thread] = []
        self._running = False
        self._started_at: float | None = None
        self._segment_started_at: float | None = None
        self._segment_duration_seconds = 0
        self._segment_number = 0

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._running

    def progress(self, now: float | None = None) -> ScreenRecordingProgress | None:
        """Return a thread-safe snapshot for the GUI progress display."""
        with self._lock:
            if (
                not self._running
                or self._started_at is None
                or self._segment_started_at is None
                or self._segment_duration_seconds <= 0
            ):
                return None
            current_time = time.monotonic() if now is None else now
            session_seconds = max(0.0, current_time - self._started_at)
            raw_segment_seconds = max(0.0, current_time - self._segment_started_at)
            extra_segments, segment_seconds = divmod(
                raw_segment_seconds, self._segment_duration_seconds
            )
            return ScreenRecordingProgress(
                session_seconds=session_seconds,
                segment_seconds=segment_seconds,
                segment_duration_seconds=self._segment_duration_seconds,
                segment_number=max(1, self._segment_number + int(extra_segments)),
            )

    def start(self, config: AppConfig) -> None:
        with self._lock:
            if self._running:
                return
            errors = config.validate(create_output=True)
            if errors:
                raise RecordingError("\n".join(errors))

            try:
                import cv2  # noqa: F401
                import mss
                import numpy  # noqa: F401
            except ModuleNotFoundError as exc:
                raise _missing_dependency(exc) from exc

            try:
                with mss.mss() as capture:
                    monitors = [dict(monitor) for monitor in capture.monitors[1:]]
            except Exception as exc:
                raise RecordingError(f"Could not access the displays: {exc}") from exc
            if not monitors:
                raise RecordingError("No displays were detected.")

            self._stop_event.clear()
            self._running = True
            started_at = time.monotonic()
            self._started_at = started_at
            self._segment_started_at = started_at
            self._segment_duration_seconds = config.segment_minutes * 60
            self._segment_number = 1
            self._threads = [
                threading.Thread(
                    target=self._record_monitor,
                    args=(monitor_id, monitor, config),
                    name=f"screen-recorder-{monitor_id}",
                    daemon=True,
                )
                for monitor_id, monitor in enumerate(monitors, start=1)
            ]
            for thread in self._threads:
                thread.start()
        self._emit("screen_started", f"Recording {len(monitors)} display(s)")

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._stop_event.set()
            threads = list(self._threads)

        for thread in threads:
            thread.join(timeout=5)

        with self._lock:
            still_alive = [thread for thread in threads if thread.is_alive()]
            self._threads = still_alive
            self._running = bool(still_alive)
            if not still_alive:
                self._clear_progress()
        if still_alive:
            self._emit("screen_error", "Some display recorders did not stop cleanly.")
        else:
            self._emit("screen_stopped", "Screen recording stopped")

    def _record_monitor(self, monitor_id: int, monitor: dict, config: AppConfig) -> None:
        import cv2
        import mss
        import numpy as np

        try:
            import pyautogui
        except Exception:
            pyautogui = None

        output_dir = config.output_dir / f"Monitor_{monitor_id}"
        output_dir.mkdir(parents=True, exist_ok=True)
        # Many video codecs require even dimensions.
        width = max(2, (int(monitor["width"] * config.scale_factor) // 2) * 2)
        height = max(2, (int(monitor["height"] * config.scale_factor) // 2) * 2)
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        segment_seconds = config.segment_minutes * 60
        segment_index = 0
        cursor = self._load_cursor(cv2)

        try:
            with mss.mss() as capture:
                while not self._stop_event.is_set():
                    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
                    stem = f"recording_{safe_filename(config.user_id)}_{stamp}"
                    temporary_path = output_dir / f"{stem}.part.avi"
                    final_path = output_dir / f"{stem}.avi"
                    writer = cv2.VideoWriter(
                        str(temporary_path), fourcc, float(config.fps), (width, height)
                    )
                    if not writer.isOpened():
                        writer.release()
                        if temporary_path.exists():
                            temporary_path.unlink()
                        raise RecordingError(f"Could not create video file in {output_dir}")

                    frames_written = 0
                    segment_started = time.monotonic()
                    segment_index += 1
                    if monitor_id == 1:
                        with self._lock:
                            self._segment_started_at = segment_started
                            self._segment_number = segment_index
                    next_frame = segment_started
                    try:
                        while (
                            not self._stop_event.is_set()
                            and time.monotonic() - segment_started < segment_seconds
                        ):
                            frame = np.asarray(capture.grab(monitor))
                            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                            if cursor is not None and pyautogui is not None:
                                try:
                                    mouse_x, mouse_y = pyautogui.position()
                                    self._overlay_cursor(frame, cursor, monitor, mouse_x, mouse_y)
                                except Exception:
                                    pass
                            if config.scale_factor != 1.0:
                                frame = cv2.resize(frame, (width, height))
                            writer.write(frame)
                            frames_written += 1
                            next_frame += 1.0 / config.fps
                            self._stop_event.wait(max(0.0, next_frame - time.monotonic()))
                    finally:
                        writer.release()
                        if frames_written:
                            temporary_path.replace(final_path)
                            self._emit("screen_file", str(final_path))
                        elif temporary_path.exists():
                            temporary_path.unlink()
        except Exception as exc:
            self._emit("screen_error", f"Display {monitor_id}: {exc}")
        finally:
            # A worker may fail while the other displays continue recording.
            if all(thread is threading.current_thread() or not thread.is_alive() for thread in self._threads):
                with self._lock:
                    self._running = False
                    self._clear_progress()

    @staticmethod
    def _load_cursor(cv2):
        cursor = cv2.imread(str(resource_path("cursor.png")), cv2.IMREAD_UNCHANGED)
        if cursor is None or len(cursor.shape) != 3 or cursor.shape[2] != 4:
            return None
        return cv2.resize(cursor, (20, 20))

    @staticmethod
    def _overlay_cursor(frame, cursor, monitor: dict, mouse_x: int, mouse_y: int) -> None:
        import numpy as np

        relative_x = int(mouse_x - monitor["left"])
        relative_y = int(mouse_y - monitor["top"])
        cursor_height, cursor_width = cursor.shape[:2]
        x1, y1 = max(0, relative_x), max(0, relative_y)
        x2 = min(frame.shape[1], relative_x + cursor_width)
        y2 = min(frame.shape[0], relative_y + cursor_height)
        if x1 >= x2 or y1 >= y2:
            return

        cursor_x1, cursor_y1 = x1 - relative_x, y1 - relative_y
        cursor_slice = cursor[
            cursor_y1 : cursor_y1 + (y2 - y1), cursor_x1 : cursor_x1 + (x2 - x1)
        ]
        alpha = cursor_slice[:, :, 3:4].astype(np.float32) / 255.0
        region = frame[y1:y2, x1:x2].astype(np.float32)
        blended = alpha * cursor_slice[:, :, :3] + (1.0 - alpha) * region
        frame[y1:y2, x1:x2] = blended.astype(frame.dtype)

    def _emit(self, event: str, message: str) -> None:
        try:
            self._on_event(event, message)
        except Exception:
            pass

    def _clear_progress(self) -> None:
        self._started_at = None
        self._segment_started_at = None
        self._segment_duration_seconds = 0
        self._segment_number = 0


class AudioRecordingService:
    """Record one microphone session to a safely finalized WAV file."""

    def __init__(self, on_event: EventCallback | None = None) -> None:
        self._on_event = on_event or (lambda _event, _message: None)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._running = False
        self.started_at: float | None = None

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._running

    def start(self, config: AppConfig) -> None:
        with self._lock:
            if self._running:
                return
            errors = config.validate(create_output=True)
            if errors:
                raise RecordingError("\n".join(errors))
            try:
                import pyaudio  # noqa: F401
            except ModuleNotFoundError as exc:
                raise _missing_dependency(exc) from exc

            self._stop_event.clear()
            self._running = True
            self.started_at = time.monotonic()
            self._thread = threading.Thread(
                target=self._record, args=(config,), name="microphone-recorder", daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._stop_event.set()
            thread = self._thread
        if thread is not None:
            thread.join(timeout=5)

    def _record(self, config: AppConfig) -> None:
        import pyaudio

        audio = None
        stream = None
        sound_file = None
        temporary_path = None
        final_path = None
        frames_written = 0
        try:
            output_dir = config.output_dir / "Audio"
            output_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
            stem = f"audio_{safe_filename(config.user_id)}_{stamp}"
            temporary_path = output_dir / f"{stem}.part.wav"
            final_path = output_dir / f"{stem}.wav"
            audio = pyaudio.PyAudio()
            stream = audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=44_100,
                input=True,
                frames_per_buffer=1_024,
            )
            sound_file = wave.open(str(temporary_path), "wb")
            sound_file.setnchannels(1)
            sound_file.setsampwidth(audio.get_sample_size(pyaudio.paInt16))
            sound_file.setframerate(44_100)
            self._emit("audio_started", "Microphone recording started")
            while not self._stop_event.is_set():
                data = stream.read(1_024, exception_on_overflow=False)
                sound_file.writeframesraw(data)
                frames_written += 1
        except Exception as exc:
            self._emit("audio_error", str(exc))
        finally:
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            if sound_file is not None:
                try:
                    sound_file.close()
                except Exception:
                    pass
            if audio is not None:
                try:
                    audio.terminate()
                except Exception:
                    pass

            if frames_written and temporary_path is not None and final_path is not None:
                try:
                    temporary_path.replace(final_path)
                    self._emit("audio_file", str(final_path))
                except Exception as exc:
                    self._emit("audio_error", f"Could not save audio: {exc}")
            elif temporary_path is not None and temporary_path.exists():
                try:
                    temporary_path.unlink()
                except OSError:
                    pass

            with self._lock:
                self._running = False
                self.started_at = None
            self._emit("audio_stopped", "Microphone recording stopped")

    def _emit(self, event: str, message: str) -> None:
        try:
            self._on_event(event, message)
        except Exception:
            pass
"""Threaded screen and microphone recording services."""

from __future__ import annotations

import threading
import time
import wave
from datetime import datetime
from typing import Callable

from app_config import AppConfig, resource_path, safe_filename


EventCallback = Callable[[str, str], None]


class RecordingError(RuntimeError):
    pass


def _missing_dependency(exc: ModuleNotFoundError) -> RecordingError:
    package = exc.name or "a required package"
    return RecordingError(
        f"Missing dependency '{package}'. Install the packages in requirements.txt and try again."
    )


class ScreenRecordingService:
    """Record each connected monitor into timestamped AVI segments."""

    def __init__(self, on_event: EventCallback | None = None) -> None:
        self._on_event = on_event or (lambda _event, _message: None)
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._threads: list[threading.Thread] = []
        self._running = False

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._running

    def start(self, config: AppConfig) -> None:
        with self._lock:
            if self._running:
                return
            errors = config.validate(create_output=True)
            if errors:
                raise RecordingError("\n".join(errors))

            try:
                import cv2  # noqa: F401
                import mss
                import numpy  # noqa: F401
            except ModuleNotFoundError as exc:
                raise _missing_dependency(exc) from exc

            try:
                with mss.mss() as capture:
                    monitors = [dict(monitor) for monitor in capture.monitors[1:]]
            except Exception as exc:
                raise RecordingError(f"Could not access the displays: {exc}") from exc
            if not monitors:
                raise RecordingError("No displays were detected.")

            self._stop_event.clear()
            self._running = True
            self._threads = [
                threading.Thread(
                    target=self._record_monitor,
                    args=(monitor_id, monitor, config),
                    name=f"screen-recorder-{monitor_id}",
                    daemon=True,
                )
                for monitor_id, monitor in enumerate(monitors, start=1)
            ]
            for thread in self._threads:
                thread.start()
        self._emit("screen_started", f"Recording {len(monitors)} display(s)")

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._stop_event.set()
            threads = list(self._threads)

        for thread in threads:
            thread.join(timeout=5)

        with self._lock:
            still_alive = [thread for thread in threads if thread.is_alive()]
            self._threads = still_alive
            self._running = bool(still_alive)
        if still_alive:
            self._emit("screen_error", "Some display recorders did not stop cleanly.")
        else:
            self._emit("screen_stopped", "Screen recording stopped")

    def _record_monitor(self, monitor_id: int, monitor: dict, config: AppConfig) -> None:
        import cv2
        import mss
        import numpy as np

        try:
            import pyautogui
        except Exception:
            pyautogui = None

        output_dir = config.output_dir / f"Monitor_{monitor_id}"
        output_dir.mkdir(parents=True, exist_ok=True)
        # Many video codecs require even dimensions.
        width = max(2, (int(monitor["width"] * config.scale_factor) // 2) * 2)
        height = max(2, (int(monitor["height"] * config.scale_factor) // 2) * 2)
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        segment_seconds = config.segment_minutes * 60
        cursor = self._load_cursor(cv2)

        try:
            with mss.mss() as capture:
                while not self._stop_event.is_set():
                    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
                    stem = f"recording_{safe_filename(config.user_id)}_{stamp}"
                    temporary_path = output_dir / f"{stem}.part.avi"
                    final_path = output_dir / f"{stem}.avi"
                    writer = cv2.VideoWriter(
                        str(temporary_path), fourcc, float(config.fps), (width, height)
                    )
                    if not writer.isOpened():
                        writer.release()
                        if temporary_path.exists():
                            temporary_path.unlink()
                        raise RecordingError(f"Could not create video file in {output_dir}")

                    frames_written = 0
                    segment_started = time.monotonic()
                    next_frame = segment_started
                    try:
                        while (
                            not self._stop_event.is_set()
                            and time.monotonic() - segment_started < segment_seconds
                        ):
                            frame = np.asarray(capture.grab(monitor))
                            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                            if cursor is not None and pyautogui is not None:
                                try:
                                    mouse_x, mouse_y = pyautogui.position()
                                    self._overlay_cursor(frame, cursor, monitor, mouse_x, mouse_y)
                                except Exception:
                                    pass
                            if config.scale_factor != 1.0:
                                frame = cv2.resize(frame, (width, height))
                            writer.write(frame)
                            frames_written += 1
                            next_frame += 1.0 / config.fps
                            self._stop_event.wait(max(0.0, next_frame - time.monotonic()))
                    finally:
                        writer.release()
                        if frames_written:
                            temporary_path.replace(final_path)
                            self._emit("screen_file", str(final_path))
                        elif temporary_path.exists():
                            temporary_path.unlink()
        except Exception as exc:
            self._emit("screen_error", f"Display {monitor_id}: {exc}")
        finally:
            # A worker may fail while the other displays continue recording.
            if all(thread is threading.current_thread() or not thread.is_alive() for thread in self._threads):
                with self._lock:
                    self._running = False

    @staticmethod
    def _load_cursor(cv2):
        cursor = cv2.imread(str(resource_path("cursor.png")), cv2.IMREAD_UNCHANGED)
        if cursor is None or len(cursor.shape) != 3 or cursor.shape[2] != 4:
            return None
        return cv2.resize(cursor, (20, 20))

    @staticmethod
    def _overlay_cursor(frame, cursor, monitor: dict, mouse_x: int, mouse_y: int) -> None:
        import numpy as np

        relative_x = int(mouse_x - monitor["left"])
        relative_y = int(mouse_y - monitor["top"])
        cursor_height, cursor_width = cursor.shape[:2]
        x1, y1 = max(0, relative_x), max(0, relative_y)
        x2 = min(frame.shape[1], relative_x + cursor_width)
        y2 = min(frame.shape[0], relative_y + cursor_height)
        if x1 >= x2 or y1 >= y2:
            return

        cursor_x1, cursor_y1 = x1 - relative_x, y1 - relative_y
        cursor_slice = cursor[
            cursor_y1 : cursor_y1 + (y2 - y1), cursor_x1 : cursor_x1 + (x2 - x1)
        ]
        alpha = cursor_slice[:, :, 3:4].astype(np.float32) / 255.0
        region = frame[y1:y2, x1:x2].astype(np.float32)
        blended = alpha * cursor_slice[:, :, :3] + (1.0 - alpha) * region
        frame[y1:y2, x1:x2] = blended.astype(frame.dtype)

    def _emit(self, event: str, message: str) -> None:
        try:
            self._on_event(event, message)
        except Exception:
            pass


class AudioRecordingService:
    """Record one microphone session to a safely finalized WAV file."""

    def __init__(self, on_event: EventCallback | None = None) -> None:
        self._on_event = on_event or (lambda _event, _message: None)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._running = False
        self.started_at: float | None = None

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._running

    def start(self, config: AppConfig) -> None:
        with self._lock:
            if self._running:
                return
            errors = config.validate(create_output=True)
            if errors:
                raise RecordingError("\n".join(errors))
            try:
                import pyaudio  # noqa: F401
            except ModuleNotFoundError as exc:
                raise _missing_dependency(exc) from exc

            self._stop_event.clear()
            self._running = True
            self.started_at = time.monotonic()
            self._thread = threading.Thread(
                target=self._record, args=(config,), name="microphone-recorder", daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._stop_event.set()
            thread = self._thread
        if thread is not None:
            thread.join(timeout=5)

    def _record(self, config: AppConfig) -> None:
        import pyaudio

        audio = None
        stream = None
        sound_file = None
        temporary_path = None
        final_path = None
        frames_written = 0
        try:
            output_dir = config.output_dir / "Audio"
            output_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
            stem = f"audio_{safe_filename(config.user_id)}_{stamp}"
            temporary_path = output_dir / f"{stem}.part.wav"
            final_path = output_dir / f"{stem}.wav"
            audio = pyaudio.PyAudio()
            stream = audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=44_100,
                input=True,
                frames_per_buffer=1_024,
            )
            sound_file = wave.open(str(temporary_path), "wb")
            sound_file.setnchannels(1)
            sound_file.setsampwidth(audio.get_sample_size(pyaudio.paInt16))
            sound_file.setframerate(44_100)
            self._emit("audio_started", "Microphone recording started")
            while not self._stop_event.is_set():
                data = stream.read(1_024, exception_on_overflow=False)
                sound_file.writeframesraw(data)
                frames_written += 1
        except Exception as exc:
            self._emit("audio_error", str(exc))
        finally:
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            if sound_file is not None:
                try:
                    sound_file.close()
                except Exception:
                    pass
            if audio is not None:
                try:
                    audio.terminate()
                except Exception:
                    pass

            if frames_written and temporary_path is not None and final_path is not None:
                try:
                    temporary_path.replace(final_path)
                    self._emit("audio_file", str(final_path))
                except Exception as exc:
                    self._emit("audio_error", f"Could not save audio: {exc}")
            elif temporary_path is not None and temporary_path.exists():
                try:
                    temporary_path.unlink()
                except OSError:
                    pass

            with self._lock:
                self._running = False
                self.started_at = None
            self._emit("audio_stopped", "Microphone recording stopped")

    def _emit(self, event: str, message: str) -> None:
        try:
            self._on_event(event, message)
        except Exception:
            pass
