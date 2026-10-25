"""Gate 0 retrospective dataset: loading, validation, leakage scan, scoring.

The dataset lives in the repository-level gate0/ directory:

- gate0/input/<case_id>.json holds the blinded input pack an agent would
  receive: real drug, target, disease, sponsor, an evidence_as_of cutoff
  date, and claims that rest only on sources published before the pivotal
  outcome was public.
- gate0/sealed/<case_id>.outcome.json holds the outcome. It is read only
  at scoring time, never when an agent pack is built.

build_agent_pack refuses to return a pack when validation fails, when a
sealed-only field is present in the input, or when any per-case forbidden
term (stored in the input file itself) appears in any input text field.
score_run reads sealed outcomes only when scoring and reports simple
counts; evaluate_thresholds then judges those counts against the Gate 0
pass thresholds approved by the project owner on 2026-10-22 and recorded
in docs/PHASE1_SPEC.md.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from .citation_auditor import check_identifier
from .claims import audit_claims
from .schemas import validate_artifact

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GATE0_DIR = REPO_ROOT / "gate0"

MAX_QUOTE_WORDS = 25
VALID_OUTCOME_CLASSES = {"positive", "negative"}
SEALED_ONLY_KEYS = {
    "outcome_class", "pivotal_result", "outcome_source_identifier",
    "outcome_source_type", "outcome_date", "reason_class",
}
REQUIRED_PACK_FIELDS = [
    "case_id", "disease", "target", "modality", "drug_name", "sponsor",
    "evidence_as_of", "claims", "forbidden_terms",
]
REQUIRED_OUTCOME_FIELDS = [
    "case_id", "outcome_class", "pivotal_result",
    "outcome_source_identifier", "outcome_date", "reason_class",
]
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PREDICTION_ALIASES = {"advance": "positive", "kill": "negative",
                      "positive": "positive", "negative": "negative"}


def _base_dir(gate0_dir=None) -> Path:
    """The Gate 0 dataset root: the caller's directory or the bundled one."""
    return Path(gate0_dir) if gate0_dir is not None else DEFAULT_GATE0_DIR


def input_dir(gate0_dir=None) -> Path:
    """The folder holding the blinded input packs."""
    return _base_dir(gate0_dir) / "input"


def sealed_dir(gate0_dir=None) -> Path:
    """The folder holding the sealed outcome files."""
    return _base_dir(gate0_dir) / "sealed"


def list_case_ids(gate0_dir=None) -> list:
    """Case ids from input pack filenames, sorted. No outcome data."""
    folder = input_dir(gate0_dir)
    if not folder.is_dir():
        return []
    return sorted(p.stem for p in folder.glob("*.json"))


def load_input_pack(case_id: str, gate0_dir=None) -> dict:
    """Load one case's blinded input pack by case id."""
    path = input_dir(gate0_dir) / (case_id + ".json")
    return json.loads(path.read_text(encoding="utf-8"))


def load_sealed_outcome(case_id: str, gate0_dir=None) -> dict:
    """Load one case's sealed outcome file by case id. Scoring code
    only; never part of anything a provider sees."""
    path = sealed_dir(gate0_dir) / (case_id + ".outcome.json")
    return json.loads(path.read_text(encoding="utf-8"))


def _walk(node, path="$"):
    """Yield (path, key, value) for every dict entry in a JSON structure."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield path + "." + str(key), key, value
            yield from _walk(value, path + "." + str(key))
    elif isinstance(node, list):
        for idx, item in enumerate(node):
            yield from _walk(item, path + "[" + str(idx) + "]")


def _iter_text(node, skip_keys=frozenset()):
    """Yield (path, string) for every string value outside skipped keys."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in skip_keys:
                continue
            yield from _iter_text(value, skip_keys)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_text(item, skip_keys)
    elif isinstance(node, str):
        yield "$", node


def leakage_scan(pack: dict) -> list:
    """Scan an input pack for outcome leakage.

    Two checks: (1) no sealed-only key appears anywhere in the pack;
    (2) no per-case forbidden term appears in any text field. The
    forbidden_terms list itself is excluded from the text scan, since it
    names the terms by design. Returns a list of problem dicts.
    """
    problems = []
    if not isinstance(pack, dict):
        return [{"code": "pack_not_object", "message": "input pack is not a JSON object"}]
    for path, key, _value in _walk(pack):
        if key in SEALED_ONLY_KEYS:
            problems.append({"code": "sealed_field_present", "path": path,
                             "message": "sealed outcome field present in input pack: " + str(key)})
    terms = pack.get("forbidden_terms") or []
    texts = []
    if isinstance(pack, dict):
        for key, value in pack.items():
            if key == "forbidden_terms":
                continue
            for _p, s in _iter_text(value):
                texts.append(s)
    for term in terms:
        if not isinstance(term, str) or term.strip() == "":
            continue
        needle = term.lower()
        for text in texts:
            if needle in text.lower():
                problems.append({"code": "forbidden_term_found", "term": term,
                                   "message": "forbidden outcome-revealing term found in input text: " + term})
                break
    return problems


def validate_pack(pack) -> list:
    """Validate one input pack against the Claim rules and dataset rules."""
    errors = []
    if not isinstance(pack, dict):
        return [{"code": "pack_not_object", "message": "input pack is not a JSON object"}]
    case_id = pack.get("case_id", "<missing case_id>")
    for field in REQUIRED_PACK_FIELDS:
        if field not in pack:
            errors.append({"case_id": case_id, "code": "missing_pack_field",
                           "message": "required input pack field missing: " + field})
    for field in ("disease", "target", "modality", "drug_name", "sponsor"):
        value = pack.get(field)
        if field in pack and (not isinstance(value, str) or value.strip() == ""):
            errors.append({"case_id": case_id, "code": "empty_pack_field",
                           "message": "input pack field is empty: " + field})
    as_of = pack.get("evidence_as_of")
    if "evidence_as_of" in pack and not (isinstance(as_of, str) and DATE_RE.match(as_of)):
        errors.append({"case_id": case_id, "code": "bad_evidence_as_of",
                       "message": "evidence_as_of must be a YYYY-MM-DD date"})
    terms = pack.get("forbidden_terms")
    if "forbidden_terms" in pack and not (isinstance(terms, list) and len(terms) > 0):
        errors.append({"case_id": case_id, "code": "missing_forbidden_terms",
                       "message": "forbidden_terms must be a non-empty list"})
    claims = pack.get("claims")
    if "claims" in pack and not (isinstance(claims, list) and len(claims) > 0):
        errors.append({"case_id": case_id, "code": "no_claims",
                       "message": "input pack carries no claims"})
    if isinstance(claims, list):
        for claim in claims:
            if not isinstance(claim, dict):
                errors.append({"case_id": case_id, "code": "claim_not_object",
                               "message": "claim entry is not a JSON object"})
                continue
            cid = claim.get("claim_id", "<missing claim_id>")
            for schema_error in validate_artifact("claim", claim):
                errors.append({"case_id": case_id, "claim_id": cid,
                               "code": "claim_schema_" + schema_error["code"],
                               "message": schema_error["path"] + ": " + schema_error["message"]})
            fmt = check_identifier(claim.get("source_identifier"), claim.get("identifier_type"))
            if not fmt["ok"]:
                errors.append({"case_id": case_id, "claim_id": cid,
                               "code": "identifier_" + fmt["code"], "message": fmt["message"]})
            tier = claim.get("evidence_tier")
            if not (isinstance(tier, int) and not isinstance(tier, bool) and 1 <= tier <= 5):
                errors.append({"case_id": case_id, "claim_id": cid, "code": "tier_out_of_range",
                               "message": "evidence_tier must be an integer from 1 to 5"})
            if claim.get("verification_status") != "quote_checked":
                errors.append({"case_id": case_id, "claim_id": cid, "code": "not_quote_checked",
                               "message": "Gate 0 input claims must carry verification_status quote_checked, "
                                          "recorded only when the source text was fetched and read"})
            quote = claim.get("supporting_quote")
            if not isinstance(quote, str) or quote.strip() == "":
                errors.append({"case_id": case_id, "claim_id": cid, "code": "missing_supporting_quote",
                               "message": "quote_checked claim carries no supporting_quote"})
            elif len(quote.split()) > MAX_QUOTE_WORDS:
                errors.append({"case_id": case_id, "claim_id": cid, "code": "quote_too_long",
                               "message": "supporting_quote exceeds " + str(MAX_QUOTE_WORDS) + " words"})
        audit = audit_claims(pack)
        for err in audit["errors"]:
            errors.append({"case_id": case_id, "claim_id": err["claim_id"],
                           "code": err["code"], "message": err["message"]})
    for problem in leakage_scan(pack):
        errors.append({"case_id": case_id, "code": problem["code"],
                       "message": problem["message"]})
    return errors


def validate_outcome(outcome, expected_case_id=None) -> list:
    """Validate one sealed outcome's structure and outcome_class
    normalisation; returns a list of error dicts."""
    errors = []
    if not isinstance(outcome, dict):
        return [{"code": "outcome_not_object", "message": "sealed outcome is not a JSON object"}]
    case_id = outcome.get("case_id", "<missing case_id>")
    for field in REQUIRED_OUTCOME_FIELDS:
        if field not in outcome:
            errors.append({"case_id": case_id, "code": "missing_outcome_field",
                           "message": "required sealed outcome field missing: " + field})
        elif isinstance(outcome.get(field), str) and outcome[field].strip() == "":
            errors.append({"case_id": case_id, "code": "empty_outcome_field",
                           "message": "sealed outcome field is empty: " + field})
    if expected_case_id is not None and outcome.get("case_id") != expected_case_id:
        errors.append({"case_id": case_id, "code": "outcome_case_mismatch",
                       "message": "sealed outcome case_id does not match its input pack"})
    if outcome.get("outcome_class") not in VALID_OUTCOME_CLASSES:
        errors.append({"case_id": case_id, "code": "bad_outcome_class",
                       "message": "outcome_class must be positive or negative"})
    return errors


def validate_dataset(gate0_dir=None) -> dict:
    """Validate every input pack and its sealed outcome. Returns a report."""
    base = _base_dir(gate0_dir)
    errors = []
    case_ids = list_case_ids(base)
    if not case_ids:
        errors.append({"code": "no_cases", "message": "no input packs found in " + str(input_dir(base))})
    sealed_ids = []
    sdir = sealed_dir(base)
    if sdir.is_dir():
        sealed_ids = sorted(p.name[: -len(".outcome.json")] for p in sdir.glob("*.outcome.json"))
    if sealed_ids != case_ids:
        errors.append({"code": "sealed_input_mismatch",
                       "message": "sealed outcome case ids do not match input case ids: "
                                  "inputs " + str(case_ids) + ", sealed " + str(sealed_ids)})
    class_counts = {"positive": 0, "negative": 0}
    for case_id in case_ids:
        try:
            pack = load_input_pack(case_id, base)
        except Exception as exc:
            errors.append({"case_id": case_id, "code": "input_unreadable", "message": str(exc)})
            continue
        if pack.get("case_id") != case_id:
            errors.append({"case_id": case_id, "code": "pack_case_mismatch",
                           "message": "input pack case_id does not match its filename"})
        errors.extend(validate_pack(pack))
        if case_id in sealed_ids:
            try:
                outcome = load_sealed_outcome(case_id, base)
            except Exception as exc:
                errors.append({"case_id": case_id, "code": "outcome_unreadable", "message": str(exc)})
                continue
            errors.extend(validate_outcome(outcome, expected_case_id=case_id))
            if outcome.get("outcome_class") in class_counts:
                class_counts[outcome["outcome_class"]] += 1
    return {"ok": len(errors) == 0, "case_ids": case_ids, "case_count": len(case_ids),
            "positive_count": class_counts["positive"], "negative_count": class_counts["negative"],
            "error_count": len(errors), "errors": errors}


def build_agent_pack(case_id: str, gate0_dir=None) -> dict:
    """Return the blinded agent pack for a case.

    Raises ValueError when the pack fails validation or the leakage scan
    finds any sealed field or forbidden outcome-revealing term. The
    returned dict contains input data only: metadata fields and claims.
    Sealed outcomes are never read here.
    """
    pack = load_input_pack(case_id, gate0_dir)
    errors = validate_pack(pack)
    if pack.get("case_id") != case_id:
        errors.append({"case_id": case_id, "code": "pack_case_mismatch",
                       "message": "input pack case_id does not match the requested case"})
    if errors:
        summary = "; ".join(e["code"] + ": " + e["message"] for e in errors)
        raise ValueError("Gate 0 pack refused for " + case_id + " - " + summary)
    return copy.deepcopy(pack)


def score_run(predictions, sealed_dir=None) -> dict:
    """Score predicted outcome classes against the sealed outcomes.

    predictions maps case_id to a predicted class: "positive" or
    "negative" (the aliases "advance" and "kill" are also accepted).
    Sealed outcomes are read only here, at scoring time. The result is
    simple counts; pass/fail judgement lives in evaluate_thresholds.
    """
    if sealed_dir is not None and Path(sealed_dir).name == "sealed":
        base = Path(sealed_dir).parent
    else:
        base = _base_dir(sealed_dir)
    normalised = {}
    unknown_predictions = []
    for case_id, value in dict(predictions).items():
        key = str(value).strip().lower()
        if key in PREDICTION_ALIASES:
            normalised[case_id] = PREDICTION_ALIASES[key]
        else:
            unknown_predictions.append(case_id)
    case_ids = list_case_ids(base)
    correct = 0
    killed = 0
    advanced = 0
    incorrect = []
    missing = []
    for case_id in case_ids:
        outcome = load_sealed_outcome(case_id, base)
        actual = outcome.get("outcome_class")
        predicted = normalised.get(case_id)
        if predicted is None:
            missing.append(case_id)
            continue
        if predicted == actual:
            correct += 1
            if actual == "negative":
                killed += 1
            elif actual == "positive":
                advanced += 1
        else:
            incorrect.append(case_id)
    extra = sorted(c for c in normalised if c not in case_ids)
    return {"case_count": len(case_ids), "scored_count": len(case_ids) - len(missing),
            "correct_calls": correct, "failures_correctly_killed": killed,
            "positives_correctly_advanced": advanced, "incorrect_calls": incorrect,
            "missing_predictions": missing, "unknown_prediction_cases": extra,
            "invalid_prediction_cases": sorted(unknown_predictions)}


# Gate 0 pass thresholds, approved by the project owner on 2026-10-22 and
# recorded in docs/PHASE1_SPEC.md ("Approved thresholds"). Changing a
# value here without the matching spec change and changelog entry breaks
# the rule that thresholds are fixed before a scored run.
APPROVED_THRESHOLDS = {
    "min_failures_killed": 3,
    "min_positives_advanced": 3,
    "min_baseline_margin": 1,
    "max_audit_violations": 0,
    "max_judge_swap_flips": 1,
    "source": "docs/PHASE1_SPEC.md, approved 2026-10-22",
}


def _threshold_check(name, status, detail):
    """One threshold verdict line: {threshold, status, detail}."""
    return {"threshold": name, "status": status, "detail": detail}


def evaluate_thresholds(debate_score, baseline_score=None, audit_violations=None,
                        judge_swap_flips=None, thresholds=None) -> dict:
    """Judge a scored Gate 0 run against the approved thresholds.

    debate_score and baseline_score are score_run results. audit_violations
    is the count of load-bearing claims in final dossiers resting on struck
    or unverified citations. judge_swap_flips is the number of case calls
    that changed when the judging step was re-run with a different judge
    model family.

    Every threshold is reported as pass, fail, or not_evaluable. A run
    passes overall only when every threshold passes: a missing input is
    never treated as a pass. A run_completeness check comes first: a
    run that did not produce a call for every case fails outright,
    whatever its counts on the cases it did call.
    """
    limits = dict(APPROVED_THRESHOLDS if thresholds is None else thresholds)
    checks = []

    missing_predictions = debate_score.get("missing_predictions") or []
    scored_count = debate_score.get("scored_count")
    case_count = debate_score.get("case_count")
    incomplete = (bool(missing_predictions)
                  or not isinstance(case_count, int) or case_count == 0
                  or (isinstance(scored_count, int) and isinstance(case_count, int)
                      and scored_count < case_count))
    checks.append(_threshold_check(
        "run_completeness",
        "fail" if incomplete else "pass",
        "scored " + str(scored_count) + " of " + str(case_count) + " cases"
        + ("; predictions missing for: " + ", ".join(str(c) for c in missing_predictions)
           if missing_predictions else "")
        + ("; a run that did not call every case cannot pass" if incomplete else "")))

    killed = debate_score.get("failures_correctly_killed")
    if not isinstance(killed, int) or isinstance(killed, bool):
        checks.append(_threshold_check(
            "failure_kill_rate", "not_evaluable",
            "the debate score carries no failures_correctly_killed count"))
    else:
        checks.append(_threshold_check(
            "failure_kill_rate",
            "pass" if killed >= limits["min_failures_killed"] else "fail",
            "failures correctly killed: " + str(killed) + " of "
            + str(case_count) + " cases; need at least "
            + str(limits["min_failures_killed"])))

    advanced = debate_score.get("positives_correctly_advanced")
    if not isinstance(advanced, int) or isinstance(advanced, bool):
        checks.append(_threshold_check(
            "positive_advance_rate", "not_evaluable",
            "the debate score carries no positives_correctly_advanced count"))
    else:
        checks.append(_threshold_check(
            "positive_advance_rate",
            "pass" if advanced >= limits["min_positives_advanced"] else "fail",
            "positives correctly advanced: " + str(advanced) + "; need at least "
            + str(limits["min_positives_advanced"])))

    if baseline_score is None:
        checks.append(_threshold_check(
            "baseline_margin", "not_evaluable",
            "no baseline score supplied; the debate must beat a single-model "
            "baseline, so this threshold cannot be judged"))
    else:
        margin = (debate_score.get("correct_calls", 0)
                  - baseline_score.get("correct_calls", 0))
        checks.append(_threshold_check(
            "baseline_margin",
            "pass" if margin >= limits["min_baseline_margin"] else "fail",
            "debate correct calls minus baseline correct calls: " + str(margin)
            + "; need at least " + str(limits["min_baseline_margin"])))

    if audit_violations is None:
        checks.append(_threshold_check(
            "audit_integrity", "not_evaluable",
            "no audit violation count supplied"))
    else:
        checks.append(_threshold_check(
            "audit_integrity",
            "pass" if audit_violations <= limits["max_audit_violations"] else "fail",
            "load-bearing claims on struck or unverified citations: "
            + str(audit_violations) + "; allowed at most "
            + str(limits["max_audit_violations"])))

    if judge_swap_flips is None:
        checks.append(_threshold_check(
            "judge_swap_stability", "not_evaluable",
            "no judge-swap result supplied"))
    else:
        checks.append(_threshold_check(
            "judge_swap_stability",
            "pass" if judge_swap_flips <= limits["max_judge_swap_flips"] else "fail",
            "case calls flipped by a judge swap: " + str(judge_swap_flips)
            + "; allowed at most " + str(limits["max_judge_swap_flips"])))

    return {"passed": all(c["status"] == "pass" for c in checks),
            "checks": checks,
            "thresholds_applied": {k: v for k, v in limits.items() if k != "source"},
            "thresholds_source": limits.get("source")}
