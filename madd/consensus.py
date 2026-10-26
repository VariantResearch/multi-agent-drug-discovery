"""The four consensus tests, as pure functions, plus the dissent log check.

Tests operate on plain dicts (dossiers and a candidate consensus spec) and
return structured results. Agreement is a process outcome here, never
evidence: these tests decide whether a specification may be locked, they
do not make any claim true.
"""
from __future__ import annotations

from .claims import audit_claims, is_audited


def test_agreement(dossiers: list) -> dict:
    """Agreement: at least two dossiers, every one of them naming a
    focus, exactly one distinct focus across all of them, and - when
    any dossier states a direction - exactly one distinct direction.

    The direction rule matters because a locked spec is scored as an
    advance: two dossiers pointing at the same focus in opposite
    directions (one advance, one kill) are not agreement, and before
    this rule the panel could lock a spec whose direction said kill
    and have it scored as advance. The same logic closes the
    unanimous case: when every dossier states the direction and the
    one stated direction is kill, the panel has agreed to kill, not
    to advance, so there is no specification to lock even though a
    focus is named. (The research contract asks a non-advancing
    agent to omit the focus; a focus paired with an explicit kill
    is contradictory input, and the mechanical reading of the
    panel's stated decision is kill.)
    """
    focuses = []
    directions = []
    for d in dossiers:
        if isinstance(d, dict):
            focuses.append(d.get("proposed_focus_id") or d.get("focus_id"))
            directions.append(d.get("direction"))
    distinct = sorted({f for f in focuses if f})
    missing = len(dossiers) - len(focuses) + sum(1 for f in focuses if not f)
    stated = [x for x in directions if x]
    distinct_directions = sorted(set(stated))
    direction_ok = len(distinct_directions) <= 1 and len(stated) in (0, len(dossiers))
    unanimous_kill = (len(stated) == len(dossiers) and len(dossiers) > 0
                      and distinct_directions == ["kill"])
    # Every dossier must actually propose a focus: agreement among the
    # dossiers that named one, while another named none, is not agreement.
    passed = (len(dossiers) >= 2 and len(focuses) == len(dossiers)
              and all(focuses) and len(distinct) == 1 and direction_ok
              and not unanimous_kill)
    detail = "focus identifiers seen: " + ", ".join(str(f) for f in distinct)
    if missing:
        detail += "; dossiers without a focus: " + str(missing)
    if not direction_ok:
        detail += ("; directions disagree or are only partly stated: "
                   + ", ".join(str(x) for x in distinct_directions))
    if unanimous_kill:
        detail += ("; every dossier directs kill: the panel's stated "
                   "decision is to kill, so no specification can lock")
    return {"test": "agreement", "passed": passed,
            "status": "passed" if passed else "failed", "detail": detail}


def test_survival(spec: dict) -> dict:
    """Survival: the candidate specification's own claim ledger audit
    must come back clean, so nothing struck quietly re-enters."""
    report = audit_claims(spec)
    return {"test": "survival", "passed": report["ok"],
            "status": "passed" if report["ok"] else "failed",
            "detail": "load-bearing claim audit errors: " + str(report["error_count"]),
            "audit": report}


def test_evidence_floor(spec: dict) -> dict:
    """Evidence floor: the specification must carry at least one
    audited claim at tier 3 or better (best audited tier of 3 or less)."""
    claims = spec.get("claims", []) if isinstance(spec, dict) else []
    audited_tiers = [c.get("evidence_tier") for c in claims if isinstance(c, dict) and is_audited(c)]
    best = min(audited_tiers) if audited_tiers else None
    passed = best is not None and best <= 3
    return {"test": "evidence_floor", "passed": passed,
            "status": "passed" if passed else "failed",
            "detail": "best audited tier: " + (str(best) if best is not None else "none"),
            "audited_tiers": audited_tiers}


def test_stability(spec_a: dict, spec_b: dict) -> dict:
    """Stability: two specifications (original and judge-swapped)
    must name the same, present focus identifier."""
    fa = spec_a.get("focus_id") if isinstance(spec_a, dict) else None
    fb = spec_b.get("focus_id") if isinstance(spec_b, dict) else None
    passed = fa is not None and fa == fb
    return {"test": "stability", "passed": passed,
            "status": "passed" if passed else "failed",
            "detail": "judge A focus: " + str(fa) + "; judge B focus: " + str(fb)}


def check_dissent_log(spec: dict) -> dict:
    """Dissent log: the log must exist and be a list; an empty log is
    acceptable only when the specification gives a dissent_none_reason."""
    if not isinstance(spec, dict) or "dissent_log" not in spec:
        return {"test": "dissent_log", "passed": False, "status": "failed",
                "detail": "dissent_log field missing"}
    log = spec.get("dissent_log")
    if not isinstance(log, list):
        return {"test": "dissent_log", "passed": False, "status": "failed",
                "detail": "dissent_log is not a list"}
    if len(log) == 0:
        reason = spec.get("dissent_none_reason")
        if not isinstance(reason, str) or reason.strip() == "":
            return {"test": "dissent_log", "passed": False, "status": "failed",
                    "detail": "empty dissent_log without a dissent_none_reason"}
    return {"test": "dissent_log", "passed": True, "status": "passed",
            "detail": "dissent entries: " + str(len(log))}


def run_consensus_tests(dossiers: list, spec: dict, swapped_spec: dict | None = None,
                        stability_required: bool = True) -> dict:
    """Run all four consensus tests plus the dissent-log check.

    Every result carries a status: passed, failed, or not_applied.
    Stability is the one test a protocol mode may declare not
    applicable: the dual protocol (two research models, no judge) has
    no judge to swap, so with stability_required=False and no swapped
    specification the stability result is reported as not_applied
    rather than failed, and the record says so plainly. The default
    keeps the original rule: without a swapped specification,
    stability is reported as failed with the reason stated, so a
    missing judge can never pass quietly."""
    results = [test_agreement(dossiers), test_survival(spec), test_evidence_floor(spec),
               check_dissent_log(spec)]
    if swapped_spec is not None:
        results.append(test_stability(spec, swapped_spec))
    elif stability_required:
        results.append({"test": "stability", "passed": False, "status": "failed",
                        "detail": "no judge-swapped specification supplied; stability not established"})
    else:
        results.append({"test": "stability", "passed": True, "status": "not_applied",
                        "detail": "protocol mode has no judge; the judge-swap "
                                  "stability test is not applied"})
    return {"all_passed": all(r["passed"] for r in results), "results": results}
