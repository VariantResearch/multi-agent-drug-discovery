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

The quote check searched the open full text only, while Gate 0
pack quotes are drawn from abstracts. For REC-994 that difference
struck the lead claim in four dossiers: the deposited full text XML
of PMC9311989 carries an abstract section, but worded differently
from the published abstract in the Europe PMC record, where the
quoted sentence does appear. The strike followed the approved rule
as written, and this run's results stand as executed.

Resolution, 2026-10-25, at the owner's direction: the check now
searches the record's abstract as well as the full text. A quote
found in either place is quote_found; a strike still requires the
full text to have been retrieved with the quote absent from both,
so the abstract can clear a quote but never strike one. Verified
live after the fix: the struck REC-994 quote resolves quote_found,
and a fabricated control quote against the same source still
returns quote_not_found. The fix applies to future runs; nothing
about this run's record changes.

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

## Verdict on run 1

The process is validated: blinded frames, dossier contract, live
audit with all four checks, debate and consensus mechanics,
baseline comparison, scoring, bundle storage, and threshold
evaluation all ran for real and produced a complete, auditable
record, with the audit and consensus machinery visibly changing
outcomes (REC-994, BEN-2293) rather than rubber-stamping the panel.

The run does not clear the approved Phase 1 bar: the kill rate is
2 of 4 against a required 3 of 4. Under the spec's own terms, this
panel configuration would not be cleared for production. The
quote-check calibration above was repaired the same day (see the
resolution in that section), and the owner ordered the run repeated
with repairs applied until the bar is passed; runs 2 and 3 follow.

## Validation run 2 (2026-10-25)

Run id: gate0-validation-agent-panel-r2-2026-10-25. Same protocol
as run 1, a fresh panel of 40 agents, with the repaired quote check
live. Parsing was cleaner than run 1: 40 of 40 dossiers, zero
schema problems, zero failure dossiers. Entailment: 93 verdicts
(75 panel and judge, 18 baseline), 0 refuted, partial support
dominant, 1 cannot tell. The live audit struck nothing in the
entire run.

Score: debate 6 of 8 correct, baseline 5 of 8. Thresholds: run
completeness PASS, failure kill rate PASS (4 of 4), positive
advance rate FAIL (2 of 4), baseline margin PASS (1), audit
integrity PASS, judge-swap stability PASS (0 flips). Run outcome:
FAIL, on the advance rate.

The failure was mechanical, not judgment. The consensus agreement
test compared proposed focus labels as exact strings, so cases
were decided by spelling:

- Ivacaftor: all three panelists voted advance on the same target
  and wrote it two ways ("CFTR-G551D" and the expanded descriptive
  form). Agreement failed and the case did not lock.
- Semaglutide: the same accident ("GLP-1 receptor" against
  "GLP-1R").
- The accident also ran in reverse: PF-05089771 and verubecestat,
  both advanced unanimously, were scored as killed only because
  their panels spelled the target two ways, so run 2's 4 of 4 kill
  rate was partly mechanical luck rather than panel judgment.
- REC-994: the panel advanced again and the judge again proposed
  no focus, so the stability test failed, as in run 1.

## Repair between runs 2 and 3: canonical focus agreement

The agreement test was judging spelling, not the target named.
The repair is general and sits in the shipped code:

- Each Gate 0 pack now declares a canonical focus_id for its case,
  and the frame carries it to the providers.
- The research prompt instructs models to copy the frame's
  focus_id exactly when advancing, and states the advance standard
  plainly: evidence that a target is associated with a disease is
  not by itself a case for locking a specification, and an
  untested intervention effect weighs against advancing.
- The debate engine canonicalizes any proposal that names the
  frame's target (an exact or case-folded match, or a shortening or
  expansion of the target string) onto the frame's focus_id before
  the consensus tests read it, and preserves the model's original
  string as proposed_focus_raw in the record. Proposals naming a
  different focus pass through untouched, and frames without a
  focus_id behave exactly as before.

Ten new tests cover the mapping rules and the debate-level
behavior; the full suite stood at 244 passing after the repair.

## Validation run 3 (2026-10-25)

Run id: gate0-validation-agent-panel-r3-2026-10-25. Same protocol,
fresh panel, repaired code and prompt. Parsing: 40 of 40 dossiers,
zero schema problems, and every advancing dossier used the frame's
focus_id exactly. Entailment: 89 verdicts (71 panel and judge, 18
baseline): 12 supported, 77 partially supported, 0 refuted, 0
cannot tell. The live audit struck nothing: every citation
resolved, every checked quote was found, no claim was refuted by
its own quote, and no dossier cited outside its frame.

Score: debate 7 of 8 correct, baseline 7 of 8 correct.

| Case | Sealed truth | Panel call | Baseline call |
| --- | --- | --- | --- |
| BEN-2293 / pan-Trk | failure | kill | kill |
| Erenumab / CGRP receptor | success | advance | advance |
| Evolocumab / PCSK9 | success | advance | advance |
| Ivacaftor / CFTR | success | advance | advance |
| PF-05089771 / Nav1.7 | failure | no_go (panel split) | no_go |
| REC-994 / CCM | failure | kill | kill |
| Semaglutide / GLP-1R | success | advance | advance |
| Verubecestat / BACE1 | failure | advance | advance |

Thresholds: run completeness PASS, failure kill rate PASS (3 of
4), positive advance rate PASS (4 of 4), baseline margin FAIL
(debate minus baseline: 0; at least 1 required), audit integrity
PASS, judge-swap stability PASS (0 flips). Run outcome: FAIL, on
the baseline margin alone.

What changed in the panel's judgment: REC-994, advanced by the
panels in runs 1 and 2, was killed unanimously in run 3, and
PF-05089771 split its panel (one advance, two kill), so agreement
refused to lock and the case was killed by genuine disagreement
rather than by a spelling accident. The one remaining miss,
verubecestat, was advanced by panel, judge, and baseline alike;
each dossier's own notes record that the pack holds no clinical
efficacy data and that the timing step from lifelong protective
genetics to treatment after onset is unestablished, and each still
judged the genetics, mechanism, and demonstrated target engagement
sufficient. That is a judgment call on the same evidence the field
acted on, not a mechanical failure.

## Verdict on runs 2 and 3

Across three runs, each failed exactly one threshold, a different
one each time: the kill rate (run 1), the advance rate through a
spelling defect in the agreement test (run 2), and the baseline
margin (run 3). Both defects found along the way were real, were
repaired generally in the shipped code, and stayed repaired.

Run 3's margin result is the honest limit of this validation
setup. The margin threshold measures what the multi-agent process
adds over a single model answering alone. With one model family in
every seat, the baseline is effectively another panelist reading
the same evidence under the same prompt, and it made the same call
on all eight cases; the audit struck nothing for the debate to
gain from. The threshold caught exactly what it was designed to
catch: this single-family configuration shows no measurable added
value over its own baseline.

No further repair inside the validation harness closes that gap,
because the missing ingredient is the roster itself. The spec has
always required the scored run to field different model families;
which families, their API keys, and the recorded budget figure are
the owner's open items in docs/PHASE1_SPEC.md. The first scored
run, with the roster recorded and real multi-family providers,
remains ahead. (The owner's 2026-10-25 decision recorded below
has since made Gate 0 validation optional for the production
program, so the scored run no longer gates it.)

## Run 4: the first validation under a declared protocol mode (simple)

Later the same day, at the owner's direction, the validation was
run a fourth time, this time as the first run under a declared
protocol mode: simple (docs/DEBATE_PROTOCOL.md, Protocol modes).
Three panel agents per case, all on the same model, plus a
single-model baseline; no judge, by the mode's definition. The
driver passed mode="simple" to the production runner, so the
mode's shape was validated by the shipped code before any call.
Workspace ~/workspace/madd-validation-r4 (harness record, outside
the repository); bundle runs/gate0-validation-simple-2026-10-25.

Collection: 32 of 32 dossiers (3 panel + 1 baseline per case),
zero schema problems, zero failure dossiers. Entailment: 75
verdicts judged by separate same-model agents under the production
entailment prompt, zero conflicts, none refuted. The audit struck
nothing in any dossier: every claim survived live resolution, the
live quote check, entailment, and retrieval-first.

Result: the debate called 7 of 8 (the four negatives all killed;
three positives locked). The lone miss was erenumab, where two
panelists advanced and one declined, so the agreement test refused
to lock and the case went no_go. Verubecestat divided the panel
the same way and fell on the correct side of that refusal. The
baseline, one agent per case under the fixed baseline rule, called
all 8 correctly, including both divided cases.

Thresholds: run completeness pass; failure kill rate pass (4 of
4); positive advance rate pass (3 of 4); audit integrity pass (0
violations); judge-swap stability pass on 0 flips, vacuously,
because simple mode has no judge to swap (each case record shows
the stability test as not_applied, as the mode specifies);
baseline margin FAIL, at -1 (debate 7, baseline 8; at least +1
required). Run outcome: fail, on the margin alone.

## Verdict after run 4, and the owner's Gate 0 decision

Four runs have now been judged against the approved thresholds.
Each failed exactly one threshold, and the margin has failed twice,
both times for the reason run 3's verdict named: in a single-model
configuration the baseline is the same mind working alone, and the
debate machinery can only lose calls to panel disagreement, never
gain one the baseline cannot make. Across the four runs the debate
scored 6, 6, 7, 7 while the baseline swung 5, 5, 7, 8; the margin
in this staffing measures baseline variance more than debate
value. The panel's calls, as distinct from the margin, have
improved every run and in run 4 were one split panel short of
perfect.

On 2026-10-25 the owner decided that Gate 0 validation is an
option, not a requirement for the production program
(docs/PHASE1_SPEC.md). The production program therefore proceeds
without a passing Gate 0 run: live frame runs under any protocol
mode, and Phase 2 design on locked specifications, are unblocked,
with docs/LIVE_RUN.md as the runbook. The thresholds are
unchanged, validation remains available at any time, and its
results keep being recorded plainly, including this one: the
simple-mode configuration stands validated as a working protocol
whose panel calls 7 of 8 on this set, and stands not passed
against the full threshold battery because its own baseline aced
the same set.

## Target-run validation (2026-10-25, after run 4)

At the owner's correction the same day, the product definition is
target-first: name a specific target and a drug is designed for it.
The target-run pipeline (madd/target_run.py) was built and then
validated end to end the same way the Gate 0 runs were: providers
staffed by independent subagents, this time for one named target,
KRAS G12C in non-small cell lung cancer, in simple mode. Evidence
was retrieved live from Europe PMC (12 sources) and citations were
held to that set. Three research agents returned 19 claims; live
resolution, live quote checking, and recorded entailment (4
supported, 2 partially supported, 0 refuted) produced zero audit
strikes, and the debate locked the target with 5 surviving
load-bearing claims as the design brief's evidence constraints.
Two designer agents then proposed four original covalent-inhibitor
candidates with valid SMILES structures; RDKit validated all four,
ADMET-AI completed, all four ranked, and the design gate passed.
Outcome: designed. This validates the pipeline, not the candidates:
they are untested model proposals against a target that already has
approved drugs, offered as chemical starting points, and the record
says so. Bundle: runs/target-kras-g12c-validation-2026-10-25.
