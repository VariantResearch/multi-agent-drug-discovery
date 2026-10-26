"""Target-first runs: name a target, get designed candidate drugs.

This is the application's front door. The operator names a specific
target - a disease, a receptor, a genetic disorder, or a molecular
target in a disease context - and the pipeline works it end to end:

1. Frame: the target becomes a prospective frame, with evidence
   retrieved for it (Europe PMC, by the caller or the CLI) carried
   in the frame's evidence entries.
2. Research and debate: the configured panel researches the frame
   under the run's protocol mode and the debate decides whether the
   evidence supports locking a design specification for this
   target. A no_go ends the run: no design work starts from an
   unlocked target, and the record says why.
3. Design: on a locked specification, the designer panel proposes
   candidate drugs (structures required from real providers), the
   candidates are enriched, audited, and ranked by the Phase 2
   design stage (madd/design.py), and the design gate judges them.

The combined bundle freezes both stages together: the target as
named, the debate record, and, when the target locked, the design
bundle with its ranked candidates. Gate 0 remains what it always
was, a retrospective calibration set for the research layer; this
module is the production path the calibration serves.
"""
from __future__ import annotations

import re
import uuid

from .artifacts import freeze_artifact
from .budget import BudgetTracker
from .design import ModelDesigner, run_design
from .runner import run_frame

TARGET_KINDS = ("disease", "receptor", "genetic_disorder", "target")


def _slug(text) -> str:
    """Filesystem and id safe slug for a target name."""
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "target"


def build_target_frame(name: str, kind: str, target: str = None,
                       disease: str = None, focus_id: str = None,
                       evidence: list = None) -> dict:
    """Build the prospective frame for one named target.

    name is the target as the operator names it ("KRAS G12C",
    "cystic fibrosis", "the CGRP receptor"); kind is one of
    TARGET_KINDS and says what sort of thing was named. target, when
    given, is the molecular target in retrieval terms (a gene,
    protein, or receptor name); disease, when given, is the disease
    context. The frame's focus_id - the identifier a locked
    specification will carry - defaults to the molecular target when
    one is given, else to the name itself; the operator may set it
    explicitly. Evidence entries, when supplied, ride in the frame
    exactly as run-frame --retrieve supplies them.
    """
    if kind not in TARGET_KINDS:
        raise ValueError("target kind must be one of " + ", ".join(TARGET_KINDS)
                         + "; got " + repr(kind))
    if not isinstance(name, str) or not name.strip():
        raise ValueError("a target run needs the target's name")
    molecular = target or (name if kind in ("receptor", "target") else None)
    context_disease = disease or (name if kind == "disease" else None)
    frame = {
        "artifact_type": "frame",
        "schema_version": "0.1.0",
        "frame_id": "TARGET-" + _slug(name),
        "question": ("Using only the evidence supplied, decide whether this "
                     "target merits advancing to a locked design "
                     "specification: a defined target and approach, "
                     "consistent with the evidence, against which candidate "
                     "drugs can be designed."),
        "target_name": name,
        "target_kind": kind,
        "target": molecular,
        "disease": context_disease,
        "focus_id": focus_id or molecular or name,
        "round_cap": 2,
        "evidence": list(evidence or []),
    }
    return frame


def run_target(frame: dict, providers, judge_provider=None, mode=None,
               designer=None, budget=None, budget_tracker=None,
               run_id=None, on_event=None,
               resolver=None, quote_checker=None, entailment_checker=None,
               retrieval_first: bool = False, design_constraints: tuple = (),
               target_label: str = None, disease: str = None,
               use: str = "research", source_check: bool = False) -> dict:
    """Run one named target end to end. Returns the combined bundle.

    The research stage is madd.runner.run_frame under the declared
    protocol mode. When it locks a specification, the design stage
    (madd.design.run_design) runs on that spec with the designer
    given, or with a ModelDesigner over the same providers when none
    is given. The bundle outcome is "designed" when the design gate
    passes, "design_gate_failed" when the target locked but the
    design stage produced no gate-passing real candidate, and
    "no_go" when the debate would not lock the target.
    """
    run_id = run_id or ("target-" + uuid.uuid4().hex[:12])
    # One tracker for the whole run: the research stage and the
    # design stage charge the same budget, so the configured caps
    # bound the run's total provider spend.
    tracker = budget_tracker if budget_tracker is not None else (
        BudgetTracker(budget) if budget is not None else None)
    frame_bundle = run_frame(frame, providers, judge_provider=judge_provider,
                             budget_tracker=tracker, run_id=run_id + "-frame",
                             on_event=on_event, resolver=resolver,
                             quote_checker=quote_checker,
                             entailment_checker=entailment_checker,
                             retrieval_first=retrieval_first, mode=mode)
    record = frame_bundle["record"]
    spec = record["spec"]
    bundle = {
        "artifact_type": "target_run_bundle",
        "schema_version": "0.1.0",
        "run_id": run_id,
        "kind": "target_run",
        "mode": mode or "legacy",
        "target": {"name": frame.get("target_name"),
                   "kind": frame.get("target_kind"),
                   "target": frame.get("target"),
                   "disease": frame.get("disease"),
                   "focus_id": frame.get("focus_id")},
        "frame_run": frame_bundle,
        "design": None,
        "outcome": "no_go",
    }
    if record["outcome"] == "locked":
        designer = designer if designer is not None else ModelDesigner(
            providers, budget_tracker=tracker)
        design_bundle = run_design(
            spec, "target run " + run_id, designer=designer,
            budget_tracker=tracker,
            design_constraints=tuple(design_constraints),
            target=target_label or frame.get("target") or frame.get("target_name"),
            disease=disease if disease is not None else frame.get("disease"),
            use=use, source_check=source_check)
        bundle["design"] = design_bundle
        bundle["outcome"] = ("designed"
                             if design_bundle["gate_report"]["result"] == "pass"
                             else "design_gate_failed")
    bundle["frozen_bundle"] = freeze_artifact(
        {k: v for k, v in bundle.items() if k != "frozen_bundle"})
    return bundle
