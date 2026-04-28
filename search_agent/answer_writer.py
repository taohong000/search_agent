from __future__ import annotations

from .llm_client import BailianClient
from .models import LocalSearchResult, WebSearchResult


class AnswerWriter:
    def __init__(self, llm_client: BailianClient):
        self.llm_client = llm_client

    def write(
        self,
        question: str,
        local_sources: list[LocalSearchResult],
        web_sources: list[WebSearchResult],
    ) -> str:
        return self.llm_client.answer(question, local_sources, web_sources)

