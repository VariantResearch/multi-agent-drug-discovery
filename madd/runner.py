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
from concurrent.futures import ThreadPoolExecutor, as_completed

from .artifacts import canonical_hash, freeze_artifact
from .budget import BudgetExceeded, BudgetTracker
from .claims import is_audited, validate_claim
from .debate import audit_dossier, frame_identifier_set, run_debate
from .gate0 import (build_agent_pack, evaluate_thresholds, list_case_ids,
                    score_run)


def frame_for_case(case_id: str, pack: dict) -> dict:
    """The frame a provider sees for one Gate 0 case.

    The blinded pack rides inside the frame as case_pack: it is the
    pre-outcome evidence, already leakage-scanned by build_agent_pack.
    Sealed outcomes are never part of a frame. Neither is the pack's
    forbidden_terms list: that list is the leakage scanner's wordlist,
    full of outcome vocabulary and pivotal-trial identifiers, and
    sending it to a provider would hand them exactly what the blinding
    exists to withhold. It is stripped here, at the one place a pack
    becomes a frame.
    """
    case_pack = copy.deepcopy(pack)
    case_pack.pop("forbidden_terms", None)
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
        "case_pack": case_pack,
    }


def baseline_prediction(dossier: dict, resolver=None, quote_checker=None,
                        entailment_checker=None, allowed_identifiers=None) -> str:
    """The baseline rule, fixed in advance: advance when the lone
    dossier proposes a focus backed by at least one audited surviving
    claim; kill otherwise."""
    audited = audit_dossier(dossier, resolver=resolver, quote_checker=quote_checker,
                            entailment_checker=entailment_checker,
                            allowed_identifiers=allowed_identifiers)
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
    """Reserve one baseline call against the shared run tracker,
    atomically; a call that would cross the cap raises BudgetExceeded
    before it happens."""
    cost = float(getattr(provider, "cost_per_call_usd", 0.0) or 0.0)
    if tracker is not None:
        tracker.reserve(cost, note="baseline:" + str(getattr(provider, "name", "?")))


def _settle_retries(tracker, provider, cost):
    """Charge a finished call's transport retries to the tracker.

    Retries are real provider calls the reserve did not know about;
    recording them can raise BudgetExceeded, which stops the run with
    honest numbers rather than absorbing the overage silently.
    """
    if tracker is None:
        return
    extra = int(getattr(provider, "last_attempts", 1) or 1) - 1
    if extra > 0:
        tracker.record(cost * extra, calls=extra,
                       note="transport retries:" + str(getattr(provider, "name", "?")))


def _emit(on_event, event: dict):
    """Deliver one progress event to the caller's callback, if any.

    Events are plain dicts with an "event" name plus event-specific
    fields: run_started, baseline_case_done, debate_case_started,
    debate_case_done, run_finished. Interfaces (CLI, GUI) render them;
    the runner itself prints nothing.
    """
    if on_event is not None:
        on_event(event)


def run_gate0(providers, judge_provider=None, baseline_provider=None,
              budget=None, gate0_dir=None, resolver=None, run_id=None,
              on_event=None, max_workers=1, quote_checker=None,
              entailment_checker=None, retrieval_first: bool = False) -> dict:
    """Run the full Gate 0 protocol. Returns the run bundle.

    baseline_provider is required: the approved thresholds include a
    baseline margin, and a run without a baseline cannot be judged.
    on_event, when given, receives progress events (see _emit).
    max_workers runs case debates concurrently; the bundle is
    assembled in case order either way, so results are identical,
    only the wall time and the event order differ.
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

    _emit(on_event, {"event": "run_started", "run_id": run_id,
                     "case_ids": list(case_ids)})

    # Baseline first (run protocol step 3).
    baseline_predictions = {}
    baseline_dossiers = {}
    for case_id in case_ids:
        frame = frame_for_case(case_id, packs[case_id])
        _charge(tracker, baseline_provider)
        dossier = baseline_provider.research(copy.deepcopy(frame))
        _settle_retries(tracker, baseline_provider,
                        float(getattr(baseline_provider, "cost_per_call_usd", 0.0) or 0.0))
        baseline_dossiers[case_id] = dossier
        allowed = None
        if retrieval_first:
            allowed = frame_identifier_set({"case_pack": packs[case_id]}) or set()
        baseline_predictions[case_id] = baseline_prediction(
            dossier, resolver=resolver, quote_checker=quote_checker,
            entailment_checker=entailment_checker, allowed_identifiers=allowed)
        _emit(on_event, {"event": "baseline_case_done", "case_id": case_id,
                         "prediction": baseline_predictions[case_id]})

    # Debate per case, sharing the run budget tracker.
    def debate_one(case_id):
        """Run one case's debate, emitting its progress events;
        returns (case_id, record, prediction)."""
        _emit(on_event, {"event": "debate_case_started", "case_id": case_id})
        frame = frame_for_case(case_id, packs[case_id])
        record = run_debate(frame, providers, judge_provider=judge_provider,
                            budget_tracker=tracker, resolver=resolver,
                            quote_checker=quote_checker,
                            entailment_checker=entailment_checker,
                            retrieval_first=retrieval_first)
        prediction = "advance" if record["outcome"] == "locked" else "kill"
        _emit(on_event, {"event": "debate_case_done", "case_id": case_id,
                         "prediction": prediction,
                         "outcome": record["outcome"],
                         "strikes": len(record["strike_list"])})
        return case_id, record, prediction

    case_records = {}
    predictions = {}
    if max_workers and int(max_workers) > 1:
        with ThreadPoolExecutor(max_workers=int(max_workers)) as pool:
            futures = [pool.submit(debate_one, cid) for cid in case_ids]
            for future in as_completed(futures):
                cid, record, prediction = future.result()
                case_records[cid] = record
                predictions[cid] = prediction
    else:
        for case_id in case_ids:
            cid, record, prediction = debate_one(case_id)
            case_records[cid] = record
            predictions[cid] = prediction
    # Assemble in case order regardless of completion order.
    case_records = {cid: case_records[cid] for cid in case_ids}
    predictions = {cid: predictions[cid] for cid in case_ids}

    debate_score = score_run(predictions, gate0_dir)
    baseline_score = score_run(baseline_predictions, gate0_dir)
    violations = sum(spec_audit_violations(rec["spec"]) for rec in case_records.values())
    # A judge-swap flip is a case call that changed. Only a locked
    # record made an advance call that a different judge focus would
    # have unmade; a no_go record's call is kill under either focus,
    # so a differing judge focus there changes no call and is not
    # counted (the earlier count included those, overstating flips).
    flips = sum(1 for rec in case_records.values()
                if rec["spec"].get("outcome") == "locked"
                and rec.get("judge_swap")
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
        "provider_retries": {getattr(p, "name", str(i)): len(getattr(p, "retry_log", []))
                             for i, p in enumerate(
                                 list(providers)
                                 + ([judge_provider] if judge_provider else [])
                                 + [baseline_provider])},
        "outcome": "pass" if thresholds["passed"] else "fail",
    }
    _emit(on_event, {"event": "run_finished", "run_id": run_id,
                     "outcome": bundle["outcome"],
                     "debate_correct": debate_score["correct_calls"],
                     "baseline_correct": baseline_score["correct_calls"]})
    bundle["frozen_bundle"] = freeze_artifact(
        {k: v for k, v in bundle.items() if k != "frozen_bundle"})
    return bundle


def estimate_gate0_run(providers, judge_provider=None, baseline_provider=None,
                       gate0_dir=None) -> dict:
    """Count what a Gate 0 run will call and what it will cost, from
    the configured per-call costs, without making any call.

    Per case: one baseline call, one research call per panel
    provider, one judge call when a judge is configured. Retries and
    live-resolution lookups are not counted; they are bounded by
    their own settings and reported in the finished bundle.
    """
    cases = list_case_ids(gate0_dir)
    panel = list(providers)

    def cost(provider):
        """The configured per-call cost of one provider (0 when none)."""
        return float(getattr(provider, "cost_per_call_usd", 0.0) or 0.0) \
            if provider is not None else 0.0

    per_case_calls = {"baseline": 1 if baseline_provider is not None else 0,
                      "debate_panel": len(panel),
                      "judge": 1 if judge_provider is not None else 0}
    per_case_cost = (cost(baseline_provider) + sum(cost(p) for p in panel)
                     + cost(judge_provider))
    return {
        "case_count": len(cases),
        "case_ids": cases,
        "calls_per_case": per_case_calls,
        "total_calls": len(cases) * sum(per_case_calls.values()),
        "estimated_cost_usd": round(len(cases) * per_case_cost, 4),
        "baseline_configured": baseline_provider is not None,
        "note": ("research calls only; retries are bounded by each "
                 "provider's max_retries and live-resolution lookups "
                 "are separate registry calls, both reported in the "
                 "finished bundle"),
    }


def run_frame(frame, providers, judge_provider=None, budget=None,
              resolver=None, run_id=None, on_event=None, quote_checker=None,
              entailment_checker=None, retrieval_first: bool = False) -> dict:
    """Run the debate once on a prospective frame (not a Gate 0 case).

    Returns a frame run bundle whose record is the debate record: a
    locked specification or a no_go, with the full audit trail.
    """
    _emit(on_event, {"event": "debate_case_started",
                     "case_id": frame.get("frame_id")})
    record = run_debate(frame, providers, judge_provider=judge_provider,
                        budget=budget, resolver=resolver,
                        quote_checker=quote_checker,
                        entailment_checker=entailment_checker,
                        retrieval_first=retrieval_first)
    _emit(on_event, {"event": "debate_case_done",
                     "case_id": frame.get("frame_id"),
                     "outcome": record["outcome"],
                     "strikes": len(record["strike_list"])})
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
