"""Docking: place a candidate into a receptor structure with
AutoDock Vina, through Meeko preparation.

A docking pose is a computed geometry, not evidence of binding,
and every record this module produces says so. The spike that
justified shipping it (2026-10-26): indinavir, prepared from its
PubChem SMILES exactly as a candidate is prepared here, redocked
into HIV-1 protease (PDB 1HSG, receptor prepared from the PDB
exactly as a fetched structure is prepared here) with Vina
1.2.5; the top pose's centroid landed 0.61 A from the crystal
ligand's centroid with every pose atom within 2.5 A of a crystal
ligand atom, at -8.5 kcal/mol; a replicate run landed 1.26 A away
with 40 of 49 pose atoms within 2.5 A (its modes scored -10.2 to
-9.3 kcal/mol or better). Vina is stochastic, so runs vary; both
reproduced the crystal pose. The pipeline reproduces a known
pose; it does not validate any new one.

Availability is honest: Vina (binary on PATH or MADD_VINA_BIN)
and Meeko (with its receptor preparer beside the interpreter)
are optional dependencies. When either is missing, docking
reports not_available with the reason instead of failing.

The search box defaults to the receptor's CA centroid with a
24 A cube: a blind dock, labelled as such in the record. An
operator who knows the binding site passes a center (and size)
explicitly.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

NOTE = ("computed docking pose (AutoDock Vina via Meeko "
        "preparation): a geometry the scoring function prefers, "
        "not evidence of binding, affinity, or activity")


def vina_path():
    """Locate the Vina binary: MADD_VINA_BIN, then PATH."""
    override = os.environ.get("MADD_VINA_BIN")
    if override and Path(override).exists():
        return override
    return shutil.which("vina")


def receptor_preparer():
    """Locate Meeko's receptor preparation script beside the
    running interpreter (it ships with the meeko package)."""
    candidate = Path(sys.executable).parent / "mk_prepare_receptor.py"
    return str(candidate) if candidate.exists() else None


def available() -> dict:
    """Report whether docking can run here, and why not when it
    cannot."""
    problems = []
    if vina_path() is None:
        problems.append("AutoDock Vina binary not found "
                        "(PATH or MADD_VINA_BIN)")
    if receptor_preparer() is None:
        problems.append("Meeko receptor preparer not found beside "
                        "the interpreter (pip install meeko prody gemmi)")
    try:
        import meeko  # noqa: F401
        from rdkit import Chem  # noqa: F401
    except Exception as exc:
        problems.append("preparation libraries unavailable: " + str(exc))
    return {"available": not problems, "problems": problems,
            "vina": vina_path()}


def _ca_centroid(pdb_text: str):
    """The mean CA position of a PDB text, or None."""
    points = []
    for line in pdb_text.splitlines():
        if line.startswith("ATOM") and line[12:16].strip() == "CA":
            points.append((float(line[30:38]), float(line[38:46]),
                           float(line[46:54])))
    if not points:
        return None
    return [round(sum(p[i] for p in points) / len(points), 2)
            for i in range(3)]


def _ligand_pdbqt(smiles: str) -> str:
    """Prepare a ligand PDBQT from SMILES: RDKit ETKDG conformer,
    then Meeko (the spike-validated path)."""
    from meeko import MoleculePreparation, PDBQTWriterLegacy
    from rdkit import Chem
    from rdkit.Chem import AllChem
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    if mol is None:
        raise ValueError("candidate SMILES does not parse")
    AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
    setups = MoleculePreparation().prepare(mol)
    pdbqt, ok, error = PDBQTWriterLegacy.write_string(setups[0])
    if not ok:
        raise ValueError("Meeko ligand preparation failed: " + str(error))
    return pdbqt


def _pose_pdb(pdbqt_text: str) -> str:
    """Convert the first pose of a Vina PDBQT output to PDB text
    for display (coordinates and elements; no bond orders claimed)."""
    out = []
    serial = 0
    for line in pdbqt_text.splitlines():
        if line.startswith("ENDMDL"):
            break
        if line.startswith(("ATOM", "HETATM")):
            parts = line.split()
            element = parts[-1].strip("0123456789").capitalize()
            serial += 1
            out.append(
                "HETATM%5d %-4s LIG A   1    %8.3f%8.3f%8.3f  1.00  0.00"
                "          %s" % (serial, parts[2], float(parts[5]),
                                  float(parts[6]), float(parts[7]),
                                  element))
    out.append("END")
    return "\n".join(out) + "\n"


def _best_affinity(pdbqt_text: str):
    """The first pose's Vina affinity from its REMARK VINA RESULT
    line, or None."""
    for line in pdbqt_text.splitlines():
        if "VINA RESULT" in line:
            try:
                return float(line.split(":")[1].split()[0])
            except Exception:
                return None
    return None


def dock_candidate(receptor_pdb: str, smiles: str, work_dir,
                   center=None, size: float = 24.0,
                   exhaustiveness: int = 8,
                   timeout: int = 900) -> dict:
    """Dock one candidate into a receptor PDB text. Returns the
    docking record; status is completed, not_available, or failed
    (with the reason), never an exception for tool problems."""
    check = available()
    record = {"tool": "AutoDock Vina", "kind": "docking",
              "status": "completed", "note": NOTE,
              "exhaustiveness": exhaustiveness}
    if not check["available"]:
        record["status"] = "not_available"
        record["problems"] = check["problems"]
        return record
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    try:
        (work / "receptor.pdb").write_text(receptor_pdb, encoding="utf-8")
        (work / "ligand.pdbqt").write_text(_ligand_pdbqt(smiles),
                                           encoding="utf-8")
        prep = subprocess.run(
            [sys.executable, receptor_preparer(), "-i", "receptor.pdb",
             "-o", "receptor", "-p", "receptor.pdbqt"],
            cwd=str(work), capture_output=True, text=True, timeout=600)
        if prep.returncode != 0 or not (work / "receptor.pdbqt").exists():
            record["status"] = "failed"
            record["detail"] = ("receptor preparation failed: "
                                + (prep.stderr or prep.stdout)[-300:])
            return record
        box_center = center or _ca_centroid(receptor_pdb)
        if box_center is None:
            record["status"] = "failed"
            record["detail"] = ("no box center given and the receptor "
                                "has no CA atoms to center on")
            return record
        record["box"] = {"center": list(box_center), "size": size,
                         "source": ("operator-supplied center" if center
                                    else "receptor CA centroid (blind dock)")}
        run = subprocess.run(
            [check["vina"], "--receptor", "receptor.pdbqt",
             "--ligand", "ligand.pdbqt",
             "--center_x", str(box_center[0]),
             "--center_y", str(box_center[1]),
             "--center_z", str(box_center[2]),
             "--size_x", str(size), "--size_y", str(size),
             "--size_z", str(size),
             "--exhaustiveness", str(exhaustiveness),
             "--out", "poses.pdbqt"],
            cwd=str(work), capture_output=True, text=True,
            timeout=timeout)
        poses_path = work / "poses.pdbqt"
        if run.returncode != 0 or not poses_path.exists():
            record["status"] = "failed"
            record["detail"] = ("Vina failed: "
                                + (run.stderr or run.stdout)[-300:])
            return record
        poses = poses_path.read_text(encoding="utf-8")
        record["affinity_kcal_mol"] = _best_affinity(poses)
        record["pose_format"] = "pdb"
        record["pose"] = _pose_pdb(poses)
        return record
    except subprocess.TimeoutExpired:
        record["status"] = "failed"
        record["detail"] = "docking timed out"
        return record
    except Exception as exc:
        record["status"] = "failed"
        record["detail"] = str(exc)
        return record


def docking_record_path(run_dir, candidate_id: str) -> Path:
    """Where a run folder keeps one candidate's docking record."""
    safe = "".join(ch for ch in str(candidate_id)
                   if ch.isalnum() or ch in "-_")
    return Path(run_dir) / ("docking-" + safe + ".json")


def load_docking_record(run_dir, candidate_id: str):
    """A stored docking record for a candidate, or None."""
    path = docking_record_path(run_dir, candidate_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
