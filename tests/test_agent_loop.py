import tempfile
import unittest
from pathlib import Path

from search_agent.agent_loop import SearchAgent
from search_agent.models import WebPageContent, WebSearchResult


class FakeLlmClient:
    def __init__(self):
        self.calls = []

    def answer(self, question, local_sources, web_sources, web_pages=None):
        self.calls.append((question, local_sources, web_sources, web_pages or []))
        return "根据资料，失业后可按灵活就业人员参保缴费。"


class FakeWebSearch:
    def __init__(self):
        self.calls = []

    def search(self, query, num=5):
        self.calls.append((query, num))
        return [
            WebSearchResult(
                title="上海人社灵活就业参保",
                url="https://rsj.sh.gov.cn/example",
                snippet="灵活就业人员可以办理参保登记。",
                date=None,
            )
        ]


class FakeWebFetcher:
    def __init__(self):
        self.calls = []

    def fetch_many(self, results, query_terms):
        self.calls.append((results, query_terms))
        return [
            WebPageContent(
                title="上海人社灵活就业参保",
                url=results[0].url,
                text="2025年度上海灵活就业人员可按规定缴纳养老保险和医疗保险。",
                provider="jina",
                status="ok",
            )
        ]


class SearchAgentTests(unittest.TestCase):
    def test_no_web_policy_skips_network_even_for_current_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = root / "社保.md"
            doc.write_text("# 灵活就业参保\n\n失业后可以办理灵活就业参保缴费。\n", encoding="utf-8")
            web = FakeWebSearch()
            llm = FakeLlmClient()
            agent = SearchAgent(data_dir=root, llm_client=llm, web_search=web)

            result = agent.ask("现在失业了怎么缴纳社保", web_policy="never")

        self.assertFalse(result.used_web)
        self.assertEqual(web.calls, [])
        self.assertIn("灵活就业", result.answer)
        self.assertGreaterEqual(len(result.local_sources), 1)

    def test_auto_policy_uses_web_for_current_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = root / "社保.md"
            doc.write_text("# 灵活就业参保\n\n失业后可以办理灵活就业参保缴费。\n", encoding="utf-8")
            web = FakeWebSearch()
            agent = SearchAgent(data_dir=root, llm_client=FakeLlmClient(), web_search=web)

            result = agent.ask("现在上海灵活就业社保最低交多少钱", web_policy="auto")

        self.assertTrue(result.used_web)
        self.assertGreaterEqual(len(web.calls), 1)
        self.assertEqual(result.web_sources[0].title, "上海人社灵活就业参保")

    def test_web_fetch_content_is_passed_to_llm_after_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = root / "社保.md"
            doc.write_text("# 灵活就业参保\n\n失业后可以办理灵活就业参保缴费。\n", encoding="utf-8")
            web = FakeWebSearch()
            fetcher = FakeWebFetcher()
            llm = FakeLlmClient()
            agent = SearchAgent(data_dir=root, llm_client=llm, web_search=web, web_fetcher=fetcher)

            result = agent.ask("现在上海灵活就业社保最低交多少钱", web_policy="always")

        self.assertEqual(len(fetcher.calls), 1)
        self.assertEqual(len(result.web_pages), 1)
        self.assertIn("2025年度上海灵活就业人员", result.web_pages[0].text)
        self.assertEqual(len(llm.calls[0][2]), 1)
        self.assertEqual(len(llm.calls[0][3]), 1)


if __name__ == "__main__":
    unittest.main()
