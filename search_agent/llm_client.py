from __future__ import annotations

import json
import urllib.request

from .models import EvidenceDecision, LocalSearchResult, SearchPlan, SearchRound, WebPageContent, WebSearchResult


class BailianClient:
    def __init__(self, api_key: str | None, model: str, base_url: str):
        """初始化百炼兼容接口客户端。"""
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
        """基于本地资料、搜索结果和网页正文生成最终中文回答。"""
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

    def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        tool_choice="auto",
        temperature: float = 0.2,
    ) -> dict:
        """调用百炼 OpenAI 兼容 Chat Completions tool-calling 接口。"""
        if not self.api_key:
            raise RuntimeError("DASHSCOPE_API_KEY is required for tool calling")
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
            "temperature": temperature,
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
        message = result["choices"][0]["message"]
        if message.get("content") is None:
            message["content"] = ""
        if not message.get("tool_calls"):
            message["tool_calls"] = []
        return message

    def evaluate_evidence(
        self,
        question: str,
        terms: list[str],
        local_sources: list[LocalSearchResult],
        rounds: list[SearchRound],
        plan: SearchPlan,
    ) -> EvidenceDecision | None:
        """调用大模型评估当前证据是否充分，并解析为结构化决策。"""
        if not self.api_key:
            return None
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是资料检索智能体的证据评估器。"
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

    def compress_conversation(
        self,
        messages: list[dict],
        keep_recent: int = 4,
        summary_prefix: str = "先前对话摘要：",
    ) -> list[dict]:
        """压缩旧对话为摘要，保留最近几轮对话原文。"""
        if not messages:
            return messages
        system_msg = None
        rest = []
        for msg in messages:
            if msg.get("role") == "system" and system_msg is None:
                system_msg = msg
            else:
                rest.append(msg)
        if system_msg is None:
            system_msg = {"role": "system", "content": ""}
            rest = list(messages)

        user_indices = [i for i, m in enumerate(rest) if m.get("role") == "user"]
        if len(user_indices) <= keep_recent:
            return messages

        cut = user_indices[-keep_recent]
        old_msgs = rest[:cut]
        recent_msgs = rest[cut:]

        summary = self._summarize_messages(old_msgs)
        if summary is None:
            return messages

        result = [system_msg]
        result.append({"role": "user", "content": summary_prefix + summary})
        result.append({"role": "assistant", "content": "已了解。"})
        result.extend(recent_msgs)
        return result

    def _summarize_messages(self, messages: list[dict]) -> str | None:
        """调用 LLM 将消息列表压缩为摘要文本。"""
        if not self.api_key:
            return None
        lines = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content") or ""
            if not content:
                continue
            if role == "user":
                lines.append(f"用户：{content[:500]}")
            elif role == "assistant":
                lines.append(f"助手：{content[:500]}")
        if not lines:
            return None
        conversation_text = "\n".join(lines)
        prompt = (
            "请将以下多轮对话历史压缩为一段简洁的摘要，保留以下关键信息：\n"
            "1. 用户之前问过的所有问题的要点\n"
            "2. 搜索中发现的关键事实和数据\n"
            "3. 之前的回答中提到的政策、金额、比例等具体数据\n"
            "4. 用户提到的地区、身份等个人信息\n\n"
            f"对话历史：\n{conversation_text}\n\n"
            "请直接输出摘要文本，不要使用 Markdown 格式。"
        )
        try:
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "你是一个对话摘要助手。"},
                    {"role": "user", "content": prompt},
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
        except Exception:
            return None


def build_prompt(
    question: str,
    local_sources: list[LocalSearchResult],
    web_sources: list[WebSearchResult],
    web_pages: list[WebPageContent],
) -> str:
    """构造最终回答阶段的用户提示词。"""
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
    """构造证据评估阶段的用户提示词，引导大模型输出固定 JSON。"""
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
        "请逐项判断本地证据是否足以直接回答用户问题：\n"
        "1. 先抽取问题真正需要的事实点，不要依赖固定业务规则或关键词模板。\n"
        "2. 对照每条本地证据的标题、片段、路径和命中词，判断事实点是否被证据明确覆盖。\n"
        "3. 不要因为命中数量多就认为充分；证据必须覆盖问题所问的主体、事项、时间、金额、比例、条件或办理动作。\n"
        "4. 如果问题要求用户个人账户、余额、个人状态、资格结果等个体化数据，而本地证据只是通用政策，"
        "应判定 is_sufficient=false，并在 missing_facts 中说明缺少用户个人账户或个体化数据。\n"
        "5. 如果问题涉及现行、最新、今天、当前，或答案依赖会变化的日期、金额、比例、基数、上下限、标准，"
        "通常 needs_web=true，用于联网核对官方最新信息。\n"
        "6. 如果本地证据方向正确但缺少事实点，next_terms 给出下一轮本地检索词；"
        "如果证据领域不匹配，missing_facts 说明领域不匹配。\n"
        "7. 生成 next_terms 时只给本地检索关键词，不要写完整问句或自然语言查询句。"
        "每个词尽量 2-6 个汉字；政策年份、金额、比例可以单独成词。"
        "优先使用可能出现在标题、目录、元数据或正文中的短词。"
        "将长查询拆成多个短词，例如不要写“上海灵活就业社保最低缴费标准”，"
        "应写 [\"上海\", \"灵活就业\", \"社保\", \"缴费基数\", \"下限\", \"缴费比例\", \"最低缴费\"]。"
        "必须保留业务领域锚点，避免只返回“基数、下限、比例、材料”等跨领域泛词；"
        "例如社保问题保留“社保、社会保险、灵活就业”，公积金问题保留“公积金、住房公积金”，"
        "医保问题保留“医保、医疗保险”。避免重复当前关键词和已经命中的词，最多返回 6-10 个。\n\n"
        "请只返回 JSON，字段固定为："
        "{\"is_sufficient\": true/false, \"needs_web\": true/false, "
        "\"next_terms\": [\"词1\"], \"missing_facts\": [\"缺口\"], \"reason\": \"一句话原因\"}。"
    )


def parse_evidence_decision(content: str) -> EvidenceDecision | None:
    """解析大模型返回的证据评估 JSON，解析失败时返回 None。"""
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
    """未配置大模型密钥时，返回检索证据摘要。"""
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
