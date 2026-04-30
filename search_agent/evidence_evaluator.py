from __future__ import annotations

from .llm_client import BailianClient
from .models import EvidenceDecision, LocalSearchResult, SearchPlan, SearchRound
from .query_planner import QueryPlanner


POLICY_TERMS = ["社保", "社会保险", "公积金", "住房公积金", "医保"]
CURRENT_FACT_TERMS = ["现在", "最新", "今年", "当前", "目前", "多少钱", "比例", "基数", "标准", "上下限"]


class EvidenceEvaluator:
    """证据评估器：判断本地证据是否充分，决定是否需要网络验证或继续搜索。"""

    def __init__(self, llm_client: BailianClient | None = None):
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
        """评估证据：先用规则判断，再用 LLM 补充（如有），合并两者决策。"""
        rule_decision = self._rule_based_decision(question, terms, local_sources, plan)
        if self.llm_client is not None and hasattr(self.llm_client, "evaluate_evidence"):
            decision = self.llm_client.evaluate_evidence(question, terms, local_sources, rounds, plan)
            if decision is not None:
                return merge_decisions(rule_decision, decision)
        return rule_decision

    def _rule_based_decision(
        self,
        question: str,
        terms: list[str],
        local_sources: list[LocalSearchResult],
        plan: SearchPlan,
    ) -> EvidenceDecision:
        """基于规则的证据评估：检查缺失事实、判断是否需要网络验证。"""
        # 检查当前证据缺少哪些关键事实（如缴存比例、政策年度等）
        missing = missing_facts_for_question(question, local_sources)
        needs_web = plan.needs_web or should_verify_current_policy(question, missing)
        if not local_sources:
            # 无本地证据，生成下一轮搜索关键词
            next_terms = self.planner.next_terms(question, terms, set())
            return EvidenceDecision(
                is_sufficient=False,
                needs_web=needs_web,
                next_terms=next_terms,
                missing_facts=missing or ["本地证据"],
                reason="No local evidence found.",
            )
        if missing:
            # 有证据但缺少关键事实，针对性补充搜索词
            return EvidenceDecision(
                is_sufficient=False,
                needs_web=needs_web,
                next_terms=next_terms_for_missing(question, missing),
                missing_facts=missing,
                reason="Local evidence does not cover all required facts.",
            )
        # 证据充分（至少 2 条来源）
        return EvidenceDecision(
            is_sufficient=len(local_sources) >= 2,
            needs_web=needs_web,
            next_terms=[],
            missing_facts=[],
            reason="Local evidence covers the requested facts.",
        )


def should_verify_current_policy(question: str, missing_facts: list[str]) -> bool:
    """判断是否需要网络验证当前政策：涉及时效性用语或政策类问题且有缺失事实时需要。"""
    if any(term in question for term in CURRENT_FACT_TERMS):
        return True
    if any(term in question for term in POLICY_TERMS) and any(term in question for term in ["缴存", "缴纳", "交"]):
        return True
    return bool(missing_facts) and any(term in question for term in POLICY_TERMS)


def missing_facts_for_question(question: str, local_sources: list[LocalSearchResult]) -> list[str]:
    """根据问题类型检查本地证据是否覆盖所有必需事实，返回缺失事实列表。"""
    text = "\n".join(
        f"{item.title}\n{item.snippet}\n{' '.join(item.matched_terms)}" for item in local_sources
    )
    requirements: list[tuple[str, list[str]]] = []
    if any(term in question for term in ["个人账户", "账户余额", "个人公积金账户", "余额"]):
        return ["个人账户余额"]
    if "租赁" in question and "提取" in question:
        requirements.append(("租赁提取额度", ["4000元", "提取限额", "实际房租支出"]))
    if "长三角" in question or "异地贷款" in question or "还贷提取" in question:
        requirements.append(("异地贷款还贷提取限制", ["一笔", "同一时间", "异地贷款"]))
    if "公积金" in question or "住房公积金" in question:
        if any(term in question for term in ["缴存基数", "基数调整", "如何缴存"]):
            requirements.append(("缴存基数", ["缴存基数", "月平均工资"]))
        if any(term in question for term in ["缴存比例", "比例", "如何缴存"]):
            requirements.append(("缴存比例", ["缴存比例", "5%", "7%"]))
        if any(term in question for term in ["月缴存额", "计算", "公式", "如何缴存"]):
            requirements.append(("月缴存额", ["月缴存额", "计算"]))
        if "如何缴存" in question:
            requirements.append(("政策年度", ["2025年度", "2025年7月", "2026年6月", "自2025年7月1日起"]))
            requirements.append(("月缴存额上下限", ["上限", "下限", "37302", "2690"]))
            if local_sources and not has_current_fund_policy_source(local_sources):
                requirements.append(("2025年度完整政策", ["__single_source_current_policy__"]))
    if "社保" in question or "社会保险" in question:
        requirements.append(("参保缴费方式", ["参保", "缴费", "灵活就业"]))
    if "生育津贴" in question:
        requirements.append(("生育津贴证据", ["生育津贴", "生育保险", "医保"]))
    if "工伤" in question:
        requirements.append(("工伤认定证据", ["工伤认定", "工伤保险", "用人单位"]))
    if "医保" in question and ("断缴" in question or "补缴" in question):
        requirements.append(("医保补缴证据", ["医保", "医疗保险", "补缴", "待遇"]))
    if "关系转移" in question or "转移" in question:
        requirements.append(("关系转移证据", ["关系转移", "转移接续", "养老保险"]))

    missing: list[str] = []
    for label, needles in requirements:
        if not any(needle in text for needle in needles):
            missing.append(label)
    return missing


def next_terms_for_missing(question: str, missing: list[str]) -> list[str]:
    """根据缺失事实生成针对性的下一轮搜索关键词。"""
    terms: list[str] = []
    if "政策年度" not in missing and "月缴存额上下限" not in missing:
        terms.append("上海")
    if (
        ("公积金" in question or "住房公积金" in question)
        and "政策年度" not in missing
        and "月缴存额上下限" not in missing
    ):
        terms.append("住房公积金")
    mapping = {
        "缴存基数": ["缴存基数", "月平均工资"],
        "缴存比例": ["缴存比例", "5%", "7%"],
        "月缴存额": ["月缴存额", "上限", "下限"],
        "月缴存额上下限": ["月缴存额", "上限", "下限"],
        "政策年度": ["2025年度", "基数调整"],
        "2025年度完整政策": ["2025年度", "上海市", "调整", "住房公积金", "缴存基数", "比例", "月缴存额", "上下限", "通知"],
        "参保缴费方式": ["参保缴费", "灵活就业"],
        "生育津贴证据": ["生育津贴", "生育保险", "申领", "材料"],
        "工伤认定证据": ["工伤认定", "工伤保险", "申请"],
        "医保补缴证据": ["医保", "医疗保险", "断缴", "补缴", "待遇"],
        "关系转移证据": ["养老保险", "关系转移", "转移接续"],
        "本地证据": [],
    }
    for label in missing:
        terms.extend(mapping.get(label, [label]))
    return unique(terms)


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output


def merge_decisions(rule_decision: EvidenceDecision, llm_decision: EvidenceDecision) -> EvidenceDecision:
    """合并规则决策和 LLM 决策：两者都认为充分才充分，任一需要网络则需要。"""
    return EvidenceDecision(
        is_sufficient=rule_decision.is_sufficient and llm_decision.is_sufficient,
        needs_web=rule_decision.needs_web or llm_decision.needs_web,
        next_terms=rule_decision.next_terms or llm_decision.next_terms,
        missing_facts=unique(rule_decision.missing_facts + llm_decision.missing_facts),
        reason=f"rule: {rule_decision.reason} llm: {llm_decision.reason}".strip(),
    )


def has_current_fund_policy_source(sources: list[LocalSearchResult]) -> bool:
    """检查是否有包含 2025 年度公积金完整政策（年份+比例+金额上下限）的来源。"""
    for source in sources:
        text = f"{source.title}\n{source.snippet}\n{' '.join(source.matched_terms)}"
        has_year = any(marker in text for marker in ["2025年度", "2025年7月", "自2025年7月1日起"])
        has_ratio = any(marker in text for marker in ["缴存比例", "5%", "7%"])
        has_amount_limit = any(marker in text for marker in ["月缴存额", "上限", "下限", "37302", "2690"])
        if has_year and has_ratio and has_amount_limit:
            return True
    return False
