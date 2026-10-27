"""Candidate comparison workbench: one design run, side by side.

Builds the comparison the console renders for a designed run:
ranked candidates as columns, properties as grouped rows (identity
from the production sheets, RDKit-computed descriptors, ADMET-AI
endpoints, the designer's own predictions), every cell carrying the
basis it was recorded with so a computed value never sits
indistinguishably next to a designer's estimate. A delta-from-rank-1
column serves as the paired-comparison view. Best-value marks apply
only to the small declared direction table below, recorded here as
conventions of this view, not as findings about the candidates; no
composite score is computed, because ranking on point estimates
without uncertainty discards good compounds.

The data audit behind this view (2026-10-27, both designed runs on
record): ranked candidates carry a uniform computed set within a
modality - the two small molecules in each run share the same RDKit
property names from the same RDKit version and the same ADMET-AI
endpoint names from the same ADMET-AI version, while the ASO
candidates carry designer predictions only, so their computed cells
are empty and say why. Docking poses are not stored in bundles
(docking runs on demand in the console), so this view has no pose
overlay; the radar covers the small molecules' RDKit descriptors
only.
"""

import math

# Declared direction conventions for best-value marks: toxicity
# probabilities read lower-is-better; solubility, permeability, and
# bioavailability read higher-is-better. Everything else is shown
# unmarked: a descriptor is not a score.
DIRECTIONS = {
    "admet:AMES": "lower",
    "admet:DILI": "lower",
    "admet:hERG": "lower",
    "admet:Solubility_AqSolDB": "higher",
    "admet:Caco2_Wang": "higher",
    "admet:Bioavailability_Ma": "higher",
}
RADAR_AXES = ["molecular_weight", "logp", "tpsa", "hbd", "hba",
              "rotatable_bonds"]


def _design_of(bundle):
    """The design bundle inside a target bundle, or the bundle."""
    if bundle.get("kind") == "target_run":
        return bundle.get("design")
    if bundle.get("kind") == "design_run":
        return bundle
    return None


def _as_float(value):
    """A float for a recorded value, or None when it is not numeric."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _group_of(name, basis):
    """The comparison group one property belongs to."""
    if name.startswith("admet:"):
        return "ADMET-AI endpoints (predicted)"
    if basis.startswith("computed:RDKit"):
        return "RDKit descriptors (computed)"
    return "Designer predictions (as proposed)"


def _radar_svg(columns):
    """A normalised RDKit-descriptor radar for the small molecules.

    One polygon per candidate carrying every radar axis; axes are
    min-max normalised across those candidates, so the chart shows
    shape, not absolute quality. Returns "" when fewer than two
    candidates carry the axes.
    """
    usable = []
    for column in columns:
        values = {}
        for row in column["cells"].values():
            if row["group"] == "RDKit descriptors (computed)" \
                    and row["name"] in RADAR_AXES:
                number = _as_float(row["value"])
                if number is not None:
                    values[row["name"]] = number
        if len(values) == len(RADAR_AXES):
            usable.append((column["candidate_id"], values))
    if len(usable) < 2:
        return ""
    lows = {a: min(v[a] for _, v in usable) for a in RADAR_AXES}
    highs = {a: max(v[a] for _, v in usable) for a in RADAR_AXES}
    cx, cy, radius = 190, 140, 105
    palette = ["#01cdfe", "#ff71ce", "#3dff8f", "#ffd166"]

    def point(axis_index, fraction):
        """The SVG point for one axis at one normalised fraction."""
        angle = -math.pi / 2 + axis_index * 2 * math.pi / len(RADAR_AXES)
        return (cx + radius * fraction * math.cos(angle),
                cy + radius * fraction * math.sin(angle))

    parts = ["<svg width='380' height='280' viewBox='0 0 380 280' "
             "xmlns='http://www.w3.org/2000/svg' role='img'>"]
    for fraction in (0.5, 1.0):
        ring = " ".join(
            f"{point(i, fraction)[0]:.1f},{point(i, fraction)[1]:.1f}"
            for i in range(len(RADAR_AXES)))
        parts.append(f"<polygon points='{ring}' fill='none' "
                     "stroke='#9a9ab5' stroke-opacity='0.4'/>")
    for i, axis in enumerate(RADAR_AXES):
        x, y = point(i, 1.0)
        parts.append(f"<line x1='{cx}' y1='{cy}' x2='{x:.1f}' "
                     f"y2='{y:.1f}' stroke='#9a9ab5' "
                     "stroke-opacity='0.4'/>")
        lx, ly = point(i, 1.18)
        parts.append(f"<text x='{lx:.1f}' y='{ly:.1f}' font-size='9' "
                     f"fill='#e8e8f0' text-anchor='middle'>{axis}"
                     "</text>")
    for index, (candidate_id, values) in enumerate(usable):
        points = []
        for i, axis in enumerate(RADAR_AXES):
            span = highs[axis] - lows[axis]
            fraction = (0.5 if span == 0 else
                        (values[axis] - lows[axis]) / span)
            x, y = point(i, fraction)
            points.append(f"{x:.1f},{y:.1f}")
        color = palette[index % len(palette)]
        parts.append(f"<polygon points='{' '.join(points)}' "
                     f"fill='{color}' fill-opacity='0.18' "
                     f"stroke='{color}'/>")
        parts.append(f"<text x='{12 + index * 118}' y='272' "
                     f"font-size='9' fill='{color}'>"
                     f"{candidate_id}</text>")
    parts.append("</svg>")
    return "".join(parts)


def build_workbench(bundle):
    """The comparison structure for one designed run, or None.

    Columns follow the recorded ranking. Each cell carries its
    recorded value and basis; computed groups a candidate does not
    carry (the ASOs carry no RDKit or ADMET-AI values) render as
    absent cells with the reason in the column note, never as
    zeroes.
    """
    design = _design_of(bundle)
    if not design:
        return None
    from .production import build_production_sheets
    sheets = {s["candidate_id"]: s
              for s in build_production_sheets(design)}
    candidates = {c.get("candidate_id"): c
                  for c in design.get("candidates") or []}
    ranked = (design.get("ranking") or {}).get("ranked") or []
    columns = []
    for candidate_id in ranked:
        candidate = candidates.get(candidate_id) or {}
        sheet = sheets.get(candidate_id) or {}
        identity = sheet.get("identity") or {}
        cells = {}
        if identity.get("molecular_formula"):
            cells["formula"] = {
                "name": "formula",
                "group": "Identity (from the structure)",
                "value": identity["molecular_formula"],
                "basis": "computed:RDKit (production sheet)"}
        if identity.get("computed_molecular_weight") is not None:
            cells["sheet_mw"] = {
                "name": "molecular weight (sheet)",
                "group": "Identity (from the structure)",
                "value": identity["computed_molecular_weight"],
                "basis": "computed:RDKit (production sheet)"}
        for prop in candidate.get("predicted_properties") or []:
            name = str(prop.get("name") or "")
            if not name:
                continue
            cells[name] = {"name": name,
                           "group": _group_of(
                               name, str(prop.get("basis") or "")),
                           "value": prop.get("value"),
                           "basis": prop.get("basis")}
        columns.append({
            "candidate_id": candidate_id,
            "modality": candidate.get("modality"),
            "production_ready": sheet.get("production_ready"),
            "cells": cells,
            "note": ("No computed properties are recorded for this "
                     "candidate (modality "
                     + str(candidate.get("modality")) + "); its "
                     "designer predictions are shown."
                     if not any(c["group"] != "Designer predictions "
                                "(as proposed)"
                                for c in cells.values())
                     else None),
        })
    if not columns:
        return None
    groups = []
    for column in columns:
        for cell in column["cells"].values():
            if cell["group"] not in groups:
                groups.append(cell["group"])
    order = ["Identity (from the structure)",
             "RDKit descriptors (computed)",
             "ADMET-AI endpoints (predicted)",
             "Designer predictions (as proposed)"]
    groups.sort(key=lambda g: order.index(g) if g in order else 99)
    rows = []
    seen = []
    for group in groups:
        names = []
        for column in columns:
            for name, cell in column["cells"].items():
                if cell["group"] == group and name not in names:
                    names.append(name)
        for name in names:
            if name in seen:
                continue
            seen.append(name)
            values = []
            for column in columns:
                cell = column["cells"].get(name)
                values.append(cell["value"] if cell else None)
            best_index = None
            direction = DIRECTIONS.get(name)
            numeric = [(i, _as_float(v)) for i, v in enumerate(values)
                       if _as_float(v) is not None]
            if direction and len(numeric) >= 2:
                pick = (min if direction == "lower" else max)(
                    numeric, key=lambda pair: pair[1])
                best_index = pick[0]
            reference = _as_float(values[0]) if values else None
            deltas = []
            for value in values:
                number = _as_float(value)
                deltas.append(
                    round(number - reference, 4)
                    if number is not None and reference is not None
                    else None)
            rows.append({"group": group, "name": name,
                         "values": values, "best_index": best_index,
                         "deltas": deltas})
    return {
        "columns": [{"candidate_id": c["candidate_id"],
                     "modality": c["modality"],
                     "production_ready": c["production_ready"],
                     "note": c["note"]} for c in columns],
        "rows": rows,
        "radar_svg": _radar_svg(columns),
        "directions": DIRECTIONS,
        "note": ("Values are shown with the basis they were "
                 "recorded with. Best-value marks follow the "
                 "declared direction conventions in "
                 "madd/workbench.py (toxicity probabilities lower, "
                 "solubility, permeability and bioavailability "
                 "higher) and are conventions of this view, not "
                 "findings. No composite score is computed. Docking "
                 "poses are not stored in bundles, so no pose "
                 "overlay is shown."),
    }


def workbench_of_bundle(bundle):
    """The workbench for a served bundle (target or design), or None."""
    if not isinstance(bundle, dict):
        return None
    return build_workbench(bundle)
