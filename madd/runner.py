"""Run orchestration: full Gate 0 runs and single-frame runs.

Until now the pieces existed but nothing ran them together: the debate
engine debated one frame, the scorer scored a predictions file, and the
threshold evaluator judged a score, with a human expected to carry
results between them. This module is the carrying.

Gate 0 run protocol (docs/PHASE1_SPEC.md), as implemented here:
1. Input packs are validated and leakage-scanned by build_agent_pack
   and hashed into the bundle, so the exact evidence each case ran on
   is part of the record.
2. The baseline runs first: one provider, alone, one dossier per case.
   Its call for a case is "advance" when its dossier proposes a focus
   and at least one of its claims survives the evidence call as an
   audited claim, and "kill" otherwise. That rule is fixed here, in
   code, before any scored run uses it.
3. The debate system runs per case. Its call is "advance" when the
   debate locks a specification and "kill" when it ends in no_go.
4. Both are scored against the sealed outcomes, audit violations and
   judge-swap flips are counted from the debate records, and the
   approved thresholds judge the result.

One budget tracker is shared across the whole run, baseline included,
so a cap is a run cap, not a per-case allowance. A run bundle is a
plain dict; madd/storage.py writes it to disk and madd/report.py
renders it. Nothing here knows or cares whether the providers are
mocks, stubs, or live models.
"""
from __future__ import annotations

import copy
import uuid

from .artifacts import canonical_hash, freeze_artifact
from .budget import BudgetExceeded, BudgetTracker
from .claims import is_audited, validate_claim
from .debate import audit_dossier, run_debate
from .gate0 import (build_agent_pack, evaluate_thresholds, list_case_ids,
                    score_run)


def frame_for_case(case_id: str, pack: dict) -> dict:
    """The frame a provider sees for one Gate 0 case.

    The blinded pack rides inside the frame as case_pack: it is the
    pre-outcome evidence, already leakage-scanned by build_agent_pack.
    Sealed outcomes are never part of a frame.
    """
    return {
        "artifact_type": "frame",
        "schema_version": "0.1.0",
        "frame_id": "GATE0-" + case_id,
        "question": ("Using only the evidence in the case pack, decide whether "
                     "this drug program's target and approach merited advancing "
                     "to a locked specification at the evidence_as_of date."),
        "disease": pack.get("disease"),
        "target": pack.get("target"),
        "drug_name": pack.get("drug_name"),
        "evidence_as_of": pack.get("evidence_as_of"),
        "round_cap": 2,
        "case_pack": copy.deepcopy(pack),
    }


def baseline_prediction(dossier: dict, resolver=None) -> str:
    """The baseline rule, fixed in advance: advance when the lone
    dossier proposes a focus backed by at least one audited surviving
    claim; kill otherwise."""
    audited = audit_dossier(dossier, resolver=resolver)
    if not audited["proposed_focus_id"]:
        return "kill"
    if any(is_audited(c) for c in audited["surviving_claims"]):
        return "advance"
    return "kill"


def spec_audit_violations(spec: dict) -> int:
    """Load-bearing claims in a final specification that rest on struck,
    unverified, or otherwise failing citations: the audit-integrity
    count the approved thresholds set at zero."""
    count = 0
    for claim in spec.get("claims", []):
        if not isinstance(claim, dict) or not claim.get("load_bearing"):
            continue
        if validate_claim(claim):
            count += 1
        elif claim.get("verification_status") not in ("resolved", "quote_checked"):
            count += 1
    return count


def _charge(tracker, provider):
    """Charge one baseline call to the shared run tracker; a call
    that would cross the cap raises BudgetExceeded before it happens."""
    cost = float(getattr(provider, "cost_per_call_usd", 0.0) or 0.0)
    if tracker is not None:
        if tracker.would_exceed(cost):
            raise BudgetExceeded("run budget cap reached before a baseline call")
        tracker.record(cost, note="baseline:" + str(getattr(provider, "name", "?")))


def run_gate0(providers, judge_provider=None, baseline_provider=None,
              budget=None, gate0_dir=None, resolver=None, run_id=None) -> dict:
    """Run the full Gate 0 protocol. Returns the run bundle.

    baseline_provider is required: the approved thresholds include a
    baseline margin, and a run without a baseline cannot be judged.
    """
    if baseline_provider is None:
        raise ValueError("a Gate 0 run needs a baseline provider: the approved "
                         "thresholds judge the debate against a single-model "
                         "baseline, and without one the run is not evaluable")
    tracker = BudgetTracker(budget) if budget is not None else None
    run_id = run_id or ("gate0-" + uuid.uuid4().hex[:12])
    case_ids = list_case_ids(gate0_dir)
    packs = {}
    pack_hashes = {}
    for case_id in case_ids:
        pack = build_agent_pack(case_id, gate0_dir)
        packs[case_id] = pack
        pack_hashes[case_id] = canonical_hash(pack)

    # Baseline first (run protocol step 3).
    baseline_predictions = {}
    baseline_dossiers = {}
    for case_id in case_ids:
        frame = frame_for_case(case_id, packs[case_id])
        _charge(tracker, baseline_provider)
        dossier = baseline_provider.research(copy.deepcopy(frame))
        baseline_dossiers[case_id] = dossier
        baseline_predictions[case_id] = baseline_prediction(dossier, resolver=resolver)

    # Debate per case, sharing the run budget tracker.
    case_records = {}
    predictions = {}
    for case_id in case_ids:
        frame = frame_for_case(case_id, packs[case_id])
        record = run_debate(frame, providers, judge_provider=judge_provider,
                            budget_tracker=tracker, resolver=resolver)
        case_records[case_id] = record
        predictions[case_id] = "advance" if record["outcome"] == "locked" else "kill"

    debate_score = score_run(predictions, gate0_dir)
    baseline_score = score_run(baseline_predictions, gate0_dir)
    violations = sum(spec_audit_violations(rec["spec"]) for rec in case_records.values())
    flips = sum(1 for rec in case_records.values()
                if rec.get("judge_swap")
                and rec["judge_swap"]["proposed_focus_id"] != rec["spec"]["focus_id"])
    thresholds = evaluate_thresholds(debate_score, baseline_score=baseline_score,
                                   audit_violations=violations,
                                   judge_swap_flips=flips)
    bundle = {
        "artifact_type": "gate0_run_bundle",
        "schema_version": "0.1.0",
        "run_id": run_id,
        "kind": "gate0_run",
        "case_ids": case_ids,
        "input_pack_hashes": pack_hashes,
        "providers": [{"name": getattr(p, "name", None),
                       "model_version": getattr(p, "model_version", None)}
                      for p in providers],
        "judge": ({"name": getattr(judge_provider, "name", None),
                   "model_version": getattr(judge_provider, "model_version", None)}
                  if judge_provider is not None else None),
        "baseline_provider": {"name": getattr(baseline_provider, "name", None),
                              "model_version": getattr(baseline_provider,
                                                       "model_version", None)},
        "baseline_predictions": baseline_predictions,
        "baseline_dossiers": baseline_dossiers,
        "predictions": predictions,
        "case_records": case_records,
        "debate_score": debate_score,
        "baseline_score": baseline_score,
        "audit_violations": violations,
        "judge_swap_flips": flips,
        "thresholds": thresholds,
        "budget": tracker.to_dict() if tracker is not None else None,
        "outcome": "pass" if thresholds["passed"] else "fail",
    }
    bundle["frozen_bundle"] = freeze_artifact(
        {k: v for k, v in bundle.items() if k != "frozen_bundle"})
    return bundle


def run_frame(frame, providers, judge_provider=None, budget=None,
              resolver=None, run_id=None) -> dict:
    """Run the debate once on a prospective frame (not a Gate 0 case).

    Returns a frame run bundle whose record is the debate record: a
    locked specification or a no_go, with the full audit trail.
    """
    record = run_debate(frame, providers, judge_provider=judge_provider,
                        budget=budget, resolver=resolver)
    bundle = {
        "artifact_type": "frame_run_bundle",
        "schema_version": "0.1.0",
        "run_id": run_id or ("frame-" + uuid.uuid4().hex[:12]),
        "kind": "frame_run",
        "frame_id": frame.get("frame_id"),
        "record": record,
        "outcome": record["outcome"],
    }
    bundle["frozen_bundle"] = freeze_artifact(
        {k: v for k, v in bundle.items() if k != "frozen_bundle"})
    return bundle


def gate_report(bundle: dict) -> dict:
    """A GateReport artifact (madd/schemas/gate_report.json) for a
    Gate 0 run bundle, in the schema the scaffold shipped but nothing
    produced until now."""
    thresholds = bundle.get("thresholds") or {}
    report = {
        "artifact_type": "gate_report",
        "schema_version": "0.1.0",
        "gate_id": "gate0",
        "gate_name": "Gate 0 retrospective thresholds",
        "subject_id": bundle.get("run_id"),
        "result": "pass" if thresholds.get("passed") else "fail",
        "details": {
            "debate_score": bundle.get("debate_score"),
            "baseline_score": bundle.get("baseline_score"),
            "audit_violations": bundle.get("audit_violations"),
            "judge_swap_flips": bundle.get("judge_swap_flips"),
            "threshold_checks": thresholds.get("checks"),
            "thresholds_source": thresholds.get("thresholds_source"),
            "predictions": bundle.get("predictions"),
            "baseline_predictions": bundle.get("baseline_predictions"),
        },
    }
    return report
