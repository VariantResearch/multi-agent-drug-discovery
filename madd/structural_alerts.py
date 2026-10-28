"""Structural alerts: curated liability patterns, computed by RDKit.

Runs RDKit's FilterCatalog sets (PAINS, Brenk, NIH) over a
candidate's recorded structure and reports the patterns it matches.
These are the curated community catalogs medicinal chemists screen
against - PAINS patterns that interfere with assays, Brenk's
unwanted-substructure list, the NIH MLSMR set - computed from the
structure itself, never substring guesses.

Alerts are advisory flags. A match says "this pattern is present and
deserves a chemist's eye"; it is not a finding that the candidate is
bad, and nothing in this project excludes or down-ranks a candidate
over an alert. Candidates whose structures are not SMILES (the ASO
sequences) are not applicable and say so. When RDKit is not
installed the check reports itself unavailable rather than guessing.
"""

from functools import lru_cache

CATALOG_SETS = ("PAINS", "BRENK", "NIH")


@lru_cache(maxsize=None)
def _catalog(set_name):
    """One built FilterCatalog for a set name, or None without RDKit."""
    try:
        from rdkit.Chem import FilterCatalog
    except Exception:
        return None
    params = FilterCatalog.FilterCatalogParams()
    params.AddCatalog(getattr(
        FilterCatalog.FilterCatalogParams.FilterCatalogs, set_name))
    return FilterCatalog.FilterCatalog(params)


def alerts_for_smiles(smiles):
    """The structural alerts of one SMILES structure.

    Returns {"status": "ok" | "invalid" | "unavailable", "alerts":
    [{"set": ..., "pattern": ...}, ...]} with alerts sorted by set
    then pattern, duplicates across a set's sub-catalogs collapsed.
    """
    try:
        from rdkit import Chem
    except Exception:
        return {"status": "unavailable", "alerts": []}
    mol = Chem.MolFromSmiles(smiles or "")
    if mol is None:
        return {"status": "invalid", "alerts": []}
    found = set()
    for set_name in CATALOG_SETS:
        catalog = _catalog(set_name)
        if catalog is None:
            return {"status": "unavailable", "alerts": []}
        for entry in catalog.GetMatches(mol):
            found.add((set_name, entry.GetDescription()))
    return {"status": "ok",
            "alerts": [{"set": name, "pattern": pattern}
                       for name, pattern in sorted(found)]}


def alerts_for_bundle(bundle):
    """Per-candidate alert results for a designed run, or None.

    Follows the recorded order (ranked, then excluded) and reads
    each candidate's structure from its production sheet, so the
    checked structure is the sheet's canonical form.
    """
    design = None
    if bundle.get("kind") == "target_run":
        design = bundle.get("design")
    elif bundle.get("kind") == "design_run":
        design = bundle
    if not design:
        return None
    from .production import build_production_sheets
    sheets = {s["candidate_id"]: s
              for s in build_production_sheets(design)}
    ranking = design.get("ranking") or {}
    ordered = list(ranking.get("ranked") or [])
    ordered += [e.get("candidate_id")
                for e in ranking.get("excluded") or []]
    results = []
    for candidate_id in ordered:
        identity = (sheets.get(candidate_id) or {}).get("identity") or {}
        if identity.get("format") != "smiles":
            results.append({"candidate_id": candidate_id,
                            "status": "not_applicable", "alerts": []})
            continue
        result = alerts_for_smiles(
            identity.get("canonical_smiles")
            or identity.get("value_as_proposed"))
        results.append({"candidate_id": candidate_id, **result})
    return results


def format_alerts(alerts):
    """One line's worth of alerts: "PAINS: catechol_A(92); ..." """
    if not alerts:
        return "none"
    return "; ".join(f"{a['set']}: {a['pattern']}" for a in alerts)
