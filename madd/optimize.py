"""Lead optimization loop: bounded in-silico analog rounds
around one designed lead.

A design run ranks candidates and stops. Real discovery work
then iterates: propose analogs of the lead, compute on them,
keep the ones that improve it. This module runs that loop
under the same discipline as the rest of the pipeline:

- The proposer is a designer (the config's model panel through
  ModelDesigner, or a stub in tests). It receives an
  optimization brief naming the current parent, its computed
  objective values, and the objectives, and returns candidate
  analogs through the normal design contract.
- Every analog is computed on with RDKit (madd/design_rdkit):
  structure validity, descriptors, structural alerts. An
  invalid structure is dropped with the reason recorded.
  Nothing about an analog is taken from the proposer's word.
- Improvement is mechanical, on computed objectives only:
  QED (higher wins), SA score (lower wins), structural alert
  count (lower wins). An analog is kept when it is no worse
  than its parent on every shared objective and strictly
  better on at least one (Pareto improvement). Analogs whose
  logP drifts more than 1.0 from the ORIGINAL lead are dropped
  as leaving the lead's chemical neighborhood, and duplicates
  of anything already seen are dropped, both with reasons.
- Kept analogs chain: the round's best kept analog becomes the
  next round's parent. The full lineage is the record: every
  proposed analog, kept or dropped, with its computed values,
  its deltas against its parent, and its verdict.

Standing, stated plainly: this is in-silico iteration only.
Kept means better on computed objectives, not more potent,
not binding, not a drug. The loop applies to SMILES leads;
sequence candidates return not_applicable rather than being
forced through a small-molecule loop. When RDKit is not
installed the loop reports not_available instead of guessing.
"""
from . import design_rdkit

OBJECTIVES = (("qed", "max"), ("sa_score", "min"),
              ("structural_alert_count", "min"))
LOGP_DRIFT_LIMIT = 1.0
_EPSILON = 1e-9


def objective_vector(described: dict) -> dict:
    """The tracked objective values from one describe_smiles
    result. An objective whose value RDKit did not produce
    (SA score on some builds) is absent, and comparisons use
    only the objectives both sides carry."""
    descriptors = described.get("descriptors") or {}
    vector = {}
    if descriptors.get("qed") is not None:
        vector["qed"] = descriptors["qed"]
    if descriptors.get("sa_score") is not None:
        vector["sa_score"] = descriptors["sa_score"]
    vector["structural_alert_count"] = len(
        described.get("structural_alerts") or [])
    return vector


def improves(new: dict, parent: dict) -> tuple:
    """Pareto test of one objective vector against its parent's.
    Returns (kept, deltas): kept when no shared objective is
    worse and at least one is strictly better. Objectives only
    one side carries are ignored and absent from deltas."""
    deltas = {}
    better = False
    for name, direction in OBJECTIVES:
        if name not in new or name not in parent:
            continue
        delta = round(new[name] - parent[name], 4)
        deltas[name] = delta
        signed = delta if direction == "max" else -delta
        if signed < -_EPSILON:
            return False, deltas
        if signed > _EPSILON:
            better = True
    return better, deltas


def _snapshot(candidate_id, described, vector):
    """A recorded candidate snapshot: ids and computed values."""
    return {"candidate_id": candidate_id,
            "canonical_smiles": described.get("canonical_smiles"),
            "objectives": vector,
            "descriptors": described.get("descriptors"),
            "structural_alerts": described.get("structural_alerts")}


def run_optimization(lead: dict, designer, rounds: int = 2,
                     use: str = "research", source_check: bool = False,
                     budget_tracker=None) -> dict:
    """Run the bounded optimization loop around one lead.

    lead is a design candidate dict carrying a SMILES structure.
    designer is any object with design(brief) returning candidate
    dicts in the design contract's normalized shape (ModelDesigner
    in production). Returns the optimization record; its status
    is completed, not_applicable (non-SMILES lead), or
    not_available (RDKit missing, or the designer produced no
    usable analogs in any round: no_improvement is reported
    separately when analogs were judged and none kept)."""
    base = {"artifact_type": "optimization_record",
            "objectives": [{"name": name, "direction": direction}
                           for name, direction in OBJECTIVES],
            "logp_drift_limit": LOGP_DRIFT_LIMIT,
            "rounds_requested": rounds,
            "note": ("in-silico iteration on computed objectives "
                     "only: kept means Pareto-better than its parent "
                     "on QED, SA score, and structural alerts as "
                     "computed by RDKit; it is not a potency, "
                     "binding, or efficacy claim")}
    structure = lead.get("structure") or {}
    if str(structure.get("format") or "").lower() != "smiles" \
            or not structure.get("value"):
        return {**base, "status": "not_applicable",
                "reason": "the lead carries no SMILES structure; the "
                          "optimization loop covers small-molecule "
                          "leads only",
                "lead": {"candidate_id": lead.get("candidate_id")}}
    if not design_rdkit.available():
        return {**base, "status": "not_available",
                "reason": "RDKit is not installed, so no analog can "
                          "be computed on; the loop reports instead "
                          "of guessing",
                "lead": {"candidate_id": lead.get("candidate_id")}}
    described = design_rdkit.describe_smiles(structure["value"])
    if not described.get("valid"):
        return {**base, "status": "not_applicable",
                "reason": "the lead's SMILES does not parse: "
                          + str(described.get("error")),
                "lead": {"candidate_id": lead.get("candidate_id")}}
    parent = _snapshot(lead.get("candidate_id"), described,
                       objective_vector(described))
    parent_smiles = described["canonical_smiles"]
    lead_logp = (described.get("descriptors") or {}).get("logp")
    seen = set()
    lead_key = design_rdkit.inchikey(structure["value"])
    if lead_key:
        seen.add(lead_key)
    record_rounds = []
    best = parent
    total_proposed = 0
    total_kept = 0
    for round_no in range(1, rounds + 1):
        brief = {
            "artifact_type": "optimization_brief",
            "brief_id": "OPT-" + str(lead.get("candidate_id"))
                        + "-R" + str(round_no),
            "parent": {"candidate_id": parent["candidate_id"],
                       "smiles": parent_smiles,
                       "computed_objectives": parent["objectives"]},
            "objectives": base["objectives"],
            "constraints": [
                "propose analogs of the parent compound only",
                "each candidate must carry a SMILES structure",
                "improvement is judged on computed QED, SA score, "
                "and structural alerts; do not claim potency",
                "logP must stay within " + str(LOGP_DRIFT_LIMIT)
                + " of the original lead"],
        }
        try:
            proposed = designer.design(brief) or []
        except Exception as exc:
            record_rounds.append({
                "round": round_no, "parent_candidate_id":
                parent["candidate_id"], "proposed": [],
                "error": "designer failed: " + type(exc).__name__
                         + ": " + str(exc)})
            break
        entries = []
        kept = []
        for analog in proposed:
            total_proposed += 1
            entry = {"candidate_id": analog.get("candidate_id"),
                     "parent_candidate_id": parent["candidate_id"],
                     "verdict": "dropped", "reasons": []}
            astruct = analog.get("structure") or {}
            smiles = astruct.get("value")
            if str(astruct.get("format") or "").lower() != "smiles" \
                    or not smiles:
                entry["reasons"].append("no_smiles_structure")
                entries.append(entry)
                continue
            key = design_rdkit.inchikey(smiles)
            if key and key in seen:
                entry["reasons"].append("duplicate_or_parent")
                entries.append(entry)
                continue
            if key:
                seen.add(key)
            a_described = design_rdkit.describe_smiles(smiles)
            if not a_described.get("valid"):
                entry["reasons"].append("invalid_structure")
                entries.append(entry)
                continue
            entry["canonical_smiles"] = a_described["canonical_smiles"]
            a_logp = (a_described.get("descriptors") or {}).get("logp")
            if lead_logp is not None and a_logp is not None \
                    and abs(a_logp - lead_logp) > LOGP_DRIFT_LIMIT:
                entry["reasons"].append("logp_drift")
                entry["objectives"] = objective_vector(a_described)
                entries.append(entry)
                continue
            vector = objective_vector(a_described)
            ok, deltas = improves(vector, parent["objectives"])
            entry["objectives"] = vector
            entry["deltas"] = deltas
            if ok:
                entry["verdict"] = "kept"
                kept.append((_snapshot(analog.get("candidate_id"),
                                       a_described, vector), entry))
            else:
                entry["reasons"].append("no_pareto_improvement")
            entries.append(entry)
        total_kept += len(kept)
        round_record = {"round": round_no,
                        "parent_candidate_id": parent["candidate_id"],
                        "proposed": entries,
                        "kept": [snap["candidate_id"]
                                 for snap, _e in kept]}
        record_rounds.append(round_record)
        if kept:
            kept.sort(key=lambda pair: (
                -len([d for d in pair[1]["deltas"].values()
                      if d != 0]),
                -(pair[1]["deltas"].get("qed") or 0.0)))
            best = kept[0][0]
            parent = best
            parent_smiles = best["canonical_smiles"]
        else:
            round_record["stopped"] = ("no analog improved on the "
                                      "parent; the loop stops here")
            break
    status = "completed" if total_kept else (
        "no_improvement" if total_proposed else "no_analogs")
    record = {**base, "status": status,
              "lead": _snapshot(lead.get("candidate_id"), described,
                                objective_vector(described)),
              "rounds": record_rounds,
              "proposed_total": total_proposed,
              "kept_total": total_kept,
              "best": best}
    if source_check and total_kept:
        from . import design_sources
        kept_candidates = []
        for round_record in record_rounds:
            for snap_candidate_id in round_record["kept"]:
                kept_candidates.append(
                    {"candidate_id": snap_candidate_id,
                     "structure": {"format": "smiles",
                                   "value": next(
                                       e["canonical_smiles"]
                                       for e in round_record["proposed"]
                                       if e["candidate_id"]
                                       == snap_candidate_id)}})
        check = design_sources.check_candidates(kept_candidates)
        check["requested"] = True
        record["source_check"] = check
    return record
