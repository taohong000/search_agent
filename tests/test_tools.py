import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from search_agent.tools import SearchToolRunner


class SearchToolRunnerTests(unittest.TestCase):
    def test_rg_search_finds_content_and_limits_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index in range(3):
                (root / f"doc{index}.md").write_text(f"# 文档{index}\n\n灵活就业参保政策。\n", encoding="utf-8")
            runner = SearchToolRunner(root)

            result = runner.rg_search("灵活就业", max_results=2)

        self.assertTrue(result["ok"])
        self.assertEqual(len(result["results"]), 2)
        self.assertEqual(len(runner.state.search_rounds), 1)

    def test_rg_search_uses_python_fallback_when_rg_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "社保.md").write_text("# 社保\n\n失业后可以办理灵活就业参保。\n", encoding="utf-8")
            runner = SearchToolRunner(root)

            with patch("search_agent.tools.shutil.which", return_value=None):
                result = runner.rg_search("灵活就业")

        self.assertTrue(result["ok"])
        self.assertEqual(result["results"][0]["title"], "社保")

    def test_fuzzy_file_search_sorts_by_score_then_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "b-公积金.md").write_text("# B\n", encoding="utf-8")
            (root / "a-公积金.md").write_text("# A\n", encoding="utf-8")
            runner = SearchToolRunner(root)

            result = runner.fuzzy_file_search("公积金", limit=2)

        self.assertTrue(result["ok"])
        self.assertEqual([item["path"] for item in result["results"]], ["a-公积金.md", "b-公积金.md"])

    def test_read_local_file_returns_line_numbers_and_rejects_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "政策.md").write_text("# 政策\n\n第一行\n第二行\n第三行\n", encoding="utf-8")
            outside = root.parent / "outside.md"
            outside.write_text("# 外部\n", encoding="utf-8")
            runner = SearchToolRunner(root)

            result = runner.read_local_file("政策.md", start_line=3, max_lines=2)
            escaped = runner.read_local_file(str(outside))

        self.assertTrue(result["ok"])
        self.assertIn("3: 第一行", result["content"])
        self.assertIn("4: 第二行", result["content"])
        self.assertFalse(escaped["ok"])


if __name__ == "__main__":
    unittest.main()
