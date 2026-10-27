"""Audit flow: the evidence funnel of one debate, as recorded.

Computes the staged counts a run detail shows as a waterfall:
dossiers contributed, claims struck in the evidence call (grouped by
the recorded strike reasons), claims contested where the record
carries them, claims in the final specification, and the debate
outcome with its consensus tally. Every number comes from the frozen
record itself; the record does not carry the dossiers' full claim
lists, so claims that survived the audit without entering the
specification are not a recorded number, and the flow says so rather
than estimating them.
"""

from collections import Counter


def record_of_bundle(bundle):
    """The debate record inside a served bundle, or None.

    Target runs carry it at frame_run.record, frame runs at record;
    design and Gate 0 bundles have no single debate record to flow.
    """
    if not isinstance(bundle, dict):
        return None
    if bundle.get("kind") == "target_run":
        frame = bundle.get("frame_run") or {}
        record = frame.get("record")
        return record if isinstance(record, dict) else None
    if bundle.get("kind") == "frame_run":
        record = bundle.get("record")
        return record if isinstance(record, dict) else None
    return None


def audit_flow(record):
    """The audit flow stages of one debate record.

    Returns a dict with an ordered stage list; each stage carries its
    key, label and count (the outcome stage carries the outcome text
    and the consensus tally instead). by_reason on the struck stage
    counts every recorded reason, so a claim struck for two reasons
    appears under both.
    """
    strikes = record.get("strike_list") or []
    by_reason = Counter()
    for entry in strikes:
        if isinstance(entry, dict):
            by_reason.update(entry.get("reasons") or [])
    spec = record.get("spec") or {}
    evolution = record.get("evolution") or {}
    consensus = record.get("consensus") or {}
    results = consensus.get("results") or []
    stages = [
        {"key": "dossiers", "label": "Dossiers contributed",
         "count": len(evolution.get("contributing_dossiers") or [])},
        {"key": "struck", "label": "Claims struck in the evidence call",
         "count": len(strikes), "by_reason": dict(by_reason)},
    ]
    contested = spec.get("contested_claims") or []
    if contested:
        stages.append({
            "key": "contested",
            "label": "Claims contested (unresolved disputes)",
            "count": len(contested)})
    stages.append({
        "key": "spec", "label": "Claims in the final specification",
        "count": len(spec.get("claims") or [])})
    stages.append({
        "key": "outcome", "label": "Debate outcome",
        "value": record.get("outcome") or "unknown",
        "consensus_passed": sum(
            1 for r in results if isinstance(r, dict) and r.get("passed")),
        "consensus_total": len(results)})
    skipped = evolution.get("duplicate_claim_ids_skipped") or 0
    return {
        "stages": stages,
        "claims_merged": evolution.get("claims_merged"),
        "duplicate_claims_skipped": (skipped if isinstance(skipped, int)
                                     else len(skipped)),
        "note": ("Counts are the record's own. The frozen record does "
                 "not carry the dossiers' full claim lists, so claims "
                 "that survived the audit without entering the "
                 "specification are not a recorded number and are not "
                 "estimated here."),
    }


def audit_flow_of_bundle(bundle):
    """The audit flow of a bundle's debate record, or None."""
    record = record_of_bundle(bundle)
    if record is None:
        return None
    return audit_flow(record)
