"""Workbench tests: uniform computed sets, honest gaps, no scores."""

import json
from pathlib import Path

from madd.workbench import build_workbench

ROOT = Path(__file__).resolve().parent.parent
MTCH2 = ROOT / "designer-output" / "target-mtch2-inhibition-2026-10-25"


def _workbench():
    """The workbench of the frozen MTCH2 design."""
    bundle = json.loads((MTCH2 / "bundle.json").read_text())
    return build_workbench(bundle)


def test_columns_follow_the_ranking_with_modality_notes():
    """Four ranked columns; the ASOs carry the no-computed note."""
    workbench = _workbench()
    ids = [c["candidate_id"] for c in workbench["columns"]]
    assert ids == ["panel-b-cand-1", "panel-b-cand-2",
                   "panel-a-cand-1", "panel-a-cand-2"]
    notes = {c["candidate_id"]: c["note"]
             for c in workbench["columns"]}
    assert notes["panel-b-cand-1"] is None
    assert "No computed properties" in notes["panel-b-cand-2"]
    assert "No computed properties" in notes["panel-a-cand-2"]


def test_computed_rows_have_gaps_for_asos_not_zeroes():
    """The DILI row: values for the small molecules, None for ASOs."""
    workbench = _workbench()
    dili = next(r for r in workbench["rows"]
                if r["name"] == "admet:DILI")
    assert dili["group"] == "ADMET-AI endpoints (predicted)"
    values = dili["values"]
    assert values[0] is not None and values[2] is not None
    assert values[1] is None and values[3] is None
    # lower is the declared direction: the best mark is the minimum
    numeric = [(i, float(v)) for i, v in enumerate(values)
               if v is not None]
    assert dili["best_index"] == min(numeric, key=lambda p: p[1])[0]
    assert dili["deltas"][0] == 0.0
    assert dili["deltas"][1] is None


def test_radar_covers_small_molecules_only():
    """The radar SVG names the two small molecules, not the ASOs."""
    workbench = _workbench()
    assert "panel-b-cand-1" in workbench["radar_svg"]
    assert "panel-a-cand-1" in workbench["radar_svg"]
    assert "panel-b-cand-2" not in workbench["radar_svg"]
    assert "No composite score" in workbench["note"]


def test_no_design_means_no_workbench():
    """Frame and Gate 0 bundles return None."""
    assert build_workbench({"kind": "frame_run"}) is None
    assert build_workbench({"kind": "gate0_run"}) is None
