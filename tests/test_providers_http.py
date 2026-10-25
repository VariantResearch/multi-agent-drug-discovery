"""HTTP provider adapter tests, offline against a fake transport.

The canned responses are shaped from the documented wire formats
(OpenAI chat completions, Anthropic Messages) as of 2026-10-24. They
test the adapters' request building, response handling, and failure
policy. No live call is made here; the adapters have not been run
against a real model account, and nothing in this file claims they
have.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.providers_http import (AnthropicProvider, OpenAICompatibleProvider,
                                 ProviderError)

FRAME = {"frame_id": "F-HTTP-1", "question": "invented?"}
DOSSIER_JSON = json.dumps({
    "proposed_focus_id": "TARGET-X", "direction": "invented",
    "claims": [{"claim_id": "C1", "text": "invented", "load_bearing": True,
                "evidence_tier": 2, "source_kind": "journal_article",
                "source_identifier": "12345678", "identifier_type": "pmid",
                "verification_status": "quote_checked",
                "supporting_quote": "invented quote"}],
    "unverified_notes": []})

OPENAI_RESPONSE = {"model": "model-x-2026", "choices": [
    {"index": 0, "finish_reason": "stop",
     "message": {"role": "assistant", "content": DOSSIER_JSON}}],
    "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}}

ANTHROPIC_RESPONSE = {"model": "model-y-2026", "content": [
    {"type": "text", "text": DOSSIER_JSON}], "stop_reason": "end_turn",
    "usage": {"input_tokens": 90, "output_tokens": 40}}


class FakeTransport:
    """Fake HTTP transport returning canned responses."""
    def __init__(self, status, payload):
        """Initialize the test double."""
        self.status = status
        self.payload = payload
        self.calls = []

    def __call__(self, method, url, headers, body, timeout=0):
        """Act as the callable test double."""
        self.calls.append({"method": method, "url": url,
                           "headers": headers, "body": body})
        return self.status, self.payload


class TestOpenAICompatible(unittest.TestCase):
    """Tests for the OpenAI-compatible provider."""
    def _provider(self, transport):
        """Build the provider under test."""
        return OpenAICompatibleProvider(
            "prov-a", "model-x", "test-key-123", "https://example.invalid/v1",
            family="family-x", transport=transport)

    def test_request_shape_and_response_parse(self):
        """Request shape and response parse."""
        transport = FakeTransport(200, OPENAI_RESPONSE)
        dossier = self._provider(transport).research(FRAME)
        call = transport.calls[0]
        self.assertEqual(call["url"], "https://example.invalid/v1/chat/completions")
        self.assertEqual(call["headers"]["Authorization"], "Bearer test-key-123")
        self.assertEqual(call["body"]["model"], "model-x")
        self.assertEqual(call["body"]["messages"][0]["role"], "system")
        self.assertIn("Never invent an identifier",
                      call["body"]["messages"][0]["content"])
        self.assertEqual(dossier["proposed_focus_id"], "TARGET-X")
        self.assertEqual(dossier["agent_id"], "prov-a")

    def test_usage_recorded(self):
        """Usage recorded."""
        transport = FakeTransport(200, OPENAI_RESPONSE)
        provider = self._provider(transport)
        provider.research(FRAME)
        self.assertEqual(provider.last_usage["total_tokens"], 150)
        self.assertEqual(provider.last_response_model, "model-x-2026")

    def test_http_error_raises(self):
        """Http error raises."""
        transport = FakeTransport(401, {"error": {"message": "bad key"}})
        with self.assertRaises(ProviderError):
            self._provider(transport).research(FRAME)

    def test_malformed_response_raises(self):
        """Malformed response raises."""
        transport = FakeTransport(200, {"unexpected": True})
        with self.assertRaises(ProviderError):
            self._provider(transport).research(FRAME)

    def test_junk_text_becomes_failure_dossier_not_exception(self):
        """Junk text becomes failure dossier not exception."""
        payload = dict(OPENAI_RESPONSE)
        payload["choices"] = [{"message": {"content": "no json here"}}]
        transport = FakeTransport(200, payload)
        dossier = self._provider(transport).research(FRAME)
        self.assertTrue(dossier["parse_error"])
        self.assertEqual(dossier["claims"], [])


class SequenceTransport:
    """Returns queued (status, payload) pairs, one per call."""

    def __init__(self, sequence):
        """Initialize the test double."""
        self.sequence = list(sequence)
        self.calls = 0

    def __call__(self, method, url, headers, body, timeout=0):
        """Act as the callable test double."""
        self.calls += 1
        return self.sequence.pop(0)


class TestRetries(unittest.TestCase):
    """Tests for retries."""
    def _provider(self, transport, sleeps):
        """Build the provider under test."""
        return OpenAICompatibleProvider(
            "prov-r", "model-x", "k", "https://example.invalid/v1",
            transport=transport, sleeper=sleeps.append, backoff_seconds=0.5)

    def test_429_then_success_retries_once_and_logs(self):
        """429 then success retries once and logs."""
        transport = SequenceTransport([(429, {}), (200, OPENAI_RESPONSE)])
        sleeps = []
        dossier = self._provider(transport, sleeps).research(FRAME)
        self.assertEqual(dossier["proposed_focus_id"], "TARGET-X")
        self.assertEqual(transport.calls, 2)
        self.assertEqual(sleeps, [0.5])
        provider_log = self._provider(transport, sleeps)
        self.assertEqual(len(provider_log.retry_log), 0)  # fresh instance

    def test_retry_log_records_the_retry(self):
        """Retry log records the retry."""
        transport = SequenceTransport([(503, {}), (200, OPENAI_RESPONSE)])
        sleeps = []
        provider = self._provider(transport, sleeps)
        provider.research(FRAME)
        self.assertEqual(len(provider.retry_log), 1)
        self.assertEqual(provider.retry_log[0]["status"], 503)

    def test_401_is_never_retried(self):
        """401 is never retried."""
        transport = SequenceTransport([(401, {}), (200, OPENAI_RESPONSE)])
        sleeps = []
        with self.assertRaises(ProviderError):
            self._provider(transport, sleeps).research(FRAME)
        self.assertEqual(transport.calls, 1)

    def test_retries_exhausted_raises(self):
        """Retries exhausted raises."""
        transport = SequenceTransport([(429, {}), (429, {}), (429, {})])
        sleeps = []
        with self.assertRaises(ProviderError):
            self._provider(transport, sleeps).research(FRAME)
        self.assertEqual(transport.calls, 3)
        self.assertEqual(sleeps, [0.5, 1.0])


class TestAnthropic(unittest.TestCase):
    """Tests for anthropic."""
    def _provider(self, transport):
        """Build the provider under test."""
        return AnthropicProvider(
            "prov-b", "model-y", "test-key-456", "https://api.anthropic.com/v1",
            family="family-y", transport=transport)

    def test_request_shape_and_response_parse(self):
        """Request shape and response parse."""
        transport = FakeTransport(200, ANTHROPIC_RESPONSE)
        dossier = self._provider(transport).research(FRAME)
        call = transport.calls[0]
        self.assertEqual(call["url"], "https://api.anthropic.com/v1/messages")
        self.assertEqual(call["headers"]["x-api-key"], "test-key-456")
        self.assertEqual(call["headers"]["anthropic-version"], "2023-06-01")
        self.assertEqual(call["body"]["model"], "model-y")
        self.assertIn("system", call["body"])
        self.assertEqual(dossier["proposed_focus_id"], "TARGET-X")

    def test_usage_recorded(self):
        """Usage recorded."""
        transport = FakeTransport(200, ANTHROPIC_RESPONSE)
        provider = self._provider(transport)
        provider.research(FRAME)
        self.assertEqual(provider.last_usage["input_tokens"], 90)

    def test_http_error_raises(self):
        """Http error raises."""
        transport = FakeTransport(429, {})
        with self.assertRaises(ProviderError):
            self._provider(transport).research(FRAME)

    def test_missing_key_rejected_at_construction(self):
        """Missing key rejected at construction."""
        with self.assertRaises(ProviderError):
            AnthropicProvider("prov-b", "model-y", "", "https://api.anthropic.com/v1")


if __name__ == "__main__":
    unittest.main()
