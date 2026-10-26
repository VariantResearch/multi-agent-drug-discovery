"""3D structure generation for designed candidates.

The console shows a ranked candidate as a fully rendered 3D model.
This module produces the geometry two ways from the same embedding:
plain atom and bond data for the lightweight canvas fallback, and a
molfile for the WebGL viewer (3Dmol.js, vendored under assets/).
RDKit embeds one 3D conformer for the candidate's SMILES
(deterministic seed, heavy atoms only). The conformer is a
generated geometry for visualization, not a measured structure and
not a docked pose; nothing here asserts the molecule adopts it.

The module also serves receptor structures shipped with the
package (assets/receptors/), keyed by target name: today that is
the AlphaFold predicted model for human MTCH2, labelled predicted
wherever it is used. A target with no shipped structure gets an
honest none. Molecule and receptor are always separate models for
separate views - no run here docks anything, so no binding pose is
ever presented. When RDKit is unavailable, or the SMILES does not
parse, or embedding fails, the status says so and no geometry is
invented.
"""
from __future__ import annotations

# CPK-style element colors, brightened for the console theme.
ELEMENT_COLORS = {
    "C": "#b8b8d0", "H": "#ffffff", "O": "#ff5a5a", "N": "#5a7fff",
    "S": "#ffd75a", "P": "#ff9a3c", "F": "#7dff8a", "Cl": "#4ae38a",
    "Br": "#a62929", "I": "#940094",
}
_DEFAULT_COLOR = "#ff71ce"


def element_color(symbol: str) -> str:
    """The display color for an element symbol."""
    return ELEMENT_COLORS.get(symbol, _DEFAULT_COLOR)


def smiles_to_3d(smiles: str) -> dict:
    """Embed one 3D conformer for a SMILES string.

    Returns {"status": "ok", "atoms": [...], "bonds": [...],
    "atom_count": n} on success, or {"status": "unavailable" |
    "invalid" | "embed_failed", "reason": ...} without geometry.
    Coordinates are heavy-atom positions in angstroms from RDKit's
    ETKDG embedding with a fixed seed, so the same SMILES yields the
    same view on every load.
    """
    from . import design_rdkit
    if not design_rdkit.available():
        return {"status": "unavailable",
                "reason": "RDKit is not installed in this environment"}
    if not isinstance(smiles, str) or not smiles.strip():
        return {"status": "invalid", "reason": "no SMILES structure"}
    from rdkit import Chem
    from rdkit.Chem import AllChem
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return {"status": "invalid",
                "reason": "RDKit could not parse the SMILES"}
    mol = Chem.AddHs(mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = 20261025
    if AllChem.EmbedMolecule(mol, params) != 0:
        return {"status": "embed_failed",
                "reason": "RDKit could not embed a 3D conformer"}
    try:
        AllChem.MMFFOptimizeMolecule(mol, maxIters=200)
    except Exception:
        pass
    mol = Chem.RemoveHs(mol)
    conf = mol.GetConformer()
    atoms = []
    for atom in mol.GetAtoms():
        pos = conf.GetAtomPosition(atom.GetIdx())
        symbol = atom.GetSymbol()
        atoms.append({"element": symbol, "x": round(pos.x, 3),
                      "y": round(pos.y, 3), "z": round(pos.z, 3),
                      "color": element_color(symbol)})
    bonds = []
    for bond in mol.GetBonds():
        bonds.append({"a": bond.GetBeginAtomIdx(),
                      "b": bond.GetEndAtomIdx(),
                      "order": float(bond.GetBondTypeAsDouble())})
    return {"status": "ok", "atoms": atoms, "bonds": bonds,
            "atom_count": len(atoms),
            "note": ("Generated conformer (RDKit ETKDG + MMFF) for "
                     "visualization; not a measured structure or a "
                     "docked pose.")}


def _find_candidate(bundle: dict, candidate_id: str):
    """The (design bundle, candidate) pair for a candidate id in a
    design bundle or a target-run bundle's nested design stage;
    the candidate is None when the run has no such candidate."""
    design = bundle if bundle.get("kind") == "design_run" \
        else bundle.get("design") or {}
    for cand in design.get("candidates") or []:
        if cand.get("candidate_id") == candidate_id:
            return design, cand
    return design, None


def candidate_structure3d(bundle: dict, candidate_id: str) -> dict:
    """The 3D structure payload for one candidate of a run bundle.

    Accepts a design bundle or a target-run bundle (whose design
    stage is nested). Sequence candidates carry no SMILES and get an
    honest not_applicable status: this viewer renders small-molecule
    structures only.
    """
    design, candidate = _find_candidate(bundle, candidate_id)
    if candidate is None:
        return {"status": "not_found",
                "reason": "no such candidate in this run"}
    structure = candidate.get("structure") or {}
    if str(structure.get("format") or "").lower() != "smiles":
        return {"status": "not_applicable",
                "reason": ("candidate structure is a sequence, not a "
                           "SMILES; the 3D viewer renders small "
                           "molecules")}
    payload = smiles_to_3d(structure.get("value"))
    payload["candidate_id"] = candidate_id
    payload["smiles"] = structure.get("value")
    return payload


def smiles_to_sdf(smiles: str) -> dict:
    """The same embedded conformer as smiles_to_3d, as molfile text.

    Returns {"status": "ok", "sdf": text} on success, or the same
    honest failure statuses as smiles_to_3d, without content. The
    fully rendered WebGL viewer consumes molfiles; the coordinates
    are the ETKDG embedding with the fixed seed, hydrogens removed.
    """
    from . import design_rdkit
    if not design_rdkit.available():
        return {"status": "unavailable",
                "reason": "RDKit is not installed in this environment"}
    if not isinstance(smiles, str) or not smiles.strip():
        return {"status": "invalid", "reason": "no SMILES structure"}
    import io

    from rdkit import Chem
    from rdkit.Chem import AllChem
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return {"status": "invalid",
                "reason": "RDKit could not parse the SMILES"}
    mol = Chem.AddHs(mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = 20261025
    if AllChem.EmbedMolecule(mol, params) != 0:
        return {"status": "embed_failed",
                "reason": "RDKit could not embed a 3D conformer"}
    try:
        AllChem.MMFFOptimizeMolecule(mol, maxIters=200)
    except Exception:
        pass
    mol = Chem.RemoveHs(mol)
    buffer = io.StringIO()
    writer = Chem.SDWriter(buffer)
    writer.write(mol)
    writer.close()
    return {"status": "ok", "sdf": buffer.getvalue()}


# Receptor structures shipped with the package, keyed by the target
# name they belong to. A target with no entry simply has no receptor
# on file; the console says so rather than substituting another
# protein. Every entry names its kind plainly: a predicted model is
# labelled predicted, never presented as an experimental structure.
RECEPTORS = {
    "MTCH2": {
        "file": "receptors/mtch2_alphafold.pdb",
        "label": "MTCH2 (human, UniProt Q9Y6C9)",
        "kind": "predicted",
        "detail": ("AlphaFold predicted model AF-Q9Y6C9-F1 v6, mean "
                   "pLDDT 86.3; not an experimental structure"),
        "source": "AlphaFold Protein Structure Database (CC BY 4.0)",
    },
}


def receptor_for_target(target) -> dict:
    """The receptor structure on file for a target name, or None.

    Matches the target name against the shipped registry
    (normalizing case, spaces, and parentheticals, so a brief
    target of "MTCH2 (inhibition)" matches the MTCH2 entry).
    Returns the registry metadata plus the PDB text, or None when
    no structure is on file for the target.
    """
    if not target:
        return None
    from pathlib import Path
    norm = "".join(ch for ch in str(target).upper() if ch.isalnum())
    for key, info in RECEPTORS.items():
        if key in norm:
            path = Path(__file__).parent / "assets" / info["file"]
            if not path.exists():
                return None
            out = {k: v for k, v in info.items() if k != "file"}
            out["format"] = "pdb"
            out["data"] = path.read_text()
            return out
    return None


def candidate_model3d(bundle: dict, candidate_id: str) -> dict:
    """The fully rendered 3D model payload for one candidate: its
    molfile plus the receptor structure on file for the design
    brief's target, when one is shipped.

    The molecule and the receptor are separate models for separate
    views. Nothing here docks the candidate into the receptor, and
    the payload says so: presenting the two as a complex would
    claim a binding pose no run produced.
    """
    design, candidate = _find_candidate(bundle, candidate_id)
    if candidate is None:
        return {"status": "not_found",
                "reason": "no such candidate in this run"}
    structure = candidate.get("structure") or {}
    if str(structure.get("format") or "").lower() != "smiles":
        return {"status": "not_applicable",
                "reason": ("candidate structure is a sequence, not a "
                           "SMILES; the 3D viewer renders small "
                           "molecules")}
    built = smiles_to_sdf(structure.get("value"))
    if built["status"] != "ok":
        return built
    brief = design.get("brief") or {}
    receptor = receptor_for_target(brief.get("target"))
    return {"status": "ok", "candidate_id": candidate_id,
            "smiles": structure.get("value"),
            "mol_format": "sdf", "mol": built["sdf"],
            "receptor": receptor,
            "note": ("Molecule: generated conformer (RDKit ETKDG + "
                     "MMFF), not a measured structure. Receptor and "
                     "molecule are shown in separate views; the "
                     "candidate has not been docked, so no binding "
                     "pose is shown or claimed.")}
