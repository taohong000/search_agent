import tempfile
import unittest
from pathlib import Path

from search_agent.agent_loop import EvidenceDecision, SearchAgent
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


class FakeEvidenceEvaluator:
    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.calls = []

    def evaluate(self, question, terms, local_sources, rounds, plan):
        self.calls.append((question, list(terms), list(local_sources), list(rounds), plan))
        if self.decisions:
            return self.decisions.pop(0)
        return EvidenceDecision(is_sufficient=True, needs_web=False)


class OverconfidentLlmClient(FakeLlmClient):
    def evaluate_evidence(self, question, terms, local_sources, rounds, plan):
        return EvidenceDecision(is_sufficient=True, needs_web=False, reason="LLM thinks enough.")


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

    def test_evaluator_can_continue_local_search_after_enough_hits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index in range(3):
                doc = root / f"公积金基础{index}.md"
                doc.write_text("# 公积金\n\n上海住房公积金可以由单位缴存。\n", encoding="utf-8")
            detail = root / "缴存比例.md"
            detail.write_text("# 缴存比例\n\n单位和职工住房公积金缴存比例为各5%至7%。\n", encoding="utf-8")
            evaluator = FakeEvidenceEvaluator(
                [
                    EvidenceDecision(
                        is_sufficient=False,
                        needs_web=False,
                        next_terms=["缴存比例"],
                        missing_facts=["缴存比例"],
                        reason="Need ratio details.",
                    ),
                    EvidenceDecision(is_sufficient=True, needs_web=False),
                ]
            )
            agent = SearchAgent(
                data_dir=root,
                llm_client=FakeLlmClient(),
                evidence_evaluator=evaluator,
                max_rounds=3,
            )

            result = agent.ask("上海公积金是如何缴存的", web_policy="never", top_k=3)

        self.assertEqual(len(result.search_rounds), 2)
        self.assertEqual(result.search_rounds[1].query_terms, ["缴存比例"])
        self.assertGreaterEqual(len(evaluator.calls), 2)

    def test_evaluator_can_require_web_verification_for_policy_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = root / "公积金.md"
            doc.write_text("# 公积金缴存\n\n上海住房公积金由单位和职工共同缴存。\n", encoding="utf-8")
            web = FakeWebSearch()
            evaluator = FakeEvidenceEvaluator(
                [
                    EvidenceDecision(
                        is_sufficient=True,
                        needs_web=True,
                        reason="Policy answer should be verified against official current sources.",
                    )
                ]
            )
            agent = SearchAgent(
                data_dir=root,
                llm_client=FakeLlmClient(),
                web_search=web,
                evidence_evaluator=evaluator,
            )

            result = agent.ask("上海公积金是如何缴存的", web_policy="auto")

        self.assertTrue(result.used_web)
        self.assertEqual(len(web.calls), 1)

    def test_default_evaluator_expands_current_fund_question_to_policy_year_terms(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_doc = root / "2018问答.md"
            old_doc.write_text(
                "# 2018年度住房公积金基数调整问答\n\n"
                "上海住房公积金缴存基数可以调整。住房公积金缴存基数可以调整。\n",
                encoding="utf-8",
            )
            current_doc = root / "2025通知.md"
            current_doc.write_text(
                "# 2025年度调整通知\n\n"
                "2025年度上海市调整住房公积金缴存基数、比例以及月缴存额上下限。"
                "缴存基数按2024年月平均工资确定。"
                "单位和职工缴存比例为各5%至7%。"
                "月缴存额是基数分别乘以单位和职工比例之和，上限和下限按年度通知执行。\n",
                encoding="utf-8",
            )
            agent = SearchAgent(data_dir=root, llm_client=FakeLlmClient(), max_rounds=3)

            result = agent.ask("上海公积金是如何缴存的", web_policy="never", top_k=1)

        self.assertGreaterEqual(len(result.search_rounds), 2)
        self.assertIn("2025年度", result.search_rounds[1].query_terms)
        self.assertEqual(result.local_sources[0].title, "2025年度调整通知")

    def test_rule_guard_overrides_overconfident_llm_evaluation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_doc = root / "2018问答.md"
            old_doc.write_text(
                "# 2018年度住房公积金基数调整问答\n\n"
                "上海住房公积金缴存基数可以调整。住房公积金缴存基数可以调整。\n",
                encoding="utf-8",
            )
            current_doc = root / "2025通知.md"
            current_doc.write_text(
                "# 2025年度调整通知\n\n"
                "2025年度上海市调整住房公积金缴存基数、比例以及月缴存额上下限。"
                "缴存基数按2024年月平均工资确定。"
                "单位和职工缴存比例为各5%至7%。"
                "月缴存额是缴存基数分别乘以单位和职工比例之和，上限和下限按年度通知执行。\n",
                encoding="utf-8",
            )
            agent = SearchAgent(data_dir=root, llm_client=OverconfidentLlmClient(), max_rounds=3)

            result = agent.ask("上海公积金是如何缴存的", web_policy="never", top_k=1)

        self.assertGreaterEqual(len(result.search_rounds), 2)
        self.assertEqual(result.local_sources[0].title, "2025年度调整通知")

    def test_current_fund_answer_sources_filter_out_stale_years(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current_doc = root / "2025通知.md"
            current_doc.write_text(
                "# 关于2025年度上海市调整住房公积金缴存基数、比例以及月缴存额上下限的通知\n\n"
                "住房公积金缴存基数最高不超过37302元，最低不低于2690元。"
                "单位和职工住房公积金缴存比例为各5%~7%。"
                "住房公积金月缴存额上限为5222元，下限为376元。\n",
                encoding="utf-8",
            )
            stale_doc = root / "2024通知.md"
            stale_doc.write_text(
                "# 关于2024年度上海市调整住房公积金缴存基数、比例以及月缴存额上下限的通知\n\n"
                "住房公积金缴存基数最高不超过36921元。"
                "住房公积金月缴存额上限为5168元。\n",
                encoding="utf-8",
            )
            agent = SearchAgent(data_dir=root, llm_client=FakeLlmClient(), max_rounds=3)

            result = agent.ask("上海公积金是如何缴存的", web_policy="never", top_k=8)

        self.assertTrue(result.local_sources)
        self.assertTrue(all("2024年度" not in source.title for source in result.local_sources))

    def test_unrelated_sources_mark_answer_not_answerable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = root / "公积金.md"
            doc.write_text("# 上海公积金\n\n住房公积金月缴存额上下限。\n", encoding="utf-8")
            agent = SearchAgent(data_dir=root, llm_client=FakeLlmClient(), max_rounds=2)

            result = agent.ask("在上海申领生育津贴需要什么条件和材料？", web_policy="never", top_k=5)

        self.assertFalse(result.answerable)
        self.assertIn("生育津贴", result.unable_reason)


if __name__ == "__main__":
    unittest.main()
