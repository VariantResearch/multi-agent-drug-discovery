"""ChEMBL lookups for the target scout: target resolution and
two factual druggability-adjacent signals.

ChEMBL (CC BY-SA 4.0, EMBL-EBI) is the standard public record
of bioactive molecules and their targets. The scout uses
exactly three of its facts per target, each a count or an
identifier the API itself reports:

- the target's ChEMBL identifier, resolved by name search
  (an exact preferred-name match wins, else the first hit);
- the number of drug mechanisms recorded against the target
  (targets with approved-drug mechanisms are validated, and
  occupied);
- the number of bioactivity records against the target (a
  measure of how much screening attention it has had).

No score is computed here and nothing is inferred: counts are
reported as the API reports them, and a failed lookup returns
None rather than a zero, because "not found" and "zero" are
different facts.
"""
import json
import urllib.parse
import urllib.request

BASE = "https://www.ebi.ac.uk/chembl/api/data"
TIMEOUT_SECONDS = 60


def default_transport(url: str) -> tuple:
    """GET one ChEMBL API URL, returning (status, parsed)."""
    req = urllib.request.Request(
        url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            return resp.status, json.loads(
                resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        return exc.code, None


def _get(path: str, transport=None):
    """GET one API path through the transport; parsed body or
    None on any failure."""
    transport = transport or default_transport
    try:
        status, payload = transport(BASE + path)
    except Exception:
        return None
    if status != 200 or not isinstance(payload, dict):
        return None
    return payload


def search_target(name: str, transport=None):
    """Resolve a target name to {chembl_id, pref_name,
    target_type}, or None when ChEMBL has no hit."""
    payload = _get("/target/search.json?q="
                   + urllib.parse.quote(str(name))
                   + "&limit=10", transport=transport)
    if not payload:
        return None
    targets = payload.get("targets") or []
    if not targets:
        return None
    wanted = str(name).strip().lower()

    def rank_key(item):
        """Resolution preference: a component synonym exactly
        matching the query (gene symbols live there, not in
        pref_name), then an exact pref_name, then a single-
        protein target, then the API's own order."""
        index, target = item
        synonyms = set()
        for component in target.get("target_components") or []:
            for synonym in component.get(
                    "target_component_synonyms") or []:
                value = str(synonym.get("component_synonym")
                            or "").strip().lower()
                if value:
                    synonyms.add(value)
        return (wanted not in synonyms,
                str(target.get("pref_name") or "").strip().lower()
                != wanted,
                target.get("target_type") != "SINGLE PROTEIN",
                index)

    chosen = sorted(enumerate(targets), key=rank_key)[0][1]
    return {"chembl_id": chosen.get("target_chembl_id"),
            "pref_name": chosen.get("pref_name"),
            "target_type": chosen.get("target_type")}


def _total_count(path: str, transport=None):
    """The page_meta total_count of a filtered list endpoint,
    or None when the lookup fails."""
    payload = _get(path, transport=transport)
    if not payload:
        return None
    meta = payload.get("page_meta") or {}
    total = meta.get("total_count")
    return total if isinstance(total, int) else None


def mechanism_count(chembl_id: str, transport=None):
    """Drug mechanisms recorded against one target, or None."""
    return _total_count("/mechanism.json?target_chembl_id="
                        + urllib.parse.quote(str(chembl_id))
                        + "&limit=1", transport=transport)


def bioactivity_count(chembl_id: str, transport=None):
    """Bioactivity records against one target, or None."""
    return _total_count("/activity.json?target_chembl_id="
                        + urllib.parse.quote(str(chembl_id))
                        + "&limit=1", transport=transport)


def target_signals(name: str, transport=None) -> dict:
    """All three ChEMBL facts for one target name. Resolution
    failure leaves every field None, distinctly from a real
    zero count."""
    found = search_target(name, transport=transport)
    if not found or not found.get("chembl_id"):
        return {"chembl_id": None, "pref_name": None,
                "target_type": None, "known_mechanisms": None,
                "bioactivity_records": None}
    chembl_id = found["chembl_id"]
    return {"chembl_id": chembl_id,
            "pref_name": found.get("pref_name"),
            "target_type": found.get("target_type"),
            "known_mechanisms": mechanism_count(chembl_id,
                                                transport=transport),
            "bioactivity_records": bioactivity_count(
                chembl_id, transport=transport)}
