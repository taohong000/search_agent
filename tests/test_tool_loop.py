import json
import tempfile
import unittest
from pathlib import Path

from search_agent.agent_loop import SearchAgent
from search_agent.models import WebPageContent, WebSearchResult


class FakeToolClient:
    api_key = "test-key"

    def __init__(self, messages):
        self.messages = list(messages)
        self.calls = []

    def chat_with_tools(self, messages, tools, tool_choice="auto", temperature=0.2):
        self.calls.append(
            {
                "messages": list(messages),
                "tools": list(tools),
                "tool_choice": tool_choice,
                "temperature": temperature,
            }
        )
        if isinstance(tool_choice, dict):
            return tool_message("forced-final", "final_answer", {"answer": "", "answerable": False})
        return self.messages.pop(0)


class FakeWebSearch:
    def search(self, query, num=5):
        return [
            WebSearchResult(
                title="上海人社",
                url="https://example.test/policy",
                snippet="现行灵活就业政策。",
                date="2026-05-01",
            )
        ]


class FakeWebFetcher:
    def fetch_many(self, results, query_terms):
        return [
            WebPageContent(
                title="上海人社",
                url=results[0].url,
                text="2026年灵活就业人员缴费政策正文。",
                provider="jina",
                status="ok",
            )
        ]


class ToolLoopTests(unittest.TestCase):
    def test_clarification_gate_asks_before_exposing_search_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "公积金.md").write_text("# 公积金缴存\n\n上海住房公积金缴存政策。\n", encoding="utf-8")
            client = FakeToolClient(
                [
                    tool_message(
                        "call-clarify",
                        "clarification_decision",
                        {
                            "needs_clarification": True,
                            "question": "请问您想了解哪个城市、哪类身份的公积金缴存政策？",
                            "reason": "缺少城市和身份类型。",
                        },
                    ),
                    tool_message("call-rg", "rg_search", {"query": "公积金"}),
                ]
            )
            agent = SearchAgent(data_dir=root, llm_client=client, max_tool_steps=3)

            result = agent.ask("公积金如何缴存？", web_policy="never")

        self.assertTrue(result.needs_clarification)
        self.assertEqual(result.local_sources, [])
        exposed = {tool["function"]["name"] for tool in client.calls[0]["tools"]}
        self.assertEqual(exposed, {"clarification_decision"})
        self.assertEqual(len(client.calls), 1)

    def test_clarification_gate_allows_clear_question_to_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "公积金.md").write_text("# 上海公积金缴存\n\n单位和职工共同缴存住房公积金。\n", encoding="utf-8")
            client = FakeToolClient(
                [
                    tool_message(
                        "call-no-clarify",
                        "clarification_decision",
                        {
                            "needs_clarification": False,
                            "question": "",
                            "reason": "问题已包含城市和业务事项。",
                        },
                    ),
                    tool_message("call-rg", "rg_search", {"query": "公积金 缴存", "city_code": "SH"}),
                    tool_message(
                        "call-final",
                        "final_answer",
                        {
                            "answer": "上海公积金由单位和职工共同缴存。",
                            "answerable": True,
                            "local_sources": [{"path": "公积金.md"}],
                        },
                    ),
                ]
            )
            agent = SearchAgent(data_dir=root, llm_client=client, max_tool_steps=3)

            result = agent.ask("上海公积金如何缴存？", web_policy="never")

        self.assertFalse(result.needs_clarification)
        self.assertTrue(result.answerable)
        exposed = {tool["function"]["name"] for tool in client.calls[1]["tools"]}
        self.assertIn("rg_search", exposed)

    def test_tool_loop_passes_tool_results_to_next_round_and_final_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "社保.md").write_text("# 灵活就业参保\n\n失业后可以办理灵活就业参保。\n", encoding="utf-8")
            client = FakeToolClient(
                [
                    no_clarification_message(),
                    tool_message("call-rg", "rg_search", {"query": "灵活就业"}),
                    tool_message("call-read", "read_local_file", {"path": "社保.md", "start_line": 1, "max_lines": 20}),
                    tool_message(
                        "call-final",
                        "final_answer",
                        {
                            "answer": "失业后可以办理灵活就业参保。",
                            "answerable": True,
                            "local_sources": [{"path": "社保.md"}],
                        },
                    ),
                ]
            )
            agent = SearchAgent(data_dir=root, llm_client=client, max_tool_steps=5)

            result = agent.ask("失业后怎么缴纳社保？", web_policy="never")

        self.assertTrue(result.answerable)
        self.assertFalse(result.used_web)
        self.assertEqual(result.local_sources[0].title, "灵活就业参保")
        self.assertTrue(any(message["role"] == "tool" for message in client.calls[2]["messages"]))

    def test_tool_loop_uses_web_search_and_fetch_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "社保.md").write_text("# 社保\n\n本地社保政策。\n", encoding="utf-8")
            client = FakeToolClient(
                [
                    no_clarification_message(),
                    tool_message("call-web", "web_search", {"query": "上海 灵活就业 社保 2026", "num": 1}),
                    tool_message(
                        "call-fetch",
                        "web_fetch",
                        {"urls": ["https://example.test/policy"], "query_terms": ["灵活就业"]},
                    ),
                    tool_message(
                        "call-final",
                        "final_answer",
                        {
                            "answer": "已联网核对现行政策。",
                            "answerable": True,
                            "web_sources": [{"url": "https://example.test/policy"}],
                        },
                    ),
                ]
            )
            agent = SearchAgent(
                data_dir=root,
                llm_client=client,
                web_search=FakeWebSearch(),
                web_fetcher=FakeWebFetcher(),
                max_tool_steps=5,
            )

            result = agent.ask("现在上海灵活就业社保政策是什么？", web_policy="always")

        self.assertTrue(result.used_web)
        self.assertEqual(result.web_sources[0].title, "上海人社")
        self.assertEqual(result.web_pages[0].provider, "jina")

    def test_tool_loop_forces_final_answer_after_step_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "社保.md").write_text("# 社保\n\n灵活就业。\n", encoding="utf-8")
            client = FakeToolClient(
                [
                    no_clarification_message(),
                    tool_message("call-rg", "rg_search", {"query": "灵活就业"}),
                    tool_message("call-final", "final_answer", {"answer": "", "answerable": False}),
                ]
            )
            agent = SearchAgent(data_dir=root, llm_client=client, max_tool_steps=1)

            result = agent.ask("问题", web_policy="never")

        self.assertFalse(result.answerable)
        self.assertEqual(client.calls[-1]["tool_choice"], "auto")
        self.assertIn("final_answer", [tool["function"]["name"] for tool in client.calls[-1]["tools"]])

    def test_no_web_policy_does_not_expose_web_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "社保.md").write_text("# 社保\n\n灵活就业。\n", encoding="utf-8")
            client = FakeToolClient(
                [
                    no_clarification_message(),
                    tool_message("call-web", "web_search", {"query": "should be unavailable"}),
                    tool_message("call-fuzzy", "fuzzy_file_search", {"query": "社保"}),
                    tool_message(
                        "call-final",
                        "final_answer",
                        {
                            "answer": "无法联网。",
                            "answerable": False,
                            "unable_reason": "禁止联网。",
                        },
                    ),
                ]
            )
            agent = SearchAgent(data_dir=root, llm_client=client, web_search=FakeWebSearch(), max_tool_steps=3)

            result = agent.ask("问题", web_policy="never")

        exposed = {tool["function"]["name"] for tool in client.calls[1]["tools"]}
        self.assertNotIn("web_search", exposed)
        self.assertFalse(result.used_web)
        self.assertFalse(result.answerable)
        self.assertIn("tool unavailable: web_search", client.calls[2]["messages"][-1]["content"])

    def test_premature_final_answer_is_rejected_until_local_search_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "公积金.md").write_text("# 公积金缴存\n\n单位和职工共同缴存住房公积金。\n", encoding="utf-8")
            client = FakeToolClient(
                [
                    no_clarification_message(),
                    tool_message(
                        "call-final-too-soon",
                        "final_answer",
                        {"answer": "证据不足。", "answerable": False, "unable_reason": "未搜索。"},
                    ),
                    tool_message("call-rg", "rg_search", {"query": "共同缴存"}),
                    tool_message(
                        "call-final",
                        "final_answer",
                        {
                            "answer": "单位和职工共同缴存住房公积金。",
                            "answerable": True,
                            "local_sources": [{"path": "公积金.md"}],
                        },
                    ),
                ]
            )
            agent = SearchAgent(data_dir=root, llm_client=client, max_tool_steps=4)

            result = agent.ask("上海公积金如何缴存", web_policy="auto")

        self.assertTrue(result.answerable)
        self.assertIn("final_answer rejected", client.calls[2]["messages"][-1]["content"])


def tool_message(call_id, name, arguments):
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
            }
        ],
    }


def no_clarification_message():
    return tool_message(
        "call-no-clarify",
        "clarification_decision",
        {"needs_clarification": False, "question": "", "reason": "问题足够明确。"},
    )


if __name__ == "__main__":
    unittest.main()
