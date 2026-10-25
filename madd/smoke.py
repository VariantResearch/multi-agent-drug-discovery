"""Provider smoke tests: one small live call per provider.

The HTTP adapters are verified against fake transports in the test
suite, which proves the code, not the account. A smoke test is the
account proof: it makes exactly one research call with a tiny
invented frame per provider and reports whether the call returned, how
long it took, which model string the service actually reported back,
and its token usage. Exactly one call per provider, never more: this
is a billable operation on a real account, and the CLI says so before
running. To keep that promise true at the transport level, the smoke
call disables the provider's retry policy for its one call - a 429
during a smoke test is reported, not retried into three calls. A smoke
pass proves reachability and parsing on the real service; it says
nothing about research quality.
"""
from __future__ import annotations

import time

from .providers_http import ProviderError

SMOKE_FRAME = {
    "artifact_type": "frame",
    "schema_version": "0.1.0",
    "frame_id": "SMOKE-TEST",
    "question": ("Smoke test: return a dossier with no claims and no "
                 "proposed focus. This call checks connectivity only."),
    "round_cap": 1,
}


def smoke_provider(provider, frame=None) -> dict:
    """Make one research call on a provider and report the result.

    Never raises: failures come back as ok=False with the error text,
    so a panel can be reported in one pass.
    """
    started = time.monotonic()
    saved_retries = getattr(provider, "max_retries", None)
    if saved_retries is not None:
        provider.max_retries = 0
    try:
        dossier = provider.research(dict(frame or SMOKE_FRAME))
        error = None
    except ProviderError as exc:
        dossier = None
        error = str(exc)
    except Exception as exc:  # a smoke tool reports, it does not crash
        dossier = None
        error = type(exc).__name__ + ": " + str(exc)
    finally:
        if saved_retries is not None:
            provider.max_retries = saved_retries
    latency_ms = round((time.monotonic() - started) * 1000)
    return {
        "provider": getattr(provider, "name", "?"),
        "model_configured": getattr(provider, "model_version", None),
        "model_returned": getattr(provider, "last_response_model", None),
        "ok": dossier is not None,
        "latency_ms": latency_ms,
        "usage": getattr(provider, "last_usage", None),
        "retries": len(getattr(provider, "retry_log", [])),
        "parse_error": bool(dossier.get("parse_error")) if dossier else None,
        "error": error,
    }


def smoke_panel(providers) -> list:
    """Smoke-test each provider in order; one result dict per provider."""
    return [smoke_provider(p) for p in providers]
