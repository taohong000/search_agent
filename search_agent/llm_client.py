from __future__ import annotations

import json
import urllib.request

from .models import LocalSearchResult, WebPageContent, WebSearchResult


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
