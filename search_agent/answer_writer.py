from __future__ import annotations

from .llm_client import BailianClient
from .models import LocalSearchResult, WebSearchResult


class AnswerWriter:
    """答案撰写器：将本地来源和网络来源交给 LLM 生成最终中文答案。"""

    def __init__(self, llm_client: BailianClient):
        self.llm_client = llm_client

    def write(
        self,
        question: str,
        local_sources: list[LocalSearchResult],
        web_sources: list[WebSearchResult],
    ) -> str:
        """调用 LLM，基于本地和网络来源撰写答案。"""
        return self.llm_client.answer(question, local_sources, web_sources)

