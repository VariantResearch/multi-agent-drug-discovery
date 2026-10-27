"""Tests for the meta-review: deterministic signals, strict
finding validation, the unavailable-not-fabricated failure
rule, the config builder, and the advisory boundary in a full
debate. Offline, stub reviewers."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.config import meta_reviewer_from_config
from madd.debate import run_debate
from madd.meta_review import compute_signals, review_run
from tests.test_debate import (FRAME, StubProvider, agreeing_providers,
                               dossier, good_claim)


def fake_audited():
    """Two audited dossiers: one clean, one heavily struck."""
    return [
        {"dossier_id": "D1", "agent_id": "a1",
         "surviving_claims": [
             {"claim_id": "c1", "load_bearing": True,
              "source_identifier": "111", "identifier_type": "pmid"},
             {"claim_id": "c2", "load_bearing": True,
              "source_identifier": "111", "identifier_type": "pmid"}],
         "struck": [{"claim_id": "s1"}]},
        {"dossier_id": "D2", "agent_id": "a2",
         "surviving_claims": [
             {"claim_id": "c3", "load_bearing": True,
              "source_identifier": "222", "identifier_type": "pmid"}],
         "struck": [{"claim_id": "s2"}, {"claim_id": "s3"},
                    {"claim_id": "s4"}]},
    ]


def test_compute_signals():
    """Signals are the record's facts: counts, shares, the
    divergence flag, and the failed consensus tests."""
    signals = compute_signals(
        fake_audited(), [], [{"x": 1}],
        [{"cluster_id": "CL-1", "size": 2}],
        {"ratings": [{"cluster_id": "CL-9"}]},
        [{"cluster_id": "CL-1"}],
        {"all_passed": False,
         "results": [{"test": "agreement", "passed": False},
                     {"test": "survival", "passed": True},
                     {"test": "stability", "passed": False,
                      "status": "not_evaluable"}]},
        "no_go", True)
    assert signals["surviving_load_bearing_claims"] == 3
    assert signals["distinct_sources_surviving"] == 2
    assert signals["strikes_total"] == 4
    assert signals["top_agent_strike_share"] == 0.75
    assert signals["disputes"] == 1
    assert signals["largest_cluster_share"] == 1.0
    assert signals["preference_divergence"] is True
    assert signals["failed_consensus_tests"] == ["agreement"]


class ReviewerStub:
    """A reviewer provider answering a fixed payload."""

    name = "reviewer-stub"
    model_version = "reviewer-stub-v1"
    cost_per_call_usd = 0.0

    def __init__(self, payload):
        """Store the payload to answer with."""
        self.payload = payload

    def complete(self, system, user):
        """Return the payload as JSON text."""
        return self.payload


def test_review_run_parsing_and_validation():
    """Valid findings pass; findings outside the vocabularies
    are dropped; an empty findings list is a completed review,
    not a failure."""
    payload = json.dumps({
        "findings": [
            {"pattern": "thin_evidence", "severity": "concern",
             "detail": "3 surviving claims across 2 dossiers."},
            {"pattern": "invented_pattern", "severity": "serious",
             "detail": "this entry must be dropped"},
            {"pattern": "thin_evidence", "severity": "extreme",
             "detail": "bad severity, dropped too"}],
        "overall": "A thin run."})
    out = review_run({"outcome": "no_go"}, ReviewerStub(payload))
    assert out["status"] == "completed"
    assert len(out["findings"]) == 1
    assert out["findings"][0]["pattern"] == "thin_evidence"
    assert out["overall"] == "A thin run."

    clean = review_run({}, ReviewerStub(
        json.dumps({"findings": [], "overall": "Clean run."})))
    assert clean["status"] == "completed"
    assert clean["findings"] == []


def test_review_run_failures_are_unavailable_not_fabricated():
    """A raising reviewer and an unparseable answer both record
    unavailable with no findings."""
    class BrokenReviewer:
        """A reviewer whose completion raises."""

        def complete(self, system, user):
            """Raise like a dead provider."""
            raise RuntimeError("down")

    out = review_run({}, BrokenReviewer())
    assert out["status"] == "unavailable" and out["findings"] == []
    out = review_run({}, ReviewerStub("the run seemed fine overall"))
    assert out["status"] == "unavailable" and out["findings"] == []


def test_config_builder():
    """Off means no reviewer; on without a judge is a config
    error; on with a judge yields a completing reviewer."""
    assert meta_reviewer_from_config({}) is None
    try:
        meta_reviewer_from_config({"meta_review": True})
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    reviewer = meta_reviewer_from_config(
        {"meta_review": True, "judge": ReviewerStub(
            json.dumps({"findings": [], "overall": "ok"}))})
    assert reviewer.complete("s", "u")


def test_debate_meta_review_is_advisory():
    """End to end: the review and its signals land on the
    record, and the outcome matches the same panel unreviewed."""
    a, b = agreeing_providers()
    judge = StubProvider("stub-judge", dossier(
        "D-J", "agent-j", "FOCUS-A", [good_claim("C-J1")]))
    plain = run_debate(FRAME, [a, b], judge_provider=judge)
    a, b = agreeing_providers()
    judge = StubProvider("stub-judge", dossier(
        "D-J", "agent-j", "FOCUS-A", [good_claim("C-J1")]))
    reviewed = run_debate(
        FRAME, [a, b], judge_provider=judge,
        meta_reviewer=ReviewerStub(json.dumps({
            "findings": [{"pattern": "cluster_collapse",
                          "severity": "note",
                          "detail": "largest cluster share is 1.0"}],
            "overall": "One proposal, twice."})))
    assert plain["meta_review"] is None
    review = reviewed["meta_review"]
    assert review["status"] == "completed"
    assert review["findings"][0]["pattern"] == "cluster_collapse"
    assert review["signals"]["clusters"] == 1
    assert reviewed["outcome"] == plain["outcome"]
