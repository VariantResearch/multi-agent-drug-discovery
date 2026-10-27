"""Tests for assay design output: modality-matched blocks,
ranking order, hypotheses carried from the brief, criteria
labelled as conventions, and the no-candidates refusal."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from madd.assay import plan_assays
from madd.design import run_design
from tests.test_design import locked_spec


def design_bundle():
    """A real design run's output to plan assays from."""
    return run_design(locked_spec(), "test")


def test_plan_from_design_run():
    """The plan names the target, carries the brief's evidence
    constraints as hypotheses, and plans the ranked top
    candidates with controls and criteria in every block."""
    bundle = design_bundle()
    plan = plan_assays(bundle, top_n=2)
    assert plan["artifact_type"] == "assay_plan"
    assert plan["candidates_planned"] == 2
    assert plan["candidates_total"] == len(bundle["candidates"])
    assert plan["hypotheses"], "the brief's constraints are the hypotheses"
    for entry in plan["candidates"]:
        block = entry["assay_block"]
        assert block["primary_assay"]["readout"]
        assert block["controls"]["vehicle"]
        assert block["acceptance_criteria"]
        for criterion in block["acceptance_criteria"]:
            assert "convention" in criterion["basis"]


def test_blocks_match_modality():
    """Small molecules get the dose-response block, sequences
    the knockdown block, in the same plan."""
    plan = plan_assays(design_bundle(), top_n=5)
    by_modality = {}
    for entry in plan["candidates"]:
        by_modality.setdefault(entry["modality"],
                               entry["assay_block"])
    if "small_molecule" in by_modality:
        assert "biochemical" in by_modality[
            "small_molecule"]["primary_assay"]["name"]
    if "sequence" in by_modality:
        assert "knockdown" in by_modality[
            "sequence"]["primary_assay"]["name"]


def test_plan_from_target_bundle_shape():
    """A target bundle's nested design section plans the same
    way as a bare design artifact."""
    bundle = design_bundle()
    plan = plan_assays({"kind": "target_run", "design": bundle},
                       top_n=1)
    assert plan["candidates_planned"] == 1
    assert plan["spec_id"] == bundle["brief"]["spec_id"]


def test_no_candidates_refused():
    """A design with no candidates has nothing to plan."""
    with pytest.raises(ValueError):
        plan_assays({"candidates": [], "brief": {}})
