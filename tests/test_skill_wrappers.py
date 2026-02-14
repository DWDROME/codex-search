import os
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SkillWrapperValidationTests(unittest.TestCase):
    def _run(self, rel_path, args, extra_env=None):
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        cmd = [sys.executable, str(PROJECT_ROOT / rel_path), *args]
        return subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env, capture_output=True, text=True)

    def test_search_requires_freshness_for_status(self):
        proc = self._run(
            "skills/search-layer/scripts/search.py",
            ["AI latest progress", "--intent", "status", "--mode", "deep"],
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("requires --freshness", proc.stderr)

    def test_search_requires_multi_queries_for_comparison(self):
        proc = self._run(
            "skills/search-layer/scripts/search.py",
            ["A vs B", "--intent", "comparison", "--mode", "deep"],
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("comparison intent requires --queries", proc.stderr)

    def test_research_requires_freshness_for_status(self):
        proc = self._run(
            "skills/search-layer/scripts/research.py",
            ["AI latest progress", "--intent", "status", "--mode", "deep"],
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("requires --freshness", proc.stderr)

    def test_content_extract_requires_valid_url(self):
        proc = self._run(
            "skills/content-extract/scripts/content_extract.py",
            ["--url", "not-a-url"],
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("must be a valid http(s) URL", proc.stderr)

    def test_github_explorer_validates_issue_range(self):
        proc = self._run(
            "skills/github-explorer/scripts/explore.py",
            ["openai/codex", "--issues", "1"],
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--issues must be between 3 and 20", proc.stderr)

    def test_mineru_rejects_page_ranges_with_html_model(self):
        proc = self._run(
            "skills/mineru-extract/scripts/mineru_parse_documents.py",
            [
                "--file-sources",
                "https://example.com",
                "--model-version",
                "MinerU-HTML",
                "--page-ranges",
                "1-2",
            ],
            extra_env={"MINERU_TOKEN": "dummy"},
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("page-ranges", proc.stdout)


if __name__ == "__main__":
    unittest.main()
