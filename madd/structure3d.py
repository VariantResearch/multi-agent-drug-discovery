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
a registered predicted model, labelled predicted
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


# Receptor structures registered with the package, keyed by the
# target name they belong to. None ship today: the application
# opens blank, for the operator's own targets, and a target with
# no entry simply has no receptor on file - the console says so
# rather than substituting another protein or preloading an
# example target. When a structure is registered, its entry
# names its kind plainly: a predicted model is labelled
# predicted, never presented as an experimental structure.
RECEPTORS = {}


def receptor_for_target(target) -> dict:
    """The receptor structure on file for a target name, or None.

    Matches the target name against the registry (normalizing
    case, spaces, and parentheticals). The registry ships empty,
    so this returns None for every target until a structure is
    registered.
    Returns the registry metadata plus the PDB text, or None when
    no structure is on file for the target.
    """
    if not target:
        return None
    from pathlib import Path
    norm = "".join(ch for ch in str(target).upper() if ch.isalnum())
    for key, info in RECEPTORS.items():
        if key in norm:
            if info.get("path"):
                path = Path(info["path"])
            else:
                path = Path(__file__).parent / "assets" / info["file"]
            if not path.exists():
                return None
            out = {k: v for k, v in info.items() if k != "file"}
            out["format"] = "pdb"
            out["data"] = path.read_text()
            return out
    return None


UNIPROT_SEARCH = ("https://rest.uniprot.org/uniprotkb/search"
                  "?query=gene_exact:{symbol}+AND+organism_id:9606"
                  "+AND+reviewed:true&format=json&fields=accession"
                  "&size=1")
ALPHAFOLD_API = "https://alphafold.ebi.ac.uk/api/prediction/"

_ACCESSION_RE = __import__("re").compile(
    r"\b([OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9][A-Z][A-Z0-9]{2}[0-9])\b")
_GENE_RE = __import__("re").compile(r"^[A-Z][A-Z0-9-]{1,11}$")


def _get(fetcher, url):
    """One GET through a resolve-style fetcher, or None on failure."""
    try:
        status, body = fetcher(url)
    except Exception:
        return None
    return body if status == 200 else None


def resolve_uniprot_accession(target, fetcher=None):
    """Resolve a target name to a human UniProt accession, or None.

    An accession written into the target text wins. Otherwise the
    target's first token is tried as a gene symbol against the
    UniProt REST search (reviewed human entries only). Anything
    ambiguous or unresolvable returns None: a wrong structure is
    worse than none on file.
    """
    import json as _json

    from .resolve import default_fetcher
    fetch = fetcher if fetcher is not None else default_fetcher
    text = str(target or "")
    match = _ACCESSION_RE.search(text.upper())
    if match:
        return match.group(1)
    tokens = text.replace("(", " ").replace(")", " ").split()
    if not tokens or not _GENE_RE.match(tokens[0].upper()):
        return None
    body = _get(fetch, UNIPROT_SEARCH.format(
        symbol=__import__("urllib.parse", fromlist=["quote"]).quote(
            tokens[0].upper(), safe="")))
    if not body:
        return None
    try:
        results = _json.loads(body).get("results") or []
    except Exception:
        return None
    if len(results) != 1:
        return None
    return results[0].get("primaryAccession")


def fetch_receptor(target, fetcher=None, cache_dir=None):
    """Fetch a target's AlphaFold predicted model on demand.

    Resolves the target to a UniProt accession, asks the
    AlphaFold API for its predicted model, downloads the PDB,
    caches it under cache_dir (default ~/.madd/structures), and
    registers it in RECEPTORS for this process. Returns the
    receptor payload (metadata plus PDB text) or None when the
    target cannot be resolved or the services do not answer.
    The entry is labelled predicted with its source, model
    version, and mean pLDDT: fetched on demand for the operator's
    own target, never a prefilled example.
    """
    import json as _json
    from datetime import date
    from pathlib import Path

    from .resolve import default_fetcher
    fetch = fetcher if fetcher is not None else default_fetcher
    existing = receptor_for_target(target)
    if existing is not None:
        return existing
    accession = resolve_uniprot_accession(target, fetcher=fetch)
    if not accession:
        return None
    body = _get(fetch, ALPHAFOLD_API + accession)
    if not body:
        return None
    try:
        entries = _json.loads(body)
        entry = entries[0] if isinstance(entries, list) and entries else None
    except Exception:
        entry = None
    if not entry or not entry.get("pdbUrl"):
        return None
    pdb_text = _get(fetch, entry["pdbUrl"])
    if not pdb_text or "ATOM" not in pdb_text:
        return None
    folder = Path(cache_dir) if cache_dir else (
        Path.home() / ".madd" / "structures")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (accession + ".pdb")
    path.write_text(pdb_text, encoding="utf-8")
    gene = entry.get("gene") or accession
    RECEPTORS[str(gene).upper()] = {
        "path": str(path),
        "label": (str(gene) + " (human, UniProt " + accession + ")"),
        "kind": "predicted",
        "detail": ("AlphaFold predicted model "
                   + str(entry.get("modelEntityId") or accession)
                   + " v" + str(entry.get("latestVersion") or "?")
                   + ", mean pLDDT "
                   + str(entry.get("globalMetricValue") or "?")
                   + "; fetched " + date.today().isoformat()
                   + "; not an experimental structure"),
        "source": "AlphaFold Protein Structure Database (CC BY 4.0)",
    }
    return receptor_for_target(target) or receptor_for_target(accession)


def candidate_model3d(bundle: dict, candidate_id: str,
                      fetch_missing: bool = False, cache_dir=None) -> dict:
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
    if receptor is None and fetch_missing:
        receptor = fetch_receptor(brief.get("target"), cache_dir=cache_dir)
    return {"status": "ok", "candidate_id": candidate_id,
            "smiles": structure.get("value"),
            "mol_format": "sdf", "mol": built["sdf"],
            "receptor": receptor,
            "note": ("Molecule: generated conformer (RDKit ETKDG + "
                     "MMFF), not a measured structure. Receptor and "
                     "molecule are shown in separate views; the "
                     "candidate has not been docked, so no binding "
                     "pose is shown or claimed.")}
