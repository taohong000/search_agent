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


class FakeFundWebSearch:
    def __init__(self):
        self.calls = []

    def search(self, query, num=5):
        self.calls.append((query, num))
        return [
            WebSearchResult(
                title="2025年度住房公积金基数调整",
                url="https://www.shzfgjj.cn/static/jstz/index.html",
                snippet="上海住房公积金网当前展示2025年度住房公积金基数调整。",
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
    def test_database_only_questions_use_front_matter_and_version_indexes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_policy_fixture(root)
            agent = SearchAgent(data_dir=root, llm_client=FakeLlmClient(), max_rounds=3)

            cases = [
                (
                    "2025年度上海住房公积金的单位和职工缴存比例是多少？",
                    "2025年度基数调整问答",
                ),
                (
                    "上海市场租赁住房提取公积金的月提取限额是多少？",
                    "关于优化本市住房公积金租赁提取业务问答",
                ),
                (
                    "长三角异地住房公积金贷款还贷提取中，同时偿还多笔异地贷款时同一时间支持几笔？",
                    "长三角异地住房公积金贷款还贷提取业务问答",
                ),
            ]

            results = [(question, agent.ask(question, web_policy="never", top_k=5)) for question, _ in cases]

        for (question, result), (_, expected_title) in zip(results, cases):
            with self.subTest(question=question):
                self.assertTrue(result.answerable, result.unable_reason)
                self.assertFalse(result.used_web)
                self.assertTrue(result.local_sources)
                self.assertEqual(result.local_sources[0].title, expected_title)

    def test_personal_account_question_is_not_answerable_from_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_policy_fixture(root)
            agent = SearchAgent(data_dir=root, llm_client=FakeLlmClient(), max_rounds=3)

            result = agent.ask("帮我查询一下我个人公积金账户现在余额是多少？", web_policy="never", top_k=5)

        self.assertFalse(result.answerable)
        self.assertFalse(result.used_web)
        self.assertIn("个人账户", result.unable_reason)

    def test_today_new_policy_question_uses_web_even_with_local_indexes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_policy_fixture(root)
            web = FakeFundWebSearch()
            agent = SearchAgent(data_dir=root, llm_client=FakeLlmClient(), web_search=web, max_rounds=3)

            result = agent.ask(
                "今天上海住房公积金网有没有发布新的2026年度基数调整通知？",
                web_policy="auto",
                top_k=5,
            )

        self.assertTrue(result.used_web)
        self.assertEqual(len(web.calls), 1)
        self.assertEqual(result.web_sources[0].title, "2025年度住房公积金基数调整")

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


def write_policy_fixture(root: Path) -> None:
    policy_dir = root / "官网" / "上海住房公积金网" / "政策解读"
    index_dir = policy_dir / "_indexes" / "version"
    policy_dir.mkdir(parents=True)
    index_dir.mkdir(parents=True)

    (index_dir / "基数调整问答.md").write_text(
        "---\n"
        "index_type: \"version_index\"\n"
        "version_group_id: 151\n"
        "current_policy_document_id: 322\n"
        "current_version_no: 4\n"
        "group_name: \"基数调整问答\"\n"
        "---\n\n"
        "# 基数调整问答\n\n"
        "| 版本 | 文档ID | 标题 | 生效日期 |\n"
        "|---|---:|---|---|\n"
        "| 4 | 322 | 2025年度基数调整问答 | 2025-07-01 |\n"
        "| 3 | 328 | 2024年度基数调整问答 | 2024-07-01 |\n",
        encoding="utf-8",
    )
    (policy_dir / "2025年度基数调整问答.md").write_text(
        "---\n"
        "policy_document_id: 322\n"
        "version_group_id: 151\n"
        "version_index_path: \"_indexes/version/基数调整问答.md\"\n"
        "title: \"2025年度基数调整问答\"\n"
        "effective_date: \"2025-07-01\"\n"
        "version_no: 4\n"
        "doc_status: \"active\"\n"
        "primary_business_line: \"公积金\"\n"
        "business_lines: [\"公积金\"]\n"
        "service_items: [\"缴存基数调整\", \"缴存比例调整\", \"月缴存额\"]\n"
        "doc_kind: \"faq\"\n"
        "agent_eligible: true\n"
        "---\n\n"
        "# 2025年度基数调整问答\n\n"
        "## 四、2025年度住房公积金的缴存比例是多少？\n\n"
        "答：2025年度单位和职工住房公积金缴存比例为各5%~7%（取整数值）。\n\n"
        "## 五、住房公积金月缴存额如何计算？\n\n"
        "答：住房公积金月缴存额 = 缴存基数 × 单位住房公积金缴存比例 + "
        "缴存基数 × 职工住房公积金缴存比例。\n",
        encoding="utf-8",
    )
    (policy_dir / "2024年度基数调整问答.md").write_text(
        "---\n"
        "policy_document_id: 328\n"
        "version_group_id: 151\n"
        "title: \"2024年度基数调整问答\"\n"
        "effective_date: \"2024-07-01\"\n"
        "version_no: 3\n"
        "doc_status: \"superseded\"\n"
        "primary_business_line: \"公积金\"\n"
        "service_items: [\"缴存基数调整\", \"缴存比例调整\"]\n"
        "agent_eligible: true\n"
        "---\n\n"
        "# 2024年度基数调整问答\n\n"
        "答：2024年度单位和职工住房公积金缴存比例为各5%~7%。\n",
        encoding="utf-8",
    )
    (policy_dir / "关于优化本市住房公积金租赁提取业务问答.md").write_text(
        "---\n"
        "policy_document_id: 327\n"
        "title: \"关于优化本市住房公积金租赁提取业务问答\"\n"
        "effective_date: \"2024-11-01\"\n"
        "doc_status: \"active\"\n"
        "primary_business_line: \"公积金\"\n"
        "service_items: [\"公积金提取\", \"租赁提取\"]\n"
        "doc_kind: \"faq\"\n"
        "agent_eligible: true\n"
        "---\n\n"
        "# 关于优化本市住房公积金租赁提取业务问答\n\n"
        "## 三、《通知》施行后，各类住房租赁提取额度是多少？\n\n"
        "答：在本市无自有住房，依法租赁市场租赁住房的，每户家庭月提取限额为4000元。\n",
        encoding="utf-8",
    )
    (policy_dir / "长三角异地住房公积金贷款还贷提取业务问答.md").write_text(
        "---\n"
        "policy_document_id: 330\n"
        "title: \"长三角异地住房公积金贷款还贷提取业务问答\"\n"
        "doc_status: \"active\"\n"
        "primary_business_line: \"公积金\"\n"
        "service_items: [\"公积金提取\", \"异地贷款\", \"还贷提取\"]\n"
        "doc_kind: \"faq\"\n"
        "agent_eligible: true\n"
        "---\n\n"
        "# 长三角异地住房公积金贷款还贷提取业务问答\n\n"
        "答：申请人同时偿还多笔异地贷款的，同一时间仅支持一笔贷款办理还贷提取。\n",
        encoding="utf-8",
    )
    (policy_dir / "2025年度住房公积金缴存基数调整温馨提示.md").write_text(
        "---\n"
        "title: \"2025年度住房公积金缴存基数调整温馨提示\"\n"
        "doc_status: \"active\"\n"
        "primary_business_line: \"公积金\"\n"
        "service_items: [\"缴存基数调整\"]\n"
        "agent_eligible: true\n"
        "---\n\n"
        "# 2025年度住房公积金缴存基数调整温馨提示\n\n"
        "上海住房公积金缴存基数调整，公积金，住房公积金，缴存，基数调整。\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
