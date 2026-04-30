import unittest
from pathlib import Path

from scripts.version_index_paths import (
    build_version_index_relative_path,
    resolve_version_index_path,
)


class VersionIndexPathsTests(unittest.TestCase):
    def test_uses_output_path_parts_json_local_index_directory(self):
        group = {
            "group_name": "基数调整问答",
            "output_path_parts_json": '["官网", "上海住房公积金网", "政策解读"]',
        }

        self.assertEqual(
            resolve_version_index_path(Path("D:/data"), group),
            Path("D:/data/官网/上海住房公积金网/政策解读/_indexes/version/基数调整问答.md"),
        )

    def test_relative_path_points_from_document_to_index(self):
        doc_path = Path("D:/data/官网/上海住房公积金网/政策解读/2025年度基数调整问答.md")
        group = {
            "group_name": "基数调整问答",
            "output_path_parts_json": '["官网", "上海住房公积金网", "政策解读"]',
        }

        self.assertEqual(
            build_version_index_relative_path(Path("D:/data"), doc_path, group),
            "_indexes/version/基数调整问答.md",
        )


if __name__ == "__main__":
    unittest.main()
