from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.version_index_paths import build_version_index_relative_path

DEFAULT_CRAWLER_ROOT = Path(r"D:\code\sicrawl")
DEFAULT_ENV_FILE = DEFAULT_CRAWLER_ROOT / ".env.qa"
DEFAULT_CRAWLER_OUTPUT_DIR = DEFAULT_CRAWLER_ROOT / "output"
DEFAULT_DATA_DIR = PROJECT_ROOT / "本地数据"
DEFAULT_STATUSES = ("auto_approved", "manual_approved", "filter_disabled")
FRONT_MATTER_RE = re.compile(r"\A---[ \t]*\n.*?\n---[ \t]*(?:\n|\Z)", re.DOTALL)
INVALID_FILENAME_RE = re.compile(r'[\\/:*?"<>|]+')


@dataclass(frozen=True)
class MysqlSettings:
    host: str
    port: int
    user: str
    password: str
    database: str


@dataclass(frozen=True)
class PlannedWrite:
    status: str
    content: str


@dataclass
class SyncStats:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    missing_content: int = 0
    failed: int = 0
    samples: dict[str, list[str]] = field(default_factory=lambda: {
        "created": [],
        "updated": [],
        "skipped": [],
        "missing_content": [],
        "failed": [],
    })

    def record(self, status: str, path: Path) -> None:
        if not hasattr(self, status):
            raise ValueError(f"Unknown sync status: {status}")
        setattr(self, status, int(getattr(self, status)) + 1)
        bucket = self.samples.setdefault(status, [])
        if len(bucket) < 10:
            bucket.append(str(path))

    def as_dict(self) -> dict[str, Any]:
        return {
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "missing_content": self.missing_content,
            "failed": self.failed,
            "samples": self.samples,
        }


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_mysql_settings(env_file: Path = DEFAULT_ENV_FILE) -> MysqlSettings:
    env = load_env_file(env_file)
    required = [
        "SOCIAL_INSURANCE_MYSQL_HOST",
        "SOCIAL_INSURANCE_MYSQL_USER",
        "SOCIAL_INSURANCE_MYSQL_PASSWORD",
        "SOCIAL_INSURANCE_MYSQL_DATABASE",
    ]
    missing = [key for key in required if not str(env.get(key, "")).strip()]
    if missing:
        raise ValueError(f"Missing MySQL settings in {env_file}: {', '.join(missing)}")
    return MysqlSettings(
        host=str(env["SOCIAL_INSURANCE_MYSQL_HOST"]).strip(),
        port=int(str(env.get("SOCIAL_INSURANCE_MYSQL_PORT") or "3306").strip()),
        user=str(env["SOCIAL_INSURANCE_MYSQL_USER"]).strip(),
        password=str(env["SOCIAL_INSURANCE_MYSQL_PASSWORD"]),
        database=str(env["SOCIAL_INSURANCE_MYSQL_DATABASE"]).strip(),
    )


def resolve_data_dir(config_path: Path | None = None) -> Path:
    path = config_path or PROJECT_ROOT / "search-agent.toml"
    if path.exists():
        with path.open("rb") as handle:
            config = tomllib.load(handle)
        configured = config.get("data_dir")
        if configured:
            return Path(str(configured))
    return DEFAULT_DATA_DIR


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def yaml_scalar(value: Any) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return json.dumps(normalize_text(value), ensure_ascii=False)


def build_front_matter(row: dict[str, Any]) -> str:
    fields = [
        ("policy_document_id", row.get("id")),
        ("version_group_id", row.get("version_group_id")),
        ("version_index_path", row.get("version_index_path")),
        ("source_url", row.get("source_url")),
        ("source_name", row.get("source_name")),
        ("source_type", row.get("source_type")),
        ("city_code", row.get("city_code")),
        ("title", row.get("title")),
        ("publish_date", row.get("publish_date")),
        ("effective_date", row.get("effective_date")),
        ("review_status", row.get("review_status")),
        ("content_hash", row.get("content_hash")),
        ("version_no", row.get("version_no")),
        ("doc_status", row.get("doc_status")),
        ("updated_at", row.get("updated_at")),
    ]
    lines = ["---"]
    for key, value in fields:
        if key in {"version_group_id", "version_index_path"} and normalize_text(value) == "":
            continue
        lines.append(f"{key}: {yaml_scalar(value)}")
    lines.append("---")
    return "\n".join(lines)


def strip_front_matter(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return FRONT_MATTER_RE.sub("", normalized, count=1).lstrip("\n")


def normalize_markdown_body(text: str) -> str:
    return strip_front_matter(text).replace("\r\n", "\n").replace("\r", "\n").strip() + "\n"


def build_markdown_with_front_matter(row: dict[str, Any]) -> str:
    body = normalize_markdown_body(str(row.get("markdown_content") or ""))
    return f"{build_front_matter(row)}\n\n{body}"


def sanitize_path_part(value: str, fallback: str = "document") -> str:
    cleaned = INVALID_FILENAME_RE.sub("_", normalize_text(value))
    cleaned = re.sub(r"[\r\n\t]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned or fallback


def path_parts_lower(path: Path) -> list[str]:
    return [part.lower() for part in path.parts]


def map_markdown_target_path(
    normalized_text_path: str,
    crawler_output_dir: Path,
    data_dir: Path,
    source_type: str,
    source_name: str,
    title: str,
    version_no: Any = None,
    append_version: bool = False,
) -> Path:
    safe_title = sanitize_path_part(title, "document")
    normalized_version = normalize_text(version_no)
    filename = f"{safe_title}_v{normalized_version}.md" if append_version and normalized_version else f"{safe_title}.md"
    raw = normalize_text(normalized_text_path)
    if raw:
        source_path = Path(raw)
        output_dir = crawler_output_dir.resolve()
        markdown_root = output_dir / "markdown"
        candidates = [source_path]
        if not source_path.is_absolute():
            candidates.extend([DEFAULT_CRAWLER_ROOT / source_path, output_dir.parent / source_path])
        for candidate in candidates:
            try:
                relative = candidate.resolve().relative_to(markdown_root.resolve())
                return data_dir / relative.parent / filename
            except (OSError, ValueError):
                continue
        parts = list(source_path.parts)
        lowered = [part.lower() for part in parts]
        if "markdown" in lowered:
            index = lowered.index("markdown")
            if index + 1 < len(parts):
                relative_parent = Path(*parts[index + 1 : -1])
                return data_dir / relative_parent / filename

    safe_source_type = sanitize_path_part(source_type, "unknown_source_type")
    safe_source_name = sanitize_path_part(source_name, "unknown_source")
    return data_dir / safe_source_type / safe_source_name / filename


def plan_markdown_write(row: dict[str, Any], target_path: Path) -> PlannedWrite:
    desired = build_markdown_with_front_matter(row)
    if not target_path.exists():
        return PlannedWrite("created", desired)
    existing = target_path.read_text(encoding="utf-8-sig")
    if existing.replace("\r\n", "\n").replace("\r", "\n") == desired:
        return PlannedWrite("skipped", desired)
    existing_body = normalize_markdown_body(existing)
    desired_body = normalize_markdown_body(str(row.get("markdown_content") or ""))
    if existing_body == desired_body and strip_front_matter(existing) != existing and existing == desired:
        return PlannedWrite("skipped", desired)
    return PlannedWrite("updated", desired)


def resolve_target_path_for_row(row: dict[str, Any], crawler_output_dir: Path, data_dir: Path) -> Path:
    base_path = map_markdown_target_path(
        normalized_text_path=normalize_text(row.get("normalized_text_path")),
        crawler_output_dir=crawler_output_dir,
        data_dir=data_dir,
        source_type=normalize_text(row.get("source_type")),
        source_name=normalize_text(row.get("source_name")),
        title=normalize_text(row.get("title")),
    )
    if not base_path.exists():
        return base_path
    existing = base_path.read_text(encoding="utf-8-sig")
    desired_body = normalize_markdown_body(str(row.get("markdown_content") or ""))
    if normalize_markdown_body(existing) == desired_body:
        return base_path
    return map_markdown_target_path(
        normalized_text_path=normalize_text(row.get("normalized_text_path")),
        crawler_output_dir=crawler_output_dir,
        data_dir=data_dir,
        source_type=normalize_text(row.get("source_type")),
        source_name=normalize_text(row.get("source_name")),
        title=normalize_text(row.get("title")),
        version_no=row.get("version_no"),
        append_version=True,
    )


def fetch_reviewed_rows(
    settings: MysqlSettings,
    statuses: Iterable[str] = DEFAULT_STATUSES,
    limit: int | None = None,
    since_updated_at: str | None = None,
    source_id: int | None = None,
) -> list[dict[str, Any]]:
    try:
        import pymysql
    except ImportError as exc:
        raise RuntimeError("PyMySQL is required. Install it with: python -m pip install PyMySQL") from exc

    selected_statuses = [status for status in statuses if status]
    if not selected_statuses:
        raise ValueError("At least one review_status is required.")

    sql, params = build_reviewed_rows_query(
        statuses=selected_statuses,
        limit=limit,
        since_updated_at=since_updated_at,
        source_id=source_id,
    )

    connection = pymysql.connect(
        host=settings.host,
        port=settings.port,
        user=settings.user,
        password=settings.password,
        database=settings.database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return list(cursor.fetchall())
    finally:
        connection.close()


def build_reviewed_rows_query(
    statuses: Iterable[str],
    limit: int | None = None,
    since_updated_at: str | None = None,
    source_id: int | None = None,
) -> tuple[str, list[Any]]:
    selected_statuses = [status for status in statuses if status]
    status_placeholders = ", ".join(["%s"] * len(selected_statuses))
    filters = [
        "d.doc_status <> 'deleted'",
        f"d.review_status IN ({status_placeholders})",
        "c.markdown_content IS NOT NULL",
        "TRIM(c.markdown_content) <> ''",
    ]
    params: list[Any] = [*selected_statuses, *selected_statuses]
    if since_updated_at:
        filters.append("d.updated_at >= %s")
        params.append(since_updated_at)
    if source_id is not None:
        filters.append("d.source_id = %s")
        params.append(int(source_id))
    limit_sql = ""
    if limit is not None:
        limit_sql = "LIMIT %s"
        params.append(max(0, int(limit)))

    sql = f"""
        SELECT d.id,
               d.version_group_id,
               d.city_code,
               d.title,
               d.source_url,
               d.publish_date,
               d.effective_date,
               d.content_hash,
               d.version_no,
               d.doc_status,
               d.review_status,
               d.normalized_text_path,
               d.updated_at,
               s.source_name,
               s.source_type,
               g.group_name AS version_group_name,
               g.output_path_parts_json AS version_output_path_parts_json,
               (
                   SELECT COUNT(*)
                   FROM policy_document vd
                   WHERE vd.version_group_id = d.version_group_id
                     AND vd.doc_status <> 'deleted'
                     AND vd.review_status IN ({status_placeholders})
               ) AS version_group_document_count,
               c.markdown_content
        FROM policy_document d
        LEFT JOIN policy_source s ON s.id = d.source_id
        LEFT JOIN policy_version_group g ON g.id = d.version_group_id
        INNER JOIN policy_document_content c ON c.policy_id = d.id
        WHERE {' AND '.join(filters)}
        ORDER BY d.updated_at DESC, d.id DESC
        {limit_sql}
    """
    return sql, params


def sync_rows(
    rows: Iterable[dict[str, Any]],
    crawler_output_dir: Path,
    data_dir: Path,
    dry_run: bool = False,
) -> SyncStats:
    stats = SyncStats()
    for row in rows:
        markdown = normalize_text(row.get("markdown_content"))
        target_path = resolve_target_path_for_row(row, crawler_output_dir, data_dir)
        version_group_id = normalize_text(row.get("version_group_id"))
        version_group_name = normalize_text(row.get("version_group_name"))
        version_group_document_count = int(row.get("version_group_document_count") or 0)
        if version_group_id and version_group_name and version_group_document_count >= 2:
            row = dict(row)
            row["version_index_path"] = build_version_index_relative_path(
                data_dir,
                target_path,
                {
                    "version_group_id": row.get("version_group_id"),
                    "group_name": version_group_name,
                    "output_path_parts_json": row.get("version_output_path_parts_json"),
                },
            )
        if not markdown:
            stats.record("missing_content", target_path)
            continue
        try:
            action = plan_markdown_write(row, target_path)
            if action.status != "skipped" and not dry_run:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(action.content, encoding="utf-8", newline="\n")
            stats.record(action.status, target_path)
        except Exception:
            stats.record("failed", target_path)
            raise
    return stats


def parse_statuses(raw: str) -> tuple[str, ...]:
    values = tuple(value.strip() for value in raw.split(",") if value.strip())
    return values or DEFAULT_STATUSES


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync reviewed policy Markdown from sicrawl MySQL into local data.")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    parser.add_argument("--crawler-root", default=str(DEFAULT_CRAWLER_ROOT))
    parser.add_argument("--crawler-output-dir", default=str(DEFAULT_CRAWLER_OUTPUT_DIR))
    parser.add_argument("--data-dir")
    parser.add_argument("--config", default=str(PROJECT_ROOT / "search-agent.toml"))
    parser.add_argument("--statuses", default=",".join(DEFAULT_STATUSES))
    parser.add_argument("--since-updated-at")
    parser.add_argument("--source-id", type=int)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    env_file = Path(args.env_file)
    crawler_output_dir = Path(args.crawler_output_dir)
    data_dir = Path(args.data_dir) if args.data_dir else resolve_data_dir(Path(args.config))
    settings = load_mysql_settings(env_file)
    rows = fetch_reviewed_rows(
        settings=settings,
        statuses=parse_statuses(args.statuses),
        limit=args.limit,
        since_updated_at=args.since_updated_at,
        source_id=args.source_id,
    )
    stats = sync_rows(
        rows=rows,
        crawler_output_dir=crawler_output_dir,
        data_dir=data_dir,
        dry_run=bool(args.dry_run),
    )
    print(json.dumps(stats.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
