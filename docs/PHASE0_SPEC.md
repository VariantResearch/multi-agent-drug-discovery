# Phase 0 Specification

Status: design document and scaffold description. This document describes
what the Phase 0 code contains and the designs it prepares. It reports no
results. Field facts not contained in this repository are marked not yet
established.

## Artifact schemas

JSON Schema files live in madd/schemas/. A small structural validator in
madd/schemas.py checks the subset of JSON Schema used by those files:
type, required, properties, items, and enum. It does not claim full JSON
Schema compliance.

| Artifact | File | Purpose |
|----------|------|---------|
| Frame | frame.json | The question, intended effect profile, and exclusions fixed before a run. |
| Claim | claim.json | One ledger record for a single claim and its source. |
| Dossier | dossier.json | One agent's sealed research output: claims plus a proposed focus. |
| ConsensusSpec | consensus_spec.json | The locked specification, or a no-go, produced after debate. |
| Candidate | candidate.json | A design produced only against a locked ConsensusSpec. |
| DesignBrief | design_brief.json | The Phase 2 design brief built from a locked ConsensusSpec (added in Phase 2; listed here so the inventory stays complete). |
| GateReport | gate_report.json | The outcome of one validation gate for one artifact. |
| RunManifest | run_manifest.json | Model, version, prompt hash, tool versions, and budget for a run. |

Every artifact carries an artifact_type and a schema_version. Frozen
artifacts are identified by the SHA-256 of their canonical JSON form
(sorted keys, compact separators), computed in madd/artifacts.py.

## Citation verification design

### Verification states

- unverified - recorded, not yet checked. Cannot support a locked
  specification.
- resolved - the identifier was resolved against its issuing registry and
  the record found matches the citation metadata. Live resolution was
  not implemented in Phase 0; it exists now as madd/resolve.py, which
  resolves the identifier and reports the registry title. Matching the
  record against the full citation metadata is not automated.
- quote_checked - resolved, and a supporting quotation from the source was
  recorded in the supporting_quote field and checked against the claim
  text. Quote checking against source text is not automated anywhere in
  this repository; the Gate 0 quotes were checked by hand at dataset
  construction (see gate0/VERIFICATION_LEDGER.md).
- struck - failed a check, or sourced from an agent or model opinion, or
  otherwise excluded under docs/EVIDENCE_POLICY.md.

### Offline auditor (implemented)

madd/citation_auditor.py performs offline checks only:

- Identifier format: DOI pattern, PMID numeric pattern, NCT pattern.
- Claims marked quote_checked must carry a non-empty supporting_quote.
- Claims with any other status are listed as still needing live
  resolution, by claim_id.
- The auditor makes no network calls and never upgrades a claim's status.
  It reports what a live resolver still has to do.

### Live resolution (TODO interface, not implemented in Phase 0)

A future resolver module is expected to: resolve an identifier against
its registry, compare returned metadata with the citation, fetch or receive
the source text under its license terms, and check the supporting
quotation. Until that module exists and is tested, every claim in every
run remains at most "unverified" in practice, and no specification may be
locked on the basis of this scaffold alone.

Addendum, updated 2026-10-25: the resolver exists as madd/resolve.py.
It resolves identifiers against the registry that owns each type -
PubMed, Crossref, ClinicalTrials.gov, Europe PMC, the GWAS Catalog,
ChEMBL, PubChem, and UniProt - and reports the registry title. It also
checks supporting quotations against open-access full text served by
Europe PMC: a quote absent from retrieved text is reported, while a
source with no open full text proves nothing either way, so the
caution above still stands wherever full text is not openly available.

## Gate 0: retrospective test set design

Purpose (design): before the system is trusted on a new question, it is
run blinded on historical cases with known outcomes, to measure whether
its ranking and strike behaviour would have pointed at the outcomes that
were actually observed.

Selection design:

- Cases are selected by criteria written before any case is chosen:
  the case class, the time window, and the inclusion rule are fixed first.
  (For Gate 0 v1 the criteria were applied at construction: eight
  well-documented pivotal programs, four positive and four negative.
  See gate0/README.md.)
- Each case must be documented from a primary source, recorded with its
  identifier in the case file before the case is admitted.
- Cases are split into a selection set and a held-out set by a rule fixed
  in advance. The held-out set is not used to tune thresholds.
- Negative and failed cases must be included by the inclusion rule, not
  only successes. A test set of successes only cannot measure the strike
  behaviour that this project depends on.

Blinding design:

- Agents receive case inputs with outcome-identifying fields removed.
- The outcome key is held outside the agent context and joined only at
  scoring time.
- Any case whose outcome leaks into its inputs is removed and recorded.

Pass criteria:

- Pass criteria are numeric thresholds on pre-declared measures, written
  and frozen before the first Gate 0 run, and never set after seeing
  results. The values were set and approved on 2026-10-22 and are
  recorded in docs/PHASE1_SPEC.md; madd.gate0.evaluate_thresholds
  applies them.
- Failing Gate 0 stops the program at this phase. It is not a prompt to
  tune until it passes on the same set.

Current status, stated plainly:

- Eight Gate 0 cases are included in this repository, in gate0/, each
  with its primary sources recorded in gate0/VERIFICATION_LEDGER.md.
- No case may be added without a primary source recorded for it.
- No Gate 0 run has been performed with live models, and no score
  reported anywhere in this repository is a Gate 0 result. Mock and
  stub runs in the test suite are plumbing checks only.

## Gates after Gate 0 (names only in Phase 0)

Later gates are named here so outputs can be labelled honestly:
Gate 1 citation audit, Gate 2 independent-tool cross-check,
Gate 3 computational design checks, Gate 4 human review sign-off,
Gate 5 partner-lab experimental handoff. Only Gate 1 is partially
implemented in Phase 0, as the offline auditor. The rest are not yet
established as working gates.
