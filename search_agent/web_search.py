from __future__ import annotations

import json
import urllib.parse
import urllib.request

from .models import WebSearchResult


class SerpApiSearch:
    def __init__(self, api_key: str | None):
        self.api_key = api_key

    def search(self, query: str, num: int = 5) -> list[WebSearchResult]:
        if not self.api_key:
            return []
        params = urllib.parse.urlencode(
            {
                "engine": "google",
                "q": query,
                "api_key": self.api_key,
                "num": str(num),
                "hl": "zh-cn",
                "gl": "cn",
            }
        )
        url = f"https://serpapi.com/search.json?{params}"
        request = urllib.request.Request(url, headers={"User-Agent": "search-agent/0.1"})
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))

        results: list[WebSearchResult] = []
        for item in payload.get("organic_results", [])[:num]:
            results.append(
                WebSearchResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet", ""),
                    date=item.get("date"),
                )
            )
        return results

