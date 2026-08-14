import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from topic_pulse_v2.config import load_env_file


class EnvLoaderTests(unittest.TestCase):
    def test_load_env_file_sets_values_without_overriding_existing_env(self):
        with TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "SMTP_HOST=smtp.qq.com",
                        "SMTP_FROM_NAME=\"Topic Pulse\"",
                        "EXISTING=value-from-file",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"EXISTING": "keep-me"}, clear=False):
                loaded = load_env_file(env_path)
                self.assertEqual(loaded, env_path)
                self.assertEqual(os.environ["SMTP_HOST"], "smtp.qq.com")
                self.assertEqual(os.environ["SMTP_FROM_NAME"], "Topic Pulse")
                self.assertEqual(os.environ["EXISTING"], "keep-me")


if __name__ == "__main__":
    unittest.main()
