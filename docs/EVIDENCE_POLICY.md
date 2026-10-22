# Evidence Policy

Status: design document. This policy describes rules this project intends
to enforce. It reports no results and cites no external findings; where a
field fact would be needed, it is marked not yet established.

## Evidence tiers

Higher weight means closer to a causal effect in a human. Tier numbers are
labels; the ordering below is the policy.

| Tier | Kind | Counts as evidence |
|------|------|--------------------|
| 1 | Human causal genetics | Yes |
| 2 | Human clinical or human phenotype data | Yes |
| 3 | Human tissue expression data | Yes |
| 4 | Human cell or organoid data | Yes |
| 5 | Animal data, or in vitro data not from a human system | Yes, weakest |
| 0 | Model opinion, agent opinion, or prose confidence | No. Never evidence. |

Notes:

- A source's tier is a property of the source and study design, not of how
  confidently an agent describes it.
- Tier assignment rules for specific study types are not yet established
  in this scaffold and must be written before any real run.

## Claim ledger rules

- Every claim entered in a dossier is a ledger record with: claim_id,
  text, load_bearing flag, evidence_tier, source_kind, source_identifier,
  identifier_type, verification_status, and supporting_quote.
- A load-bearing claim must carry a non-empty source_identifier.
- A load-bearing claim must not have source_kind "agent" or
  "model_opinion".
- A load-bearing claim must not cite a tier-0 source.
- A claim with verification_status "struck" cannot be load-bearing in any
  later artifact.
- Non-load-bearing claims may be recorded for context, but they cannot be
  promoted to load-bearing without passing the same checks.
- The ledger is append-only within a run. Corrections create a new record
  that references the record it replaces.

## Strike rules

A claim is struck when any of the following holds:

- Its identifier does not resolve to the source it claims to be. (Live
  resolution is not implemented in Phase 0; see docs/PHASE0_SPEC.md.)
- Its supporting quotation, when checked, does not support the claim text.
- Its source is an agent, a model output, or another artifact generated in
  the same run.
- It duplicates a struck claim under a new identifier.

Struck claims are kept in the ledger with status "struck" and the reason,
so an audit can see what was removed. They are excluded from debate,
ranking, design, and paper generation.

## Focus ranking

- Focus score is computed deterministically in madd/focus.py from the
  evidence tiers of audited claims only.
- Audited here means verification_status is "resolved" or "quote_checked",
  the claim is not struck, and the source is not tier 0.
- Tier weights used by the scorer: tier 1 = 100, tier 2 = 70, tier 3 = 40,
  tier 4 = 25, tier 5 = 10, tier 0 = 0.
- Model confidence, prose quality, agent seniority, and vote counts are
  not inputs to the score and must never be added as inputs.
- The scorer returns the per-tier counts it used, so any score can be
  recomputed by hand from the ledger.
