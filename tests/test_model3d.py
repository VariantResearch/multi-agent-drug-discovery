"""Fully rendered 3D model tests: molfile generation, the receptor
registry (a real shipped AlphaFold model for MTCH2, an honest none
for everything else), and the combined candidate model payload."""
import json
from pathlib import Path

from madd.gui import PAGE
from madd.structure3d import (candidate_model3d, receptor_for_target,
                              smiles_to_sdf)

_MTCH2_BUNDLE = Path(
    "designer-output/target-mtch2-inhibition-2026-10-25/bundle.json")


def test_sdf_for_ethanol():
    """Ethanol's molfile carries 3 atoms and the M END marker."""
    out = smiles_to_sdf("CCO")
    assert out["status"] == "ok"
    lines = out["sdf"].splitlines()
    counts = lines[3]
    assert int(counts[0:3]) == 3
    assert "M  END" in out["sdf"]
    assert smiles_to_sdf("not-a-smiles(((")["status"] == "invalid"


def test_receptor_registry_mtch2_only():
    """MTCH2 resolves to the shipped predicted model (303 CA atoms,
    labelled predicted); other targets and empty input get none."""
    rec = receptor_for_target("MTCH2 (inhibition)")
    assert rec is not None
    assert rec["kind"] == "predicted"
    assert rec["format"] == "pdb"
    assert rec["data"].count(" CA ") == 303
    assert "AF-Q9Y6C9-F1" in rec["detail"]
    assert receptor_for_target("KRAS G12C") is None
    assert receptor_for_target(None) is None
    assert receptor_for_target("") is None


def test_model3d_payload_shapes():
    """A synthetic design bundle yields a molecule with no receptor;
    a sequence candidate stays not applicable."""
    design = {"kind": "design_run",
              "brief": {"target": "TARGET-X"},
              "candidates": [
                  {"candidate_id": "mol",
                   "structure": {"format": "smiles", "value": "CCO"}},
                  {"candidate_id": "pep",
                   "structure": {"format": "sequence",
                                 "value": "ACDEFG"}}],
              "ranking": {"ranked": ["mol", "pep"], "excluded": []}}
    out = candidate_model3d(design, "mol")
    assert out["status"] == "ok"
    assert out["mol_format"] == "sdf" and "M  END" in out["mol"]
    assert out["receptor"] is None
    assert "not been docked" in out["note"]
    seq = candidate_model3d(design, "pep")
    assert seq["status"] == "not_applicable"


def test_model3d_mtch2_bundle_when_present():
    """The published MTCH2 bundle's top candidate pairs its molfile
    with the MTCH2 receptor model (skips when the bundle is
    absent)."""
    if not _MTCH2_BUNDLE.exists():
        return
    bundle = json.loads(_MTCH2_BUNDLE.read_text())
    out = candidate_model3d(bundle, "panel-b-cand-1")
    assert out["status"] == "ok"
    assert out["receptor"] is not None
    assert out["receptor"]["kind"] == "predicted"


def test_page_loads_webgl_library():
    """The console page loads the vendored WebGL library and calls
    the model3d endpoint."""
    assert "/assets/3Dmol-min.js" in PAGE
    assert "/model3d/" in PAGE
    assert "glMolStyle" in PAGE
