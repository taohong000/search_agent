from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    dashscope_api_key: str | None
    serpapi_api_key: str | None
    model: str
    base_url: str
    max_rounds: int
    max_tool_steps: int
    top_k: int
    web_fetch_enabled: bool
    web_fetch_max_pages: int
    web_fetch_max_chars: int
    web_fetch_timeout_seconds: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls.from_config({})

    @classmethod
    def from_sources(cls, config_path: str | Path | None = None) -> "Settings":
        config = read_config(config_path)
        return cls.from_config(config)

    @classmethod
    def from_config(cls, config: dict) -> "Settings":
        secrets = config.get("secrets", {})
        search = config.get("search", {})
        agent = config.get("agent", {})
        default_data_dir = Path.cwd() / "\u672c\u5730\u6570\u636e"
        max_rounds = int(os.environ.get("SEARCH_AGENT_MAX_ROUNDS", search.get("max_rounds", 3)))
        return cls(
            data_dir=Path(
                os.environ.get(
                    "SEARCH_AGENT_DATA_DIR",
                    str(config.get("data_dir", default_data_dir)),
                )
            ),
            dashscope_api_key=blank_to_none(
                os.environ.get("DASHSCOPE_API_KEY", secrets.get("dashscope_api_key"))
            ),
            serpapi_api_key=blank_to_none(
                os.environ.get("SERPAPI_API_KEY", secrets.get("serpapi_api_key"))
            ),
            model=os.environ.get("SEARCH_AGENT_MODEL", str(config.get("model", "deepseek-v4-pro"))),
            base_url=os.environ.get(
                "DASHSCOPE_BASE_URL",
                str(config.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")),
            ),
            max_rounds=max_rounds,
            max_tool_steps=int(
                os.environ.get(
                    "SEARCH_AGENT_MAX_TOOL_STEPS",
                    agent.get("max_tool_steps", search.get("max_rounds", 8)),
                )
            ),
            top_k=int(os.environ.get("SEARCH_AGENT_TOP_K", search.get("top_k", 8))),
            web_fetch_enabled=str(
                os.environ.get(
                    "SEARCH_AGENT_WEB_FETCH_ENABLED",
                    config.get("web_fetch", {}).get("enabled", False),
                )
            ).lower()
            in {"1", "true", "yes", "on"},
            web_fetch_max_pages=int(
                os.environ.get(
                    "SEARCH_AGENT_WEB_FETCH_MAX_PAGES",
                    config.get("web_fetch", {}).get("max_pages", 3),
                )
            ),
            web_fetch_max_chars=int(
                os.environ.get(
                    "SEARCH_AGENT_WEB_FETCH_MAX_CHARS",
                    config.get("web_fetch", {}).get("max_chars_per_page", 20000),
                )
            ),
            web_fetch_timeout_seconds=int(
                os.environ.get(
                    "SEARCH_AGENT_WEB_FETCH_TIMEOUT_SECONDS",
                    config.get("web_fetch", {}).get("timeout_seconds", 30),
                )
            ),
        )


def read_config(config_path: str | Path | None) -> dict:
    path = resolve_config_path(config_path)
    if path is None:
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)


def resolve_config_path(config_path: str | Path | None) -> Path | None:
    if config_path is not None:
        path = Path(config_path)
        return path if path.exists() else None
    default = Path("search-agent.toml")
    return default if default.exists() else None


def blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
