import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codex_search_stack.config import Settings
from codex_search_stack.contracts import DecisionTrace, SearchRequest
from codex_search_stack.policy import build_search_context, build_search_plan


def _settings(**kwargs) -> Settings:
    base = dict(
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
        mineru_token=None,
        mineru_token_file=None,
        mineru_api_base="https://mineru.net",
        mineru_wrapper_path=None,
        mineru_workspace=None,
        search_timeout_seconds=15,
        extract_timeout_seconds=15,
        policy={},
        decision_trace_enabled=True,
    )
    base.update(kwargs)
    return Settings(**base)


class PolicyRouterTests(unittest.TestCase):
    def test_model_profile_routes_to_policy_profile(self) -> None:
        settings = _settings(
            policy={
                "models": {
                    "grok": {
                        "default": "grok-4.1",
                        "profiles": {
                            "strong": "grok-4.1-thinking",
                        },
                    }
                }
            }
        )
        req = SearchRequest(query="test", mode="deep", model_profile="strong")
        ctx = build_search_context(req)
        trace = DecisionTrace()

        plan = build_search_plan(req, ctx, settings, trace)

        self.assertEqual(plan.model, "grok-4.1-thinking")
        self.assertTrue(plan.use_exa)
        self.assertTrue(plan.use_tavily)
        self.assertTrue(plan.use_grok)
        self.assertGreaterEqual(len(trace.events), 2)

    def test_explicit_sources_and_budget_trim(self) -> None:
        settings = _settings()
        req = SearchRequest(query="test", mode="deep", sources=["exa", "grok"])
        req.budget.max_calls = 1
        ctx = build_search_context(req)
        trace = DecisionTrace()

        plan = build_search_plan(req, ctx, settings, trace)

        self.assertEqual(plan.source_order, ["exa"])
        self.assertTrue(plan.use_exa)
        self.assertFalse(plan.use_grok)
        self.assertIn("budget_trimmed_sources:max_calls", plan.notes)

    def test_budget_latency_is_split_to_per_source_timeout(self) -> None:
        settings = _settings(search_timeout_seconds=30)
        req = SearchRequest(query="test", mode="deep", sources=["exa", "tavily", "grok"])
        req.budget.max_calls = 3
        req.budget.max_latency_ms = 6000
        ctx = build_search_context(req)
        trace = DecisionTrace()

        plan = build_search_plan(req, ctx, settings, trace)

        self.assertEqual(plan.source_timeouts.get("exa"), 2)
        self.assertEqual(plan.source_timeouts.get("tavily"), 2)
        self.assertEqual(plan.source_timeouts.get("grok"), 2)

    def test_answer_mode_without_tavily_is_marked(self) -> None:
        settings = _settings(tavily_api_key=None)
        req = SearchRequest(query="test", mode="answer")
        ctx = build_search_context(req)
        trace = DecisionTrace()

        plan = build_search_plan(req, ctx, settings, trace)

        self.assertFalse(plan.use_tavily)
        self.assertIn("answer_mode_without_tavily", plan.notes)


if __name__ == "__main__":
    unittest.main()
