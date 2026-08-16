"""Configuration and application-path helpers for A New Hope."""

from __future__ import annotations

import ast
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Iterable


APP_NAME = "A New Hope"
CONFIG_VERSION = 1


def resource_path(filename: str) -> Path:
    """Return an asset path in both source and PyInstaller builds."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / filename


def user_config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / APP_NAME


def default_recordings_dir() -> Path:
    return Path.home() / "Documents" / f"{APP_NAME} Recordings"


def safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return cleaned.strip("._") or "user"


@dataclass
class AppConfig:
    user_id: str = "User"
    segment_minutes: int = 15
    output_path: str = field(default_factory=lambda: str(default_recordings_dir()))
    fps: int = 5
    scale_percent: int = 80
    start_recording_on_launch: bool = False

    @property
    def output_dir(self) -> Path:
        return Path(self.output_path).expanduser()

    @property
    def scale_factor(self) -> float:
        return self.scale_percent / 100.0

    def validate(self, create_output: bool = False) -> list[str]:
        errors: list[str] = []
        if not self.user_id.strip():
            errors.append("User ID is required.")
        if not 1 <= self.segment_minutes <= 1_440:
            errors.append("File length must be between 1 and 1,440 minutes.")
        if not 1 <= self.fps <= 30:
            errors.append("Frame rate must be between 1 and 30 FPS.")
        if not 25 <= self.scale_percent <= 100:
            errors.append("Resolution must be between 25% and 100%.")
        if not self.output_path.strip():
            errors.append("A recordings folder is required.")
        elif create_output:
            try:
                self.output_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                errors.append(f"The recordings folder cannot be created: {exc}")
        return errors


class ConfigStore:
    def __init__(self, config_dir: Path | None = None, legacy_paths: Iterable[Path] = ()) -> None:
        self.config_dir = config_dir or user_config_dir()
        self.path = self.config_dir / "config.json"
        self.legacy_paths = tuple(legacy_paths) or (resource_path("conf_info.txt"),)

    def load(self) -> AppConfig:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                return self._from_mapping(data)
            except (OSError, ValueError, TypeError):
                # A damaged settings file should not prevent the app from opening.
                return AppConfig()

        migrated = self._load_legacy()
        if migrated is not None:
            try:
                self.save(migrated)
            except (OSError, ValueError):
                pass
            return migrated
        return AppConfig()

    def save(self, config: AppConfig) -> None:
        errors = config.validate(create_output=True)
        if errors:
            raise ValueError("\n".join(errors))

        self.config_dir.mkdir(parents=True, exist_ok=True)
        payload = {"version": CONFIG_VERSION, **asdict(config)}
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    @staticmethod
    def _from_mapping(data: object) -> AppConfig:
        if not isinstance(data, dict):
            raise ValueError("Configuration must be an object")
        return AppConfig(
            user_id=str(data.get("user_id", "User")),
            segment_minutes=int(data.get("segment_minutes", 15)),
            output_path=str(data.get("output_path") or default_recordings_dir()),
            fps=int(data.get("fps", 5)),
            scale_percent=int(data.get("scale_percent", 80)),
            start_recording_on_launch=bool(data.get("start_recording_on_launch", False)),
        )

    def _load_legacy(self) -> AppConfig | None:
        for legacy_path in self.legacy_paths:
            try:
                lines = legacy_path.read_text(encoding="utf-8").splitlines()
                if len(lines) < 3:
                    continue
                raw_paths = ast.literal_eval(lines[2].strip())
                paths = raw_paths if isinstance(raw_paths, list) else [raw_paths]
                output_path = str(paths[-1]).strip() if paths else ""
                windows_path = PureWindowsPath(output_path)
                is_bundled_placeholder = (
                    len(windows_path.parts) >= 3
                    and windows_path.parts[1].lower() == "users"
                    and windows_path.parts[2].lower() == "user"
                )
                if is_bundled_placeholder or (
                    sys.platform != "win32" and windows_path.drive
                ):
                    output_path = ""
                return AppConfig(
                    user_id=lines[0].strip() or "User",
                    segment_minutes=int(lines[1].strip()),
                    output_path=output_path or str(default_recordings_dir()),
                )
            except (OSError, ValueError, SyntaxError, TypeError):
                continue
        return None
