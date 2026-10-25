"""Claim ledger validation.

A load-bearing claim fails when:
- it has no source identifier,
- its source kind is "agent" or "model_opinion",
- its verification status is "struck", or
- it cites a tier-0 source as load-bearing.

All problems are returned as structured errors. Nothing raises on the
first error, so an audit reports everything wrong in one pass.
"""
from __future__ import annotations

NON_EVIDENCE_SOURCE_KINDS = {"agent", "model_opinion"}
AUDITED_STATUSES = {"resolved", "quote_checked"}


def extract_claims(document) -> list:
    """Accept a claim dict, a list of claims, or a dossier/spec dict."""
    if isinstance(document, list):
        return [c for c in document if isinstance(c, dict)]
    if isinstance(document, dict):
        if isinstance(document.get("claims"), list):
            return [c for c in document["claims"] if isinstance(c, dict)]
        if "claim_id" in document:
            return [document]
    return []


def validate_claim(claim: dict) -> list:
    """Validate one claim dict against the ledger rules and return a
    list of error dicts (empty when the claim is clean). Every problem
    found is reported, not just the first."""
    errors = []
    cid = claim.get("claim_id", "<missing claim_id>")
    if not claim.get("load_bearing"):
        if claim.get("verification_status") == "struck":
            errors.append({"claim_id": cid, "code": "struck_claim_present",
                           "message": "struck claim recorded; it must stay excluded, not load-bearing"})
        return errors
    identifier = claim.get("source_identifier")
    if identifier is None or (isinstance(identifier, str) and identifier.strip() == ""):
        errors.append({"claim_id": cid, "code": "missing_source_identifier",
                       "message": "load-bearing claim has no source identifier"})
    kind = str(claim.get("source_kind", "")).strip().lower()
    if kind in NON_EVIDENCE_SOURCE_KINDS:
        errors.append({"claim_id": cid, "code": "non_evidence_source_kind",
                       "message": "load-bearing claim sourced from " + kind + ", which is not evidence"})
    if claim.get("verification_status") == "struck":
        errors.append({"claim_id": cid, "code": "struck_load_bearing",
                       "message": "struck claim cannot be load-bearing"})
    tier = claim.get("evidence_tier")
    if tier == 0:
        errors.append({"claim_id": cid, "code": "tier_zero_load_bearing",
                       "message": "tier-0 source (model opinion) cannot be load-bearing"})
    return errors


def audit_claims(document) -> dict:
    """Audit every claim in a document. Returns a structured report."""
    claims = extract_claims(document)
    errors = []
    for claim in claims:
        errors.extend(validate_claim(claim))
    seen = {}
    for claim in claims:
        cid = claim.get("claim_id")
        if cid is not None:
            seen[cid] = seen.get(cid, 0) + 1
    for cid, count in seen.items():
        if count > 1:
            errors.append({"claim_id": cid, "code": "duplicate_claim_id",
                           "message": "claim_id appears " + str(count) + " times in one "
                                      "document; identifiers must be unique within a "
                                      "document, or a struck claim can re-enter under "
                                      "the same id as its replacement"})
    return {"claim_count": len(claims), "error_count": len(errors),
            "ok": len(errors) == 0, "errors": errors}


def is_audited(claim: dict) -> bool:
    """True when a claim can count toward focus scoring."""
    if claim.get("verification_status") not in AUDITED_STATUSES:
        return False
    if str(claim.get("source_kind", "")).strip().lower() in NON_EVIDENCE_SOURCE_KINDS:
        return False
    tier = claim.get("evidence_tier")
    # bool is a subclass of int in Python; a boolean tier is not a tier.
    return isinstance(tier, int) and not isinstance(tier, bool) and tier >= 1
