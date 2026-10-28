"""Cross-run candidate library export: one screening table.

Scans a runs directory for every designed run (target runs with a
design stage and standalone design runs) and writes one CSV with a
row per candidate - ranked and excluded alike - and a column per
computed property recorded anywhere in those runs. Values are the
record's own: identity from the production sheets, properties only
where the recorded basis is a computation (an RDKit or ADMET-AI
tool run), never designer predictions, which vary in shape and
meaning from candidate to candidate and do not belong in a
screening matrix. A candidate with no recorded value for a column
gets an empty cell, never a substitute.
"""

import csv
from pathlib import Path

from .production import build_production_sheets

FIXED_COLUMNS = ["run_id", "target", "rank", "status", "candidate_id",
                 "modality", "production_ready", "structure",
                 "formula", "exclusion_reasons"]


def _designs(runs_dir):
    """Yield (run_id, target_name, design) per designed run on disk."""
    from .storage import load_bundle
    runs = Path(runs_dir)
    if not runs.exists():
        return
    for child in sorted(runs.iterdir()):
        if not child.is_dir() or not (child / "bundle.json").exists():
            continue
        try:
            bundle = load_bundle(runs_dir, child.name)
        except Exception:
            continue
        design = None
        target = None
        if bundle.get("kind") == "target_run":
            design = bundle.get("design")
            target = (bundle.get("target") or {}).get("name")
        elif bundle.get("kind") == "design_run":
            design = bundle
            brief = bundle.get("brief") or {}
            named = brief.get("target")
            target = (named.get("name") if isinstance(named, dict)
                      else named)
        if design:
            yield child.name, target, design


def build_library(runs_dir):
    """The library table: (fieldnames, rows) over all designed runs.

    Rows follow run order then recorded rank; excluded candidates
    appear after the ranked ones with their recorded reasons.
    """
    property_names = []
    pending = []
    for run_id, target, design in _designs(runs_dir):
        sheets = {s["candidate_id"]: s
                  for s in build_production_sheets(design)}
        candidates = {c.get("candidate_id"): c
                      for c in design.get("candidates") or []}
        ranking = design.get("ranking") or {}
        ordered = [(cid, i + 1, "ranked", "")
                   for i, cid in enumerate(ranking.get("ranked") or [])]
        ordered += [(e.get("candidate_id"), None, "excluded",
                     "; ".join(e.get("reasons") or []))
                    for e in ranking.get("excluded") or []]
        for candidate_id, rank, status, reasons in ordered:
            candidate = candidates.get(candidate_id) or {}
            sheet = sheets.get(candidate_id) or {}
            identity = sheet.get("identity") or {}
            row = {
                "run_id": run_id,
                "target": target,
                "rank": rank,
                "status": status,
                "candidate_id": candidate_id,
                "modality": candidate.get("modality"),
                "production_ready": sheet.get("production_ready"),
                "structure": (identity.get("canonical_smiles")
                              or identity.get("value_as_proposed")),
                "formula": identity.get("molecular_formula"),
                "exclusion_reasons": reasons,
            }
            for prop in candidate.get("predicted_properties") or []:
                basis = str(prop.get("basis") or "")
                name = str(prop.get("name") or "")
                if not name or not basis.startswith("computed:"):
                    continue
                if name not in property_names:
                    property_names.append(name)
                row[name] = prop.get("value")
            pending.append(row)
    fieldnames = FIXED_COLUMNS + property_names
    for row in pending:
        for name in property_names:
            row.setdefault(name, None)
    return fieldnames, pending


def write_library_csv(runs_dir, out_path):
    """Write the library CSV; return the export summary."""
    fieldnames, rows = build_library(runs_dir)
    with open(out_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: ("" if value is None else value)
                             for key, value in row.items()})
    return {"runs_with_design": len({r["run_id"] for r in rows}),
            "candidates": len(rows),
            "property_columns": len(fieldnames) - len(FIXED_COLUMNS),
            "out": str(out_path)}
