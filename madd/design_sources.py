"""Known-compound checks for designed candidates, against ChEMBL and
PubChem.

A designed candidate with a SMILES structure gets an InChIKey (via
madd/design_rdkit.py), and the two public chemistry registries are
asked whether that exact compound is already known: PubChem by
InChIKey (CID list) and ChEMBL by standard InChIKey (molecule ids).
The outcome is recorded on the candidate as source_check: known to a
registry, or no record found. "Known" is information, not a verdict:
a known compound may still be the right candidate, and a compound no
registry holds is not thereby novel in the patent sense. The check
never excludes a candidate and never invents a result: a registry
that cannot be reached leaves the candidate unchecked with the
failure counted in the run record, and without RDKit there is no
InChIKey and the check is reported as unavailable.

Network access is explicit: run_design only calls this when the
operator asks (design-run --source-check). The transport is
injectable for tests, like madd/resolve.py.
"""
from __future__ import annotations

import json
import urllib.parse

from . import design_rdkit
from .resolve import CHEMBL_BASE, PUBCHEM_BASE, default_fetcher


def _get_json(fetch, url):
    """GET JSON via the fetcher; return (payload, error_status)."""
    try:
        status_code, body = fetch(url)
    except Exception:
        return None, "lookup_error"
    if status_code == 404:
        return None, "not_found"
    if status_code != 200:
        return None, "lookup_error"
    try:
        return json.loads(body), None
    except Exception:
        return None, "lookup_error"


def pubchem_cids_by_inchikey(inchikey: str, fetcher=None):
    """Return the PubChem CID list for an InChIKey, [] when PubChem
    holds no such compound, or None when the lookup could not run."""
    fetch = fetcher if fetcher is not None else default_fetcher
    url = (PUBCHEM_BASE + "/compound/inchikey/"
           + urllib.parse.quote(inchikey, safe="") + "/cids/JSON")
    payload, error = _get_json(fetch, url)
    if error == "not_found":
        return []
    if payload is None:
        return None
    return [int(c) for c in payload.get("IdentifierList", {}).get("CID", [])]


def chembl_ids_by_inchikey(inchikey: str, fetcher=None):
    """Return the ChEMBL molecule ids for a standard InChIKey, [] when
    ChEMBL holds no such molecule, or None when the lookup failed."""
    fetch = fetcher if fetcher is not None else default_fetcher
    url = (CHEMBL_BASE + "/molecule.json?molecule_structures__standard_inchi_key="
           + urllib.parse.quote(inchikey, safe="") + "&limit=20")
    payload, error = _get_json(fetch, url)
    if payload is None:
        return None
    return [m.get("molecule_chembl_id") for m in payload.get("molecules", [])
            if m.get("molecule_chembl_id")]


def check_candidates(candidates: list, fetcher=None) -> dict:
    """Check every SMILES candidate against PubChem and ChEMBL.

    Mutates candidates in place, adding a source_check entry, and
    returns the tool-run record for the design bundle.
    """
    record = {"tool": "ChEMBL+PubChem", "kind": "source_lookup",
              "requested": False, "status": "completed",
              "checked": 0, "known": 0, "no_record": 0, "skipped": 0,
              "failures": 0}
    if not design_rdkit.available():
        record["status"] = "not_available"
        record["detail"] = ("RDKit is not installed, so no InChIKey can be "
                            "computed and no registry can be keyed")
        return record
    for cand in candidates:
        structure = cand.get("structure") or {}
        if structure.get("format") != "smiles" or not structure.get("value"):
            record["skipped"] += 1
            continue
        key = design_rdkit.inchikey(structure["value"])
        if key is None:
            record["skipped"] += 1
            cand["source_check"] = {"status": "skipped_invalid_structure"}
            continue
        cids = pubchem_cids_by_inchikey(key, fetcher=fetcher)
        chembl_ids = chembl_ids_by_inchikey(key, fetcher=fetcher)
        record["checked"] += 1
        if cids is None or chembl_ids is None:
            record["failures"] += 1
            cand["source_check"] = {"status": "lookup_failed",
                                    "inchikey": key,
                                    "pubchem_cids": cids,
                                    "chembl_ids": chembl_ids}
            continue
        known = bool(cids or chembl_ids)
        cand["source_check"] = {"status": "known" if known else "no_record",
                                "inchikey": key,
                                "pubchem_cids": cids,
                                "chembl_ids": chembl_ids,
                                "known_compound": known}
        if known:
            record["known"] += 1
        else:
            record["no_record"] += 1
    if record["checked"] and record["failures"] == record["checked"]:
        record["status"] = "lookup_error"
    return record
