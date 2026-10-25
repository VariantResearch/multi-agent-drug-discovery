"""Live citation resolution and source-text quote checking.

The Phase 0 citation auditor (madd/citation_auditor.py) checks
identifier format offline and honestly reports every claim as still
needing live resolution, because nothing ever resolved one. This module
is that missing step. It asks the registry that owns the identifier
whether the record exists, and returns what the registry says:

- PMID: NCBI E-utilities esummary (PubMed).
- DOI: the Crossref works API.
- NCT number: the ClinicalTrials.gov API v2 study record.
- PMCID and preprint (PPR) ids: Europe PMC search.
- GCST study accessions and rsIDs: the GWAS Catalog REST API v2 (the
  v1 API was retired by the Catalog and returns no records).
- ChEMBL molecule ids: the ChEMBL API (EBI).
- PubChem compound ids (CID): the PubChem PUG REST API.
- UniProt accessions: the UniProt REST API.

A resolved result means the identifier exists in its registry and the
registry's title (or nearest label) is reported alongside it. It does
not mean the source supports the claim built on it, and this module
never changes a claim's verification_status. A lookup that cannot be
completed (network failure, registry error) is reported as
lookup_error, never as not_found and never as resolved.

Europe PMC also serves open-access full text for PMCID records.
check_quote_against_source uses it to test the one thing resolution
cannot: whether the exact quote a claim carries actually appears in
the source text. Full text that is not openly available is reported
as full_text_unavailable and proves nothing either way.

The HTTP transport is injectable: pass fetcher(url) -> (status, body)
to test without a network. The default fetcher uses urllib from the
standard library with a short timeout. Nothing here writes anywhere.
"""
from __future__ import annotations

import html as _html
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from .citation_auditor import check_identifier
from .claims import extract_claims

USER_AGENT = "madd-resolver/0.1 (open-source research scaffold)"
TIMEOUT_SECONDS = 15

ENDPOINTS = {
    "pmid": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
            "?db=pubmed&retmode=json&id=",
    "doi": "https://api.crossref.org/works/",
    "nct": "https://clinicaltrials.gov/api/v2/studies/",
}

EUROPEPMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
EUROPEPMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
GWAS_BASE = "https://www.ebi.ac.uk/gwas/rest/api/v2"
CHEMBL_BASE = "https://www.ebi.ac.uk/chembl/api/data"
PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
UNIPROT_BASE = "https://rest.uniprot.org/uniprotkb"


def default_fetcher(url: str) -> tuple:
    """GET a URL, return (status_code, body_text). Never raises for HTTP
    error statuses; transport failures raise and are handled upstream."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return exc.code, body


def _europepmc_query_url(query: str) -> str:
    """Build a Europe PMC core search URL for one query string."""
    return (EUROPEPMC_SEARCH + "?query=" + urllib.parse.quote(query)
            + "&format=json&resultType=core&pageSize=1")


def _url_for(itype: str, identifier) -> str:
    """Build the registry URL for one identifier by type."""
    ident = urllib.parse.quote(str(identifier), safe="")
    if itype in ENDPOINTS:
        return ENDPOINTS[itype] + ident
    if itype == "pmcid":
        return _europepmc_query_url("PMCID:" + str(identifier))
    if itype == "preprint":
        return _europepmc_query_url("EXT_ID:" + str(identifier) + " AND SRC:PPR")
    if itype == "gcst":
        return GWAS_BASE + "/studies/" + ident
    if itype == "rsid":
        return GWAS_BASE + "/single-nucleotide-polymorphisms/" + ident
    if itype == "chembl":
        return CHEMBL_BASE + "/molecule/" + ident + ".json"
    if itype == "pubchem_cid":
        return PUBCHEM_BASE + "/compound/cid/" + ident + "/property/Title/JSON"
    if itype == "uniprot":
        return UNIPROT_BASE + "/" + ident + ".json"
    raise ValueError("no endpoint for identifier type " + itype)


def _extract_title(identifier_type: str, payload: dict, identifier=None):
    """Pull the registry's own title (or nearest label) for the record.

    Returns (title, found, related): found is False when the response
    contains no record for the identifier; related carries cross-ids
    Europe PMC reports for the same record (pmid, pmcid, doi).
    """
    try:
        if identifier_type == "pmid":
            uids = payload.get("result", {}).get("uids", [])
            if not uids:
                return None, False, {}
            record = payload["result"][str(uids[0])]
            if "error" in record:
                return None, False, {}
            return record.get("title"), True, {}
        if identifier_type == "doi":
            titles = payload.get("message", {}).get("title") or []
            return (titles[0] if titles else None), True, {}
        if identifier_type == "nct":
            module = payload.get("protocolSection", {}).get("identificationModule", {})
            return module.get("briefTitle"), True, {}
        if identifier_type in ("pmcid", "preprint"):
            results = payload.get("resultList", {}).get("result") or []
            if not results:
                return None, False, {}
            record = results[0]
            related = {k: record.get(k) for k in ("pmid", "pmcid", "doi")
                       if record.get(k)}
            return record.get("title"), True, related
        if identifier_type == "gcst":
            if "accession_id" not in payload:
                return None, False, {}
            trait = payload.get("disease_trait")
            if isinstance(trait, dict):
                trait = trait.get("trait")
            return (trait or payload.get("reported_trait")), True, {}
        if identifier_type == "rsid":
            if str(payload.get("rs_id", "")).lower() != str(identifier).lower():
                return None, False, {}
            genes = payload.get("mapped_genes") or []
            label = str(payload.get("rs_id"))
            extras = [str(g) for g in genes]
            if payload.get("functional_class"):
                extras.append(str(payload["functional_class"]))
            if extras:
                label += " (" + "; ".join(extras) + ")"
            return label, True, {}
        if identifier_type == "chembl":
            if not payload.get("molecule_chembl_id"):
                return None, False, {}
            return payload.get("pref_name"), True, {}
        if identifier_type == "pubchem_cid":
            props = (payload.get("PropertyTable", {}).get("Properties") or [])
            if not props:
                return None, False, {}
            return props[0].get("Title"), True, {}
        if identifier_type == "uniprot":
            if not payload.get("primaryAccession"):
                return None, False, {}
            name = (payload.get("proteinDescription", {})
                    .get("recommendedName", {}).get("fullName", {})
                    .get("value"))
            return name, True, {}
    except Exception:
        return None, False, {}
    return None, False, {}


def resolve_identifier(identifier, identifier_type, fetcher=None) -> dict:
    """Resolve one identifier against its registry.

    Returns {identifier, identifier_type, status, title, registry,
    detail, related} with status one of: resolved, not_found,
    format_invalid, unknown_type, lookup_error.
    """
    fetch = fetcher if fetcher is not None else default_fetcher
    base = {"identifier": identifier, "identifier_type": identifier_type,
            "title": None, "registry": None, "detail": "", "related": {}}
    fmt = check_identifier(identifier, identifier_type)
    if not fmt["ok"]:
        status = "unknown_type" if fmt["code"] == "unknown_identifier_type" else "format_invalid"
        return dict(base, status=status, detail=fmt["message"])
    itype = str(identifier_type).strip().lower()
    url = _url_for(itype, identifier)
    base["registry"] = urllib.parse.urlparse(url).hostname
    try:
        status_code, body = fetch(url)
    except Exception as exc:
        return dict(base, status="lookup_error",
                    detail="registry lookup failed: " + type(exc).__name__ + ": " + str(exc))
    if status_code == 404:
        return dict(base, status="not_found",
                    detail="registry returned 404 for this identifier")
    if status_code != 200:
        return dict(base, status="lookup_error",
                    detail="registry returned HTTP " + str(status_code))
    try:
        payload = json.loads(body)
    except Exception:
        return dict(base, status="lookup_error", detail="registry response was not JSON")
    title, found, related = _extract_title(itype, payload, identifier)
    if not found:
        return dict(base, status="not_found",
                    detail="registry response contains no record for this identifier")
    return dict(base, status="resolved", title=title, related=related,
                detail="record exists in the registry; title as recorded there")


def resolve_document(document, fetcher=None) -> dict:
    """Resolve every claim identifier in a document. Returns a report
    with per-claim entries and status counts. Claims are not modified."""
    claims = extract_claims(document)
    entries = []
    counts = {}
    for claim in claims:
        result = resolve_identifier(claim.get("source_identifier"),
                                    claim.get("identifier_type"), fetcher=fetcher)
        entries.append({"claim_id": claim.get("claim_id", "<missing claim_id>"),
                        **result})
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    return {"claim_count": len(claims), "entries": entries, "status_counts": counts}


def europepmc_record(identifier, identifier_type, fetcher=None):
    """Fetch the Europe PMC core record for a literature identifier.

    Handles pmid, doi, pmcid, and preprint ids. Returns (record, None)
    on success, (None, status) where status is lookup_error when the
    service cannot be reached or answers badly, or source_not_found
    when Europe PMC holds no such record.
    """
    fetch = fetcher if fetcher is not None else default_fetcher
    itype = str(identifier_type or "").strip().lower()
    if itype == "pmid":
        query = "EXT_ID:" + str(identifier) + " AND SRC:MED"
    elif itype == "doi":
        query = "DOI:" + str(identifier)
    elif itype == "pmcid":
        query = "PMCID:" + str(identifier)
    elif itype == "preprint":
        query = "EXT_ID:" + str(identifier) + " AND SRC:PPR"
    else:
        return None, "not_applicable"
    try:
        status_code, body = fetch(_europepmc_query_url(query))
    except Exception:
        return None, "lookup_error"
    if status_code != 200:
        return None, "lookup_error"
    try:
        payload = json.loads(body)
    except Exception:
        return None, "lookup_error"
    results = payload.get("resultList", {}).get("result") or []
    if not results:
        return None, "source_not_found"
    return results[0], None


def fetch_full_text(pmcid, fetcher=None):
    """Fetch the open-access full text XML for a PMCID from Europe PMC.

    Returns the XML string, or None when Europe PMC holds no open full
    text for the article (paywalled, not deposited, or not OA). None is
    a statement about availability, never about the article.
    """
    fetch = fetcher if fetcher is not None else default_fetcher
    url = EUROPEPMC_BASE + "/" + urllib.parse.quote(str(pmcid), safe="") + "/fullTextXML"
    try:
        status_code, body = fetch(url)
    except Exception:
        return None
    if status_code != 200 or not body or not body.lstrip().startswith("<"):
        return None
    return body


def _plain_text(xml: str) -> str:
    """Reduce JATS XML to comparable plain text: tags out, entities
    decoded, whitespace collapsed, case folded."""
    text = re.sub(r"<[^>]+>", " ", xml)
    return " ".join(_html.unescape(text).split()).casefold()


def check_quote_against_source(identifier, identifier_type, quote, fetcher=None) -> dict:
    """Check a claim's supporting quote against the source's full text.

    Returns {status, pmcid, detail} with status one of: quote_found
    (the quote appears in the open full text), quote_not_found (full
    text was retrieved and the quote is not in it), full_text_unavailable
    (the source has no open full text at Europe PMC, so nothing is
    proven either way), source_not_found, lookup_error, not_applicable
    (identifier types with no full-text source here, and empty quotes).
    Only quote_not_found is evidence against a claim.
    """
    base = {"pmcid": None, "detail": ""}
    if not isinstance(quote, str) or not quote.strip():
        return dict(base, status="not_applicable", detail="claim carries no quote to check")
    record, problem = europepmc_record(identifier, identifier_type, fetcher=fetcher)
    if problem is not None:
        return dict(base, status=problem,
                    detail="Europe PMC lookup did not produce a record")
    pmcid = record.get("pmcid")
    if not pmcid:
        ids = record.get("fullTextIdList", {}).get("fullTextId") or []
        pmcid = ids[0] if ids else None
    base["pmcid"] = pmcid
    if not pmcid:
        return dict(base, status="full_text_unavailable",
                    detail="record has no PMCID, so no open full text is expected")
    xml = fetch_full_text(pmcid, fetcher=fetcher)
    if xml is None:
        return dict(base, status="full_text_unavailable",
                    detail="Europe PMC holds no open full text for " + str(pmcid))
    if _plain_text(quote) in _plain_text(xml):
        return dict(base, status="quote_found",
                    detail="quote located in the open full text of " + str(pmcid))
    return dict(base, status="quote_not_found",
                detail="full text of " + str(pmcid) + " was retrieved and the "
                       "quote does not appear in it")
