"""Trial landscape: the clinical-trial record for a disease,
from ClinicalTrials.gov.

Novelty and whitespace claims are empty without the trial
record: a target with three Phase 3 programs running is a
different proposition from one nobody has taken into humans.
This module reads the public ClinicalTrials.gov API (v2) and
reports what the registry itself says, point in time:

- how many studies the registry holds for the disease, by
  phase and by recruitment status;
- for each focus term (a drug name or a target), how many of
  those studies name it as an intervention;
- the most recent studies, with their NCT identifiers,
  phases, statuses, and sponsors, so every line can be
  checked at the registry.

Counts are the registry's, fetched live and stamped with the
query date. A failed fetch records the section as
unavailable; it never reports a zero it did not observe.
Nothing here judges a trial's quality or a program's
prospects: the landscape is the map, not the verdict.
"""
import json
import urllib.parse
import urllib.request

BASE = "https://clinicaltrials.gov/api/v2/studies"
TIMEOUT_SECONDS = 60


def default_transport(url: str) -> tuple:
    """GET one API URL, returning (status, parsed_or_None)."""
    req = urllib.request.Request(
        url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            return resp.status, json.loads(
                resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except Exception:
        return 0, None


def _query(params: dict, transport=None):
    """Run one studies query; the parsed body or None."""
    transport = transport or default_transport
    url = BASE + "?" + urllib.parse.urlencode(params)
    try:
        status, payload = transport(url)
    except Exception:
        return None
    if status != 200 or not isinstance(payload, dict):
        return None
    return payload


def _study_summary(study: dict) -> dict:
    """The registry facts of one study worth citing."""
    protocol = (study or {}).get("protocolSection") or {}
    ident = protocol.get("identificationModule") or {}
    status = protocol.get("statusModule") or {}
    design = protocol.get("designModule") or {}
    sponsor = (protocol.get("sponsorCollaboratorsModule") or {}).get(
        "leadSponsor") or {}
    interventions = ((protocol.get("armsInterventionsModule") or {})
                     .get("interventions") or [])
    return {
        "nct_id": ident.get("nctId"),
        "title": ident.get("briefTitle"),
        "status": status.get("overallStatus"),
        "start_date": (status.get("startDateStruct") or {}).get("date"),
        "phases": design.get("phases") or [],
        "sponsor": sponsor.get("name"),
        "interventions": [item.get("name") for item in interventions
                          if item.get("name")],
    }


def _count_by(studies, field):
    """Count studies by a summary field's values."""
    counts = {}
    for study in studies:
        values = study.get(field)
        if isinstance(values, list):
            for value in values:
                counts[value] = counts.get(value, 0) + 1
        elif values:
            counts[values] = counts.get(values, 0) + 1
    return counts


def landscape(disease: str, focus_terms=(), queried_on: str = None,
              transport=None, sample_size: int = 100) -> dict:
    """The trial landscape for one disease.

    The registry is sampled (up to sample_size studies for the
    phase and status breakdowns, which are counts over the
    sample and are labelled as such) while totals come from
    the registry's own count. Each focus term gets its own
    counted query. Failures mark their section unavailable.
    """
    total_payload = _query(
        {"query.cond": disease, "countTotal": "true",
         "pageSize": "0"}, transport=transport)
    total = (total_payload or {}).get("totalCount")
    sample_payload = _query(
        {"query.cond": disease, "pageSize": str(sample_size),
         "sort": "StartDate:desc"}, transport=transport)
    studies = [_study_summary(study) for study in
               (sample_payload or {}).get("studies") or []]
    focus = []
    for term in focus_terms:
        payload = _query(
            {"query.cond": disease, "query.intr": str(term),
             "countTotal": "true", "pageSize": "5",
             "sort": "StartDate:desc"}, transport=transport)
        if payload is None:
            focus.append({"term": term, "status": "unavailable"})
            continue
        focus.append({
            "term": term,
            "trials": payload.get("totalCount"),
            "recent": [_study_summary(study) for study
                       in payload.get("studies") or []],
        })
    return {
        "artifact_type": "trial_landscape",
        "schema_version": "0.1.0",
        "disease": disease,
        "queried_on": queried_on,
        "registry": "ClinicalTrials.gov",
        "total_trials": total,
        "sample": {
            "size": len(studies),
            "by_phase": _count_by(studies, "phases"),
            "by_status": _count_by(studies, "status"),
        } if sample_payload is not None else None,
        "recent": studies[:5],
        "focus": focus,
        "note": ("Registry data as ClinicalTrials.gov reports "
                 "it, fetched live on the query date. Phase and "
                 "status breakdowns count the returned sample "
                 "(up to " + str(sample_size) + " most recent "
                 "studies), not the full registry; totals and "
                 "focus counts are the registry's own. Presence "
                 "in the registry is a fact about a program's "
                 "existence, not about its quality or "
                 "prospects."),
    }
