"""Sources batch tests: Europe PMC, GWAS Catalog v2, ChEMBL, PubChem,
UniProt resolution; full-text quote checking; candidate source checks.

All offline, through injectable fetchers shaped like the real API
responses probed live on 2026-10-25.
"""
import json

import pytest

from madd import design_sources, resolve
from madd.citation_auditor import check_identifier
from madd.debate import audit_dossier

XML = ("<article><front><article-title>Some Study</article-title></front>"
       "<body><p>Aspirin reduces platelet aggregation in humans.</p></body></article>")


def fake_fetch(url):
    """Fetcher stub routing by URL shape, mirroring the live APIs."""
    if "fullTextXML" in url:
        if "PMC1" in url:
            return 200, XML
        return 404, "{}"
    if "europepmc" in url and "search" in url:
        record = {"id": "111", "source": "MED", "pmid": "111",
                  "pmcid": "PMC1", "title": "Aspirin study",
                  "doi": "10.1000/test"}
        if "PMCID" in url or "EXT_ID" in url or "DOI" in url:
            return 200, json.dumps({"resultList": {"result": [record]},
                                    "hitCount": 1})
        return 200, json.dumps({"resultList": {"result": []}, "hitCount": 0})
    if "gwas" in url and "/studies/" in url:
        return 200, json.dumps({"accession_id": "GCST000854",
                                "disease_trait": {"trait": "Bipolar disorder"}})
    if "gwas" in url and "single-nucleotide-polymorphisms" in url:
        return 200, json.dumps({"rs_id": "rs3798220", "mapped_genes": ["LPA"],
                                "functional_class": "missense_variant"})
    if "chembl" in url and "molecule.json" in url:
        return 200, json.dumps({"molecules": [{"molecule_chembl_id": "CHEMBL25"}]})
    if "chembl" in url and "/molecule/" in url:
        return 200, json.dumps({"molecule_chembl_id": "CHEMBL25",
                                "pref_name": "ASPIRIN"})
    if "pubchem" in url and "inchikey" in url:
        return 200, json.dumps({"IdentifierList": {"CID": [2244]}})
    if "pubchem" in url and "/cid/" in url:
        return 200, json.dumps({"PropertyTable": {"Properties": [
            {"CID": 2244, "Title": "Aspirin"}]}})
    if "uniprot" in url:
        return 200, json.dumps({
            "primaryAccession": "P00533",
            "proteinDescription": {"recommendedName": {
                "fullName": {"value": "Epidermal growth factor receptor"}}}})
    return 404, "{}"


def test_new_identifier_formats():
    """New identifier formats."""
    for ident, itype in [("PMC7095418", "pmcid"), ("PPR123456", "preprint"),
                         ("GCST000854", "gcst"), ("rs3798220", "rsid"),
                         ("CHEMBL25", "chembl"), ("2244", "pubchem_cid"),
                         ("P00533", "uniprot")]:
        assert check_identifier(ident, itype)["ok"], (ident, itype)
    for ident, itype in [("PM7095418", "pmcid"), ("GCST", "gcst"),
                         ("rsABC", "rsid"), ("CHEMBL", "chembl"),
                         ("p00533", "uniprot")]:
        assert not check_identifier(ident, itype)["ok"], (ident, itype)


@pytest.mark.parametrize("ident,itype,title_part", [
    ("PMC7095418", "pmcid", "Aspirin study"),
    ("PPR123456", "preprint", "Aspirin study"),
    ("GCST000854", "gcst", "Bipolar disorder"),
    ("rs3798220", "rsid", "LPA"),
    ("CHEMBL25", "chembl", "ASPIRIN"),
    ("2244", "pubchem_cid", "Aspirin"),
    ("P00533", "uniprot", "Epidermal growth factor receptor"),
])
def test_new_resolvers_resolve(ident, itype, title_part):
    """New resolvers resolve."""
    result = resolve.resolve_identifier(ident, itype, fetcher=fake_fetch)
    assert result["status"] == "resolved", result
    assert title_part in (result["title"] or "")


def test_pmcid_resolution_reports_related_ids():
    """Pmcid resolution reports related ids."""
    result = resolve.resolve_identifier("PMC7095418", "pmcid", fetcher=fake_fetch)
    assert result["related"]["pmid"] == "111"
    assert result["related"]["doi"] == "10.1000/test"


def test_gwas_empty_record_is_not_found():
    """Gwas empty record is not found."""
    def empty_fetch(url):
        """Fetch double returning an empty result set."""
        return 200, json.dumps({"something_else": True})
    result = resolve.resolve_identifier("GCST999999999", "gcst", fetcher=empty_fetch)
    assert result["status"] == "not_found"


def test_quote_found_in_full_text():
    """Quote found in full text."""
    result = resolve.check_quote_against_source(
        "111", "pmid", "Aspirin reduces platelet aggregation in humans.",
        fetcher=fake_fetch)
    assert result["status"] == "quote_found"
    assert result["pmcid"] == "PMC1"


def test_quote_absent_from_retrieved_full_text_is_the_only_strike_grade():
    """Quote absent from retrieved full text is the only strike grade."""
    result = resolve.check_quote_against_source(
        "111", "pmid", "This sentence was never in the paper.",
        fetcher=fake_fetch)
    assert result["status"] == "quote_not_found"


def test_quote_found_in_abstract_when_full_text_lacks_it():
    """Quote found in abstract when full text lacks it."""
    def abstract_fetch(url):
        """Fetch double whose record abstract carries the quote while
        the deposited full text XML does not (the live REC-994 shape:
        the XML abstract section is worded differently)."""
        if "fullTextXML" in url:
            return 200, XML
        if "europepmc" in url and "search" in url:
            record = {"id": "111", "source": "MED", "pmid": "111",
                      "pmcid": "PMC1", "title": "Aspirin study",
                      "abstractText": "Background. Aspirin reduces platelet "
                                      "aggregation in humans. More text."}
            return 200, json.dumps({"resultList": {"result": [record]},
                                    "hitCount": 1})
        return 404, "{}"
    result = resolve.check_quote_against_source(
        "111", "pmid", "Aspirin reduces platelet aggregation in humans.",
        fetcher=abstract_fetch)
    assert result["status"] == "quote_found"


def test_quote_found_in_abstract_without_open_full_text():
    """Quote found in abstract without open full text."""
    def abstract_only_fetch(url):
        """Fetch double with an abstract and no PMCID at all."""
        if "europepmc" in url and "search" in url:
            record = {"id": "222", "source": "MED", "pmid": "222",
                      "title": "Paywalled study",
                      "abstractText": "Aspirin reduces platelet aggregation "
                                      "in humans."}
            return 200, json.dumps({"resultList": {"result": [record]},
                                    "hitCount": 1})
        return 404, "{}"
    result = resolve.check_quote_against_source(
        "222", "pmid", "Aspirin reduces platelet aggregation in humans.",
        fetcher=abstract_only_fetch)
    assert result["status"] == "quote_found"


def test_quote_absent_from_abstract_and_full_text_still_strikes():
    """Quote absent from abstract and full text still strikes."""
    def abstract_fetch(url):
        """Fetch double whose abstract exists but lacks the quote."""
        if "fullTextXML" in url:
            return 200, XML
        if "europepmc" in url and "search" in url:
            record = {"id": "111", "source": "MED", "pmid": "111",
                      "pmcid": "PMC1", "title": "Aspirin study",
                      "abstractText": "An abstract about something else."}
            return 200, json.dumps({"resultList": {"result": [record]},
                                    "hitCount": 1})
        return 404, "{}"
    result = resolve.check_quote_against_source(
        "111", "pmid", "This sentence was never in the paper.",
        fetcher=abstract_fetch)
    assert result["status"] == "quote_not_found"


def test_quote_check_unavailable_full_text_proves_nothing():
    """Quote check unavailable full text proves nothing."""
    def no_pmcid_fetch(url):
        """Fetch double whose records carry no PMCID."""
        if "europepmc" in url:
            return 200, json.dumps({"resultList": {"result": [
                {"pmid": "222", "title": "Paywalled study"}]}, "hitCount": 1})
        return 404, "{}"
    result = resolve.check_quote_against_source(
        "222", "pmid", "Any quote.", fetcher=no_pmcid_fetch)
    assert result["status"] == "full_text_unavailable"


def test_quote_check_not_applicable_types():
    """Quote check not applicable types."""
    result = resolve.check_quote_against_source(
        "NCT01234567", "nct", "Any quote.", fetcher=fake_fetch)
    assert result["status"] == "not_applicable"


def _quote_checked_dossier():
    """Build a dossier with one quote_checked claim."""
    return {"dossier_id": "D1", "agent_id": "a", "proposed_focus_id": "T",
            "direction": "advance",
            "claims": [{"claim_id": "C1", "text": "t", "load_bearing": True,
                        "evidence_tier": 2, "source_kind": "journal_article",
                        "source_identifier": "111", "identifier_type": "pmid",
                        "verification_status": "quote_checked",
                        "supporting_quote": "q"}]}


def test_evidence_call_strikes_only_on_quote_not_found():
    """Evidence call strikes only on quote not found."""
    struck = audit_dossier(_quote_checked_dossier(),
                           quote_checker=lambda claim: "quote_not_found")
    assert struck["struck"][0]["reasons"] == ["quote_not_in_full_text"]
    spared = audit_dossier(_quote_checked_dossier(),
                           quote_checker=lambda claim: "full_text_unavailable")
    assert len(spared["surviving_claims"]) == 1


@pytest.mark.skipif(not design_sources.design_rdkit.available(),
                    reason="RDKit not installed in this environment")
def test_candidate_source_check_finds_aspirin_known():
    """Candidate source check finds aspirin known."""
    cand = {"candidate_id": "C1",
            "structure": {"format": "smiles", "value": "CC(=O)Oc1ccccc1C(=O)O"},
            "predicted_properties": [], "constraint_results": []}
    record = design_sources.check_candidates([cand], fetcher=fake_fetch)
    assert record["status"] == "completed"
    assert record["known"] == 1
    check = cand["source_check"]
    assert check["known_compound"] is True
    assert check["pubchem_cids"] == [2244]
    assert check["chembl_ids"] == ["CHEMBL25"]
    assert check["inchikey"] == "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"


@pytest.mark.skipif(not design_sources.design_rdkit.available(),
                    reason="RDKit not installed in this environment")
def test_candidate_source_check_records_failures_honestly():
    """Candidate source check records failures honestly."""
    def down_fetch(url):
        """Fetch double that always fails."""
        raise ConnectionError("offline")
    cand = {"candidate_id": "C1",
            "structure": {"format": "smiles", "value": "CC(=O)Oc1ccccc1C(=O)O"},
            "predicted_properties": [], "constraint_results": []}
    record = design_sources.check_candidates([cand], fetcher=down_fetch)
    assert record["status"] == "lookup_error"
    assert cand["source_check"]["status"] == "lookup_failed"
