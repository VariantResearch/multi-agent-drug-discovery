# Design references

External patterns recorded for later phases. This file is
a reference shelf, not a spec: nothing here changes
PHASE0_SPEC.md or PHASE1_SPEC.md, and nothing here is in
force until a phase spec adopts it with the owner's
approval.

## TradeMemory Protocol - failure memory with a brake

Recorded 2026-10-23 at the owner's direction.
Source: github.com/mnemox-ai/tradememory-protocol

The project gives trading agents a persistent memory
of their past trades, weighted by outcome, plus a
pre-trade brake that refuses orders its policy cannot
evaluate.
The pattern that transfers to MADD: research agents that
can see the project's own killed hypotheses and failed
arguments before re-arguing a similar case, with the
burden of proof rising when a new case resembles a past
kill. That fits the project's anti-slop rule (no
load-bearing claim without a verified primary source):
a failure memory is one more audited input, never a
substitute for evidence.

Boundary: Gate 0 and Phase 1 run blinded by design, and
a shared failure memory could leak outcomes across
cases. Any adoption belongs in a later phase spec, with
the leakage question answered first, the same way Gate 0
handled known outcomes. Noted here so the idea is not
lost; not proposed for Phase 1.

## Desloppify - scored fix loop with attestation

Recorded 2026-10-24 at the owner's direction.
Source: github.com/peteromallet/desloppify

Desloppify is a codebase health harness for coding
agents: mechanical detectors plus subjective LLM review
produce scored findings, the agent fixes them one at a
time or marks them wontfix, and a rescan verifies the
result. State persists across sessions. Two of its rules
are the transferable part for MADD. First, resolving a
finding requires an attestation that the fix actually
happened and is not score gaming; second, a wontfix
lowers the strict score, so waived findings stay visible
as a gap between the lenient and strict scores instead
of disappearing. Mapped onto the claim audit loop, that
reads: a struck claim is resolved only with a recorded
note of what evidence changed, and a claim waived
instead of repaired carries a visible debt against the
run. Its subjective review also ships as blind packets,
the same instinct as this project's blinding.

There is also a plain direct use: MADD itself is a
Python codebase, and Python is one of Desloppify's
full-depth languages, so the tool could run as a
codebase health pass on the madd/ package. That is a
repo maintenance decision for the owner, separate from
the research layer.

Boundary: Desloppify's health score must never become
a research score here. MADD's focus score is
deterministic, computed from audited evidence tiers
only, by design; a codebase quality score steers no
target decision. Persistent cross-run state also
carries the same leakage question as the TradeMemory
entry above for blinded Gate 0 and Phase 1 work, so any
adoption belongs in a later phase spec with that
question answered first. Not proposed for Phase 1.
