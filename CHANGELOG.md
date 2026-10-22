# Changelog

## [Unreleased]

### Added

- Gate 0 retrospective dataset (gate0/): 8 real historical drug programs
  with known pivotal outcomes, 4 positive and 4 negative, each verified
  on primary sources fetched and read on 2026-10-22. Blinded input packs
  (gate0/input/) carry pre-outcome claims only, each with an identifier,
  a supporting quote of at most 25 words, and a per-case forbidden_terms
  list; sealed outcomes (gate0/sealed/) are read only at scoring time.
  Verification ledger and leakage limitation statement in
  gate0/VERIFICATION_LEDGER.md; construction corrections in
  gate0/REJECTED.md (no case was dropped).
- madd/gate0.py: dataset validation against the Claim schema and ledger
  rules, a leakage scan over input text fields, build_agent_pack, and
  score_run (simple counts, no thresholds; Gate 0 pass thresholds are
  not yet set, per docs/PHASE0_SPEC.md).
- CLI subcommands gate0-validate and gate0-list.
- tests/test_gate0.py: dataset integrity tests over the real Gate 0 set.

## [0.1.0] - 2026-10-22

Unreleased work in progress. This entry describes the Phase 0 scaffold;
no release has been made and nothing here is a research result.

### Added

- Artifact schemas for Frame, Claim, Dossier, ConsensusSpec, Candidate,
  GateReport, and RunManifest, with a small structural validator.
- Claim ledger audit, offline citation auditor, and strike rules.
- License registry with run-use enforcement.
- Consensus tests, dissent log check, and a deterministic focus scorer.
- Provider interface and a deterministic mock provider for tests.
- Command line interface: audit-claims, check-tool, focus-score,
  validate-artifact.
- Synthetic example fixtures, labelled synthetic, for code tests only.
- Evidence policy, debate protocol, Phase 0 specification, responsible
  use, and contributing documents.
