"""Smoke test tests: mock providers and a failing stub, no network."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.providers import MockProvider
from madd.providers_http import ProviderError
from madd.smoke import smoke_panel, smoke_provider


class FailingProvider:
    """Provider double whose research always fails."""
    name = "failing"
    model_version = "fail-1"
    last_usage = None
    last_response_model = None
    retry_log = []

    def research(self, frame):
        """Return the double's fixed research result."""
        raise ProviderError("provider failing: HTTP 401 from https://example.invalid")


class TestSmoke(unittest.TestCase):
    """Tests for smoke."""
    def test_mock_provider_smokes_ok(self):
        """Mock provider smokes ok."""
        result = smoke_provider(MockProvider("s1"))
        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "mock")
        self.assertIsNone(result["error"])
        self.assertGreaterEqual(result["latency_ms"], 0)

    def test_failure_is_reported_not_raised(self):
        """Failure is reported not raised."""
        result = smoke_provider(FailingProvider())
        self.assertFalse(result["ok"])
        self.assertIn("401", result["error"])

    def test_panel_reports_each_provider(self):
        """Panel reports each provider."""
        results = smoke_panel([MockProvider("a"), FailingProvider()])
        self.assertEqual([r["ok"] for r in results], [True, False])


if __name__ == "__main__":
    unittest.main()
