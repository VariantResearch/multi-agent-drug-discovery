"""Tests for the target scout and its ChEMBL client: stubbed
transports for both public APIs, ranking by the association
score as reported, the mechanical whitespace labels,
unresolved targets recorded rather than dropped, and ChEMBL
counts reported as the API reports them (None, never zero,
on failure)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.chembl import target_signals
from madd.scout import scout_targets, whitespace_read

OT_DATA = {
    "obesity": {"id": "MONDO_0011122", "name": "obesity"},
    "mtch2": {"id": "ENSG00000109971", "name": "MTCH2"},
    "pcsk9": {"id": "ENSG00000169174", "name": "PCSK9"},
}
ASSOCIATIONS = {
    "ENSG00000109971": {"score": 0.10,
                        "datatypeScores": [
                            {"id": "literature", "score": 0.81},
                            {"id": "genetic_association",
                             "score": 0.05}]},
    "ENSG00000169174": {"score": 0.62,
                        "datatypeScores": [
                            {"id": "literature", "score": 0.9},
                            {"id": "genetic_association",
                             "score": 0.7}]},
}


def ot_transport(query):
    """Answer Open Targets GraphQL from the fixtures."""
    if "search" in query:
        for key, hit in OT_DATA.items():
            if key in query.lower():
                return 200, json.dumps({"data": {"search": {
                    "hits": [hit]}}})
        return 200, json.dumps({"data": {"search": {"hits": []}}})
    for ensembl_id, assoc in ASSOCIATIONS.items():
        if ensembl_id in query:
            row = {"disease": OT_DATA["obesity"],
                   "score": assoc["score"],
                   "datatypeScores": assoc["datatypeScores"]}
            return 200, json.dumps({"data": {"target": {
                "id": ensembl_id, "approvedSymbol": "X",
                "associatedDiseases": {"rows": [row]}}}})
    return 200, json.dumps({"data": {"target": None}})


def chembl_transport(url):
    """Answer ChEMBL endpoints from the fixtures."""
    if "/target/search.json" in url:
        if "MTCH2" in url:
            return 200, {"targets": [{
                "target_chembl_id": "CHEMBL4523361",
                "pref_name": "MTCH2", "target_type": "SINGLE PROTEIN"}]}
        if "PCSK9" in url:
            return 200, {"targets": [{
                "target_chembl_id": "CHEMBL3626",
                "pref_name": "PCSK9", "target_type": "SINGLE PROTEIN"}]}
        return 200, {"targets": []}
    if "/mechanism.json" in url:
        count = 3 if "CHEMBL3626" in url else 0
        return 200, {"page_meta": {"total_count": count}}
    if "/activity.json" in url:
        count = 1200 if "CHEMBL3626" in url else 12
        return 200, {"page_meta": {"total_count": count}}
    return 404, None


def test_scout_ranks_and_labels():
    """PCSK9 outranks MTCH2 on the reported association, and
    the whitespace labels follow the fetched records: occupied
    for the target with mechanisms, open for the one without."""
    report = scout_targets("obesity", ["MTCH2", "PCSK9"],
                           ot_transport=ot_transport,
                           chembl_transport=chembl_transport)
    assert report["disease_resolved"]["id"] == "MONDO_0011122"
    first, second = report["candidates"]
    assert first["target_input"] == "PCSK9" and first["rank"] == 1
    assert first["signals"]["association_score"] == 0.62
    assert first["signals"]["known_mechanisms"] == 3
    assert "occupied" in first["whitespace"]
    assert second["signals"]["literature_score"] == 0.81
    assert "comparatively open" in second["whitespace"]
    assert second["chembl"]["chembl_id"] == "CHEMBL4523361"


def test_scout_records_unresolved_and_unassociated():
    """A target nothing resolves to is kept with its problems
    named and ranked last, not dropped."""
    report = scout_targets("obesity", ["MTCH2", "NOSUCHGENE"],
                           ot_transport=ot_transport,
                           chembl_transport=chembl_transport)
    assert report["candidates_total"] == 2
    ghost = report["candidates"][-1]
    assert ghost["target_input"] == "NOSUCHGENE"
    assert ghost["signals"]["association_score"] is None
    assert "unestablished" in ghost["whitespace"]
    assert ghost["problems"]


def test_whitespace_read_states():
    """The label is a pure function of the two fetched facts."""
    assert "unestablished" in whitespace_read(None, 0)
    assert "partial" in whitespace_read(0.5, None)
    assert "comparatively open" in whitespace_read(0.5, 0)
    assert "occupied" in whitespace_read(0.5, 2)


def test_chembl_failure_is_none_not_zero():
    """A dead ChEMBL transport yields None counts, distinctly
    from a real zero."""
    def dead(url):
        """Fail every request."""
        raise RuntimeError("down")

    signals = target_signals("MTCH2", transport=dead)
    assert signals["chembl_id"] is None
    assert signals["known_mechanisms"] is None
