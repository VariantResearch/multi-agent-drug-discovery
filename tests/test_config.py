"""Run config tests. Keys here are invented strings in a fake environ."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.config import ConfigError, build_providers, validate_config
from madd.providers import MockProvider
from madd.providers_http import AnthropicProvider, OpenAICompatibleProvider

ENV = {"OPENAI_API_KEY": "invented-key-a", "ANTHROPIC_API_KEY": "invented-key-b"}

CONFIG = {
    "providers": [
        {"name": "panel-a", "kind": "openai-compatible", "model": "model-a",
         "family": "fam-a", "api_key_env": "OPENAI_API_KEY"},
        {"name": "panel-b", "kind": "anthropic", "model": "model-b",
         "family": "fam-b", "api_key_env": "ANTHROPIC_API_KEY"},
        {"name": "panel-c", "kind": "mock", "label": "pc"},
    ],
    "judge": {"name": "judge", "kind": "mock", "label": "j"},
    "baseline": {"name": "base", "kind": "mock", "label": "b"},
    "budget": {"max_cost_usd": 10.0},
    "live_resolution": True,
}


class TestConfig(unittest.TestCase):
    """Tests for config."""
    def test_example_config_file_is_valid(self):
        """Example config file is valid."""
        import json
        example = json.loads((Path(__file__).resolve().parent.parent
                              / "examples" / "run-config.example.json")
                             .read_text(encoding="utf-8"))
        self.assertEqual(validate_config(example), [])

    def test_build_all_kinds(self):
        """Build all kinds."""
        built = build_providers(CONFIG, environ=dict(ENV))
        kinds = [type(p).__name__ for p in built["providers"]]
        self.assertEqual(kinds, ["OpenAICompatibleProvider",
                                 "AnthropicProvider", "MockProvider"])
        self.assertIsInstance(built["judge"], MockProvider)
        self.assertIsInstance(built["baseline"], MockProvider)
        self.assertEqual(built["budget"], {"max_cost_usd": 10.0})
        self.assertTrue(built["live_resolution"])
        self.assertEqual(built["providers"][0].model_version, "model-a")

    def test_missing_key_variable_names_the_variable(self):
        """Missing key variable names the variable."""
        with self.assertRaises(ConfigError) as ctx:
            build_providers(CONFIG, environ={})
        self.assertIn("OPENAI_API_KEY", str(ctx.exception))
        self.assertNotIn("invented-key", str(ctx.exception))

    def test_duplicate_names_rejected(self):
        """Duplicate names rejected."""
        bad = {"providers": [{"name": "x", "kind": "mock"},
                             {"name": "x", "kind": "mock"}]}
        self.assertTrue(any("unique" in e for e in validate_config(bad)))

    def test_too_few_providers_rejected(self):
        """Too few providers rejected."""
        bad = {"providers": [{"name": "only", "kind": "mock"}]}
        self.assertTrue(validate_config(bad))

    def test_http_entry_needs_model_and_key_env(self):
        """Http entry needs model and key env."""
        bad = {"providers": [{"name": "a", "kind": "anthropic"},
                             {"name": "b", "kind": "mock"}]}
        errors = validate_config(bad)
        self.assertTrue(any("model is required" in e for e in errors))
        self.assertTrue(any("api_key_env is required" in e for e in errors))

    def test_uncapped_budget_rejected(self):
        """Uncapped budget rejected."""
        bad = dict(CONFIG)
        bad["budget"] = {}
        self.assertTrue(any("budget" in e for e in validate_config(bad)))


if __name__ == "__main__":
    unittest.main()
