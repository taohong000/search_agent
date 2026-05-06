from __future__ import annotations

import fnmatch
import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .logging_config import get_logger
from .local_search import extract_title, read_utf8, split_front_matter
from .models import LocalSearchResult, SearchRound, WebPageContent, WebSearchResult


logger = get_logger("tools")


@dataclass
class ToolRunState:
    local_sources: dict[str, LocalSearchResult] = field(default_factory=dict)
    web_sources: dict[str, WebSearchResult] = field(default_factory=dict)
    web_pages: dict[str, WebPageContent] = field(default_factory=dict)
    search_rounds: list[SearchRound] = field(default_factory=list)
    used_web: bool = False


class SearchToolRunner:
    def __init__(self, data_dir: str | Path, web_search=None, web_fetcher=None):
        self.data_dir = Path(data_dir).resolve()
        self.web_search = web_search
        self.web_fetcher = web_fetcher
        self.state = ToolRunState()
        self._city_code_cache: dict[Path, str] = {}

    def run(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        logger.info("tool.run name=%s args=%s", name, args)
        try:
            if name == "rg_search":
                return self.rg_search(**args)
            if name == "fuzzy_file_search":
                return self.fuzzy_file_search(**args)
            if name == "read_local_file":
                return self.read_local_file(**args)
            if name == "web_search":
                return self.web_search_tool(**args)
            if name == "web_fetch":
                return self.web_fetch_tool(**args)
            return {"ok": False, "error": f"unknown tool: {name}"}
        except TypeError as exc:
            logger.warning("tool.run invalid_arguments name=%s error=%s", name, exc)
            return {"ok": False, "error": f"invalid arguments for {name}: {exc}"}
        except Exception as exc:
            logger.exception("tool.run failed name=%s error=%s", name, exc)
            return {"ok": False, "error": f"{name} failed: {exc}"}

    def rg_search(
        self,
        query: str,
        roots: list[str] | None = None,
        globs: list[str] | None = None,
        context: int = 2,
        max_results: int = 20,
        city_code: str | None = None,
    ) -> dict[str, Any]:
        query = str(query or "").strip()
        max_results = clamp_int(max_results, 1, 100, 20)
        context = clamp_int(context, 0, 10, 2)
        if not query:
            logger.warning("rg_search missing query")
            return {"ok": False, "error": "query is required", "results": []}
        search_roots = self._resolve_roots(roots)
        if not search_roots:
            logger.info("rg_search no roots query=%r roots=%s", query, roots)
            return {"ok": True, "query": query, "results": []}

        results = self._rg_subprocess(query, search_roots, globs, context, max_results)
        if results is None:
            logger.info("rg_search using python fallback query=%r", query)
            results = self._python_content_search(query, search_roots, globs, context, max_results)
        if city_code:
            results = self._filter_by_city_code(results, city_code)
        self.state.search_rounds.append(SearchRound(query_terms=[query], hit_count=len(results)))
        logger.info(
            "rg_search done query=%r roots=%s globs=%s context=%s max_results=%s city_code=%s hits=%s",
            query,
            [str(root) for root in search_roots],
            globs,
            context,
            max_results,
            city_code,
            len(results),
        )
        return {"ok": True, "query": query, "results": results}

    def fuzzy_file_search(
        self,
        query: str,
        roots: list[str] | None = None,
        limit: int = 20,
        city_code: str | None = None,
    ) -> dict[str, Any]:
        query = str(query or "").strip()
        limit = clamp_int(limit, 1, 100, 20)
        if not query:
            logger.warning("fuzzy_file_search missing query")
            return {"ok": False, "error": "query is required", "results": []}
        search_roots = self._resolve_roots(roots)
        candidates = sorted({path for root in search_roots for path in root.rglob("*.md")})

        scored: list[tuple[float, str, Path]] = []
        for path in candidates:
            if city_code and not self._path_matches_city_code(path, city_code):
                continue
            rel = self._display_path(path)
            score = fuzzy_score(query, rel)
            if score > 0:
                scored.append((score, rel, path))
        scored.sort(key=lambda item: (-item[0], item[1]))
        results = [
            {"path": rel, "score": round(score, 3), "title": self._title_for_path(path)}
            for score, rel, path in scored[:limit]
        ]
        self.state.search_rounds.append(SearchRound(query_terms=[query], hit_count=len(results)))
        logger.info(
            "fuzzy_file_search done query=%r roots=%s city_code=%s candidates=%s results=%s",
            query,
            [str(root) for root in search_roots],
            city_code,
            len(candidates),
            len(results),
        )
        return {"ok": True, "query": query, "results": results}

    def read_local_file(self, path: str, start_line: int = 1, max_lines: int = 120) -> dict[str, Any]:
        resolved = self._resolve_local_path(path)
        if resolved is None:
            logger.warning("read_local_file rejected path=%r reason=outside_or_missing", path)
            return {"ok": False, "error": "path is outside data_dir or does not exist"}
        if resolved.suffix.lower() != ".md":
            logger.warning("read_local_file rejected path=%s reason=non_markdown", resolved)
            return {"ok": False, "error": "only Markdown files can be read"}
        text = read_utf8(resolved)
        if text is None:
            logger.warning("read_local_file rejected path=%s reason=utf8", resolved)
            return {"ok": False, "error": "file is not readable as UTF-8"}
        lines = text.splitlines()
        start_line = clamp_int(start_line, 1, max(len(lines), 1), 1)
        max_lines = clamp_int(max_lines, 1, 500, 120)
        end_line = min(len(lines), start_line + max_lines - 1)
        numbered = [f"{index}: {lines[index - 1]}" for index in range(start_line, end_line + 1)]
        title, metadata = self._title_and_metadata(resolved, text)
        result = LocalSearchResult(
            path=resolved,
            title=title,
            snippet="\n".join(lines[start_line - 1 : end_line])[:1200],
            matched_terms=[],
            score=0.0,
            metadata=metadata,
        )
        self.state.local_sources[str(resolved)] = result
        logger.info(
            "read_local_file done path=%s title=%r start_line=%s end_line=%s chars=%s",
            resolved,
            title,
            start_line,
            end_line,
            len("\n".join(numbered)),
        )
        return {
            "ok": True,
            "path": self._display_path(resolved),
            "title": title,
            "start_line": start_line,
            "end_line": end_line,
            "content": "\n".join(numbered),
        }

    def web_search_tool(self, query: str, num: int = 5) -> dict[str, Any]:
        if self.web_search is None:
            logger.warning("web_search unavailable query=%r", query)
            return {"ok": False, "error": "web_search is unavailable", "results": []}
        num = clamp_int(num, 1, 10, 5)
        results = self.web_search.search(str(query or ""), num=num)
        self.state.used_web = True
        for item in results:
            self.state.web_sources[item.url] = item
        logger.info("web_search done query=%r num=%s results=%s", query, num, [item.url for item in results])
        return {
            "ok": True,
            "query": query,
            "results": [web_source_to_dict(item) for item in results],
        }

    def web_fetch_tool(self, urls: list[str], query_terms: list[str] | None = None) -> dict[str, Any]:
        if self.web_fetcher is None:
            logger.warning("web_fetch unavailable urls=%s", urls)
            return {"ok": False, "error": "web_fetch is unavailable", "pages": []}
        query_terms = [str(item) for item in query_terms or []]
        results = [
            self.state.web_sources.get(url)
            or WebSearchResult(title="", url=str(url), snippet="", date=None)
            for url in urls
            if str(url).strip()
        ]
        pages = self.web_fetcher.fetch_many(results, query_terms)
        self.state.used_web = True
        for page in pages:
            self.state.web_pages[page.url] = page
        logger.info(
            "web_fetch done urls=%s pages=%s",
            urls,
            [(page.url, page.provider, page.status, len(page.text)) for page in pages],
        )
        return {"ok": True, "pages": [web_page_to_dict(page) for page in pages]}

    def local_sources_from_final(self, requested: Any) -> list[LocalSearchResult]:
        paths: list[str] = []
        if isinstance(requested, list):
            for item in requested:
                if isinstance(item, dict):
                    value = item.get("path") or item.get("source_id")
                else:
                    value = item
                if value:
                    paths.append(str(value))
        output: list[LocalSearchResult] = []
        seen: set[str] = set()
        for path_text in paths:
            resolved = self._resolve_local_path(path_text)
            key = str(resolved) if resolved else path_text
            source = self.state.local_sources.get(key)
            if source is None and resolved is not None:
                title = self._title_for_path(resolved)
                source = LocalSearchResult(
                    path=resolved,
                    title=title,
                    snippet="",
                    matched_terms=[],
                    score=0.0,
                    metadata={},
                )
            if source is not None and str(source.path) not in seen:
                seen.add(str(source.path))
                output.append(source)
        if output:
            return output
        return list(self.state.local_sources.values())

    def web_sources_from_final(self, requested: Any) -> list[WebSearchResult]:
        urls: list[str] = []
        if isinstance(requested, list):
            for item in requested:
                if isinstance(item, dict):
                    value = item.get("url")
                else:
                    value = item
                if value:
                    urls.append(str(value))
        output: list[WebSearchResult] = []
        seen: set[str] = set()
        for url in urls:
            source = self.state.web_sources.get(url)
            if source is None:
                source = WebSearchResult(title=url, url=url, snippet="", date=None)
            if source.url not in seen:
                seen.add(source.url)
                output.append(source)
        if output:
            return output
        return list(self.state.web_sources.values())

    def _rg_subprocess(
        self,
        query: str,
        roots: list[Path],
        globs: list[str] | None,
        context: int,
        max_results: int,
    ) -> list[dict[str, Any]] | None:
        if shutil.which("rg") is None:
            return None
        cmd = ["rg", "--line-number", "--with-filename", "--color", "never"]
        for glob in globs or ["*.md"]:
            cmd.extend(["--glob", str(glob)])
        cmd.append(query)
        cmd.extend(str(root) for root in roots)
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=20, check=False, encoding="utf-8", errors="replace"
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode not in {0, 1}:
            return None
        matches: list[tuple[Path, int]] = []
        for line in (proc.stdout or "").splitlines():
            match = re.match(r"^(.*?):(\d+):(.*)$", line)
            if not match:
                continue
            path = Path(match.group(1)).resolve()
            if self._is_under_data_dir(path):
                matches.append((path, int(match.group(2))))
            if len(matches) >= max_results:
                break
        return [self._context_result(path, line_no, context, query) for path, line_no in matches]

    def _python_content_search(
        self,
        query: str,
        roots: list[Path],
        globs: list[str] | None,
        context: int,
        max_results: int,
    ) -> list[dict[str, Any]]:
        patterns = globs or ["*.md"]
        results: list[dict[str, Any]] = []
        needle = query.lower()
        for path in sorted({path for root in roots for path in root.rglob("*.md")}):
            rel = self._display_path(path)
            if not any(fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(path.name, pattern) for pattern in patterns):
                continue
            text = read_utf8(path)
            if text is None:
                continue
            for index, line in enumerate(text.splitlines(), 1):
                if needle in line.lower():
                    results.append(self._context_result(path, index, context, query, text=text))
                    break
            if len(results) >= max_results:
                break
        return results

    def _context_result(
        self,
        path: Path,
        line_no: int,
        context: int,
        query: str,
        text: str | None = None,
    ) -> dict[str, Any]:
        text = text if text is not None else read_utf8(path) or ""
        lines = text.splitlines()
        start = max(1, line_no - context)
        end = min(len(lines), line_no + context)
        title, metadata = self._title_and_metadata(path, text)
        snippet = "\n".join(lines[start - 1 : end])
        source = LocalSearchResult(
            path=path,
            title=title,
            snippet=snippet[:1200],
            matched_terms=[query],
            score=1.0,
            metadata=metadata,
        )
        self.state.local_sources[str(path)] = source
        return {
            "path": self._display_path(path),
            "title": title,
            "line": line_no,
            "start_line": start,
            "end_line": end,
            "snippet": snippet,
        }

    def _resolve_roots(self, roots: list[str] | None) -> list[Path]:
        if not roots:
            return [self.data_dir] if self.data_dir.exists() else []
        resolved: list[Path] = []
        for root in roots:
            path = self._resolve_local_path(root)
            if path is not None and path.is_dir():
                resolved.append(path)
        return resolved

    def _resolve_local_path(self, path_text: str) -> Path | None:
        raw = Path(str(path_text))
        path = raw if raw.is_absolute() else self.data_dir / raw
        try:
            resolved = path.resolve()
        except OSError:
            return None
        if not self._is_under_data_dir(resolved) or not resolved.exists():
            return None
        return resolved

    def _is_under_data_dir(self, path: Path) -> bool:
        try:
            path.relative_to(self.data_dir)
            return True
        except ValueError:
            return False

    def _display_path(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.data_dir))
        except ValueError:
            return str(path)

    def _title_for_path(self, path: Path) -> str:
        text = read_utf8(path)
        title, _ = self._title_and_metadata(path, text or "")
        return title

    def _title_and_metadata(self, path: Path, text: str) -> tuple[str, dict[str, str]]:
        metadata, body = split_front_matter(text)
        title = metadata.get("title") or extract_title(body) or path.stem
        return title, metadata

    def _filter_by_city_code(self, results: list[dict[str, Any]], city_code: str) -> list[dict[str, Any]]:
        """过滤搜索结果，只保留 city_code 匹配的文档。"""
        city_code = city_code.upper()
        filtered = []
        for result in results:
            path = self._resolve_local_path(result.get("path", ""))
            if path and self._path_matches_city_code(path, city_code):
                filtered.append(result)
        return filtered

    def _path_matches_city_code(self, path: Path, city_code: str) -> bool:
        """检查文件的 front matter 中 city_code 是否匹配。"""
        return self._get_city_code(path) == city_code.upper()

    def _get_city_code(self, path: Path) -> str:
        """获取文件的 city_code，带缓存。"""
        cached = self._city_code_cache.get(path)
        if cached is not None:
            return cached
        text = read_utf8(path)
        if text is None:
            self._city_code_cache[path] = ""
            return ""
        metadata, _ = split_front_matter(text)
        code = metadata.get("city_code", "").upper()
        self._city_code_cache[path] = code
        return code


def clamp_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def fuzzy_score(query: str, candidate: str) -> float:
    try:
        from rapidfuzz import fuzz

        return float(max(fuzz.partial_ratio(query, candidate), fuzz.token_set_ratio(query, candidate)))
    except Exception:
        import difflib

        if query in candidate:
            return 100.0
        return difflib.SequenceMatcher(None, query.lower(), candidate.lower()).ratio() * 100.0


def web_source_to_dict(source: WebSearchResult) -> dict[str, Any]:
    return {"title": source.title, "url": source.url, "snippet": source.snippet, "date": source.date}


def web_page_to_dict(page: WebPageContent) -> dict[str, Any]:
    return {
        "title": page.title,
        "url": page.url,
        "text": page.text,
        "provider": page.provider,
        "status": page.status,
    }


def tool_content(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)
