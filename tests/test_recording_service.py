import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from app_config import AppConfig
from recording_service import AudioRecordingService, ScreenRecordingService


class CursorOverlayTests(unittest.TestCase):
    def test_cursor_is_alpha_blended_and_clipped_at_monitor_edge(self):
        frame = np.zeros((3, 3, 3), dtype=np.uint8)
        cursor = np.zeros((2, 2, 4), dtype=np.uint8)
        cursor[:, :, :3] = 200
        cursor[:, :, 3] = 128
        monitor = {"left": 10, "top": 20}

        ScreenRecordingService._overlay_cursor(frame, cursor, monitor, 9, 19)

        self.assertTrue(np.all(frame[0, 0] == 100))
        self.assertEqual(int(frame[1, 1, 0]), 0)


class ScreenLifecycleTests(unittest.TestCase):
    def test_stop_finalizes_current_segment_and_reports_lifecycle(self):
        frame_written = threading.Event()

        class FakeWriter:
            def __init__(self, path, *_args):
                self.path = Path(path)
                self.path.touch()

            def isOpened(self):
                return True

            def write(self, _frame):
                frame_written.set()

            def release(self):
                pass

        class FakeCapture:
            monitors = [
                {"left": 0, "top": 0, "width": 4, "height": 4},
                {"left": 0, "top": 0, "width": 4, "height": 4},
            ]

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                pass

            def grab(self, _monitor):
                return np.zeros((4, 4, 4), dtype=np.uint8)

        fake_cv2 = types.SimpleNamespace(
            IMREAD_UNCHANGED=-1,
            COLOR_BGRA2BGR=1,
            VideoWriter_fourcc=lambda *_args: 0,
            VideoWriter=FakeWriter,
            imread=lambda *_args: None,
            cvtColor=lambda frame, _mode: frame[:, :, :3],
            resize=lambda frame, _size: frame,
        )
        fake_mss = types.SimpleNamespace(mss=FakeCapture)
        fake_pyautogui = types.SimpleNamespace(position=lambda: (100, 100))

        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            sys.modules, {"cv2": fake_cv2, "mss": fake_mss, "pyautogui": fake_pyautogui}
        ):
            events = []
            service = ScreenRecordingService(lambda event, message: events.append((event, message)))
            config = AppConfig(
                user_id="test user",
                segment_minutes=1,
                output_path=temporary,
                fps=5,
                scale_percent=100,
            )

            service.start(config)
            self.assertTrue(frame_written.wait(timeout=2))
            service.stop()

            videos = list((Path(temporary) / "Monitor_1").glob("*.avi"))
            self.assertEqual(len(videos), 1)
            self.assertNotIn(".part.", videos[0].name)
            self.assertFalse(service.is_recording)
            self.assertEqual(events[0][0], "screen_started")
            self.assertIn("screen_file", [event for event, _message in events])
            self.assertEqual(events[-1][0], "screen_stopped")


class AudioLifecycleTests(unittest.TestCase):
    def test_audio_streams_to_disk_and_finalizes_on_stop(self):
        frame_read = threading.Event()

        class FakeStream:
            def read(self, _size, exception_on_overflow=False):
                self.exception_on_overflow = exception_on_overflow
                frame_read.set()
                frame_read.wait(0.002)
                return b"\x00\x00" * 1_024

            def stop_stream(self):
                pass

            def close(self):
                pass

        class FakeAudio:
            def open(self, **_kwargs):
                return FakeStream()

            def get_sample_size(self, _format):
                return 2

            def terminate(self):
                pass

        fake_pyaudio = types.SimpleNamespace(paInt16=8, PyAudio=FakeAudio)

        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            sys.modules, {"pyaudio": fake_pyaudio}
        ):
            events = []
            service = AudioRecordingService(lambda event, message: events.append((event, message)))
            config = AppConfig(output_path=temporary)

            service.start(config)
            self.assertTrue(frame_read.wait(timeout=2))
            service.stop()

            audio_files = list((Path(temporary) / "Audio").glob("*.wav"))
            self.assertEqual(len(audio_files), 1)
            self.assertGreater(audio_files[0].stat().st_size, 44)
            self.assertFalse(service.is_recording)
            self.assertIn("audio_started", [event for event, _message in events])
            self.assertIn("audio_file", [event for event, _message in events])
            self.assertEqual(events[-1][0], "audio_stopped")


if __name__ == "__main__":
    unittest.main()
