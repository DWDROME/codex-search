import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codex_search_stack.config import Settings
from codex_search_stack.contracts import ExtractionResponse, SearchResponse
from codex_search_stack.extract.pipeline import run_extract_pipeline
from codex_search_stack.observability import aggregate_decision_trace_jsonl
from codex_search_stack.search.orchestrator import run_multi_source_search


def _settings(trace_path: str) -> Settings:
    return Settings(
        grok_api_url="https://grok.example/v1",
        grok_api_key="sk-grok",
        grok_model="grok-4.1",
        exa_api_key="exa-key",
        tavily_api_key="tvly-key",
        tavily_api_url="https://api.tavily.com",
        github_token=None,
        key_pool_file=None,
        key_pool_enabled=False,
        confidence_profile="deep",
        mineru_token="mineru-token",
        mineru_token_file=None,
        mineru_api_base="https://mineru.net",
        mineru_wrapper_path="skills/mineru-extract/scripts/mineru_parse_documents.py",
        mineru_workspace="./.runtime/codex-workspace",
        search_timeout_seconds=10,
        extract_timeout_seconds=10,
        policy={},
        decision_trace_enabled=True,
        decision_trace_persist=True,
        decision_trace_jsonl_path=trace_path,
    )


class DecisionTraceIntegrationTests(unittest.TestCase):
    def test_search_persists_trace_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trace_path = str(Path(tmp) / "trace.jsonl")
            settings = _settings(trace_path)

            raw_rows = [
                {
                    "title": "A",
                    "url": "https://example.com/a",
                    "snippet": "demo",
                    "source": "grok,tavily",
                    "published_date": "",
                }
            ]
            with patch(
                "codex_search_stack.search.orchestrator._execute_single_query",
                return_value=(raw_rows, None, ["mocked"]),
            ):
                out = run_multi_source_search(query="demo", settings=settings, mode="deep")

            self.assertIsInstance(out, SearchResponse)
            agg = aggregate_decision_trace_jsonl(trace_path, limit=10)
            self.assertEqual(agg["records_used"], 1)
            self.assertEqual(agg["by_kind"]["search"]["total"], 1)
            self.assertEqual(agg["source_hits"]["grok"], 1)

    def test_extract_persists_trace_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trace_path = str(Path(tmp) / "trace.jsonl")
            settings = _settings(trace_path)
            mineru_ok = ExtractionResponse(
                ok=True,
                source_url="https://zhuanlan.zhihu.com/p/1",
                engine="mineru",
                markdown="x" * 800,
                notes=["fallback:mineru_parse_documents"],
                sources=["https://zhuanlan.zhihu.com/p/1"],
            )
            with patch("codex_search_stack.extract.pipeline.run_mineru_wrapper", return_value=mineru_ok):
                out = run_extract_pipeline(
                    url="https://zhuanlan.zhihu.com/p/1",
                    settings=settings,
                    strategy="auto",
                )

            self.assertIsInstance(out, ExtractionResponse)
            self.assertTrue(out.ok)
            agg = aggregate_decision_trace_jsonl(trace_path, limit=10)
            self.assertEqual(agg["records_used"], 1)
            self.assertEqual(agg["by_kind"]["extract"]["total"], 1)
            self.assertEqual(agg["source_hits"]["mineru"], 1)


if __name__ == "__main__":
    unittest.main()

