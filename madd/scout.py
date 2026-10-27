"""Target scout: rank candidate targets for a disease before
any debate is staffed.

MADD is target-first, and choosing the target is the highest-
leverage decision in the pipeline. Target nomination tools
rank candidates on integrated evidence; this scout does the
same job from the two public sources MADD already trusts, and
shows its work:

- Open Targets resolves each named target and the disease,
  and reports the pair's association score with its datatype
  breakdown (the literature component is shown separately).
- ChEMBL reports whether any drug mechanism is recorded
  against the target and how many bioactivity records exist.

The whitespace read is mechanical and labelled as such: an
associated target with no recorded drug mechanism is
"comparatively open"; one with mechanisms is "validated but
occupied"; a pair with no association at all is
"unestablished". These are descriptions of the fetched
records, not predictions of success, and the ranking is the
association score's order and nothing else - the scout
proposes which targets deserve a debate; the debate, with
its evidence call and audit, remains where targets are
actually judged. A target that fails to resolve is recorded
as unresolved with the reason, never dropped.
"""
from . import chembl as chembl_api
from . import opentargets


def whitespace_read(association_score, known_mechanisms) -> str:
    """The mechanical whitespace label for one pair, from the
    fetched records only."""
    if association_score is None:
        return ("unestablished: no Open Targets association "
                "recorded for this target-disease pair")
    if known_mechanisms is None:
        return ("association recorded; ChEMBL mechanism count "
                "unavailable, so the whitespace read is partial")
    if known_mechanisms == 0:
        return ("comparatively open: association recorded and "
                "no drug mechanism recorded in ChEMBL")
    return ("validated but occupied: " + str(known_mechanisms)
            + " drug mechanism(s) recorded in ChEMBL")


def scout_targets(disease: str, target_names,
                  ot_transport=None, chembl_transport=None) -> dict:
    """Scout the named targets against one disease.

    Returns the scout report: the resolved disease, one entry
    per input target (in ranked order), and the method note.
    Live lookups throughout; every failure is recorded on the
    entry it belongs to.
    """
    disease_hit = opentargets.search_entity(disease, "disease",
                                            transport=ot_transport)
    entries = []
    for name in target_names:
        entry = {"target_input": name, "resolved": None,
                 "association": None, "signals": {},
                 "whitespace": None, "problems": []}
        target_hit = opentargets.search_entity(
            name, "target", transport=ot_transport)
        signals = chembl_api.target_signals(
            name, transport=chembl_transport)
        entry["chembl"] = signals
        if target_hit is None:
            entry["problems"].append(
                "target did not resolve in Open Targets search")
        if disease_hit is None:
            entry["problems"].append(
                "disease did not resolve in Open Targets search")
        if target_hit is not None:
            entry["resolved"] = {"ensembl_id": target_hit["id"],
                                 "name": target_hit["name"],
                                 "chembl_id": signals.get("chembl_id")}
        association = None
        if target_hit is not None and disease_hit is not None:
            association = opentargets.association(
                target_hit["id"], disease_hit["id"],
                transport=ot_transport)
            if association is None:
                entry["problems"].append(
                    "no Open Targets association for this pair")
        entry["association"] = association
        datatype = (association or {}).get("datatype_scores") or {}
        entry["signals"] = {
            "association_score": (association or {}).get("score"),
            "literature_score": datatype.get("literature"),
            "genetic_association_score": datatype.get(
                "genetic_association"),
            "known_mechanisms": signals.get("known_mechanisms"),
            "bioactivity_records": signals.get("bioactivity_records"),
        }
        entry["whitespace"] = whitespace_read(
            entry["signals"]["association_score"],
            signals.get("known_mechanisms"))
        entries.append(entry)

    def rank_key(entry):
        """Rank by association score, unresolved and
        unassociated last, input order breaking ties."""
        score = entry["signals"].get("association_score")
        return (0, -score) if isinstance(score, (int, float)) \
            else (1, 0.0)

    ranked = sorted(entries, key=rank_key)
    for i, entry in enumerate(ranked):
        entry["rank"] = i + 1
    return {
        "artifact_type": "target_scout_report",
        "schema_version": "0.1.0",
        "disease_input": disease,
        "disease_resolved": ({"id": disease_hit["id"],
                              "name": disease_hit["name"]}
                             if disease_hit else None),
        "candidates": ranked,
        "candidates_total": len(ranked),
        "note": ("Ranked by the Open Targets association score "
                 "for the named pair; signals from Open Targets "
                 "and ChEMBL as those sources report them. The "
                 "whitespace labels are mechanical descriptions "
                 "of the fetched records, not predictions. The "
                 "scout nominates targets for a debate; it "
                 "locks nothing in, and every nominated target "
                 "still faces the full evidence call and audit."),
    }
