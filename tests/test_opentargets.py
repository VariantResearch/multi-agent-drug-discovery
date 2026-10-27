"""Tests for the Open Targets evidence source: identifier
format, live-resolution result shapes, and frame evidence,
all on a canned GraphQL transport in the live API's shapes
(the live shapes were probed against the real API on
2026-10-26: search hits, and the Bs-filtered association for
MTCH2 x obesity disorder, MONDO_0011122)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd import opentargets
from madd.citation_auditor import check_identifier
from madd.resolve import resolve_identifier

IDENT = "ENSG00000109919:MONDO_0011122"


def canned_transport(query):
    """Answer GraphQL queries in the real API's shapes."""
    if "search" in query and '"MTCH2"' in query:
        return 200, json.dumps({"data": {"search": {"hits": [
            {"id": "ENSG00000109919", "name": "MTCH2",
             "entity": "target"},
            {"id": "ENSG00000260438", "name": "MTCH2P3",
             "entity": "target"}]}}})
    if "search" in query and '"obesity"' in query:
        return 200, json.dumps({"data": {"search": {"hits": [
            {"id": "MONDO_0011122", "name": "obesity disorder",
             "entity": "disease"}]}}})
    if "associatedDiseases" in query and "MONDO_0011122" in query:
        return 200, json.dumps({"data": {"target": {
            "id": "ENSG00000109919", "approvedSymbol": "MTCH2",
            "associatedDiseases": {"rows": [{
                "disease": {"id": "MONDO_0011122",
                            "name": "obesity disorder"},
                "score": 0.0983,
                "datatypeScores": [
                    {"id": "literature", "score": 0.8086}]}]}}}})
    if "associatedDiseases" in query:
        return 200, json.dumps({"data": {"target": {
            "id": "ENSG00000109919", "approvedSymbol": "MTCH2",
            "associatedDiseases": {"rows": []}}}})
    return 200, json.dumps({"data": {"search": {"hits": []}}})


def test_identifier_format():
    """The opentargets identifier type accepts an Ensembl:disease
    pair and rejects anything else."""
    assert check_identifier(IDENT, "opentargets")["ok"]
    assert not check_identifier("MTCH2:obesity", "opentargets")["ok"]
    assert not check_identifier("ENSG00000109919", "opentargets")["ok"]
    assert not check_identifier(IDENT, "uniprot")["ok"]


def test_resolve_association_found_and_missing():
    """A real pair resolves with its score in related; a pair
    with no association does not resolve."""
    out = opentargets.resolve_association(IDENT,
                                          transport=canned_transport)
    assert out["status"] == "resolved"
    assert out["title"].startswith("MTCH2 - obesity disorder")
    assert out["related"]["association_score"] == 0.0983
    assert out["related"]["datatype_scores"] == {"literature": 0.8086}
    miss = opentargets.resolve_association(
        "ENSG00000109919:MONDO_9999999", transport=canned_transport)
    assert miss["status"] == "not_found"


def test_resolve_through_the_resolver(monkeypatch):
    """madd.resolve routes the opentargets type to the Platform
    module rather than the GET registries: a malformed pair is
    decided by the format gate, and a well-formed pair reaches
    the Platform resolver (stubbed here, keeping the suite
    offline) and names the Platform host."""
    bad = resolve_identifier("nonsense", "opentargets")
    assert bad["status"] == "format_invalid"
    seen = {}
    original = opentargets.resolve_association

    def stub(identifier, transport=None):
        """Record the routing and answer not_found."""
        seen["identifier"] = identifier
        return original(identifier, transport=canned_transport)

    monkeypatch.setattr(opentargets, "resolve_association", stub)
    out = resolve_identifier("ENSG00000109919:MONDO_9999999",
                             "opentargets")
    assert seen["identifier"] == "ENSG00000109919:MONDO_9999999"
    assert out["status"] == "not_found"
    assert out["registry"] == "api.platform.opentargets.org"


def test_evidence_for_frame():
    """A frame with a gene target and a disease gains one
    citable association entry with the score breakdown."""
    frame = {"target": "MTCH2 (mitochondrial carrier 2)",
             "disease": "obesity", "target_name": "MTCH2"}
    entries = opentargets.evidence_for_frame(
        frame, transport=canned_transport)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["source_identifier"] == IDENT
    assert entry["identifier_type"] == "opentargets"
    assert entry["source_kind"] == "association_record"
    assert entry["association"]["score"] == 0.0983
    assert "not a primary" in entry["association"]["note"]


def test_evidence_for_frame_absent_is_empty():
    """Unresolvable frames and frames without a disease get no
    Open Targets entry: absence is reported, never padded."""
    assert opentargets.evidence_for_frame(
        {"target": "ZZZNOTAGENE", "disease": "obesity"},
        transport=canned_transport) == []
    assert opentargets.evidence_for_frame(
        {"target": "MTCH2"}, transport=canned_transport) == []
    assert opentargets.evidence_for_frame(
        {}, transport=canned_transport) == []
