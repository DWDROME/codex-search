import importlib
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class _FakeFastMCP:
    def __init__(self, name: str) -> None:
        self.name = name
        self.tools = {}
        self.tool_desc = {}
        self.ran = False

    def tool(self, name: str, description: str):
        def decorator(func):
            self.tools[name] = func
            self.tool_desc[name] = description
            return func

        return decorator

    def run(self) -> None:
        self.ran = True


class _DummyResult:
    def __init__(self, payload):
        self._payload = payload

    def to_dict(self):
        return dict(self._payload)


class MCPServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tracked_modules = [
            "mcp",
            "mcp.server",
            "mcp.server.fastmcp",
            "codex_search_stack.mcp_server",
        ]
        self._backup = {name: sys.modules.get(name) for name in self._tracked_modules}
        for name in self._tracked_modules:
            sys.modules.pop(name, None)

        mcp_module = types.ModuleType("mcp")
        server_module = types.ModuleType("mcp.server")
        fastmcp_module = types.ModuleType("mcp.server.fastmcp")
        fastmcp_module.FastMCP = _FakeFastMCP
        server_module.fastmcp = fastmcp_module
        mcp_module.server = server_module
        sys.modules["mcp"] = mcp_module
        sys.modules["mcp.server"] = server_module
        sys.modules["mcp.server.fastmcp"] = fastmcp_module

        self.mod = importlib.import_module("codex_search_stack.mcp_server")
        self.mcp = self.mod.mcp

    def tearDown(self) -> None:
        for name in self._tracked_modules:
            sys.modules.pop(name, None)
        for name, module in self._backup.items():
            if module is not None:
                sys.modules[name] = module

    def test_tools_registered(self) -> None:
        self.assertEqual(self.mcp.name, "codex-search")
        self.assertEqual(set(self.mcp.tools.keys()), {"search", "extract", "explore", "research", "get_config_info"})

    def test_search_tool_success(self) -> None:
        payload = {"mode": "deep", "query": "q", "count": 1, "results": [{"title": "x", "url": "https://a"}]}
        with patch.object(self.mod, "load_settings", return_value=object()), patch.object(
            self.mod, "run_multi_source_search", return_value=_DummyResult(payload)
        ) as run_search:
            raw = self.mcp.tools["search"](query="q")

        data = json.loads(raw)
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["query"], "q")
        run_search.assert_called_once()

    def test_extract_tool_success(self) -> None:
        payload = {
            "ok": True,
            "engine": "tavily_extract",
            "source_url": "https://example.com",
            "notes": ["primary:tavily_extract"],
        }
        with patch.object(self.mod, "load_settings", return_value=object()), patch.object(
            self.mod, "run_extract_pipeline", return_value=_DummyResult(payload)
        ) as run_extract:
            raw = self.mcp.tools["extract"](url="https://example.com")

        data = json.loads(raw)
        self.assertTrue(data["ok"])
        self.assertEqual(data["engine"], "tavily_extract")
        run_extract.assert_called_once()

    def test_explore_tool_markdown_and_json(self) -> None:
        with patch.object(self.mod, "load_settings", return_value=types.SimpleNamespace(confidence_profile="deep")), patch.object(
            self.mod,
            "run_github_explorer",
            return_value={"ok": True, "target": "openai/codex", "repo": {"full_name": "openai/codex"}},
        ) as run_explore, patch.object(self.mod, "attach_book_to_result") as attach_book, patch.object(
            self.mod,
            "persist_explore_artifacts",
            return_value={"out_dir": ".runtime/demo", "book_downloaded": 1, "book_download_failed": 0},
        ) as persist, patch.object(self.mod, "render_markdown", return_value="# report") as render_md:
            md = self.mcp.tools["explore"](target="openai/codex", output_format="markdown")
            raw = self.mcp.tools["explore"](target="openai/codex", output_format="json", with_artifacts=False)

        data = json.loads(raw)
        self.assertIn("# report", md)
        self.assertIn("**📁 输出目录**", md)
        self.assertEqual(data["target"], "openai/codex")
        self.assertEqual(run_explore.call_count, 2)
        self.assertEqual(attach_book.call_count, 2)
        persist.assert_called_once()
        self.assertEqual(render_md.call_count, 2)

    def test_failure_injection_search_tool(self) -> None:
        with patch.object(self.mod, "load_settings", return_value=object()), patch.object(
            self.mod, "run_multi_source_search", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                self.mcp.tools["search"](query="q")

    def test_search_tool_validation_error(self) -> None:
        raw = self.mcp.tools["search"](query="latest ai news", intent="status")
        data = json.loads(raw)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"]["code"], "invalid_arguments")
        self.assertIn("requires freshness", data["error"]["message"])

    def test_extract_tool_validation_error(self) -> None:
        raw = self.mcp.tools["extract"](url="not-a-url")
        data = json.loads(raw)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"]["code"], "invalid_arguments")
        self.assertIn("valid http(s) URL", data["error"]["message"])

    def test_extract_tool_force_mineru_on_high_risk_domain(self) -> None:
        payload = {"ok": True, "engine": "mineru", "source_url": "https://zhuanlan.zhihu.com/p/1", "notes": []}
        settings = types.SimpleNamespace(policy={})
        with patch.object(self.mod, "load_settings", return_value=settings), patch.object(
            self.mod, "run_extract_pipeline", return_value=_DummyResult(payload)
        ) as run_extract:
            self.mcp.tools["extract"](url="https://zhuanlan.zhihu.com/p/1", force_mineru=False)

        _, kwargs = run_extract.call_args
        self.assertTrue(kwargs["force_mineru"])

    def test_explore_tool_validation_error(self) -> None:
        raw = self.mcp.tools["explore"](target="openai/codex", issues=1)
        data = json.loads(raw)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"]["code"], "invalid_arguments")
        self.assertIn("issues must be between 3 and 20", data["error"]["message"])

    def test_research_tool_success(self) -> None:
        payload = {"ok": True, "query": "q", "count": 1, "results": [{"title": "x", "url": "https://a"}]}
        with patch.object(self.mod, "load_settings", return_value=object()), patch.object(
            self.mod, "run_research_loop", return_value=payload
        ) as run_research:
            raw = self.mcp.tools["research"](query="q")
        data = json.loads(raw)
        self.assertTrue(data["ok"])
        self.assertEqual(data["count"], 1)
        run_research.assert_called_once()

    def test_research_tool_validation_error(self) -> None:
        raw = self.mcp.tools["research"](query="latest ai news", intent="status")
        data = json.loads(raw)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"]["code"], "invalid_arguments")
        self.assertIn("requires freshness", data["error"]["message"])


if __name__ == "__main__":
    unittest.main()
