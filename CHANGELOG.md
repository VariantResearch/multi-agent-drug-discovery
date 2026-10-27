# Changelog

## [Unreleased]

### Added (competitive-gap item 19, 2026-10-27)

- Figure and table evidence extraction (madd/figure_table.py,
  `madd extract-evidence --pmcid <id>`), the last item of the
  competitive-gap implementation list, built only after its
  spike held. The spike (live, 2026-10-27) sampled Europe PMC
  full texts: clinical articles carried structured JATS
  tables whose cell grids extract mechanically and verbatim
  with the standard library (5 of 6 articles, 12 tables),
  figures carried rich captions, and cell-biology articles
  carried no tables at all. The build covers exactly what
  held: tables as label, caption, and full cell grid;
  figures as label and caption. Figure graphics are images:
  counted, flagged graphic_extracted False, never read -
  values are not lifted off chart images by a tool this
  system does not have. Each table and caption becomes an
  evidence entry named by its source (PMCID:Table 1), its
  text the verbatim lines a claim may quote. An article
  without tables yields no entries rather than an error.

### Added (competitive-gap item 18, 2026-10-27)

- Bundle-faithful manuscript draft (madd/manuscript.py,
  `madd manuscript <bundle>`), the fourth wave-4 item of the
  competitive-gap implementation list. The draft has the
  shape of a short computational paper and is assembled
  from statements: each sentence is rendered from a named
  bundle field and carries that field path in the draft's
  statement list, so a reader can trace every number to its
  source and nothing enters the text that the bundle does
  not contain. References are the surviving claims' sources,
  deduplicated; a struck claim's source stays out (verified
  against the frozen MTCH2 inhibition bundle, whose struck
  EMBO source is absent from its draft). The limitations
  section states the bundle's scope as a fact: computational
  only, no synthesis, assay, or clinical results recorded,
  no candidate made or tested.

### Added (competitive-gap item 17, 2026-10-27)

- Fenced run memory (madd/run_memory.py, `madd run-memory`),
  the third wave-4 item of the competitive-gap implementation
  list. A digest over the finished bundles in a runs
  directory carries operational metadata only: per target,
  the runs attempted, their outcomes, and strike totals; per
  provider, participation counts and debate outcomes; per
  run, its kind and gate results. The fence is structural:
  the scan reads only the named metadata fields, so claim
  text, supporting quotes, dossier content, and candidate
  structures cannot cross into the memory (a test plants
  distinctive claim and structure strings in a fixture
  bundle and asserts their absence from the digest). The
  memory is surfaced to the operator, never to a run:
  target-run prints a target's history at framing time when
  one exists. Prior AI output is not citable as evidence,
  and under this fence it cannot quietly become so.

### Added (competitive-gap item 16, 2026-10-27)

- Checkpointed long runs (madd/checkpoints.py; --checkpoint-dir
  and --resume on run-gate0 and target-run), the second wave-4
  item of the competitive-gap implementation list. Gate 0
  persists each case's baseline and debate results as the
  case completes; target runs persist the frame stage and
  the design stage. A resumed run reuses a checkpoint only
  when its guard matches the inputs just rebuilt (the case
  pack's hash for Gate 0, a hash of the frame for target
  runs): changed inputs invalidate the checkpoint completely
  rather than letting a different run wear the same id.
  Resumed stages make no provider calls and charge no
  budget, the event stream names each resumed stage, and
  the bundle a resumed run produces is identical in form to
  a fresh run's. Checkpoints are working state in their own
  directory, never the frozen record of anything.

### Added (competitive-gap item 15, 2026-10-27)

- Full-text retrieval tiers (madd/fulltext.py), the first
  wave-4 item of the competitive-gap implementation list.
  Retrieved evidence now comes in three tiers, selectable
  per run through the retrieval_tier config key or the
  target-run --retrieval-tier flag, and honored by CLI and
  console runs alike: abstract (the default; identifiers and
  titles, exactly as retrieval has always supplied), concise
  (up to 3 open-access full texts fetched from Europe PMC
  and chunked into the evidence entries, at most 8 chunks
  each, with the abstract carried too), and deep (up to 10
  articles, 40 chunks each, wider search). An article with
  no open full text is recorded abstract_only, and one past
  the tier's cap is recorded as not attempted; neither is
  ever padded with invented text. The preflight estimate
  prices the tier, naming its fetch and chunk caps before a
  run spends anything, in both the CLI estimate and the
  console's preflight line. An unknown tier name is a config
  error, not a silent default.

### Added (competitive-gap item 14, 2026-10-27)

- Trial landscape (madd/trials.py, `madd trials --disease
  <d> [--focus <drug,...>]`), the fifth and final wave-3
  item of the competitive-gap implementation list. From the
  ClinicalTrials.gov API: the registry's own total for the
  disease, phase and status breakdowns over a sample of the
  most recent studies (labelled as sample counts, not
  registry totals), a counted query per focus term with its
  recent studies, and the five most recent studies with NCT
  identifiers, statuses, sponsors, and interventions, all
  stamped with the query date. A failed fetch marks its
  section unavailable rather than reporting an unobserved
  zero. The report states that registry presence is a fact
  about a program's existence, not its quality or prospects.
  Live-checked at build time: 15,097 obesity studies in the
  registry, with no obesity study naming evolocumab or
  MTCH2 as an intervention. As the list specifies, every
  target run also gains the landscape as a bundle section
  for its disease (focus: the run's target), fetched during
  the run with the same failure tolerance - a registry
  failure marks the section unavailable and never fails the
  run - so a design is produced knowing what the clinic has
  already tried.

### Added (competitive-gap item 13, 2026-10-27)

- Target scout (madd/scout.py and madd/chembl.py, `madd
  scout --disease <d> --targets <a,b,c>`), the fourth wave-3
  item of the competitive-gap implementation list. For each
  named target the scout resolves the pair in Open Targets
  (association score with the literature and genetic
  components shown separately) and pulls ChEMBL's recorded
  drug-mechanism count and bioactivity count for the target,
  then ranks by the association score as reported. The
  whitespace read is mechanical and labelled: an associated
  target with no recorded mechanism is "comparatively open",
  one with mechanisms is "validated but occupied", and a
  pair with no association is "unestablished". ChEMBL
  resolution prefers a component synonym exactly matching
  the query (gene symbols live there, not in the preferred
  name) and the search uses the API's search endpoint; both
  choices were forced by live checks during the build, in
  which the naive lookups returned the same wrong target for
  every query and then an mRNA entry for PCSK9. Failed
  lookups record None, never zero, and unresolved targets
  are kept in the report with their problems named. The
  scout nominates; it locks nothing in. ChEMBL is registered
  (CC BY-SA 4.0).

### Added (competitive-gap item 12, 2026-10-27)

- Executable protocol export (madd/protocol_export.py,
  `madd protocol-export <plan bundle>`), the third wave-3
  item of the competitive-gap implementation list. One assay
  plan renders as a single bench-ready Markdown document:
  the hypotheses under test by claim id, and per candidate
  the structure, primary and secondary assays with readouts,
  counterscreens, the named controls, and the acceptance
  criteria as a checklist spelling out the metric and
  threshold each graded criterion uses, closing with the
  plan's conduct and decision rule. The export is a rendering
  of the plan as written - nothing in it is added, computed,
  or re-thresholded - and its notes repeat the boundary:
  reagent identities and settings are verified against local
  SOPs, execution is laboratory work outside this system,
  and results return through assay-grade.

### Added (competitive-gap item 11, 2026-10-27)

- Assay results ingestion (madd/assay_results.py, `madd
  assay-grade <plan bundle> <results.json>`), the second
  wave-3 item of the competitive-gap implementation list,
  closing the design loop. Assay plan criteria now also
  carry a machine-checkable form (metric, comparison,
  threshold) beside their prose rule, and returned
  measurements are graded against exactly those checks:
  met, not_met, or not_reported, where a missing measurement
  is named as outstanding and never counted as met.
  Recommendations follow the plan's own decision rule:
  advance when every criterion is met, retire when the hit
  call or a counterscreen-class criterion failed, revise
  otherwise with the gaps named. Results for candidates the
  plan never named are recorded as unplanned and not graded;
  planned candidates without results are recorded as
  outstanding. A plan_id mismatch between the results file
  and the plan is recorded on the report, and the report
  states that grading operator-supplied measurements is not
  verification the assay was run as planned.

### Added (competitive-gap item 10, 2026-10-27)

- Assay design output (madd/assay.py, `madd assay-plan
  <design bundle>`), the first wave-3 item of the
  competitive-gap implementation list. From a design run (or
  a target bundle's design section), the top candidates in
  ranking order each get a concrete assay plan: the
  hypotheses under test are the design brief's surviving
  evidence constraints; the assay blocks are matched to each
  candidate's modality (small molecule: biochemical
  dose-response plus a cell-based functional assay and
  counterscreens; sequence: knockdown with mRNA and protein
  readouts; other modalities: binding plus functional), with
  named controls, dose layouts, and acceptance criteria.
  Every criterion is recorded in the plan as an assay-design
  convention chosen before any data exists, and the plan
  states plainly that executing it is laboratory work
  outside this system. Returned results (next item) will be
  graded against these criteria as written.

### Added (competitive-gap item 9, 2026-10-27)

- DiffDock pose cross-check (madd/diffdock.py), the ninth and
  final wave-2 item of the competitive-gap implementation
  list. Where an installation is configured
  (MADD_DIFFDOCK_HOME naming a DiffDock checkout, registered
  MIT in the license registry), the console's dock action
  also runs DiffDock on the same receptor and ligand and
  compares its top pose against the Vina pose: centroid
  distance graded agree (at most 2.0 A), partial (at most
  4.0 A), or disagree, with DiffDock's own confidence
  recorded when its output reports one. The verdict rides in
  the docking record and in the console's pose caption. The
  record states plainly that a centroid is a coarse geometry
  summary, not an RMSD, and that agreement between two
  computed poses is not evidence of binding. With no
  installation configured, no cross-check key appears in the
  record at all, so absence never reads as a failed check.

### Added (competitive-gap item 8, 2026-10-27)

- Generative designer seat (madd/design_generative.py), the
  eighth item of the competitive-gap implementation list. A
  generative chemistry endpoint named by MADD_GENERATIVE_URL
  (MADD_GENERATIVE_MODEL names the model for provenance,
  MADD_GENERATIVE_N the sample count, MADD_GENERATIVE_TOKEN
  an optional bearer token) fills one seat in the design
  panel beside the language models: run_design composes it
  in automatically when the environment configures one, for
  design runs and target runs alike. Sampled molecules enter
  as ordinary candidates stamped design_tool
  "generative:<model>" with no claims (a sampler asserts
  nothing), and pass through the same RDKit validation,
  candidate audit, ranking, and design gate as any proposed
  candidate. With no endpoint configured the seat is simply
  absent; a configured endpoint that fails contributes no
  candidates and records the failure in the designer notes.
  Endpoint calls are metered outside the run budget, and the
  seat's note in the bundle says so.

### Added (competitive-gap item 7, 2026-10-27)

- TxGemma property predictions (madd/design_txgemma.py), the
  seventh item of the competitive-gap implementation list.
  TxGemma runs as a served model, not a library, so the bridge
  calls an operator-configured text-generation endpoint named
  by MADD_TXGEMMA_URL (an HF Inference Endpoint or TGI-style
  URL serving TxGemma; MADD_TXGEMMA_TOKEN optionally supplies
  a bearer token). With design-run --txgemma, each SMILES
  candidate is asked three TDC tasks (Ames mutagenicity Yes/No,
  hERG inhibition Yes/No, aqueous solubility logS), answers
  are parsed conservatively, and predictions attach as
  txgemma:* predicted properties with verified False, the same
  grade ADMET-AI carries: never evidence, never in the audit's
  path. With no endpoint configured the tool run records
  not_configured and predicts nothing; an endpoint that
  answers nothing parseable records failed. TxGemma is
  registered in the license registry under the Gemma Terms of
  Use: allowed for research, blocked for commercial use.

### Added (competitive-gap item 6, 2026-10-27)

- Lead optimization loop (madd/optimize.py, CLI command
  `madd optimize`), the sixth item of the competitive-gap
  implementation list and the first of wave 2. Given a design
  bundle and one of its SMILES candidates (the top-ranked by
  default), the config's designer panel proposes analogs in
  bounded rounds (default 2). Every analog is computed on
  with RDKit; it is kept only when it Pareto-improves on its
  parent across the computed objectives (QED up, SA score
  down, structural alert count down), and dropped with its
  reason otherwise: duplicate or parent itself, invalid
  structure, logP drift beyond 1.0 from the original lead, or
  no Pareto improvement. Kept analogs chain, the round's best
  becoming the next round's parent, and the full lineage,
  every proposal with its computed values, deltas, and
  verdict, is stored as an optimization bundle. An optional
  registry source check runs over kept analogs, recorded,
  never excluding. The record states its standing in itself:
  in-silico iteration on computed objectives, not a potency,
  binding, or efficacy claim. Sequence leads return
  not_applicable; a missing RDKit returns not_available.

### Added (competitive-gap item 5, 2026-10-26)

- Meta-review (madd/meta_review.py), the fifth item of the
  competitive-gap implementation list, completing wave 1.
  After each debate, deterministic signals are computed from
  the finished record (strikes by agent and their
  concentration, surviving load-bearing claims and their
  distinct sources, disputes, cluster shape, tournament
  divergence from the mechanical ranking, failed consensus
  tests, red-team and judge-swap state) and the config's
  judge provider writes a structured critique over those
  signals only, choosing findings from a closed pattern
  vocabulary (strike_concentration, single_source_dependence,
  unresolved_disputes, preference_divergence,
  cluster_collapse, thin_evidence, consensus_failure,
  judge_instability) with note, concern, or serious severity.
  Findings outside the vocabulary are dropped, an empty
  findings list is a valid clean review, and a reviewer that
  cannot answer records the review as unavailable instead of
  fabricating one. The review and its signals are recorded on
  the run, advisory only. Enabled by the meta_review config
  switch (CLI and console setup).

### Added (competitive-gap item 4, 2026-10-26)

- Tournament ratings (madd/tournament.py), the fourth item of
  the competitive-gap implementation list, in the AI
  co-scientist's shape: when the tournament switch is on, a
  run's proposal clusters play judged head-to-head matches
  between their representatives (round-robin, capped at 45),
  the judge comparing the proposals on the claims each
  representative actually survived with. Wins, losses, and
  ties accumulate into Elo-style ratings (start 1500, K = 32)
  recorded on the run record with the match list. The ratings
  are advisory only, and the record says so: they are a
  preference ordering over the proposals as argued and move
  no consensus test, lock, spec, or gate. Copies get no extra
  matches (representatives play, not dossiers), a judge
  failure records the match unverifiable and changes no
  rating, and judging calls are budget-reserved like the
  other judged checks. Enabled by the tournament config
  switch (CLI and console setup), judged by the config's
  judge provider.

### Added (competitive-gap item 3, 2026-10-26)

- Proposal clustering (madd/clustering.py), the third item of
  the competitive-gap implementation list. After ranking, the
  audited dossiers are grouped deterministically (no model
  calls) into proposal clusters: two dossiers merge when they
  propose the same focus in the same direction, or argue the
  same direction on substantially overlapping sources (Jaccard
  similarity of cited identifiers at or above 0.5); direction
  is never merged across. Each cluster is recorded on the
  debate record with its members in ranking order, its
  top-ranked representative, the rules that fired, and the
  sources at least two members share; ranking entries name
  their cluster. Near-duplicate proposals are thus visible as
  one cluster instead of several apparent endorsements, and
  the tournament ratings (item 4) will rate clusters rather
  than copies. Clustering is descriptive in this item: it
  changes no consensus outcome.

### Added (competitive-gap item 2, 2026-10-26)

- Contradiction detection (madd/contradictions.py), the second
  item of the competitive-gap implementation list, in the shape
  of PaperQA2's ContraCrow: after the evidence call, surviving
  load-bearing claims from different dossiers are compared.
  Candidate pairs are prefiltered deterministically (claims
  citing the same source first, then shared content tokens,
  capped at 24 judged pairs) and a judge provider rules on each:
  contradicts, compatible, or cannot_tell. Only a clear
  "contradicts" creates a dispute, and every failure of the
  check itself creates nothing. Disputes are not strikes: both
  claims survive annotated with their partners, the
  cross-examination transcript names each dispute as an
  objection that must be answered, and the evolution merge
  keeps disputed claims out of the consensus spec, recording
  them there as contested claims, so a lock cannot silently
  rest on a claim another surviving claim contradicts. The
  screened and judged pair counts are recorded on the run.
  Enabled by the contradiction_check config switch (CLI and
  console setup), judged by the config's judge provider, with
  judging calls reserved against the run budget like every
  other provider call.

### Added (competitive-gap item 1, 2026-10-26)

- Open Targets as an evidence source (madd/opentargets.py),
  the first item of the competitive-gap implementation list.
  Target-disease associations from the Open Targets Platform
  are now citable claims: the identifier is the Ensembl target
  id and disease id joined by a colon (identifier_type
  "opentargets"), live resolution re-queries the Platform's
  GraphQL API for exactly that pair, and a pair with no
  association does not resolve. Target runs (CLI and console)
  retrieve the frame's association at framing time beside the
  Europe PMC set, carrying the overall score and the
  per-datatype breakdown, labelled as the Platform's integrated
  score, not a primary measurement. The API answers GraphQL
  over POST only, so the source carries its own injectable
  transport rather than riding the resolver's GET fetcher.

### Added (the nine-item build, 2026-10-26)

- Cooperative stop: debates, frame runs, Gate 0 runs, and target
  runs accept a stop flag checked at phase boundaries. The
  console's stop button ends the active run; a stopped run
  finishes with its partial bundle marked stopped, its completed
  cases kept, and thresholds recorded as not evaluated rather
  than failed.
- Design-stage candidate source checks now fan out across
  worker threads (per-candidate verdicts are computed
  independently and aggregated on the caller thread; the record
  is unchanged). Measured on a canned registry: six candidates
  in about 0.66 s against about 1.2 s serial.
- Every bundle-writing path persists its event stream: design
  runs through the console now write events.jsonl like target
  runs do, so the run detail replays the design stage too.
- Pre-registration (madd/prereg.py): a target run's target,
  question, panel model identities, and lock criteria are
  hashed and written before the run starts; the finished bundle
  carries the hash, and `madd prereg-verify <bundle>` recomputes
  it and checks the bundle answers the declared question. CLI
  target runs pre-register by default (`--no-prereg` skips it);
  console target runs always do. The record states its own
  limit: it proves declaration-before-execution, not that no
  undeclared runs happened.
- AlphaFold fetch on demand (madd/structure3d.py): when no
  receptor is on file for a design's target, the console resolves
  the target to a reviewed human UniProt entry, fetches its
  AlphaFold predicted model, caches it in the runs directory,
  and registers it, labelled predicted with the model identity,
  version, and mean pLDDT. Unresolvable targets keep the honest
  none-on-file state.
- Docking (madd/docking.py): an operator-triggered dock places
  the viewed candidate into the on-file receptor with AutoDock
  Vina via Meeko preparation, persists a docking record in the
  run folder, and adds a computed-pose view with the Vina score,
  labelled as a scoring-function geometry, not evidence of
  binding. It shipped only after a redocking spike passed:
  indinavir, prepared from its PubChem SMILES as candidates are
  prepared here, redocked into HIV-1 protease (PDB 1HSG) with
  its top pose 0.61 A (centroid) from the crystal ligand and
  every pose atom within 2.5 A of a crystal atom, at -8.5
  kcal/mol; a replicate run landed 1.26 A away with 40 of 49
  pose atoms within 2.5 A. Vina is stochastic; both runs
  reproduce the known pose, which validates the pipeline, not
  any new pose. Missing tooling reports not_available with the
  reason.
- Target-run preflight: the console prices a run against the
  saved setup before it starts (debate and design call counts,
  estimated cost, and any budget cap the estimate would break).
- Live run header: the activity panel shows elapsed time, the
  current stage, budget consumption, and the stop button while
  a run is active.
- The run library is filterable by kind and outcome, searchable
  by run id or target, and sortable; bundle index entries now
  carry the target name and creation time to feed it.

### Changed

- The console is now purely the product interface, at the
  owner's direction: Gate 0 and the prefilled MTCH2 are removed
  from it. Gate 0 is a validation set, not the product - it
  remains fully available from the CLI (gate0-validate,
  run-gate0, and the calibration command) to validate a setup
  and calibrate it, but the console's scoreboard panel, run
  control (check / dry run / run Gate 0), Gate 0 detail view,
  and calibration panel are gone, its endpoints return 404,
  and Gate 0 bundles are no longer listed in the run library.
  The target form opens blank: the preset target chips (MTCH2
  and the Gate 0 case targets) are removed, and the bundled
  MTCH2 AlphaFold receptor no longer ships - the receptor
  registry mechanism remains, empty, so a design's receptor
  view states none on file instead of showing a preloaded
  example protein. The design-from-a-run action now runs on
  the saved setup's models when no config is named. The
  `gui --gate0-dir` option is removed with the surface it fed.

### Added

- Three feature sets from the owner's research commission
  (2026-10-26), chosen from a sourced review of GUI, speed, and
  novel-capability options. (1) Live run streaming: run progress
  events now reach the console over server-sent events
  (/api/events, backlog replay via ?since=, keep-alive comments,
  a terminal caught_up event), replacing 700 ms polling as the
  primary transport with polling kept as the fallback; each
  finished run's events persist as events.jsonl in its folder
  and replay in the run detail. (2) Registry transport speed:
  the resolver's default fetcher keeps persistent per-host
  connections (measured on loopback at roughly 12x for repeated
  GETs, before counting the TLS handshakes it also saves on
  real hosts), and an opt-in cross-run SQLite cache
  (MADD_REGISTRY_CACHE; the console enables it in its runs
  directory) stores 200 responses for 24 hours with singleflight
  deduplication of concurrent identical lookups and hit/miss
  counters, joining the parallel case fan-out the runner
  already had. Freshness is bounded by the TTL and every cached
  response keeps its fetch timestamp. (3) Calibration, a
  capability the application did not have in any form:
  madd/calibration.py buckets Gate 0 verdicts by panel
  agreement (unanimous / majority / split, read from each
  record's ranking) and reports realized accuracy per bucket
  per protocol mode against the sealed outcomes - as
  `madd calibration <bundle>...`, at /api/calibration, and as
  a table under the console's run library. Counts only: no
  fitted probabilities, and the report states plainly that
  bucket accuracies over a small frozen set are diagnostics,
  not guarantees.
- Improvements adopted from the MADD-Gcloud variant review
  (owner's instruction, 2026-10-26), each rebuilt to this
  project's rules rather than copied: (1) structural alerts and
  triage scores in the design stage - the RDKit pass now also
  computes QED and the SA score (recorded as computed properties)
  and screens every SMILES candidate against the PAINS and Brenk
  FilterCatalogs, recording alerts on the candidate and on its
  production sheet as triage information that never excludes on
  its own; (2) a PDF report export - madd/report_pdf.py renders
  a bundle's canonical HTML report to PDF through WeasyPrint
  (BSD, added to the license registry) when the package is
  installed, reports not_installed plainly when it is not, and
  is reachable as `madd report-pdf <bundle> --out <file>`, as a
  console /api/runs/<run>/report.pdf route, and as a PDF report
  link beside each HTML report link. Assessed and not adopted,
  with reasons: the variant's extra provider kinds duplicate the
  openai-compatible kind's base_url reach; its ClinicalTrials.gov
  resolver duplicates the NCT resolution resolve.py already does;
  its hardcoded descriptor table and hash-derived InChIKey
  function contradict the computed-or-absent rule and were
  rejected outright; its analog-editing studio and target
  intelligence suite remain unbuilt here (the latter was
  researched and shelved before the variant existed).
- A fourth protocol mode, simple_judge (owner's decision,
  2026-10-26): the research panel on one model, plus a judge. It
  completes the ablation square - one model or two, judge or
  none - so the contribution of the second model and of the
  judge can each be measured on Gate 0 before anything is
  claimed for them; the scored Phase 1 mode remains dual_judge.
  Enforced in config validation and in the runner like the other
  modes; spec, runbook, and README updated.
- The console's setup-first flow and target form (the external
  audit's suggested first feature, owner's design). On load the
  console checks its saved setup: a SETUP panel assigns the
  Primary, Secondary, and Judge model slots - each a provider
  entry naming the environment variable that holds its API key,
  key values never entering the page or the file - plus the
  protocol mode the assignments support, a budget, and the
  evidence switches; saving writes a normal run config to
  runs/console-config.json (a one-model setup materializes its
  second agent as a clone entry, as a hand-written config would;
  an existing judge_swap or baseline entry is preserved). Each
  slot shows whether its key variable is present in the server's
  environment, and a per-slot Test button runs the smoke call
  against the saved setup. Below it, a TARGET RUN form: quick
  pick chips for the project's known targets, a kind selector
  (molecular target, receptor, disease, genetic disorder), the
  molecular target and disease context fields, design
  constraints, and the Europe PMC retrieval toggle; runs execute
  in the background on the setup's models under its mode, land
  in the run library, and open in a target detail view (debate
  outcome, focus, strikes, design gate). Regression tests in
  tests/test_gui_setup_target.py.
- README screenshots of the console (screenshots/): the run
  control and Gate 0 scoreboard, a completed target run with its
  rendered molecule and receptor, and the build guide panel -
  captured from the live console against the published MTCH2 run.
- Fully rendered 3D molecule and receptor views in the MADD
  Console. The run view of a completed design now renders the
  target drug as a shaded WebGL model (3Dmol.js v2.5.5, vendored
  under madd/assets/ so the console works offline) with
  ball-and-stick, sticks, space-filling, and line styles and spin,
  beside the receptor structure on file for the target in its own
  view. The first shipped receptor is the AlphaFold predicted
  model for human MTCH2 (AF-Q9Y6C9-F1 v6, mean pLDDT 86.3, CC BY
  4.0), labelled predicted everywhere it appears. Molecule and
  receptor are separate views: the candidate has not been docked,
  and no binding pose is shown or claimed. Targets with no
  receptor on file say so. Behind GET
  /api/runs/<run>/model3d/<candidate>; the earlier canvas viewer
  remains as the fallback when the WebGL library cannot load.
- A build guide panel in the MADD Console: the run view of a
  completed design renders each ranked candidate's production
  sheet as steps (make the structure by its route, confirm
  identity against the sheet, run the confirmation assay), behind
  GET /api/runs/<run>/build-guide. Sheets are served as stored,
  or built mechanically for older bundles that predate stored
  sheets; anything the sheet records as unspecified is named in
  the panel, never filled in.
- Build guides for the two MTCH2 small-molecule candidates in
  designer-output/target-mtch2-inhibition-2026-10-25/
  (build-guide-panel-b-cand-1.md, build-guide-panel-a-cand-1.md):
  proposed Hantzsch routes, release QC against the production
  sheets, and a proposed confirmation plan, each labelled as
  proposal work for a compound not yet made or assayed.
- A 3D structural view in the MADD Console (madd/structure3d.py):
  when a design completes, the run view shows a rotatable
  ball-and-stick model of each ranked small-molecule candidate,
  generated from its SMILES by RDKit (ETKDG conformer, fixed seed,
  MMFF-relaxed) behind GET /api/runs/<run>/structure3d/<candidate>.
  The view states what it is: a generated conformer for
  visualization, not a measured structure or a docked pose.
  Sequence candidates return an honest not_applicable; the buttons
  for them are disabled with the reason shown.
- The first published designer output (designer-output/): the
  MTCH2 inhibition target run's frozen bundle, production sheets,
  rendered report, and a provenance README carrying the run's
  audit caveats with the output.
- Production targets (madd/production.py): every design bundle now
  carries one production sheet per ranked candidate, built
  mechanically - the structure exactly as proposed, its computed
  identity (canonical SMILES, formula, molecular weight, InChIKey;
  length and composition for sequences), the production route its
  modality implies, the targeted process from the brief, and a
  not_specified list naming what the designer did not supply. A
  sheet is production_ready only when the thing to make is fully
  determined. The design contract now asks designers for
  production_notes (modification pattern, confirmation assay), and
  both reports render the sheets. This is the stage's end goal per
  the owner's 2026-10-25 statement: drug, peptide, and
  oligonucleotide targets specified for production, not just
  ranked ideas.
- The target-first pipeline (madd/target_run.py, CLI
  `madd target-run`): the operator names a specific target (a
  disease, a receptor, a genetic disorder, or a molecular target in
  a disease context) and one run carries it end to end - evidence
  retrieved from Europe PMC, the panel debate under the config's
  protocol mode, and, only on a locked specification, the Phase 2
  design stage, frozen into one combined bundle with outcome
  designed, design_gate_failed, or no_go. This is the application's
  front door, per the owner's 2026-10-25 correction of the product
  definition: Gate 0 and the debate are the evidence engine in
  front of design, not the product itself. Validated the same day
  with an agent-staffed simple-mode run on KRAS G12C in non-small
  cell lung cancer: the target locked with zero audit strikes and
  four original designer candidates were ranked, design gate pass
  (bundle target-kras-g12c-validation-2026-10-25; a validation of
  the pipeline, not a scored Gate 0 run and not a claim about the
  candidates, which are model proposals, computationally
  validated in the run and not made or assayed).

### Fixed

- All four findings of the follow-up external audit (CodeRabbit,
  2026-10-26, against c73930d2, the A1-A7 repair revision),
  reproduced with the audit's probes and repaired; regression
  tests in tests/test_coderabbit_audit_2026_10_26.py pin them.
  F1: the new design and entailment budget paths reserved one
  logical call but never settled the HTTP transport's retry
  attempts (the research path settles them); both now settle via
  budget.settle_transport_retries, so attempts are recorded and a
  settlement that crosses the cap stops the run. F2: the repaired
  judge-swap metric still compared a panel outcome against itself
  plus one judge, with no second judging result; a run config can
  now name a judge_swap provider, the debate records a
  judge_swap_experiment per case (each case call computed under
  each judge, both model families as provenance), and the runner
  counts flips only when every case has an experiment whose two
  families differ - otherwise the stability threshold records
  not_evaluable, so a scored dual_judge run now requires the swap
  configuration (docs and runbook updated). F3: a claim whose id
  was a JSON array or object crashed both auditors with a
  TypeError before the schema check could strike it; audit
  structures now index claims by claims.claim_key (the string id
  or a fixed placeholder), and such claims are struck
  schema_invalid / hard-fail the candidate audit as intended.
  F4: budget exhaustion inside the model designer was converted
  into a per-provider note, so a truncated panel could still
  report a design pass; BudgetExceeded now escapes the designer,
  and the design entry points (CLI design-run, console) report a
  stopped run. The A2 regression expectation changed accordingly:
  a target run whose budget runs out stops, openly.
- All seven findings of an external code audit (CodeRabbit,
  2026-10-26, run by the owner against revision aa6dad86) were
  reproduced with the audit's own probes and repaired; nine
  regression tests in tests/test_coderabbit_audit_2026_10_26.py
  pin them. A1: the console's Gate 0 runner silently dropped the
  config's resolver, quote checker, entailment checker, and
  retrieval_first switches; the evidence-callback factories now
  live in madd/config.py, shared by the CLI and the console, and
  a console run wires all four as the CLI does. A2: design and
  entailment provider calls bypassed the run budget; one budget
  tracker is now built per run and shared by the research stage,
  the entailment checker (which reserves per judging call and
  stops the run at the cap), and the model designer (which
  reserves per completion), across the CLI run commands, target
  runs, and the console. A3: the judge-swap flip count could
  never see a flip, because a differing judge focus fails
  stability and unlocks the spec before the count; the debate now
  records the original and swapped case calls per case
  (judge_swap original_outcome and swapped_outcome) and the
  runner counts calls the swap changed, still reporting
  not_evaluable when no swap ran. A4: a production sheet called
  a structure ready when its validity was unknown (RDKit
  unavailable) or its stereochemistry unassigned; readiness now
  requires positive validation and assigned stereocenters. A5: a
  unanimous explicit kill direction paired with a focus could
  lock and be scored as an advance; the agreement test now reads
  that combination as the panel's stated kill decision, and the
  baseline rule reads a kill dossier the same way. A6:
  schema-invalid model evidence could lock a spec; the response
  parser now returns a failure dossier for schema-failing output
  (its documented contract), and the evidence call and the
  candidate audit strike claims that fail the claim schema with
  reason schema_invalid. A7: repeated designs of one spec shared
  a run id and silently overwrote the earlier saved bundle;
  design run ids are now unique per execution, and write_bundle
  refuses to overwrite an existing bundle whose content differs.
  The README's test instructions now state the suite's actual
  requirements (pytest, plus RDKit for the structure tests).
- Full validation of the written record against the code and the
  run artifacts (2026-10-26, at the owner's direction): the test
  suite (288 passing), the Gate 0 validation and mock-debate
  quickstart results, the frozen MTCH2 bundle (byte-identical to
  the runs/ copy; envelope hashes verify at all three levels; 24
  panel claims, 15 supported / 9 partially supported entailment
  verdicts, 12 strikes all quote_not_in_full_text, 6 locked spec
  claims), the production sheets and build guides (formulas,
  molecular weights, InChIKeys, and both HRMS values recomputed
  with RDKit and matching exactly), the receptor file (303
  residues, 2,335 atoms, mean pLDDT 86.3 per residue), the
  vendored 3Dmol.js banner (v2.5.5; its LICENSE file byte-identical
  to the npm package's), and the validation run numbers in
  docs/PHASE1_SPEC.md and docs/VALIDATION_RUN_2026-10-25.md against
  the run reports all check out. Two wording corrections resulted.
  The designer output was described as simply "untested", which
  erased the validation the runs did perform; the standing text
  now credits the computational validation on record (mechanical
  audits, RDKit structure checks, design gate, hash verification)
  and states the remaining gap plainly: no candidate has been
  synthesized or assayed. And docs/PHASE1_SPEC.md no longer says
  prospective runs wait for Gate 0 to pass, which the owner's
  2026-10-25 Gate-0-optional decision superseded.
- The Gate 0 runner counted judge-swap flips as 0 whenever no
  case carried a swap record, so a run in simple or dual mode (or
  a judgeless legacy run) recorded judge-swap stability as a pass
  on a test that never ran. The runner now passes the flip count
  as unknown when no swap ran, and the threshold evaluation
  records not_evaluable. The validation run 4 record is corrected
  to match: four thresholds passed, stability not evaluable.
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

- Validation run 4, the first under a declared protocol mode
  (simple: three panel agents per case on one model, no judge),
  recorded in docs/VALIDATION_RUN_2026-10-25.md and the spec's
  validation record: debate 7 of 8, baseline 8 of 8, zero audit
  strikes, four thresholds passed, baseline margin failed
  at -1, judge-swap stability not evaluable (not applied in
  simple mode), run outcome fail.
- Gate 0 validation is now optional for the production program
  (owner's decision, 2026-10-25, recorded in docs/PHASE1_SPEC.md):
  live frame runs and Phase 2 design no longer wait on a scored or
  passing Gate 0 run. Thresholds and honest pass/fail reporting of
  any validation run are unchanged.
- docs/LIVE_RUN.md: the live run runbook (what a live run needs,
  the three modes in brief, the providers-check, dry-run,
  providers-smoke, run sequence, and what comes back).
- Three protocol modes for runs, selected by the config's mode
  field: simple (every research agent on one and the same model, no
  judge), dual (research agents across two models, no judge), and
  dual_judge (two models plus a judge model, the full protocol).
  Modes count distinct models, not agents; every mode fields at
  least two research agents. In simple and dual the judge-swap
  stability test is recorded as not applied rather than failed, so
  a specification can lock on agreement, survival, and the evidence
  floor. Config validation and the runner both enforce each mode's
  shape before any provider is called, bundles and reports record
  the mode, and the shipped example config now runs dual_judge. A
  run with no mode keeps the original behaviour exactly.
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
  list; sealed outcomes (gate0/sealed/) are read by dataset validation
  and at scoring time, and are never given to agents.
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
