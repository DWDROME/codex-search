import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "skills/git-workflow/scripts/git_guardrails.py"


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(SCRIPT_PATH), "--repo", str(repo), *args]
    return subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True, text=True)


class GitWorkflowGuardrailsTests(unittest.TestCase):
    def test_detects_bearer_token_in_staged_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _git(repo, "init")
            target = repo / "app.py"
            target.write_text("headers = {\"Authorization\": \"Bearer abcdefghijklmnopqrstuvwxy\"}\n", encoding="utf-8")
            _git(repo, "add", "app.py")

            proc = _run(repo, "--scope", "staged")
            self.assertEqual(proc.returncode, 2)
            payload = json.loads(proc.stdout)
            self.assertGreater(payload.get("findings_count", 0), 0)
            rules = {item.get("rule") for item in payload.get("findings", [])}
            self.assertIn("bearer_token", rules)

    def test_detects_remote_embedded_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _git(repo, "init")
            _git(repo, "remote", "add", "origin", "https://user:token1234567890@github.com/example/repo.git")

            proc = _run(repo, "--scope", "staged")
            self.assertEqual(proc.returncode, 2)
            payload = json.loads(proc.stdout)
            rules = {item.get("rule") for item in payload.get("findings", [])}
            self.assertIn("remote_embedded_credentials", rules)

    def test_allow_findings_mode_keeps_exit_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _git(repo, "init")
            target = repo / "a.txt"
            target.write_text("/home/dw/secret/path\n", encoding="utf-8")
            _git(repo, "add", "a.txt")

            proc = _run(repo, "--scope", "staged", "--allow-findings")
            self.assertEqual(proc.returncode, 0)
            payload = json.loads(proc.stdout)
            self.assertGreater(payload.get("findings_count", 0), 0)


if __name__ == "__main__":
    unittest.main()
