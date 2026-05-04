from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOGGER_NAME = "search_agent"


def configure_logging(
    enabled: bool = True,
    level: str = "INFO",
    file_path: str | Path = "logs/search-agent.log",
) -> None:
    logger = logging.getLogger(LOGGER_NAME)
    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()
    logger.propagate = False
    if not enabled:
        logger.addHandler(logging.NullHandler())
        logger.setLevel(logging.CRITICAL + 1)
        return

    log_path = Path(file_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_path,
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(parse_level(level))


def get_logger(name: str | None = None) -> logging.Logger:
    suffix = f".{name}" if name else ""
    return logging.getLogger(f"{LOGGER_NAME}{suffix}")


def parse_level(level: str) -> int:
    return getattr(logging, str(level or "INFO").upper(), logging.INFO)


def summarize_text(text: str, limit: int = 300) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "..."
