# Phase 1 Specification - Debate Engine

Status: APPROVED by the project owner on 2026-10-22. The thresholds
below are in force from that date. Two items remain open and are marked
as such where they appear: the model roster, and the budget figure,
which must be recorded in this file before the first scored run. No
scored Gate 0 run may be reported against thresholds that were chosen
after the run.

Implementation status, 2026-10-25: the full Phase 1 machinery is
built - debate engine (madd/debate.py), budget tracker
(madd/budget.py), threshold evaluator (madd/gate0.py
evaluate_thresholds), live citation resolution (madd/resolve.py),
run orchestration (madd/runner.py), provider adapters for the
OpenAI-compatible and Anthropic wire protocols
(madd/providers_http.py) behind one prompt and response contract
(madd/prompting.py), run configuration (madd/config.py), and bundle
storage with plain-language reports (madd/storage.py,
madd/report.py), all driven from the CLI. The adapters are tested
against fake transports shaped from the documented wire formats;
they have not been run against a real model account. On 2026-10-25,
at the owner's direction, the full pipeline was validated end to
end with the owner's own agents standing in as providers (see the
validation run record below and docs/VALIDATION_RUN_2026-10-25.md).
That run was judged against the approved thresholds and failed the
failure kill rate (2 of 4 negatives killed, 3 required); it is not
a scored Phase 1 run, because this spec's roster and budget were
never recorded for it. What remains before the first scored run is
exactly what this spec reserves to the owner: record the model
roster and the budget figure above, and supply the API keys through
the environment. No scored Gate 0 run has taken place, and nothing
in this repository is a Phase 1 result.

## Purpose

Phase 1 connects real models to the Phase 0 backbone and answers one
question: does the debate process find better targets than one good
model working alone? If the answer is no, the project simplifies to a
single model plus the auditor, and says so in the changelog. That is a
valid outcome of this phase, not a failure to be edited away.

## Scope

In scope:

- A provider adapter that can call at least three different frontier
  model families plus one open-weight model, through one interface,
  with model name, version, settings, and prompt hashes written to the
  run manifest for every call.
- The research stage: each model gets the same frame and the same
  Gate 0 input pack, works alone, and returns a sealed dossier in the
  existing schema.
- The debate stage, run exactly as written in docs/DEBATE_PROTOCOL.md:
  cross-examination, evidence calls to the auditor, pairwise ranking,
  one evolution round, the four consensus tests, and a dissent log.
- A single-model baseline: one model, chosen before the run and named
  in the run record, answers each Gate 0 case alone with no debate and
  no auditor strikes beyond the standard claim audit. The debate system
  is scored against this baseline, not against a feeling.
- Scoring with madd/gate0.py score_run, which reads the sealed outcomes
  only at scoring time.
- Hard per-run and per-phase budgets, set before the run, displayed
  during the run, and enforced by stopping the run when they are hit.

Out of scope for Phase 1: candidate design, molecule or peptide
generation, any external submission, and any prospective (new target)
run. Prospective runs come after Gate 0 is passed, not before.

## Approved thresholds

Approved by the project owner on 2026-10-22, as proposed in the draft
of the same date. Changing any value below after a scored run has
started requires a new run record and a changelog entry saying why.

1. Failure kill rate: the debate system must call at least 3 of the 4
   known negative Gate 0 cases a no-go.
2. Positive advance rate: the debate system must advance at least 3 of
   the 4 known positive cases.
3. Baseline margin: the debate system must score at least 1 case more
   correct, in total, than the single-model baseline on the same eight
   cases. A tie means the debate added cost without adding accuracy,
   and the simplification rule in Purpose applies.
4. Audit integrity: zero load-bearing claims in any final dossier may
   rest on a struck or unverified citation. One violation fails the
   phase regardless of the case score.
5. Stability: swapping the ranking judge to a different model family
   must not change the winning call on more than 1 of the 8 cases.
6. Budget: a full eight-case run, debate plus baseline, must complete
   within the per-run budget recorded in the run manifest. The budget
   figure itself is set by the owner when API access is arranged, and
   is recorded here before the first scored run.

The owner may also decide that both models in a pair must come from
different providers for a result to count as cross-family. That rule is
recommended but left as an owner decision.

## Model roster (owner decision, still open)

No model is named as approved in this specification. The run needs:

- Three frontier model families from three different providers.
- One open-weight model that can be run or hosted independently, as the
  reproducibility baseline.
- API access and keys supplied by the owner through the secure vault or
  environment, never committed to this repository.

Until the owner records the roster here, Phase 1 code may be built and
tested against the mock provider only. The one exception so far is
the owner-directed validation run of 2026-10-25, recorded below,
which used the owner's own agents as providers; it does not name or
imply a roster.

## Validation run record (2026-10-25)

At the owner's direction, the production pipeline was run end to
end with the owner's own agents as providers: 40 independent agents
produced the panel, judge, and baseline dossiers from the blinded
production frames, and 9 more judged entailment, with live
resolution, live quote checking, entailment checking, and the
retrieval-first rule all on. Run id
gate0-validation-agent-panel-2026-10-25; full report in
docs/VALIDATION_RUN_2026-10-25.md.

Result: debate 6 of 8 correct, baseline 5 of 8. Judged against the
approved thresholds above: run completeness passed (8 of 8),
positive advance rate passed (4 of 4), baseline margin passed (1),
audit integrity passed (0 violations), judge-swap stability passed
(0 flips), and the failure kill rate failed (2 of 4 killed; 3
required). The run outcome under the approved rules is fail. The
two missed negatives (PF-05089771, verubecestat) were advanced by
every agent on tier 1 genetics evidence, the same call the field
made pre-outcome.

One calibration finding from the run was repaired the same day, at
the owner's direction: the live quote check searched the open full
text only, while Gate 0 pack quotes are drawn from abstracts, and
the deposited full text XML does not always carry the published
abstract verbatim (for the struck REC-994 source, PMC9311989, the
XML abstract section is worded differently from the record
abstract). The check now searches the record's abstract as well as
the full text: a quote found in either is quote_found, and a strike
still requires the full text to have been retrieved with the quote
absent from both, so the abstract can clear a quote but never
strike one. Live-verified on the struck quote, which now resolves
quote_found, with a fabricated control quote still returning
quote_not_found. The validation results above stand as executed
under the rule as it then was; the fix applies to future runs.

The owner ordered the run repeated with repairs applied. Run 2
(gate0-validation-agent-panel-r2-2026-10-25, same day, fresh
panel, repaired quote check): debate 6 of 8, baseline 5 of 8; the
kill rate passed (4 of 4) and the positive advance rate failed
(2 of 4), run outcome fail. The advance failure was mechanical:
the consensus agreement test compared proposed focus labels as
exact strings, so ivacaftor and semaglutide failed agreement on
spelling despite unanimous advance judgment, and the 4 of 4 kill
rate was itself partly the same accident in reverse. The repair
is general and shipped: each Gate 0 pack declares a canonical
focus_id, the frame carries it, the research prompt instructs
models to copy it exactly when advancing, and the debate engine
canonicalizes any proposal naming the frame's target onto that
id, preserving the model's original string as proposed_focus_raw;
the prompt also states the advance standard (target association
alone is not a case for locking a specification). Full account in
docs/VALIDATION_RUN_2026-10-25.md.

Run 3 (gate0-validation-agent-panel-r3-2026-10-25, fresh panel,
repaired code): debate 7 of 8, baseline 7 of 8, zero audit strikes;
kill rate passed (3 of 4, including REC-994 killed unanimously and
PF-05089771 refused on a genuine panel split), advance rate
passed (4 of 4), audit integrity and judge-swap stability passed,
and the baseline margin failed (0; at least 1 required), run
outcome fail. With one model family in every seat the baseline
made the same call as the debate on all eight cases, so the
single-family configuration shows no measurable margin over its
own baseline, which is what that threshold exists to detect. The
remaining lever is the roster itself: different model families in
the panel seats, under the run protocol below.

Run 4 (gate0-validation-simple-2026-10-25, the first validation
under a declared protocol mode, simple: three panel agents per
case on one model, no judge, mode enforced by the shipped runner):
debate 7 of 8, baseline 8 of 8, zero audit strikes; kill rate
passed (4 of 4), advance rate passed (3 of 4; erenumab lost to a
split panel), audit integrity passed, judge-swap stability passed
vacuously (no judge in simple mode; the test is recorded
not_applied in every case record), and the baseline margin failed
(-1), run outcome fail. The lone baseline called every case
correctly, including both cases the panel split on.

These runs do not satisfy the run protocol below and change
nothing in it: the roster and budget above remain open, and the
first scored run still begins at step 1. Under the owner's
2026-10-25 decision (next section), Gate 0 validation is optional
for the production program, so the absence of a passing scored
run does not hold the program back.

## Run protocol for the first scored Gate 0 run

The scored run runs in dual_judge protocol mode (research agents
across two models, plus a judge model): the approved thresholds
include judge-swap stability, which only that mode applies. The
simple and dual modes exist for cheaper exploratory and validation
runs; a validation run in any mode may be judged against the
approved thresholds and recorded, without becoming the scored
Phase 1 run, which is dual_judge with the roster and budget
recorded above.

Gate 0 validation is an option, not a requirement (owner's
decision, 2026-10-25). The production program - live frame runs
under any protocol mode, and Phase 2 design on locked
specifications - may start and run without a scored Gate 0 run,
and without any validation run having passed. Validation remains
available at any time as a check on a configuration, and its
results are recorded when run; the thresholds above are unchanged,
and a validation run is still reported as passing or failing
against them, plainly. What the decision removes is the gate, not
the measurement.

1. Record in this file: the model roster with exact version
   identifiers, the baseline model, and the budget. (Thresholds were
   recorded and approved on 2026-10-22.)
2. Freeze the Gate 0 input packs at their current hashes. Any edit to a
   pack after this point starts a new run record.
3. Run the baseline first, seal its calls, then run the debate system.
4. Score both against the sealed outcomes. Publish the full run bundle
   (manifests, dossiers, debate transcripts, dissent logs, scores) in
   the repository, including the cases the system got wrong.
5. Write the result into the changelog in plain terms: passed, or did
   not pass, against the thresholds recorded in step 1.

## Risks specific to this phase

- Remembered outcomes: Gate 0 cases are well known, so a model may
  recall a result rather than reason to it. The baseline comparison
  partly controls for this, since the baseline model has the same
  memory. This limitation stays written in gate0/README.md and in every
  run report.
- Politeness collapse: models tend to concede to each other. The
  debate protocol's anti-groupthink rules (docs/DEBATE_PROTOCOL.md) are
  the countermeasure, and the meta-review of each transcript checks
  whether concessions cited evidence or only tone.
- Cost drift: debate rounds multiply API calls. The budget stop is a
  hard stop in code, not a guideline.
