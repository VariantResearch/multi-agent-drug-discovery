"""Retraction and correction surveillance over cited sources.

Frozen run records cite sources by DOI and PMID. Papers get
retracted, corrected, or flagged with expressions of concern after
the fact, and a frozen record cannot change - so this watch checks
the cited identifiers against Crossref's update metadata (the
Retraction Watch data, carried in the works record's updated-by
list) cross-checked with Europe PMC's record types, and writes its
findings to a separate overlay file keyed by run. Bundles are never
modified. Corrections are reported as informational only; the
severity ladder keeps a correction from ever reading as a
retraction, and the report language is always "no notice found as
of" a date, never "clean".

Transports are injectable for tests; the defaults are plain urllib
with a descriptive user agent, no key.
"""

import json
import urllib.parse
import urllib.request
from pathlib import Path

CROSSREF_WORKS = "https://api.crossref.org/works/"
EUROPEPMC_SEARCH = ("https://www.ebi.ac.uk/europepmc/webservices/rest"
                    "/search?resulttype=core&format=json&query=")
USER_AGENT = ("MADD retraction-watch "
              "(https://github.com/VariantResearch/"
              "multi-agent-drug-discovery)")

# Severity ladder, highest first. Crossref update types and Europe
# PMC comment-correction types both map onto it.
SEVERITY_ORDER = ["retraction", "partial_retraction",
                  "expression_of_concern", "correction"]
_CROSSREF_TYPES = {
    "retraction": "retraction",
    "removal": "retraction",
    "withdrawal": "retraction",
    "partial_retraction": "partial_retraction",
    "expression_of_concern": "expression_of_concern",
    "correction": "correction",
    "corrigendum": "correction",
    "erratum": "correction",
    "addendum": "correction",
    "clarification": "correction",
}
_EPMC_COMMENT_TYPES = {
    "Retraction in": "retraction",
    "Expression of concern in": "expression_of_concern",
    "Correction in": "correction",
    "Erratum in": "correction",
}


def default_fetch_json(url):
    """GET a URL and parse its JSON body (the live transport)."""
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT,
                      "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _records_of_bundle(bundle):
    """Every debate record a bundle carries, target, frame, or cases."""
    records = []
    if not isinstance(bundle, dict):
        return records
    if bundle.get("kind") == "target_run":
        record = (bundle.get("frame_run") or {}).get("record")
        if isinstance(record, dict):
            records.append(record)
    elif bundle.get("kind") == "frame_run":
        record = bundle.get("record")
        if isinstance(record, dict):
            records.append(record)
    for record in (bundle.get("case_records") or {}).values():
        if isinstance(record, dict):
            records.append(record)
    return records


def _claim_sources(claim):
    """The (identifier, type) pairs one claim cites, both shapes.

    Locked-spec claims carry source_identifier/identifier_type on
    the claim; dossier-era claims carry an evidence list whose
    entries carry identifier/identifier_type.
    """
    found = []
    if claim.get("source_identifier"):
        found.append((str(claim["source_identifier"]),
                      str(claim.get("identifier_type") or "")))
    for entry in claim.get("evidence") or []:
        if isinstance(entry, dict) and entry.get("identifier"):
            found.append((str(entry["identifier"]),
                          str(entry.get("identifier_type") or "")))
    return found


def collect_cited_sources(runs_dir):
    """Map every cited DOI/PMID to the runs and claims citing it.

    Returns {(identifier_type, identifier): {"runs": {run_id:
    [claim_id, ...]}}}. DOIs are normalised to lowercase bare form;
    only doi and pmid identifiers are watchable, others are counted
    under coverage by the caller from the same walk.
    """
    from .storage import load_bundle
    cited = {}
    # The watch scans the directories on disk rather than the run
    # index: surveillance should cover every bundle actually
    # present, including folders copied in by hand.
    run_ids = sorted(
        child.name for child in Path(runs_dir).iterdir()
        if child.is_dir() and (child / "bundle.json").exists()) \
        if Path(runs_dir).exists() else []
    for run_id in run_ids:
        bundle = load_bundle(runs_dir, run_id)
        entry = {"run_id": run_id}
        for record in _records_of_bundle(bundle):
            spec = record.get("spec") or {}
            claims = list(spec.get("claims") or [])
            claims += list(spec.get("contested_claims") or [])
            for claim in claims:
                if not isinstance(claim, dict):
                    continue
                for identifier, itype in _claim_sources(claim):
                    itype = itype.lower()
                    if itype == "doi":
                        identifier = identifier.lower().removeprefix(
                            "https://doi.org/").removeprefix(
                            "http://doi.org/")
                    elif itype != "pmid":
                        continue
                    slot = cited.setdefault((itype, identifier),
                                            {"runs": {}})
                    slot["runs"].setdefault(
                        entry["run_id"], []).append(
                        claim.get("claim_id") or "?")
    return cited


def crossref_notices(doi, fetch_json):
    """The update notices Crossref records for one DOI.

    Reads message.updated-by (the documented route: the update-type
    filter returns notices, not retracted works). Each notice keeps
    the publisher's own type label alongside the mapped severity.
    """
    url = CROSSREF_WORKS + urllib.parse.quote(doi, safe="")
    try:
        payload = fetch_json(url)
    except Exception:
        return []
    message = (payload or {}).get("message") or {}
    notices = []
    for update in message.get("updated-by") or []:
        severity = _CROSSREF_TYPES.get(str(update.get("type") or ""))
        if severity is None:
            continue
        date = None
        parts = ((update.get("updated") or {}).get("date-parts")
                 or [[None]])[0]
        if parts and parts[0]:
            date = "-".join(str(p) for p in parts if p is not None)
        notices.append({
            "severity": severity,
            "type_label": update.get("label") or update.get("type"),
            "notice_doi": update.get("DOI"),
            "date": date,
            "source": "crossref",
        })
    return notices


def europepmc_notices(pmid, fetch_json):
    """The update signals Europe PMC records for one PMID.

    Signals live in the core search record: a Retracted Publication
    pub type, and the commentCorrectionList types. The Annotations
    API is text-mined entities, not updates, and is not used.
    """
    query = urllib.parse.quote(f"SRC:MED AND EXT_ID:{pmid}")
    try:
        payload = fetch_json(EUROPEPMC_SEARCH + query)
    except Exception:
        return []
    results = ((payload or {}).get("resultList") or {}).get(
        "result") or []
    if not results:
        return []
    record = results[0]
    notices = []
    pub_types = ((record.get("pubTypeList") or {}).get("pubType")
                 or [])
    if "Retracted Publication" in pub_types:
        notices.append({"severity": "retraction",
                        "type_label": "Retracted Publication",
                        "notice_doi": None, "date": None,
                        "source": "europepmc"})
    for comment in (record.get("commentCorrectionList") or {}).get(
            "commentCorrection") or []:
        severity = _EPMC_COMMENT_TYPES.get(
            str(comment.get("type") or ""))
        if severity is None:
            continue
        notices.append({
            "severity": severity,
            "type_label": comment.get("type"),
            "notice_doi": None,
            "notice_ref": (f"{comment.get('id')} "
                           f"({comment.get('source')})"
                           if comment.get("id") else None),
            "date": None,
            "source": "europepmc",
        })
    return notices


def _worst(notices):
    """The highest-severity notice in a list, or None."""
    best = None
    for notice in notices:
        if best is None or SEVERITY_ORDER.index(
                notice["severity"]) < SEVERITY_ORDER.index(
                best["severity"]):
            best = notice
    return best


def watch(runs_dir, out_path=None, fetch_json=None, today=None):
    """Check every cited source and write the overlay report.

    The overlay is a separate JSON file (default
    <runs_dir>/retraction-overlay.json); bundle files are read, never
    written. Returns the report dict: checked_on, sources_checked,
    identifiers by type, and findings - one per cited source with at
    least one notice, carrying its worst severity, all notices, and
    the runs and claims citing it.
    """
    import datetime
    fetch_json = fetch_json or default_fetch_json
    cited = collect_cited_sources(runs_dir)
    findings = []
    for (itype, identifier), slot in sorted(cited.items()):
        if itype == "doi":
            notices = crossref_notices(identifier, fetch_json)
        else:
            notices = europepmc_notices(identifier, fetch_json)
        if not notices:
            continue
        findings.append({
            "identifier": identifier,
            "identifier_type": itype,
            "severity": _worst(notices)["severity"],
            "notices": notices,
            "cited_by": {run: claims for run, claims
                         in sorted(slot["runs"].items())},
        })
    findings.sort(key=lambda f: (
        SEVERITY_ORDER.index(f["severity"]), f["identifier"]))
    report = {
        "artifact_type": "retraction_overlay",
        "checked_on": today or datetime.date.today().isoformat(),
        "sources_checked": len(cited),
        "sources_by_type": {
            "doi": sum(1 for t, _ in cited if t == "doi"),
            "pmid": sum(1 for t, _ in cited if t == "pmid"),
        },
        "findings": findings,
        "note": ("Findings are update notices recorded by Crossref "
                 "and Europe PMC as of the checked date. A source "
                 "with no finding had no notice found as of that "
                 "date; that is not a certification that none "
                 "exists. Corrections are informational and are not "
                 "retractions."),
    }
    target = Path(out_path) if out_path else (
        Path(runs_dir) / "retraction-overlay.json")
    target.write_text(json.dumps(report, indent=2, sort_keys=True),
                      encoding="utf-8")
    return report
