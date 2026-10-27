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
pre-trade brake that refuses orders that fail its
policy checks or that its policy cannot evaluate.
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

## Swarms - multi-agent orchestration framework

Recorded 2026-10-26 at the owner's direction.
Source: github.com/kyegomez/swarms (Apache-2.0, Python)

Swarms is a general-purpose framework for orchestrating
many agents: pooling agents across providers, arranging
them in sequential, parallel, and hierarchical
topologies, and running the group as one system. The
pattern that transfers to MADD is at the panel layer.
The validation runs recorded on 2026-10-25 showed the
pipeline works but the panel configuration is not
cleared for production, and the missing ingredient named
there is roster diversity: in single-model staffing the
baseline is the same mind working solo. A framework
whose whole job is composing heterogeneous agent groups
is a useful comparison shelf when the owner picks the
commercial roster, and its topology vocabulary (who
works in parallel, who reviews whom, what a hierarchy
buys) maps onto the protocol modes the owner designed
(simple, dual, dual_judge).

Boundary: MADD's debate engine is purpose-built, and
its guarantees are the product: blinded inputs, sealed
outcomes, a mechanical citation audit, and a focus score
computed deterministically from audited evidence tiers
only. A general orchestration framework enforces none
of that. Nothing here proposes replacing the engine or
routing a scored run through Swarms; the entry is a
reference for panel-composition decisions, and any
adoption belongs in a phase spec with the audit
guarantees re-proven against it first.

## Carbon-X - conversational DNA model

Recorded 2026-10-26 at the owner's direction, parked for
later relevance.
Source: Hugging Face release, 2026-10-22 (Zhongguancun
Academy and University of Naples Federico II / Telethon
Institute of Genetics and Medicine collaborators);
Apache-2.0, 14.8B parameters, downloadable weights.

Carbon-X is a DNA language model: DNA and English share
one token stream (DNA read as 6-mers), so a researcher
pastes a sequence (up to about 50 kb per call) and asks
questions in plain language. Its stated tasks are variant
pathogenicity prediction, identifying regions that
control gene activity, sequence classification, and
next-base prediction, with natural-language explanations.

The pattern that could transfer to MADD is narrow and
specific: as a registry-gated prediction tool in the
design stage, in the slot ADMET-AI already occupies, for
sequence-shaped work - variant-effect reads on
genetic-disorder targets (a frame kind the target form
already supports) and locus context for antisense
designs. Its predictions would be recorded exactly the
way ADMET-AI's are: basis labelled, verified: false,
information for the panel, never evidence.

Boundary: it is not a provider candidate. Its outputs
are unverified model predictions by its own creators'
description (no laboratory validation at release, and
early independent coverage flags unreliable sequence
operations and inconsistent deployment documentation),
so it cannot carry claims in an audit that strikes
anything without a verified primary source. Practical
blockers today: 14.8B parameters need GPU infrastructure
the run setup does not have, the 50 kb window cannot hold
large loci whole (the CFTR gene spans roughly 250 kb),
and the model was four days old at recording. Revisit
when a genetic-disorder target run is actually on the
table; adoption would belong in a phase spec, behind the
license registry, with its prediction labels settled
first.
