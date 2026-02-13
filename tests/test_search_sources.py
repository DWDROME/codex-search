import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codex_search_stack.search.sources import _extract_sse_content, _parse_result_payload, _safe_results


class SearchSourcesTests(unittest.TestCase):
    def test_parse_result_payload_from_fenced_json(self) -> None:
        payload = "```json\n{\"results\":[{\"title\":\"A\",\"url\":\"https://a.com\"}]}\n```"
        data = _parse_result_payload(payload)
        self.assertEqual(data["results"][0]["url"], "https://a.com")

    def test_parse_result_payload_from_embedded_json(self) -> None:
        payload = "prefix text\n{\"results\":[{\"title\":\"A\",\"url\":\"https://a.com\"}]}\nsuffix"
        data = _parse_result_payload(payload)
        self.assertEqual(data["results"][0]["title"], "A")

    def test_extract_sse_content(self) -> None:
        raw = (
            "data: {\"choices\":[{\"delta\":{\"content\":\"hello \"}}]}\n\n"
            "data: {\"choices\":[{\"delta\":{\"content\":\"world\"}}]}\n\n"
        )
        self.assertEqual(_extract_sse_content(raw), "hello world")

    def test_safe_results_filters_invalid_urls(self) -> None:
        rows = [
            {"title": "ok", "url": "https://ok.com", "snippet": "x", "published_date": ""},
            {"title": "bad", "url": "ftp://bad.com", "snippet": "x", "published_date": ""},
            {"title": "bad2", "url": "https:///missing-host", "snippet": "x", "published_date": ""},
        ]
        out = _safe_results(rows, "test")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["source"], "test")


if __name__ == "__main__":
    unittest.main()
