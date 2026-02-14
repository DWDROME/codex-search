import itertools
import multiprocessing
import re
import sys
import unittest
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import codex_search_stack.contracts as contracts
from codex_search_stack.contracts import DecisionTrace


_REQ_ID_RE = re.compile(r"^[0-9a-f]{12}$")


def _generate_ids_in_process(total: int) -> list[str]:
    from codex_search_stack.contracts import DecisionTrace

    return [DecisionTrace().request_id for _ in range(total)]


class DecisionTraceRequestIdTests(unittest.TestCase):
    def setUp(self) -> None:
        contracts._REQUEST_ID_COUNTER = itertools.count()
        contracts._REQUEST_ID_AGENT = ""

    def test_request_id_without_random_source_dependency(self) -> None:
        with patch("uuid.uuid4", side_effect=AssertionError("uuid.uuid4 should never be called")):
            with patch("codex_search_stack.contracts.os.urandom", side_effect=AssertionError("os.urandom should not be called")):
                trace = DecisionTrace()

        self.assertRegex(trace.request_id, _REQ_ID_RE)

    def test_request_id_uniqueness_under_threads(self) -> None:
        with patch("codex_search_stack.contracts.os.urandom", side_effect=AssertionError("os.urandom should not be called")):
            with ThreadPoolExecutor(max_workers=8) as pool:
                ids = [trace.request_id for trace in pool.map(lambda _: DecisionTrace(), range(1000))]

        self.assertEqual(len(ids), len(set(ids)))
        for request_id in ids:
            self.assertRegex(request_id, _REQ_ID_RE)

    def test_request_id_uniqueness_under_three_processes(self) -> None:
        per_process = 400
        start_method = "fork" if "fork" in multiprocessing.get_all_start_methods() else "spawn"
        ctx = multiprocessing.get_context(start_method)
        with ProcessPoolExecutor(max_workers=3, mp_context=ctx) as pool:
            groups = list(pool.map(_generate_ids_in_process, [per_process, per_process, per_process]))
        ids = [request_id for group in groups for request_id in group]

        self.assertEqual(len(ids), len(set(ids)))
        for request_id in ids[:20]:
            self.assertRegex(request_id, _REQ_ID_RE)

    def test_request_id_format_is_stable(self) -> None:
        with patch("codex_search_stack.contracts.os.urandom", side_effect=AssertionError("os.urandom should not be called")):
            ids = [DecisionTrace().request_id for _ in range(50)]
        for request_id in ids:
            self.assertRegex(request_id, _REQ_ID_RE)

    def test_request_id_uses_agent_hint(self) -> None:
        with patch.dict("os.environ", {"CODEX_SEARCH_AGENT_ID": "agent-A"}, clear=False):
            contracts._REQUEST_ID_AGENT = "agent-A"
            trace = DecisionTrace()
        self.assertRegex(trace.request_id, _REQ_ID_RE)


if __name__ == "__main__":
    unittest.main()
