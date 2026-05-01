from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SearchPlan:
    terms: list[str]
    needs_web: bool


@dataclass(frozen=True)
class LocalSearchResult:
    path: Path
    title: str
    snippet: str
    matched_terms: list[str]
    score: float
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str
    date: str | None = None


@dataclass(frozen=True)
class WebPageContent:
    title: str
    url: str
    text: str
    provider: str
    status: str


@dataclass(frozen=True)
class SearchRound:
    query_terms: list[str]
    hit_count: int


@dataclass(frozen=True)
class EvidenceDecision:
    is_sufficient: bool
    needs_web: bool
    next_terms: list[str] = field(default_factory=list)
    missing_facts: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass(frozen=True)
class AgentAnswer:
    answer: str
    local_sources: list[LocalSearchResult] = field(default_factory=list)
    web_sources: list[WebSearchResult] = field(default_factory=list)
    web_pages: list[WebPageContent] = field(default_factory=list)
    search_rounds: list[SearchRound] = field(default_factory=list)
    used_web: bool = False
    answerable: bool = True
    unable_reason: str = ""
