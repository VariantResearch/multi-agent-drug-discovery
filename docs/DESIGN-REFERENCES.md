# Design references

External patterns recorded for later phases. This file is
a reference shelf, not a spec: nothing here changes
PHASE0_SPEC.md or PHASE1_SPEC.md, and nothing here is in
force until a phase spec adopts it with the owner's
approval.

## TradeMemory Protocol - failure memory with a brake

Recorded 2026-10-23 at the owner's direction.
Source: github.com/mnemox-ai/tradememory-protocol

The project gives trading agents a memory of their
losing trades plus a brake that throttles risky repeats.
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
