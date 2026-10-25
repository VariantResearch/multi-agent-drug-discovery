# Phase 2 Specification: Candidate Design

Status: built 2026-10-24 at the owner's order. This spec describes the
design stage as implemented in madd/design.py and madd/design_tools.py,
including what it honestly cannot do yet.

## Purpose

Phase 1 ends with a locked target specification: a target that survived
blinded research, debate, and mechanical citation audit. Phase 2 takes
that specification and produces candidate records for the target - the
first step from "this target is worth pursuing" toward "here is what a
program against it could look like" - under the same evidence discipline
as everything else in this repository.

## Pipeline

1. **Design brief.** Built mechanically from a locked consensus spec
   (outcome "locked", taken from a frame run bundle, a Gate 0 case
   record, or a spec file). The brief carries the target, the disease,
   the question, the source spec id, and two kinds of constraints:
   evidence constraints (the spec's surviving load-bearing claims, by
   claim id, so a candidate can be checked against the evidence it is
   supposed to respect) and free-text design constraints supplied by the
   operator. A spec that is not locked is refused: no design work starts
   from a killed or unresolved target.
2. **Candidate generation.** Behind a Designer interface, the same way
   providers sit behind an interface in Phase 1. The shipped designer
   is the deterministic mock: it returns synthetic, clearly labelled
   example candidates so the pipeline can be exercised end to end. It
   invents no structures: its candidates carry no SMILES, no sequence,
   and no potency numbers, and say so.
3. **Tool runs (optional).** External structure tools run through
   madd/design_tools.py, which enforces the license registry before
   anything executes: a tool the registry blocks for the intended use
   is refused, a tool that is not installed is reported not_installed,
   and a tool that runs has its outputs recorded by path and SHA-256
   hash in a tool manifest. Only files the run created or changed are
   recorded: the output directory is snapshotted first, and
   pre-existing files in a reused directory are listed as skipped,
   never claimed as this run's outputs. Only structure-suffixed files
   (.cif, .pdb, and peers) become candidates; logs and other side
   files stay in the manifest only. Boltz-2 and Chai-1 are the registry-cleared
   entries; they are not installed in the development environment, so
   no real tool run has happened yet. Each output structure file
   becomes one candidate whose provenance is the tool run; MADD
   attaches no invented assessment to it.
4. **Candidate audit.** Every claim a candidate carries goes through
   the research layer's machinery, not a local copy: the document
   claim audit (ledger rules plus duplicate claim_id detection) and
   the citation auditor (identifier format and quote rules). A claim
   counts as audited support only when it is error-free and audited
   under the same is_audited rule the focus score uses, counted once
   per claim_id. Predicted properties must name their basis: a tool
   run, or an explicit designer prediction, which is counted as
   unverified. A candidate whose load-bearing claim carries any audit
   error, or which records a failed constraint, is excluded from the
   ranking, with the reasons preserved.
5. **Ranking.** Deterministic: ranked candidates sort by audited
   load-bearing claim count (descending), then fewer unknown
   constraints, then candidate id. No model confidence, no invented
   weights.
6. **Design gate and bundle.** A design bundle freezes the brief, the
   candidates, the per-candidate audits, any tool runs, the ranking,
   and a gate report, under the same canonical hash envelope as every
   other run bundle. The gate checks are: the brief came from a locked
   spec; at least one candidate is ranked; at least one ranked
   candidate is real (not a synthetic mock or fixture candidate - a
   mock-only run fails this check by design, because exercising the
   pipeline is not a design result); no tool run was license-blocked;
   and, when tool runs were requested, at least one completed. Audit
   failures do not appear as a gate check: a candidate that fails
   audit is excluded before ranking, so the ranked set is clean by
   construction and the exclusions are listed in the bundle instead.
   The gate report validates against the project's gate_report schema,
   and design-run exits non-zero when the gate fails.

## What candidates are, and are not

A candidate record (schema: candidate) names its spec, its modality,
its designer or tool, its claims, its predicted properties with their
basis, and its constraint results. It is a record that a design step
proposed something and that the proposal survived mechanical checking.

It is not evidence that the candidate binds the target, works in an
assay, or is safe. Nothing in Phase 2 runs a wet-lab step, a docking
score, or a property calculation unless a real external tool produced
it and the tool run is in the manifest saying so. Model-generated or
mock-generated properties are labelled predictions and counted as
unverified in every report.

## In scope

- Design briefs from locked specs, with refusal for unlocked ones.
- The Designer interface, the deterministic mock designer, and the
  license-gated external tool runner.
- Candidate audit, exclusion with reasons, deterministic ranking.
- Design bundles with gate reports, stored like run bundles, readable
  in the text report, the HTML report, and the MADD Console.
- CLI: design-brief and design-run.

## Out of scope

- Any real molecule generation until a registry-cleared tool is
  installed and run for real; until then candidates come from the mock
  designer (synthetic, structure-free) or from recorded tool outputs.
- Docking, ADMET calculation, synthesis planning, and wet-lab
  protocols. A future stage may add them behind the same manifest and
  audit rules.
- Any claim that a ranked candidate is a drug or a lead. Ranking orders
  proposals by audited support; it validates nothing about biology.
