"""Tests for bundle-faithful manuscript drafts: the real
frozen MTCH2 bundle renders with its own numbers, a number
absent from the bundle appears nowhere in the draft, a no-go
bundle invents no candidates, and every statement carries
its source field."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.manuscript import build_manuscript

ROOT = Path(__file__).resolve().parent.parent
REAL = ROOT / "designer-output" / "target-mtch2-inhibition-2026-10-25" / "bundle.json"


def test_real_bundle_manuscript_is_faithful():
    """The frozen inhibition bundle renders its own record:
    outcome, strikes, gate, candidates, references - and a
    distinctive number the bundle does not contain (98.6)
    appears nowhere."""
    bundle = json.loads(REAL.read_text(encoding="utf-8"))
    assert "98.6" not in json.dumps(bundle)
    draft = build_manuscript(bundle)
    text = draft["markdown"]
    assert "MTCH2" in text
    assert "designed" in text
    assert "Strikes for quote_not_in_full_text: 12." in text
    assert "Design gate: pass (4 checks)." in text
    assert "panel-b-cand-1" in text
    assert "PMID 41960826" in text
    assert "39753955" not in text, "a struck claim's source stays out"
    assert "98.6" not in text
    assert "no candidate named here has been made or tested" in text
    assert all(s["source"] for s in draft["statements"])


def test_no_go_bundle_invents_nothing():
    """A no-go bundle renders an honest draft: no candidates,
    no gate line, limitations still stated."""
    bundle = {"kind": "target_run", "run_id": "x",
              "outcome": "no_go", "mode": "simple",
              "target": {"name": "TGT", "focus_id": None},
              "frame_run": {"record": {
                  "outcome": "no_go",
                  "providers": [{"name": "p1",
                                 "model_version": "m1"}],
                  "spec": {"claims": []}, "strike_list": []}}}
    draft = build_manuscript(bundle)
    assert "Candidate " not in draft["markdown"]
    assert "Design gate" not in draft["markdown"]
    assert "no_go" in draft["markdown"]
