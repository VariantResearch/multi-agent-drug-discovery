```
            O
            ||
      C-----C
     /       \
   C           C----N
     \       /
      C-----C
            |
            C----S
```

# Multi-Agent Drug Discovery (MADD)

MADD is a provider-neutral system for multi-agent drug discovery research. Several AI research agents independently study the same drug program from the same pre-outcome evidence, a structured debate compares their work, and mechanical auditors - not the models - decide whose evidence survives. The system's rule is simple: no claim counts unless it rests on a real, checkable primary source, and no model gets to grade its own homework.

This repository contains the complete working application: the research and debate engine, the evidence auditors, the Gate 0 retrospective test set of eight real drug programs, the run orchestration, adapters for live models, and a command line interface. The only thing not included is the models themselves: choose a roster, supply API keys, and it runs.

## What it does

For each drug program under study, the application:

1. Frames the question with a cutoff date, so agents judge the program on the evidence that existed at the time, not on how things turned out.
2. Sends the frame to several research agents at once. Each works blind, without seeing the others, and returns a structured dossier of claims. Every claim names its source (a PubMed, DOI, or ClinicalTrials.gov identifier), its evidence tier, and a supporting quote.
3. Runs an evidence call. A claim ledger audit and a citation audit strike any claim that is unsourced, sourced to model opinion, malformed, or - when live resolution is switched on - pointing at a registry record that does not exist. Struck claims take no further part.
4. Debates the surviving dossiers: structured cross-examination, a red-team round whenever the agents agree too quickly, pairwise ranking on audited evidence scores only, and one evolution round that merges the best material.
5. Applies four consensus tests (agreement, survival, evidence floor, stability under a judge swap). Only when all four pass does the run lock a target specification. Otherwise it ends in a no-go, with the disagreements preserved in a dissent log instead of averaged away.
6. Freezes the whole run - dossiers, strikes, transcripts, manifest with per-call prompt hashes - into a hashed, verifiable run bundle with a plain-language report.

On top of that sits Gate 0, the retrospective test: eight real, completed drug programs, four that succeeded and four that failed, with inputs frozen at pre-outcome evidence and outcomes sealed. A run of the system over Gate 0 is scored against pass thresholds that were fixed and approved before any run took place.

## Requirements

- Python 3.11 or newer.
- Nothing else. The package uses only the Python standard library: there are no dependencies to install.
- For live model runs, API keys for the providers in your run configuration, set as environment variables (see Run a full Gate 0 run below). No key is needed for the mock workflows, the auditors, or the test suite.

## Quick start (no models, no keys)

Clone the repository and run the built-in checks and the mock debate:

```
git clone https://github.com/VariantResearch/multi-agent-drug-discovery.git
cd multi-agent-drug-discovery
python3 -m unittest discover -s tests
python3 -m madd gate0-validate
python3 -m madd gate0-list
python3 -m madd debate-mock examples/synthetic/frame.json --judge
```

Expected results: the test suite passes (150 tests), Gate 0 validation prints PASS, and the mock debate ends in an honest no_go - the mock provider's one claim is invented and unsourceable, so the evidence call strikes it.

Try the auditors on the synthetic example dossier:

```
python3 -m madd audit-claims examples/synthetic/dossier.json
python3 -m madd focus-score examples/synthetic/dossier.json
python3 -m madd validate-artifact dossier examples/synthetic/dossier.json
python3 -m madd check-tool Boltz-2
python3 -m madd resolve-citations examples/synthetic/dossier.json
```

The first four run offline. resolve-citations makes live lookups against PubMed, Crossref, and ClinicalTrials.gov, and on this invented dossier it correctly reports the invented identifiers as not found or badly formatted, since none of them exist in any registry.

## The MADD Console (GUI)

A retro cyberpunk web interface ships with the package, in the synthwave theme (near-black, neon pink, purple, cyan, laser rules, grid backdrop, a scanning laser line over the header):

```
python3 -m madd gui
```

Open http://127.0.0.1:8765. The console has run control (check a config, dry-run it, run Gate 0 and watch the per-case progress live), the Gate 0 scoreboard, and a run library with per-run scores, threshold checks, styled HTML reports, and debate transcripts. It binds to localhost only and has no authentication - it is a local tool, and running a config from it executes that config exactly as the CLI would. Options: --port, --host, --runs-dir, --gate0-dir.

## Run a full Gate 0 run

A run is described by a JSON configuration file naming the providers, the judge, the baseline model, and the budget. Start from the shipped example:

```
cp examples/run-config.example.json my-run.json
```

Edit my-run.json: replace each REPLACE-WITH-MODEL-ID and REPLACE-WITH-FAMILY with the models you have chosen, and set each provider's cost_per_call_usd if you want the budget tracker to account in dollars (a budget with a call cap alone also works). Then set the API keys the config names, in the environment only - never in the file:

```
export OPENAI_API_KEY="your key"
export ANTHROPIC_API_KEY="your key"
```

Check the configuration before spending anything. This builds every provider object and reports which key variables are set; it makes no network calls:

```
python3 -m madd providers-check --config my-run.json
python3 -m madd run-gate0 --config my-run.json --dry-run
```

The dry run counts the calls the run will make and prices them from the config, without making any. One step further, providers-smoke makes exactly one small billable call per configured provider and reports latency, the model string the service returned, and usage - the account-level proof that a provider works before a scored run depends on it. It prints the call count before making any:

```
python3 -m madd providers-smoke --config my-run.json
```

Run Gate 0. The baseline model runs first, alone, then the debate runs per case, both are scored against the sealed outcomes, the approved thresholds judge the result, and the full bundle is written under runs/:

```
python3 -m madd run-gate0 --config my-run.json --out runs
```

The command prints both scores and every threshold check, and exits 0 on a pass, 1 on a fail, 2 when the run itself stopped (bad config, budget cap reached, provider error). Output lands in runs/<run-id>/ as bundle.json (the complete frozen record), report.md (the readable report), and gate-report.json, with runs/index.json listing every run.

To run the same machinery on a new question rather than the Gate 0 set, write a frame file (see examples/synthetic/frame.json for the shape) and run:

```
python3 -m madd run-frame my-frame.json --config my-run.json --out runs
```

A frame run locks a specification or ends in a no-go, and writes the same bundle and report.

To try the full pipeline with no keys at all, save this all-mock configuration as mock-run.json and run it. The mocks return the same invented dossier for every case, endorse nothing, and the run fails the thresholds honestly - which is the correct result for a panel that did no research:

```
{
  "providers": [
    {"name": "panel-a", "kind": "mock", "label": "a"},
    {"name": "panel-b", "kind": "mock", "label": "b"}
  ],
  "judge": {"name": "judge", "kind": "mock", "label": "j"},
  "baseline": {"name": "base", "kind": "mock", "label": "base"},
  "budget": {"max_calls": 500},
  "live_resolution": false
}
```

```
python3 -m madd run-gate0 --config mock-run.json --out runs
```

## Run configuration reference

Top-level fields:

- providers (required): at least two research agents.
- judge (optional): a third provider whose dossier supplies the judge-swap stability comparison. Without one, stability cannot be established and debates end in no-go.
- baseline (required for Gate 0 runs): the single model the debate system must beat.
- budget (optional): {"max_cost_usd": number, "max_calls": integer}. At least one cap is required when a budget is given; uncapped budgets are rejected. The cap is shared across the whole run, baseline included, and the run stops when it is reached.
- live_resolution (optional, default false): when true, the evidence call also strikes claims whose identifiers the live registries report as not found. A registry that cannot be reached never strikes anything.
- parallel_cases (optional, default 1): how many case debates may run at once. The bundle is assembled in case order either way; only wall time changes. run-gate0 --jobs overrides it.

Each provider entry:

- name: unique across providers, judge, and baseline.
- kind: "mock", "openai-compatible", or "anthropic".
- model: the provider's exact model identifier (not needed for mock).
- family: the model family label recorded in dossiers and manifests.
- base_url: endpoint base; defaults to https://api.openai.com/v1 for openai-compatible and https://api.anthropic.com/v1 for anthropic. Any compatible endpoint (OpenRouter, a local LM Studio or Ollama server, a gateway) works by changing this.
- api_key_env: the name of the environment variable holding the API key (not needed for mock).
- cost_per_call_usd: what one call costs, for budget accounting. The code invents no prices; leave it 0 and cap by calls if you prefer.
- max_tokens: response cap per call, default 4096.
- label: mock providers only; differentiates their output.

Every model receives the same research prompt (madd/prompting.py): supplied evidence only, no invented identifiers or quotes, honest unverified labels, and one JSON dossier back. A response that cannot be parsed becomes a dossier with no claims and the failure recorded, never a repaired invention. An HTTP error stops the run loudly instead: an outage must not be scored as a model failure.

## All commands

```
python3 -m madd audit-claims <file>            claim ledger + citation audit of a document
python3 -m madd check-tool <name>              license registry verdict for a tool
python3 -m madd focus-score <file>             deterministic score from audited evidence tiers
python3 -m madd validate-artifact <schema> <file>
python3 -m madd gate0-validate [--gate0-dir <dir>]
python3 -m madd gate0-list [--gate0-dir <dir>]
python3 -m madd gate0-report <predictions.json> [--baseline <file>]
                [--audit-violations <n>] [--judge-swap-flips <n>]
python3 -m madd gate0-new-case <case-id>       scaffold a new case (templates, fails validation until completed)
python3 -m madd resolve-citations <file>       live registry lookups for a document's claims
python3 -m madd debate-mock <frame.json> [--judge] [--out <file>]
python3 -m madd providers-check --config <file>
python3 -m madd providers-smoke --config <file>   one billable call per provider, reported
python3 -m madd run-gate0 --config <file> [--out <dir>] [--dry-run] [--jobs <n>]
python3 -m madd run-frame <frame.json> --config <file> [--out <dir>]
python3 -m madd compare-runs <bundle-a> <bundle-b>
python3 -m madd transcript <record-or-bundle.json>
python3 -m madd report-html <bundle.json>
python3 -m madd gui [--port 8765] [--runs-dir runs]
```

Finished run folders also carry report.html (the styled report), transcripts of every debate, and gate-report.json, next to bundle.json and report.md. compare-runs diffs two Gate 0 bundles: score deltas, exactly which case calls flipped, and which thresholds changed status.

A predictions file for gate0-report maps case ids (see gate0-list) to "advance" or "kill". Example: {"evolocumab-pcsk9-cvd": "advance"}.

Installing the package instead of running it from the checkout also works, and provides the same commands as the madd entry point:

```
pip install .
madd gate0-validate
```

## Gate 0: the retrospective test set

Eight real cases, inputs frozen at pre-outcome evidence, outcomes sealed, every input claim quote-checked by hand against its primary source at construction (the ledger is gate0/VERIFICATION_LEDGER.md).

Positive controls (the programs worked): evolocumab / PCSK9, ivacaftor / CFTR, semaglutide / GLP-1R, erenumab / CGRP receptor.
Negative controls (the programs failed): verubecestat / BACE1, PF-05089771 / Nav1.7, BEN-2293 / pan-Trk, REC-994 / CCM.

Pass thresholds, approved 2026-10-22 and recorded in docs/PHASE1_SPEC.md before any scored run: kill at least 3 of the 4 failures; advance at least 3 of the 4 successes; beat the single-model baseline by at least 1 case; zero audit violations; a judge swap may flip at most 1 of 8 calls. A run must also be complete - every case called - or it cannot pass at all.

One honest caveat: these outcomes are famous, and frontier models may remember them despite the blinded inputs and cutoff dates. Gate 0 v1 is therefore a calibration and regression set, not a pristine blind test. A prospective set with a preregistered analysis is a later phase's work.

Status today: no scored Gate 0 run has taken place. The thresholds are approved; the model roster and the budget figure are the owner's recorded decisions, still to be entered in docs/PHASE1_SPEC.md. Anything in examples/ labelled synthetic is invented test material and is not evidence about any real drug program.

## How the evidence rules work

- Evidence tiers: 1 human causal genetics, 2 human clinical or randomised, 3 human observational or biomarker, 4 animal or in-vivo, 5 in-vitro, computational, or indirect.
- A focus score counts audited claims only, weighted by tier, with each claim counted once no matter how often it is repeated. Model confidence, prose quality, and vote counts are never inputs.
- The license registry records which discovery tools may be used for which purpose: Boltz-2 (MIT) and Chai-1 (Apache-2.0) are allowed; AlphaFold 3 and ESM3-open are blocked for commercial use by their terms.
- Every run artifact is canonicalised and hashed, so a record shown later can be checked against the record that was frozen at run time.

## Repository layout

```
madd/            the package (standard library only)
  runner.py        full Gate 0 runs and frame runs
  debate.py        the debate engine (protocol steps 1 to 7)
  providers_http.py  live provider adapters (OpenAI-compatible, Anthropic)
  providers.py       the provider interface and the mock provider
  prompting.py       the shared research prompt and response contract
  config.py          run configuration loading and validation
  claims.py          the claim ledger audit
  citation_auditor.py  offline identifier format and consistency checks
  resolve.py         live citation resolution (PubMed, Crossref, ClinicalTrials.gov)
  consensus.py       the four consensus tests
  focus.py           the deterministic focus score
  gate0.py           the Gate 0 dataset tools, scorer, and threshold evaluator
  budget.py          the shared run budget tracker
  artifacts.py       canonical hashing, manifests, frozen records
  schemas.py         artifact schema validation
  license_registry.py  tool license checks
  storage.py         run bundle persistence and index
  report.py          the plain-language run report
  html_report.py     the styled, self-contained HTML report
  transcript.py      debate records rendered as readable transcripts
  compare.py         run-to-run comparison
  smoke.py           one-call provider smoke tests
  gui.py             the MADD Console web interface (stdlib server)
  cli.py             the command line interface
gate0/           the Gate 0 dataset: input/, sealed/, ledger, case notes
docs/            design documents and phase specifications
examples/        the example run config and synthetic fixtures
tests/           the test suite
runs/            run output (created by runs, gitignored)
```

Key documents: docs/PHASE1_SPEC.md (scope, approved thresholds, run protocol), docs/DEBATE_PROTOCOL.md (the seven steps), docs/EVIDENCE_POLICY.md (what counts as evidence), docs/GATE0_NOTES.md (how the test set was built), docs/DESIGN-REFERENCES.md (patterns borrowed from other projects, with sources), docs/DECISIONS.md (the decision log), RESPONSIBLE_USE.md (use boundaries).

## Contributing and license

Contributions are welcome under the rules in CONTRIBUTING.md: the test suite must pass, no fabricated citations anywhere including tests and docs, and synthetic material stays labelled synthetic. The project is Apache-2.0 (see LICENSE). Its own tools check the licenses of other tools before use; a tool with unverified terms is blocked, not assumed fine.
