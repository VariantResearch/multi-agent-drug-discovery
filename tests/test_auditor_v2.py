"""Auditor v2 tests: retraction strikes, entailment verdicts, and the
retrieval-first rule. All offline with stub registries and judges."""
import copy
import json

from madd import cli, entailment, resolve, retrieval
from madd.debate import audit_dossier, frame_identifier_set, run_debate
from tests.test_debate import FRAME, StubProvider, dossier, good_claim


def _claim(cid, ident="12345678", itype="pmid", **kw):
    claim = {"claim_id": cid, "text": "a claim", "load_bearing": True,
             "evidence_tier": 2, "source_kind": "journal_article",
             "source_identifier": ident, "identifier_type": itype,
             "verification_status": "quote_checked",
             "supporting_quote": "the passage"}
    claim.update(kw)
    return claim


def _dossier(claims):
    return {"dossier_id": "D1", "agent_id": "a", "proposed_focus_id": "T",
            "direction": "advance", "claims": claims}


# --- retraction -------------------------------------------------------

def test_crossref_retraction_is_flagged_on_resolution():
    def fetch(url):
        return 200, json.dumps({"message": {
            "title": ["A retracted finding"],
            "update-to": [{"type": "retraction", "DOI": "10.1000/notice"}]}})
    result = resolve.resolve_identifier("10.1000/xyz", "doi", fetcher=fetch)
    assert result["status"] == "resolved"
    assert result["retracted"] is True


def test_cli_resolver_maps_retracted_for_the_evidence_call(monkeypatch):
    monkeypatch.setattr(cli, "resolve_identifier",
                        lambda i, t: {"status": "resolved", "retracted": True})
    resolver = cli._resolver_from_config({"live_resolution": True})
    assert resolver("10.1000/xyz", "doi") == "retracted"


def test_evidence_call_strikes_retracted_citations():
    audited = audit_dossier(_dossier([_claim("C1")]),
                            resolver=lambda i, t: "retracted")
    assert audited["struck"][0]["reasons"] == ["citation_retracted_live"]
    assert audited["surviving_claims"] == []


# --- entailment -------------------------------------------------------

class StubJudge:
    def __init__(self, answer):
        self._answer = answer

    def complete(self, system, user):
        return self._answer


def test_entailment_verdicts_parse_strictly():
    assert entailment.check_entailment(
        _claim("C1"), StubJudge('{"verdict": "refuted"}')) == "refuted"
    assert entailment.check_entailment(
        _claim("C1"), StubJudge('{"verdict": "supported"}')) == "supported"
    assert entailment.check_entailment(
        _claim("C1"), StubJudge('{"verdict": "partially_supported"}')) \
        == "partially_supported"
    assert entailment.check_entailment(
        _claim("C1"), StubJudge("I think it is fine")) == "unverifiable"
    assert entailment.check_entailment(
        _claim("C1"), StubJudge('{"verdict": "definitely"}')) == "unverifiable"


def test_entailment_judge_failure_is_unverifiable():
    class Down:
        def complete(self, system, user):
            raise RuntimeError("offline")
    assert entailment.check_entailment(_claim("C1"), Down()) == "unverifiable"


def test_evidence_call_strikes_only_refuted_claims():
    refuted = audit_dossier(_dossier([_claim("C1")]),
                            entailment_checker=lambda c: "refuted")
    assert refuted["struck"][0]["reasons"] == ["claim_refuted_by_its_quote"]
    partial = audit_dossier(_dossier([_claim("C1")]),
                            entailment_checker=lambda c: "partially_supported")
    assert len(partial["surviving_claims"]) == 1


# --- retrieval-first ----------------------------------------------------

def test_allowed_identifiers_strike_outside_citations():
    allowed = {("pmid", "16554528")}
    inside = _claim("C1", ident="16554528")
    outside = _claim("C2", ident="99999999")
    audited = audit_dossier(_dossier([inside, outside]),
                            allowed_identifiers=allowed)
    assert [c["claim_id"] for c in audited["surviving_claims"]] == ["C1"]
    assert audited["struck"][0]["reasons"] == ["citation_not_in_evidence"]


def test_frame_identifier_set_reads_packs_and_evidence():
    frame = {"case_pack": {"claims": [{"source_identifier": "16554528",
                                       "identifier_type": "pmid"}]},
             "evidence": [{"identifier": "10.1000/x", "type": "doi"}]}
    assert frame_identifier_set(frame) == {("pmid", "16554528"),
                                           ("doi", "10.1000/x")}
    assert frame_identifier_set({"frame_id": "F"}) is None


def test_retrieval_normalizes_records():
    records = [{"pmid": "111", "source": "MED", "title": "Paper"},
               {"id": "PPR999", "source": "PPR", "title": "Preprint"},
               {"doi": "10.1000/only", "source": "MED", "title": "DOI only"},
               {"title": "No identifier at all"}]
    entries = retrieval.evidence_from_records(records)
    assert [(e["identifier_type"], e["source_identifier"]) for e in entries] == [
        ("pmid", "111"), ("preprint", "PPR999"), ("doi", "10.1000/only")]


def test_retrieve_evidence_uses_frame_terms():
    def fetch(url):
        assert "PCSK9" in url
        return 200, json.dumps({"resultList": {"result": [
            {"pmid": "16554528", "source": "MED", "title": "PCSK9 paper"}]}})
    entries = retrieval.retrieve_evidence(
        {"target": "PCSK9", "disease": "cardiovascular disease"}, fetcher=fetch)
    assert entries[0]["source_identifier"] == "16554528"


def test_run_debate_retrieval_first_blocks_memory_citations():
    frame = copy.deepcopy(FRAME)
    frame["case_pack"] = {"claims": [{"source_identifier": "16554528",
                                      "identifier_type": "pmid"}]}
    inside_claim = good_claim("C-IN")
    inside_claim["source_identifier"] = "16554528"
    a = StubProvider("stub-a", dossier("D-A", "agent-a", "FOCUS-A", [inside_claim]))
    outside_claim = good_claim("C-OUT")  # cites 12345678, not in the pack
    b = StubProvider("stub-b", dossier("D-B", "agent-b", "FOCUS-A", [outside_claim]))
    record = run_debate(frame, [a, b], retrieval_first=True)
    struck_ids = {entry["claim_id"] for entry in record["strike_list"]}
    assert "C-OUT" in struck_ids
    assert "C-IN" not in struck_ids
