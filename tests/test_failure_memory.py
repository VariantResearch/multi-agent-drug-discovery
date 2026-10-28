"""Tests for the operator-side failure memory: the EverOS
client's request mapping, the recorder's entry building from
synthetic finished-run bundles, the disabled and unreachable
no-op behaviour, and the isolation rule - no blinded pipeline
module may import the failure memory, and in the whole package
only the operator CLI may.
"""
import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.failure_memory import (EverOSClient, build_failure_entry,
                                 entry_text, failure_memory_enabled,
                                 record_bundle, search_failures)

ROOT = Path(__file__).resolve().parent.parent
ENABLED = {"MADD_FAILURE_MEMORY": "everos"}


class FakeTransport:
    """A transport double: records every call, answers canned
    JSON, or raises a stored error to simulate an outage."""

    def __init__(self, error=None):
        """Start with no calls recorded and an optional error
        to raise on every call."""
        self.calls = []
        self.error = error

    def __call__(self, method, url, payload, timeout):
        """Record the call, then raise or answer."""
        self.calls.append({"method": method, "url": url,
                           "payload": payload, "timeout": timeout})
        if self.error is not None:
            raise self.error
        return 200, '{"ok": true, "results": []}'


def no_go_bundle():
    """A synthetic finished target run whose debate would not
    lock: one failed consensus test and three strikes."""
    return {
        "kind": "target_run", "run_id": "target-test-001",
        "mode": "dual_judge", "outcome": "no_go",
        "target": {"name": "SYNTH1", "kind": "target"},
        "frame_run": {"record": {
            "outcome": "no_go",
            "strike_list": [{"claim_id": "c1"}, {"claim_id": "c2"},
                            {"claim_id": "c3"}],
            "consensus": {"all_passed": False, "results": [
                {"test": "focus_unanimity", "passed": True,
                 "detail": "one focus"},
                {"test": "quote_integrity", "passed": False,
                 "detail": "two claims carry quotes absent from "
                           "their sources"}]}}},
        "design": None,
    }


def gate0_fail_bundle():
    """A synthetic finished Gate 0 run that failed one threshold
    and recorded an audit violation."""
    return {
        "kind": "gate0_run", "run_id": "gate0-test-001",
        "mode": "dual_judge", "outcome": "fail",
        "audit_violations": 1, "judge_swap_flips": 0,
        "thresholds": {"passed": False, "checks": [
            {"threshold": "kill_negatives", "status": "pass",
             "detail": "3 of 4 killed"},
            {"threshold": "baseline_margin", "status": "fail",
             "detail": "panel ties the single-model baseline"}]},
    }


def design_gate_fail_bundle():
    """A synthetic finished target run that locked but whose
    design gate refused every candidate."""
    return {
        "kind": "target_run", "run_id": "target-test-002",
        "mode": "simple", "outcome": "design_gate_failed",
        "target": {"name": "SYNTH2", "kind": "target"},
        "frame_run": {"record": {"outcome": "locked",
                                 "strike_list": [],
                                 "consensus": {"all_passed": True,
                                               "results": []}}},
        "design": {"gate_report": {"result": "fail", "checks": [
            {"name": "spec_locked", "status": "pass",
             "detail": "brief built from locked spec"},
            {"name": "real_candidates_ranked", "status": "fail",
             "detail": "every ranked candidate is synthetic"}]}},
    }


def clean_bundle():
    """A synthetic clean designed run: no failure to log."""
    bundle = design_gate_fail_bundle()
    bundle["run_id"] = "target-test-003"
    bundle["outcome"] = "designed"
    bundle["design"] = {"gate_report": {"result": "pass", "checks": [
        {"name": "real_candidates_ranked", "status": "pass",
         "detail": "2 non-synthetic candidates ranked"}]}}
    return bundle


def test_client_maps_requests_to_the_everos_api():
    """add, flush, and search hit the v2 endpoints with the
    madd app id, the failure-memory project id, the message
    shape EverOS expects, and keyword search."""
    transport = FakeTransport()
    client = EverOSClient(base_url="http://127.0.0.1:8000/",
                          transport=transport)
    client.add("sess-1", [{"sender_id": "madd-failure-log",
                           "role": "user", "timestamp": 123,
                           "content": "a failure"}])
    client.flush("sess-1")
    client.search("no_go", top_k=3)
    add, flush, search = transport.calls
    assert add["url"] == "http://127.0.0.1:8000/api/v2/memory/add"
    assert add["payload"]["session_id"] == "sess-1"
    assert add["payload"]["app_id"] == "madd"
    assert add["payload"]["project_id"] == "failure-memory"
    assert add["payload"]["messages"][0]["content"] == "a failure"
    assert flush["url"] == "http://127.0.0.1:8000/api/v2/memory/flush"
    assert flush["payload"]["session_id"] == "sess-1"
    assert search["url"] == "http://127.0.0.1:8000/api/v2/memory/search"
    assert search["payload"]["query"] == "no_go"
    assert search["payload"]["method"] == "keyword"
    assert search["payload"]["top_k"] == 3


def test_recorder_builds_entry_from_no_go_bundle():
    """A no_go run produces a no_go entry carrying the failed
    consensus test's recorded detail and the strike count."""
    entry = build_failure_entry(no_go_bundle())
    assert entry is not None
    assert entry["run_id"] == "target-test-001"
    assert entry["target"] == "SYNTH1"
    assert entry["mode"] == "dual_judge"
    assert entry["categories"] == ["no_go"]
    assert entry["strikes"] == 3
    assert any("quote_integrity" in reason
               and "absent from their sources" in reason
               for reason in entry["reasons"])
    text = entry_text(entry)
    assert "target-test-001" in text and "no_go" in text


def test_recorder_builds_entry_from_gate0_threshold_failure():
    """A failed Gate 0 run produces threshold and audit entries
    carrying the run's own recorded check details."""
    entry = build_failure_entry(gate0_fail_bundle())
    assert entry is not None
    assert "threshold_failure" in entry["categories"]
    assert "audit_violations" in entry["categories"]
    assert any("baseline_margin" in reason
               and "ties the single-model baseline" in reason
               for reason in entry["reasons"])


def test_recorder_builds_entry_from_design_gate_failure():
    """A design gate failure produces an entry carrying the
    failed gate check's recorded detail."""
    entry = build_failure_entry(design_gate_fail_bundle())
    assert entry is not None
    assert entry["categories"] == ["design_gate_failed"]
    assert any("real_candidates_ranked" in reason
               for reason in entry["reasons"])


def test_recorder_ignores_a_clean_designed_run():
    """A clean designed outcome is not a failure entry, and
    recording one is a reported no-op, not an error."""
    assert build_failure_entry(clean_bundle()) is None
    report = record_bundle(clean_bundle(), environ=ENABLED,
                           client=EverOSClient(transport=FakeTransport()))
    assert report["status"] == "not_a_failure"


def test_disabled_is_a_quiet_noop():
    """With the opt-in unset, recording and searching report
    disabled and make no transport calls at all."""
    transport = FakeTransport()
    client = EverOSClient(transport=transport)
    assert not failure_memory_enabled({})
    report = record_bundle(no_go_bundle(), client=client, environ={})
    assert report["status"] == "disabled"
    search = search_failures("no_go", client=client, environ={})
    assert search["status"] == "disabled"
    assert transport.calls == []


def test_unreachable_server_is_a_quiet_noop():
    """With the feature on but the server down, recording and
    searching report unavailable instead of raising."""
    transport = FakeTransport(error=ConnectionError("refused"))
    client = EverOSClient(transport=transport)
    report = record_bundle(no_go_bundle(), client=client,
                           environ=ENABLED)
    assert report["status"] == "unavailable"
    assert report["entry"]["run_id"] == "target-test-001"
    search = search_failures("no_go", client=client, environ=ENABLED)
    assert search["status"] == "unavailable"


def test_recorder_posts_and_flushes_the_entry():
    """An enabled recorder adds the rendered entry text, then
    flushes the same session, in that order."""
    transport = FakeTransport()
    client = EverOSClient(transport=transport)
    report = record_bundle(no_go_bundle(), client=client,
                           environ=ENABLED)
    assert report["status"] == "recorded"
    assert [call["url"].rsplit("/", 1)[-1]
            for call in transport.calls] == ["add", "flush"]
    content = transport.calls[0]["payload"]["messages"][0]["content"]
    assert "target-test-001" in content
    assert "no_go" in content
    assert "quote_integrity" in content


def _imported_modules(path):
    """Every module name a source file imports, by AST."""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _imports_failure_memory(path):
    """True when a source file imports the failure memory under
    any spelling (relative, package, or submodule)."""
    return any(name == "failure_memory"
               or name.endswith(".failure_memory")
               for name in _imported_modules(path))


BLINDED_MODULES = [
    "debate.py", "gate0.py", "target_run.py", "runner.py",
    "providers.py", "providers_http.py", "config.py",
    "prompting.py", "consensus.py", "claims.py",
    "citation_auditor.py", "audit_flow.py", "entailment.py",
    "contradictions.py", "resolve.py", "retrieval.py",
    "fulltext.py",
]


def test_blinded_pipeline_modules_do_not_import_failure_memory():
    """Isolation: the debate engine, the Gate 0 dataset and
    scorer, the target pipeline, the runner, the providers, the
    config, and the audit family (claims, citation auditor,
    audit flow, entailment, contradictions, resolution) never
    import the failure memory. The design family is covered by
    the design glob below."""
    package = ROOT / "madd"
    offenders = [name for name in BLINDED_MODULES
                 if _imports_failure_memory(package / name)]
    offenders += [path.name for path in sorted(package.glob("design*.py"))
                  if _imports_failure_memory(path)]
    assert offenders == [], (
        "blinded pipeline modules importing failure_memory: "
        + str(offenders))


def test_only_the_operator_cli_imports_failure_memory():
    """Isolation, package-wide: outside failure_memory.py
    itself, the only module in madd/ that may import it is the
    operator CLI. The console, the run pipeline, and every
    other module stay clean."""
    package = ROOT / "madd"
    importers = sorted(
        path.name for path in package.glob("*.py")
        if path.name != "failure_memory.py"
        and _imports_failure_memory(path))
    assert importers == ["cli.py"], (
        "unexpected failure_memory importers: " + str(importers))
