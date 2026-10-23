"""Live citation resolution.

The Phase 0 citation auditor (madd/citation_auditor.py) checks
identifier format offline and honestly reports every claim as still
needing live resolution, because nothing ever resolved one. This module
is that missing step. It asks the registry that owns the identifier
whether the record exists, and returns what the registry says:

- PMID: NCBI E-utilities esummary (PubMed).
- DOI: the Crossref works API.
- NCT number: the ClinicalTrials.gov API v2 study record.

A resolved result means the identifier exists in its registry and the
registry's title is reported alongside it. It does not mean the source
supports the claim built on it: quote checking against the source text
stays a separate, human-or-better step, and this module never changes a
claim's verification_status. A lookup that cannot be completed (network
failure, registry error) is reported as lookup_error, never as
not_found and never as resolved.

The HTTP transport is injectable: pass fetcher(url) -> (status, body)
to test without a network. The default fetcher uses urllib from the
standard library with a short timeout. Nothing here writes anywhere.
"""
from __future__ import annotations

import json
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


def _extract_title(identifier_type: str, payload: dict):
    """Pull the registry's own title for the record, or None."""
    try:
        if identifier_type == "pmid":
            uids = payload.get("result", {}).get("uids", [])
            if not uids:
                return None, False
            record = payload["result"][str(uids[0])]
            if "error" in record:
                return None, False
            return record.get("title"), True
        if identifier_type == "doi":
            titles = payload.get("message", {}).get("title") or []
            return (titles[0] if titles else None), True
        if identifier_type == "nct":
            module = payload.get("protocolSection", {}).get("identificationModule", {})
            return module.get("briefTitle"), True
    except Exception:
        return None, False
    return None, False


def resolve_identifier(identifier, identifier_type, fetcher=None) -> dict:
    """Resolve one identifier against its registry.

    Returns {identifier, identifier_type, status, title, registry, detail}
    with status one of: resolved, not_found, format_invalid,
    unknown_type, lookup_error.
    """
    fetch = fetcher if fetcher is not None else default_fetcher
    base = {"identifier": identifier, "identifier_type": identifier_type,
            "title": None, "registry": None, "detail": ""}
    fmt = check_identifier(identifier, identifier_type)
    if not fmt["ok"]:
        status = "unknown_type" if fmt["code"] == "unknown_identifier_type" else "format_invalid"
        return dict(base, status=status, detail=fmt["message"])
    itype = str(identifier_type).strip().lower()
    if itype == "doi":
        url = ENDPOINTS[itype] + urllib.parse.quote(str(identifier), safe="")
    else:
        url = ENDPOINTS[itype] + urllib.parse.quote(str(identifier), safe="")
    base["registry"] = urllib.parse.urlparse(ENDPOINTS[itype]).hostname
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
    title, found = _extract_title(itype, payload)
    if not found:
        return dict(base, status="not_found",
                    detail="registry response contains no record for this identifier")
    return dict(base, status="resolved", title=title,
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
