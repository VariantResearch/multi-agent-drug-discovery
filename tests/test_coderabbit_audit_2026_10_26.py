"""Regression tests for the 2026-10-26 external audits (CodeRabbit).

Each test names the finding it pins: A1-A7 from the first audit
report, F1-F4 from the same-day follow-up audit of the repairs.
The audits' probes demonstrated every defect against the pre-fix
tree with synthetic providers only; these tests keep them fixed.
"""
import json
from unittest.mock import patch

import pytest

from madd import gui, production, storage
from madd.budget import BudgetExceeded, BudgetTracker
from madd.config import entailment_checker_from_config
from madd.debate import audit_dossier
from madd.design import MockDesigner, run_design
from madd.prompting import parse_dossier_response
from madd.runner import baseline_prediction, run_frame, run_gate0
from madd.target_run import build_target_frame, run_target


def _claim(cid):
    """One schema-valid synthetic claim for the audit probes."""
    return {"_synthetic": True, "claim_id": cid,
            "text": "Invented audit-only claim",
            "load_bearing": True, "evidence_tier": 2,
            "source_kind": "journal_article",
            "source_identifier": "10.99999/synthetic-audit-only",
            "identifier_type": "doi",
            "verification_status": "quote_checked",
            "supporting_quote": "Invented quote"}


class _Provider:
    """Synthetic provider: fixed focus and direction, call counting."""

    model_version = "synthetic-model"
    cost_per_call_usd = 1

    def __init__(self, name, focus="SYNTHETIC-TARGET",
                 direction="advance", bad=False, family="synthetic"):
        """Initialize the test double."""
        self.name, self.focus, self.direction, self.bad = (
            name, focus, direction, bad)
        self.family = family
        self.research_calls = self.complete_calls = 0

    def research(self, frame):
        """Return one parsed dossier naming the fixed focus."""
        self.research_calls += 1
        claim = _claim(self.name + "-claim")
        if self.bad:
            del claim["text"]
        return parse_dossier_response(json.dumps({
            "_synthetic": True, "dossier_id": "D-" + self.name,
            "proposed_focus_id": self.focus, "direction": self.direction,
            "claims": [claim] if self.focus else [],
            "unverified_notes": []}),
            self.name, self.family, frame["frame_id"])

    def complete(self, system, user):
        """Answer entailment prompts and design prompts minimally."""
        self.complete_calls += 1
        if "entailment judge" in system:
            return '{"verdict":"supported"}'
        return '{"candidates":[]}'


def _frame():
    """The synthetic target frame the probes share."""
    return build_target_frame("SYNTHETIC-TARGET", "target")


def test_a1_console_passes_all_four_evidence_switches(tmp_path):
    """A1: a Gate 0 run wires resolver, quote checker, entailment
    checker, and retrieval_first from the config. Written against
    the console's run path; the console no longer runs Gate 0
    (the owner's call: Gate 0 is CLI validation tooling), so the
    probe now targets the surviving CLI path, which shares the
    same run_config_kwargs wiring."""
    from types import SimpleNamespace

    from madd import cli
    config = {"providers": [{"name": "a", "kind": "mock", "label": "a"},
                            {"name": "b", "kind": "mock", "label": "b"}],
              "judge": {"name": "j", "kind": "mock", "label": "j"},
              "baseline": {"name": "base", "kind": "mock", "label": "base"},
              "live_resolution": True, "live_quote_check": True,
              "entailment_check": True, "retrieval_first": True,
              "budget": {"max_calls": 500}}
    cfg = tmp_path / "synthetic.json"
    cfg.write_text(json.dumps(config))
    captured = {}

    def capture(providers, **kwargs):
        """Record the runner invocation, then run it for real
        (mock providers keep it offline and fast)."""
        captured.update(kwargs)
        kwargs.pop("on_event", None)
        return run_gate0(providers, **kwargs)

    args = SimpleNamespace(config=str(cfg), dry_run=False, out=None,
                           gate0_dir=None, jobs=None)
    with patch.object(cli, "run_gate0", capture):
        code = cli._cmd_run_gate0(args)
    # Exit 1: the run completed and failed its thresholds, as
    # mock panels do; 2 would mean the run itself stopped.
    assert code == 1
    assert callable(captured.get("resolver"))
    assert callable(captured.get("quote_checker"))
    assert callable(captured.get("entailment_checker"))
    assert captured.get("retrieval_first") is True
    assert captured.get("budget_tracker") is not None


def test_a2_design_calls_charge_the_run_budget():
    """A2/F4: design completions reserve against the same tracker
    as research; a cap the research stage consumes stops the run
    with BudgetExceeded rather than designing on silently."""
    panel = [_Provider("a"), _Provider("b")]
    with pytest.raises(BudgetExceeded):
        run_target(_frame(), panel, mode="simple",
                   budget={"max_calls": 2})
    actual = sum(p.research_calls + p.complete_calls for p in panel)
    assert actual == 2


def test_a2_entailment_calls_charge_the_run_budget():
    """A2: entailment judging reserves against the shared tracker;
    at the cap the run stops with BudgetExceeded instead of
    overspending unrecorded."""
    panel = [_Provider("a"), _Provider("b")]
    judge = _Provider("judge")
    tracker = BudgetTracker({"max_calls": 3})
    checker = entailment_checker_from_config(
        {"entailment_check": True, "judge": judge}, tracker)
    with pytest.raises(BudgetExceeded):
        run_frame(_frame(), panel, judge_provider=judge,
                  budget_tracker=tracker, entailment_checker=checker)
    actual = sum(p.research_calls + p.complete_calls
                 for p in panel + [judge])
    assert actual == 3 and tracker.calls_made == 3


def _stability_check(bundle):
    """The judge_swap_stability threshold check of a Gate 0 bundle."""
    return next(c for c in bundle["thresholds"]["checks"]
                if c["threshold"] == "judge_swap_stability")


def test_f2_swap_needs_two_judges_from_different_families():
    """A3/F2: the stability threshold compares two independently
    produced judging results from different model families. With
    no swap judge, or a same-family swap judge, there is no swap
    experiment to score: the threshold is not_evaluable, never a
    pass on 0 flips."""
    bundle = run_gate0(
        [_Provider("a"), _Provider("b")],
        judge_provider=_Provider("judge"),
        baseline_provider=_Provider("baseline", None))
    assert bundle["judge_swap_flips"] is None
    assert _stability_check(bundle)["status"] == "not_evaluable"
    bundle = run_gate0(
        [_Provider("a"), _Provider("b")],
        judge_provider=_Provider("judge", family="family-a"),
        swap_judge_provider=_Provider("swap", family="family-a"),
        baseline_provider=_Provider("baseline", None))
    assert bundle["judge_swap_flips"] is None
    assert _stability_check(bundle)["status"] == "not_evaluable"


def test_f2_cross_family_swap_counts_changed_calls():
    """A3/F2: with an operative judge and a different-family swap
    judge, flips are the case calls the swap changed: a swap judge
    disagreeing on focus in all 8 cases flips 8 calls and fails
    the threshold; one agreeing flips none and passes."""
    bundle = run_gate0(
        [_Provider("a"), _Provider("b")],
        judge_provider=_Provider("judge", family="family-a"),
        swap_judge_provider=_Provider("swap", "SYNTHETIC-OTHER",
                                      family="family-b"),
        baseline_provider=_Provider("baseline", None))
    assert bundle["judge_swap_flips"] == 8
    assert _stability_check(bundle)["status"] == "fail"
    bundle = run_gate0(
        [_Provider("a"), _Provider("b")],
        judge_provider=_Provider("judge", family="family-a"),
        swap_judge_provider=_Provider("swap", family="family-b"),
        baseline_provider=_Provider("baseline", None))
    assert bundle["judge_swap_flips"] == 0
    assert _stability_check(bundle)["status"] == "pass"


def test_a5_unanimous_kill_cannot_lock():
    """A5: two dossiers naming one focus and both directing kill
    produce no_go, and the baseline rule reads the same dossier
    the same way."""
    frame = _frame()
    panel = [_Provider("a", direction="kill"),
             _Provider("b", direction="kill")]
    bundle = run_frame(frame, panel, mode="simple")
    assert bundle["outcome"] == "no_go"
    dossier = panel[0].research(frame)
    assert baseline_prediction(dossier) == "kill"


def test_a6_schema_invalid_claims_cannot_lock():
    """A6: claims missing a required schema field become failure
    dossiers at the parser, and the evidence call strikes such a
    claim schema_invalid even in a hand-built dossier."""
    frame = _frame()
    panel = [_Provider("a", bad=True), _Provider("b", bad=True)]
    bundle = run_frame(frame, panel, mode="simple")
    assert bundle["outcome"] == "no_go"
    claim = _claim("c1")
    del claim["text"]
    dossier = {"dossier_id": "D-x", "agent_id": "x",
               "proposed_focus_id": "T", "direction": "advance",
               "claims": [claim]}
    audited = audit_dossier(dossier)
    assert audited["struck"]
    assert "schema_invalid" in audited["struck"][0]["reasons"]


def test_a4_unvalidated_structure_is_not_production_ready():
    """A4: with RDKit unavailable a SMILES candidate's validity is
    unknown, and unknown is not ready."""
    candidate = {"_synthetic": True, "candidate_id": "synthetic-invalid",
                 "modality": "small_molecule",
                 "structure": {"format": "smiles", "value": "invalid((("}}
    with patch("madd.production.design_rdkit.available",
               return_value=False):
        sheet = production.build_production_sheet(candidate, {})
    assert sheet["production_ready"] is False
    assert any("validation" in n for n in sheet["not_specified"])


def test_a4_unassigned_stereocenter_blocks_readiness():
    """A4: a structure with an unassigned stereocenter does not
    determine one product, so its sheet is not production-ready."""
    if not production.design_rdkit.available():
        pytest.skip("RDKit not installed")
    candidate = {"_synthetic": True, "candidate_id": "synthetic-stereo",
                 "modality": "small_molecule",
                 "structure": {"format": "smiles",
                               "value": "CC(O)C(=O)O"}}
    sheet = production.build_production_sheet(candidate, {})
    assert sheet["identity"]["unspecified_stereocenters"] == 1
    assert sheet["production_ready"] is False


def test_a7_design_ids_unique_and_overwrite_refused(tmp_path):
    """A7: two designs of one spec get different run ids, both
    bundles survive, a same-id rewrite of the identical bundle is
    fine, and a different bundle under an existing id is refused."""
    spec = {"artifact_type": "consensus_spec", "spec_id": "SPEC-SYNTHETIC",
            "outcome": "locked", "focus_id": "SYNTHETIC-TARGET",
            "claims": []}
    first = run_design(spec, "synthetic first run",
                       designer=MockDesigner(), rdkit=False, admet=False)
    second = run_design(spec, "synthetic second run",
                        designer=MockDesigner(), rdkit=False, admet=False)
    assert first["run_id"] != second["run_id"]
    out = tmp_path / "runs"
    storage.write_bundle(first, out)
    storage.write_bundle(second, out)
    assert len(storage.list_runs(out)) == 2
    storage.write_bundle(first, out)
    altered = json.loads(json.dumps(first))
    altered["brief"]["source"] = "tampered"
    from madd.artifacts import freeze_artifact
    altered["frozen_bundle"] = freeze_artifact(
        {k: v for k, v in altered.items() if k != "frozen_bundle"})
    with pytest.raises(ValueError, match="refusing to overwrite"):
        storage.write_bundle(altered, out)


def _retry_provider(name, answer):
    """An HTTP provider whose transport 429s twice before answering:
    3 attempts per logical call, reported on last_attempts."""
    import json as _json

    from madd.providers_http import OpenAICompatibleProvider
    attempts = []

    def transport(method, url, headers, body, timeout=None):
        """Synthetic transport: two rate limits, then a 200."""
        attempts.append(1)
        if len(attempts) < 3:
            return 429, {}
        return 200, {"model": "synthetic-model", "choices": [
            {"message": {"content": _json.dumps(answer)}}]}

    provider = OpenAICompatibleProvider(
        name, "synthetic-model", "synthetic-local-key",
        "https://example.org/synthetic-api", cost_per_call_usd=1,
        transport=transport, sleeper=lambda _: None)
    return provider, attempts


def test_f1_design_and_entailment_settle_transport_retries():
    """F1: the design and entailment budget paths settle transport
    retries against the shared tracker, like the research path: 3
    attempts are 3 recorded calls when the cap has headroom, and
    settling over the cap raises BudgetExceeded."""
    from madd.design import ModelDesigner
    provider, attempts = _retry_provider("synthetic-design",
                                         {"candidates": []})
    tracker = BudgetTracker({"max_calls": 5, "max_cost_usd": 5})
    ModelDesigner([provider], budget_tracker=tracker).design(
        {"spec_id": "SPEC-SYNTHETIC"})
    assert len(attempts) == 3 and tracker.calls_made == 3

    provider, attempts = _retry_provider("synthetic-entailment",
                                         {"verdict": "supported"})
    tracker = BudgetTracker({"max_calls": 5, "max_cost_usd": 5})
    checker = entailment_checker_from_config(
        {"entailment_check": True, "judge": provider}, tracker)
    assert checker(_claim("C-SYNTHETIC")) == "supported"
    assert len(attempts) == 3 and tracker.calls_made == 3

    provider, attempts = _retry_provider("synthetic-design",
                                         {"candidates": []})
    tracker = BudgetTracker({"max_calls": 1, "max_cost_usd": 1})
    with pytest.raises(BudgetExceeded):
        ModelDesigner([provider], budget_tracker=tracker).design(
            {"spec_id": "SPEC-SYNTHETIC"})


def test_f3_malformed_claim_ids_are_rejected_not_crashes():
    """F3: a claim whose id is a JSON array is struck schema_invalid
    by the research evidence call and hard-fails the candidate
    audit; neither auditor raises on the unhashable id."""
    from madd.design import audit_candidate
    claim = _claim("placeholder")
    claim["claim_id"] = ["invented-invalid-id"]
    audited = audit_dossier({"dossier_id": "D-SYNTHETIC",
                             "agent_id": "synthetic", "claims": [claim]})
    assert audited["struck"]
    assert "schema_invalid" in audited["struck"][0]["reasons"]
    result = audit_candidate({
        "_synthetic": True, "candidate_id": "C-SYNTHETIC",
        "spec_id": "SPEC-SYNTHETIC", "modality": "peptide",
        "claims": [claim], "predicted_properties": [],
        "constraint_results": []})
    assert result["hard_fail"] is True
    assert result["claim_errors"]


def test_f4_budget_exhaustion_stops_a_design():
    """F4: when the budget runs out mid-panel, BudgetExceeded
    escapes the designer and the design run: a truncated panel is
    a stopped run, never a reported pass."""
    from madd.design import ModelDesigner, run_design

    class CandidateProvider:
        """Designer double returning one rankable candidate."""

        model_version = "synthetic-model"
        cost_per_call_usd = 1

        def __init__(self, name):
            """Initialize the test double."""
            self.name = name
            self.calls = 0

        def complete(self, system, user):
            """Return one synthetic rankable candidate."""
            self.calls += 1
            return json.dumps({"candidates": [{
                "_synthetic": True,
                "description": "Invented for code tests only.",
                "modality": "peptide",
                "structure": {"format": "sequence",
                              "value": "ACDEFGHIK"},
                "claims": [], "constraint_results": [],
                "predicted_properties": [],
                "production_notes": {"modifications": "unmodified"}}]})

    spec = {"_synthetic": True, "artifact_type": "consensus_spec",
            "spec_id": "SPEC-SYNTHETIC", "focus_id": "SYNTHETIC-TARGET",
            "outcome": "locked", "claims": []}
    panel = [CandidateProvider("synthetic-a"),
             CandidateProvider("synthetic-b")]
    tracker = BudgetTracker({"max_calls": 1})
    with pytest.raises(BudgetExceeded):
        run_design(spec, "synthetic",
                   designer=ModelDesigner(panel, budget_tracker=tracker),
                   budget_tracker=tracker, rdkit=False, admet=False)
    assert panel[0].calls == 1 and panel[1].calls == 0
