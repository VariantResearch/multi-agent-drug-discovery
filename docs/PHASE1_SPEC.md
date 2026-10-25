# Phase 1 Specification - Debate Engine

Status: APPROVED by the project owner on 2026-10-22. The thresholds
below are in force from that date. Two items remain open and are marked
as such where they appear: the model roster, and the budget figure,
which must be recorded in this file before the first scored run. No
scored Gate 0 run may be reported against thresholds that were chosen
after the run.

Implementation status, 2026-10-24: the full Phase 1 machinery is
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
they have not been run against a real model account. What remains
before the first scored run is exactly what this spec reserves to
the owner: record the model roster and the budget figure above, and
supply the API keys through the environment. No scored Gate 0 run
has taken place, and nothing in this repository is a Phase 1 result.

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

No model is named as approved in this draft. The run needs:

- Three frontier model families from three different providers.
- One open-weight model that can be run or hosted independently, as the
  reproducibility baseline.
- API access and keys supplied by the owner through the secure vault or
  environment, never committed to this repository.

Until the owner records the roster here, Phase 1 code may be built and
tested against the mock provider only.

## Run protocol for the first scored Gate 0 run

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
