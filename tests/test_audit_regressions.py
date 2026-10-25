"""Regression tests for the 2026-10-24 full-codebase audit fixes.

Each test names the audit finding it pins. The probes in the audit
report demonstrated every one of these defects against the pre-fix
tree; these tests keep them fixed.
"""
import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from madd import design, design_tools, gate0, storage
from madd.budget import BudgetExceeded, BudgetTracker
from madd.cli import main
from madd.consensus import test_agreement as agreement
from madd.debate import audit_dossier, run_debate
from madd.gui import PAGE
from madd.prompting import build_user_prompt
from madd.providers_http import OpenAICompatibleProvider, ProviderError
from madd.runner import frame_for_case
from madd.smoke import smoke_provider
from madd.transcript import record_to_markdown

ROOT_PACK = "verubecestat-bace1-alzheimer"


def test_h1_forbidden_terms_never_reach_a_provider_prompt():
    pack = gate0.build_agent_pack(ROOT_PACK)
    assert pack.get("forbidden_terms"), "fixture pack must carry terms"
    frame = frame_for_case(ROOT_PACK, pack)
    assert "forbidden_terms" not in frame["case_pack"]
    prompt = build_user_prompt(frame)
    for term in pack["forbidden_terms"]:
        assert term.lower() not in prompt.lower(), term


class _SlowStub:
    def __init__(self, label, counter):
        self.name = "slow-" + label
        self.model_version = "stub"
        self.label = label
        self.counter = counter
        self.cost_per_call_usd = 0.0

    def research(self, frame):
        with self.counter["lock"]:
            self.counter["calls"] += 1
        time.sleep(0.05)
        return {"artifact_type": "dossier", "schema_version": "0.1.0",
                "dossier_id": "D-" + self.label + "-" + str(frame.get("frame_id")),
                "frame_id": frame.get("frame_id"), "agent_id": "agent-" + self.label,
                "model_family": "stub", "proposed_focus_id": None,
                "direction": "kill", "unverified_notes": [], "claims": []}


def test_h2_parallel_debates_cannot_overshoot_the_call_cap():
    from madd.runner import run_gate0
    counter = {"calls": 0, "lock": threading.Lock()}
    providers = [_SlowStub("a", counter), _SlowStub("b", counter)]
    judge = _SlowStub("j", counter)
    baseline = _SlowStub("base", counter)
    # 8 baseline calls fit; the cap leaves room for exactly 1 debate call.
    with pytest.raises(BudgetExceeded):
        run_gate0(providers, judge_provider=judge, baseline_provider=baseline,
                  budget={"max_calls": 9}, max_workers=4, run_id="h2-probe")
    assert counter["calls"] <= 9, counter["calls"]


def _http_provider(transport, **kw):
    return OpenAICompatibleProvider(
        "retry-probe", "probe-model", "test-key",
        base_url="https://example.invalid/v1", family="probe-family",
        transport=transport, sleeper=lambda s: None, **kw)


def test_h5_retries_are_counted_and_smoke_makes_one_transport_call():
    calls = {"n": 0}

    def transport(method, url, headers, body, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            return 429, {}
        return 200, {"model": "probe-model",
                     "choices": [{"message": {"content": "{\"claims\": []}"}}],
                     "usage": {"prompt_tokens": 1, "completion_tokens": 1}}

    provider = _http_provider(transport)
    provider.research({"frame_id": "F-1"})
    assert calls["n"] == 3
    assert provider.last_attempts == 3

    calls["n"] = 0
    provider2 = _http_provider(transport)
    result = smoke_provider(provider2)
    # The transport would have succeeded on a retry (its third call
    # returns 200). Smoke must not retry: exactly one transport call,
    # and the 429 is reported as the failure it is.
    assert result["ok"] is False
    assert "429" in (result["error"] or "")
    assert calls["n"] == 1, "smoke must make exactly one transport call"
    assert provider2.max_retries == 2, "smoke must restore the retry policy"


def test_h5_retry_settling_stops_a_run_that_crosses_the_cap():
    class RetryingStub:
        name = "retrying-stub"
        model_version = "stub"
        cost_per_call_usd = 0.0
        last_attempts = 3

        def research(self, frame):
            return {"artifact_type": "dossier", "schema_version": "0.1.0",
                    "dossier_id": "D-" + str(time.time_ns()),
                    "frame_id": frame.get("frame_id"), "agent_id": "agent-x",
                    "model_family": "stub", "proposed_focus_id": None,
                    "direction": "kill", "unverified_notes": [], "claims": []}

    frame = {"artifact_type": "frame", "schema_version": "0.1.0",
             "frame_id": "F-RETRY", "question": "?", "round_cap": 2}
    # Two providers: reserve 1 + settle 2 = 3 calls each; cap of 4 is
    # crossed while settling the second provider's retries.
    with pytest.raises(BudgetExceeded):
        run_debate(frame, [RetryingStub(), RetryingStub()],
                   budget={"max_calls": 4})


def _candidate(cid, claims, **kw):
    base = {"artifact_type": "candidate", "schema_version": "0.1.0",
            "candidate_id": cid, "spec_id": "SPEC-T-1",
            "modality": "small_molecule", "design_tool": "test",
            "claims": claims, "predicted_properties": [],
            "constraint_results": []}
    base.update(kw)
    return base


def _good_claim(cid):
    return {"claim_id": cid, "text": "supported", "load_bearing": True,
            "evidence_tier": 2, "source_kind": "journal_article",
            "source_identifier": "12345678", "identifier_type": "pmid",
            "verification_status": "quote_checked",
            "supporting_quote": "a real quote"}


def test_h3_candidate_audit_matches_research_layer():
    bad = {"claim_id": "CLM-X", "text": "fabricated support",
           "load_bearing": True, "evidence_tier": 2,
           "source_kind": "journal_article", "source_identifier": "NOT-A-PMID",
           "identifier_type": "pmid", "verification_status": "unverified",
           "supporting_quote": ""}
    audit = design.audit_candidate(_candidate("C-BAD", [bad]))
    assert audit["hard_fail"] is True
    assert audit["audited_load_bearing"] == 0


def test_h3_duplicate_claim_ids_fail_and_never_double_count():
    dup = _candidate("C-DUP", [_good_claim("CLM-D"), _good_claim("CLM-D")])
    audit = design.audit_candidate(dup)
    assert audit["hard_fail"] is True
    assert audit["audited_load_bearing"] == 0
    two = _candidate("C-TWO", [_good_claim("CLM-1"), _good_claim("CLM-2")])
    audit2 = design.audit_candidate(two)
    assert audit2["hard_fail"] is False
    assert audit2["audited_load_bearing"] == 2


def test_m1_agreement_requires_direction_agreement():
    dossiers = [{"proposed_focus_id": "T1", "direction": "advance"},
                {"proposed_focus_id": "T1", "direction": "kill"}]
    assert agreement(dossiers)["passed"] is False
    same = [{"proposed_focus_id": "T1", "direction": "advance"},
            {"proposed_focus_id": "T1", "direction": "advance"}]
    assert agreement(same)["passed"] is True


def test_m1_round_cap_below_one_is_refused():
    frame = {"artifact_type": "frame", "schema_version": "0.1.0",
             "frame_id": "F-CAP", "question": "?", "round_cap": 0}

    class P:
        name = "p"
        model_version = "s"
        cost_per_call_usd = 0.0

        def research(self, f):
            raise AssertionError("research must not run under a 0 cap")

    with pytest.raises(ValueError):
        run_debate(frame, [P(), P()])


def test_m2_duplicate_claim_ids_strike_every_copy():
    malformed = dict(_good_claim("DUP-1"), source_identifier="GARBAGE!!")
    clean = _good_claim("DUP-1")
    dossier = {"dossier_id": "D-1", "agent_id": "a",
               "proposed_focus_id": "T1", "claims": [malformed, clean]}
    out = audit_dossier(dossier)
    assert out["surviving_claims"] == []
    assert len(out["struck"]) == 2
    assert all("duplicate_claim_id" in s["reasons"] for s in out["struck"])


def test_m3_tool_outputs_exclude_stale_files_and_logs(tmp_path, monkeypatch):
    import stat as stat_mod
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "boltz"
    script.write_text(
        "#!/bin/sh\nout=''\nprev=''\nfor a in \"$@\"; do\n"
        "  if [ \"$prev\" = '--out_dir' ]; then out=\"$a\"; fi\n"
        "  prev=\"$a\"\ndone\nmkdir -p \"$out\"\n"
        "printf 'NEW' > \"$out/model.cif\"\nprintf 'log' > \"$out/run.log\"\n")
    script.chmod(script.stat().st_mode | stat_mod.S_IEXEC)
    monkeypatch.setenv("PATH", str(bin_dir))
    work = tmp_path / "work"
    stale_dir = work / "tool-output"
    stale_dir.mkdir(parents=True)
    (stale_dir / "stale_from_yesterday.cif").write_text("OLD")
    manifest = design_tools.run_structure_tool("Boltz-2", "research", work,
                                               input_path="in.yaml")
    assert manifest["status"] == "completed"
    paths = [o["path"] for o in manifest["outputs"]]
    assert any(p.endswith("model.cif") for p in paths)
    assert not any("stale_from_yesterday" in p for p in paths)
    assert any("stale_from_yesterday" in p
               for p in manifest["pre_existing_outputs_skipped"])
    cands = design_tools.candidates_from_tool_run(manifest, "SPEC-T-1")
    assert len(cands) == 1, "the .log output must not become a candidate"
    assert cands[0]["structure"]["format"] == "cif"


def test_m5_load_bundle_refuses_path_traversal(tmp_path):
    with pytest.raises(ValueError):
        storage.load_bundle(tmp_path, "../secret")
    with pytest.raises(ValueError):
        storage.load_bundle(tmp_path, "a/b")


def test_m6_gui_escapes_bundle_fields():
    assert "function esc(" in PAGE
    assert "esc(b.brief.target)" in PAGE
    assert "data-runid" in PAGE
    assert "design-disease" in PAGE


def test_m8_duplicate_candidate_ids_are_refused():
    from tests.test_design import locked_spec
    dupe = _candidate("brief-spec-t-1-a", [])
    with pytest.raises(ValueError):
        design.run_design(locked_spec(), "test", extra_candidates=(dupe,))


def test_m9_transport_failure_is_a_provider_error(monkeypatch):
    import madd.providers_http as ph

    def boom(request, timeout=None):
        raise urllib.error.URLError("name resolution failed")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(ProviderError):
        ph.default_transport("POST", "https://example.invalid/v1", {}, {})


def test_m10_config_validation_catches_bad_numbers():
    from madd.config import validate_config
    cfg = {"providers": [
        {"name": "a", "kind": "openai-compatible", "model": "m",
         "api_key_env": "K", "max_tokens": "lots", "cost_per_call_usd": -5},
        {"name": "b", "kind": "mock"}]}
    errors = validate_config(cfg)
    assert any("max_tokens" in e for e in errors)
    assert any("cost_per_call_usd" in e for e in errors)


def test_low_list_runs_tolerates_a_corrupt_index(tmp_path):
    (tmp_path / "index.json").write_text("{not json")
    assert storage.list_runs(tmp_path) == []


def test_low_transcript_uses_real_record_fields():
    record = {
        "frame_id": "F-T", "outcome": "locked",
        "providers": [], "strike_list": [],
        "ranking": [{"dossier_id": "D1", "focus_score": 100,
                     "struck_count": 0, "wins": 2.0}],
        "cross_examination": [], "evolution": {},
        "consensus": {"results": []}, "judge_swap": None,
        "spec": {"focus_id": "T1", "outcome": "locked", "claims": [],
                 "dissent_log": [{"objector_agent_id": "agent-x",
                                  "objection": "the evidence is thin",
                                  "status": "unresolved"}]},
    }
    text = record_to_markdown(record)
    assert "| 2.0 |" in text
    assert "agent-x: the evidence is thin [unresolved]" in text


def test_low_threshold_details_use_class_denominators():
    predictions = {cid: "advance" for cid in gate0.list_case_ids()}
    score = gate0.score_run(predictions)
    assert score["negative_cases"] == 4
    assert score["positive_cases"] == 4
    checks = gate0.evaluate_thresholds(score, baseline_score=score,
                                       audit_violations=0, judge_swap_flips=0)
    details = {c["threshold"]: c["detail"] for c in checks["checks"]}
    assert "of 4 negative cases" in details["failure_kill_rate"]
    assert "of 4 positive cases" in details["positive_advance_rate"]


def test_low_mock_candidates_do_not_share_mutable_state():
    from tests.test_design import locked_spec
    brief = design.build_brief(locked_spec(), "test")
    a, b = design.MockDesigner().design(brief)
    a["constraint_results"].append({"constraint": "X", "status": "fail"})
    a["predicted_properties"].append({"name": "y", "basis": "designer_prediction"})
    assert len(b["constraint_results"]) == 1
    assert len(b["predicted_properties"]) == 1


def test_h4_design_run_exit_codes_and_tool_gate(tmp_path, capsys):
    from tests.test_design import locked_spec
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(locked_spec()))
    out = tmp_path / "runs"
    # Blocked tool: bundle written, gate fails, exit 1.
    rc = main(["design-run", str(spec_path), "--out", str(out),
               "--tool", "AlphaFold 3", "--use", "commercial"])
    assert rc == 1
    assert "gate: fail" in capsys.readouterr().out
    # Cleared but absent tool: requested_tools_produced fails the gate.
    rc = main(["design-run", str(spec_path), "--out", str(out),
               "--tool", "Boltz-2", "--tool-input", "in.yaml"])
    assert rc == 1
    bundle = storage.load_bundle(out, "design-spec-t-1")
    checks = {c["name"]: c["status"] for c in bundle["gate_report"]["checks"]}
    assert checks["requested_tools_produced"] == "fail"
