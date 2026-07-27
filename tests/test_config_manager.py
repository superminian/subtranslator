import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config_manager import ConfigError, load_config, save_config


class ConfigManagerTests(unittest.TestCase):
    def test_saved_config_overrides_environment_and_preserves_masked_key(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "settings.json"
            environment = {
                "CONFIG_FILE": str(config_path),
                "API_KEY": "environment-key",
                "MODEL": "environment-model",
            }
            with patch.dict(os.environ, environment, clear=True):
                save_config(
                    {
                        "API_KEY": "saved-key",
                        "MODEL": "saved-model",
                        "MAX_WORKERS": "4",
                    }
                )
                self.assertEqual(load_config()["API_KEY"], "saved-key")
                self.assertEqual(load_config()["MODEL"], "saved-model")

                save_config({"API_KEY": "***", "MAX_WORKERS": "5"})
                self.assertEqual(load_config()["API_KEY"], "saved-key")
                self.assertEqual(load_config()["MAX_WORKERS"], "5")

                mode = stat.S_IMODE(config_path.stat().st_mode)
                self.assertEqual(mode, 0o600)

    def test_invalid_worker_count_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = {
                "CONFIG_FILE": str(Path(temporary_directory) / "settings.json"),
            }
            with (
                patch.dict(os.environ, environment, clear=True),
                self.assertRaises(ConfigError),
            ):
                save_config({"MAX_WORKERS": "0"})

    def test_unknown_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = {
                "CONFIG_FILE": str(Path(temporary_directory) / "settings.json"),
            }
            with (
                patch.dict(os.environ, environment, clear=True),
                self.assertRaises(ConfigError),
            ):
                save_config({"UNKNOWN_SETTING": "value"})


if __name__ == "__main__":
    unittest.main()
