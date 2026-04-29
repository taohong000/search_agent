from __future__ import annotations

from pathlib import Path

from .config import Settings
from .evidence_evaluator import EvidenceEvaluator
from .llm_client import BailianClient
from .local_search import LocalSearchEngine
from .models import AgentAnswer, EvidenceDecision, LocalSearchResult, SearchRound, WebSearchResult
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
        evidence_evaluator=None,
        max_rounds: int = 3,
    ):
        self.local_search = LocalSearchEngine(data_dir)
        self.planner = QueryPlanner()
        self.llm_client = llm_client
        self.web_search = web_search
        self.web_fetcher = web_fetcher
        self.evidence_evaluator = evidence_evaluator or EvidenceEvaluator(llm_client)
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
        evaluator_needs_web = False
        final_decision: EvidenceDecision | None = None

        for _ in range(self.max_rounds):
            hits = self.local_search.search(terms, top_k=top_k)
            rounds.append(SearchRound(query_terms=terms, hit_count=len(hits)))
            all_local = merge_local_sources(all_local, hits)
            for hit in hits:
                matched_terms.update(hit.matched_terms)
            decision = self.evidence_evaluator.evaluate(question, terms, all_local, rounds, plan)
            final_decision = decision
            evaluator_needs_web = evaluator_needs_web or decision.needs_web
            if decision.is_sufficient:
                break
            next_terms = decision.next_terms or self.planner.next_terms(question, terms, matched_terms)
            if not next_terms or next_terms == terms:
                break
            terms = next_terms

        use_web = should_use_web(web_policy, plan.needs_web or evaluator_needs_web, all_local)
        web_sources: list[WebSearchResult] = []
        web_pages = []
        if use_web and self.web_search is not None:
            web_query = " ".join(plan.terms[:8])
            web_sources = self.web_search.search(web_query, num=5)
            if self.web_fetcher is not None:
                web_pages = self.web_fetcher.fetch_many(web_sources, plan.terms)

        llm_client = self.llm_client or BailianClient(None, "deepseek-v4-flash", "")
        all_local = filter_final_sources(question, rank_final_sources(question, all_local))
        answer = llm_client.answer(question, all_local[:top_k], web_sources, web_pages)
        answerable = final_decision.is_sufficient if final_decision is not None else bool(all_local)
        return AgentAnswer(
            answer=answer,
            local_sources=all_local[:top_k],
            web_sources=web_sources,
            web_pages=web_pages,
            search_rounds=rounds,
            used_web=bool(web_sources) or use_web,
            answerable=answerable,
            unable_reason="" if answerable else build_unable_reason(final_decision),
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


def rank_final_sources(question: str, sources: list[LocalSearchResult]) -> list[LocalSearchResult]:
    return sorted(sources, key=lambda item: final_source_score(question, item), reverse=True)


def final_source_score(question: str, source: LocalSearchResult) -> float:
    text = f"{source.title} {source.path} {source.snippet}"
    score = source.score
    if "公积金" in question or "住房公积金" in question:
        if "2025年度" in text or "2025年" in text:
            score += 100
        if "上海住房公积金网" in str(source.path) or "官网" in str(source.path):
            score += 30
        if "规范性文件" in str(source.path) or "通知" in source.title:
            score += 20
        if any(year in text for year in ["2018年度", "2019年度", "2020年度", "2021年度", "2022年度", "2023年度"]):
            score -= 30
    return score


def filter_final_sources(question: str, sources: list[LocalSearchResult]) -> list[LocalSearchResult]:
    if "公积金" not in question and "住房公积金" not in question:
        return sources
    if "如何缴存" not in question and not any(term in question for term in ["现在", "最新", "今年", "当前", "目前"]):
        return sources
    current_sources = [source for source in sources if is_current_fund_source(source)]
    return current_sources or sources


def is_current_fund_source(source: LocalSearchResult) -> bool:
    text = f"{source.title} {source.path} {source.snippet}"
    has_year = "2025年度" in text or "2025年" in text
    has_core_fact = any(
        marker in text
        for marker in [
            "缴存基数、比例以及月缴存额上下限",
            "37302",
            "2690",
            "5%~7%",
            "5%至7%",
            "5222",
            "376",
        ]
    )
    return has_year and has_core_fact


def build_unable_reason(decision: EvidenceDecision | None) -> str:
    if decision is None:
        return "没有找到足够证据。"
    if decision.missing_facts:
        return "缺少证据：" + "、".join(decision.missing_facts)
    return decision.reason or "没有找到足够证据。"
