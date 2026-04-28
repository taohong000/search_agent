from __future__ import annotations

import re
from pathlib import Path

from .models import LocalSearchResult


HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", re.MULTILINE)
GENERIC_TERMS = {"上海", "社保", "社会保险", "参保", "缴费", "养老保险", "医疗保险"}


class LocalSearchEngine:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def search(self, terms: list[str], top_k: int = 8) -> list[LocalSearchResult]:
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
    rel_path = str(path.relative_to(root))
    title = extract_title(text) or path.stem
    headings = "\n".join(HEADING_RE.findall(text))
    path_lower = rel_path.lower()
    title_lower = title.lower()
    headings_lower = headings.lower()
    text_lower = text.lower()

    matched: list[str] = []
    score = 0.0
    best_term: str | None = None
    for term in terms:
        needle = term.lower()
        weight = term_weight(term)
        term_score = 0.0
        if needle in path_lower:
            term_score += 8 * weight
        if needle in title_lower:
            term_score += 10 * weight
        if needle in headings_lower:
            term_score += 6 * weight
        body_count = text_lower.count(needle)
        if body_count:
            term_score += min(body_count, 5) * 2 * weight
        if term_score:
            matched.append(term)
            score += term_score
            if best_term is None or term_score > 0:
                best_term = term

    if not matched:
        return None

    snippet = extract_snippet(text, matched[0] if best_term is None else best_term)
    return LocalSearchResult(path=path, title=title, snippet=snippet, matched_terms=matched, score=score)


def term_weight(term: str) -> float:
    if term in GENERIC_TERMS:
        return 0.35
    if len(term) >= 4:
        return 2.5
    return 1.0


def extract_title(text: str) -> str | None:
    match = HEADING_RE.search(text)
    return match.group(1).strip() if match else None


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
