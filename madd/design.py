"""Phase 2 candidate design: briefs, designers, candidate audit, ranking.

The design stage starts only from a locked consensus spec and applies
the research layer's discipline to what it produces: every candidate
claim is validated like any other claim, every predicted property names
its basis, candidates that fail audit or a recorded constraint are
excluded from the ranking with their reasons preserved, and the ranking
itself is a fixed deterministic rule stated in docs/PHASE2_SPEC.md.

The shipped designer is a deterministic mock. It returns synthetic,
clearly labelled candidates with no structures and no invented numbers,
so the pipeline can be exercised end to end. Real candidates come from
license-gated external tools through madd/design_tools.py, whose
outputs enter as candidates with their provenance recorded and no
assessment invented for them.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from . import citation_auditor
from . import claims as claims_mod
from . import schemas
from .artifacts import freeze_artifact


def _slug(text: str) -> str:
    """Filesystem and id safe slug for ids built from spec ids."""
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "spec"


def build_brief(spec: dict, source: str,
                design_constraints: tuple = (),
                target: str = None, disease: str = None) -> dict:
    """Build a design brief from a locked consensus spec.

    Raises ValueError when the spec is not locked: no design work
    starts from a killed, parked, or unresolved target. Evidence
    constraints are the spec's surviving load-bearing claims, carried
    by claim id so candidates can be checked against them.

    The target comes from the spec's focus_id (the field debate-locked
    specs actually carry); the spec records no disease, so disease is
    taken from the operator's override when given and otherwise left
    empty rather than guessed.
    """
    if not isinstance(spec, dict) or spec.get("artifact_type") != "consensus_spec":
        raise ValueError("design requires a consensus_spec artifact")
    if spec.get("outcome") != "locked":
        raise ValueError(
            "design requires a locked spec; this spec's outcome is "
            + repr(spec.get("outcome")))
    evidence = []
    for c in spec.get("claims", []):
        if c.get("load_bearing"):
            evidence.append({
                "claim_id": c.get("claim_id"),
                "text": c.get("text"),
                "evidence_tier": c.get("evidence_tier"),
            })
    focus = spec.get("focus")
    if isinstance(focus, dict):
        focus_label = focus.get("label") or focus.get("focus_id") or ""
    else:
        focus_label = spec.get("focus_id") or ""
    brief = {
        "artifact_type": "design_brief",
        "schema_version": "0.1.0",
        "brief_id": "brief-" + _slug(spec.get("spec_id", "spec")),
        "spec_id": spec.get("spec_id"),
        "target": target or focus_label,
        "disease": disease or spec.get("disease_context") or spec.get("disease") or "",
        "question": ("Design candidates against " + (target or focus_label or "the locked target")
                     + " consistent with the surviving evidence."),
        "evidence_constraints": evidence,
        "design_constraints": [str(c) for c in design_constraints],
        "source": source,
    }
    errors = schemas.validate_artifact("design_brief", brief)
    if errors:
        raise ValueError("built brief failed its schema: "
                         + "; ".join(e["path"] + ": " + e["message"] for e in errors))
    return brief


class MockDesigner:
    """Deterministic synthetic designer: pipeline exercise only.

    Returns two labelled synthetic candidates with no structure, no
    claims, and no evaluated constraints. It exists so the design
    pipeline, audit, ranking, and reporting can be verified without a
    real design tool, and it must never be presented as a designer of
    actual candidates.
    """

    name = "mock"

    def design(self, brief: dict) -> list[dict]:
        """Return the two fixed synthetic candidates for a brief.

        Every list and dict is built fresh per candidate: an earlier
        version shallow-copied a shared base dict, so both candidates
        held the same constraint_results and predicted_properties list
        objects and mutating one mutated the other.
        """
        out = []
        for suffix, modality in (("a", "small_molecule"), ("b", "biologic")):
            out.append({
                "artifact_type": "candidate",
                "schema_version": "0.1.0",
                "candidate_id": brief["brief_id"] + "-" + suffix,
                "spec_id": brief["spec_id"],
                "modality": modality,
                "design_tool": "mock",
                "description": ("Synthetic " + modality.replace("_", " ")
                                + " placeholder for "
                                + (brief.get("target") or "the target") + "."),
                "claims": [],
                "structure": None,
                "structure_note": ("The mock designer invents no structures; a real "
                                   "candidate's structure comes from a recorded tool run."),
                "predicted_properties": [{
                    "name": "target_engagement",
                    "value": "unknown",
                    "basis": "designer_prediction",
                    "note": "Synthetic placeholder; not a measurement or a calculation.",
                }],
                "constraint_results": (
                    [{"constraint": c["claim_id"], "kind": "evidence", "status": "unknown",
                      "basis": "mock designer does not evaluate constraints"}
                     for c in brief.get("evidence_constraints", [])]
                    + [{"constraint": c, "kind": "design", "status": "unknown",
                        "basis": "mock designer does not evaluate constraints"}
                       for c in brief.get("design_constraints", [])]
                ),
                "_synthetic": True,
                "synthetic_notice": ("Synthetic pipeline-test candidate. Not a real "
                                     "designed molecule."),
            })
        return out


def audit_candidate(candidate: dict) -> dict:
    """Audit one candidate's claims and constraint results.

    The claim audit is the research layer's, not a weaker local copy
    (an earlier version ran only the ledger presence checks, so a
    load-bearing claim with a malformed identifier, no quote, and an
    unverified status scored as audited support). Here every claim
    goes through the document claim audit (ledger rules plus duplicate
    claim_id detection) and the citation auditor (identifier format
    and quote rules), and a claim counts toward audited_load_bearing
    only when it is error-free and claims.is_audited - counted once
    per claim_id. A load-bearing claim carrying any audit error, a
    non-object claim entry, or any constraint recorded as failed is a
    hard failure: the candidate is excluded from ranking. Predicted
    properties based on a designer prediction (rather than a recorded
    tool run) are counted as unverified, never silently treated as
    data.
    """
    reasons = []
    claim_errors = []
    raw_claims = candidate.get("claims", [])
    claims_list = [c for c in raw_claims if isinstance(c, dict)]
    if len(claims_list) != len(raw_claims):
        reasons.append("candidate carries a claim entry that is not an object")
    codes_by_id = {}
    for err in claims_mod.audit_claims(candidate)["errors"]:
        codes_by_id.setdefault(err["claim_id"], set()).add(err["code"])
    entries = citation_auditor.audit_citations(candidate)["entries"]
    for claim, entry in zip(claims_list, entries):
        codes = codes_by_id.setdefault(claim.get("claim_id"), set())
        if not entry["format"]["ok"]:
            codes.add("citation_" + entry["format"]["code"])
        for problem in entry["problems"]:
            codes.add(problem["code"])
    audited_ids = set()
    unaudited_load_bearing = 0
    for claim in claims_list:
        cid = claim.get("claim_id")
        codes = codes_by_id.get(cid, set())
        if codes:
            claim_errors.append({"claim_id": cid, "errors": sorted(codes)})
            if claim.get("load_bearing"):
                reasons.append("load-bearing claim " + str(cid)
                               + " failed audit: " + ", ".join(sorted(codes)))
        elif claim.get("load_bearing"):
            if claims_mod.is_audited(claim):
                audited_ids.add(cid)
            else:
                unaudited_load_bearing += 1
    unverified = 0
    for prop in candidate.get("predicted_properties", []):
        if isinstance(prop, dict) and prop.get("basis") == "designer_prediction":
            unverified += 1
    failed_constraints = []
    unknown_constraints = 0
    for cr in candidate.get("constraint_results", []):
        if not isinstance(cr, dict):
            continue
        if cr.get("status") == "fail":
            failed_constraints.append(cr.get("constraint"))
            reasons.append("constraint failed: " + str(cr.get("constraint")))
        elif cr.get("status") == "unknown":
            unknown_constraints += 1
    errors = schemas.validate_artifact("candidate", candidate)
    if errors:
        reasons.append("candidate failed its schema: "
                       + "; ".join(e["path"] + ": " + e["message"] for e in errors))
    return {
        "candidate_id": candidate.get("candidate_id"),
        "claim_errors": claim_errors,
        "audited_load_bearing": len(audited_ids),
        "unaudited_load_bearing": unaudited_load_bearing,
        "unverified_predictions": unverified,
        "failed_constraints": failed_constraints,
        "unknown_constraints": unknown_constraints,
        "hard_fail": bool(reasons),
        "reasons": reasons,
    }


def rank_candidates(candidates: list[dict], audits: list[dict]) -> dict:
    """Apply the fixed ranking rule from docs/PHASE2_SPEC.md.

    Hard-failed candidates are excluded with reasons. The rest sort by
    audited load-bearing claim count descending, then fewer unknown
    constraints, then candidate id, so the ranking is reproducible.
    """
    by_id = {a["candidate_id"]: a for a in audits}
    ranked, excluded = [], []
    for cand in candidates:
        audit = by_id.get(cand.get("candidate_id"))
        if audit and audit["hard_fail"]:
            excluded.append({"candidate_id": cand.get("candidate_id"),
                             "reasons": audit["reasons"]})
        else:
            ranked.append(cand.get("candidate_id"))
    ranked.sort(key=lambda cid: (
        -(by_id.get(cid) or {}).get("audited_load_bearing", 0),
        (by_id.get(cid) or {}).get("unknown_constraints", 0),
        str(cid)))
    return {"ranked": ranked, "excluded": excluded}


def run_design(spec: dict, source: str, designer=None,
               design_constraints: tuple = (), tool_runs: tuple = (),
               extra_candidates: tuple = (),
               target: str = None, disease: str = None) -> dict:
    """Run the design stage for a locked spec and freeze the bundle.

    The gate passes only when the brief came from a locked spec (which
    build_brief enforces), at least one candidate is ranked, at least
    one ranked candidate is real (not a synthetic mock or fixture), no
    tool run in the bundle was license-blocked, and every requested
    tool run completed. A mock-only run therefore fails the gate while
    still recording its ranked placeholders: the pipeline exercised is
    not a design result.
    """
    brief = build_brief(spec, source, design_constraints,
                        target=target, disease=disease)
    designer = designer or MockDesigner()
    candidates = list(designer.design(brief)) + list(extra_candidates)
    candidate_ids = [c.get("candidate_id") for c in candidates]
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("duplicate candidate_id in one design run: "
                         + ", ".join(str(x) for x in candidate_ids
                                     if candidate_ids.count(x) > 1)
                         + "; audits and ranking are keyed by candidate_id, "
                           "so duplicates would silently merge two candidates")
    audits = [audit_candidate(c) for c in candidates]
    ranking = rank_candidates(candidates, audits)
    blocked_tools = [t for t in tool_runs if t.get("status") == "blocked_license"]
    by_id = {c.get("candidate_id"): c for c in candidates}
    real_ranked = [cid for cid in ranking["ranked"]
                   if not (by_id.get(cid) or {}).get("_synthetic")]
    checks = [
        {"name": "spec_locked", "status": "pass",
         "detail": "brief built from locked spec " + str(spec.get("spec_id"))},
        {"name": "candidates_ranked",
         "status": "pass" if ranking["ranked"] else "fail",
         "detail": str(len(ranking["ranked"])) + " ranked, "
         + str(len(ranking["excluded"])) + " excluded"},
        {"name": "real_candidates_ranked",
         "status": "pass" if real_ranked else "fail",
         "detail": (str(len(real_ranked)) + " non-synthetic candidates ranked")
         if real_ranked else ("every ranked candidate is synthetic (the mock "
                             "designer or a labelled fixture): the pipeline ran, "
                             "but no real candidate exists, so the gate cannot pass")},
        {"name": "tools_license_clean",
         "status": "fail" if blocked_tools else "pass",
         "detail": ("blocked tool attempts: "
                    + ", ".join(t.get("tool", "?") for t in blocked_tools))
         if blocked_tools else "no blocked tool runs"},
    ]
    if tool_runs:
        completed = [t for t in tool_runs if t.get("status") == "completed"]
        checks.append(
            {"name": "requested_tools_produced",
             "status": "pass" if completed else "fail",
             "detail": (str(len(completed)) + " of " + str(len(tool_runs))
                        + " requested tool runs completed")
             if completed else ("tool runs were requested and none completed: "
                                + ", ".join(str(t.get("tool")) + "=" + str(t.get("status"))
                                            for t in tool_runs))})
    result = "pass" if all(c["status"] == "pass" for c in checks) else "fail"
    run_id = "design-" + _slug(spec.get("spec_id", "spec"))
    bundle = {
        "kind": "design_run",
        "run_id": run_id,
        "outcome": result,
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "designer": getattr(designer, "name", "unknown"),
        "brief": brief,
        "candidates": candidates,
        "audits": audits,
        "ranking": ranking,
        "tool_runs": list(tool_runs),
        "gate_report": {
            "artifact_type": "gate_report",
            "schema_version": "0.1.0",
            "gate_id": run_id,
            "gate_name": "phase2-design",
            "subject_id": spec.get("spec_id"),
            "result": result,
            "checks": checks,
        },
    }
    bundle["frozen_bundle"] = freeze_artifact(
        {k: v for k, v in bundle.items() if k != "frozen_bundle"})
    return bundle
