import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app_config import AppConfig, ConfigStore, safe_filename


class AppConfigTests(unittest.TestCase):
    def test_round_trip_creates_output_and_preserves_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = ConfigStore(root / "settings", legacy_paths=(root / "missing.txt",))
            expected = AppConfig(
                user_id="operator-7",
                segment_minutes=4,
                output_path=str(root / "recordings"),
                fps=8,
                scale_percent=70,
                start_recording_on_launch=True,
            )

            store.save(expected)
            actual = store.load()

            self.assertEqual(actual, expected)
            self.assertTrue(expected.output_dir.is_dir())
            self.assertEqual(json.loads(store.path.read_text())["version"], 1)

    def test_validation_reports_every_invalid_field(self):
        config = AppConfig(
            user_id=" ", segment_minutes=0, output_path=" ", fps=31, scale_percent=10
        )
        errors = config.validate()
        self.assertEqual(len(errors), 5)

    def test_damaged_json_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = ConfigStore(root, legacy_paths=(root / "missing.txt",))
            store.path.write_text("not json", encoding="utf-8")
            self.assertEqual(store.load().user_id, "User")

    @patch("app_config.sys.platform", "linux")
    def test_legacy_windows_path_is_not_migrated_on_other_platforms(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy = root / "conf_info.txt"
            legacy.write_text("old-user\n10\n['C:\\\\Users\\\\someone\\\\Videos']\n", encoding="utf-8")
            store = ConfigStore(root / "settings", legacy_paths=(legacy,))

            migrated = store.load()

            self.assertEqual(migrated.user_id, "old-user")
            self.assertNotIn("C:", migrated.output_path)

    def test_bundled_placeholder_path_is_ignored(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy = root / "conf_info.txt"
            legacy.write_text("user\n15\n['C:\\\\Users\\\\user\\\\Documents']\n", encoding="utf-8")
            store = ConfigStore(root / "settings", legacy_paths=(legacy,))
            migrated = store.load()
            self.assertNotIn("Users\\\\user", migrated.output_path)

    def test_user_id_becomes_a_safe_filename_component(self):
        self.assertEqual(safe_filename(" Alice / Lab 7 "), "Alice_Lab_7")
        self.assertEqual(safe_filename("..."), "user")


if __name__ == "__main__":
    unittest.main()
