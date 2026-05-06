from __future__ import annotations

import json
import urllib.request

from .models import WebSearchResult


class BochaSearch:
    """博查 Web Search API 封装。"""

    ENDPOINT = "https://api.bocha.cn/v1/web-search"

    def __init__(self, api_key: str | None):
        self.api_key = api_key

    def search(self, query: str, num: int = 5) -> list[WebSearchResult]:
        if not self.api_key:
            return []
        payload = json.dumps(
            {"query": query, "freshness": "noLimit", "summary": True, "count": num},
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            self.ENDPOINT,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                body = json.loads(response.read().decode("utf-8"))
        except Exception:
            return []

        results: list[WebSearchResult] = []
        for item in (body.get("data", {}).get("webPages", {}).get("value") or [])[:num]:
            results.append(
                WebSearchResult(
                    title=item.get("name", ""),
                    url=item.get("url", ""),
                    snippet=item.get("snippet", "") or item.get("summary", ""),
                    date=item.get("datePublished"),
                )
            )
        return results
