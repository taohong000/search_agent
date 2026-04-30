import tempfile
import unittest
import subprocess
import sys
from pathlib import Path

from scripts.build_version_indexes import (
    build_version_groups_query,
    build_version_index_markdown,
    resolve_version_index_path,
    write_version_indexes,
)


class BuildVersionIndexesTests(unittest.TestCase):
    def test_build_version_groups_query_filters_source_id(self):
        sql, params = build_version_groups_query(source_id=3, statuses=("auto_approved", "filter_disabled"))

        self.assertIn("d.source_id = %s", sql)
        self.assertIn("d.review_status IN (%s, %s)", sql)
        self.assertEqual(params, ["auto_approved", "filter_disabled", 3])

    def test_resolve_version_index_path_uses_local_index_directory(self):
        path = resolve_version_index_path(
            Path("D:/data"),
            {
                "group_name": "上海市住房公积金年度缴存基数调整",
                "output_path_parts_json": '["官网", "上海住房公积金网", "政策解读"]',
            },
        )

        self.assertEqual(path, Path("D:/data/官网/上海住房公积金网/政策解读/_indexes/version/上海市住房公积金年度缴存基数调整.md"))

    def test_build_version_index_markdown_marks_current_and_history(self):
        group = {
            "version_group_id": 10,
            "group_name": "上海市住房公积金年度缴存基数调整",
            "family_key": "上海市住房公积金年度缴存基数调整",
            "source_name": "上海住房公积金网",
            "source_type": "website",
            "channel_name": "政策解读",
            "output_path_parts_json": '["官网", "上海住房公积金网", "政策解读"]',
            "updated_at": "2026-04-30 11:00:00",
        }
        docs = [
            {
                "id": 1,
                "title": "2024年度基数调整问答",
                "version_no": 2024,
                "publish_date": "2024-06-30",
                "effective_date": "2024-07-01",
                "source_url": "https://example.test/2024",
                "review_status": "filter_disabled",
                "doc_status": "active",
            },
            {
                "id": 2,
                "title": "2025年度基数调整问答",
                "version_no": 2025,
                "publish_date": "2025-06-30",
                "effective_date": "2025-07-01",
                "source_url": "https://example.test/2025",
                "review_status": "filter_disabled",
                "doc_status": "active",
            },
        ]
        changes = [
            {
                "new_policy_id": 2,
                "old_policy_id": 1,
                "change_type": "replace",
                "change_summary": "2025版替代2024版",
            }
        ]

        markdown = build_version_index_markdown(group, docs, changes)

        self.assertIn('index_type: "version_index"', markdown)
        self.assertIn("version_group_id: 10", markdown)
        self.assertIn('current_policy_document_id: 2', markdown)
        self.assertIn("# 上海市住房公积金年度缴存基数调整", markdown)
        self.assertIn("| 2025 | 2 | 2025年度基数调整问答 | 2025-07-01 | https://example.test/2025 |", markdown)
        self.assertIn("| 版本 | 状态 | 文档ID | 标题 | 原文 | 替代关系 |", markdown)
        self.assertIn("| 2024 | superseded | 1 | 2024年度基数调整问答 | https://example.test/2024 | 2025版替代2024版 |", markdown)

    def test_write_version_indexes_dry_run_does_not_write_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            group = {
                "version_group_id": 10,
                "group_name": "社保退休办理",
                "family_key": "社保退休办理",
                "source_name": "上海社保",
                "source_type": "wechat_mp",
                "channel_name": "上海社保",
                "output_path_parts_json": '["公众号", "上海社保公众号"]',
                "updated_at": "2026-04-30 11:00:00",
            }
            docs = {
                10: [
                    {
                        "id": 1,
                        "title": "退休办理",
                        "version_no": 1,
                        "publish_date": "",
                        "effective_date": "",
                        "source_url": "https://example.test",
                        "review_status": "auto_approved",
                        "doc_status": "active",
                    },
                    {
                        "id": 2,
                        "title": "退休办理新版",
                        "version_no": 2,
                        "publish_date": "",
                        "effective_date": "",
                        "source_url": "https://example.test/2",
                        "review_status": "auto_approved",
                        "doc_status": "active",
                    }
                ]
            }

            stats = write_version_indexes(data_dir, [group], docs, {}, dry_run=True)

        self.assertEqual(stats.created, 1)
        self.assertFalse((data_dir / "_indexes").exists())

    def test_write_version_indexes_skips_groups_with_fewer_than_two_documents(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            group = {
                "version_group_id": 10,
                "group_name": "社保退休办理",
                "family_key": "社保退休办理",
                "source_name": "上海社保",
                "source_type": "wechat_mp",
                "channel_name": "上海社保",
                "output_path_parts_json": '["公众号", "上海社保公众号"]',
                "updated_at": "2026-04-30 11:00:00",
            }
            docs = {
                10: [
                    {
                        "id": 1,
                        "title": "退休办理",
                        "version_no": 1,
                        "publish_date": "",
                        "effective_date": "",
                        "source_url": "https://example.test",
                        "review_status": "auto_approved",
                        "doc_status": "active",
                    }
                ]
            }

            stats = write_version_indexes(data_dir, [group], docs, {}, dry_run=True)

        self.assertEqual(stats.created, 0)
        self.assertEqual(stats.skipped, 1)
        self.assertFalse((data_dir / "_indexes").exists())

    def test_script_help_runs_when_invoked_by_file_path(self):
        result = subprocess.run(
            [sys.executable, "scripts/build_version_indexes.py", "--help"],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--source-id", result.stdout)


if __name__ == "__main__":
    unittest.main()
