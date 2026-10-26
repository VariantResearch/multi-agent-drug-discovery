# Live Run Runbook

How to start a live run: real model accounts, real calls, a real
bundle. Everything below is a command the CLI already supports;
nothing here is aspirational.

## What a live run needs

1. A run configuration (JSON) declaring the protocol mode and the
   providers. Start from examples/run-config.example.json
   (dual_judge) and replace the model ids and family names with the
   roster you intend to run.
2. API keys in environment variables. The config names the variable
   per provider (api_key_env); the key itself never appears in the
   config, the bundle, or any report.
3. For a scored Gate 0 run only: the model roster with exact version
   identifiers and the budget figure recorded in
   docs/PHASE1_SPEC.md first, per its run protocol. Exploratory and
   validation runs, and all frame runs, do not need this. Gate 0
   validation is an option, not a requirement for the production
   program (owner's decision, 2026-10-25, recorded in
   docs/PHASE1_SPEC.md).

## Protocol modes in one paragraph each

Modes count distinct models, not agents; every mode fields a
research panel of at least two agents under the same debate
protocol and evidence call.

- simple: every agent on one and the same model, no judge. The
  cheapest live configuration. The judge-swap stability test is
  recorded as not applied.
- dual: agents across two models, no judge. Stability likewise
  not applied.
- dual_judge: agents across two models plus a judge model. The
  full protocol, stability included, and the mode of the scored
  Gate 0 run. For the stability threshold to be evaluable, the
  config also needs a judge_swap entry: a second judge from a
  different model family than the judge. Without one the run
  still executes, but stability records not_evaluable and a
  scored run cannot pass that threshold.

## The start sequence

Run from the repository root. Substitute your config path.

```
python3 -m madd providers-check --config my-run.json
```

Validates the config (mode shape included) and reports each
provider's readiness without making a billable call.

```
python3 -m madd run-gate0 --config my-run.json --dry-run
```

Prints the call count and the estimated cost from the config's
per-call prices, and stops. Check the numbers against the budget
before going live.

```
python3 -m madd providers-smoke --config my-run.json
```

Makes exactly one small billable call per configured provider and
reports latency, the model string the service returned, and usage.
This is the account-level proof that every key and model id works
before a full run depends on them.

```
python3 -m madd run-gate0 --config my-run.json --out runs
```

The live Gate 0 run: baseline first, then the panel per case under
the configured mode, live resolution, quote checking, entailment,
and retrieval-first each on only if the config enables them. The
bundle lands in runs/<run-id>/ with the report and transcripts.

For a single prospective target instead of the Gate 0 set:

```
python3 -m madd run-frame --config my-run.json --frame my-frame.json --out runs
```

Add --retrieve to build the frame's evidence set live from Europe
PMC and hold citations to it.

## What comes back

Every run writes a frozen, hashed bundle: the dossiers, the audit
strike list, the consensus results (with not-applied tests named as
such), the scores, and the threshold verdict for Gate 0 runs, plus
a plain-language report. A run that fails the thresholds says so;
the bundle is the record either way.

## Stopping

The budget in the config is a hard stop enforced in code: when the
call or cost cap is reached, the run stops rather than overspending.
An HTTP error from a provider also stops the run loudly; an outage
is never scored as a model failure.
