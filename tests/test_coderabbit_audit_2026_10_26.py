"""Regression tests for the 2026-10-26 external audit (CodeRabbit).

Each test names the finding it pins (A1-A7 in the audit report).
The audit's probes demonstrated every defect against the pre-fix
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
                 direction="advance", bad=False):
        """Initialize the test double."""
        self.name, self.focus, self.direction, self.bad = (
            name, focus, direction, bad)
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
            self.name, "synthetic", frame["frame_id"])

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
    """A1: a console Gate 0 run wires resolver, quote checker,
    entailment checker, and retrieval_first from the config,
    exactly as the CLI does."""
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
    original = gui.run_gate0

    def capture(*args, **kwargs):
        """Record the runner invocation, then run it for real."""
        captured.update(kwargs)
        return original(*args, **kwargs)

    manager = gui.RunManager(str(tmp_path), None)
    with patch.object(gui, "run_gate0", capture):
        manager._run_gate0(str(cfg))
    assert manager.error is None
    assert callable(captured.get("resolver"))
    assert callable(captured.get("quote_checker"))
    assert callable(captured.get("entailment_checker"))
    assert captured.get("retrieval_first") is True
    assert captured.get("budget_tracker") is not None


def test_a2_design_calls_charge_the_run_budget():
    """A2: design completions reserve against the same tracker as
    research, so a cap the research stage consumes leaves nothing
    for design to spend silently."""
    panel = [_Provider("a"), _Provider("b")]
    bundle = run_target(_frame(), panel, mode="simple",
                        budget={"max_calls": 2})
    actual = sum(p.research_calls + p.complete_calls for p in panel)
    recorded = bundle["frame_run"]["record"]["budget"]["calls_made"]
    assert actual == 2 and recorded == 2
    assert bundle["outcome"] == "design_gate_failed"
    assert any("BudgetExceeded" in n
               for n in bundle["design"]["designer_notes"])


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


def test_a3_judge_swap_flips_count_changed_calls():
    """A3: a swapped judge disagreeing on every case reports 8
    flips and fails the stability threshold, not 0 and pass."""
    bundle = run_gate0(
        [_Provider("a"), _Provider("b")],
        judge_provider=_Provider("judge", "SYNTHETIC-OTHER"),
        baseline_provider=_Provider("baseline", None))
    check = next(c for c in bundle["thresholds"]["checks"]
                 if c["threshold"] == "judge_swap_stability")
    assert bundle["judge_swap_flips"] == 8
    assert check["status"] == "fail"


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
