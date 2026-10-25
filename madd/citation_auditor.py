"""Offline citation auditor. No network calls.

Checks identifier format (DOI pattern, PMID numeric, NCT pattern) and that
claims marked quote_checked carry a non-empty supporting_quote. Everything
else is reported as still needing live resolution. This auditor never
upgrades a claim's verification status and makes no network calls: live
resolution lives in madd/resolve.py and is not faked here.
"""
from __future__ import annotations

import re

from .claims import extract_claims

DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
PMID_RE = re.compile(r"^\d+$")
NCT_RE = re.compile(r"^NCT\d{8}$")
PMCID_RE = re.compile(r"^PMC\d+$")
PREPRINT_RE = re.compile(r"^PPR\d+$")
GCST_RE = re.compile(r"^GCST\d+$")
RSID_RE = re.compile(r"^rs\d+$")
CHEMBL_RE = re.compile(r"^CHEMBL\d+$")
PUBCHEM_CID_RE = re.compile(r"^\d+$")
UNIPROT_RE = re.compile(r"^([A-Z][0-9][A-Z0-9]{3}[0-9]|[A-Z0-9]{6,10})$")

PATTERNS = {"doi": DOI_RE, "pmid": PMID_RE, "nct": NCT_RE,
            "pmcid": PMCID_RE, "preprint": PREPRINT_RE, "gcst": GCST_RE,
            "rsid": RSID_RE, "chembl": CHEMBL_RE,
            "pubchem_cid": PUBCHEM_CID_RE, "uniprot": UNIPROT_RE}


def check_identifier(identifier, identifier_type) -> dict:
    """Check one identifier's format by type (pmid, doi, nct) and return
    {'ok', 'code', 'message'}; the code names the exact format failure."""
    if identifier is None or (isinstance(identifier, str) and identifier.strip() == ""):
        return {"ok": False, "code": "missing_identifier",
                "message": "no identifier to check"}
    itype = str(identifier_type or "").strip().lower()
    pattern = PATTERNS.get(itype)
    if pattern is None:
        return {"ok": False, "code": "unknown_identifier_type",
                "message": "identifier_type not recognised: " + (itype or "<missing>")}
    if pattern.match(str(identifier)):
        return {"ok": True, "code": "format_ok", "message": itype + " format ok"}
    return {"ok": False, "code": "format_invalid",
            "message": "identifier does not match the " + itype + " pattern"}


def audit_citations(document) -> dict:
    """Audit citations in a document. Returns a structured report."""
    claims = extract_claims(document)
    results = []
    needs_live = []
    for claim in claims:
        cid = claim.get("claim_id", "<missing claim_id>")
        fmt = check_identifier(claim.get("source_identifier"), claim.get("identifier_type"))
        entry = {"claim_id": cid, "format": fmt, "problems": []}
        if claim.get("verification_status") == "quote_checked":
            quote = claim.get("supporting_quote")
            if not isinstance(quote, str) or quote.strip() == "":
                entry["problems"].append({
                    "code": "quote_checked_without_quote",
                    "message": "quote_checked claim carries no supporting_quote"})
        status = claim.get("verification_status")
        if status not in ("resolved", "quote_checked"):
            needs_live.append(cid)
            entry["needs_live_resolution"] = True
        else:
            entry["needs_live_resolution"] = True
            entry["live_resolution_note"] = (
                "status recorded as " + str(status) + "; this offline auditor "
                "does not perform live resolution (madd/resolve.py does), so "
                "treat the recorded status as unverified until resolution runs")
        results.append(entry)
    problem_count = sum(1 for r in results if not r["format"]["ok"] or r["problems"])
    return {"claim_count": len(claims), "entries": results,
            "needs_live_resolution": needs_live,
            "problem_count": problem_count,
            "ok": problem_count == 0}
