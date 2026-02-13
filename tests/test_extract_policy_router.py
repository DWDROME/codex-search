import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codex_search_stack.config import Settings
from codex_search_stack.contracts import DecisionTrace, ExtractRequest
from codex_search_stack.policy.extract_router import build_extract_plan


def _settings(**kwargs) -> Settings:
    base = dict(
        grok_api_url=None,
        grok_api_key=None,
        grok_model="grok-4.1",
        exa_api_key=None,
        tavily_api_key="tvly-key",
        tavily_api_url="https://api.tavily.com",
        github_token=None,
        key_pool_file=None,
        key_pool_enabled=False,
        confidence_profile="deep",
        mineru_token="mineru-token",
        mineru_token_file=None,
        mineru_api_base="https://mineru.net",
        mineru_wrapper_path=None,
        mineru_workspace=None,
        search_timeout_seconds=15,
        extract_timeout_seconds=12,
        policy={},
        decision_trace_enabled=True,
    )
    base.update(kwargs)
    return Settings(**base)


class ExtractPolicyRouterTests(unittest.TestCase):
    def test_auto_anti_bot_host_routes_to_mineru_only(self) -> None:
        settings = _settings()
        request = ExtractRequest(url="https://zhuanlan.zhihu.com/p/123", strategy="auto")
        trace = DecisionTrace()

        plan = build_extract_plan(request, settings, trace)

        self.assertEqual(plan.strategy, "mineru_only")
        self.assertEqual(plan.first_engine, "mineru")
        self.assertEqual(plan.fallback_engine, "")
        self.assertGreaterEqual(len(trace.events), 1)

    def test_policy_default_strategy_is_used(self) -> None:
        settings = _settings(policy={"extract": {"default_strategy": "mineru_first"}})
        request = ExtractRequest(url="https://example.com/a", strategy="")
        trace = DecisionTrace()

        plan = build_extract_plan(request, settings, trace)

        self.assertEqual(plan.strategy, "mineru_first")
        self.assertEqual(plan.first_engine, "mineru")
        self.assertEqual(plan.fallback_engine, "tavily")

    def test_force_mineru_overrides_strategy(self) -> None:
        settings = _settings()
        request = ExtractRequest(url="https://example.com/a", strategy="tavily_only", force_mineru=True)
        trace = DecisionTrace()

        plan = build_extract_plan(request, settings, trace)

        self.assertEqual(plan.strategy, "mineru_only")
        self.assertEqual(plan.first_engine, "mineru")
        self.assertIn("force_mineru:true", plan.notes)


if __name__ == "__main__":
    unittest.main()
