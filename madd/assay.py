"""Assay design output: from a design run to a concrete,
executable assay plan.

The design gate can say a candidate is worth making; it cannot
say how anyone would find out whether the candidate works.
This module closes that gap on paper: from a design artifact
(a design run, or the design section of a target bundle) it
produces an assay plan artifact naming, per top candidate, the
assays to run, the readouts, the controls, the dose layout,
and the acceptance criteria the results will later be graded
against.

Everything in a plan is a recorded design choice made before
any data exists:

- The hypotheses under test are the design brief's surviving
  evidence constraints, carried by claim id.
- Assay blocks are matched to each candidate's modality from
  fixed templates (small molecule, sequence, biologic, other).
- Acceptance criteria (plate quality, curve quality, hit
  thresholds) are conventions recorded in the plan itself,
  each labelled as such. They are not measurements, not
  literature values, and not predictions; item 11's results
  ingestion grades returned data against exactly these
  criteria, as written, so a plan cannot be quietly re-cut
  after the data arrives.
- Executing a plan is laboratory work outside this system.
  The plan never claims an assay was run.
"""
from .design import _slug

PLAN_NOTE = ("This plan is a design artifact. Every assay, "
             "control, and criterion in it is a recorded choice "
             "made before any data exists; nothing here is a "
             "measurement or a result. Executing the plan is "
             "laboratory work outside this system; returned "
             "results are graded against these criteria as "
             "written.")


def _criterion(name: str, rule: str) -> dict:
    """One acceptance criterion, labelled as a convention."""
    return {"criterion": name, "rule": rule,
            "basis": "assay-design convention (recorded default)"}


def _small_molecule_block(target: str) -> dict:
    """The assay block for a small-molecule candidate."""
    return {
        "modality": "small_molecule",
        "primary_assay": {
            "name": "biochemical activity assay against " + target,
            "readout": ("dose-response activity (percent inhibition "
                        "or activation versus vehicle) across an "
                        "8-point, 3-fold serial dilution, in "
                        "triplicate"),
            "purpose": ("direct target engagement in a cell-free "
                        "system; produces the IC50/EC50 the hit "
                        "call is graded on"),
        },
        "secondary_assay": {
            "name": "cell-based functional assay",
            "readout": ("pathway or phenotype readout in a "
                        "target-expressing cell line, same dose "
                        "layout"),
            "purpose": ("activity in a cellular context, where "
                        "permeability and toxicity first show"),
        },
        "counterscreens": [
            "cytotoxicity in the same cell line at the same doses",
            "an unrelated-target activity counterscreen for "
            "selectivity",
        ],
        "controls": {
            "vehicle": "DMSO at the final assay concentration",
            "positive": ("a reference modulator of " + target
                         + " where one is established; the "
                         "compound used is recorded at execution "
                         "time in the results file"),
            "negative": ("a structurally matched inactive analog "
                         "where available, else vehicle only, "
                         "recorded at execution time"),
        },
        "acceptance_criteria": [
            _criterion("plate quality", "Z' >= 0.5 on every plate"),
            _criterion("curve quality",
                       "dose-response fit R^2 >= 0.9 with a "
                       "defined top and bottom plateau"),
            _criterion("hit call",
                       "IC50/EC50 at or below 10 uM in the "
                       "primary assay with the counterscreens "
                       "clean at that concentration"),
        ],
    }


def _sequence_block(target: str) -> dict:
    """The assay block for a sequence candidate (ASO/siRNA)."""
    return {
        "modality": "sequence",
        "primary_assay": {
            "name": "target knockdown assay for " + target,
            "readout": ("target mRNA by qPCR at 48-72 h after "
                        "transfection into a target-expressing "
                        "cell line, 6-point dose layout, in "
                        "triplicate"),
            "purpose": ("the candidate's mechanism is reducing "
                        "the target transcript; this is the "
                        "direct test"),
        },
        "secondary_assay": {
            "name": "target protein quantification",
            "readout": ("protein level by western blot or ELISA "
                        "at the same doses"),
            "purpose": ("mRNA knockdown that does not move the "
                        "protein does not advance"),
        },
        "counterscreens": [
            "cell viability at every dose",
            "a non-target transcript panel for sequence "
            "specificity",
        ],
        "controls": {
            "vehicle": "transfection reagent only",
            "positive": ("a validated knockdown reagent for "
                         + target + " where one exists, recorded "
                         "at execution time"),
            "negative": "a non-targeting scrambled sequence of "
                        "the same chemistry and length",
        },
        "acceptance_criteria": [
            _criterion("hit call",
                       ">= 70% mRNA knockdown at the top "
                       "tolerated dose, with protein reduced "
                       "in the same direction"),
            _criterion("viability",
                       ">= 80% viability at every dose counted "
                       "toward the hit call"),
            _criterion("specificity",
                       "no non-target transcript in the panel "
                       "reduced by more than 30%"),
        ],
    }


def _generic_block(modality: str, target: str) -> dict:
    """The assay block for any other modality: a binding and a
    functional measurement, conservatively framed."""
    return {
        "modality": modality,
        "primary_assay": {
            "name": "binding assay against " + target,
            "readout": ("binding signal (ELISA or SPR) across a "
                        "dilution series, in triplicate"),
            "purpose": "direct target engagement",
        },
        "secondary_assay": {
            "name": "cell-based functional assay",
            "readout": ("pathway or phenotype readout in a "
                        "target-expressing system"),
            "purpose": "engagement that changes function",
        },
        "counterscreens": ["a specificity counterscreen against "
                           "an unrelated target"],
        "controls": {
            "vehicle": "assay buffer or vehicle as appropriate",
            "positive": ("a reference binder for " + target
                         + " where one is established, recorded "
                         "at execution time"),
            "negative": "an isotype- or scaffold-matched "
                        "non-binding control where applicable",
        },
        "acceptance_criteria": [
            _criterion("hit call",
                       "a saturable, dose-dependent binding "
                       "signal clearly separated from the "
                       "negative control, with functional "
                       "activity in the same direction"),
            _criterion("curve quality",
                       "dilution-series fit R^2 >= 0.9"),
        ],
    }


def block_for(modality: str, target: str) -> dict:
    """The assay block matching one candidate's modality."""
    kind = str(modality or "").lower()
    if kind == "small_molecule":
        return _small_molecule_block(target)
    if kind == "sequence":
        return _sequence_block(target)
    return _generic_block(kind or "unspecified", target)


def design_of(bundle_or_design: dict) -> dict:
    """The design artifact inside a target bundle, or the dict
    itself when it already is one."""
    if isinstance(bundle_or_design, dict) and isinstance(
            bundle_or_design.get("design"), dict):
        return bundle_or_design["design"]
    return bundle_or_design


def plan_assays(bundle_or_design: dict, top_n: int = 3) -> dict:
    """Build the assay plan for a design run's top candidates.

    Candidates are taken in the design's ranking order (the
    design's own candidates order when no ranking is present).
    Raises ValueError when the input carries no candidates.
    """
    design = design_of(bundle_or_design)
    candidates = design.get("candidates") or []
    if not candidates:
        raise ValueError("the design run carries no candidates "
                         "to plan assays for")
    brief = design.get("brief") or {}
    target = str(brief.get("target") or "the target")
    by_id = {str(c.get("candidate_id")): c for c in candidates}
    order = []
    ranking = design.get("ranking") or {}
    ranked_ids = ranking.get("ranked") if isinstance(
        ranking, dict) else ranking
    for cid in ranked_ids or []:
        cid = str(cid)
        if cid in by_id and cid not in order:
            order.append(cid)
    for candidate in candidates:
        cid = str(candidate.get("candidate_id"))
        if cid not in order:
            order.append(cid)
    entries = []
    for cid in order[:max(1, int(top_n))]:
        candidate = by_id[cid]
        entries.append({
            "candidate_id": cid,
            "modality": candidate.get("modality") or "unspecified",
            "design_tool": candidate.get("design_tool"),
            "structure": candidate.get("structure"),
            "assay_block": block_for(candidate.get("modality"),
                                     target),
        })
    return {
        "artifact_type": "assay_plan",
        "schema_version": "0.1.0",
        "plan_id": "assay-plan-" + _slug(brief.get("spec_id")
                                         or design.get("run_id")
                                         or "design"),
        "spec_id": brief.get("spec_id"),
        "target": brief.get("target"),
        "disease": brief.get("disease"),
        "generated_from": {
            "design_run_id": design.get("run_id"),
            "designer": design.get("designer"),
            "gate_outcome": (design.get("gate") or {}).get("outcome"),
        },
        "hypotheses": brief.get("evidence_constraints") or [],
        "candidates": entries,
        "candidates_planned": len(entries),
        "candidates_total": len(candidates),
        "conduct": {
            "replicates": "every readout in triplicate unless a "
                          "block states otherwise",
            "blinding": "plate maps randomized; the analyst is "
                        "blinded to candidate identity where "
                        "practical (recorded design choice)",
            "decision_rule": ("a candidate advances on meeting "
                              "its block's hit call with clean "
                              "counterscreens, is revised on "
                              "partial activity, and is retired "
                              "on inactivity or a dirty "
                              "counterscreen; results are "
                              "graded against this plan as "
                              "written"),
        },
        "note": PLAN_NOTE,
    }
