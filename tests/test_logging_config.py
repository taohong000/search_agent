import logging
import tempfile
import unittest
from pathlib import Path

from search_agent.logging_config import configure_logging, get_logger


class LoggingConfigTests(unittest.TestCase):
    def test_configure_logging_writes_to_file_by_default_style(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "logs" / "search-agent.log"
            configure_logging(enabled=True, level="INFO", file_path=log_path)
            logger = get_logger("test")

            logger.info("tool_loop step=%s", 1)
            for handler in logging.getLogger("search_agent").handlers:
                handler.flush()

            content = log_path.read_text(encoding="utf-8")
            configure_logging(enabled=False)

        self.assertIn("INFO search_agent.test tool_loop step=1", content)

    def test_configure_logging_can_disable_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "logs" / "search-agent.log"
            configure_logging(enabled=False, file_path=log_path)
            logger = get_logger("test")

            logger.error("should not be written")

        self.assertFalse(log_path.exists())


if __name__ == "__main__":
    unittest.main()
