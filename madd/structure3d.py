"""3D structure generation for designed candidates.

The console shows a ranked candidate as a rotatable 3D ball-and-stick
model. This module produces the geometry: RDKit embeds one 3D
conformer for the candidate's SMILES (deterministic seed, heavy
atoms only) and returns plain data - element symbols, coordinates
in angstroms, and bonds with orders - that the GUI renders. The
conformer is a generated geometry for visualization, not a measured
structure and not a docked pose; nothing here asserts the molecule
adopts it. When RDKit is unavailable, or the SMILES does not parse,
or embedding fails, the status says so and no geometry is invented.
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


def candidate_structure3d(bundle: dict, candidate_id: str) -> dict:
    """The 3D structure payload for one candidate of a run bundle.

    Accepts a design bundle or a target-run bundle (whose design
    stage is nested). Sequence candidates carry no SMILES and get an
    honest not_applicable status: this viewer renders small-molecule
    structures only.
    """
    design = bundle if bundle.get("kind") == "design_run" \
        else bundle.get("design") or {}
    candidate = None
    for cand in design.get("candidates") or []:
        if cand.get("candidate_id") == candidate_id:
            candidate = cand
            break
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
