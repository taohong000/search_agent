from __future__ import annotations

import json
import urllib.request

from .models import EvidenceDecision, LocalSearchResult, SearchPlan, SearchRound, WebPageContent, WebSearchResult


class BailianClient:
    def __init__(self, api_key: str | None, model: str, base_url: str):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    def answer(
        self,
        question: str,
        local_sources: list[LocalSearchResult],
        web_sources: list[WebSearchResult],
        web_pages: list[WebPageContent] | None = None,
    ) -> str:
        web_pages = web_pages or []
        if not self.api_key:
            return fallback_answer(question, local_sources, web_sources, web_pages)

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "\u4f60\u662f\u8d44\u6599\u5e93\u67e5\u8be2\u52a9\u624b\u3002"
                        "\u53ea\u80fd\u57fa\u4e8e\u7ed9\u5b9a\u8bc1\u636e\u56de\u7b54\u3002"
                        "\u533a\u5206\u672c\u5730\u8d44\u6599\u548c\u8054\u7f51\u8d44\u6599\uff1b"
                        "\u6d89\u53ca\u65e5\u671f\u3001\u91d1\u989d\u3001\u6bd4\u4f8b\u65f6\u8bf4\u660e\u6765\u6e90\u3002"
                        "\u8bc1\u636e\u4e0d\u8db3\u65f6\u76f4\u63a5\u8bf4\u660e\u3002"
                    ),
                },
                {
                    "role": "user",
                    "content": build_prompt(question, local_sources, web_sources, web_pages),
                },
            ],
            "temperature": 0.2,
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
        return result["choices"][0]["message"]["content"]

    def evaluate_evidence(
        self,
        question: str,
        terms: list[str],
        local_sources: list[LocalSearchResult],
        rounds: list[SearchRound],
        plan: SearchPlan,
    ) -> EvidenceDecision | None:
        if not self.api_key:
            return None
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是资料检索 agent 的证据评估器。"
                        "只返回 JSON，不要返回 Markdown。"
                        "判断当前证据是否足够回答用户问题，以及是否需要联网核对。"
                    ),
                },
                {
                    "role": "user",
                    "content": build_evaluation_prompt(question, terms, local_sources, rounds, plan),
                },
            ],
            "temperature": 0,
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                result = json.loads(response.read().decode("utf-8"))
            content = result["choices"][0]["message"]["content"]
            return parse_evidence_decision(content)
        except Exception:
            return None


def build_prompt(
    question: str,
    local_sources: list[LocalSearchResult],
    web_sources: list[WebSearchResult],
    web_pages: list[WebPageContent],
) -> str:
    local_block = "\n".join(
        f"[本地{i}] 标题：{item.title}\n路径：{item.path}\n片段：{item.snippet}"
        for i, item in enumerate(local_sources, 1)
    )
    web_result_block = "\n".join(
        f"[搜索{i}] 标题：{item.title}\n链接：{item.url}\n摘要：{item.snippet}\n日期：{item.date or '未知'}"
        for i, item in enumerate(web_sources, 1)
    )
    web_page_block = "\n".join(
        f"[网页{i}] 标题：{item.title}\n链接：{item.url}\n抓取器：{item.provider}\n状态：{item.status}\n正文：{item.text[:4000]}"
        for i, item in enumerate(web_pages, 1)
    )
    return (
        f"用户问题：{question}\n\n"
        f"本地资料：\n{local_block or '无'}\n\n"
        f"搜索结果：\n{web_result_block or '无'}\n\n"
        f"网页正文：\n{web_page_block or '无'}\n\n"
        "请用中文给出直接、可执行的回答，末尾列出参考来源。"
    )


def build_evaluation_prompt(
    question: str,
    terms: list[str],
    local_sources: list[LocalSearchResult],
    rounds: list[SearchRound],
    plan: SearchPlan,
) -> str:
    evidence = "\n".join(
        f"[本地{i}] 标题：{item.title}\n路径：{item.path}\n片段：{item.snippet}\n命中：{', '.join(item.matched_terms)}"
        for i, item in enumerate(local_sources[:8], 1)
    )
    round_block = "\n".join(
        f"第{i}轮：关键词={', '.join(item.query_terms)}；命中={item.hit_count}"
        for i, item in enumerate(rounds, 1)
    )
    return (
        f"用户问题：{question}\n"
        f"初始关键词：{', '.join(plan.terms)}\n"
        f"当前关键词：{', '.join(terms)}\n"
        f"初始是否时效敏感：{plan.needs_web}\n\n"
        f"检索轮次：\n{round_block or '无'}\n\n"
        f"本地证据：\n{evidence or '无'}\n\n"
        "请返回 JSON，字段固定为："
        "{\"is_sufficient\": true/false, \"needs_web\": true/false, "
        "\"next_terms\": [\"词1\"], \"missing_facts\": [\"缺口\"], \"reason\": \"一句话原因\"}。"
        "如果涉及现行政策、日期、金额、比例、基数、上下限，通常需要 needs_web=true。"
    )


def parse_evidence_decision(content: str) -> EvidenceDecision | None:
    try:
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.startswith("json"):
                stripped = stripped[4:].strip()
        payload = json.loads(stripped)
    except (TypeError, json.JSONDecodeError):
        return None
    return EvidenceDecision(
        is_sufficient=bool(payload.get("is_sufficient")),
        needs_web=bool(payload.get("needs_web")),
        next_terms=[str(item) for item in payload.get("next_terms", []) if str(item).strip()],
        missing_facts=[str(item) for item in payload.get("missing_facts", []) if str(item).strip()],
        reason=str(payload.get("reason", "")),
    )


def fallback_answer(
    question: str,
    local_sources: list[LocalSearchResult],
    web_sources: list[WebSearchResult],
    web_pages: list[WebPageContent],
) -> str:
    lines = [f"问题：{question}", "", "未配置 DASHSCOPE_API_KEY，以下为检索到的证据摘要："]
    if local_sources:
        lines.append("")
        lines.append("本地资料：")
        for item in local_sources[:5]:
            lines.append(f"- {item.title}：{item.snippet}（{item.path}）")
    if web_pages:
        lines.append("")
        lines.append("网页正文：")
        for item in web_pages[:5]:
            lines.append(f"- {item.title or item.url}：{item.text[:300]}（{item.provider}, {item.status}）")
    if web_sources:
        lines.append("")
        lines.append("搜索结果：")
        for item in web_sources[:5]:
            lines.append(f"- {item.title}：{item.snippet}（{item.url}）")
    if not local_sources and not web_sources and not web_pages:
        lines.append("没有找到足够证据。")
    return "\n".join(lines)
