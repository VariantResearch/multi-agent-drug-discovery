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
    def __init__(self, status, payload):
        self.status = status
        self.payload = payload
        self.calls = []

    def __call__(self, method, url, headers, body, timeout=0):
        self.calls.append({"method": method, "url": url,
                           "headers": headers, "body": body})
        return self.status, self.payload


class TestOpenAICompatible(unittest.TestCase):
    def _provider(self, transport):
        return OpenAICompatibleProvider(
            "prov-a", "model-x", "test-key-123", "https://example.invalid/v1",
            family="family-x", transport=transport)

    def test_request_shape_and_response_parse(self):
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
        transport = FakeTransport(200, OPENAI_RESPONSE)
        provider = self._provider(transport)
        provider.research(FRAME)
        self.assertEqual(provider.last_usage["total_tokens"], 150)
        self.assertEqual(provider.last_response_model, "model-x-2026")

    def test_http_error_raises(self):
        transport = FakeTransport(401, {"error": {"message": "bad key"}})
        with self.assertRaises(ProviderError):
            self._provider(transport).research(FRAME)

    def test_malformed_response_raises(self):
        transport = FakeTransport(200, {"unexpected": True})
        with self.assertRaises(ProviderError):
            self._provider(transport).research(FRAME)

    def test_junk_text_becomes_failure_dossier_not_exception(self):
        payload = dict(OPENAI_RESPONSE)
        payload["choices"] = [{"message": {"content": "no json here"}}]
        transport = FakeTransport(200, payload)
        dossier = self._provider(transport).research(FRAME)
        self.assertTrue(dossier["parse_error"])
        self.assertEqual(dossier["claims"], [])


class TestAnthropic(unittest.TestCase):
    def _provider(self, transport):
        return AnthropicProvider(
            "prov-b", "model-y", "test-key-456", "https://api.anthropic.com/v1",
            family="family-y", transport=transport)

    def test_request_shape_and_response_parse(self):
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
        transport = FakeTransport(200, ANTHROPIC_RESPONSE)
        provider = self._provider(transport)
        provider.research(FRAME)
        self.assertEqual(provider.last_usage["input_tokens"], 90)

    def test_http_error_raises(self):
        transport = FakeTransport(429, {})
        with self.assertRaises(ProviderError):
            self._provider(transport).research(FRAME)

    def test_missing_key_rejected_at_construction(self):
        with self.assertRaises(ProviderError):
            AnthropicProvider("prov-b", "model-y", "", "https://api.anthropic.com/v1")


if __name__ == "__main__":
    unittest.main()
