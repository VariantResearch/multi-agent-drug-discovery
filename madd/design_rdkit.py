"""RDKit structure validation and computed descriptors for candidates.

RDKit is the one real cheminformatics engine in the design stage: it
parses a candidate's SMILES, says whether the structure is valid, and
computes descriptors (molecular weight, logP, TPSA, hydrogen bond
donors and acceptors, rotatable bonds) that are calculations, not
model opinions. Computed values enter a candidate's predicted
properties with the basis "computed:RDKit <version>", which the audit
keeps distinct from designer predictions.

RDKit is an optional dependency, deliberately: the package core is
standard-library only, and this bridge follows the same pattern as the
external tool runner. The license registry is checked before any use
(RDKit is BSD, allowed for research and commercial use). When RDKit is
not installed, enrichment reports not_installed and candidates keep
only what their designer gave them - nothing is fabricated to fill
the gap.
"""
from __future__ import annotations

import importlib.util

from . import license_registry

TOOL_NAME = "RDKit"


def available() -> bool:
    """True when the rdkit package is importable in this environment."""
    return importlib.util.find_spec("rdkit") is not None


def describe_smiles(smiles: str) -> dict:
    """Validate one SMILES string and compute its descriptors.

    Returns {valid, canonical_smiles, descriptors} for a parseable
    structure, or {valid: False, error} when RDKit rejects it. Raises
    RuntimeError when RDKit is not installed; callers check available()
    or use enrich_candidates, which reports instead of raising.
    """
    from rdkit import Chem
    from rdkit.Chem import Crippen, Descriptors, rdMolDescriptors
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return {"valid": False, "error": "RDKit could not parse the SMILES"}
    return {
        "valid": True,
        "canonical_smiles": Chem.MolToSmiles(mol),
        "descriptors": {
            "molecular_weight": round(float(Descriptors.MolWt(mol)), 3),
            "logp": round(float(Crippen.MolLogP(mol)), 3),
            "tpsa": round(float(rdMolDescriptors.CalcTPSA(mol)), 3),
            "hbd": int(rdMolDescriptors.CalcNumHBD(mol)),
            "hba": int(rdMolDescriptors.CalcNumHBA(mol)),
            "rotatable_bonds": int(rdMolDescriptors.CalcNumRotatableBonds(mol)),
        },
    }


def inchikey(smiles: str):
    """Return the standard InChIKey for a SMILES string, or None when
    RDKit is unavailable or the structure does not parse. The InChIKey
    is the join key the public chemistry registries index by."""
    if not available() or not isinstance(smiles, str):
        return None
    from rdkit import Chem
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    try:
        return Chem.MolToInchiKey(mol)
    except Exception:
        return None


def enrich_candidates(candidates: list, use: str = "research") -> dict:
    """Validate SMILES candidates and attach computed descriptors.

    Mutates the candidate dicts in place (computed properties appended,
    a structure_valid constraint result recorded for every SMILES
    candidate) and returns a tool-run style record of what happened:
    completed with counts, not_installed, or blocked_license.
    """
    record = {"tool": TOOL_NAME, "kind": "computed_properties",
              "requested": False, "use": use, "status": "not_run",
              "checked": 0, "valid": 0, "invalid": 0}
    verdict = license_registry.check_tool(TOOL_NAME, use)
    record["license"] = verdict
    if not verdict.get("allowed"):
        record["status"] = "blocked_license"
        record["reason"] = verdict.get("reason") or "registry does not allow this use"
        return record
    if not available():
        record["status"] = "not_installed"
        record["reason"] = "the rdkit package is not installed in this environment"
        return record
    import rdkit
    version = rdkit.__version__
    record["version"] = version
    basis = "computed:RDKit " + str(version)
    for cand in candidates:
        structure = cand.get("structure")
        if not isinstance(structure, dict):
            continue
        fmt = str(structure.get("format") or "").lower()
        value = structure.get("value")
        if fmt != "smiles" or not isinstance(value, str) or not value.strip():
            continue
        record["checked"] += 1
        result = describe_smiles(value)
        cand.setdefault("constraint_results", []).append({
            "constraint": "structure_valid_smiles", "kind": "computed",
            "status": "pass" if result["valid"] else "fail",
            "basis": basis + " MolFromSmiles"})
        if result["valid"]:
            record["valid"] += 1
            structure["canonical_smiles"] = result["canonical_smiles"]
            for name, val in result["descriptors"].items():
                cand.setdefault("predicted_properties", []).append(
                    {"name": name, "value": val, "basis": basis,
                     "verified": True})
        else:
            record["invalid"] += 1
    record["status"] = "completed"
    return record
