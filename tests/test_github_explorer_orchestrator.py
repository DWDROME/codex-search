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
from codex_search_stack.github_explorer.orchestrator import (
    _collect_deepwiki,
    _collect_external,
    _collect_zread,
    _external_relevance_score,
)


class GithubExplorerExternalTests(unittest.TestCase):
    def test_external_relevance_prefers_target_repo(self) -> None:
        target = _external_relevance_score(
            owner="example-org",
            repo="example-repo",
            title="example-org/example-repo release notes",
            snippet="",
            url="https://github.com/example-org/example-repo/releases",
        )
        unrelated = _external_relevance_score(
            owner="example-org",
            repo="example-repo",
            title="openai/codex issue",
            snippet="",
            url="https://github.com/openai/codex/issues/1",
        )
        self.assertGreater(target, unrelated)

    def test_collect_external_prioritizes_repo_anchored_results(self) -> None:
        mock_rows = [
            SearchResult(
                title="openai/codex issue",
                url="https://github.com/openai/codex/issues/1",
                snippet="random",
                source="exa",
            ),
            SearchResult(
                title="example-org/example-repo overview",
                url="https://github.com/example-org/example-repo",
                snippet="repo homepage",
                source="tavily",
            ),
            SearchResult(
                title="example-org/example-repo 使用体验",
                url="https://example.com/example-repo-review",
                snippet="example-org/example-repo 实测",
                source="grok",
            ),
        ]

        def _fake_search(**kwargs):
            return types.SimpleNamespace(results=list(mock_rows), notes=["mock_search_called"])

        with patch("codex_search_stack.github_explorer.orchestrator.run_multi_source_search", side_effect=_fake_search), patch(
            "codex_search_stack.github_explorer.orchestrator._collect_deepwiki", return_value=(None, [])
        ), patch("codex_search_stack.github_explorer.orchestrator._collect_zread", return_value=(None, [])):
            external, notes, competitors, coverage = _collect_external(
                owner="example-org",
                repo="example-repo",
                settings=types.SimpleNamespace(),
                external_limit=2,
                extract_top=0,
                with_extract=False,
            )

        self.assertEqual(len(external), 2)
        urls = [item["url"] for item in external]
        self.assertIn("https://github.com/example-org/example-repo", urls)
        self.assertNotIn("https://github.com/openai/codex/issues/1", urls)
        self.assertTrue(any(note.startswith("external_relevance_selected:") for note in notes))
        self.assertIsInstance(competitors, list)
        self.assertIn("arxiv", coverage)

    def test_collect_external_prioritizes_deepwiki_when_available(self) -> None:
        mock_rows = [
            SearchResult(
                title="example-org/example-repo overview",
                url="https://github.com/example-org/example-repo",
                snippet="repo homepage",
                source="tavily",
            ),
            SearchResult(
                title="example-org/example-repo review",
                url="https://example.com/example-repo-review",
                snippet="example-org/example-repo 实测",
                source="grok",
            ),
        ]

        deepwiki_item = {
            "title": "example-repo wiki",
            "url": "https://deepwiki.com/example-org/example-repo",
            "snippet": "DeepWiki repository knowledge graph",
            "source": "deepwiki",
            "published_date": "",
        }

        def _fake_search(**kwargs):
            return types.SimpleNamespace(results=list(mock_rows), notes=["mock_search_called"])

        with patch("codex_search_stack.github_explorer.orchestrator.run_multi_source_search", side_effect=_fake_search), patch(
            "codex_search_stack.github_explorer.orchestrator._collect_deepwiki", return_value=(deepwiki_item, [])
        ), patch("codex_search_stack.github_explorer.orchestrator._collect_zread", return_value=(None, [])):
            external, notes, competitors, coverage = _collect_external(
                owner="example-org",
                repo="example-repo",
                settings=types.SimpleNamespace(),
                external_limit=2,
                extract_top=0,
                with_extract=False,
            )

        self.assertEqual(len(external), 2)
        self.assertEqual(external[0]["source"], "deepwiki")
        self.assertEqual(external[0]["url"], "https://deepwiki.com/example-org/example-repo")
        self.assertIn("external_deepwiki_prioritized", notes)
        self.assertEqual(coverage.get("deepwiki", {}).get("status"), "found")
        self.assertIsInstance(competitors, list)

    def test_collect_external_extracts_competitor_repo(self) -> None:
        mock_rows = [
            SearchResult(
                title="example-org/example-repo alternatives vs sourcegraph",
                url="https://github.com/sourcegraph/sourcegraph",
                snippet="compare example-org/example-repo with sourcegraph",
                source="grok",
            ),
            SearchResult(
                title="example-org/example-repo",
                url="https://github.com/example-org/example-repo",
                snippet="repo homepage",
                source="grok",
            ),
        ]

        def _fake_search(**kwargs):
            return types.SimpleNamespace(results=list(mock_rows), notes=[])

        with patch("codex_search_stack.github_explorer.orchestrator.run_multi_source_search", side_effect=_fake_search), patch(
            "codex_search_stack.github_explorer.orchestrator._collect_deepwiki", return_value=(None, [])
        ), patch("codex_search_stack.github_explorer.orchestrator._collect_zread", return_value=(None, [])):
            _, _, competitors, _ = _collect_external(
                owner="example-org",
                repo="example-repo",
                settings=types.SimpleNamespace(),
                external_limit=3,
                extract_top=0,
                with_extract=False,
            )
        repos = [item.get("repo") for item in competitors]
        self.assertIn("sourcegraph/sourcegraph", repos)

    def test_collect_external_injects_repo_seed_when_sources_unstable(self) -> None:
        def _fake_search(**kwargs):
            source_list = kwargs.get("sources") or []
            if source_list == ["tavily"]:
                return types.SimpleNamespace(results=[], notes=["tavily_candidate_failed:mock"])
            return types.SimpleNamespace(results=[], notes=["grok_candidate_failed:mock", "exa_failed:mock"])

        with patch("codex_search_stack.github_explorer.orchestrator.run_multi_source_search", side_effect=_fake_search), patch(
            "codex_search_stack.github_explorer.orchestrator._collect_deepwiki", return_value=(None, [])
        ), patch("codex_search_stack.github_explorer.orchestrator._collect_zread", return_value=(None, [])):
            external, notes, _, _ = _collect_external(
                owner="example-org",
                repo="example-repo",
                settings=types.SimpleNamespace(search_timeout_seconds=30),
                external_limit=4,
                extract_top=0,
                with_extract=False,
            )

        self.assertTrue(any(item.get("source") == "repo_seed" for item in external))
        self.assertTrue(
            any(note.startswith("external_failure_seed_injected:") for note in notes)
            or ("external_relevance_seeded_from_repo" in notes)
        )

    def test_collect_deepwiki_returns_unavailable_note_on_http_error(self) -> None:
        fake_response = types.SimpleNamespace(status_code=404, text="not found", url="https://deepwiki.com/example-org/example-repo")
        with patch("codex_search_stack.github_explorer.orchestrator.requests.get", return_value=fake_response):
            item, notes = _collect_deepwiki("example-org", "example-repo", settings=types.SimpleNamespace(search_timeout_seconds=10))
        self.assertIsNone(item)
        self.assertIn("deepwiki_unavailable:not_indexed", notes)

    def test_collect_zread_returns_unavailable_note_on_http_error(self) -> None:
        fake_response = types.SimpleNamespace(status_code=404, text="not found", url="https://zread.ai/example-org/example-repo")
        with patch("codex_search_stack.github_explorer.orchestrator.requests.get", return_value=fake_response):
            item, notes = _collect_zread("example-org", "example-repo", settings=types.SimpleNamespace(search_timeout_seconds=10))
        self.assertIsNone(item)
        self.assertIn("zread_unavailable:not_indexed", notes)

    def test_collect_external_runs_followup_for_missing_index_and_paper(self) -> None:
        calls = []

        def _fake_search(**kwargs):
            calls.append(kwargs.get("query", ""))
            query = kwargs.get("query", "")
            if "site:zread.ai" in query:
                return types.SimpleNamespace(
                    results=[
                        SearchResult(
                            title="example-org/example-repo | zread",
                            url="https://zread.ai/example-org/example-repo",
                            snippet="repo index",
                            source="exa",
                        )
                    ],
                    notes=[],
                )
            if "site:arxiv.org" in query:
                return types.SimpleNamespace(
                    results=[
                        SearchResult(
                            title="Example Repo Paper",
                            url="https://arxiv.org/abs/2501.00001",
                            snippet="paper",
                            source="grok",
                        )
                    ],
                    notes=[],
                )
            return types.SimpleNamespace(results=[], notes=[])

        with patch("codex_search_stack.github_explorer.orchestrator.run_multi_source_search", side_effect=_fake_search), patch(
            "codex_search_stack.github_explorer.orchestrator._collect_deepwiki", return_value=(None, [])
        ), patch("codex_search_stack.github_explorer.orchestrator._collect_zread", return_value=(None, [])):
            external, notes, _, coverage = _collect_external(
                owner="example-org",
                repo="example-repo",
                settings=types.SimpleNamespace(search_timeout_seconds=30),
                external_limit=4,
                extract_top=0,
                with_extract=False,
            )

        self.assertTrue(any("external_followup_queries:" in note for note in notes))
        self.assertTrue(any("external_followup_used:index_followup" in note for note in notes))
        self.assertTrue(any("external_followup_used:paper_followup" in note for note in notes))
        self.assertTrue(any("zread.ai/example-org/example-repo" in (item.get("url") or "") for item in external))
        self.assertEqual(coverage.get("zread", {}).get("status"), "found")
        self.assertGreaterEqual(len(calls), 2)

    def test_collect_external_uses_policy_external_source_mix(self) -> None:
        calls = []

        def _fake_search(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return types.SimpleNamespace(results=[], notes=[])
            return types.SimpleNamespace(
                results=[
                    SearchResult(
                        title="example-org/example-repo overview",
                        url="https://github.com/example-org/example-repo",
                        snippet="repo",
                        source="exa",
                    )
                ],
                notes=[],
            )

        policy = {
            "explore": {
                "external": {
                    "model_profile": "balanced",
                    "timeout_seconds": 11,
                    "primary_sources": ["grok"],
                    "fallback_source": "exa",
                    "followup_rounds": 0,
                }
            }
        }

        with patch("codex_search_stack.github_explorer.orchestrator.run_multi_source_search", side_effect=_fake_search), patch(
            "codex_search_stack.github_explorer.orchestrator._collect_deepwiki", return_value=(None, [])
        ), patch("codex_search_stack.github_explorer.orchestrator._collect_zread", return_value=(None, [])), patch(
            "codex_search_stack.github_explorer.orchestrator._build_external_queries",
            return_value=[
                {
                    "query": '"example-org/example-repo" release',
                    "intent": "resource",
                    "tag": "repo",
                    "boost_domains": ["github.com"],
                }
            ],
        ), patch("codex_search_stack.github_explorer.orchestrator._build_followup_queries", return_value=[]):
            _collect_external(
                owner="example-org",
                repo="example-repo",
                settings=types.SimpleNamespace(search_timeout_seconds=30, policy=policy),
                external_limit=3,
                extract_top=0,
                with_extract=False,
            )

        self.assertGreaterEqual(len(calls), 2)
        self.assertEqual(calls[0].get("sources"), ["grok"])
        self.assertEqual(calls[1].get("sources"), ["exa"])
        self.assertEqual(calls[0].get("model_profile"), "balanced")
        self.assertEqual(int(calls[0].get("budget_max_latency_ms", 0)), 11000)

    def test_collect_external_honors_followup_rounds_policy(self) -> None:
        calls = []

        def _fake_search(**kwargs):
            query = kwargs.get("query", "")
            calls.append(query)
            return types.SimpleNamespace(
                results=[
                    SearchResult(
                        title="row for %s" % query,
                        url="https://example.com/%s" % query.replace(" ", "-"),
                        snippet="snippet",
                        source="grok",
                    )
                ],
                notes=[],
            )

        followup_queue = [
            [{"query": "followup round 1", "intent": "resource", "tag": "f1", "boost_domains": []}],
            [{"query": "followup round 2", "intent": "resource", "tag": "f2", "boost_domains": []}],
            [],
        ]

        policy = {"explore": {"external": {"followup_rounds": 2, "primary_sources": ["grok"], "fallback_source": "tavily"}}}
        with patch("codex_search_stack.github_explorer.orchestrator.run_multi_source_search", side_effect=_fake_search), patch(
            "codex_search_stack.github_explorer.orchestrator._collect_deepwiki", return_value=(None, [])
        ), patch("codex_search_stack.github_explorer.orchestrator._collect_zread", return_value=(None, [])), patch(
            "codex_search_stack.github_explorer.orchestrator._build_external_queries",
            return_value=[],
        ), patch(
            "codex_search_stack.github_explorer.orchestrator._build_followup_queries",
            side_effect=followup_queue,
        ):
            _, notes, _, _ = _collect_external(
                owner="example-org",
                repo="example-repo",
                settings=types.SimpleNamespace(search_timeout_seconds=30, policy=policy),
                external_limit=4,
                extract_top=0,
                with_extract=False,
            )

        self.assertIn("followup round 1", calls)
        self.assertIn("followup round 2", calls)
        self.assertTrue(any("external_followup_round:1:queries:1" == note for note in notes))
        self.assertTrue(any("external_followup_round:2:queries:1" == note for note in notes))


if __name__ == "__main__":
    unittest.main()
