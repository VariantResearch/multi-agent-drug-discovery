# Production Readiness

What stands between this repository and production use, item by
item, with the evidence for each claim. An item is listed as ready
only when it has been verified in the tree or on the remote, not
when it is planned.

## Ready, with evidence

- **Test suite.** The full suite passes from a clean checkout
  (471 tests at the last full run, 2026-10-27; the README carries
  the current count and a documentation test keeps it honest).
- **Packaging.** The core installs with `pip install .` and has
  no required dependencies. The design stack (RDKit, ADMET-AI,
  PoseBusters, Meeko) and PDF export (WeasyPrint) are declared as
  the `design`, `pdf`, and `all` extras with floors at the
  versions the recorded computations were produced with, so
  `pip install ".[design]"` reproduces the compute environment
  instead of discovering it from error messages. The package
  version has a single source (`madd.__version__`); the build
  reads it dynamically and `madd --version` reports it.
- **Console security.** Host allowlist, Origin and Referer checks
  on POSTs, a 1 MiB POST body cap, security headers and a content
  security policy on the page, and API keys handled as environment
  variable names plus presence booleans, never values. The trust
  model is written down in SECURITY.md: the mechanical audit is
  the load-bearing layer, prompt fencing is defence in depth.
- **Live-run procedure.** docs/LIVE_RUN.md is a complete runbook:
  providers-check (no billable calls), run-gate0 --dry-run (call
  count and cost estimate against the budget), providers-smoke
  (one small billable call per provider), then the run, with
  checkpoint and resume for long runs.
- **Evidence discipline.** Every designed candidate's values
  carry their basis (designer prediction, or computed with the
  tool and version named). Structural alerts are advisory flags,
  never exclusions. No composite candidate score exists. Run
  bundles are canonicalised and hashed at freeze time.
- **Data honesty in shipped outputs.** The two recorded designed
  runs are labelled demonstration work. No candidate has been
  synthesized or assayed, and no output of this system says
  otherwise.

## Owner gates (the owner's decisions, not engineering work)

- **Model roster.** The commercial models for production runs,
  recorded with exact version identifiers. Not yet entered.
- **Budget figure.** The run budget recorded in
  docs/PHASE1_SPEC.md. Not yet entered.
- **API keys.** One environment variable per configured provider,
  supplied by the owner at run time. Keys never enter the
  repository, a config file, or a bundle.
- **Scored Gate 0 run.** Optional by the owner's decision of
  2026-10-25 (production proceeds without it); the thresholds
  approved 2026-10-22 stand unchanged for whenever it is run.
- **Target lock.** No target is locked in. A production program
  starts when the owner names a target and accepts a proposal
  pack; until then every designed run is demonstration work.

## Operations gates

- **Console remote access.** The Cloudflare tunnel and Access
  application for madd.variantresearchgroup.com exist and the
  gate is fail-closed: no allow policy is in force yet. Opening
  it needs the owner to grant the API token two Access edit
  permissions, then an owner-only allow policy, then the
  connector running on the owner's PC beside the console. Until
  then the console is a local tool, which is a safe default.

## Release state

Version 0.1.0, no tag. Cutting a 1.0.0 release is an owner
decision that follows the owner gates above, not a substitute
for them; the packaging now supports it (single version source,
declared extras) when the owner calls it.
