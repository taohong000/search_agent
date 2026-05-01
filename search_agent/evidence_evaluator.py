from __future__ import annotations

from .llm_client import BailianClient
from .models import EvidenceDecision, LocalSearchResult, SearchPlan, SearchRound
from .query_planner import QueryPlanner
from .relevance import domains_for_question, is_domain_mismatch


class EvidenceEvaluator:
    """证据评估器：优先使用大模型评估，仅保留很薄的通用兜底。"""

    def __init__(self, llm_client: BailianClient | None = None):
        """初始化证据评估器和兜底检索词规划器。"""
        self.llm_client = llm_client
        self.planner = QueryPlanner()

    def evaluate(
        self,
        question: str,
        terms: list[str],
        local_sources: list[LocalSearchResult],
        rounds: list[SearchRound],
        plan: SearchPlan,
    ) -> EvidenceDecision:
        """有大模型评估结果时直接采用；否则使用通用兜底判断。"""
        if self.llm_client is not None and hasattr(self.llm_client, "evaluate_evidence"):
            decision = self.llm_client.evaluate_evidence(question, terms, local_sources, rounds, plan)
            if decision is not None:
                return decision
        return self._fallback_decision(question, terms, local_sources, plan)

    def _fallback_decision(
        self,
        question: str,
        terms: list[str],
        local_sources: list[LocalSearchResult],
        plan: SearchPlan,
    ) -> EvidenceDecision:
        """大模型评估不可用时，仅根据领域相关性和证据是否存在做兜底判断。"""
        relevant_sources = [source for source in local_sources if not is_domain_mismatch(question, source)]
        if local_sources and domains_for_question(question) and not relevant_sources:
            return EvidenceDecision(
                is_sufficient=False,
                needs_web=plan.needs_web,
                next_terms=self.planner.next_terms(question, terms, set()),
                missing_facts=["领域不匹配"],
                reason="本地证据领域与问题不匹配。",
            )

        if not relevant_sources:
            missing_facts = ["领域不匹配"] if domains_for_question(question) else ["本地证据"]
            reason = "未找到匹配问题领域的本地证据。" if domains_for_question(question) else "未找到本地证据。"
            return EvidenceDecision(
                is_sufficient=False,
                needs_web=plan.needs_web,
                next_terms=self.planner.next_terms(question, terms, set()),
                missing_facts=missing_facts,
                reason=reason,
            )

        return EvidenceDecision(
            is_sufficient=True,
            needs_web=plan.needs_web,
            next_terms=[],
            missing_facts=[],
            reason="已找到本地证据；当前未启用大模型证据评估。",
        )
