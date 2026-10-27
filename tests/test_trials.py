"""Tests for the trial landscape: aggregation over a stubbed
registry sample, totals from the registry's own count, focus
term counting, and failure marking sections unavailable
rather than zero."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.trials import landscape


def study(nct, status, phases, title="A study", sponsor="Sponsor",
          start="2026-01-15", interventions=("Drug A",)):
    """One registry-shaped study record."""
    return {"protocolSection": {
        "identificationModule": {"nctId": nct, "briefTitle": title},
        "statusModule": {"overallStatus": status,
                         "startDateStruct": {"date": start}},
        "designModule": {"phases": phases},
        "sponsorCollaboratorsModule": {
            "leadSponsor": {"name": sponsor}},
        "armsInterventionsModule": {
            "interventions": [{"name": name, "type": "DRUG"}
                              for name in interventions]},
    }}


SAMPLE = [study("NCT001", "RECRUITING", ["PHASE2"], "Newer study",
                start="2026-03-01"),
          study("NCT002", "COMPLETED", ["PHASE3"], "Older study",
                start="2024-06-01"),
          study("NCT003", "RECRUITING", ["PHASE1", "PHASE2"],
                "Early study", start="2025-09-10")]


def transport(url):
    """Answer registry queries from the fixtures: focus
    queries carry query.intr, totals carry pageSize=0."""
    if "query.intr" in url:
        return 200, {"totalCount": 2, "studies": SAMPLE[:2]}
    if "pageSize=0" in url:
        return 200, {"totalCount": 4321}
    return 200, {"studies": SAMPLE}


def test_landscape_aggregates_the_registry():
    """Totals come from the registry count; phase and status
    breakdowns count the sample; recent studies keep their
    NCT identifiers."""
    report = landscape("obesity", focus_terms=["evolocumab"],
                       queried_on="2026-10-27", transport=transport)
    assert report["total_trials"] == 4321
    assert report["sample"]["by_phase"] == {
        "PHASE2": 2, "PHASE3": 1, "PHASE1": 1}
    assert report["sample"]["by_status"] == {
        "RECRUITING": 2, "COMPLETED": 1}
    assert report["recent"][0]["nct_id"] == "NCT001"
    focus = report["focus"][0]
    assert focus["trials"] == 2 and len(focus["recent"]) == 2
    assert report["queried_on"] == "2026-10-27"


def test_target_run_bundle_carries_the_landscape(monkeypatch):
    """Every target run's bundle gains the landscape section
    for its disease, and a landscape failure marks the section
    unavailable without failing the run. The debate plumbing
    itself is covered by the target-run suite; here the
    landscape function is stubbed at its seam."""
    import madd.trials
    from madd.target_run import build_target_frame, run_target
    from tests.test_target_run import _panel, _StubDesigner

    monkeypatch.setattr(
        madd.trials, "landscape",
        lambda disease, focus_terms=(), queried_on=None, **kw: {
            "artifact_type": "trial_landscape", "disease": disease,
            "total_trials": 3, "focus": []})
    frame = build_target_frame("KRAS G12C", "target",
                               disease="lung cancer")
    bundle = run_target(frame, _panel(frame),
                        designer=_StubDesigner(), mode="simple")
    section = bundle["trial_landscape"]
    assert section["disease"] == "lung cancer"
    assert section["total_trials"] == 3

    def boom(*args, **kwargs):
        """Raise like a dead registry."""
        raise RuntimeError("registry down")

    monkeypatch.setattr(madd.trials, "landscape", boom)
    bundle = run_target(frame, _panel(frame),
                        designer=_StubDesigner(), mode="simple")
    assert bundle["trial_landscape"]["status"] == "unavailable"
    assert bundle["outcome"] in ("designed", "no_go",
                                  "design_gate_failed")


def test_landscape_failure_is_unavailable_not_zero():
    """A dead registry leaves totals None and focus sections
    unavailable, never a fabricated zero."""
    def dead(url):
        """Fail every request."""
        return 503, None

    report = landscape("obesity", focus_terms=["x"],
                       transport=dead)
    assert report["total_trials"] is None
    assert report["sample"] is None
    assert report["focus"][0]["status"] == "unavailable"
