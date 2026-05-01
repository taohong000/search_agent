from __future__ import annotations

import re
from pathlib import Path

from .models import LocalSearchResult


HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", re.MULTILINE)
GENERIC_TERMS = {"上海", "社保", "社会保险", "参保", "缴费", "养老保险", "医疗保险"}
FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
YEAR_RE = re.compile(r"20\d{2}")


class LocalSearchEngine:
    """本地搜索引擎：遍历 Markdown 文件，按关键词匹配打分，返回 Top-K 结果。"""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def search(self, terms: list[str], top_k: int = 8) -> list[LocalSearchResult]:
        """搜索本地 Markdown 文件：遍历所有 .md 文件，对每个文件评分并返回得分最高的 top_k 个。"""
        normalized_terms = unique_terms(terms)
        if not normalized_terms or not self.root.exists():
            return []

        results: list[LocalSearchResult] = []
        for path in self.root.rglob("*.md"):
            text = read_utf8(path)
            if text is None:
                continue
            result = score_document(self.root, path, text, normalized_terms)
            if result is not None:
                results.append(result)

        results.sort(key=lambda item: item.score, reverse=True)
        return results[:top_k]


def unique_terms(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for term in terms:
        normalized = term.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            output.append(normalized)
    return output


def read_utf8(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return None
    except OSError:
        return None


def score_document(root: Path, path: Path, text: str, terms: list[str]) -> LocalSearchResult | None:
    """对单个文档评分：综合路径、标题、元数据、正文中的关键词命中次数和权重。"""
    metadata, body = split_front_matter(text)
    if metadata.get("agent_eligible", "").lower() == "false":
        return None
    rel_path = str(path.relative_to(root))
    title = metadata.get("title") or extract_title(body) or path.stem
    headings = "\n".join(HEADING_RE.findall(body))
    metadata_text = metadata_search_text(metadata)
    path_lower = rel_path.lower()
    title_lower = title.lower()
    headings_lower = headings.lower()
    metadata_lower = metadata_text.lower()
    text_lower = body.lower()

    matched: list[str] = []
    score = 0.0
    best_term: str | None = None
    best_term_score = 0.0
    for term in terms:
        needle = term.lower()
        weight = term_weight(term)
        term_score = 0.0
        body_count = text_lower.count(needle)
        if needle in path_lower:
            term_score += 8 * weight
        if needle in title_lower:
            term_score += 10 * weight
        if needle in metadata_lower:
            term_score += 7 * weight
        if needle in headings_lower:
            term_score += 6 * weight
        if body_count:
            term_score += min(body_count, 5) * 2 * weight
        if term_score:
            matched.append(term)
            score += term_score
            snippet_score = term_score + (20 if body_count else 0) + len(term) * 0.2
            if best_term is None or snippet_score > best_term_score:
                best_term = term
                best_term_score = snippet_score

    if not matched:
        return None

    score += metadata_score_adjustment(metadata)
    score += requested_year_adjustment(terms, rel_path, title, metadata_text)
    snippet = extract_multi_snippet(body, matched, best_term)
    return LocalSearchResult(path=path, title=title, snippet=snippet, matched_terms=matched, score=score, metadata=metadata)


def term_weight(term: str) -> float:
    """关键词权重：通用词（如"上海"、"社保"）权重低，长词（>=4字）权重高。"""
    if term in GENERIC_TERMS:
        return 0.35
    if len(term) >= 4:
        return 2.5
    return 1.0


def extract_title(text: str) -> str | None:
    match = HEADING_RE.search(text)
    return match.group(1).strip() if match else None


def split_front_matter(text: str) -> tuple[dict[str, str], str]:
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return {}, text
    return parse_front_matter(match.group(1)), text[match.end() :]


def parse_front_matter(block: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        value = raw_value.strip().strip('"').strip("'")
        if key:
            metadata[key] = value
    return metadata


def metadata_search_text(metadata: dict[str, str]) -> str:
    keys = [
        "title",
        "primary_business_line",
        "business_lines",
        "service_items",
        "doc_kind",
        "doc_status",
        "effective_date",
        "version_no",
        "version_index_path",
    ]
    return " ".join(metadata.get(key, "") for key in keys)


def metadata_score_adjustment(metadata: dict[str, str]) -> float:
    """根据文档元数据调整分数：active 状态加分，过期/废止扣分，FAQ 加分。"""
    score = 0.0
    if metadata.get("doc_status") == "active":
        score += 12
    elif metadata.get("doc_status") in {"superseded", "expired", "inactive"}:
        score -= 20
    if metadata.get("doc_kind") == "faq":
        score += 4
    version_no = metadata.get("version_no")
    if metadata.get("doc_status") == "active" and version_no and version_no.isdigit():
        score += min(int(version_no), 10) * 3
    return score


def requested_year_adjustment(
    terms: list[str],
    rel_path: str,
    title: str,
    metadata_text: str,
) -> float:
    """年份匹配调整：如果搜索词包含年份且文档匹配则大幅加分，不匹配则扣分。"""
    requested_years = set()
    for term in terms:
        requested_years.update(YEAR_RE.findall(term))
    if not requested_years:
        return 0.0

    haystack = f"{rel_path}\n{title}\n{metadata_text}"
    if any(year in haystack for year in requested_years):
        return 80.0
    return -35.0


def extract_snippet(text: str, term: str, radius: int = 90) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    index = compact.lower().find(term.lower())
    if index < 0:
        return compact[: radius * 2]
    start = max(0, index - radius)
    end = min(len(compact), index + len(term) + radius)
    prefix = "..." if start else ""
    suffix = "..." if end < len(compact) else ""
    return f"{prefix}{compact[start:end]}{suffix}"


def extract_multi_snippet(text: str, matched_terms: list[str], best_term: str | None, radius: int = 90) -> str:
    """提取多段摘要：围绕最佳匹配词和关键事实词，最多取 3 段不重叠的上下文片段。"""
    priority_terms = []
    fact_terms = ["最高不超过", "最低不低于", "缴存比例", "月缴存额上限", "月缴存额下限"]
    for term in [best_term, *matched_terms, *fact_terms]:
        if term and term not in priority_terms:
            priority_terms.append(term)
    compact = re.sub(r"\s+", " ", text).strip()
    snippets: list[str] = []
    used_ranges: list[tuple[int, int]] = []
    for term in priority_terms:
        index = compact.lower().find(term.lower())
        if index < 0:
            continue
        start = max(0, index - radius)
        end = min(len(compact), index + len(term) + radius)
        if any(not (end < used_start or start > used_end) for used_start, used_end in used_ranges):
            continue
        used_ranges.append((start, end))
        prefix = "..." if start else ""
        suffix = "..." if end < len(compact) else ""
        snippets.append(f"{prefix}{compact[start:end]}{suffix}")
        if len(snippets) >= 3:
            break
    return " ".join(snippets) if snippets else compact[: radius * 2]
