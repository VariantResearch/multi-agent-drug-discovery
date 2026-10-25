# Gate 0 retrospective test set, v1

Gate 0 is the retrospective test set described in docs/PHASE0_SPEC.md:
before the system is trusted on a new question, it is run blinded on
historical cases with known outcomes, to measure whether its ranking and
strike behaviour would have pointed at the outcomes that were actually
observed.

Every case here is a real historical drug program. Every input claim
rests on a primary source that was fetched and read during dataset
construction, recorded in VERIFICATION_LEDGER.md. No case, claim, number,
or date in this directory is synthetic. Synthetic fixtures exist only in
tests/ and examples/synthetic/ as code plumbing, always labelled
synthetic, never as research content.

## Layout

- input/<case_id>.json: the blinded input pack an agent receives. It
  carries the real drug, target, disease, modality, and sponsor, an
  evidence_as_of date set before the pivotal outcome was public, and a
  claims array following the repo Claim schema. Input claims cover only
  pre-outcome rationale: human genetics or Mendelian evidence, human
  expression or pathway evidence, prior human clinical signals available
  before the cutoff, and known risks at the time. Each input pack also
  carries its own forbidden_terms list of outcome-revealing words and
  phrases, used by the leakage scan in madd/gate0.py.
- sealed/<case_id>.outcome.json: the sealed outcome for the case: its
  outcome class, the pivotal result stated narrowly with the numbers as
  the primary source states them, the outcome source identifier, the
  date the result became public, and a one-line reason class. Sealed
  files are read only at scoring time (madd.gate0.score_run). Agents
  never receive them.
- VERIFICATION_LEDGER.md: one row per claim and per outcome, with the
  identifier, source title, fetch date, and verdict, plus the leakage
  limitation statement.
- REJECTED.md: cases or sources that did not survive verification, with
  reasons. An empty rejection list is recorded there explicitly.

## Cases

Outcome classes are deliberately not shown in this table; they live only
in sealed/.

| Case id | Drug | Target | Disease | Evidence as of |
|---|---|---|---|---|
| evolocumab-pcsk9-cvd | Evolocumab | PCSK9 | Atherosclerotic cardiovascular disease and hypercholesterolemia | 2017-03-16 |
| ivacaftor-cftr-cf | Ivacaftor (VX-770) | CFTR, G551D gating mutation | Cystic fibrosis | 2011-10-31 |
| semaglutide-glp1r-obesity | Semaglutide | GLP-1 receptor | Obesity | 2021-02-09 |
| erenumab-cgrpr-migraine | Erenumab | CGRP receptor | Episodic migraine (prevention) | 2017-11-28 |
| verubecestat-bace1-alzheimer | Verubecestat (MK-8931) | BACE1 | Alzheimer disease (mild-to-moderate) | 2017-02-01 |
| pf05089771-nav17-dpn | PF-05089771 | Nav1.7 (SCN9A) | Painful diabetic peripheral neuropathy | 2018-02-28 |
| ben2293-pantrk-atopic-dermatitis | BEN-2293 | Pan-Trk (TrkA, TrkB, TrkC) | Atopic dermatitis (mild-to-moderate) | 2023-04-03 |
| rec994-ccm | REC-994 | Superoxide-mediated oxidative stress in CCM | Cerebral cavernous malformation (symptomatic) | 2025-05-04 |

The set contains 8 cases: 4 with positive pivotal outcomes and 4 with
negative pivotal outcomes, as recorded in sealed/.

## Running the checks

From the repository root:

    python3 -m madd gate0-validate
    python3 -m madd gate0-list
    python3 -m unittest discover -s tests

gate0-validate loads every input pack, checks every claim against the
Claim schema, the claim ledger rules in madd/claims.py, and the offline
citation format rules, enforces the quote and cutoff rules of this
dataset, runs the leakage scan, and confirms a sealed outcome exists for
exactly the same case ids. It exits non-zero on any error.
gate0-list prints case ids and diseases only, never outcomes.

## Pass criteria

Per docs/PHASE0_SPEC.md, Gate 0 pass criteria are numeric thresholds on
pre-declared measures, written and frozen before the first Gate 0 run.
The measures are the counts produced by madd.gate0.score_run: correct
calls, failures correctly killed, and positives correctly advanced.

The threshold values were set and approved on 2026-10-22, before any
scored run, and are recorded in docs/PHASE1_SPEC.md;
madd.gate0.evaluate_thresholds applies them. No Gate 0 run has been
performed with this dataset yet, and no score reported anywhere in
this repository is a Gate 0 result.
