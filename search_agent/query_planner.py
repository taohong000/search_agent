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
    "医疗保险": ["医保", "职工医保"],
    "断缴": ["补缴", "待遇", "医疗保险"],
    "补缴": ["断缴", "待遇"],
    "生育津贴": ["生育保险", "申领", "材料", "条件"],
    "工伤": ["工伤认定", "工伤保险", "申请"],
    "工伤认定": ["工伤", "工伤保险", "申请"],
    "关系转移": ["转移接续", "养老保险"],
    "转移": ["关系转移", "转移接续", "养老保险"],
    "公积金": ["住房公积金"],
    "缴纳": ["缴费", "参保缴费"],
    "交": ["缴费", "参保缴费"],
}

DOMAIN_DEFAULTS = ["上海"]


class QueryPlanner:
    """查询规划器：理解用户问题，提取搜索关键词，判断是否涉及时效性信息。"""

    def initial_plan(self, question: str) -> SearchPlan:
        """生成初始搜索计划：提取关键词并判断是否需要网络验证。"""
        terms = self.extract_terms(question)
        return SearchPlan(terms=terms, needs_web=is_time_sensitive(question))

    def extract_terms(self, question: str) -> list[str]:
        """从问题中提取搜索关键词：领域默认词 + 同义词扩展 + 领域专有词 + 问题原文分词。"""
        terms: list[str] = []
        # 补充领域默认词（如"上海"）
        for default in DOMAIN_DEFAULTS:
            if default in question:
                terms.append(default)
        # 同义词扩展（如"社保" -> ["社会保险", "参保", ...]）
        for key, values in EXPANSIONS.items():
            if key in question:
                terms.append(key)
                terms.extend(values)
        # 领域专有词（如"租赁+提取" -> 提取额度相关词）
        terms.extend(domain_terms(question))

        # 从问题原文中提取 2 字以上的中英文 token，过滤噪音词
        for token in re.findall(r"[一-鿿A-Za-z0-9]{2,}", question):
            if token not in terms and not is_noise(token):
                terms.append(token)

        # 兜底：如果前面没提取到任何词，直接用原文分词
        if not terms:
            terms.extend(re.findall(r"[一-鿿A-Za-z0-9]{2,}", question))
        return unique(terms)

    def next_terms(
        self,
        question: str,
        previous_terms: list[str],
        matched_terms: set[str],
    ) -> list[str]:
        """生成下一轮搜索关键词：扩展后去除已命中的词，避免重复搜索。"""
        expanded = self.extract_terms(question)
        if "社保" in previous_terms or "失业" in previous_terms or "失业" in question:
            expanded.extend(["灵活就业", "参保登记", "养老保险", "医疗保险", "个人缴费"])
        return [term for term in unique(expanded) if term not in matched_terms]


def is_time_sensitive(question: str) -> bool:
    """判断问题是否涉及时效性信息（如"最新"、"今年"、"比例"等），需要网络验证。"""
    return any(term in question for term in TIME_SENSITIVE_TERMS)


def domain_terms(question: str) -> list[str]:
    """根据问题中的领域关键词，补充专有搜索词（如租赁提取额度、缴存比例等）。"""
    terms: list[str] = []
    if "租赁" in question and "提取" in question:
        terms.extend(["租赁提取", "提取额度", "提取限额", "月提取限额", "4000元"])
    if "长三角" in question:
        terms.extend(["长三角", "异地贷款", "还贷提取"])
    if "异地贷款" in question or "还贷提取" in question:
        terms.extend(["异地贷款", "还贷提取", "一笔贷款", "同一时间"])
    if "缴存比例" in question or "比例" in question:
        terms.extend(["缴存比例", "5%~7%", "5%", "7%"])
    if "月缴存额" in question or "计算公式" in question:
        terms.extend(["月缴存额", "计算", "缴存基数"])
    if "基数调整" in question:
        terms.extend(["基数调整", "2025年度"])
    if ("公积金" in question or "住房公积金" in question) and any(term in question for term in ["如何缴存", "怎么缴存", "缴存"]):
        terms.extend(["缴存基数", "缴存比例", "月缴存额", "基数调整"])
    if "医保" in question or "医疗保险" in question:
        if "断缴" in question or "补缴" in question:
            terms.extend(["医保", "医疗保险", "补缴", "待遇"])
    if "生育津贴" in question:
        terms.extend(["生育津贴", "生育保险", "申领", "材料", "条件"])
    if "工伤" in question:
        terms.extend(["工伤", "工伤认定", "工伤保险", "申请"])
    if "关系转移" in question or "转移接续" in question:
        terms.extend(["关系转移", "转移接续", "养老保险"])
    return terms


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
