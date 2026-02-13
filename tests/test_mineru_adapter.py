import json
import tempfile
import unittest
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codex_search_stack.extract.mineru_adapter import _default_mineru_wrapper, run_mineru_wrapper


class MineruAdapterTests(unittest.TestCase):
    def test_default_wrapper_path_points_to_skills(self) -> None:
        project_root = Path("/tmp/codex-search")
        target = _default_mineru_wrapper(project_root)
        self.assertEqual(
            target,
            project_root / "skills" / "mineru-extract" / "scripts" / "mineru_parse_documents.py",
        )

    def test_missing_wrapper_returns_error_response(self) -> None:
        out = run_mineru_wrapper(
            url="https://example.com/a",
            wrapper_path="/tmp/__not_exists__/mineru_parse_documents.py",
            token=None,
            api_base=None,
            workspace=None,
        )
        self.assertFalse(out.ok)
        self.assertEqual(out.engine, "mineru")
        self.assertTrue(any(note.startswith("mineru_wrapper_not_found:") for note in out.notes))

    def test_workspace_env_is_injected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wrapper = Path(tmp) / "mineru_parse_documents.py"
            wrapper.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
            captured = {}

            def fake_run(cmd, capture_output, text, env):
                captured["cmd"] = cmd
                captured["env"] = env
                payload = {
                    "items": [
                        {
                            "markdown": "ok",
                            "full_zip_url": "https://example.com/full.zip",
                            "markdown_path": "/tmp/parsed.md",
                            "out_dir": "/tmp/out",
                            "zip_path": "/tmp/out.zip",
                            "task_id": "task-1",
                            "cache_key": "cache-1",
                        }
                    ]
                }
                return SimpleNamespace(returncode=0, stdout=json.dumps(payload))

            with patch("codex_search_stack.extract.mineru_adapter.subprocess.run", side_effect=fake_run):
                out = run_mineru_wrapper(
                    url="https://example.com/a",
                    wrapper_path=str(wrapper),
                    token="token-1",
                    api_base="https://mineru.net",
                    workspace="/tmp/codex-workspace",
                )

        self.assertTrue(out.ok)
        self.assertEqual(out.engine, "mineru")
        self.assertIn("https://example.com/full.zip", out.sources)
        self.assertIn("/tmp/parsed.md", out.sources)
        self.assertEqual(captured["env"]["CODEX_WORKSPACE"], "/tmp/codex-workspace")
        self.assertEqual(captured["env"]["MINERU_WORKSPACE"], "/tmp/codex-workspace")


if __name__ == "__main__":
    unittest.main()
