"""Tests for proposal clustering: the merge rules (same focus,
source overlap, direction never merged across), representative
and ordering, and the debate record's clusters. Deterministic,
offline."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.clustering import cluster_dossiers, cluster_id_by_dossier
from madd.debate import run_debate
from tests.test_debate import (FRAME, StubProvider, agreeing_providers,
                               dossier, good_claim)


def audited(dossier_id, agent, focus, direction, idents):
    """One audited-dossier-shaped dict citing the given PMIDs."""
    return {"dossier_id": dossier_id, "agent_id": agent,
            "proposed_focus_id": focus, "direction": direction,
            "surviving_claims": [
                {"claim_id": dossier_id + "-" + str(i),
                 "text": "claim " + str(i), "load_bearing": True,
                 "source_identifier": ident, "identifier_type": "pmid"}
                for i, ident in enumerate(idents)],
            "struck": []}


def test_same_focus_same_direction_merges():
    """Two dossiers proposing the same focus in the same
    direction are one cluster, with the shared source recorded."""
    a = audited("D1", "a1", "F1", "advance", ["111"])
    b = audited("D2", "a2", "F1", "advance", ["111", "222"])
    clusters = cluster_dossiers([a, b])
    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster["cluster_id"] == "CL-1"
    assert cluster["size"] == 2 and cluster["near_duplicate"]
    assert cluster["merge_basis"] == ["same_focus"]
    assert cluster["shared_sources"] == ["pmid:111"]
    assert cluster["representative_dossier_id"] == "D1"


def test_direction_never_merges():
    """Advancing and killing the same focus are opposing
    proposals and stay separate clusters."""
    a = audited("D1", "a1", "F1", "advance", ["111"])
    b = audited("D2", "a2", "F1", "kill", ["111"])
    clusters = cluster_dossiers([a, b])
    assert len(clusters) == 2
    assert all(not c["near_duplicate"] for c in clusters)


def test_source_overlap_merges_different_labels():
    """Different focus labels standing on substantially the
    same sources (Jaccard at least 0.5) merge as near-duplicates;
    below the threshold they do not."""
    a = audited("D1", "a1", "F1", "advance", ["1", "2", "3"])
    b = audited("D2", "a2", "F2", "advance", ["1", "2", "3", "4", "5"])
    clusters = cluster_dossiers([a, b])
    assert len(clusters) == 1
    assert clusters[0]["merge_basis"] == ["source_overlap"]
    thin = audited("D3", "a3", "F3", "advance", ["1", "9"])
    clusters = cluster_dossiers([a, thin])
    assert len(clusters) == 2


def test_ranking_sets_representative_and_order():
    """With a ranking, the top-ranked member represents the
    cluster and clusters are ordered by representative rank."""
    a = audited("D1", "a1", "F1", "advance", ["111"])
    b = audited("D2", "a2", "F1", "advance", ["111"])
    c = audited("D3", "a3", "F2", "advance", ["999"])
    ranking = [{"dossier_id": "D3"}, {"dossier_id": "D2"},
               {"dossier_id": "D1"}]
    clusters = cluster_dossiers([a, b, c], ranking)
    assert clusters[0]["representative_dossier_id"] == "D3"
    assert clusters[1]["representative_dossier_id"] == "D2"
    assert clusters[1]["dossier_ids"] == ["D2", "D1"]
    mapping = cluster_id_by_dossier(clusters)
    assert mapping["D1"] == mapping["D2"] != mapping["D3"]


def test_debate_record_carries_clusters():
    """A debate of agreeing providers records one cluster of
    both dossiers, and the ranking entries name their cluster;
    a split panel records one cluster per proposal."""
    a, b = agreeing_providers()
    record = run_debate(FRAME, [a, b])
    assert len(record["clusters"]) == 1
    assert record["clusters"][0]["size"] == 2
    assert all(s["cluster_id"] == "CL-1" for s in record["ranking"])

    a2 = StubProvider("stub-a", dossier("D-A", "agent-a", "FOCUS-A",
                                        [good_claim("C-A1")]))
    b2 = StubProvider("stub-b", dossier("D-B", "agent-b", "FOCUS-B",
                                        [good_claim("C-B1")]))
    record2 = run_debate(FRAME, [a2, b2])
    # Different focuses but the same single source: the overlap
    # rule (1 of 1 shared) merges them, which the record shows.
    assert len(record2["clusters"]) == 1
    assert record2["clusters"][0]["merge_basis"] == ["source_overlap"]
