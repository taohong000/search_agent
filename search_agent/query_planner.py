from __future__ import annotations

import re

from .models import SearchPlan


TIME_SENSITIVE_TERMS = [
    "现在",
    "最新",
    "今年",
    "今天",
    "当前",
    "目前",
    "2025",
    "2026",
    "多少钱",
    "比例",
    "基数",
    "标准",
]

EXPANSIONS = {
    "社保": ["社会保险", "参保", "参保缴费", "养老保险", "医疗保险"],
    "社会保险费": ["社保", "社会保险", "参保", "参保缴费", "灵活就业", "个人缴费"],
    "社会保险": ["社保", "参保", "参保缴费", "养老保险", "医疗保险"],
    "灵活就业": ["个人缴费", "参保登记", "参保缴费", "养老保险", "医疗保险"],
    "失业": ["失业保险", "失业保险金", "灵活就业", "个人缴费"],
    "没工作": ["失业", "灵活就业", "个人缴费"],
    "无业": ["失业", "灵活就业", "个人缴费"],
    "医保": ["医疗保险", "职工医保", "灵活就业"],
    "公积金": ["住房公积金", "缴存", "基数调整"],
    "缴纳": ["缴费", "参保缴费"],
    "交": ["缴费", "参保缴费"],
}

DOMAIN_DEFAULTS = ["上海"]


class QueryPlanner:
    def initial_plan(self, question: str) -> SearchPlan:
        terms = self.extract_terms(question)
        return SearchPlan(terms=terms, needs_web=is_time_sensitive(question))

    def extract_terms(self, question: str) -> list[str]:
        terms: list[str] = []
        for default in DOMAIN_DEFAULTS:
            if default in question:
                terms.append(default)
        for key, values in EXPANSIONS.items():
            if key in question:
                terms.append(key)
                terms.extend(values)

        for token in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", question):
            if token not in terms and not is_noise(token):
                terms.append(token)

        if not terms:
            terms.extend(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", question))
        return unique(terms)

    def next_terms(
        self,
        question: str,
        previous_terms: list[str],
        matched_terms: set[str],
    ) -> list[str]:
        expanded = self.extract_terms(question)
        if "社保" in previous_terms or "失业" in previous_terms or "失业" in question:
            expanded.extend(["灵活就业", "参保登记", "养老保险", "医疗保险", "个人缴费"])
        return [term for term in unique(expanded) if term not in matched_terms]


def is_time_sensitive(question: str) -> bool:
    return any(term in question for term in TIME_SENSITIVE_TERMS)


def unique(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for term in terms:
        value = term.strip()
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output


def is_noise(token: str) -> bool:
    return token in {"我住在上海", "我想问下", "怎么", "如何", "什么", "可以", "需要"}
