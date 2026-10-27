"""Assay results ingestion: returned measurements graded
against the assay plan, as written.

The assay plan (madd/assay.py) records its acceptance criteria
before any data exists, each with a machine-checkable form:
the metric a results file reports, the comparison, and the
threshold. This module grades a results file against exactly
those checks. Nothing is re-derived, re-thresholded, or
smoothed:

- A criterion whose metric is absent from the results is
  "not_reported" - never counted as met, and the report names
  it as outstanding.
- A criterion with no check in the plan is "not_gradable"
  and is listed, not silently passed.
- Recommendations follow the plan's own decision rule:
  advance when every criterion is met; retire when the hit
  call failed or a counterscreen/viability/specificity
  criterion failed (the candidate did the wrong thing, or
  nothing, decisively); revise otherwise, with the failed or
  missing measurements named as the next step.
- Results for candidates the plan never named are recorded
  as unplanned and are not graded. Planned candidates with
  no results are recorded as outstanding. Both appear in the
  report; the loop cannot quietly drop either.
- Returned data is laboratory output supplied by the
  operator; this module grades it against the plan, it does
  not verify that the assay was run as planned.
"""
import operator

_OPS = {">=": operator.ge, "<=": operator.le,
        ">": operator.gt, "<": operator.lt, "==": operator.eq}

FAIL_RETIRE_CRITERIA = {"hit call", "viability", "specificity"}


def _run_check(check: dict, measurements: dict) -> dict:
    """Evaluate one check (with its optional 'also' companion)
    against the reported measurements."""
    parts = []
    current = check
    while current is not None:
        metric = current.get("metric")
        if metric not in measurements:
            parts.append({"metric": metric, "status": "not_reported"})
        else:
            value = measurements[metric]
            try:
                ok = bool(_OPS[current["op"]](value,
                                              current["value"]))
            except Exception:
                ok = False
            parts.append({"metric": metric,
                          "status": "met" if ok else "not_met",
                          "reported": value,
                          "threshold": current["value"],
                          "op": current["op"]})
        current = current.get("also")
    if any(p["status"] == "not_met" for p in parts):
        status = "not_met"
    elif any(p["status"] == "not_reported" for p in parts):
        status = "not_reported"
    else:
        status = "met"
    return {"status": status, "parts": parts}


def grade_candidate(plan_entry: dict, measurements: dict) -> dict:
    """Grade one planned candidate's measurements against its
    assay block's criteria."""
    block = plan_entry.get("assay_block") or {}
    verdicts = []
    for criterion in block.get("acceptance_criteria") or []:
        check = criterion.get("check")
        if check is None:
            verdicts.append({"criterion": criterion["criterion"],
                             "status": "not_gradable"})
            continue
        graded = _run_check(check, measurements)
        verdicts.append({"criterion": criterion["criterion"],
                         "status": graded["status"],
                         "parts": graded["parts"]})
    failed = [v["criterion"] for v in verdicts
              if v["status"] == "not_met"]
    missing = [v["criterion"] for v in verdicts
               if v["status"] == "not_reported"]
    if verdicts and all(v["status"] in ("met", "not_gradable")
                        for v in verdicts):
        recommendation = "advance"
        next_step = ("advance: proceed to a confirmation assay "
                     "or the next design round (lead "
                     "optimization) with this candidate")
    elif any(name in FAIL_RETIRE_CRITERIA for name in failed):
        recommendation = "retire"
        next_step = ("retire: the plan's decision rule retires "
                     "the candidate on: " + ", ".join(failed))
    else:
        recommendation = "revise"
        gaps = failed + ["not reported: " + name for name in missing]
        next_step = ("revise: repeat or complete the assay for: "
                     + ", ".join(gaps) if gaps else
                     "revise: no criterion could be graded")
    return {"candidate_id": plan_entry.get("candidate_id"),
            "modality": plan_entry.get("modality"),
            "verdicts": verdicts,
            "recommendation": recommendation,
            "next_step": next_step}


def grade_results(plan: dict, results: dict) -> dict:
    """Grade a whole results file against an assay plan.

    The results file's shape: {"plan_id": ..., "results":
    [{"candidate_id": ..., "measurements": {...}}]}. A plan_id
    mismatch is recorded, not refused: grading proceeds
    against the plan given, and the mismatch is on the record.
    """
    entries = (plan or {}).get("candidates") or []
    by_id = {str(e.get("candidate_id")): e for e in entries}
    reported = {}
    unplanned = []
    for row in (results or {}).get("results") or []:
        cid = str((row or {}).get("candidate_id"))
        if cid not in by_id:
            unplanned.append(cid)
            continue
        reported[cid] = (row or {}).get("measurements") or {}
    graded = [grade_candidate(by_id[cid], reported[cid])
              for cid in by_id if cid in reported]
    outstanding = [cid for cid in by_id if cid not in reported]
    return {
        "artifact_type": "assay_results_report",
        "schema_version": "0.1.0",
        "plan_id": (plan or {}).get("plan_id"),
        "results_plan_id": (results or {}).get("plan_id"),
        "plan_id_match": (results or {}).get("plan_id")
        == (plan or {}).get("plan_id"),
        "target": (plan or {}).get("target"),
        "graded": graded,
        "outstanding_candidates": outstanding,
        "unplanned_candidates": unplanned,
        "summary": {
            "advance": sum(1 for g in graded
                           if g["recommendation"] == "advance"),
            "revise": sum(1 for g in graded
                          if g["recommendation"] == "revise"),
            "retire": sum(1 for g in graded
                          if g["recommendation"] == "retire"),
            "outstanding": len(outstanding),
        },
        "note": ("Graded against the assay plan's criteria as "
                 "written, including their recorded thresholds. "
                 "The measurements are operator-supplied "
                 "laboratory output; grading them is not "
                 "verification that the assay was run as "
                 "planned."),
    }
