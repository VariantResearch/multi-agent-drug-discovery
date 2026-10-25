# Changelog

## [Unreleased]

### Fixed

- Consensus agreement compared proposed focus labels as exact
  strings, so cases were decided by spelling: a unanimous panel
  could fail agreement for writing the same target two ways, and a
  case could be scored killed by the same accident in reverse
  (validation run 2). Gate 0 packs now declare a canonical
  focus_id, the frame carries it to providers, the research prompt
  instructs models to copy it exactly when advancing, and the
  debate engine canonicalizes any proposal naming the frame's
  target onto that id before the consensus tests read it, keeping
  the model's original string as proposed_focus_raw. Frames
  without a focus_id behave as before.
- Live quote check searched only the deposited full text XML, whose
  abstract section does not always match the published abstract, so
  genuine abstract quotes struck as quote_not_in_full_text (the
  validation run's REC-994 lead claim, in four dossiers). The check
  now searches the Europe PMC record's abstract as well as the full
  text: a quote found in either is quote_found, and a strike still
  requires the full text retrieved with the quote absent from both.
  Live-verified: the struck quote resolves quote_found and a
  fabricated control quote still strikes.

### Added

- Validation runs 2 and 3 recorded (docs/VALIDATION_RUN_2026-10-25.md,
  run record in docs/PHASE1_SPEC.md). Run 2 (repaired quote check,
  fresh agent panel): debate 6 of 8, baseline 5 of 8, kill rate
  passed 4 of 4, positive advance rate failed 2 of 4 on a spelling
  defect in the agreement test, outcome fail. Run 3 (canonical
  focus repair, fresh panel): debate 7 of 8, baseline 7 of 8, zero
  audit strikes, kill rate 3 of 4 and advance rate 4 of 4 passed,
  baseline margin failed at 0 because a single model family in
  every seat made the baseline an effective extra panelist,
  outcome fail. Neither is a scored Phase 1 run; the roster and
  budget in PHASE1_SPEC remain open.
- Agent-panel validation run recorded (docs/VALIDATION_RUN_2026-10-25.md,
  run record in docs/PHASE1_SPEC.md). On 2026-10-25 the production
  Gate 0 pipeline ran end to end with the owner's own agents as
  providers and all four live audit checks on: debate 6 of 8
  correct against a 5 of 8 baseline, five of six approved
  thresholds passed, and the failure kill rate failed (2 of 4
  negatives killed, 3 required), so the run outcome under the
  approved rules is fail. Not a scored Phase 1 run: the roster and
  budget in PHASE1_SPEC remain open. The run also surfaced a
  quote-check calibration question (abstract quotes versus
  full-text body search) recorded for the owner's decision.
- Design power batch. ADMET-AI enrichment (madd/design_admet.py):
  every SMILES candidate in a design run gains a panel of predicted
  ADMET endpoints from the trained TDC models, recorded as
  computed:ADMET-AI with verified: false - a tool's predictions, not
  measurements, and counted as unverified by the audit. Verified live:
  aspirin receives 16 endpoints on CPU. AutoDock Vina joins the
  license-gated tool runner (input is a Vina config file; the docked
  PDBQT becomes a candidate), verified live by redocking the 1HVR
  ligand through the runner (best mode -14.5 kcal/mol). PoseBusters
  pose validation (madd/design_pose.py) reports each geometric check
  by name; verified live on RDKit conformers, clean and deliberately
  broken. AiZynthFinder retrosynthesis gets a dedicated runner
  (design_tools.run_retrosynthesis, design-run --retro-config) with an
  honest no_config status when its model files were never downloaded.
  License registry gains all four tools with licenses verified
  against their own repositories (ADMET-AI MIT, Vina Apache-2.0,
  PoseBusters MIT, AiZynthFinder MIT).
- Auditor v2: three evidence-call upgrades, each behind its own
  run-config flag and each striking only on positive evidence.
  Retraction strikes: a DOI whose Crossref record carries a
  retraction or withdrawal is flagged at resolution and struck as
  citation_retracted_live under live_resolution. Entailment checking
  (entailment_check, madd/entailment.py): the config's judge provider
  compares each surviving quote_checked claim with the passage it
  cites; only a refuted verdict strikes (claim_refuted_by_its_quote),
  and an unanswerable judge strikes nothing. Retrieval-first rule
  (retrieval_first): load-bearing claims may cite only identifiers in
  the evidence the run supplied (citation_not_in_evidence otherwise);
  madd/retrieval.py builds a prospective frame's evidence set live
  from Europe PMC, wired as run-frame --retrieve.
- Sources batch: live resolution grows from three registries to eight.
  New identifier types, each format-checked offline and resolved
  against its owning registry: pmcid and preprint (PPR) via Europe PMC,
  gcst and rsid via the GWAS Catalog REST API v2 (the v1 API is
  retired and returns no records), chembl via the ChEMBL API,
  pubchem_cid via PubChem PUG REST, and uniprot via the UniProt REST
  API. All seven verified live against the real registries.
- Full-text quote checking: Europe PMC serves open-access full text
  for PMCID records, and a claim's supporting quote can now be checked
  against the actual source text (resolve.check_quote_against_source;
  resolve-citations --check-quotes). Statuses are honest about the
  middle case: full_text_unavailable proves nothing. Behind the new
  live_quote_check run-config flag, the evidence call strikes a
  quote_checked claim whose quote is absent from retrieved full text
  (quote_not_in_full_text); unavailable text never strikes.
- Design source check (design-run --source-check): each candidate's
  InChIKey is looked up in ChEMBL and PubChem, and the known-compound
  result is recorded on the candidate. Information, not a verdict; it
  never excludes a candidate, and registry failures are recorded as
  lookup failures, never as novelty.
- The real design cycle: ModelDesigner turns the run config's provider
  panel into the designer (design-run --config, or the console's
  config field). Providers answer a strict candidate contract through
  a new complete() completion method on the HTTP adapters and
  MockProvider; every candidate must carry a real structure (SMILES
  or sequence), structureless proposals from real providers are
  dropped with the reason recorded, and mock-provider candidates are
  marked synthetic so they can never pass a gate. RDKit enrichment
  (madd/design_rdkit.py, license-gated, BSD) validates every SMILES
  before audit and attaches computed descriptors (molecular weight,
  logP, TPSA, HBD, HBA, rotatable bonds) with the basis
  "computed:RDKit <version>", so a design cycle ends with ranked
  candidates carrying real structures, calculated properties, and
  audited claims - or a failed gate saying why not. RDKit is an
  optional dependency; when absent the step reports not_installed and
  fabricates nothing.
- Phase 2 candidate design (docs/PHASE2_SPEC.md): design briefs built
  mechanically from locked consensus specs (unlocked specs refused),
  carrying the spec's surviving load-bearing claims as evidence
  constraints; a Designer interface with a deterministic mock designer
  whose synthetic candidates carry no structures and no invented
  numbers; candidate audit under the same claim rules as the research
  layer, with exclusion and reasons for failed claims or constraints;
  a fixed deterministic ranking rule; design bundles with gate
  reports, stored and reported like run bundles (text, HTML, console).
  CLI: design-brief and design-run, with --case for Gate 0 bundles and
  --target/--disease overrides (specs record a focus id but no disease).
  External structure tools run through a license-gated runner: the
  registry verdict is enforced before anything executes, outputs are
  recorded by path and SHA-256 hash in a manifest, and each output
  becomes a candidate with that provenance and no invented assessment.
  The MADD Console starts a design run from a locked frame run and
  shows design bundles in the run library.
- Chai-1 license registry entry verified against the chaidiscovery/
  chai-lab repository (2026-10-25): its LICENSE is Apache-2.0 and its
  README states the license covers both code and model weights,
  commercial use included, superseding the 2024 technical report's
  non-commercial weights language. The entry stands as recorded; the
  verification is noted on the entry itself.
- Documentation pass (2026-10-25): every module, class, and function
  in madd/ and tests/ now carries a docstring (331 added across the
  test suite), enforced from here on by tests/test_documentation.py,
  which also checks that the README repository layout names every
  package module. Stale sections rewritten in place: the README
  layout gained the six design modules and the package entry files;
  docs/PHASE0_SPEC.md describes live resolution and full-text quote
  checking as built; docs/PHASE2_SPEC.md covers the enrichment steps,
  Vina docking, and the AiZynthFinder runner, and no longer lists
  docking, ADMET, or synthesis planning as out of scope;
  docs/EVIDENCE_POLICY.md lists the retraction, full-text,
  entailment, and retrieval-first strike rules; docs/
  DEBATE_PROTOCOL.md describes the live checks in the evidence call.

### Fixed

Full-codebase audit of 2026-10-24 (independent review, every finding
probe-verified against the tree; regression tests in
tests/test_audit_regressions.py):

- Gate 0 blinding: the input pack's forbidden_terms list - the leakage
  scanner's wordlist of outcome vocabulary and pivotal-trial
  identifiers - was copied into every case frame and serialized into
  provider prompts. frame_for_case now strips it; a regression test
  asserts no forbidden term appears in a built prompt.
- Budget race: the check-then-record flow was not atomic, so parallel
  case debates sharing one tracker overshot max_calls (a probe made
  12 calls against a cap of 9). BudgetTracker.reserve() now charges
  atomically before a call is made, in debates and for the baseline.
- Retried provider calls were invisible to the budget, and the smoke
  test could make three transport calls while claiming exactly one.
  Providers now report last_attempts and debates settle retry costs
  against the tracker (stopping the run if they cross the cap); the
  smoke test disables retries for its one call.
- Consensus agreement compared only focus ids, so a panel split
  advance/kill on the same focus could lock a spec whose direction
  said kill and have it scored as advance. Direction agreement is
  required when directions are stated. A frame round_cap below 1 is
  now refused before any provider call.
- Duplicate claim_ids inside one dossier defeated the evidence call's
  citation check (dict keyed by claim_id): every copy of a duplicated
  id is now struck, matching the document-level rule.
- Candidate audit parity: the design layer's audit ran only ledger
  presence checks. It now uses the document claim audit and the
  citation auditor, counts audited support once per claim_id, and
  excludes candidates whose load-bearing claims carry any audit error.
- Design gate honesty: the gate previously passed on synthetic mock
  candidates alone, even when a requested tool never ran, and
  design-run exited 0 on a failed gate. The gate now requires a real
  ranked candidate and completed requested tools; design-run exits
  non-zero on gate failure. Design bundles are frozen under the
  canonical hash envelope, and the design gate report validates
  against the gate_report schema (gate_name and subject_id added).
- design_tools claimed stale files in a reused output directory as a
  run's outputs and turned every output file (including logs) into a
  structure candidate. Outputs are snapshotted before the run; only
  created or changed files are recorded, and only structure-suffixed
  files become candidates.
- Duplicate candidate_ids in one design run are refused (audits and
  ranking are keyed by id), and MockDesigner candidates no longer
  share mutable list state.
- Console: bundle fields were interpolated into innerHTML unescaped
  and run ids into inline onclick handlers; fields are escaped now
  and clicks bind through data attributes. storage.load_bundle
  refuses path separators and dot segments (a ../ URL segment could
  read bundle files outside the runs directory). list_runs tolerates
  a corrupt index instead of failing the run library.
- Reports now mark synthetic candidates as SYNTHETIC placeholders in
  the text report, the HTML report, and the console, so a ranked list
  is never mistaken for real candidates.
- Transport failures (DNS, refused connections) escaped as raw
  URLError tracebacks; they now surface as ProviderError and stop run
  commands cleanly. Config validation rejects non-numeric
  cost_per_call_usd and non-integer max_tokens, which previously
  crashed providers-check with a bare ValueError.
- Judge-swap flips counted no_go records whose call could not have
  changed; flips now count only locked records the swap would have
  unmade. Threshold details state their real denominators (of 4
  negative / 4 positive cases), fed by new score_run counts.
  Transcripts rendered None for pairwise wins and anonymous dissent:
  they read ranking wins and dissent objector_agent_id, the fields
  debate records actually carry.
- tests/test_madd.py imported the consensus test functions under their
  test_* names, so pytest collected them as tests and errored on
  their parameters (they are library functions, called from unittest
  methods). The imports are aliased now.
- Documentation: the documented test command is pytest everywhere
  (unittest discovery silently skips the pytest-style files and
  reported 150 tests while pytest runs the full suite); the README
  key-documents list named two files that do not exist
  (GATE0_NOTES.md, DECISIONS.md) and now cites the real ones;
  gate0/README's synthetic-fixtures line now includes
  examples/synthetic/; DEBATE_PROTOCOL describes frame coverage as
  the recorded not_applied it is, the evolution re-audit as the
  claim-ledger audit it is, and the round cap as the enforced floor
  it is; PHASE0_SPEC's artifact table lists design_brief;
  madd/__init__ and license_registry docstrings describe the package
  and registry file as they are.

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

- Ten features added 2026-10-24, ranked by improvement and built in
  dependency order: (1) the MADD Console, a retro cyberpunk web GUI
  (madd/gui.py, stdlib server, localhost by default) with run
  control, a live progress console, the Gate 0 scoreboard, and a run
  library with HTML reports and transcripts; (2) live run progress
  events from the runner; (3) providers-smoke, one billable call per
  provider with latency, returned model, and usage; (4) a dry-run
  call and cost estimator; (5) run comparison (score deltas, flipped
  calls, threshold changes); (6) a self-contained styled HTML report
  with inline SVG charts, written with every bundle; (7) debate
  transcripts rendered from records and written with every bundle;
  (8) gate0-new-case scaffolding that deliberately fails validation
  until completed with verified material; (9) bounded provider
  retries on 429 and 5xx, every retry logged and counted into the
  bundle; (10) parallel case execution under a thread-safe budget,
  bundle order deterministic. Test suite is now 150 tests.
- Repository presentation, 2026-10-24: the GitHub About description
  was simplified to a plain summary of the app (the commands live in
  the README, where they fit), and the README gained a molecule
  banner above its title: a plain ASCII structural formula, atom
  letters and bonds, no legend.
- Documentation and commenting pass, 2026-10-24: the README is now
  the complete manual (what the system does, requirements, exact
  commands for every workflow including a full Gate 0 run, the run
  configuration reference, the Gate 0 cases and thresholds, and the
  repository layout), and the GitHub repository description was set
  to the fullest summary the platform's 350-character limit allows,
  commands included, pointing to the README for the rest. Every
  module, class, and function in madd/ now carries a docstring
  (verified mechanically: zero undocumented definitions remain), and
  the pyproject description no longer claims no live model calls.
  Code changes are docstring insertions only; the suite still passes
  unchanged.
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
