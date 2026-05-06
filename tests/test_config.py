import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from search_agent.config import Settings


class SettingsTests(unittest.TestCase):
    def test_reads_keys_from_environment_without_requiring_values_in_code(self):
        with patch.dict(
            os.environ,
            {
                "DASHSCOPE_API_KEY": "dashscope-test-key",
                "BOCHA_API_KEY": "bocha-test-key",
                "SEARCH_AGENT_DATA_DIR": "D:/query-agent-data",
            },
            clear=True,
        ):
            settings = Settings.from_env()

        self.assertEqual(settings.dashscope_api_key, "dashscope-test-key")
        self.assertEqual(settings.bocha_api_key, "bocha-test-key")
        self.assertEqual(settings.model, "deepseek-v4-pro")
        self.assertEqual(settings.data_dir, Path("D:/query-agent-data"))

    def test_reads_values_from_toml_config_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "search-agent.toml"
            config_path.write_text(
                """
data_dir = "D:/docs"
model = "deepseek-v4-flash"
base_url = "https://example.test/v1"

[search]
max_rounds = 2
top_k = 6

[web_fetch]
enabled = true
max_pages = 4

[secrets]
dashscope_api_key = "dashscope-from-file"
bocha_api_key = "bocha-from-file"
""".strip(),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                settings = Settings.from_sources(config_path)

        self.assertEqual(settings.data_dir, Path("D:/docs"))
        self.assertEqual(settings.model, "deepseek-v4-flash")
        self.assertEqual(settings.base_url, "https://example.test/v1")
        self.assertEqual(settings.max_rounds, 2)
        self.assertEqual(settings.max_tool_steps, 2)
        self.assertEqual(settings.top_k, 6)
        self.assertTrue(settings.web_fetch_enabled)
        self.assertEqual(settings.web_fetch_max_pages, 4)
        self.assertEqual(settings.web_fetch_max_chars, 20000)
        self.assertEqual(settings.web_fetch_timeout_seconds, 30)
        self.assertTrue(settings.log_enabled)
        self.assertEqual(settings.log_level, "INFO")
        self.assertEqual(settings.log_file, Path("logs/search-agent.log"))
        self.assertEqual(settings.dashscope_api_key, "dashscope-from-file")
        self.assertEqual(settings.bocha_api_key, "bocha-from-file")

    def test_environment_values_override_config_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "search-agent.toml"
            config_path.write_text(
                """
data_dir = "D:/docs-from-file"
model = "model-from-file"

[secrets]
dashscope_api_key = "dashscope-from-file"
""".strip(),
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {
                    "SEARCH_AGENT_DATA_DIR": "D:/docs-from-env",
                    "SEARCH_AGENT_MODEL": "model-from-env",
                    "DASHSCOPE_API_KEY": "dashscope-from-env",
                },
                clear=True,
            ):
                settings = Settings.from_sources(config_path)

        self.assertEqual(settings.data_dir, Path("D:/docs-from-env"))
        self.assertEqual(settings.model, "model-from-env")
        self.assertEqual(settings.dashscope_api_key, "dashscope-from-env")

    def test_agent_max_tool_steps_can_override_legacy_rounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "search-agent.toml"
            config_path.write_text(
                """
[search]
max_rounds = 2

[agent]
max_tool_steps = 9
""".strip(),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                settings = Settings.from_sources(config_path)

        self.assertEqual(settings.max_rounds, 2)
        self.assertEqual(settings.max_tool_steps, 9)

    def test_logging_config_can_be_disabled_and_customized(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "search-agent.toml"
            config_path.write_text(
                """
[logging]
enabled = false
level = "DEBUG"
file = "tmp/search.log"
""".strip(),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                settings = Settings.from_sources(config_path)

        self.assertFalse(settings.log_enabled)
        self.assertEqual(settings.log_level, "DEBUG")
        self.assertEqual(settings.log_file, Path("tmp/search.log"))


if __name__ == "__main__":
    unittest.main()
