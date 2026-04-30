import unittest
from pathlib import Path


class SyncAllScriptTests(unittest.TestCase):
    def test_sync_all_script_exists_and_orchestrates_steps(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "sync_all.ps1"

        self.assertTrue(script.exists())
        content = script.read_text(encoding="utf-8")
        self.assertIn("sync_reviewed_markdown.ps1", content)
        self.assertIn("add_local_indexes.ps1", content)
        self.assertIn("build_version_indexes.ps1", content)
        self.assertLess(content.index("sync_reviewed_markdown.ps1"), content.index("add_local_indexes.ps1"))
        self.assertLess(content.index("add_local_indexes.ps1"), content.index("build_version_indexes.ps1"))

    def test_sync_all_script_exposes_shared_parameters(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "sync_all.ps1"

        content = script.read_text(encoding="utf-8")
        for parameter in ("$EnvFile", "$DataDir", "$SourceId", "$Statuses", "$DryRun"):
            self.assertIn(parameter, content)


if __name__ == "__main__":
    unittest.main()
