# Gate 0 Agent-Panel Validation Run - Report

Date: 2026-10-25. Run id: gate0-validation-agent-panel-2026-10-25.
Ordered by the project owner: run the test protocol using the owner's
own agents to validate the process before production.

This is a validation run, not a scored Phase 1 run under
docs/PHASE1_SPEC.md: no owner-recorded model roster or budget figure
exists yet, and every provider role was staffed by the owner's own
agents. It is recorded here because it exercised the production
pipeline end to end and was judged against the approved thresholds.

## What was run

The production Gate 0 pipeline, unmodified, in its full production
configuration: live citation resolution, live full-text quote
checking, judge entailment checking, and retrieval-first citation
restriction all on. The only substitution was the providers: instead
of commercial model accounts, each role was filled by independent
agents whose answers were recorded and then served through the real
Provider interface, so the debate engine, evidence call, scoring,
and threshold code all executed exactly as shipped.

- Panel: 40 independent agents, 5 per case (panel-a, panel-b,
  panel-c, judge, baseline), each given the production system prompt
  and the production blinded frame verbatim, each answering with a
  dossier under the production contract, citing only the case pack.
- Parsing: every raw answer went through the production parser.
  40 of 40 parsed into dossiers; zero failure dossiers. One output
  had a schema defect the parser recorded itself (ben2293 judge,
  third claim, identifier_type type mismatch).
- Entailment: 91 claim-versus-quote judgments by 9 further agents
  under the production entailment prompt (73 panel and judge
  claims, 18 baseline claims). Results: 20 supported, 71 partially
  supported, 0 refuted, 0 cannot tell, and no disagreements on
  identical claim-and-quote pairs.
- Budget: capped at 200 calls and a 5.00 dollar cap as the budget
  rule requires; 40 calls were made. Per-call cost is recorded as
  0.0 because agent compute is unmetered, so the dollar cap could
  not trigger. That is stated here rather than hidden.
- Bundle: the run bundle (bundle.json, gate-report.json,
  report.md, report.html, transcripts) was written by the standard
  storage path under runs/gate0-validation-agent-panel-2026-10-25
  in the operator's workspace and is visible in the console run
  library. The runs directory is gitignored, so this report is the
  in-repository record of the run.

## Score

Debate panel: 6 of 8 correct. Baseline (single agent): 5 of 8.

| Case | Sealed truth | Panel call | Baseline call |
| --- | --- | --- | --- |
| BEN-2293 / pan-Trk | failure | kill | kill |
| Erenumab / CGRP receptor | success | advance | advance |
| Evolocumab / PCSK9 | success | advance | advance |
| Ivacaftor / CFTR | success | advance | advance |
| PF-05089771 / Nav1.7 | failure | advance | advance |
| REC-994 / CCM | failure | kill | advance |
| Semaglutide / GLP-1R | success | advance | advance |
| Verubecestat / BACE1 | failure | advance | advance |

## Thresholds (approved 2026-10-22, docs/PHASE1_SPEC.md)

- run_completeness: PASS - scored 8 of 8 cases.
- failure_kill_rate: FAIL - failures correctly killed: 2 of 4;
  the approved bar is at least 3.
- positive_advance_rate: PASS - positives correctly advanced:
  4 of 4; bar is at least 3.
- baseline_margin: PASS - debate correct minus baseline correct:
  1; bar is at least 1.
- audit_integrity: PASS - load-bearing claims resting on struck or
  unverified citations in the final records: 0; bar is 0.
- judge_swap_stability: PASS - case calls flipped by a judge swap:
  0; bar is at most 1.

Run outcome under the approved rules: FAIL, on the kill rate alone.

## What the audit did

Seven strike events, all traceable in the bundle:

- REC-994 debate, 5 strikes. Three panel dossiers each lost their
  lead genetics claim (PMID 35883785) to quote_not_in_full_text:
  the full text of PMC9311989 was retrieved live and the quoted
  sentence, which comes from the article abstract, does not appear
  verbatim in the body. One panel dossier (panel-b) also lost two
  further claims to citation_missing_identifier: it had written 5
  claims for a 3-claim pack, and the two extra claims carried no
  source identifier at all.
- Judge dossiers, 2 strikes: the same REC-994 abstract quote in the
  judge's own dossier, and the BEN-2293 judge's third claim (the
  one with the schema defect) for a missing identifier.
- Live resolution struck nothing: every cited identifier resolved.
  Retrieval-first struck nothing: no dossier cited a source
  outside its frame. Entailment struck nothing: no judge found a
  claim contradicted by its own quote, though 71 of 91 claims were
  judged only partially supported by the short quotes attached to
  them, which is the entailment prompt being strict as designed.

How the two kills happened:

- BEN-2293: the panel genuinely split (two kill dossiers, one
  advance). The consensus agreement test failed on the split, and
  the outcome was no_go. The process resolved disagreement by
  refusing to lock, which is the designed behavior.
- REC-994: all three panel dossiers advanced and agreement passed,
  but the stability test failed because the swap judge's own
  dossier declined to propose a focus. Outcome no_go. The baseline,
  which never faces a stability test, advanced the case and got it
  wrong; this single case is the entire baseline margin.

## The two misses

PF-05089771 and verubecestat were advanced by every agent, panel,
judge, and baseline alike. On the pre-outcome evidence in the
packs, both carried tier 1 human genetics support (SCN9A loss of
function abolishing pain; the protective APP A673T variant at the
BACE1 cleavage site), and both are cases where the field itself
advanced the program on that evidence and the program still failed.
No audit defect contributed: the citations are real, the quotes are
real, and the entailment judges found the claims supported or
partially supported. This is a judgment limit of a single model
family reading the same evidence the field read, not a pipeline
failure.

## Calibration finding for production

The quote check searches the open full text body only, while Gate 0
pack quotes are drawn from abstracts. For REC-994 that difference
struck the lead claim in four dossiers. The strike followed the
approved rule as written, and this run's results stand as executed.
Before the first scored run, the owner decides one of: extend the
quote check to search the abstract as well as the body, or keep
the strictness knowingly. Nothing was changed for this run.

## Caveats

- One model family staffed every role. The panel, judge, and
  baseline are independent agents but the same underlying model, so
  this validates the process end to end and does not test the
  multi-family hypothesis the production design rests on.
- The agents inherit the operator's conversation context, so prior
  knowledge of these programs' outcomes cannot be fully excluded.
  Gate 0 v1 is labelled a calibration and regression set for the
  same reason.
- Entailment was judged in per-case batches rather than one claim
  per call; the prompt text and verdict vocabulary were the
  production ones.
- The HTTP provider adapters remain untested against real model
  accounts; providers-smoke has still never run on a live account.

## Verdict

The process is validated: blinded frames, dossier contract, live
audit with all four checks, debate and consensus mechanics,
baseline comparison, scoring, bundle storage, and threshold
evaluation all ran for real and produced a complete, auditable
record, with the audit and consensus machinery visibly changing
outcomes (REC-994, BEN-2293) rather than rubber-stamping the panel.

The run does not clear the approved Phase 1 bar: the kill rate is
2 of 4 against a required 3 of 4. Under the spec's own terms, this
panel configuration would not be cleared for production. Moving to
production still needs, from the owner: the commercial model
roster and API keys, the recorded budget figure for PHASE1_SPEC,
and a decision on the quote-check calibration above. The first
scored run should then be run with real multi-family providers.
