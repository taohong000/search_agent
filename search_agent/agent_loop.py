from __future__ import annotations

import json
from pathlib import Path

from .config import Settings
from .evidence_evaluator import EvidenceEvaluator
from .llm_client import BailianClient
from .local_search import LocalSearchEngine
from .models import AgentAnswer, EvidenceDecision, LocalSearchResult, SearchRound, WebSearchResult
from .query_planner import QueryPlanner
from .relevance import (
    domains_for_question,
    is_current_policy_question,
    is_domain_mismatch,
    latest_year,
    requested_years,
    service_terms_for_question,
    source_is_active,
    source_is_official,
    source_is_superseded,
    source_text,
    source_years,
)
from .tools import SearchToolRunner, tool_content
from .web_fetch import Crawl4AIProvider, JinaReaderProvider, WebFetchRouter
from .web_search import SerpApiSearch


class SearchAgent:
    def __init__(
        self,
        data_dir: str | Path,
        llm_client=None,
        web_search=None,
        web_fetcher=None,
        evidence_evaluator=None,
        max_rounds: int = 3,
        max_tool_steps: int | None = None,
    ):
        self.local_search = LocalSearchEngine(data_dir)
        self.planner = QueryPlanner()
        self.llm_client = llm_client
        self.web_search = web_search
        self.web_fetcher = web_fetcher
        self.evidence_evaluator = evidence_evaluator or EvidenceEvaluator(llm_client)
        self.max_rounds = max_rounds
        self.max_tool_steps = max_tool_steps or max_rounds or 8

    @classmethod
    def from_settings(cls, settings: Settings) -> "SearchAgent":
        return cls(
            data_dir=settings.data_dir,
            llm_client=BailianClient(
                api_key=settings.dashscope_api_key,
                model=settings.model,
                base_url=settings.base_url,
            ),
            web_search=SerpApiSearch(settings.serpapi_api_key),
            web_fetcher=WebFetchRouter(
                jina_provider=JinaReaderProvider(
                    timeout_seconds=settings.web_fetch_timeout_seconds,
                    max_chars=settings.web_fetch_max_chars,
                ),
                crawl4ai_provider=Crawl4AIProvider(
                    timeout_seconds=max(settings.web_fetch_timeout_seconds, 60),
                    max_chars=settings.web_fetch_max_chars,
                ),
                max_pages=settings.web_fetch_max_pages,
            )
            if settings.web_fetch_enabled
            else None,
            max_rounds=settings.max_rounds,
            max_tool_steps=settings.max_tool_steps,
        )

    def ask(self, question: str, web_policy: str = "auto", top_k: int = 8) -> AgentAnswer:
        if self._can_use_tool_loop():
            try:
                return self._ask_with_tools(question, web_policy=web_policy, top_k=top_k)
            except Exception:
                return self._ask_legacy(question, web_policy=web_policy, top_k=top_k)
        return self._ask_legacy(question, web_policy=web_policy, top_k=top_k)

    def _can_use_tool_loop(self) -> bool:
        return bool(getattr(self.llm_client, "api_key", None)) and hasattr(self.llm_client, "chat_with_tools")

    def _ask_with_tools(self, question: str, web_policy: str = "auto", top_k: int = 8) -> AgentAnswer:
        runner = SearchToolRunner(self.local_search.root, self.web_search, self.web_fetcher)
        tools = build_tool_schemas(web_policy, self.web_search is not None, self.web_fetcher is not None)
        available_tool_names = {tool["function"]["name"] for tool in tools}
        messages = [
            {"role": "system", "content": build_tool_loop_system_prompt(web_policy)},
            {"role": "user", "content": question},
        ]

        final_payload = None
        for _ in range(self.max_tool_steps):
            message = self.llm_client.chat_with_tools(messages, tools, tool_choice="auto")
            messages.append(normalize_assistant_message(message))
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                messages.append(
                    {
                        "role": "user",
                        "content": "请使用 final_answer 工具给出结构化最终答案；证据不足时 answerable=false。",
                    }
                )
                continue

            for call in tool_calls:
                name = tool_call_name(call)
                args, error = parse_tool_arguments(call)
                if name == "final_answer":
                    if should_accept_final_answer(runner, args, error, web_policy):
                        final_payload = args if error is None else {"answerable": False, "unable_reason": error}
                    else:
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.get("id", ""),
                                "content": tool_content(
                                    {
                                        "ok": False,
                                        "error": (
                                            "final_answer rejected: call rg_search or fuzzy_file_search first, "
                                            "then read_local_file when local candidates exist."
                                        ),
                                    }
                                ),
                            }
                        )
                    break
                result = dispatch_tool_call(runner, name, args, error, available_tool_names)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", ""),
                        "content": tool_content(result),
                    }
                )
            if final_payload is not None:
                break

        if final_payload is None:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "已达到常规工具步数上限。若已有足够证据，请立即调用 final_answer；"
                        "若刚发现候选文件但尚未读取，可最多再读取必要文件一次，然后调用 final_answer。"
                    ),
                }
            )
            for _ in range(2):
                forced = self.llm_client.chat_with_tools(messages, tools, tool_choice="auto")
                messages.append(normalize_assistant_message(forced))
                tool_calls = forced.get("tool_calls") or []
                for call in tool_calls:
                    name = tool_call_name(call)
                    args, error = parse_tool_arguments(call)
                    if name == "final_answer":
                        final_payload = args if error is None else {"answerable": False, "unable_reason": error}
                        break
                    result = dispatch_tool_call(runner, name, args, error, available_tool_names)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.get("id", ""),
                            "content": tool_content(result),
                        }
                    )
                if final_payload is not None or not tool_calls:
                    break

        if final_payload is None:
            final_payload = {
                "answer": build_unanswerable_answer(question, "达到工具调用上限，模型未给出最终答案。", [], []),
                "answerable": False,
                "unable_reason": "达到工具调用上限，模型未给出最终答案。",
            }

        answer = str(final_payload.get("answer") or "")
        answerable = bool(final_payload.get("answerable"))
        unable_reason = "" if answerable else str(final_payload.get("unable_reason") or "证据不足。")
        local_sources = runner.local_sources_from_final(final_payload.get("local_sources"))[:top_k]
        web_sources = runner.web_sources_from_final(final_payload.get("web_sources"))
        if not answer:
            answer = build_unanswerable_answer(question, unable_reason, local_sources, web_sources)
        return AgentAnswer(
            answer=answer,
            local_sources=local_sources,
            web_sources=web_sources,
            web_pages=list(runner.state.web_pages.values()),
            search_rounds=runner.state.search_rounds,
            used_web=runner.state.used_web or web_policy == "always",
            answerable=answerable,
            unable_reason=unable_reason,
        )

    def _ask_legacy(self, question: str, web_policy: str = "auto", top_k: int = 8) -> AgentAnswer:
        """主入口：接收用户问题，执行多轮本地搜索 + 可选网络搜索，返回最终答案。"""
        # 第一步：理解问题，生成初始搜索计划（关键词 + 是否需要网络验证）
        plan = self.planner.initial_plan(question)
        all_local: list[LocalSearchResult] = []
        rounds: list[SearchRound] = []
        terms = plan.terms
        matched_terms: set[str] = set()
        evaluator_needs_web = False
        final_decision: EvidenceDecision | None = None

        # 第二步：多轮本地搜索循环，每轮由评估器判断证据是否充分
        for _ in range(self.max_rounds):
            hits = self.local_search.search(terms, top_k=top_k)
            rounds.append(SearchRound(query_terms=terms, hit_count=len(hits)))
            # 合并去重，保留同一文档的最高分命中
            all_local = merge_local_sources(all_local, hits)
            for hit in hits:
                matched_terms.update(hit.matched_terms)
            # 评估当前证据：是否充分、是否需要网络、缺少哪些事实
            decision = self.evidence_evaluator.evaluate(question, terms, all_local, rounds, plan)
            final_decision = decision
            evaluator_needs_web = evaluator_needs_web or decision.needs_web
            if decision.is_sufficient:
                break
            # 下一轮本地检索词由评估器生成；为空表示不继续本地搜索。
            next_terms = decision.next_terms
            if not next_terms or next_terms == terms:
                break
            terms = next_terms

        # 第三步：根据策略决定是否进行网络搜索
        use_web = should_use_web(web_policy, plan.needs_web or evaluator_needs_web, all_local)
        web_sources: list[WebSearchResult] = []
        web_pages = []
        if use_web and self.web_search is not None:
            web_query = " ".join(plan.terms[:8])
            web_sources = self.web_search.search(web_query, num=5)
            # 抓取网页正文用于交叉验证日期、比例等关键数据
            if self.web_fetcher is not None:
                web_pages = self.web_fetcher.fetch_many(web_sources, plan.terms)

        # 第四步：排序、过滤本地来源，证据不足时直接返回缺口说明
        all_local = filter_final_sources(question, rank_final_sources(question, all_local))
        answerable = final_decision.is_sufficient if final_decision is not None else bool(all_local)
        unable_reason = "" if answerable else build_unable_reason(final_decision)
        if answerable:
            llm_client = self.llm_client or BailianClient(None, "deepseek-v4-flash", "")
            answer = llm_client.answer(question, all_local[:top_k], web_sources, web_pages)
        else:
            answer = build_unanswerable_answer(question, unable_reason, all_local[:top_k], web_sources)
        return AgentAnswer(
            answer=answer,
            local_sources=all_local[:top_k],
            web_sources=web_sources,
            web_pages=web_pages,
            search_rounds=rounds,
            used_web=bool(web_sources) or use_web,
            answerable=answerable,
            unable_reason=unable_reason,
        )


def normalize_assistant_message(message: dict) -> dict:
    normalized = {
        "role": "assistant",
        "content": message.get("content") or "",
    }
    tool_calls = message.get("tool_calls") or []
    if tool_calls:
        normalized["tool_calls"] = tool_calls
    return normalized


def tool_call_name(call: dict) -> str:
    return str((call.get("function") or {}).get("name") or "")


def parse_tool_arguments(call: dict) -> tuple[dict, str | None]:
    raw = (call.get("function") or {}).get("arguments") or "{}"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {}, f"invalid JSON arguments: {exc}"
    if not isinstance(payload, dict):
        return {}, "tool arguments must be a JSON object"
    return payload, None


def dispatch_tool_call(
    runner: SearchToolRunner,
    name: str,
    args: dict,
    parse_error: str | None,
    available_tool_names: set[str],
) -> dict:
    if parse_error is not None:
        return {"ok": False, "error": parse_error}
    if name not in available_tool_names:
        return {"ok": False, "error": f"tool unavailable: {name}"}
    return runner.run(name, args)


def should_accept_final_answer(
    runner: SearchToolRunner,
    args: dict,
    parse_error: str | None,
    web_policy: str,
) -> bool:
    if parse_error is not None:
        return True
    if web_policy == "always" and runner.state.used_web:
        return True
    return bool(runner.state.search_rounds or runner.state.local_sources)


def build_tool_loop_system_prompt(web_policy: str) -> str:
    web_instruction = {
        "never": "本次禁止联网；不要调用 web_search 或 web_fetch，只能使用本地只读工具。",
        "always": "本次要求联网核对；除非 web 工具返回不可用，否则至少调用一次 web_search。",
    }.get(web_policy, "如果问题涉及现行、最新、今天、金额、比例、政策状态等时效信息，应主动调用 web_search 核对。")
    return (
        "你是资料库搜索智能体。你必须通过工具收集证据，再调用 final_answer 结束。"
        "优先使用 fuzzy_file_search 或 rg_search 找候选资料，再用 read_local_file 读取足够片段。"
        "在调用 final_answer 前，至少先调用一次 rg_search 或 fuzzy_file_search；找到候选文件后必须 read_local_file。"
        "所有回答必须基于已观察到的工具结果；证据不足时 final_answer(answerable=false)。"
        "本地工具只读，且只能访问 data_dir 内文件。"
        f"{web_instruction}"
    )


def build_tool_schemas(web_policy: str, has_web_search: bool, has_web_fetch: bool) -> list[dict]:
    tools = [
        function_tool(
            "rg_search",
            "Search Markdown content under data_dir with ripgrep-style text search.",
            {
                "query": {"type": "string"},
                "roots": {"type": "array", "items": {"type": "string"}},
                "globs": {"type": "array", "items": {"type": "string"}},
                "context": {"type": "integer"},
                "max_results": {"type": "integer"},
            },
            ["query"],
        ),
        function_tool(
            "fuzzy_file_search",
            "Fuzzy search Markdown file paths and names under data_dir.",
            {
                "query": {"type": "string"},
                "roots": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer"},
            },
            ["query"],
        ),
        function_tool(
            "read_local_file",
            "Read a line-numbered Markdown snippet from a data_dir file.",
            {
                "path": {"type": "string"},
                "start_line": {"type": "integer"},
                "max_lines": {"type": "integer"},
            },
            ["path"],
        ),
    ]
    if web_policy != "never" and has_web_search:
        tools.append(
            function_tool(
                "web_search",
                "Search the web for current or external verification.",
                {"query": {"type": "string"}, "num": {"type": "integer"}},
                ["query"],
            )
        )
    if web_policy != "never" and has_web_fetch:
        tools.append(
            function_tool(
                "web_fetch",
                "Fetch web page contents for selected URLs.",
                {
                    "urls": {"type": "array", "items": {"type": "string"}},
                    "query_terms": {"type": "array", "items": {"type": "string"}},
                },
                ["urls"],
            )
        )
    tools.append(
        function_tool(
            "final_answer",
            "Finish the search loop with a structured answer.",
            {
                "answer": {"type": "string"},
                "answerable": {"type": "boolean"},
                "unable_reason": {"type": "string"},
                "local_sources": {
                    "type": "array",
                    "items": {"oneOf": [{"type": "object"}, {"type": "string"}]},
                },
                "web_sources": {
                    "type": "array",
                    "items": {"oneOf": [{"type": "object"}, {"type": "string"}]},
                },
            },
            ["answer", "answerable"],
        )
    )
    return tools


def function_tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


def should_use_web(web_policy: str, needs_web: bool, local_sources: list[LocalSearchResult]) -> bool:
    """根据 web_policy 策略和证据状态决定是否启用网络搜索。"""
    if web_policy == "never":
        return False
    if web_policy == "always":
        return True
    # auto 模式：评估器要求网络验证，或本地证据少于 2 条时启用
    return needs_web or len(local_sources) < 2


def merge_local_sources(
    existing: list[LocalSearchResult],
    new_items: list[LocalSearchResult],
) -> list[LocalSearchResult]:
    """合并多轮搜索结果，同一文档保留最高分，按分数降序排列。"""
    by_path: dict[Path, LocalSearchResult] = {item.path: item for item in existing}
    for item in new_items:
        current = by_path.get(item.path)
        if current is None or item.score > current.score:
            by_path[item.path] = item
    return sorted(by_path.values(), key=lambda item: item.score, reverse=True)


def rank_final_sources(question: str, sources: list[LocalSearchResult]) -> list[LocalSearchResult]:
    """对最终本地来源重新排序，按领域、事项、时效性和权威性加权。"""
    return sorted(sources, key=lambda item: final_source_score(question, item), reverse=True)


def final_source_score(question: str, source: LocalSearchResult) -> float:
    """计算最终排序分数：基础分 + 领域/事项/年份/状态/权威来源信号。"""
    score = source.score
    text = source_text(source)
    if domains_for_question(question):
        score += -80 if is_domain_mismatch(question, source) else 40
    for term in service_terms_for_question(question):
        if term in text:
            score += 18
    years = requested_years(question)
    if years:
        score += 80 if years & source_years(source) else -35
    if source_is_active(source):
        score += 30
    if source_is_superseded(source):
        score -= 30
    if source_is_official(source):
        score += 20
    if "规范性文件" in str(source.path) or "通知" in source.title:
        score += 10
    return score


def filter_final_sources(question: str, sources: list[LocalSearchResult]) -> list[LocalSearchResult]:
    """过滤最终来源：移除领域错配来源，当前政策问题优先保留目标年份或最新年份。"""
    relevant = [source for source in sources if not is_domain_mismatch(question, source)]
    if domains_for_question(question) and not relevant:
        return []
    filtered = relevant or sources
    years = requested_years(question)
    if years:
        year_matches = [source for source in filtered if years & source_years(source)]
        return year_matches or filtered
    if is_current_policy_question(question):
        year = latest_year(filtered)
        if year is not None:
            latest_sources = [source for source in filtered if year in source_years(source)]
            return latest_sources or filtered
    return filtered


def build_unable_reason(decision: EvidenceDecision | None) -> str:
    """构建"无法回答"的原因说明，用于返回给用户。"""
    if decision is None:
        return "没有找到足够证据。"
    if decision.missing_facts:
        return "缺少证据：" + "、".join(decision.missing_facts)
    return decision.reason or "没有找到足够证据。"


def build_unanswerable_answer(
    question: str,
    unable_reason: str,
    local_sources: list[LocalSearchResult],
    web_sources: list[WebSearchResult],
) -> str:
    """证据不足时构造保守回答，避免大模型基于不充分证据继续发挥。"""
    lines = [
        f"问题：{question}",
        "",
        f"无法回答：{unable_reason}",
    ]
    if local_sources:
        lines.append("")
        lines.append("已检索到的本地来源：")
        for source in local_sources[:5]:
            lines.append(f"- {source.title}（{source.path}）")
    if web_sources:
        lines.append("")
        lines.append("已检索到的网络来源：")
        for source in web_sources[:5]:
            lines.append(f"- {source.title}（{source.url}）")
    return "\n".join(lines)
