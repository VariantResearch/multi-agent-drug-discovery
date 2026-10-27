"""Calibration of panel verdicts against sealed Gate 0 outcomes.

Accuracy alone cannot say how much a verdict is worth: a panel
that is right when it agrees and coin-flipping when it splits is
a different instrument from one that is uniformly decent, and the
difference is exactly what protocol choices (a second model, a
judge) are supposed to buy. This module measures that difference
from recorded runs only: for every case in one or more Gate 0
bundles it buckets the debate by how much the panel agreed, then
reports the realized accuracy inside each bucket, grouped by the
run's protocol mode.

Agreement is read from the record's ranking, the per-agent
proposed focus identifiers: unanimous (every agent proposed the
same focus), majority (one focus held by more than half), or
split (no majority). The case call is the runner's own rule
(locked reads as advance, anything else as kill) and correctness
is judged against the sealed outcomes, read only here, at
measurement time, the same boundary score_run keeps.

Everything reported is a count of recorded cases. No probability
is fitted or implied: bucket accuracies are diagnostics over a
small frozen set, not guarantees, and they are weakest exactly
where the buckets are smallest. A calibration table over eight
cases can rank protocol modes by their agreement profile; it
cannot certify any of them.
"""
from __future__ import annotations

from collections import Counter

from .gate0 import list_case_ids, load_sealed_outcome

BUCKETS = ("unanimous", "majority", "split", "no_proposals")


def case_call(record: dict) -> str:
    """The runner's per-case call: locked is advance, else kill."""
    return "advance" if record.get("outcome") == "locked" else "kill"


def case_bucket(record: dict) -> str:
    """Bucket one debate record by panel agreement on the focus.

    Reads the ranking's proposed focus identifiers: unanimous
    when every agent proposed the same one, majority when one
    focus holds more than half of the proposals, split when no
    focus holds a majority, and no_proposals when the ranking
    carries none.
    """
    proposals = [entry.get("proposed_focus_id")
                 for entry in record.get("ranking") or []
                 if entry.get("proposed_focus_id")]
    if not proposals:
        return "no_proposals"
    top_focus, top_count = Counter(proposals).most_common(1)[0]
    if top_count == len(proposals):
        return "unanimous"
    if top_count * 2 > len(proposals):
        return "majority"
    return "split"


def _empty_group() -> dict:
    """A zeroed accuracy group: totals plus per-bucket counts."""
    return {"cases": 0, "correct": 0,
            "buckets": {name: {"cases": 0, "correct": 0}
                        for name in BUCKETS}}


def _finish(group: dict) -> dict:
    """Add accuracy ratios to a counted group, in place."""
    group["accuracy"] = (round(group["correct"] / group["cases"], 3)
                         if group["cases"] else None)
    for bucket in group["buckets"].values():
        bucket["accuracy"] = (round(bucket["correct"] / bucket["cases"], 3)
                              if bucket["cases"] else None)
    return group


def calibration_report(bundles, gate0_dir=None) -> dict:
    """Measure agreement-bucketed accuracy over Gate 0 bundles.

    bundles is an iterable of gate0 run bundles (dicts with
    case_records). Returns {runs, cases, modes, overall}: modes
    maps each bundle's protocol mode to its group, and every
    group carries case/correct counts and accuracy overall and
    per agreement bucket. Cases whose sealed outcome cannot be
    read are skipped and counted under "unscored".
    """
    modes = {}
    overall = _empty_group()
    runs = 0
    unscored = 0
    known_cases = set(list_case_ids(gate0_dir))
    for bundle in bundles:
        if not isinstance(bundle, dict):
            continue
        records = bundle.get("case_records") or {}
        if not records:
            continue
        runs += 1
        mode = str(bundle.get("mode") or "legacy")
        group = modes.setdefault(mode, _empty_group())
        for case_id, record in records.items():
            if case_id not in known_cases:
                unscored += 1
                continue
            actual = load_sealed_outcome(case_id, gate0_dir).get("outcome_class")
            predicted = "positive" if case_call(record) == "advance" else "negative"
            correct = predicted == actual
            bucket = case_bucket(record)
            for target in (group, overall):
                target["cases"] += 1
                target["buckets"][bucket]["cases"] += 1
                if correct:
                    target["correct"] += 1
                    target["buckets"][bucket]["correct"] += 1
    for group in modes.values():
        _finish(group)
    _finish(overall)
    return {"runs": runs, "unscored": unscored, "modes": modes,
            "overall": overall}


def format_calibration(report: dict) -> str:
    """Render a calibration report as a readable text table."""
    def group_lines(label, group):
        """Render one mode group as table lines."""
        lines = [label + ": " + str(group["correct"]) + "/" +
                 str(group["cases"]) + " correct" +
                 (" (accuracy " + str(group["accuracy"]) + ")"
                  if group["accuracy"] is not None else "")]
        for name in BUCKETS:
            bucket = group["buckets"][name]
            if bucket["cases"]:
                lines.append("  " + name.ljust(13) +
                             str(bucket["correct"]) + "/" +
                             str(bucket["cases"]) +
                             " (accuracy " + str(bucket["accuracy"]) + ")")
        return lines

    lines = ["Calibration over " + str(report["runs"]) + " Gate 0 run(s), " +
             str(report["overall"]["cases"]) + " scored case(s)" +
             (", " + str(report["unscored"]) + " unscored"
              if report["unscored"] else "")]
    for mode in sorted(report["modes"]):
        lines += group_lines("mode " + mode, report["modes"][mode])
    if len(report["modes"]) > 1:
        lines += group_lines("overall", report["overall"])
    lines.append("Bucket accuracies are diagnostics over a small frozen"
                 " set, not guarantees.")
    return "\n".join(lines)
