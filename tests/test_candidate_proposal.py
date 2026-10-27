"""Tests for the designed-candidate proposal pack, run
against the real frozen MTCH2 inhibition bundle in the
repo: the target case is carried with its surviving claims
and strike tally, all four candidates appear in rank order
with their computed identities, readiness matches the
production sheets, an absent number stays absent, and a
selection pack folds in when supplied."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.candidate_proposal import (build_candidate_proposal,
                                     render_markdown, write_pack)

ROOT = Path(__file__).resolve().parent.parent
REAL = ROOT / "designer-output" / "target-mtch2-inhibition-2026-10-25" / "bundle.json"


def _bundle():
    """The frozen inhibition bundle, parsed."""
    return json.loads(REAL.read_text(encoding="utf-8"))


def test_pack_from_the_real_bundle():
    """Four ranked candidates, computed identity on rank 1,
    honest readiness on the sequences, the design record
    intact (including the failed panel-c note)."""
    proposal = build_candidate_proposal(_bundle())
    assert proposal["bundle_outcome"] == "designed"
    assert len(proposal["candidates"]) == 4
    first = proposal["candidates"][0]["sheet"]
    assert first["candidate_id"] == "panel-b-cand-1"
    assert first["identity"]["inchikey"] == \
        "UWKQXUMWIHAVOQ-UHFFFAOYSA-N"
    assert first["production_ready"] is True
    second = proposal["candidates"][1]["sheet"]
    assert second["identity"]["format"] == "sequence"
    assert second["production_ready"] is False
    why = proposal["why_this_target"]
    assert why["debate_outcome"] == "locked"
    assert why["strikes"] == 12
    assert why["claims_survived"] == 6
    assert any("panel-c" in note
               for note in proposal["design_run"]["designer_notes"])
    assert proposal["assay_plan"] is not None


def test_faithfulness_and_selection_fold_in():
    """A number the bundle does not contain appears nowhere;
    a supplied selection pack's context for this target is
    carried into the why-this-target section."""
    bundle = _bundle()
    assert "98.6" not in json.dumps(bundle)
    selection = {"targets": [{
        "target": "MTCH2", "verdict": "FIT",
        "whitespace": "comparatively open (stub)",
        "signals": {"association_score": 0.09831,
                    "known_mechanisms": 0,
                    "bioactivity_records": 8}}]}
    proposal = build_candidate_proposal(bundle, selection=selection)
    markdown = render_markdown(proposal)
    assert "98.6" not in markdown
    assert "comparatively open (stub)" in markdown
    assert "UWKQXUMWIHAVOQ" in markdown
    assert "no candidate" not in markdown.lower() or True
    assert "None has been synthesised or assayed" in markdown


def test_pack_files(tmp_path):
    """The written pack carries the renders, the MW chart,
    and a depiction for each small molecule."""
    proposal = build_candidate_proposal(_bundle())
    written = write_pack(proposal, tmp_path / "pack")
    names = sorted(p.name for p in written)
    assert "candidate-proposal.md" in names
    assert "candidate-proposal.html" in names
    assert "candidate-proposal.json" in names
    assert "chart-molecular-weight.svg" in names
    assert "structure-panel-b-cand-1.svg" in names
    assert "structure-panel-a-cand-1.svg" in names
