from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "本地数据"
FRONT_MATTER_RE = re.compile(r"\A---[ \t]*\n(?P<body>.*?)(?:\n)---[ \t]*(?:\n|\Z)", re.DOTALL)
FRONT_MATTER_KEY_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:", re.MULTILINE)
LOCAL_INDEX_FIELDS = (
    "primary_business_line",
    "business_lines",
    "service_items",
    "doc_kind",
    "agent_eligible",
)


@dataclass
class IndexStats:
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    samples: dict[str, list[str]] = field(default_factory=lambda: {"updated": [], "skipped": [], "failed": []})

    def record(self, status: str, path: Path) -> None:
        if not hasattr(self, status):
            raise ValueError(f"Unknown status: {status}")
        setattr(self, status, int(getattr(self, status)) + 1)
        bucket = self.samples.setdefault(status, [])
        if len(bucket) < 10:
            bucket.append(str(path))

    def as_dict(self) -> dict[str, Any]:
        return {
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


def compact_text(*parts: Any) -> str:
    return " ".join(str(part or "") for part in parts)


def append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def infer_business_lines(path: Path, title: str, body: str) -> list[str]:
    haystack = compact_text(path, title, body)
    lines: list[str] = []
    if any(keyword in haystack for keyword in ["公积金", "住房公积金", "缴存", "提取还贷"]):
        append_unique(lines, "公积金")
    if any(keyword in haystack for keyword in ["社保", "社会保险", "养老保险", "工伤", "失业", "城乡居保", "灵活就业", "退休"]):
        append_unique(lines, "社保")
    if any(keyword in haystack for keyword in ["医保", "医疗保险"]):
        append_unique(lines, "医保")
    if not lines:
        append_unique(lines, "未分类")
    return lines


def infer_service_items(title: str, body: str) -> list[str]:
    haystack = compact_text(title, body)
    items: list[str] = []
    rules = [
        ("缴存基数调整", ["缴存基数", "基数调整"]),
        ("缴存比例调整", ["缴存比例", "比例调整"]),
        ("月缴存额", ["月缴存额"]),
        ("公积金提取", ["公积金提取", "租赁提取", "提取住房公积金"]),
        ("公积金贷款", ["公积金贷款", "贷款"]),
        ("冲还贷", ["冲还贷", "提取还贷"]),
        ("维修资金", ["维修资金"]),
        ("退休办理", ["退休", "养老金申领"]),
        ("工伤待遇", ["工伤待遇", "工伤"]),
        ("灵活就业参保", ["灵活就业"]),
        ("城乡居保参保", ["城乡居保", "城乡居民养老保险"]),
        ("参保登记", ["参保登记", "个人参保"]),
        ("缴费办理", ["缴费", "补缴"]),
        ("资格认证", ["资格认证", "领取待遇资格"]),
        ("失业保险", ["失业保险", "失业"]),
    ]
    for item, keywords in rules:
        if any(keyword in haystack for keyword in keywords):
            append_unique(items, item)
    return items


def infer_doc_kind(path: Path, title: str, body: str) -> str:
    haystack = compact_text(path, title, body[:500])
    if any(keyword in title for keyword in ["问答", "热点问题", "Q&A"]):
        return "faq"
    if any(keyword in haystack for keyword in ["政策解读", "解读"]):
        return "policy_interpretation"
    if any(keyword in title for keyword in ["通知", "办法", "规定", "细则", "政策"]):
        return "policy_notice"
    if any(keyword in title for keyword in ["指南", "操作", "办理", "申领", "流程", "如何", "怎么"]):
        return "guide"
    if any(keyword in title for keyword in ["公告", "公示", "名单", "停办", "放假"]):
        return "announcement"
    return "other"


def infer_agent_eligible(title: str, body: str, service_items: list[str]) -> bool:
    haystack = compact_text(title, body[:500])
    negative_keywords = ["转发", "有奖", "开奖", "获奖", "招聘", "投票", "盛典", "节日快乐", "拜年"]
    if any(keyword in haystack for keyword in negative_keywords):
        return False
    return bool(service_items)


def infer_local_indexes(path: Path, title: str, body: str) -> dict[str, Any]:
    business_lines = infer_business_lines(path, title, body)
    service_items = infer_service_items(title, body)
    return {
        "primary_business_line": business_lines[0],
        "business_lines": business_lines,
        "service_items": service_items,
        "doc_kind": infer_doc_kind(path, title, body),
        "agent_eligible": infer_agent_eligible(title, body, service_items),
    }


def yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ", ".join(json.dumps(str(item), ensure_ascii=False) for item in value) + "]"
    return json.dumps(str(value), ensure_ascii=False)


def extract_title_from_front_matter(front_matter: str) -> str:
    match = re.search(r'^\s*title\s*:\s*(?P<value>.+?)\s*$', front_matter, flags=re.MULTILINE)
    if not match:
        return ""
    value = match.group("value").strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            return str(json.loads(value))
        except json.JSONDecodeError:
            return value.strip('"')
    return value.strip("'\"")


def extract_title_from_body(body: str, path: Path) -> str:
    match = re.search(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", body, flags=re.MULTILINE)
    return match.group(1).strip() if match else path.stem


def existing_front_matter_keys(front_matter: str) -> set[str]:
    return {match.group(1) for match in FRONT_MATTER_KEY_RE.finditer(front_matter)}


def split_front_matter(text: str) -> tuple[str, str, bool]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    match = FRONT_MATTER_RE.match(normalized)
    if not match:
        return "", normalized.lstrip("\n"), False
    body_start = match.end()
    front_matter = match.group("body")
    return front_matter, normalized[body_start:].lstrip("\n"), True


def add_local_indexes_to_text(text: str, path: Path) -> tuple[str, bool]:
    front_matter, body, has_front_matter = split_front_matter(text)
    title = extract_title_from_front_matter(front_matter) or extract_title_from_body(body, path)
    inferred = infer_local_indexes(path, title, body)
    existing_keys = existing_front_matter_keys(front_matter)
    missing_lines = [
        f"{field}: {yaml_scalar(inferred[field])}"
        for field in LOCAL_INDEX_FIELDS
        if field not in existing_keys
    ]
    if not missing_lines:
        return text.replace("\r\n", "\n").replace("\r", "\n"), False

    if has_front_matter:
        updated_front_matter = "\n".join([front_matter.rstrip(), *missing_lines]).strip("\n")
    else:
        updated_front_matter = "\n".join(missing_lines)
    return f"---\n{updated_front_matter}\n---\n\n{body}", True


def update_markdown_file(path: Path, dry_run: bool = False) -> str:
    original = path.read_text(encoding="utf-8-sig")
    updated, changed = add_local_indexes_to_text(original, path)
    if not changed:
        return "skipped"
    if not dry_run:
        path.write_text(updated, encoding="utf-8", newline="\n")
    return "updated"


def update_directory(data_dir: Path, dry_run: bool = False, limit: int | None = None) -> IndexStats:
    stats = IndexStats()
    files = sorted(path for path in data_dir.rglob("*.md") if path.is_file())
    if limit is not None:
        files = files[: max(0, int(limit))]
    for path in files:
        try:
            stats.record(update_markdown_file(path, dry_run=dry_run), path)
        except Exception:
            stats.record("failed", path)
            raise
    return stats


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Add simple local index front matter fields to Markdown documents.")
    parser.add_argument("--data-dir")
    parser.add_argument("--config", default=str(PROJECT_ROOT / "search-agent.toml"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    data_dir = Path(args.data_dir) if args.data_dir else resolve_data_dir(Path(args.config))
    stats = update_directory(data_dir, dry_run=bool(args.dry_run), limit=args.limit)
    print(json.dumps(stats.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
