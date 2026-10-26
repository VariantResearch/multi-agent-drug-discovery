"""Structure3d tests: conformer generation for SMILES candidates,
honest statuses for everything else, and bundle lookup across
design and target-run bundles.

Structures here are simple known molecules used as fixtures; the
tests assert geometry plumbing (atom and bond counts), not any
candidate's merit."""
import json
from pathlib import Path

from madd.structure3d import candidate_structure3d, smiles_to_3d


def test_ethanol_geometry():
    """Ethanol embeds to 3 heavy atoms and 2 bonds, deterministically."""
    out = smiles_to_3d("CCO")
    assert out["status"] == "ok"
    assert out["atom_count"] == 3
    assert sorted(a["element"] for a in out["atoms"]) == ["C", "C", "O"]
    assert len(out["bonds"]) == 2
    again = smiles_to_3d("CCO")
    assert again["atoms"] == out["atoms"]


def test_invalid_smiles_status():
    """An unparseable SMILES returns invalid, never geometry."""
    out = smiles_to_3d("not-a-smiles(((")
    assert out["status"] == "invalid"
    assert "atoms" not in out


def test_bundle_lookup_design_and_target():
    """Candidate lookup works on design bundles and target bundles,
    and sequence candidates are honestly not applicable."""
    design = {"kind": "design_run", "candidates": [
        {"candidate_id": "mol", "structure": {"format": "smiles",
                                              "value": "CCO"}},
        {"candidate_id": "pep", "structure": {"format": "sequence",
                                              "value": "ACDEFG"}}]}
    out = candidate_structure3d(design, "mol")
    assert out["status"] == "ok" and out["candidate_id"] == "mol"
    seq = candidate_structure3d(design, "pep")
    assert seq["status"] == "not_applicable"
    missing = candidate_structure3d(design, "nope")
    assert missing["status"] == "not_found"
    target = {"kind": "target_run", "design": design}
    out2 = candidate_structure3d(target, "mol")
    assert out2["status"] == "ok"


def test_mtch2_bundle_top_candidate_when_present():
    """The published MTCH2 bundle's top candidate yields a structure
    (skips silently when the local runs directory is absent)."""
    path = Path("runs/target-mtch2-inhibition-2026-10-25/bundle.json")
    if not path.exists():
        return
    bundle = json.loads(path.read_text())
    out = candidate_structure3d(bundle, "panel-b-cand-1")
    assert out["status"] == "ok"
    assert out["atom_count"] == 24
