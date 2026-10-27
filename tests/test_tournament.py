"""Tests for the tournament: Elo math, judged matches between
cluster representatives, failure discipline (a broken judge
changes no rating), the advisory boundary (ratings never move
an outcome), and the config builder. Offline, stub judges."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.config import tournament_judge_from_config
from madd.debate import run_debate
from madd.tournament import (compare_proposals, run_tournament,
                             update_elo)
from tests.test_debate import FRAME, StubProvider, dossier, good_claim


def test_elo_math():
    """Equal ratings: a win moves the winner up 16 and the loser
    down 16 at K=32; a tie between equals changes nothing; an
    underdog win moves more than a favorite win."""
    won_a, lost_b = update_elo(1500.0, 1500.0, 1.0)
    assert (won_a, lost_b) == (1516.0, 1484.0)
    tie_a, tie_b = update_elo(1500.0, 1500.0, 0.5)
    assert (tie_a, tie_b) == (1500.0, 1500.0)
    dog_a, fav_b = update_elo(1400.0, 1600.0, 1.0)
    assert dog_a - 1400.0 > 16.0 and 1600.0 - fav_b > 16.0


class WinnerJudge:
    """A judge provider that always crowns proposal A."""

    name = "winner-judge"
    model_version = "winner-judge-v1"
    cost_per_call_usd = 0.0

    def complete(self, system, user):
        """Answer that proposal A wins."""
        return '{"winner": "a"}'


def test_compare_proposals_failures_are_unverifiable():
    """A raising judge and an unparseable answer both judge
    nothing."""
    summary = {"focus_id": "F", "direction": "advance", "size": 1,
               "focus_score": 1.0, "struck_count": 0,
               "claim_texts": ["one claim"]}
    assert compare_proposals(summary, summary, WinnerJudge()) == "a"

    class BrokenJudge:
        """A judge whose completion raises."""

        def complete(self, system, user):
            """Raise like a dead provider."""
            raise RuntimeError("down")

    class JunkJudge:
        """A judge answering prose instead of the verdict JSON."""

        def complete(self, system, user):
            """Return unparseable text."""
            return "proposal A seemed nicer overall"

    assert compare_proposals(summary, summary, BrokenJudge()) \
        == "unverifiable"
    assert compare_proposals(summary, summary, JunkJudge()) \
        == "unverifiable"


def clusters_and_audited():
    """Two clusters over three dossiers in the shapes the
    tournament consumes."""
    audited = [
        {"dossier_id": "D1", "agent_id": "a1",
         "proposed_focus_id": "F1", "direction": "advance",
         "surviving_claims": [good_claim("C1")], "struck": []},
        {"dossier_id": "D2", "agent_id": "a2",
         "proposed_focus_id": "F2", "direction": "advance",
         "surviving_claims": [good_claim("C2")], "struck": []},
        {"dossier_id": "D3", "agent_id": "a3",
         "proposed_focus_id": "F2", "direction": "advance",
         "surviving_claims": [good_claim("C3")], "struck": []},
    ]
    clusters = [
        {"cluster_id": "CL-1", "focus_id": "F1", "direction": "advance",
         "representative_dossier_id": "D1", "dossier_ids": ["D1"],
         "agent_ids": ["a1"], "size": 1, "near_duplicate": False,
         "merge_basis": [], "shared_sources": []},
        {"cluster_id": "CL-2", "focus_id": "F2", "direction": "advance",
         "representative_dossier_id": "D2", "dossier_ids": ["D2", "D3"],
         "agent_ids": ["a2", "a3"], "size": 2, "near_duplicate": True,
         "merge_basis": ["same_focus"], "shared_sources": ["pmid:1"]},
    ]
    ranking = [{"dossier_id": "D1", "focus_score": 2.0, "struck_count": 0},
               {"dossier_id": "D2", "focus_score": 1.0, "struck_count": 0},
               {"dossier_id": "D3", "focus_score": 1.0, "struck_count": 0}]
    return clusters, audited, ranking


def test_run_tournament_ratings_and_records():
    """A full round-robin: representatives only (two clusters,
    one match however many dossiers each holds), ratings and
    match records accumulate, unverifiable matches change no
    rating, and the cap is honored and recorded."""
    clusters, audited, ranking = clusters_and_audited()
    out = run_tournament(clusters, audited, ranking,
                         lambda a, b: "a")
    assert len(out["matches"]) == 1
    top = out["ratings"][0]
    assert top["cluster_id"] == "CL-1" and top["rating"] == 1516.0
    assert top["wins"] == 1
    assert out["ratings"][1]["losses"] == 1
    assert out["matches_skipped"] == 0
    assert "advisory" in out["note"]

    out = run_tournament(clusters, audited, ranking,
                         lambda a, b: "unverifiable")
    assert all(row["rating"] == 1500.0 for row in out["ratings"])
    assert out["matches"][0]["result"] == "unverifiable"

    out = run_tournament(clusters, audited, ranking,
                         lambda a, b: "tie", max_matches=0)
    assert out["matches"] == [] and out["matches_skipped"] == 1


def test_config_builder():
    """Off means no comparator; on without a judge is a config
    error; on with a judge yields match verdicts."""
    assert tournament_judge_from_config({}) is None
    try:
        tournament_judge_from_config({"tournament": True})
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    comparator = tournament_judge_from_config(
        {"tournament": True, "judge": WinnerJudge()})
    summary = {"focus_id": "F", "direction": "advance", "size": 1,
               "focus_score": 1.0, "struck_count": 0,
               "claim_texts": ["one claim"]}
    assert comparator(summary, summary) == "a"


def test_debate_tournament_is_advisory_only():
    """End to end: a split panel plays a tournament and records
    ratings, and the debate outcome is exactly what the same
    panel produces with no tournament judge."""
    def claim_on(cid, pmid):
        """A passing claim citing a chosen PMID, so the two
        proposals stand on different sources and cluster apart."""
        claim = good_claim(cid)
        claim["source_identifier"] = pmid
        return claim

    def panel():
        """A two-proposal panel of stub providers."""
        a = StubProvider("stub-a", dossier(
            "D-A", "agent-a", "FOCUS-A", [claim_on("C-A1", "11111111")]))
        b = StubProvider("stub-b", dossier(
            "D-B", "agent-b", "FOCUS-B", [claim_on("C-B1", "22222222")]))
        judge = StubProvider("stub-judge", dossier(
            "D-J", "agent-j", "FOCUS-A", [good_claim("C-J1")]))
        return a, b, judge

    a, b, judge = panel()
    plain = run_debate(FRAME, [a, b], judge_provider=judge)
    a, b, judge = panel()
    rated = run_debate(FRAME, [a, b], judge_provider=judge,
                       tournament_judge=lambda x, y: "a")
    assert plain["tournament"] is None
    assert rated["tournament"] is not None
    assert len(rated["tournament"]["matches"]) >= 1
    assert rated["outcome"] == plain["outcome"]
    assert rated["spec"]["claims"] == plain["spec"]["claims"]
