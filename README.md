# Multi-Agent Drug Discovery

MADD runs the early part of drug discovery as a structured argument.

You start with a disease and the effect you want in a patient. Several AI
models then research possible targets on their own, without seeing each
other's work. After that they have to defend what they found in front of
each other. Claims that cannot be tied to a real source get removed.
Whatever survives becomes one target specification, and candidates are
designed against that specification only.

The point of the setup is to slow the models down. A single model will
give you a confident answer in seconds, and the citations behind it do
not always hold up. Here every load-bearing claim needs a source
identifier, an auditor checks it, and a red-team pass argues against the
leading target before anything is locked.

## Where it stands

This is early work. What is in the repo now:

- The data formats for each stage (frame, claims, dossier, consensus
  specification, candidate, gate report, run manifest), with hashing so
  a finished stage cannot be quietly edited later.
- A claim auditor and an offline citation checker. They reject claims
  with no source, claims resting on model opinion, and claims that have
  been struck.
- A live citation resolver that checks identifiers against the
  registries that own them: PubMed for PMIDs, Crossref for DOIs,
  ClinicalTrials.gov for trial numbers. It reports whether the record
  exists and the title the registry holds. It does not decide whether
  the source supports the claim built on it.
- A license registry for the design tools, so a model whose license
  forbids commercial use cannot slip into a commercial run.
- The consensus tests and a focus score that is calculated from the
  evidence behind a target, not from how confident a model sounds.
- The debate engine from docs/DEBATE_PROTOCOL.md: blinded dossiers, an
  evidence call that strikes bad claims, structured cross-examination
  (with a red-team round when everyone agrees too fast), pairwise
  ranking on audited evidence, one evolution round, the consensus
  tests, and a frozen, hashed record of the whole run.
- A budget tracker with a hard stop, so a run cannot drift past the
  cost or call cap set for it.
- Gate 0, a test set of eight real drug programs (see below), plus the
  code that judges a scored run against the pass thresholds in
  docs/PHASE1_SPEC.md.
- A command line tool and a mock model provider for testing.

Real models are not wired in yet. The debate engine runs against the
mock provider and test stubs today; it designs no molecule and runs no
experiment. The Gate 0 pass thresholds in docs/PHASE1_SPEC.md were
approved on 2026-10-22; the model roster is still to be chosen, and the
budget figure with it. The only network calls in the package are the
citation lookups named above.

## Gate 0

Before this system is trusted on a new target, it has to show it can
tell apart real programs that worked from real ones that failed, using
only the evidence that existed before the result was known.

gate0/ holds eight cases: evolocumab, ivacaftor, semaglutide and
erenumab on one side; verubecestat, PF-05089771, BEN-2293 and REC-994 on
the other. Each case is a blinded pack of pre-outcome evidence, with the
actual result kept in a separate sealed folder. Every claim in the packs
was checked against its primary source (PubMed, ClinicalTrials.gov, FDA
records, or the sponsor's own statement) and the ledger in
gate0/VERIFICATION_LEDGER.md shows the source for each one.

One honest caveat: these are famous programs, so a model may remember
how they ended. Treat Gate 0 as a calibration test, not a clean blind
trial. It is there to catch bad reasoning and bad citations, and it will
catch some of both.

## The rules that matter

These are enforced by the code where the code can enforce them. The
full policy is in docs/EVIDENCE_POLICY.md.

- A claim without a primary source does not count, no matter which
  model made it or how many models agree with it.
- Agreement between models is not evidence. It is just agreement.
- A struck claim is out. It does not get debated back in.
- Results are labelled by the highest test they actually passed. A
  candidate that passed a computer check is "computationally validated"
  and nothing more.
- Test fixtures for the code use invented data and say so. The research
  data in gate0/ is real, with sources.

Safety and scope rules (which targets are out of bounds, why a person
has to sign off before anything leaves the system) are in
RESPONSIBLE_USE.md.

## Running it

    python3 -m unittest discover -s tests -v
    python3 -m madd gate0-validate
    python3 -m madd gate0-list
    python3 -m madd audit-claims examples/synthetic/dossier.json
    python3 -m madd check-tool Boltz-2 --use commercial
    python3 -m madd check-tool "AlphaFold 3" --use commercial
    python3 -m madd debate-mock examples/synthetic/frame.json --judge
    python3 -m madd gate0-report predictions.json --baseline baseline.json
    python3 -m madd resolve-citations examples/synthetic/dossier.json

The audit of the synthetic dossier fails on purpose: it contains a claim
resting on model opinion, and the auditor is supposed to catch it. The
mock debate ends in a no-go for the same reason: the mock claim is
struck at the evidence call, so nothing audited remains to stand on.
resolve-citations makes live calls to the public registries; on the
synthetic dossier it correctly reports the invented identifiers as not
found or badly formatted, since none of them exist in any registry. gate0-report takes a JSON file mapping case ids to calls
("advance" or "kill") and judges it against the approved thresholds;
with --baseline it takes a second such file as the single-model
baseline the run must beat.

## Layout

- madd/ - the Python package. Standard library only.
- madd/schemas/ - the stage formats.
- madd/data/license_registry.json - tool licenses and what they allow.
- gate0/ - the retrospective test set, its sealed outcomes, and its
  verification ledger.
- docs/ - evidence policy, debate protocol, and the phase specs.
- examples/synthetic/ - invented fixtures for the code tests.
- tests/ - the test suite.

## License

Apache-2.0 for this project's own code. The tools listed in the license
registry have their own licenses, which the registry tracks; listing a
tool here does not grant any rights to it.
