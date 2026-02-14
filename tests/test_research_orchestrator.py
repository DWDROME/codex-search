import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codex_search_stack.contracts import SearchResult
from codex_search_stack.research import run_research_loop


class ResearchOrchestratorTests(unittest.TestCase):
    def _settings(self):
        return types.SimpleNamespace(
            search_timeout_seconds=30,
            decision_trace_enabled=True,
            decision_trace_persist=False,
            decision_trace_jsonl_path="./.runtime/decision-trace/decision_trace.jsonl",
        )

    def test_research_loop_stops_when_no_gap(self) -> None:
        rows = [
            SearchResult(
                title="Official docs",
                url="https://developer.example.org/docs",
                snippet="updated 2026",
                source="grok",
                published_date="2026-02-10",
                score=0.9,
            ),
            SearchResult(
                title="Release notes",
                url="https://github.com/example/repo/releases",
                snippet="release",
                source="exa",
                published_date="2026-02-09",
                score=0.85,
            ),
            SearchResult(
                title="Changelog",
                url="https://github.com/example/repo/blob/main/CHANGELOG.md",
                snippet="changes",
                source="tavily",
                published_date="2026-02-08",
                score=0.8,
            ),
            SearchResult(
                title="Issue update",
                url="https://github.com/example/repo/issues/1",
                snippet="status",
                source="grok",
                published_date="2026-02-07",
                score=0.75,
            ),
            SearchResult(
                title="Docs blog",
                url="https://docs.example.org/blog/update",
                snippet="news",
                source="exa",
                published_date="2026-02-06",
                score=0.7,
            ),
        ]

        with patch("codex_search_stack.research.orchestrator.run_multi_source_search", return_value=types.SimpleNamespace(results=rows, notes=[])):
            payload = run_research_loop(
                query="example framework latest",
                settings=self._settings(),
                intent="status",
                freshness="pw",
                max_rounds=3,
                extract_per_round=0,
            )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["round_count"], 1)
        self.assertEqual(payload["stop_reason"], "no_more_gap")
        self.assertGreaterEqual(payload["count"], 1)

    def test_research_loop_runs_followup(self) -> None:
        call_idx = {"value": 0}

        def _fake_search(**kwargs):
            call_idx["value"] += 1
            if call_idx["value"] == 1:
                return types.SimpleNamespace(
                    results=[SearchResult(title="blog", url="https://example.com/post", snippet="old", source="exa", score=0.3)],
                    notes=[],
                )
            return types.SimpleNamespace(
                results=[
                    SearchResult(
                        title="repo",
                        url="https://github.com/example/repo",
                        snippet="official",
                        source="grok",
                        published_date="2026-02-10",
                        score=0.8,
                    )
                ],
                notes=[],
            )

        with patch("codex_search_stack.research.orchestrator.run_multi_source_search", side_effect=_fake_search):
            payload = run_research_loop(
                query="example repo",
                settings=self._settings(),
                intent="exploratory",
                max_rounds=2,
                extract_per_round=0,
            )

        self.assertEqual(payload["round_count"], 2)
        self.assertIn(payload["stop_reason"], {"no_more_gap", "max_rounds_reached"})
        self.assertTrue(any(item.get("followup_query") for item in payload["rounds"]))

    def test_research_loop_collects_extract(self) -> None:
        rows = [
            SearchResult(
                title="zhihu",
                url="https://zhuanlan.zhihu.com/p/1",
                snippet="post",
                source="tavily",
                score=0.5,
            )
        ]
        fake_extract = types.SimpleNamespace(ok=True, engine="mineru", notes=["ok"], markdown="content")
        with patch("codex_search_stack.research.orchestrator.run_multi_source_search", return_value=types.SimpleNamespace(results=rows, notes=[])), patch(
            "codex_search_stack.research.orchestrator.run_extract_pipeline", return_value=fake_extract
        ):
            payload = run_research_loop(
                query="zhihu post",
                settings=self._settings(),
                max_rounds=1,
                extract_per_round=1,
            )
        self.assertEqual(payload["round_count"], 1)
        self.assertTrue(payload["results"][0]["extract"].get("ok"))
        self.assertEqual(payload["results"][0]["extract"].get("engine"), "mineru")


if __name__ == "__main__":
    unittest.main()
