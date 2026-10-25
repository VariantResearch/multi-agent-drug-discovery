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
  score_run (simple counts; the pass thresholds were approved on
  2026-10-22 and are applied by evaluate_thresholds, added 2026-10-23).
- CLI subcommands gate0-validate and gate0-list.
- tests/test_gate0.py: dataset integrity tests over the real Gate 0 set.
- docs/PHASE1_SPEC.md: specification for the debate engine, including
  the Gate 0 pass thresholds approved on 2026-10-22 (see the approval
  entry below); the model roster is not yet approved.
- Phase 1 thresholds approved by the project owner on 2026-10-22 and
  recorded as in force in docs/PHASE1_SPEC.md: kill at least 3 of 4
  known negatives, advance at least 3 of 4 known positives, beat the
  single-model baseline by at least 1 case, zero audit violations,
  judge-swap stability of at most 1 flipped call in 8. The model roster
  and the run budget figure remain open and must be recorded in the
  spec before the first scored run.
- Five upgrades, applied one at a time on 2026-10-23 after a repo audit
  ranked ten candidates: (1) madd/gate0.py evaluate_thresholds judges a
  scored run against the approved thresholds, with missing inputs
  reported as not_evaluable, never as a pass; (2) madd/budget.py, a
  budget tracker whose caps are a hard stop (an uncapped budget is
  rejected); (3) madd/debate.py, the debate engine implementing
  docs/DEBATE_PROTOCOL.md steps 1 to 7 over the Provider interface,
  producing a frozen hashed run record; (4) madd/resolve.py, live
  citation resolution against PubMed, Crossref, and ClinicalTrials.gov
  with an injectable transport, probed live on 2026-10-23 (PMID
  28304224, DOI 10.1056/NEJMoa1615664, and NCT01764633 resolved with
  their registry titles; a bogus PMID returned not_found); (5) CLI run
  commands gate0-report, resolve-citations, and debate-mock, plus the
  first CLI tests. Test suite is now 82 tests.

- Feature completion pass, 2026-10-24: the application now runs end
  to end and lacks only the models. Ten features, ranked by
  improvement and built in order: (1) madd/runner.py orchestrates a
  full Gate 0 run (baseline first under a rule fixed in code, debate
  per case, one shared run budget, scoring, threshold judgement,
  frozen bundle) and single-frame runs; (2) madd/providers_http.py
  adds OpenAI-compatible and Anthropic Messages adapters over stdlib
  HTTPS (tested offline against fake transports shaped from the
  documented wire formats; not yet run against a real model account);
  (3) madd/prompting.py holds the shared research prompt and the
  dossier response contract, whose failure mode is an honest empty
  dossier, never a repaired invention; (4) madd/config.py loads and
  validates run configs, reading API keys from the environment by
  variable name only; (5) prospective frame runs; (6) gate_report
  produces the GateReport artifact, with audit violations and
  judge-swap flips computed from the records; (7) live citation
  resolution can strike not_found claims inside the evidence call,
  config-gated, and a lookup error never strikes; (8) CLI commands
  run-gate0, run-frame, and providers-check; (9) madd/storage.py
  writes one folder per run plus an index; (10) madd/report.py
  renders the plain-language run report. Test suite is now 128 tests.
- Five further upgrades, applied one at a time on 2026-10-24 after a
  fresh audit of the current code and docs, each finding demonstrated
  against the tree before it was fixed: (1) the stale-claims sweep was
  finished repo-wide (the earlier repair pass had missed PHASE0_SPEC's
  status lines, gate0/README's thresholds text, and a contradictory
  changelog bullet, all now corrected; the TradeMemory shelf entry no
  longer narrows that project to losing trades); (2) the agreement
  consensus test no longer passes when a dossier proposes no focus;
  (3) duplicate claim identifiers are flagged by the claim audit and
  counted once in focus scoring; (4) evaluate_thresholds opens with a
  run_completeness check, so a run missing predictions cannot pass,
  and absent kill or advance counts report not_evaluable rather than
  fail; (5) debate records are complete: duplicate dossier ids are
  rejected, judge strikes are recorded, the manifest carries a
  per-call entry with prompt hash, and the record states which rubric
  terms are applied (frame coverage is recorded as not applied, since
  it is not mechanically defined). Test suite is now 90 tests.

### Fixed

- A claim with evidence_tier set to a boolean counted as a tier-1
  claim in focus scoring (bool is a subclass of int in Python). It is
  no longer treated as audited, with a regression test.
- Stale status text corrected after the upgrades: DEBATE_PROTOCOL.md
  no longer says no debate has been run (mock and stub debates run in
  tests; no live-model debate has taken place), EVIDENCE_POLICY.md and
  the Phase 0 spec no longer say live resolution is unimplemented, and
  the citation auditor's notes and the package description point at
  madd/resolve.py.

### Changed

- README rewritten in plainer language and updated for Gate 0. The old
  "What this is not" list was removed: parts of it were obvious, and its
  claim that the repository makes no disease or target claims stopped
  being true when the real Gate 0 data landed.

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
