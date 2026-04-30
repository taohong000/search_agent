import tempfile
import unittest
from pathlib import Path

from scripts.add_local_indexes import (
    add_local_indexes_to_text,
    infer_local_indexes,
    update_markdown_file,
)


class AddLocalIndexesTests(unittest.TestCase):
    def test_infers_social_security_guide_indexes_from_path_and_title(self):
        path = Path("公众号") / "上海社保公众号" / "灵活就业人员退休一件事操作指南.md"

        indexes = infer_local_indexes(path, "灵活就业人员退休一件事操作指南", "退休办理流程")

        self.assertEqual(indexes["primary_business_line"], "社保")
        self.assertEqual(indexes["business_lines"], ["社保"])
        self.assertIn("退休办理", indexes["service_items"])
        self.assertIn("灵活就业参保", indexes["service_items"])
        self.assertEqual(indexes["doc_kind"], "guide")
        self.assertTrue(indexes["agent_eligible"])

    def test_infers_housing_fund_faq_indexes(self):
        path = Path("官网") / "上海住房公积金网" / "政策解读" / "2025年度基数调整问答.md"

        indexes = infer_local_indexes(path, "2025年度基数调整问答", "缴存基数上限和缴存比例")

        self.assertEqual(indexes["primary_business_line"], "公积金")
        self.assertEqual(indexes["business_lines"], ["公积金"])
        self.assertIn("缴存基数调整", indexes["service_items"])
        self.assertIn("缴存比例调整", indexes["service_items"])
        self.assertEqual(indexes["doc_kind"], "faq")

    def test_marks_reposted_articles_as_not_agent_eligible(self):
        indexes = infer_local_indexes(
            Path("公众号") / "上海社保公众号" / "【转发】关于工伤待遇的问题.md",
            "【转发】关于工伤待遇的问题",
            "工伤待遇说明",
        )

        self.assertFalse(indexes["agent_eligible"])

    def test_adds_missing_local_index_fields_to_existing_front_matter(self):
        text = (
            "---\n"
            "policy_document_id: 1\n"
            "title: \"灵活就业人员退休一件事操作指南\"\n"
            "---\n\n"
            "# 灵活就业人员退休一件事操作指南\n\n正文"
        )

        updated, changed = add_local_indexes_to_text(
            text,
            Path("公众号") / "上海社保公众号" / "灵活就业人员退休一件事操作指南.md",
        )

        self.assertTrue(changed)
        self.assertIn('primary_business_line: "社保"', updated)
        self.assertIn('business_lines: ["社保"]', updated)
        self.assertIn('service_items: ["退休办理", "灵活就业参保"]', updated)
        self.assertIn('doc_kind: "guide"', updated)
        self.assertIn("agent_eligible: true", updated)
        self.assertIn("# 灵活就业人员退休一件事操作指南", updated)

    def test_preserves_existing_manual_index_fields(self):
        text = (
            "---\n"
            "policy_document_id: 1\n"
            "primary_business_line: \"人工分类\"\n"
            "service_items: [\"人工事项\"]\n"
            "---\n\n"
            "正文"
        )

        updated, changed = add_local_indexes_to_text(text, Path("公众号") / "上海社保公众号" / "退休.md")

        self.assertTrue(changed)
        self.assertIn('primary_business_line: "人工分类"', updated)
        self.assertIn('service_items: ["人工事项"]', updated)
        self.assertIn('business_lines: ["社保"]', updated)
        self.assertNotIn('primary_business_line: "社保"', updated)

    def test_update_markdown_file_supports_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "公众号" / "上海社保公众号" / "退休指南.md"
            path.parent.mkdir(parents=True)
            path.write_text("---\ntitle: \"退休指南\"\n---\n\n正文", encoding="utf-8")

            status = update_markdown_file(path, dry_run=True)
            content = path.read_text(encoding="utf-8")

        self.assertEqual(status, "updated")
        self.assertNotIn("primary_business_line", content)


if __name__ == "__main__":
    unittest.main()
