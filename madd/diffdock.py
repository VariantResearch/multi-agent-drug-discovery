"""DiffDock pose cross-check: a second, independent docking
method against the Vina pose.

A Vina pose is one scoring function's geometry. DiffDock
(MIT, gcorso/DiffDock) is a diffusion model that predicts
poses by a wholly different method, so where the two put the
same ligand in the same place, the placement is corroborated
by unlike machinery, and where they disagree, that is worth
knowing too. This module runs DiffDock where an installation
is configured and records the comparison:

- Configuration: MADD_DIFFDOCK_HOME names a DiffDock checkout
  (the directory holding its inference module). The run is
  `python -m inference --protein_path <pdb>
  --ligand_description <smiles> --out_dir <dir>` from that
  checkout, the project's documented entry point.
- The comparison is a centroid agreement: the distance
  between the DiffDock top pose's atom centroid and the Vina
  pose's, graded agree (at most 2.0 A), partial (at most
  4.0 A), or disagree. A centroid is a coarse summary, not an
  RMSD, and the record says so; neither pose is evidence of
  binding, and agreement is agreement between two computed
  geometries, nothing more.
- DiffDock's own confidence for its top pose is recorded when
  the run's output reports one (a results CSV); when it does
  not, confidence is recorded as unreported rather than
  reconstructed.
- No installation configured: status not_available with the
  reason, and the caller adds no cross-check to the docking
  record at all, so absence never reads as a failed check.
"""
import csv
import math
import os
import subprocess
import sys
from pathlib import Path

TOOL_NAME = "DiffDock"
ENV_HOME = "MADD_DIFFDOCK_HOME"
AGREE_A = 2.0
PARTIAL_A = 4.0
NOTE = ("centroid agreement between two computed poses (Vina "
        "and DiffDock); a coarse geometry comparison, not an "
        "RMSD and not evidence of binding")


def configured_home():
    """The configured DiffDock checkout path, or None when the
    environment does not name an existing one."""
    home = os.environ.get(ENV_HOME, "").strip()
    if home and Path(home).is_dir():
        return home
    return None


def _centroid_from_pdb(text: str):
    """Mean atom position from PDB ATOM/HETATM lines, or None."""
    points = []
    for line in (text or "").splitlines():
        if line.startswith(("ATOM", "HETATM")):
            try:
                points.append((float(line[30:38]), float(line[38:46]),
                               float(line[46:54])))
            except ValueError:
                continue
    if not points:
        return None
    n = float(len(points))
    return tuple(sum(p[i] for p in points) / n for i in range(3))


def _centroid_from_sdf(text: str):
    """Mean atom position from an SDF mol block, or None. The
    atom count is line 4's first field; atom lines follow."""
    lines = (text or "").splitlines()
    if len(lines) < 4:
        return None
    try:
        count = int(lines[3][:3])
    except ValueError:
        return None
    points = []
    for line in lines[4:4 + count]:
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            points.append((float(parts[0]), float(parts[1]),
                           float(parts[2])))
        except ValueError:
            continue
    if not points:
        return None
    n = float(len(points))
    return tuple(sum(p[i] for p in points) / n for i in range(3))


def _distance(a, b) -> float:
    """Euclidean distance between two 3D points."""
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def agreement_for(distance_a: float) -> str:
    """Grade one centroid distance: agree, partial, disagree."""
    if distance_a <= AGREE_A:
        return "agree"
    if distance_a <= PARTIAL_A:
        return "partial"
    return "disagree"


def _default_runner(home, protein_path, smiles, out_dir):
    """Run DiffDock's inference entry point in its checkout."""
    return subprocess.run(
        [sys.executable, "-m", "inference",
         "--protein_path", str(protein_path),
         "--ligand_description", smiles,
         "--out_dir", str(out_dir)],
        cwd=home, capture_output=True, text=True, timeout=1800)


def _find_top_pose(out_dir: Path):
    """The run's top-ranked pose file: a rank1 SDF anywhere
    under the output directory, else the first rank*.sdf."""
    ranked = sorted(out_dir.rglob("rank*.sdf"))
    if not ranked:
        return None
    for path in ranked:
        if path.name.startswith("rank1"):
            return path
    return ranked[0]


def _find_confidence(out_dir: Path):
    """DiffDock's reported confidence for its top pose from a
    results CSV under the output directory, or None when the
    run reported none in a readable place."""
    for path in sorted(out_dir.rglob("*.csv")):
        try:
            rows = list(csv.DictReader(
                path.read_text(encoding="utf-8").splitlines()))
        except Exception:
            continue
        for row in rows:
            for key, value in row.items():
                if key and "confidence" in key.lower() and value:
                    try:
                        return float(value)
                    except ValueError:
                        continue
    return None


def cross_check(receptor_pdb: str, smiles: str, vina_pose_pdb: str,
                work_dir, runner=None, use: str = "research") -> dict:
    """Run DiffDock on the same receptor and ligand and compare
    its top pose against the Vina pose. Returns the cross-check
    record; status is completed, not_available, blocked_license,
    or failed, never an exception for tool problems."""
    from .license_registry import check_tool
    record = {"tool": TOOL_NAME, "kind": "docking_cross_check",
              "status": "completed", "note": NOTE}
    verdict = check_tool(TOOL_NAME, use)
    record["license"] = verdict
    if not verdict.get("allowed"):
        record["status"] = "blocked_license"
        record["detail"] = verdict.get("reason") or "registry refusal"
        return record
    home = configured_home()
    if home is None:
        record["status"] = "not_available"
        record["detail"] = ("no DiffDock installation is configured "
                            "(set " + ENV_HOME + " to a DiffDock "
                            "checkout); no cross-check was run")
        return record
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    protein = work / "receptor.pdb"
    protein.write_text(receptor_pdb, encoding="utf-8")
    out_dir = work / "diffdock-out"
    run = runner or _default_runner
    try:
        result = run(home, protein, smiles, out_dir)
    except Exception as exc:
        record["status"] = "failed"
        record["detail"] = ("DiffDock run failed: "
                            + type(exc).__name__ + ": " + str(exc))
        return record
    if getattr(result, "returncode", 0) != 0:
        record["status"] = "failed"
        record["detail"] = ("DiffDock exited "
                            + str(getattr(result, "returncode", "?"))
                            + ": " + str(getattr(result, "stderr", "")
                                         or "")[-300:])
        return record
    pose_path = _find_top_pose(out_dir)
    if pose_path is None:
        record["status"] = "failed"
        record["detail"] = "DiffDock produced no ranked pose file"
        return record
    diffdock_centroid = _centroid_from_sdf(
        pose_path.read_text(encoding="utf-8", errors="replace"))
    vina_centroid = _centroid_from_pdb(vina_pose_pdb)
    if diffdock_centroid is None or vina_centroid is None:
        record["status"] = "failed"
        record["detail"] = ("a pose centroid could not be computed "
                            "(diffdock pose parseable: "
                            + str(diffdock_centroid is not None)
                            + ", vina pose parseable: "
                            + str(vina_centroid is not None) + ")")
        return record
    distance = _distance(diffdock_centroid, vina_centroid)
    record["centroid_distance_a"] = round(distance, 2)
    record["agreement"] = agreement_for(distance)
    record["diffdock_confidence"] = _find_confidence(out_dir)
    record["diffdock_pose_file"] = pose_path.name
    return record
