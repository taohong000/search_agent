import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from scripts.sync_reviewed_markdown import (
    DEFAULT_STATUSES,
    SyncStats,
    build_front_matter,
    build_reviewed_rows_query,
    load_mysql_settings,
    map_markdown_target_path,
    plan_markdown_write,
    strip_front_matter,
)


class SyncReviewedMarkdownTests(unittest.TestCase):
    def test_load_mysql_settings_reads_sicrawl_env_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env.qa"
            env_file.write_text(
                "\n".join(
                    [
                        "SOCIAL_INSURANCE_MYSQL_HOST=127.0.0.1",
                        "SOCIAL_INSURANCE_MYSQL_PORT=3307",
                        "SOCIAL_INSURANCE_MYSQL_USER=root",
                        "SOCIAL_INSURANCE_MYSQL_PASSWORD=secret",
                        "SOCIAL_INSURANCE_MYSQL_DATABASE=social_insurance_ai",
                    ]
                ),
                encoding="utf-8",
            )

            settings = load_mysql_settings(env_file)

        self.assertEqual(settings.host, "127.0.0.1")
        self.assertEqual(settings.port, 3307)
        self.assertEqual(settings.user, "root")
        self.assertEqual(settings.password, "secret")
        self.assertEqual(settings.database, "social_insurance_ai")

    def test_load_mysql_settings_does_not_override_file_with_process_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env.qa"
            env_file.write_text(
                "\n".join(
                    [
                        "SOCIAL_INSURANCE_MYSQL_HOST=file-host",
                        "SOCIAL_INSURANCE_MYSQL_PORT=3306",
                        "SOCIAL_INSURANCE_MYSQL_USER=file-user",
                        "SOCIAL_INSURANCE_MYSQL_PASSWORD=file-password",
                        "SOCIAL_INSURANCE_MYSQL_DATABASE=file-db",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(
                "os.environ",
                {
                    "SOCIAL_INSURANCE_MYSQL_HOST": "env-host",
                    "SOCIAL_INSURANCE_MYSQL_USER": "env-user",
                    "SOCIAL_INSURANCE_MYSQL_PASSWORD": "env-password",
                    "SOCIAL_INSURANCE_MYSQL_DATABASE": "env-db",
                },
            ):
                settings = load_mysql_settings(env_file)

        self.assertEqual(settings.host, "file-host")
        self.assertEqual(settings.user, "file-user")
        self.assertEqual(settings.password, "file-password")
        self.assertEqual(settings.database, "file-db")

    def test_default_statuses_include_approved_and_filter_disabled_only(self):
        self.assertEqual(DEFAULT_STATUSES, ("auto_approved", "manual_approved", "filter_disabled"))

    def test_map_markdown_target_path_uses_crawler_markdown_layout(self):
        crawler_output_dir = Path("crawler-root/output").resolve()
        data_dir = Path("local-data").resolve()
        target = map_markdown_target_path(
            normalized_text_path=str(crawler_output_dir / "markdown" / "官网" / "上海住房公积金网" / "政策解读" / "a.md"),
            crawler_output_dir=crawler_output_dir,
            data_dir=data_dir,
            source_type="website",
            source_name="上海住房公积金网",
            title="2025年度基数调整问答",
        )

        self.assertEqual(target, data_dir / "官网" / "上海住房公积金网" / "政策解读" / "2025年度基数调整问答.md")

    def test_map_markdown_target_path_supports_relative_output_path(self):
        crawler_output_dir = Path("crawler-root/output").resolve()
        data_dir = Path("local-data").resolve()
        target = map_markdown_target_path(
            normalized_text_path=str(Path("output") / "markdown" / "公众号" / "上海社保公众号" / "a.md"),
            crawler_output_dir=crawler_output_dir,
            data_dir=data_dir,
            source_type="wechat_mp",
            source_name="上海社保",
            title="灵活就业参保指南",
        )

        self.assertEqual(target, data_dir / "公众号" / "上海社保公众号" / "灵活就业参保指南.md")

    def test_map_markdown_target_path_appends_version_when_requested(self):
        crawler_output_dir = Path("crawler-root/output").resolve()
        data_dir = Path("local-data").resolve()
        target = map_markdown_target_path(
            normalized_text_path=str(Path("output") / "markdown" / "官网" / "上海住房公积金网" / "政策解读" / "source.md"),
            crawler_output_dir=crawler_output_dir,
            data_dir=data_dir,
            source_type="website",
            source_name="上海住房公积金网",
            title="2025年度基数调整问答",
            version_no=4,
            append_version=True,
        )

        self.assertEqual(target, data_dir / "官网" / "上海住房公积金网" / "政策解读" / "2025年度基数调整问答_v4.md")

    def test_map_markdown_target_path_falls_back_to_source_and_title(self):
        data_dir = Path("local-data").resolve()
        target = map_markdown_target_path(
            normalized_text_path="",
            crawler_output_dir=Path("crawler-root/output").resolve(),
            data_dir=data_dir,
            source_type="wechat_mp",
            source_name="上海社保公众号",
            title='退休怎么办理？蓝娃给您讲清楚！',
        )

        self.assertEqual(target, data_dir / "wechat_mp" / "上海社保公众号" / "退休怎么办理？蓝娃给您讲清楚！.md")

    def test_strip_front_matter_only_removes_leading_metadata_block(self):
        text = "---\ntitle: old\n---\n# 标题\n\n正文\n\n---\n\n正文分隔线"

        body = strip_front_matter(text)

        self.assertEqual(body, "# 标题\n\n正文\n\n---\n\n正文分隔线")

    def test_build_front_matter_quotes_strings_and_keeps_required_fields(self):
        row = {
            "id": 123,
            "version_group_id": 88,
            "version_index_path": "../../../_indexes/version/官网/上海住房公积金网/政策解读/基数调整问答.md",
            "source_url": "https://example.test/a?x=1",
            "source_name": "上海住房公积金网",
            "source_type": "website",
            "city_code": "SH",
            "title": "标题: 含冒号",
            "publish_date": "2025-06-25",
            "effective_date": None,
            "review_status": "filter_disabled",
            "normalized_text_path": r"D:\code\sicrawl\output\markdown\a.md",
            "content_hash": "abc",
            "version_no": 1,
            "doc_status": "active",
            "updated_at": "2026-04-30 10:00:00",
        }

        front_matter = build_front_matter(row)

        self.assertIn("policy_document_id: 123", front_matter)
        self.assertIn("version_group_id: 88", front_matter)
        self.assertIn('version_index_path: "../../../_indexes/version/官网/上海住房公积金网/政策解读/基数调整问答.md"', front_matter)
        self.assertIn('title: "标题: 含冒号"', front_matter)
        self.assertIn('effective_date: ""', front_matter)
        self.assertIn('review_status: "filter_disabled"', front_matter)
        self.assertNotIn("normalized_text_path", front_matter)

    def test_plan_markdown_write_adds_front_matter_for_new_file(self):
        row = {
            "id": 1,
            "source_url": "https://example.test",
            "source_name": "来源",
            "source_type": "website",
            "city_code": "SH",
            "title": "标题",
            "publish_date": "",
            "effective_date": "",
            "review_status": "auto_approved",
            "normalized_text_path": "",
            "content_hash": "hash",
            "version_no": 1,
            "doc_status": "active",
            "updated_at": "",
            "markdown_content": "# 标题\n\n正文",
        }
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "doc.md"

            action = plan_markdown_write(row, target)

        self.assertEqual(action.status, "created")
        self.assertIn("---\npolicy_document_id: 1", action.content)
        self.assertTrue(action.content.endswith("# 标题\n\n正文\n"))

    def test_plan_markdown_write_skips_when_body_and_front_matter_match(self):
        row = {
            "id": 1,
            "source_url": "https://example.test",
            "source_name": "来源",
            "source_type": "website",
            "city_code": "SH",
            "title": "标题",
            "publish_date": "",
            "effective_date": "",
            "review_status": "auto_approved",
            "normalized_text_path": "",
            "content_hash": "hash",
            "version_no": 1,
            "doc_status": "active",
            "updated_at": "",
            "markdown_content": "# 标题\n\n正文",
        }
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "doc.md"
            first = plan_markdown_write(row, target)
            target.write_text(first.content, encoding="utf-8", newline="\n")

            second = plan_markdown_write(row, target)

        self.assertEqual(second.status, "skipped")
        self.assertEqual(second.content, first.content)

    def test_sync_stats_counts_statuses(self):
        stats = SyncStats()
        stats.record("created", Path("a.md"))
        stats.record("updated", Path("b.md"))
        stats.record("skipped", Path("c.md"))

        self.assertEqual(stats.created, 1)
        self.assertEqual(stats.updated, 1)
        self.assertEqual(stats.skipped, 1)

    def test_build_reviewed_rows_query_filters_source_id(self):
        sql, params = build_reviewed_rows_query(
            statuses=("auto_approved", "filter_disabled"),
            limit=10,
            since_updated_at=None,
            source_id=3,
        )

        self.assertIn("d.source_id = %s", sql)
        self.assertEqual(params, ["auto_approved", "filter_disabled", "auto_approved", "filter_disabled", 3, 10])


if __name__ == "__main__":
    unittest.main()
