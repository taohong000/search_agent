from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

INVALID_FILENAME_RE = re.compile(r'[\\/:*?"<>|]+')


def normalize_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def sanitize_path_part(value: str, fallback: str = "document") -> str:
    cleaned = INVALID_FILENAME_RE.sub("_", normalize_text(value))
    cleaned = re.sub(r"[\r\n\t]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned or fallback


def parse_output_path_parts(raw: Any) -> list[str]:
    text = normalize_text(raw)
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [sanitize_path_part(str(part)) for part in parsed if normalize_text(part)]


def resolve_version_index_path(data_dir: Path, group: dict[str, Any]) -> Path:
    parts = parse_output_path_parts(group.get("output_path_parts_json"))
    group_name = sanitize_path_part(
        normalize_text(group.get("group_name")),
        f"group_{group.get('version_group_id') or group.get('id') or 'unknown'}",
    )
    if parts:
        return data_dir / Path(*parts) / "_indexes" / "version" / f"{group_name}.md"
    return data_dir / "_indexes" / "version" / "未分类" / f"{group_name}.md"


def build_version_index_relative_path(data_dir: Path, document_path: Path, group: dict[str, Any]) -> str:
    target = resolve_version_index_path(data_dir, group)
    relative = os.path.relpath(target, start=document_path.parent)
    return relative.replace("\\", "/")
