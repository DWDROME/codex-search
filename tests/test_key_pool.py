import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codex_search_stack.key_pool import _parse_pool_line, build_service_candidates, load_pool_candidates


class KeyPoolTests(unittest.TestCase):
    def test_parse_csv_line(self) -> None:
        row = _parse_pool_line(
            "grok,https://api.x.ai/v1,sk-abc,200",
            {"grok": "https://fallback", "tavily": "https://api.tavily.com"},
        )
        self.assertIsNotNone(row)
        self.assertEqual(row.service, "grok")
        self.assertEqual(row.url, "https://api.x.ai/v1")
        self.assertEqual(row.key, "sk-abc")
        self.assertEqual(row.weight, 200)

    def test_legacy_single_token_raises_with_line_number(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pool_file = Path(tmp) / "pool.csv"
            pool_file.write_text("user@example.com----tvly-dev-123\n", encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError,
                r"pool\.csv line 1 invalid format \(column_count\), expected service,url,key,weight",
            ):
                load_pool_candidates(
                    str(pool_file),
                    {"grok": "https://api.x.ai/v1", "tavily": "https://api.tavily.com"},
                )

    def test_invalid_service_raises(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            r"pool\.csv line 7 invalid format \(unsupported_service\), expected service,url,key,weight",
        ):
            _parse_pool_line(
                "exa,https://api.exa.ai,key,10",
                {"grok": "https://api.x.ai/v1", "tavily": "https://api.tavily.com"},
                line_no=7,
            )

    def test_build_candidates_dedup_primary_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pool_file = Path(tmp) / "pool.csv"
            pool_file.write_text(
                "grok,https://grok.example,sk-primary,10\n"
                "grok,https://grok.example,sk-other,5\n",
                encoding="utf-8",
            )
            rows = build_service_candidates(
                service="grok",
                primary_url="https://grok.example",
                primary_key="sk-primary",
                pool_file=str(pool_file),
                pool_enabled=True,
            )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].key, "sk-primary")
        self.assertEqual(rows[0].source, "primary")
        self.assertEqual(rows[1].key, "sk-other")


if __name__ == "__main__":
    unittest.main()
