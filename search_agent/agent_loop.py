from __future__ import annotations

from pathlib import Path

from .config import Settings
from .llm_client import BailianClient
from .local_search import LocalSearchEngine
from .models import AgentAnswer, LocalSearchResult, SearchRound, WebSearchResult
from .query_planner import QueryPlanner
from .web_fetch import Crawl4AIProvider, JinaReaderProvider, WebFetchRouter
from .web_search import SerpApiSearch


class SearchAgent:
    def __init__(
        self,
        data_dir: str | Path,
        llm_client=None,
        web_search=None,
        web_fetcher=None,
        max_rounds: int = 3,
    ):
        self.local_search = LocalSearchEngine(data_dir)
        self.planner = QueryPlanner()
        self.llm_client = llm_client
        self.web_search = web_search
        self.web_fetcher = web_fetcher
        self.max_rounds = max_rounds

    @classmethod
    def from_settings(cls, settings: Settings) -> "SearchAgent":
        return cls(
            data_dir=settings.data_dir,
            llm_client=BailianClient(
                api_key=settings.dashscope_api_key,
                model=settings.model,
                base_url=settings.base_url,
            ),
            web_search=SerpApiSearch(settings.serpapi_api_key),
            web_fetcher=WebFetchRouter(
                jina_provider=JinaReaderProvider(
                    timeout_seconds=settings.web_fetch_timeout_seconds,
                    max_chars=settings.web_fetch_max_chars,
                ),
                crawl4ai_provider=Crawl4AIProvider(
                    timeout_seconds=max(settings.web_fetch_timeout_seconds, 60),
                    max_chars=settings.web_fetch_max_chars,
                ),
                max_pages=settings.web_fetch_max_pages,
            )
            if settings.web_fetch_enabled
            else None,
            max_rounds=settings.max_rounds,
        )

    def ask(self, question: str, web_policy: str = "auto", top_k: int = 8) -> AgentAnswer:
        plan = self.planner.initial_plan(question)
        all_local: list[LocalSearchResult] = []
        rounds: list[SearchRound] = []
        terms = plan.terms
        matched_terms: set[str] = set()

        for _ in range(self.max_rounds):
            hits = self.local_search.search(terms, top_k=top_k)
            rounds.append(SearchRound(query_terms=terms, hit_count=len(hits)))
            all_local = merge_local_sources(all_local, hits)
            for hit in hits:
                matched_terms.update(hit.matched_terms)
            if len(all_local) >= min(3, top_k):
                break
            next_terms = self.planner.next_terms(question, terms, matched_terms)
            if not next_terms or next_terms == terms:
                break
            terms = next_terms

        use_web = should_use_web(web_policy, plan.needs_web, all_local)
        web_sources: list[WebSearchResult] = []
        web_pages = []
        if use_web and self.web_search is not None:
            web_query = " ".join(plan.terms[:8])
            web_sources = self.web_search.search(web_query, num=5)
            if self.web_fetcher is not None:
                web_pages = self.web_fetcher.fetch_many(web_sources, plan.terms)

        llm_client = self.llm_client or BailianClient(None, "deepseek-v4-flash", "")
        answer = llm_client.answer(question, all_local[:top_k], web_sources, web_pages)
        return AgentAnswer(
            answer=answer,
            local_sources=all_local[:top_k],
            web_sources=web_sources,
            web_pages=web_pages,
            search_rounds=rounds,
            used_web=bool(web_sources) or use_web,
        )


def should_use_web(web_policy: str, needs_web: bool, local_sources: list[LocalSearchResult]) -> bool:
    if web_policy == "never":
        return False
    if web_policy == "always":
        return True
    return needs_web or len(local_sources) < 2


def merge_local_sources(
    existing: list[LocalSearchResult],
    new_items: list[LocalSearchResult],
) -> list[LocalSearchResult]:
    by_path: dict[Path, LocalSearchResult] = {item.path: item for item in existing}
    for item in new_items:
        current = by_path.get(item.path)
        if current is None or item.score > current.score:
            by_path[item.path] = item
    return sorted(by_path.values(), key=lambda item: item.score, reverse=True)
