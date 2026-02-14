import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codex_search_stack.search.orchestrator import run_multi_source_search


def _settings():
    return types.SimpleNamespace(
        grok_api_url="https://grok.example/v1",
        grok_api_key="sk-grok",
        grok_model="grok-4.1-thinking",
        exa_api_key=None,
        tavily_api_key=None,
        tavily_api_url="https://api.tavily.com",
        github_token=None,
        key_pool_file=None,
        key_pool_enabled=False,
        confidence_profile="deep",
        mineru_token=None,
        mineru_token_file=None,
        mineru_api_base="https://mineru.net",
        mineru_wrapper_path=None,
        mineru_workspace=None,
        search_timeout_seconds=10,
        extract_timeout_seconds=10,
        policy={},
        decision_trace_enabled=True,
        decision_trace_persist=False,
        decision_trace_jsonl_path="./.runtime/decision-trace/decision_trace.jsonl",
    )


class SearchOrchestratorGrokRetryTests(unittest.TestCase):
    def test_grok_retries_twice_then_success(self) -> None:
        state = {"n": 0}

        def _fake_search_grok(*args, **kwargs):
            state["n"] += 1
            if state["n"] < 3:
                raise RuntimeError("temporary")
            return [{"title": "ok", "url": "https://example.com", "snippet": "x", "published_date": ""}]

        with patch("codex_search_stack.search.orchestrator.search_grok", side_effect=_fake_search_grok):
            out = run_multi_source_search(
                query="test",
                settings=_settings(),
                mode="deep",
                sources=["grok"],
                limit=3,
            )

        self.assertEqual(out.count, 1)
        self.assertTrue(any("grok_candidate_retrying" in note for note in out.notes))
        self.assertTrue(any("grok_candidate_recovered_after_retry" in note for note in out.notes))
        self.assertIn("grok_required_satisfied", out.notes)

    def test_grok_retry_exhausted_marks_unsatisfied(self) -> None:
        def _fake_search_grok(*args, **kwargs):
            raise RuntimeError("down")

        with patch("codex_search_stack.search.orchestrator.search_grok", side_effect=_fake_search_grok):
            out = run_multi_source_search(
                query="test",
                settings=_settings(),
                mode="deep",
                sources=["grok"],
                limit=3,
            )

        self.assertEqual(out.count, 0)
        self.assertTrue(any("attempt_3" in note for note in out.notes))
        self.assertIn("grok_required_unsatisfied_after_retries", out.notes)
        self.assertIn("grok_required_retry_attempts:3", out.notes)

    def test_grok_retry_attempts_is_configurable(self) -> None:
        def _fake_search_grok(*args, **kwargs):
            raise RuntimeError("down")

        settings = _settings()
        settings.policy = {"search": {"grok": {"retry_attempts": 2}}}
        with patch("codex_search_stack.search.orchestrator.search_grok", side_effect=_fake_search_grok):
            out = run_multi_source_search(
                query="test",
                settings=settings,
                mode="deep",
                sources=["grok"],
                limit=3,
            )

        self.assertEqual(out.count, 0)
        self.assertTrue(any("attempt_2" in note for note in out.notes))
        self.assertFalse(any("attempt_3" in note for note in out.notes))
        self.assertIn("grok_required_retry_attempts:2", out.notes)


if __name__ == "__main__":
    unittest.main()
