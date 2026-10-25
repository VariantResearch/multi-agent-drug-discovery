"""Deterministic focus scoring.

The score is computed only from the evidence tiers of audited claims (see
madd/claims.py is_audited). Model confidence, prose, and vote counts are
never inputs. Each claim_id counts at most once: repeating the same claim
in a document does not raise the score. Tier weights: 1 = 100, 2 = 70,
3 = 40, 4 = 25, 5 = 10, 0 = 0. The scorer returns its per-tier counts so
any score can be recomputed by hand from the ledger.
"""
from __future__ import annotations

from .claims import extract_claims, is_audited

TIER_WEIGHTS = {1: 100, 2: 70, 3: 40, 4: 25, 5: 10, 0: 0}


def focus_score(document) -> dict:
    claims = extract_claims(document)
    per_tier = {str(t): 0 for t in sorted(TIER_WEIGHTS)}
    audited = 0
    score = 0
    counted_ids = set()
    for claim in claims:
        if not is_audited(claim):
            continue
        tier = claim.get("evidence_tier")
        if tier not in TIER_WEIGHTS:
            continue
        cid = claim.get("claim_id")
        if cid is not None:
            if cid in counted_ids:
                continue
            counted_ids.add(cid)
        audited += 1
        per_tier[str(tier)] += 1
        score += TIER_WEIGHTS[tier]
    return {"score": score, "audited_claim_count": audited,
            "total_claim_count": len(claims), "per_tier_counts": per_tier,
            "tier_weights": {str(k): v for k, v in sorted(TIER_WEIGHTS.items())},
            "basis": "audited claims only; verification_status resolved or quote_checked; tier 1 to 5"}
