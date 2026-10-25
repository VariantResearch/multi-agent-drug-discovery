"""Retrieval: build a run's evidence set from a live source, so agents
cite what a search returned instead of what a model remembers.

The retrieval-first rule (enforced in madd/debate.py) strikes
load-bearing claims that cite identifiers outside the evidence the
run supplied. For Gate 0 that evidence is the curated case pack. For
a prospective frame there is no pack, so this module builds the
evidence set at run time: a Europe PMC search over the frame's target,
disease, and drug terms, normalized into evidence entries carrying
the identifiers agents may then cite.

Retrieval returns what the search returns: titles and identifiers
from Europe PMC's index, labelled as retrieved evidence. It does not
judge quality, and an empty result is reported as an empty set, never
padded. The transport is injectable, like madd/resolve.py.
"""
from __future__ import annotations

import json
import urllib.parse

from .resolve import EUROPEPMC_SEARCH, default_fetcher


def search_europepmc(query: str, fetcher=None, limit: int = 10) -> list:
    """One Europe PMC core search; returns the raw result records.

    Raises nothing: a failed or malformed search returns an empty
    list, and callers report the empty evidence set as what it is.
    """
    fetch = fetcher if fetcher is not None else default_fetcher
    url = (EUROPEPMC_SEARCH + "?query=" + urllib.parse.quote(query)
           + "&format=json&resultType=core&pageSize=" + str(int(limit)))
    try:
        status_code, body = fetch(url)
    except Exception:
        return []
    if status_code != 200:
        return []
    try:
        payload = json.loads(body)
    except Exception:
        return []
    return payload.get("resultList", {}).get("result") or []


def evidence_from_records(records: list) -> list:
    """Normalize Europe PMC records into evidence entries.

    Each entry carries the strongest identifier the record offers, in
    the claim ledger's own terms: pmid first, then a preprint id for
    PPR records, then doi, then pmcid. Records with no usable
    identifier are dropped: evidence an agent cannot cite is not
    evidence for this system.
    """
    entries = []
    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("pmid"):
            ident, itype = str(record["pmid"]), "pmid"
        elif record.get("source") == "PPR" and record.get("id"):
            ident, itype = str(record["id"]), "preprint"
        elif record.get("doi"):
            ident, itype = str(record["doi"]), "doi"
        elif record.get("pmcid"):
            ident, itype = str(record["pmcid"]), "pmcid"
        else:
            continue
        entries.append({
            "source_identifier": ident,
            "identifier_type": itype,
            "title": record.get("title"),
            "source_kind": "preprint" if itype == "preprint" else "journal_article",
            "registry": "Europe PMC",
        })
    return entries


def frame_query(frame: dict) -> str:
    """Build the Europe PMC query for a frame from its own terms:
    target, disease, and drug name, in that order, skipping blanks."""
    terms = [str(frame.get(k)).strip() for k in ("target", "disease", "drug_name")
             if frame.get(k) and str(frame.get(k)).strip()]
    return " ".join(terms)


def retrieve_evidence(frame: dict, fetcher=None, limit: int = 10) -> list:
    """Retrieve the evidence set for a prospective frame.

    Returns normalized evidence entries (possibly an empty list when
    the frame names nothing searchable or the search finds nothing).
    """
    query = frame_query(frame)
    if not query:
        return []
    return evidence_from_records(search_europepmc(query, fetcher=fetcher,
                                                  limit=limit))
