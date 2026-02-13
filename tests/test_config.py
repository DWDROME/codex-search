import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codex_search_stack.config import load_settings


class ConfigTests(unittest.TestCase):
    def test_github_token_reads_official_env_name(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CODEX_SEARCH_CONFIG": "/tmp/__codex_search_tests__/missing.yaml",
                "GITHUB_TOKEN": "ghp-real-token",
            },
            clear=True,
        ):
            settings = load_settings()
        self.assertEqual(settings.github_token, "ghp-real-token")

    def test_legacy_gh_token_is_not_used(self) -> None:
        with patch.dict(
            os.environ,
            {"CODEX_SEARCH_CONFIG": "/tmp/__codex_search_tests__/missing.yaml", "GH_TOKEN": "gh-legacy-token"},
            clear=True,
        ):
            settings = load_settings()
        self.assertIsNone(settings.github_token)

    def test_legacy_github_pat_is_not_used(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CODEX_SEARCH_CONFIG": "/tmp/__codex_search_tests__/missing.yaml",
                "GITHUB_PAT": "ghp-legacy-token",
            },
            clear=True,
        ):
            settings = load_settings()
        self.assertIsNone(settings.github_token)

    def test_yaml_config_is_loaded_from_code_search_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            token_file = root / "mineru_key.txt"
            token_file.write_text("mineru-from-file", encoding="utf-8")
            config_file = root / "config.yaml"
            config_file.write_text(
                "\n".join(
                    [
                        "search:",
                        "  exa:",
                        "    api_key: exa-yaml",
                        "  grok:",
                        "    api_url: https://grok.example/v1",
                        "    api_key: sk-yaml",
                        "    model: grok-4.1-thinking",
                        "  tavily:",
                        "    api_url: http://localhost:8080/mcp",
                        "    api_key: tvly-yaml",
                        "  key_pool:",
                        "    enabled: false",
                        "    file: /tmp/pool.csv",
                        "extract:",
                        "  mineru:",
                        "    token_file: " + str(token_file),
                        "    api_base: https://mineru.example",
                        "    workspace: /tmp/mineru-workspace",
                        "explore:",
                        "  github_token: ghp-yaml",
                        "runtime:",
                        "  confidence_profile: quick",
                        "  search_timeout_seconds: 12",
                        "  extract_timeout_seconds: 34",
                        "policy:",
                        "  models:",
                        "    grok:",
                        "      default: grok-4.1",
                        "      profiles:",
                        "        strong: grok-4.1-thinking",
                        "  routing:",
                        "    by_mode:",
                        "      fast: [exa, grok]",
                        "observability:",
                        "  decision_trace:",
                        "    enabled: false",
                    ]
                ),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"CODEX_SEARCH_CONFIG": str(config_file), "GROK_API_KEY": "sk-env"},
                clear=True,
            ):
                settings = load_settings()

        self.assertEqual(settings.exa_api_key, "exa-yaml")
        self.assertEqual(settings.grok_api_url, "https://grok.example/v1")
        self.assertEqual(settings.grok_api_key, "sk-yaml")
        self.assertEqual(settings.grok_model, "grok-4.1-thinking")
        self.assertEqual(settings.tavily_api_url, "http://localhost:8080/mcp")
        self.assertEqual(settings.tavily_api_key, "tvly-yaml")
        self.assertFalse(settings.key_pool_enabled)
        self.assertEqual(settings.key_pool_file, "/tmp/pool.csv")
        self.assertEqual(settings.mineru_token, "mineru-from-file")
        self.assertEqual(settings.mineru_api_base, "https://mineru.example")
        self.assertEqual(settings.mineru_workspace, "/tmp/mineru-workspace")
        self.assertEqual(settings.github_token, "ghp-yaml")
        self.assertEqual(settings.confidence_profile, "quick")
        self.assertEqual(settings.search_timeout_seconds, 12)
        self.assertEqual(settings.extract_timeout_seconds, 34)
        self.assertIn("models", settings.policy)
        self.assertFalse(settings.decision_trace_enabled)

    def test_env_is_ignored_when_yaml_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_file = Path(tmp) / "config.yaml"
            config_file.write_text(
                "\n".join(
                    [
                        "search:",
                        "  grok:",
                        "    api_url: https://yaml.example/v1",
                        "    api_key: sk-from-yaml",
                    ]
                ),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "CODEX_SEARCH_CONFIG": str(config_file),
                    "GROK_API_URL": "https://env.example/v1",
                    "GROK_API_KEY": "sk-from-env",
                },
                clear=True,
            ):
                settings = load_settings()

        self.assertEqual(settings.grok_api_url, "https://yaml.example/v1")
        self.assertEqual(settings.grok_api_key, "sk-from-yaml")


if __name__ == "__main__":
    unittest.main()
