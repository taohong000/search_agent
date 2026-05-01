from __future__ import annotations

import re

from .models import LocalSearchResult


YEAR_RE = re.compile(r"20\d{2}")

DOMAIN_KEYWORDS = {
    "公积金": ["公积金", "住房公积金"],
    "社保": ["社保", "社会保险", "养老保险", "失业保险", "退休", "参保"],
    "医保": ["医保", "医疗保险", "职工医保"],
    "生育": ["生育津贴", "生育保险"],
    "工伤": ["工伤", "工伤认定", "工伤保险"],
}

SERVICE_KEYWORDS = [
    "灵活就业",
    "参保缴费",
    "医保补缴",
    "断缴",
    "补缴",
    "待遇",
    "生育津贴",
    "申领",
    "材料",
    "条件",
    "工伤认定",
    "申请",
    "关系转移",
    "转移接续",
    "租赁提取",
    "异地贷款",
    "还贷提取",
    "缴存基数",
    "缴存比例",
    "月缴存额",
]

CURRENT_POLICY_TERMS = [
    "现在",
    "最新",
    "今年",
    "今天",
    "当前",
    "目前",
    "多少钱",
    "比例",
    "基数",
    "标准",
    "上下限",
    "如何缴存",
    "缴存",
    "缴纳",
]


def source_text(source: LocalSearchResult) -> str:
    metadata_text = " ".join(str(value) for value in source.metadata.values())
    return f"{source.title}\n{source.path}\n{source.snippet}\n{' '.join(source.matched_terms)}\n{metadata_text}"


def domains_for_text(text: str) -> set[str]:
    domains: set[str] = set()
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            domains.add(domain)
    return domains


def domains_for_question(question: str) -> set[str]:
    domains = domains_for_text(question)
    if "生育津贴" in question:
        domains.update({"生育", "医保"})
    if "工伤" in question:
        domains.update({"工伤", "社保"})
    if "关系转移" in question or "转移接续" in question:
        domains.update({"社保"})
    return domains


def service_terms_for_question(question: str) -> set[str]:
    return {term for term in SERVICE_KEYWORDS if term in question}


def is_domain_mismatch(question: str, source: LocalSearchResult) -> bool:
    question_domains = domains_for_question(question)
    if not question_domains:
        return False
    text = source_text(source)
    source_domains = domains_for_text(text)
    if question_domains & source_domains:
        return False
    service_terms = service_terms_for_question(question)
    return not any(term in text for term in service_terms)


def is_current_policy_question(question: str) -> bool:
    return any(term in question for term in CURRENT_POLICY_TERMS)


def requested_years(question: str, terms: list[str] | None = None) -> set[str]:
    years = set(YEAR_RE.findall(question))
    for term in terms or []:
        years.update(YEAR_RE.findall(term))
    return years


def source_years(source: LocalSearchResult) -> set[str]:
    policy_text = "\n".join(
        [
            source.title,
            source.path.name,
            source.metadata.get("title", ""),
            source.metadata.get("publish_date", ""),
            source.metadata.get("effective_date", ""),
        ]
    )
    return set(YEAR_RE.findall(policy_text))


def latest_year(sources: list[LocalSearchResult]) -> str | None:
    years: set[str] = set()
    for source in sources:
        years.update(source_years(source))
    return max(years) if years else None


def source_is_active(source: LocalSearchResult) -> bool:
    return source.metadata.get("doc_status") == "active"


def source_is_superseded(source: LocalSearchResult) -> bool:
    return source.metadata.get("doc_status") in {"superseded", "expired", "inactive"}


def source_is_official(source: LocalSearchResult) -> bool:
    text = str(source.path)
    return any(marker in text for marker in ["官网", "上海市政府", "上海人社", "上海医保", "上海住房公积金网", "sh.gov.cn"])
