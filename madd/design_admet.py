"""ADMET-AI enrichment for designed candidates.

ADMET-AI (MIT, registry-cleared) predicts absorption, distribution,
metabolism, excretion, and toxicity endpoints from a SMILES string
with trained Chemprop models - the TDC endpoint set, 41 endpoints in
the published model. It runs on CPU. This module is the bridge, in
the same shape as the RDKit bridge: candidates with SMILES structures
gain predicted properties recorded with the basis
"computed:ADMET-AI <version>".

The basis says computed because a named tool produced the numbers,
not the designing model - but they are model predictions, not
measurements and not deterministic calculations like RDKit's
descriptors, so every entry carries verified: False and the candidate
audit counts them as unverified predictions. That is the honest
grade for a predicted hERG probability, and it is still far more
information than a designer's own guess at the same number.

ADMET-AI is an optional dependency with heavy transitive deps
(torch). When it is not installed, enrichment reports not_installed
and fabricates nothing. Endpoint selection: a curated subset of
decision-relevant endpoints when the installed model offers them,
otherwise whatever numeric endpoints it returns.
"""
from __future__ import annotations

import importlib.util

# Endpoints worth surfacing on every candidate when the model has
# them: cardiotoxicity, mutagenicity, liver injury, solubility,
# permeability, blood-brain barrier, and two clearance/metabolism
# staples. Matched case-insensitively against the model's columns.
_PREFERRED = ("herg", "ames", "dili", "solubility", "caco2", "bbb",
              "clearance", "cyp2c9", "cyp3a4", "ld50", "half_life",
              "ppbr", "bioavailability")


def available() -> bool:
    """True when the admet_ai package can be imported here."""
    try:
        return importlib.util.find_spec("admet_ai") is not None
    except Exception:
        return False


def _version() -> str:
    """The installed admet-ai version string, or 'unknown'."""
    try:
        import importlib.metadata
        return importlib.metadata.version("admet-ai")
    except Exception:
        return "unknown"


def _select_columns(columns) -> list:
    """Choose the endpoint columns to record: preferred endpoints
    first (in model order), capped so a candidate is not buried."""
    preferred = [c for c in columns
                 if any(key in str(c).lower() for key in _PREFERRED)]
    chosen = preferred if preferred else list(columns)
    return chosen[:16]


def predict_smiles(smiles_list: list) -> list:
    """Run ADMET-AI over a list of SMILES strings.

    Returns one dict of {endpoint: float} per input, aligned by index.
    Raises whatever the library raises; callers record failures rather
    than hiding them. Calls are chunked at 100 molecules: ADMET-AI's
    own documentation warns that a single call assumes fewer than
    about 100 SMILES on a personal machine.
    """
    from admet_ai import ADMETModel
    model = ADMETModel()
    out = []
    smiles_list = list(smiles_list)
    for start in range(0, len(smiles_list), 100):
        frame = model.predict(smiles=smiles_list[start:start + 100])
        columns = _select_columns(list(frame.columns))
        for _, row in frame.iterrows():
            values = {}
            for col in columns:
                try:
                    values[str(col)] = round(float(row[col]), 4)
                except Exception:
                    continue
            out.append(values)
    return out


def enrich_candidates(candidates: list, use: str = "research") -> dict:
    """Attach ADMET-AI predictions to every SMILES candidate.

    Mutates candidates in place (appends to predicted_properties) and
    returns the tool-run record for the design bundle. Statuses:
    completed, not_installed, blocked_license, failed (the library
    ran and errored; the error is named, nothing is fabricated).
    """
    from .license_registry import check_tool
    record = {"tool": "ADMET-AI", "kind": "predicted_properties",
              "requested": False, "status": "completed",
              "checked": 0, "predicted": 0}
    verdict = check_tool("ADMET-AI", use)
    if not verdict.get("allowed"):
        record["status"] = "blocked_license"
        record["detail"] = verdict.get("reason") or "registry refusal"
        return record
    if not available():
        record["status"] = "not_installed"
        record["detail"] = ("admet-ai is not installed in this environment; "
                            "no ADMET predictions were made")
        return record
    smiles = []
    owners = []
    for cand in candidates:
        structure = cand.get("structure") or {}
        if structure.get("format") == "smiles" and structure.get("value"):
            smiles.append(structure["value"])
            owners.append(cand)
    record["checked"] = len(owners)
    if not owners:
        return record
    try:
        predictions = predict_smiles(smiles)
    except Exception as exc:
        record["status"] = "failed"
        record["detail"] = ("ADMET-AI run failed: " + type(exc).__name__
                            + ": " + str(exc))
        return record
    basis = "computed:ADMET-AI " + _version()
    for cand, values in zip(owners, predictions):
        props = cand.setdefault("predicted_properties", [])
        for name, value in values.items():
            props.append({"name": "admet:" + name, "value": value,
                          "basis": basis, "verified": False})
            record["predicted"] += 1
    return record
