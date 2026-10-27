"""Fully rendered 3D model tests: molfile generation, the receptor
registry (empty as shipped - the application opens blank; a
registered structure resolves, everything else is an honest
none), and the combined candidate model payload."""
import json
from pathlib import Path

from madd.gui import PAGE
import madd.structure3d as structure3d
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


def test_receptor_registry_ships_empty():
    """As shipped, no target has a receptor on file - MTCH2
    included: the application carries no prefilled target."""
    assert receptor_for_target("MTCH2 (inhibition)") is None
    assert receptor_for_target("KRAS G12C") is None
    assert receptor_for_target(None) is None
    assert receptor_for_target("") is None


def test_receptor_registry_resolves_a_registered_structure(tmp_path):
    """The registry mechanism still works when a structure is
    registered: metadata plus PDB text, labelled by kind."""
    assets = Path(structure3d.__file__).parent / "assets"
    pdb = assets / "test-receptor.pdb"
    pdb.write_text("ATOM      1  CA  ALA A   1       0.0     0.0     0.0\nEND\n")
    structure3d.RECEPTORS["TESTPROT"] = {
        "file": "test-receptor.pdb", "label": "Test protein",
        "kind": "predicted", "detail": "test fixture",
        "source": "test"}
    try:
        rec = receptor_for_target("TESTPROT (assay)")
        assert rec is not None
        assert rec["kind"] == "predicted" and rec["format"] == "pdb"
        assert " CA " in rec["data"]
    finally:
        structure3d.RECEPTORS.pop("TESTPROT", None)
        pdb.unlink()


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
    """The published MTCH2 bundle's top candidate still renders
    its molfile; with the registry shipped empty, its receptor
    reads as none on file (the run record itself is unchanged)."""
    if not _MTCH2_BUNDLE.exists():
        return
    bundle = json.loads(_MTCH2_BUNDLE.read_text())
    out = candidate_model3d(bundle, "panel-b-cand-1")
    assert out["status"] == "ok"
    assert out["receptor"] is None


def test_page_loads_webgl_library():
    """The console page loads the vendored WebGL library and calls
    the model3d endpoint."""
    assert "/assets/3Dmol-min.js" in PAGE
    assert "/model3d/" in PAGE
    assert "glMolStyle" in PAGE
