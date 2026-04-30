from __future__ import annotations

import argparse
import json
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "本地数据"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.add_local_indexes import infer_business_lines
from scripts.sync_reviewed_markdown import DEFAULT_ENV_FILE, DEFAULT_STATUSES, MysqlSettings, load_mysql_settings
from scripts.version_index_paths import parse_output_path_parts, resolve_version_index_path


@dataclass
class VersionIndexStats:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    samples: dict[str, list[str]] = field(default_factory=lambda: {
        "created": [],
        "updated": [],
        "skipped": [],
        "failed": [],
    })

    def record(self, status: str, path: Path) -> None:
        if not hasattr(self, status):
            raise ValueError(f"Unknown status: {status}")
        setattr(self, status, int(getattr(self, status)) + 1)
        bucket = self.samples.setdefault(status, [])
        if len(bucket) < 10:
            bucket.append(str(path))

    def as_dict(self) -> dict[str, Any]:
        return {
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "failed": self.failed,
            "samples": self.samples,
        }


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
    if isinstance(value, bool):
        return "true" if value else "false"
    return json.dumps(normalize_text(value), ensure_ascii=False)


def infer_business_line_for_group(group: dict[str, Any]) -> str:
    parts = parse_output_path_parts(group.get("output_path_parts_json"))
    path = Path(*parts) if parts else Path("")
    lines = infer_business_lines(path, normalize_text(group.get("group_name")), normalize_text(group.get("family_key")))
    return lines[0] if lines else "未分类"

def markdown_table_cell(value: Any) -> str:
    return normalize_text(value).replace("|", "\\|").replace("\n", " ")


def current_document(docs: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not docs:
        return None
    return sorted(
        docs,
        key=lambda row: (
            int(row.get("version_no") or 0),
            normalize_text(row.get("effective_date")),
            int(row.get("id") or 0),
        ),
        reverse=True,
    )[0]


def change_summary_by_old_policy(changes: list[dict[str, Any]]) -> dict[int, str]:
    result: dict[int, str] = {}
    for change in changes:
        old_id = change.get("old_policy_id")
        if old_id is None:
            continue
        summary = normalize_text(change.get("change_summary")) or normalize_text(change.get("change_type"))
        if summary:
            result[int(old_id)] = summary
    return result


def build_version_index_markdown(
    group: dict[str, Any],
    docs: list[dict[str, Any]],
    changes: list[dict[str, Any]] | None = None,
) -> str:
    changes = changes or []
    current = current_document(docs)
    business_line = infer_business_line_for_group(group)
    current_id = int(current["id"]) if current else 0
    current_version_no = current.get("version_no") if current else ""
    fields = [
        ("index_type", "version_index"),
        ("version_group_id", group.get("version_group_id") or group.get("id")),
        ("business_line", business_line),
        ("version_group_key", group.get("family_key")),
        ("group_name", group.get("group_name")),
        ("current_policy_document_id", current_id),
        ("current_version_no", current_version_no),
        ("source_name", group.get("source_name")),
        ("source_type", group.get("source_type")),
        ("channel_name", group.get("channel_name")),
        ("source", "policy_version_group + policy_document + policy_change_log"),
        ("updated_at", group.get("updated_at")),
    ]
    front_matter = ["---", *[f"{key}: {yaml_scalar(value)}" for key, value in fields], "---"]
    title = normalize_text(group.get("group_name")) or f"版本组 {group.get('version_group_id') or group.get('id')}"
    body = ["", f"# {title}", ""]
    if current:
        body.extend(
            [
                "## 当前版本",
                "",
                "| 版本 | 文档ID | 标题 | 生效日期 | 原文 |",
                "|---|---:|---|---|---|",
                "| "
                + " | ".join(
                    [
                        markdown_table_cell(current.get("version_no")),
                        markdown_table_cell(current.get("id")),
                        markdown_table_cell(current.get("title")),
                        markdown_table_cell(current.get("effective_date")),
                        markdown_table_cell(current.get("source_url")),
                    ]
                )
                + " |",
                "",
            ]
        )
    historical = [doc for doc in sorted(docs, key=lambda row: (int(row.get("version_no") or 0), int(row.get("id") or 0)), reverse=True) if int(doc.get("id") or 0) != current_id]
    if historical:
        change_by_old = change_summary_by_old_policy(changes)
        body.extend(
            [
                "## 历史版本",
                "",
                "| 版本 | 状态 | 文档ID | 标题 | 原文 | 替代关系 |",
                "|---|---|---:|---|---|---|",
            ]
        )
        for doc in historical:
            old_id = int(doc.get("id") or 0)
            body.append(
                "| "
                + " | ".join(
                    [
                        markdown_table_cell(doc.get("version_no")),
                        "superseded",
                        markdown_table_cell(old_id),
                        markdown_table_cell(doc.get("title")),
                        markdown_table_cell(doc.get("source_url")),
                        markdown_table_cell(change_by_old.get(old_id, "")),
                    ]
                )
                + " |"
            )
        body.append("")
    return "\n".join([*front_matter, *body]).rstrip() + "\n"


def build_version_groups_query(
    source_id: int | None = None,
    statuses: Iterable[str] = DEFAULT_STATUSES,
) -> tuple[str, list[Any]]:
    selected_statuses = [status for status in statuses if status]
    filters = [
        "d.version_group_id IS NOT NULL",
        "d.doc_status <> 'deleted'",
        f"d.review_status IN ({', '.join(['%s'] * len(selected_statuses))})",
    ]
    params: list[Any] = list(selected_statuses)
    if source_id is not None:
        filters.append("d.source_id = %s")
        params.append(int(source_id))
    sql = f"""
        SELECT DISTINCT
               g.id AS version_group_id,
               g.source_id,
               g.channel_code,
               g.channel_name,
               g.group_name,
               g.family_key,
               g.output_path_parts_json,
               g.updated_at,
               s.source_name,
               s.source_type
        FROM policy_version_group g
        INNER JOIN policy_document d ON d.version_group_id = g.id
        LEFT JOIN policy_source s ON s.id = g.source_id
        WHERE {' AND '.join(filters)}
        ORDER BY g.updated_at DESC, g.id DESC
    """
    return sql, params


def build_version_documents_query(statuses: Iterable[str] = DEFAULT_STATUSES) -> tuple[str, list[Any]]:
    selected_statuses = [status for status in statuses if status]
    sql = f"""
        SELECT id,
               version_group_id,
               title,
               version_no,
               publish_date,
               effective_date,
               source_url,
               review_status,
               doc_status
        FROM policy_document
        WHERE version_group_id IN ({{placeholders}})
          AND doc_status <> 'deleted'
          AND review_status IN ({', '.join(['%s'] * len(selected_statuses))})
        ORDER BY version_group_id ASC, version_no DESC, effective_date DESC, id DESC
    """
    return sql, list(selected_statuses)


def fetch_version_index_data(
    settings: MysqlSettings,
    source_id: int | None = None,
    statuses: Iterable[str] = DEFAULT_STATUSES,
) -> tuple[list[dict[str, Any]], dict[int, list[dict[str, Any]]], dict[int, list[dict[str, Any]]]]:
    try:
        import pymysql
    except ImportError as exc:
        raise RuntimeError("PyMySQL is required. Install it with: python -m pip install PyMySQL") from exc
    groups_sql, groups_params = build_version_groups_query(source_id=source_id, statuses=statuses)
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
            cursor.execute(groups_sql, groups_params)
            groups = list(cursor.fetchall())
            group_ids = [int(group["version_group_id"]) for group in groups]
            docs_by_group: dict[int, list[dict[str, Any]]] = {group_id: [] for group_id in group_ids}
            changes_by_group: dict[int, list[dict[str, Any]]] = {group_id: [] for group_id in group_ids}
            if not group_ids:
                return groups, docs_by_group, changes_by_group
            placeholders = ", ".join(["%s"] * len(group_ids))
            docs_sql_template, status_params = build_version_documents_query(statuses=statuses)
            docs_sql = docs_sql_template.format(placeholders=placeholders)
            cursor.execute(docs_sql, [*group_ids, *status_params])
            for doc in cursor.fetchall():
                docs_by_group.setdefault(int(doc["version_group_id"]), []).append(doc)
            cursor.execute(
                f"""
                SELECT version_group_id,
                       new_policy_id,
                       old_policy_id,
                       change_type,
                       change_summary,
                       impact_level
                FROM policy_change_log
                WHERE version_group_id IN ({placeholders})
                ORDER BY created_at DESC, id DESC
                """,
                group_ids,
            )
            for change in cursor.fetchall():
                group_id = change.get("version_group_id")
                if group_id is not None:
                    changes_by_group.setdefault(int(group_id), []).append(change)
            return groups, docs_by_group, changes_by_group
    finally:
        connection.close()


def write_version_indexes(
    data_dir: Path,
    groups: list[dict[str, Any]],
    docs_by_group: dict[int, list[dict[str, Any]]],
    changes_by_group: dict[int, list[dict[str, Any]]],
    dry_run: bool = False,
) -> VersionIndexStats:
    stats = VersionIndexStats()
    for group in groups:
        target = resolve_version_index_path(data_dir, group)
        group_id = int(group.get("version_group_id") or group.get("id"))
        docs = docs_by_group.get(group_id, [])
        if len(docs) < 2:
            stats.record("skipped", target)
            continue
        content = build_version_index_markdown(group, docs, changes_by_group.get(group_id, []))
        if not target.exists():
            status = "created"
        elif target.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n") == content:
            status = "skipped"
        else:
            status = "updated"
        if status != "skipped" and not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
        stats.record(status, target)
    return stats


def parse_statuses(raw: str) -> tuple[str, ...]:
    values = tuple(value.strip() for value in raw.split(",") if value.strip())
    return values or DEFAULT_STATUSES


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build local Markdown version index files from sicrawl version groups.")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    parser.add_argument("--data-dir")
    parser.add_argument("--config", default=str(PROJECT_ROOT / "search-agent.toml"))
    parser.add_argument("--source-id", type=int)
    parser.add_argument("--statuses", default=",".join(DEFAULT_STATUSES))
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = load_mysql_settings(Path(args.env_file))
    data_dir = Path(args.data_dir) if args.data_dir else resolve_data_dir(Path(args.config))
    groups, docs_by_group, changes_by_group = fetch_version_index_data(
        settings,
        source_id=args.source_id,
        statuses=parse_statuses(args.statuses),
    )
    stats = write_version_indexes(data_dir, groups, docs_by_group, changes_by_group, dry_run=bool(args.dry_run))
    print(json.dumps(stats.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
