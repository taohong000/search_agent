from __future__ import annotations

import asyncio
import contextlib
import io
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .models import WebPageContent, WebSearchResult


class JinaReaderProvider:
    def __init__(self, timeout_seconds: int = 30, max_chars: int = 20000):
        self.timeout_seconds = timeout_seconds
        self.max_chars = max_chars

    def fetch(self, url: str) -> WebPageContent:
        reader_url = "https://r.jina.ai/" + url
        try:
            request = urllib.request.Request(reader_url, headers={"User-Agent": "search-agent/0.1"})
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                text = response.read().decode("utf-8", errors="replace")
            title = extract_reader_title(text)
            return WebPageContent(
                title=title,
                url=url,
                text=text[: self.max_chars],
                provider="jina",
                status="ok",
            )
        except Exception as exc:
            return WebPageContent(title="", url=url, text="", provider="jina", status=f"error:{exc}")


class Crawl4AIProvider:
    def __init__(self, timeout_seconds: int = 60, max_chars: int = 20000):
        self.timeout_seconds = timeout_seconds
        self.max_chars = max_chars

    def fetch(self, url: str) -> WebPageContent:
        try:
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                return asyncio.run(self._fetch_async(url))
        except Exception as exc:
            return WebPageContent(title="", url=url, text="", provider="crawl4ai", status=f"error:{exc}")

    async def _fetch_async(self, url: str) -> WebPageContent:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

        browser_config = BrowserConfig(headless=True, verbose=False)
        run_config = CrawlerRunConfig(page_timeout=self.timeout_seconds * 1000)
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(url=url, config=run_config)
        markdown = result.markdown or ""
        if not isinstance(markdown, str):
            markdown = getattr(markdown, "raw_markdown", "") or str(markdown)
        return WebPageContent(
            title=extract_markdown_title(markdown) or "",
            url=url,
            text=markdown[: self.max_chars],
            provider="crawl4ai",
            status="ok" if result.success else f"error:{getattr(result, 'error_message', '')}",
        )


@dataclass(frozen=True)
class FetchQuality:
    min_chars: int = 500

    def is_good(self, page: WebPageContent, query_terms: list[str]) -> bool:
        if not page or page.status.startswith("error"):
            return False
        text = page.text or ""
        if len(text.strip()) < self.min_chars:
            return False
        if "Precondition Failed" in text or "Target URL returned error 412" in text:
            return False
        important_terms = [term for term in query_terms if len(term) >= 3]
        if important_terms and not any(term in text for term in important_terms):
            return False
        return True


class WebFetchRouter:
    def __init__(
        self,
        jina_provider=None,
        crawl4ai_provider=None,
        quality: FetchQuality | None = None,
        max_pages: int = 5,
    ):
        self.jina_provider = jina_provider or JinaReaderProvider()
        self.crawl4ai_provider = crawl4ai_provider or Crawl4AIProvider()
        self.quality = quality or FetchQuality()
        self.max_pages = max_pages

    def fetch(self, url: str, query_terms: list[str]) -> WebPageContent:
        if is_pdf_url(url):
            return WebPageContent(title="", url=url, text="", provider="pdf", status="pdf_unsupported")
        jina_page = self.jina_provider.fetch(url)
        if self.quality.is_good(jina_page, query_terms):
            return jina_page
        crawl_page = self.crawl4ai_provider.fetch(url)
        if self.quality.is_good(crawl_page, query_terms):
            return crawl_page
        return crawl_page if crawl_page.text else jina_page

    def fetch_many(self, results: list[WebSearchResult], query_terms: list[str]) -> list[WebPageContent]:
        pages: list[WebPageContent] = []
        for result in results[: self.max_pages]:
            page = self.fetch(result.url, query_terms)
            if page.text or page.status == "pdf_unsupported":
                pages.append(page)
        return pages


def is_pdf_url(url: str) -> bool:
    path = urllib.parse.urlparse(url).path.lower()
    return path.endswith(".pdf")


def extract_reader_title(text: str) -> str:
    match = re.search(r"^Title:\s*(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def extract_markdown_title(text: str) -> str:
    match = re.search(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", text, re.MULTILINE)
    if match:
        return match.group(1).strip()
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return first_line[:120]
