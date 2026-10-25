"""The four consensus tests, as pure functions, plus the dissent log check.

Tests operate on plain dicts (dossiers and a candidate consensus spec) and
return structured results. Agreement is a process outcome here, never
evidence: these tests decide whether a specification may be locked, they
do not make any claim true.
"""
from __future__ import annotations

from .claims import audit_claims, is_audited


def test_agreement(dossiers: list) -> dict:
    focuses = []
    for d in dossiers:
        if isinstance(d, dict):
            focuses.append(d.get("proposed_focus_id") or d.get("focus_id"))
    distinct = sorted({f for f in focuses if f})
    missing = len(dossiers) - len(focuses) + sum(1 for f in focuses if not f)
    # Every dossier must actually propose a focus: agreement among the
    # dossiers that named one, while another named none, is not agreement.
    passed = (len(dossiers) >= 2 and len(focuses) == len(dossiers)
              and all(focuses) and len(distinct) == 1)
    detail = "focus identifiers seen: " + ", ".join(str(f) for f in distinct)
    if missing:
        detail += "; dossiers without a focus: " + str(missing)
    return {"test": "agreement", "passed": passed, "detail": detail}


def test_survival(spec: dict) -> dict:
    report = audit_claims(spec)
    return {"test": "survival", "passed": report["ok"],
            "detail": "load-bearing claim audit errors: " + str(report["error_count"]),
            "audit": report}


def test_evidence_floor(spec: dict) -> dict:
    claims = spec.get("claims", []) if isinstance(spec, dict) else []
    audited_tiers = [c.get("evidence_tier") for c in claims if isinstance(c, dict) and is_audited(c)]
    best = min(audited_tiers) if audited_tiers else None
    passed = best is not None and best <= 3
    return {"test": "evidence_floor", "passed": passed,
            "detail": "best audited tier: " + (str(best) if best is not None else "none"),
            "audited_tiers": audited_tiers}


def test_stability(spec_a: dict, spec_b: dict) -> dict:
    fa = spec_a.get("focus_id") if isinstance(spec_a, dict) else None
    fb = spec_b.get("focus_id") if isinstance(spec_b, dict) else None
    passed = fa is not None and fa == fb
    return {"test": "stability", "passed": passed,
            "detail": "judge A focus: " + str(fa) + "; judge B focus: " + str(fb)}


def check_dissent_log(spec: dict) -> dict:
    if not isinstance(spec, dict) or "dissent_log" not in spec:
        return {"test": "dissent_log", "passed": False,
                "detail": "dissent_log field missing"}
    log = spec.get("dissent_log")
    if not isinstance(log, list):
        return {"test": "dissent_log", "passed": False, "detail": "dissent_log is not a list"}
    if len(log) == 0:
        reason = spec.get("dissent_none_reason")
        if not isinstance(reason, str) or reason.strip() == "":
            return {"test": "dissent_log", "passed": False,
                    "detail": "empty dissent_log without a dissent_none_reason"}
    return {"test": "dissent_log", "passed": True,
            "detail": "dissent entries: " + str(len(log))}


def run_consensus_tests(dossiers: list, spec: dict, swapped_spec: dict | None = None) -> dict:
    results = [test_agreement(dossiers), test_survival(spec), test_evidence_floor(spec),
               check_dissent_log(spec)]
    if swapped_spec is not None:
        results.append(test_stability(spec, swapped_spec))
    else:
        results.append({"test": "stability", "passed": False,
                        "detail": "no judge-swapped specification supplied; stability not established"})
    return {"all_passed": all(r["passed"] for r in results), "results": results}
