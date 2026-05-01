from __future__ import annotations

from pathlib import Path

from .config import Settings
from .evidence_evaluator import EvidenceEvaluator
from .llm_client import BailianClient
from .local_search import LocalSearchEngine
from .models import AgentAnswer, EvidenceDecision, LocalSearchResult, SearchRound, WebSearchResult
from .query_planner import QueryPlanner
from .relevance import (
    domains_for_question,
    is_current_policy_question,
    is_domain_mismatch,
    latest_year,
    requested_years,
    service_terms_for_question,
    source_is_active,
    source_is_official,
    source_is_superseded,
    source_text,
    source_years,
)
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
        """主入口：接收用户问题，执行多轮本地搜索 + 可选网络搜索，返回最终答案。"""
        # 第一步：理解问题，生成初始搜索计划（关键词 + 是否需要网络验证）
        plan = self.planner.initial_plan(question)
        all_local: list[LocalSearchResult] = []
        rounds: list[SearchRound] = []
        terms = plan.terms
        matched_terms: set[str] = set()
        evaluator_needs_web = False
        final_decision: EvidenceDecision | None = None

        # 第二步：多轮本地搜索循环，每轮由评估器判断证据是否充分
        for _ in range(self.max_rounds):
            hits = self.local_search.search(terms, top_k=top_k)
            rounds.append(SearchRound(query_terms=terms, hit_count=len(hits)))
            # 合并去重，保留同一文档的最高分命中
            all_local = merge_local_sources(all_local, hits)
            for hit in hits:
                matched_terms.update(hit.matched_terms)
            # 评估当前证据：是否充分、是否需要网络、缺少哪些事实
            decision = self.evidence_evaluator.evaluate(question, terms, all_local, rounds, plan)
            final_decision = decision
            evaluator_needs_web = evaluator_needs_web or decision.needs_web
            if decision.is_sufficient:
                break
            # 下一轮本地检索词由评估器生成；为空表示不继续本地搜索。
            next_terms = decision.next_terms
            if not next_terms or next_terms == terms:
                break
            terms = next_terms

        # 第三步：根据策略决定是否进行网络搜索
        use_web = should_use_web(web_policy, plan.needs_web or evaluator_needs_web, all_local)
        web_sources: list[WebSearchResult] = []
        web_pages = []
        if use_web and self.web_search is not None:
            web_query = " ".join(plan.terms[:8])
            web_sources = self.web_search.search(web_query, num=5)
            # 抓取网页正文用于交叉验证日期、比例等关键数据
            if self.web_fetcher is not None:
                web_pages = self.web_fetcher.fetch_many(web_sources, plan.terms)

        # 第四步：排序、过滤本地来源，证据不足时直接返回缺口说明
        all_local = filter_final_sources(question, rank_final_sources(question, all_local))
        answerable = final_decision.is_sufficient if final_decision is not None else bool(all_local)
        unable_reason = "" if answerable else build_unable_reason(final_decision)
        if answerable:
            llm_client = self.llm_client or BailianClient(None, "deepseek-v4-flash", "")
            answer = llm_client.answer(question, all_local[:top_k], web_sources, web_pages)
        else:
            answer = build_unanswerable_answer(question, unable_reason, all_local[:top_k], web_sources)
        return AgentAnswer(
            answer=answer,
            local_sources=all_local[:top_k],
            web_sources=web_sources,
            web_pages=web_pages,
            search_rounds=rounds,
            used_web=bool(web_sources) or use_web,
            answerable=answerable,
            unable_reason=unable_reason,
        )


def should_use_web(web_policy: str, needs_web: bool, local_sources: list[LocalSearchResult]) -> bool:
    """根据 web_policy 策略和证据状态决定是否启用网络搜索。"""
    if web_policy == "never":
        return False
    if web_policy == "always":
        return True
    # auto 模式：评估器要求网络验证，或本地证据少于 2 条时启用
    return needs_web or len(local_sources) < 2


def merge_local_sources(
    existing: list[LocalSearchResult],
    new_items: list[LocalSearchResult],
) -> list[LocalSearchResult]:
    """合并多轮搜索结果，同一文档保留最高分，按分数降序排列。"""
    by_path: dict[Path, LocalSearchResult] = {item.path: item for item in existing}
    for item in new_items:
        current = by_path.get(item.path)
        if current is None or item.score > current.score:
            by_path[item.path] = item
    return sorted(by_path.values(), key=lambda item: item.score, reverse=True)


def rank_final_sources(question: str, sources: list[LocalSearchResult]) -> list[LocalSearchResult]:
    """对最终本地来源重新排序，按领域、事项、时效性和权威性加权。"""
    return sorted(sources, key=lambda item: final_source_score(question, item), reverse=True)


def final_source_score(question: str, source: LocalSearchResult) -> float:
    """计算最终排序分数：基础分 + 领域/事项/年份/状态/权威来源信号。"""
    score = source.score
    text = source_text(source)
    if domains_for_question(question):
        score += -80 if is_domain_mismatch(question, source) else 40
    for term in service_terms_for_question(question):
        if term in text:
            score += 18
    years = requested_years(question)
    if years:
        score += 80 if years & source_years(source) else -35
    if source_is_active(source):
        score += 30
    if source_is_superseded(source):
        score -= 30
    if source_is_official(source):
        score += 20
    if "规范性文件" in str(source.path) or "通知" in source.title:
        score += 10
    return score


def filter_final_sources(question: str, sources: list[LocalSearchResult]) -> list[LocalSearchResult]:
    """过滤最终来源：移除领域错配来源，当前政策问题优先保留目标年份或最新年份。"""
    relevant = [source for source in sources if not is_domain_mismatch(question, source)]
    if domains_for_question(question) and not relevant:
        return []
    filtered = relevant or sources
    years = requested_years(question)
    if years:
        year_matches = [source for source in filtered if years & source_years(source)]
        return year_matches or filtered
    if is_current_policy_question(question):
        year = latest_year(filtered)
        if year is not None:
            latest_sources = [source for source in filtered if year in source_years(source)]
            return latest_sources or filtered
    return filtered


def build_unable_reason(decision: EvidenceDecision | None) -> str:
    """构建"无法回答"的原因说明，用于返回给用户。"""
    if decision is None:
        return "没有找到足够证据。"
    if decision.missing_facts:
        return "缺少证据：" + "、".join(decision.missing_facts)
    return decision.reason or "没有找到足够证据。"


def build_unanswerable_answer(
    question: str,
    unable_reason: str,
    local_sources: list[LocalSearchResult],
    web_sources: list[WebSearchResult],
) -> str:
    """证据不足时构造保守回答，避免大模型基于不充分证据继续发挥。"""
    lines = [
        f"问题：{question}",
        "",
        f"无法回答：{unable_reason}",
    ]
    if local_sources:
        lines.append("")
        lines.append("已检索到的本地来源：")
        for source in local_sources[:5]:
            lines.append(f"- {source.title}（{source.path}）")
    if web_sources:
        lines.append("")
        lines.append("已检索到的网络来源：")
        for source in web_sources[:5]:
            lines.append(f"- {source.title}（{source.url}）")
    return "\n".join(lines)
