"""Failure memory: an operator-side log of what failed and why,
backed by an EverOS memory server.

This is the TradeMemory-style failure log scoped on 2026-10-27.
It records finished runs that failed, or partly failed, so the
operator can learn across runs: which thresholds failed, which
targets no-go'd and on what recorded reasons, which design gates
refused, and how many audit strikes a debate collected.

ISOLATION RULE. This module is operator-side only. It is never
imported by, read by, or fed into any blinded run path (debate,
Gate 0, target runs, design, providers, the claim and citation
audits). Recording happens only after a run has finished and its
bundle is written, and only when the operator invokes it through
the failures command. Nothing in a run can change behaviour
because of anything stored here; the failure log is a notebook
for the human, not an input to the pipeline. A test
(tests/test_failure_memory.py) scans the pipeline modules'
sources and fails if any of them imports this module.

OPT-IN. Recording and reading are off unless the environment
variable MADD_FAILURE_MEMORY is set to "everos".
EVEROS_BASE_URL overrides the server address (default
http://127.0.0.1:8000). When the feature is disabled, or the
server is unreachable, every entry point here is a quiet no-op
that reports its status instead of raising: a memory outage can
never fail, delay, or alter a run or an operator command's real
work.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

ENABLE_ENV = "MADD_FAILURE_MEMORY"
BASE_URL_ENV = "EVEROS_BASE_URL"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
APP_ID = "madd"
PROJECT_ID = "failure-memory"
OPERATOR_ID = "operator"
SENDER_ID = "madd-failure-log"


def failure_memory_enabled(environ=None) -> bool:
    """True only when the opt-in variable names the EverOS
    backend. Anything else, including unset, is off."""
    env = os.environ if environ is None else environ
    return str(env.get(ENABLE_ENV) or "").strip().lower() == "everos"


def everos_base_url(environ=None) -> str:
    """The EverOS base URL: the override variable when set,
    otherwise the local default."""
    env = os.environ if environ is None else environ
    return str(env.get(BASE_URL_ENV) or DEFAULT_BASE_URL).rstrip("/")


def _urllib_transport(method, url, payload, timeout):
    """Default transport: one JSON HTTP request via urllib.
    Returns (status, body text). Raises on transport errors;
    callers treat any raise as unavailability."""
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers,
                                     method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.read().decode("utf-8", "replace")


class EverOSClient:
    """A minimal EverOS REST API v2 client (add, flush, search)
    over an injectable transport, so tests never touch a network.

    The transport is a callable (method, url, payload, timeout)
    returning (status, body text); the default is urllib.
    """

    def __init__(self, base_url=DEFAULT_BASE_URL, transport=None,
                 timeout=5.0):
        """Bind the client to a base URL and a transport."""
        self.base_url = str(base_url).rstrip("/")
        self.transport = transport or _urllib_transport
        self.timeout = timeout

    def _post(self, path, payload) -> dict:
        """POST one JSON payload and return the decoded body.
        Raises EverOSUnavailable on any transport or HTTP
        failure, so callers have exactly one failure shape."""
        try:
            status, body = self.transport(
                "POST", self.base_url + path, payload, self.timeout)
        except Exception as exc:
            raise EverOSUnavailable(
                "EverOS request to " + path + " failed: "
                + type(exc).__name__ + ": " + str(exc)) from exc
        if status < 200 or status >= 300:
            raise EverOSUnavailable(
                "EverOS answered HTTP " + str(status) + " for " + path)
        try:
            decoded = json.loads(body) if body else {}
        except ValueError:
            return {}
        return decoded if isinstance(decoded, dict) else {}

    def add(self, session_id, messages) -> dict:
        """Add messages to a session. Each message is a dict
        with sender_id, role, timestamp (ms epoch), content."""
        return self._post("/api/v2/memory/add", {
            "session_id": session_id, "app_id": APP_ID,
            "project_id": PROJECT_ID, "messages": list(messages)})

    def flush(self, session_id) -> dict:
        """Flush a session so its messages become durable,
        indexed memory."""
        return self._post("/api/v2/memory/flush", {
            "session_id": session_id, "app_id": APP_ID,
            "project_id": PROJECT_ID})

    def search(self, query, top_k=10) -> dict:
        """Keyword-search the failure memory. Keyword method is
        the Tier 1 search that needs no embedding provider."""
        return self._post("/api/v2/memory/search", {
            "user_id": OPERATOR_ID, "app_id": APP_ID,
            "project_id": PROJECT_ID, "query": query,
            "method": "keyword", "top_k": int(top_k)})


class EverOSUnavailable(Exception):
    """The EverOS server could not serve a request. Recording
    and reading catch this and report unavailable; it is never
    allowed to propagate into a run path."""


def _debate_record(bundle) -> dict:
    """The debate record inside a bundle, whichever run shape
    carries it; an empty dict when there is none."""
    frame_run = bundle.get("frame_run") or {}
    return frame_run.get("record") or bundle.get("record") or {}


def _design_section(bundle) -> dict:
    """The design bundle section: the nested design of a target
    run, or the bundle itself for a standalone design run."""
    if bundle.get("kind") == "design_run":
        return bundle
    return bundle.get("design") or {}


def build_failure_entry(bundle) -> dict | None:
    """Build the failure entry for one finished run bundle, or
    None when the run holds no failure worth logging.

    Only failures and partial failures produce an entry: a Gate 0
    threshold failure, a debate that would not lock (no_go), a
    design gate failure, a stopped run, recorded audit
    violations, or an explicit error recorded on the bundle. A
    clean designed, passed, or locked outcome returns None. The
    reasons are the run's own recorded texts (threshold details,
    failed consensus test details, gate check details), never a
    paraphrase invented here.
    """
    if not isinstance(bundle, dict):
        return None
    categories = []
    reasons = []

    def note(category, reason):
        """Record one failure category and its reason text."""
        if category not in categories:
            categories.append(category)
        if reason and reason not in reasons:
            reasons.append(reason)

    kind = bundle.get("kind")
    outcome = bundle.get("outcome")
    record = _debate_record(bundle)
    strikes = record.get("strike_list")
    strike_count = len(strikes) if isinstance(strikes, list) else None

    if bundle.get("error"):
        note("provider_error", "recorded error: " + str(bundle["error"]))

    if kind == "gate0_run":
        thresholds = bundle.get("thresholds") or {}
        if outcome == "fail" or thresholds.get("passed") is False:
            for check in thresholds.get("checks") or []:
                if check.get("status") != "pass":
                    note("threshold_failure",
                         "threshold " + str(check.get("threshold"))
                         + ": " + str(check.get("detail")))
            if not reasons:
                note("threshold_failure",
                     "Gate 0 thresholds did not pass")
        violations = bundle.get("audit_violations")
        if isinstance(violations, int) and violations > 0:
            note("audit_violations",
                 str(violations) + " audit violation(s) recorded")
        if outcome == "stopped":
            note("run_stopped",
                 "run stopped early: " + str(bundle.get("stopped")))

    debate_outcome = record.get("outcome")
    if debate_outcome == "no_go" or outcome == "no_go":
        consensus = record.get("consensus") or {}
        for result in consensus.get("results") or []:
            if not result.get("passed"):
                note("no_go",
                     "consensus test " + str(result.get("test"))
                     + ": " + str(result.get("detail")))
        if "no_go" not in categories:
            note("no_go", "the debate did not lock a specification")
    if debate_outcome == "stopped" or outcome == "stopped":
        note("run_stopped", "the run stopped before finishing")

    design = _design_section(bundle)
    gate = design.get("gate_report") or {}
    if gate.get("result") == "fail" or outcome == "design_gate_failed":
        for check in gate.get("checks") or []:
            if check.get("status") != "pass":
                note("design_gate_failed",
                     "design gate check " + str(check.get("name"))
                     + ": " + str(check.get("detail")))
        if "design_gate_failed" not in categories:
            note("design_gate_failed", "the design gate did not pass")

    if not categories:
        return None
    target = (bundle.get("target") or {}).get("name")
    return {
        "run_id": bundle.get("run_id"),
        "kind": kind,
        "mode": bundle.get("mode"),
        "target": target,
        "outcome": outcome,
        "categories": categories,
        "reasons": reasons,
        "strikes": strike_count,
    }


def entry_text(entry) -> str:
    """Render one failure entry as the plain-text memory an
    operator reads back from a search."""
    lines = ["MADD failure record"]
    lines.append("run: " + str(entry.get("run_id"))
                 + " | kind: " + str(entry.get("kind"))
                 + " | mode: " + str(entry.get("mode"))
                 + " | outcome: " + str(entry.get("outcome")))
    if entry.get("target"):
        lines.append("target: " + str(entry["target"]))
    lines.append("categories: " + ", ".join(entry["categories"]))
    if entry.get("strikes") is not None:
        lines.append("audit strikes: " + str(entry["strikes"]))
    lines.append("reasons:")
    for reason in entry["reasons"]:
        lines.append(" - " + str(reason))
    return "\n".join(lines)


def _session_id(entry) -> str:
    """The EverOS session id for one entry: one session per run,
    so a re-record of the same run stays in one place."""
    raw = str(entry.get("run_id") or "unknown-run")
    return "madd-failure-" + "".join(
        ch if ch.isalnum() or ch in "-_" else "-" for ch in raw)


def record_bundle(bundle, client=None, environ=None) -> dict:
    """Record one finished bundle's failure entry, if it has
    one and the feature is enabled. Never raises for a disabled
    feature, a clean run, or an unreachable server; the returned
    report says which of those happened:
    status disabled | not_a_failure | unavailable | recorded."""
    if not failure_memory_enabled(environ):
        return {"status": "disabled",
                "detail": "failure memory is off; set " + ENABLE_ENV
                          + "=everos to enable it",
                "entry": None}
    entry = build_failure_entry(bundle)
    if entry is None:
        return {"status": "not_a_failure",
                "detail": "the run recorded no failure to log",
                "entry": None}
    client = client or EverOSClient(base_url=everos_base_url(environ))
    session_id = _session_id(entry)
    message = {"sender_id": SENDER_ID, "role": "user",
               "timestamp": int(time.time() * 1000),
               "content": entry_text(entry)}
    try:
        client.add(session_id, [message])
        client.flush(session_id)
    except EverOSUnavailable as exc:
        return {"status": "unavailable", "detail": str(exc),
                "entry": entry}
    return {"status": "recorded",
            "detail": "failure entry stored in session " + session_id,
            "entry": entry}


def record_bundle_file(path, client=None, environ=None) -> dict:
    """Load a finished bundle (bundle.json path or run folder)
    and record its failure entry. Same report shape as
    record_bundle; a bundle that cannot be loaded reports
    status unreadable instead of raising."""
    from .compare import load_bundle_anywhere
    try:
        bundle = load_bundle_anywhere(path)
    except Exception as exc:
        return {"status": "unreadable",
                "detail": "could not load the bundle: "
                          + type(exc).__name__ + ": " + str(exc),
                "entry": None}
    return record_bundle(bundle, client=client, environ=environ)


def search_failures(query, top_k=10, client=None, environ=None) -> dict:
    """Search the failure memory as the operator. Reports
    status disabled | unavailable | ok, with the server's raw
    result payload under "result" when the search served."""
    if not failure_memory_enabled(environ):
        return {"status": "disabled",
                "detail": "failure memory is off; set " + ENABLE_ENV
                          + "=everos to enable it",
                "result": None}
    client = client or EverOSClient(base_url=everos_base_url(environ))
    try:
        result = client.search(query, top_k=top_k)
    except EverOSUnavailable as exc:
        return {"status": "unavailable", "detail": str(exc),
                "result": None}
    return {"status": "ok", "detail": "search served by EverOS",
            "result": result}
