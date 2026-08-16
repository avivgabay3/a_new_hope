"""System tray integration, isolated so the GUI still opens without pystray."""

from __future__ import annotations

from pathlib import Path
from typing import Callable


class TrayIcon:
    def __init__(
        self,
        icon_path: Path,
        on_show: Callable[[], None],
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
        on_open_folder: Callable[[], None],
        on_quit: Callable[[], None],
        is_recording: Callable[[], bool],
    ) -> None:
        self.icon_path = icon_path
        self.on_show = on_show
        self.on_start = on_start
        self.on_stop = on_stop
        self.on_open_folder = on_open_folder
        self.on_quit = on_quit
        self.is_recording = is_recording
        self._icon = None
        self.error: str | None = None

    @property
    def available(self) -> bool:
        return self._icon is not None

    def start(self) -> bool:
        try:
            import pystray
            from PIL import Image

            image = Image.open(self.icon_path).convert("RGBA")
            menu = pystray.Menu(
                pystray.MenuItem("Open A New Hope", self._callback(self.on_show), default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    "Start screen recording",
                    self._callback(self.on_start),
                    enabled=lambda _item: not self.is_recording(),
                ),
                pystray.MenuItem(
                    "Stop screen recording",
                    self._callback(self.on_stop),
                    enabled=lambda _item: self.is_recording(),
                ),
                pystray.MenuItem("Open recordings folder", self._callback(self.on_open_folder)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", self._callback(self.on_quit)),
            )
            self._icon = pystray.Icon("a_new_hope", image, "A New Hope", menu)
            self._icon.run_detached()
            return True
        except Exception as exc:
            self.error = str(exc)
            self._icon = None
            return False

    def refresh(self) -> None:
        if self._icon is not None:
            try:
                self._icon.update_menu()
            except Exception:
                pass

    def notify(self, message: str, title: str = "A New Hope") -> None:
        if self._icon is not None:
            try:
                self._icon.notify(message, title)
            except Exception:
                pass

    def stop(self) -> None:
        icon, self._icon = self._icon, None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass

    @staticmethod
    def _callback(callback: Callable[[], None]):
        def invoke(_icon, _item) -> None:
            callback()

        return invoke
