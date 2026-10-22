# Multi-Agent Drug Discovery (MADD) - Phase 0 Scaffold

A provider-neutral, open-source research engine design in which agents from
different model families research a framed question independently and
blinded, produce structured dossiers, debate under a written protocol, lock
a consensus specification (or record a no-go), design candidates only
against that locked specification, pass layered validation gates, and only
then generate a paper draft from the frozen artifacts.

Status: Phase 0 scaffold. This repository contains schemas, a claim
auditor, a citation auditor, a license registry, consensus logic, a focus
scorer, a mock provider, and a command line interface. It contains no live
model calls, no provider SDKs, no network calls, and no design tools wired
in yet. Nothing in this repository is a research result.

## What this is not

- Not a drug, and it does not contain one.
- Not clinical advice, and it must not be used as clinical advice.
- It cannot prove a treatment works. Software output, agent agreement, and
  a generated paper draft are not proof of effect in a human.
- Any candidate that emerges from the full design would still require a
  wet-lab handoff, independent experimental testing, and human sign-off
  before any further step. See RESPONSIBLE_USE.md.
- It makes no disease, target, or efficacy claims. Example and fixture
  data in this repository are synthetic, invented, and labelled as such.

## The six stages

1. Frame - a written question, an intended effect profile, and explicit
   exclusion criteria are fixed before any agent runs.
2. Research - each agent researches the frame independently and blinded
   and submits a sealed dossier of claims with sources.
3. Debate - dossiers are unsealed and cross-examined under
   docs/DEBATE_PROTOCOL.md. Unverified claims are struck, not debated.
4. Design - candidates are designed only against a locked consensus
   specification produced by stage 3, and only with tools the license
   registry allows for the run's declared use.
5. Validate - candidates and the consensus pass layered gates. Outputs are
   labelled by the highest gate actually passed, never higher.
6. Publish - a paper draft is generated only from frozen, hashed
   artifacts, with the dissent log and the gate reports included.

## Anti-slop evidence rules (binding)

These rules are enforced in code where code can enforce them, and are a
condition of contribution where it cannot. Full text: docs/EVIDENCE_POLICY.md.

- Every load-bearing claim must carry a primary-source identifier.
- Model opinion is never evidence. Evidence tier 0 is not evidence.
- Agreement between agents is never evidence. Consensus is a process
  outcome, not a source.
- An unverified claim may be recorded, but it cannot support a locked
  specification, a candidate, or a paper claim.
- A claim whose verification status is "struck" is removed from
  consideration. It is not debated, averaged, or outvoted.
- Focus ranking is computed deterministically from evidence tiers and
  audited status only, in madd/focus.py. Model confidence prose plays no
  part in the score.
- Citations are audited mechanically by madd/citation_auditor.py: identifier
  format first, supporting-quote presence second, live resolution later.
  A citation that has not been live-resolved is labelled unverified.
- Any text that cannot be traced to a frozen artifact and an audited claim
  does not go in a paper draft.

## Repository layout

- madd/ - the core package. Python standard library only.
- madd/schemas/ - JSON Schema files for the seven artifact types.
- madd/data/license_registry.json - tool license entries and run-use rules.
- docs/ - evidence policy, debate protocol, and the Phase 0 specification.
- examples/synthetic/ - invented fixtures, labelled synthetic, used only
  to exercise the code.
- tests/ - unittest suite.

## Running the tests

    python3 -m unittest discover -s tests -v

## Command line

Run from the repository root:

    python3 -m madd audit-claims examples/synthetic/dossier.json
    python3 -m madd check-tool Boltz-2 --use commercial
    python3 -m madd check-tool "AlphaFold 3" --use commercial
    python3 -m madd focus-score examples/synthetic/dossier.json
    python3 -m madd validate-artifact frame examples/synthetic/frame.json

Exit status is non-zero when a check fails.

## License

Apache-2.0. See LICENSE. Tool licenses are separate from this project's
license and are tracked in madd/data/license_registry.json; a tool being
listed there does not grant any rights in that tool.
