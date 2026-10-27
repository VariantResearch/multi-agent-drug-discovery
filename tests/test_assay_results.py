"""Tests for assay results ingestion: grading against the
plan's checks as written, not_reported never counting as met,
advance/revise/retire per the plan's decision rule, and
unplanned or outstanding candidates named rather than dropped.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.assay import plan_assays
from madd.assay_results import grade_results
from madd.design import run_design
from tests.test_design import locked_spec


def small_molecule_plan():
    """A plan over a real design run, narrowed to one small
    molecule candidate for precise grading."""
    bundle = run_design(locked_spec(), "test")
    plan = plan_assays(bundle, top_n=10)
    plan["candidates"] = [c for c in plan["candidates"]
                          if c["modality"] == "small_molecule"][:1]
    assert plan["candidates"], "fixture needs a small molecule"
    return plan


def results_for(plan, measurements, plan_id=None):
    """A results file for the plan's first candidate."""
    return {"plan_id": plan["plan_id"] if plan_id is None else plan_id,
            "results": [{"candidate_id":
                         plan["candidates"][0]["candidate_id"],
                         "measurements": measurements}]}


GOOD = {"z_prime": 0.72, "curve_r2": 0.97, "ic50_um": 1.8,
        "counterscreen_clean": True}


def test_advance_when_all_criteria_met():
    """Every check met, including the hit call: advance."""
    plan = small_molecule_plan()
    report = grade_results(plan, results_for(plan, GOOD))
    graded = report["graded"][0]
    assert graded["recommendation"] == "advance"
    assert report["summary"]["advance"] == 1
    assert report["plan_id_match"] is True


def test_retire_on_failed_hit_call():
    """An IC50 above the plan's threshold fails the hit call:
    retire, per the plan's decision rule."""
    plan = small_molecule_plan()
    weak = dict(GOOD, ic50_um=42.0)
    report = grade_results(plan, results_for(plan, weak))
    graded = report["graded"][0]
    assert graded["recommendation"] == "retire"
    hit = [v for v in graded["verdicts"]
           if v["criterion"] == "hit call"][0]
    assert hit["status"] == "not_met"


def test_missing_measurement_is_not_reported_never_met():
    """A criterion with no measurement is not_reported and the
    recommendation is revise naming the gap."""
    plan = small_molecule_plan()
    partial = {"ic50_um": 1.8, "counterscreen_clean": True}
    report = grade_results(plan, results_for(plan, partial))
    graded = report["graded"][0]
    assert graded["recommendation"] == "revise"
    statuses = {v["criterion"]: v["status"] for v in graded["verdicts"]}
    assert statuses["plate quality"] == "not_reported"
    assert "plate quality" in graded["next_step"]


def test_unplanned_and_outstanding_are_named():
    """Results for an unplanned candidate are flagged, not
    graded; a planned candidate with no results is
    outstanding."""
    plan = small_molecule_plan()
    results = results_for(plan, GOOD)
    results["results"].append({"candidate_id": "mystery-1",
                                "measurements": GOOD})
    report = grade_results(plan, results)
    assert report["unplanned_candidates"] == ["mystery-1"]
    empty = grade_results(plan, {"plan_id": plan["plan_id"],
                                 "results": []})
    assert empty["summary"]["outstanding"] == 1
    assert empty["graded"] == []


def test_plan_id_mismatch_is_recorded():
    """A results file naming a different plan is graded
    against the given plan with the mismatch on the record."""
    plan = small_molecule_plan()
    report = grade_results(plan, results_for(plan, GOOD,
                                             plan_id="other-plan"))
    assert report["plan_id_match"] is False
    assert report["graded"][0]["recommendation"] == "advance"
