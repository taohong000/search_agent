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


if __name__ == "__main__":
    unittest.main()
