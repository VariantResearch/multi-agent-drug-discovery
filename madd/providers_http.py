"""Live provider adapters: OpenAI-compatible and Anthropic Messages.

These are the sockets the models plug into. Each adapter speaks one
wire protocol over plain HTTPS (standard library only), sends the
shared research prompt from madd/prompting.py, and turns the answer
into a dossier through the shared response contract. Two protocols
cover the field: OpenAI-compatible chat completions (OpenAI itself,
plus OpenRouter, local servers such as LM Studio or Ollama, and most
gateways) and Anthropic Messages (Claude models).

Failure policy, kept deliberate:
- Rate limiting and transient server errors (429, 5xx) are retried a
  bounded number of times with exponential backoff, and every retry
  is recorded on the provider's retry_log and counted into the run
  bundle. A hidden retry would be a quiet change to what a run did;
  a logged one is part of the record.
- Any other HTTP error or a structurally malformed response raises
  ProviderError. That is infrastructure failing, and a scored run must
  stop loudly rather than record a fake empty dossier for an outage.
- A well-formed response whose text is not a usable dossier goes
  through parse_dossier_response and becomes an honest failure
  dossier. That is the model failing the task, which is data.

API keys are passed in by the caller (madd/config.py reads them from
the environment by variable name). Keys are never printed, never put
in a dossier or manifest, and never defaulted.

Token usage from each response is kept on the provider (last_usage)
for the run record. Cost is the caller's configured cost_per_call_usd:
this module invents no prices.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from .prompting import SYSTEM_PROMPT, build_user_prompt, parse_dossier_response

TIMEOUT_SECONDS = 120
ANTHROPIC_VERSION = "2023-06-01"
# Statuses worth retrying: rate limiting and transient server errors.
# Everything else (auth, bad request, not found) fails at once: a
# retry cannot fix it, and a scored run must stop loudly.
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


class ProviderError(RuntimeError):
    """Raised when a provider call fails at the transport or protocol
    level, as opposed to the model returning an unusable answer."""


def default_transport(method, url, headers, body, timeout=TIMEOUT_SECONDS):
    """POST JSON, return (status, parsed_json_or_empty_dict)."""
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json",
                                              **headers})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        status = exc.code
    except urllib.error.URLError as exc:
        # DNS failures, refused connections, TLS errors, timeouts: the
        # module's failure policy is that transport problems surface as
        # ProviderError so run commands stop cleanly, never as a raw
        # urllib traceback.
        raise ProviderError("transport failure: " + str(exc.reason or exc)) from exc
    try:
        return status, json.loads(raw) if raw else {}
    except Exception:
        return status, {}


class _HttpProvider:
    """Shared machinery for the HTTP adapters: configuration, the
    research call sequence (prompt, transport, extract, parse), and
    the failure policy described in the module docstring."""
    protocol = "http"

    def __init__(self, name, model, api_key, base_url, family=None,
                 cost_per_call_usd=0.0, max_tokens=4096, transport=None,
                 timeout=TIMEOUT_SECONDS, max_retries=2, backoff_seconds=1.0,
                 sleeper=None):
        """name identifies the provider in records; model is the exact
        model identifier sent on the wire and reported as model_version;
        api_key is held for the auth header and never written anywhere.
        max_retries bounds the retry policy (see research); sleeper is
        injectable so tests do not actually wait."""
        if not api_key:
            raise ProviderError("provider " + str(name) + ": no API key supplied "
                                "(config names the environment variable to read)")
        self.name = name
        self.model = model
        self.model_version = model
        self.family = family or self.protocol
        self.base_url = base_url.rstrip("/")
        self.cost_per_call_usd = float(cost_per_call_usd or 0.0)
        self.max_tokens = int(max_tokens)
        self._api_key = api_key
        self._transport = transport if transport is not None else default_transport
        self._timeout = timeout
        self.max_retries = int(max_retries)
        self.backoff_seconds = float(backoff_seconds)
        self._sleeper = sleeper if sleeper is not None else time.sleep
        self.retry_log = []
        self.last_usage = None
        self.last_response_model = None
        # Transport attempts the most recent research call actually
        # made (1 + retries used). The budget layer reads this to
        # settle retry costs; see debate.run_debate's research().
        self.last_attempts = 1

    def _call(self, system, user):
        """Send one prompt pair through the transport; subclasses build
        the protocol-specific request."""
        raise NotImplementedError

    def _extract_text(self, payload):
        """Pull the answer text (and record usage) out of a response
        payload; None when the payload is not in the expected shape."""
        raise NotImplementedError

    def research(self, frame: dict) -> dict:
        """Run one research call: build the shared prompt, call, extract
        the text, and parse it through the shared response contract. HTTP
        errors and malformed envelopes raise ProviderError; unusable
        answer text becomes a failure dossier."""
        system = SYSTEM_PROMPT
        user = build_user_prompt(frame)
        status, payload = self._call(system, user)
        attempt = 0
        while status in RETRYABLE_STATUSES and attempt < self.max_retries:
            delay = self.backoff_seconds * (2 ** attempt)
            self.retry_log.append({"status": status, "attempt": attempt + 1,
                                   "delay_seconds": delay,
                                   "frame_id": frame.get("frame_id")})
            self._sleeper(delay)
            status, payload = self._call(system, user)
            attempt += 1
        self.last_attempts = attempt + 1
        if status != 200:
            raise ProviderError("provider " + self.name + ": HTTP " + str(status)
                                + " from " + self.base_url)
        text = self._extract_text(payload)
        if text is None:
            raise ProviderError("provider " + self.name
                                + ": response had no message content in the "
                                + "expected " + self.protocol + " shape")
        self.last_response_model = payload.get("model")
        return parse_dossier_response(text, agent_id=self.name,
                                      model_family=self.family,
                                      frame_id=frame.get("frame_id"))


class OpenAICompatibleProvider(_HttpProvider):
    """POST {base_url}/chat/completions with a Bearer key."""

    protocol = "openai-compatible"

    def _call(self, system, user):
        """POST {base_url}/chat/completions with the Bearer key and a
        system plus user message pair."""
        body = {"model": self.model,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "max_tokens": self.max_tokens}
        return self._transport("POST", self.base_url + "/chat/completions",
                               {"Authorization": "Bearer " + self._api_key},
                               body, timeout=self._timeout)

    def _extract_text(self, payload):
        """Answer text from choices[0].message.content; usage recorded
        from the usage block (prompt and completion tokens)."""
        try:
            usage = payload.get("usage") or {}
            self.last_usage = {"prompt_tokens": usage.get("prompt_tokens"),
                               "completion_tokens": usage.get("completion_tokens"),
                               "total_tokens": usage.get("total_tokens")}
            return payload["choices"][0]["message"]["content"]
        except Exception:
            return None


class AnthropicProvider(_HttpProvider):
    """POST {base_url}/messages with x-api-key and anthropic-version."""

    protocol = "anthropic"

    def _call(self, system, user):
        """POST {base_url}/messages with x-api-key and anthropic-version
        headers, the system prompt as its own field, one user message."""
        body = {"model": self.model, "max_tokens": self.max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}]}
        return self._transport("POST", self.base_url + "/messages",
                               {"x-api-key": self._api_key,
                                "anthropic-version": ANTHROPIC_VERSION},
                               body, timeout=self._timeout)

    def _extract_text(self, payload):
        """Answer text by joining the text blocks of the content array;
        usage recorded from the usage block (input and output tokens)."""
        try:
            usage = payload.get("usage") or {}
            self.last_usage = {"input_tokens": usage.get("input_tokens"),
                               "output_tokens": usage.get("output_tokens")}
            blocks = payload["content"]
            texts = [b.get("text", "") for b in blocks
                     if isinstance(b, dict) and b.get("type") == "text"]
            if not texts:
                return None
            return "".join(texts)
        except Exception:
            return None
