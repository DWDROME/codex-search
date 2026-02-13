import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codex_search_stack.search.scoring import authority_score, composite_score, normalize_url


class ScoringTests(unittest.TestCase):
    def test_normalize_url_removes_utm_and_trailing_slash(self) -> None:
        url = "https://example.com/path/?utm_source=x&keep=1"
        self.assertEqual(normalize_url(url), "https://example.com/path?keep=1")

    def test_authority_score_handles_subdomain(self) -> None:
        self.assertEqual(authority_score("https://gist.github.com/a"), 1.0)
        self.assertEqual(authority_score("https://unknown.example.com/a"), 0.4)

    def test_domain_boost_changes_composite_score(self) -> None:
        kwargs = {
            "query": "python tutorial",
            "intent": "tutorial",
            "url": "https://example.com/post",
            "title": "Python tutorial basics",
            "snippet": "quick start guide",
            "published_date": "2026-01-01",
        }
        score_no_boost = composite_score(boost_domains=[], **kwargs)
        score_with_boost = composite_score(boost_domains=["example.com"], **kwargs)
        self.assertGreater(score_with_boost, score_no_boost)


if __name__ == "__main__":
    unittest.main()
