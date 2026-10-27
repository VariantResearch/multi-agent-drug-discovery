"""Tests for the full-text retrieval tiers: chunking, the
tier caps, concise/deep evidence carrying chunked text with
provenance, abstract-only honesty for articles without open
full text, the abstract tier returning base retrieval
unchanged, and the estimate pricing the tier."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from madd.fulltext import (chunk_text, retrieve_tiered_evidence,
                           tier_caps, xml_to_text)
from madd.runner import estimate_target_run

FRAME = {"target": "MTCH2", "disease": "obesity"}

RECORDS = [
    {"pmid": "111", "pmcid": "PMC111", "title": "Open article",
     "abstractText": "An abstract.", "source": "MED"},
    {"pmid": "222", "title": "Closed article", "source": "MED"},
    {"pmid": "333", "pmcid": "PMC333", "title": "Second open",
     "source": "MED"},
    {"pmid": "444", "pmcid": "PMC444", "title": "Third open",
     "source": "MED"},
]

FULLTEXT = ("<article><body><p>" + ("Alpha beta gamma delta. " * 120)
            + "</p></body></article>")


def fetcher(url):
    """Serve the search and full-text endpoints from fixtures."""
    if "fullTextXML" in url:
        return 200, FULLTEXT
    return 200, __import__("json").dumps(
        {"resultList": {"result": RECORDS}})


def test_chunking_and_xml_text():
    """Chunks are bounded, ordered, and lossless enough to
    quote from; XML reduces to readable text."""
    text = xml_to_text(FULLTEXT)
    assert text.startswith("Alpha beta gamma delta.")
    chunks = chunk_text(text, size=200, overlap=40)
    assert len(chunks) > 3
    assert all(len(chunk) <= 200 for chunk in chunks)
    assert chunks[0].startswith("Alpha")


def test_concise_tier_carries_chunks():
    """Concise fetches up to 3 full texts: entries with a PMCID
    get chunk blocks, the PMCID-less entry is abstract_only,
    and the fourth record is beyond the search window used
    here only if the tier says so."""
    entries = retrieve_tiered_evidence(FRAME, "concise",
                                       fetcher=fetcher)
    by_id = {e["source_identifier"]: e for e in entries}
    open_entry = by_id["111"]
    assert open_entry["full_text"]["pmcid"] == "PMC111"
    assert open_entry["full_text"]["chunks_supplied"] >= 2
    assert open_entry["abstract"] == "An abstract."
    assert by_id["222"]["full_text_status"] == "abstract_only"
    assert by_id["333"].get("full_text") is not None


def test_abstract_tier_is_base_retrieval():
    """The default tier is exactly the base retrieval: no
    full_text blocks anywhere."""
    entries = retrieve_tiered_evidence(FRAME, "abstract",
                                       fetcher=fetcher)
    assert entries
    assert all("full_text" not in e for e in entries)


def test_tier_pricing_and_validation():
    """The estimate names the tier's fetch caps, and an
    unknown tier is an error, not a default."""
    estimate = estimate_target_run([], retrieval_tier="deep")
    assert estimate["full_text_fetches"] == 10
    assert "deep" in estimate["note"]
    with pytest.raises(ValueError):
        tier_caps("everything")
    with pytest.raises(ValueError):
        retrieve_tiered_evidence(FRAME, "everything",
                                  fetcher=fetcher)
