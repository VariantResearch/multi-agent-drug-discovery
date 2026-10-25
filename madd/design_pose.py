"""PoseBusters pose validation for docked or predicted structures.

A docking run or a structure tool can produce a pose that is
geometrically impossible: clashes, broken bond lengths, inverted
stereochemistry. PoseBusters (MIT, registry-cleared) is the standard
mechanical check for exactly that. This module wraps it the way the
other design bridges are wrapped: license gate first, an honest
not_installed when the package is absent, and a result that reports
each individual check rather than a single unexplained verdict.

Modes follow PoseBusters' own configs: "mol" checks a molecule's
intrinsic geometry (needs a pose file and, for stereochemistry and
identity checks, a reference molecule); "dock" adds protein-ligand
checks and needs the protein file too. The wrapper picks dock when a
protein path is given, mol otherwise, unless told otherwise.
"""
from __future__ import annotations

import importlib.util


def available() -> bool:
    """True when the posebusters package can be imported here."""
    try:
        return importlib.util.find_spec("posebusters") is not None
    except Exception:
        return False


def bust_pose(pose_path, reference_path=None, protein_path=None,
              use: str = "research", config: str = None) -> dict:
    """Run PoseBusters over one pose file.

    Returns {status, passed, checks, config, detail}: status is
    completed, not_installed, blocked_license, or failed; passed is
    True only when the run completed and every check passed, False
    when a check failed, and None when no verdict exists.
    """
    from .license_registry import check_tool
    result = {"status": "completed", "passed": None, "checks": {},
              "config": config, "detail": ""}
    verdict = check_tool("PoseBusters", use)
    if not verdict.get("allowed"):
        result["status"] = "blocked_license"
        result["detail"] = verdict.get("reason") or "registry refusal"
        return result
    if not available():
        result["status"] = "not_installed"
        result["detail"] = "posebusters is not installed in this environment"
        return result
    chosen = config or ("dock" if protein_path else "mol")
    result["config"] = chosen
    try:
        from posebusters import PoseBusters
        buster = PoseBusters(config=chosen)
        frame = buster.bust(mol_pred=str(pose_path),
                            mol_true=str(reference_path) if reference_path else None,
                            mol_cond=str(protein_path) if protein_path else None)
    except Exception as exc:
        result["status"] = "failed"
        result["detail"] = ("PoseBusters run failed: " + type(exc).__name__
                            + ": " + str(exc))
        return result
    if frame is None or len(frame) == 0:
        result["status"] = "failed"
        result["detail"] = "PoseBusters produced no results for this pose"
        return result
    row = frame.iloc[0]
    checks = {}
    for col in frame.columns:
        value = row[col]
        # PoseBusters reports numpy bool_ values, which are not Python
        # bools; accept both by type name so no check is silently lost.
        if isinstance(value, bool) or type(value).__name__ == "bool_":
            checks[str(col)] = bool(value)
    result["checks"] = checks
    result["passed"] = all(checks.values()) if checks else None
    if result["passed"] is False:
        failed = [name for name, ok in checks.items() if not ok]
        result["detail"] = "failed checks: " + ", ".join(failed)
    return result
