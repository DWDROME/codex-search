import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codex_search_stack.contracts import DecisionTrace, SearchResult
from codex_search_stack.observability import (
    aggregate_decision_trace_jsonl,
    collect_extract_source_hits,
    collect_search_source_hits,
    persist_decision_trace_jsonl,
)


class DecisionTraceStoreTests(unittest.TestCase):
    def test_collect_source_hits(self) -> None:
        rows = [
            SearchResult(title="a", url="https://a", source="grok,tavily"),
            SearchResult(title="b", url="https://b", source="grok"),
            SearchResult(title="c", url="https://c", source="exa,tavily"),
        ]
        hits = collect_search_source_hits(rows)
        self.assertEqual(hits["grok"], 2)
        self.assertEqual(hits["tavily"], 2)
        self.assertEqual(hits["exa"], 1)

        self.assertEqual(collect_extract_source_hits("tavily_extract"), {"tavily": 1})
        self.assertEqual(collect_extract_source_hits("mineru"), {"mineru": 1})

    def test_persist_and_aggregate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "decision_trace.jsonl"

            t1 = DecisionTrace(request_id="req-search")
            t1.add_event("search.request", "request_received")
            err = persist_decision_trace_jsonl(
                trace=t1,
                trace_kind="search",
                ok=True,
                latency_ms=123,
                source_hits={"grok": 2, "tavily": 1},
                path=str(target),
                metadata={"mode": "deep"},
            )
            self.assertIsNone(err)

            t2 = DecisionTrace(request_id="req-extract")
            t2.add_event("extract.request", "request_received")
            err = persist_decision_trace_jsonl(
                trace=t2,
                trace_kind="extract",
                ok=False,
                latency_ms=240,
                source_hits={"mineru": 1},
                path=str(target),
                metadata={"strategy": "auto"},
            )
            self.assertIsNone(err)

            agg = aggregate_decision_trace_jsonl(str(target), limit=100)
            self.assertTrue(agg["exists"])
            self.assertEqual(agg["records_used"], 2)
            self.assertEqual(agg["overall"]["failed"], 1)
            self.assertAlmostEqual(agg["overall"]["failure_rate"], 0.5, places=4)
            self.assertEqual(agg["by_kind"]["search"]["total"], 1)
            self.assertEqual(agg["by_kind"]["extract"]["failed"], 1)
            self.assertEqual(agg["source_hits"]["grok"], 2)
            self.assertEqual(agg["source_hits"]["mineru"], 1)


if __name__ == "__main__":
    unittest.main()

