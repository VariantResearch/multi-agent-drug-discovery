"""Tests for the protocol export: the plan rendered as a
bench document carrying every candidate, its controls, its
criteria with thresholds, the hypotheses, and the boundaries,
with nothing in the document that is not in the plan."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from madd.assay import plan_assays
from madd.design import run_design
from madd.protocol_export import export_protocol
from tests.test_design import locked_spec


def make_plan():
    """A two-candidate plan from a real design run."""
    return plan_assays(run_design(locked_spec(), "test"), top_n=2)


def test_protocol_carries_the_plan():
    """The document names the target, every candidate, its
    controls and counterscreens, and the hypotheses."""
    plan = make_plan()
    text = export_protocol(plan)
    assert plan["plan_id"] in text
    assert str(plan["target"]) in text
    for entry in plan["candidates"]:
        assert entry["candidate_id"] in text
        block = entry["assay_block"]
        assert block["primary_assay"]["name"] in text
        assert block["controls"]["vehicle"] in text
    for hypothesis in plan["hypotheses"]:
        assert hypothesis["claim_id"] in text


def test_protocol_criteria_are_checklists_with_thresholds():
    """Criteria render as checkboxes, and machine-checkable
    ones spell out the metric and threshold they grade on."""
    text = export_protocol(make_plan())
    assert "- [ ]" in text
    assert "z_prime" in text and "0.5" in text
    assert "Decision rule" in text


def test_protocol_keeps_the_boundaries():
    """The export repeats that execution is laboratory work
    under local SOPs, not something the document performs."""
    text = export_protocol(make_plan())
    assert "local SOPs" in text
    assert "laboratory work" in text


def test_empty_plan_refused():
    """A plan with no candidates has no protocol."""
    with pytest.raises(ValueError):
        export_protocol({"plan_id": "x", "candidates": []})
