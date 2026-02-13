import unittest
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codex_search_stack.config import Settings
from codex_search_stack.contracts import ExtractionResponse
from codex_search_stack.extract.pipeline import _is_content_usable, run_extract_pipeline
from codex_search_stack.key_pool import KeyCandidate


def make_settings(**overrides) -> Settings:
    base = {
        "grok_api_url": None,
        "grok_api_key": None,
        "grok_model": "grok-4.1",
        "exa_api_key": None,
        "tavily_api_key": "tvly-default",
        "tavily_api_url": "https://api.tavily.com",
        "github_token": None,
        "key_pool_file": None,
        "key_pool_enabled": True,
        "confidence_profile": "deep",
        "mineru_token": "mineru-token",
        "mineru_token_file": None,
        "mineru_api_base": "https://mineru.net",
        "mineru_wrapper_path": None,
        "mineru_workspace": "/tmp/codex-workspace",
        "search_timeout_seconds": 5,
        "extract_timeout_seconds": 5,
        "policy": {},
        "decision_trace_enabled": True,
    }
    base.update(overrides)
    return Settings(**base)


class ExtractPipelineTests(unittest.TestCase):
    def test_content_usable_heuristics(self) -> None:
        self.assertFalse(_is_content_usable(None))
        self.assertFalse(_is_content_usable("short text"))
        blocked = "x" * 500 + " verify you are human "
        self.assertFalse(_is_content_usable(blocked))
        self.assertTrue(_is_content_usable("x" * 800))

    def test_force_domain_goes_directly_to_mineru(self) -> None:
        settings = make_settings()
        with patch("codex_search_stack.extract.pipeline.run_mineru_wrapper") as mocked:
            mocked.return_value = ExtractionResponse(
                ok=True,
                source_url="https://zhuanlan.zhihu.com/p/123",
                engine="mineru",
                markdown="ok",
                notes=["forced"],
                sources=["https://zhuanlan.zhihu.com/p/123"],
            )
            out = run_extract_pipeline("https://zhuanlan.zhihu.com/p/123", settings=settings)
        self.assertTrue(out.ok)
        self.assertEqual(out.engine, "mineru")
        self.assertEqual(mocked.call_count, 1)
        self.assertIsNotNone(out.decision_trace)

    def test_missing_tavily_key_falls_back_to_mineru(self) -> None:
        settings = make_settings(tavily_api_key=None)
        with patch("codex_search_stack.extract.pipeline.run_mineru_wrapper") as mocked:
            mocked.return_value = ExtractionResponse(
                ok=False,
                source_url="https://example.com/a",
                engine="mineru",
                markdown=None,
                notes=["mineru_fallback"],
                sources=["https://example.com/a"],
            )
            out = run_extract_pipeline("https://example.com/a", settings=settings)
        self.assertFalse(out.ok)
        self.assertIn("missing_tavily_api_key", out.notes)
        self.assertIn("mineru_fallback", out.notes)

    def test_tavily_rotation_note_when_second_candidate_succeeds(self) -> None:
        settings = make_settings()
        url = "https://example.com/article"
        candidates = [
            KeyCandidate("tavily", "https://api.tavily.com", "tvly-dev-111111111111", 100, "pool"),
            KeyCandidate("tavily", "https://api.tavily.com", "tvly-dev-222222222222", 90, "pool"),
        ]
        success = ExtractionResponse(
            ok=True,
            source_url=url,
            engine="tavily_extract",
            markdown="x" * 1000,
            notes=["primary:tavily_extract"],
            sources=[url],
        )
        with patch("codex_search_stack.extract.pipeline.build_service_candidates", return_value=candidates), patch(
            "codex_search_stack.extract.pipeline._extract_via_tavily_once",
            side_effect=[RuntimeError("boom"), success],
        ), patch("codex_search_stack.extract.pipeline.run_mineru_wrapper") as mineru:
            out = run_extract_pipeline(url, settings=settings)
        self.assertTrue(out.ok)
        self.assertEqual(out.engine, "tavily_extract")
        self.assertTrue(any(note.startswith("tavily_pool_rotated:") for note in out.notes))
        mineru.assert_not_called()

    def test_unusable_tavily_content_triggers_mineru(self) -> None:
        settings = make_settings()
        url = "https://example.com/article"
        candidates = [KeyCandidate("tavily", "https://api.tavily.com", "tvly-dev-333333333333", 100, "pool")]
        unusable = ExtractionResponse(
            ok=False,
            source_url=url,
            engine="tavily_extract",
            markdown="blocked",
            notes=["tavily_content_not_usable"],
            sources=[url],
        )
        fallback = ExtractionResponse(
            ok=True,
            source_url=url,
            engine="mineru",
            markdown="ok",
            notes=["mineru_ok"],
            sources=[url],
        )
        with patch("codex_search_stack.extract.pipeline.build_service_candidates", return_value=candidates), patch(
            "codex_search_stack.extract.pipeline._extract_via_tavily_once",
            return_value=unusable,
        ), patch("codex_search_stack.extract.pipeline.run_mineru_wrapper", return_value=fallback):
            out = run_extract_pipeline(url, settings=settings)
        self.assertTrue(out.ok)
        self.assertEqual(out.engine, "mineru")
        self.assertIn("tavily_content_not_usable", out.notes)
        self.assertTrue(any(note.startswith("tavily_candidate:") for note in out.notes))

    def test_strategy_tavily_only_does_not_fallback(self) -> None:
        settings = make_settings(tavily_api_key=None)
        with patch("codex_search_stack.extract.pipeline.run_mineru_wrapper") as mineru:
            out = run_extract_pipeline(
                "https://zhuanlan.zhihu.com/p/619438846",
                settings=settings,
                strategy="tavily_only",
            )
        self.assertFalse(out.ok)
        self.assertEqual(out.engine, "tavily_extract")
        self.assertIn("missing_tavily_api_key", out.notes)
        mineru.assert_not_called()

    def test_strategy_mineru_first_fallbacks_to_tavily(self) -> None:
        settings = make_settings()
        url = "https://example.com/mineru-first"
        mineru_failed = ExtractionResponse(
            ok=False,
            source_url=url,
            engine="mineru",
            notes=["mineru_failed"],
            sources=[url],
        )
        tavily_success = ExtractionResponse(
            ok=True,
            source_url=url,
            engine="tavily_extract",
            markdown="x" * 1000,
            notes=["primary:tavily_extract"],
            sources=[url],
        )
        candidates = [KeyCandidate("tavily", "https://api.tavily.com", "tvly-dev-444444444444", 100, "pool")]
        with patch("codex_search_stack.extract.pipeline.run_mineru_wrapper", return_value=mineru_failed), patch(
            "codex_search_stack.extract.pipeline.build_service_candidates",
            return_value=candidates,
        ), patch(
            "codex_search_stack.extract.pipeline._extract_via_tavily_once",
            return_value=tavily_success,
        ):
            out = run_extract_pipeline(url, settings=settings, strategy="mineru_first")
        self.assertTrue(out.ok)
        self.assertEqual(out.engine, "tavily_extract")
        self.assertIn("mineru_failed", out.notes)
        self.assertIsNotNone(out.decision_trace)


if __name__ == "__main__":
    unittest.main()
