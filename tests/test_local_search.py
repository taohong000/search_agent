import tempfile
import unittest
from pathlib import Path

from search_agent.local_search import LocalSearchEngine


class LocalSearchEngineTests(unittest.TestCase):
    def test_search_matches_path_heading_and_body_with_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = root / "公众号" / "上海社保公众号" / "@灵活就业人员，参保缴费看这里！.md"
            doc.parent.mkdir(parents=True)
            doc.write_text(
                "# 灵活就业人员参保缴费\n\n"
                "失业后可以按灵活就业人员参加养老保险和医疗保险。\n",
                encoding="utf-8",
            )

            other = root / "官网" / "上海住房公积金网" / "缴存说明.md"
            other.parent.mkdir(parents=True)
            other.write_text("# 公积金缴存\n\n单位和个人按比例缴存。\n", encoding="utf-8")

            engine = LocalSearchEngine(root)
            results = engine.search(["失业", "灵活就业", "参保"], top_k=5)

        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].title, "灵活就业人员参保缴费")
        self.assertIn("失业后可以按灵活就业人员", results[0].snippet)
        self.assertIn("灵活就业", results[0].matched_terms)
        self.assertGreater(results[0].score, 0)

    def test_search_returns_empty_for_unmatched_terms(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = root / "a.md"
            doc.write_text("# 上海社保\n\n养老保险内容。\n", encoding="utf-8")

            results = LocalSearchEngine(root).search(["火星政策"], top_k=5)

        self.assertEqual(results, [])

    def test_specific_policy_phrase_beats_generic_many_term_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            specific = root / "公众号" / "上海社保公众号" / "@灵活就业人员，参保缴费看这里！.md"
            specific.parent.mkdir(parents=True)
            specific.write_text("# 灵活就业人员参保缴费\n\n个人缴费可以办理参保登记。\n", encoding="utf-8")

            generic = root / "公众号" / "上海社保公众号" / "社会保险参保缴费问答.md"
            generic.write_text(
                "# 社会保险参保缴费问答\n\n"
                "上海社保、社会保险、参保、缴费、养老保险、医疗保险、失业保险。\n",
                encoding="utf-8",
            )

            results = LocalSearchEngine(root).search(
                ["上海", "社保", "社会保险", "参保", "缴费", "灵活就业", "个人缴费"],
                top_k=2,
            )

        self.assertEqual(results[0].title, "灵活就业人员参保缴费")

    def test_policy_snippet_includes_body_facts_not_only_title_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = root / "官网" / "上海住房公积金网" / "政策文件" / "规范性文件" / "关于2025年度上海市调整住房公积金缴存基数、比例以及月缴存额上下限的通知.md"
            doc.parent.mkdir(parents=True)
            doc.write_text(
                "# 关于2025年度上海市调整住房公积金缴存基数、比例以及月缴存额上下限的通知\n\n"
                "文号：沪公积金管委会〔2025〕8号\n\n"
                "索取号：SY4250087880-2025-228051。信息名称、发布机构、关键词、业务类别、内容描述、信息有效性等元数据用于网页展示。\n\n"
                "各住房公积金缴存单位：根据相关规定，结合本市实际，现就年度调整事项说明如下。\n\n"
                "住房公积金缴存基数最高不超过37302元，最低不低于2690元。\n\n"
                "单位和职工住房公积金缴存比例为各5%~7%。\n\n"
                "住房公积金月缴存额是缴存基数分别乘以所在单位和职工本人的住房公积金缴存比例之和。\n"
                "上述上限和下限按年度标准执行。\n",
                encoding="utf-8",
            )

            results = LocalSearchEngine(root).search(
                ["2025年度", "缴存基数", "缴存比例", "月缴存额", "上限", "下限", "通知"],
                top_k=1,
            )

        self.assertEqual(results[0].title, "关于2025年度上海市调整住房公积金缴存基数、比例以及月缴存额上下限的通知")
        self.assertIn("37302元", results[0].snippet)
        self.assertIn("5%~7%", results[0].snippet)
        self.assertIn("月缴存额", results[0].snippet)

    def test_front_matter_indexes_boost_relevant_active_agent_documents(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "官网" / "上海住房公积金网" / "政策解读" / "租赁提取问答.md"
            target.parent.mkdir(parents=True)
            target.write_text(
                "---\n"
                "title: \"关于优化本市住房公积金租赁提取业务问答\"\n"
                "doc_status: \"active\"\n"
                "service_items: [\"公积金提取\", \"租赁提取\"]\n"
                "agent_eligible: true\n"
                "---\n\n"
                "# 关于优化本市住房公积金租赁提取业务问答\n\n"
                "市场租赁住房每户家庭月提取限额为4000元。\n",
                encoding="utf-8",
            )

            noisy = root / "官网" / "上海住房公积金网" / "政策解读" / "基数调整温馨提示.md"
            noisy.write_text(
                "---\n"
                "title: \"2025年度住房公积金缴存基数调整温馨提示\"\n"
                "doc_status: \"active\"\n"
                "service_items: [\"缴存基数调整\"]\n"
                "agent_eligible: true\n"
                "---\n\n"
                "# 2025年度住房公积金缴存基数调整温馨提示\n\n"
                "公积金 住房公积金 上海 缴存 基数调整 公积金 住房公积金 上海 缴存。\n",
                encoding="utf-8",
            )

            ineligible = root / "官网" / "上海住房公积金网" / "政策解读" / "旧租赁提取问答.md"
            ineligible.write_text(
                "---\n"
                "title: \"旧租赁提取问答\"\n"
                "doc_status: \"superseded\"\n"
                "service_items: [\"租赁提取\"]\n"
                "agent_eligible: false\n"
                "---\n\n"
                "# 旧租赁提取问答\n\n"
                "租赁提取月提取限额为3000元。\n",
                encoding="utf-8",
            )

            results = LocalSearchEngine(root).search(
                ["上海", "公积金", "住房公积金", "租赁提取", "月提取限额"],
                top_k=5,
            )

        self.assertEqual(results[0].title, "关于优化本市住房公积金租赁提取业务问答")
        self.assertTrue(all(source.title != "旧租赁提取问答" for source in results))

    def test_requested_year_active_version_beats_older_repeated_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "官网" / "上海住房公积金网" / "政策文件" / "2025通知.md"
            current.parent.mkdir(parents=True)
            current.write_text(
                "---\n"
                "title: \"关于2025年度上海市调整住房公积金缴存基数、比例以及月缴存额上下限的通知\"\n"
                "version_group_id: 118\n"
                "version_no: 4\n"
                "doc_status: \"active\"\n"
                "service_items: [\"缴存基数调整\", \"缴存比例调整\", \"月缴存额\"]\n"
                "doc_kind: \"policy_notice\"\n"
                "agent_eligible: true\n"
                "---\n\n"
                "# 关于2025年度上海市调整住房公积金缴存基数、比例以及月缴存额上下限的通知\n\n"
                "单位和职工比例为各5%~7%。\n",
                encoding="utf-8",
            )
            old = root / "公众号" / "上海公积金公众号" / "2018比例问答.md"
            old.parent.mkdir(parents=True)
            old.write_text(
                "---\n"
                "title: \"《关于调整2018年度上海市住房公积金缴存比例的补充通知》的问答\"\n"
                "doc_status: \"active\"\n"
                "service_items: [\"缴存比例调整\"]\n"
                "agent_eligible: true\n"
                "---\n\n"
                "# 《关于调整2018年度上海市住房公积金缴存比例的补充通知》的问答\n\n"
                "住房公积金缴存比例 5% 7%。住房公积金缴存比例 5% 7%。"
                "住房公积金缴存比例 5% 7%。\n",
                encoding="utf-8",
            )

            results = LocalSearchEngine(root).search(
                ["2025年度", "上海", "住房公积金", "缴存比例", "5%~7%", "5%", "7%"],
                top_k=2,
            )

        self.assertEqual(results[0].title, "关于2025年度上海市调整住房公积金缴存基数、比例以及月缴存额上下限的通知")


if __name__ == "__main__":
    unittest.main()
