"""Run comparison: what changed between two Gate 0 run bundles.

The second run is where the questions start: did the new roster do
better, which case calls flipped, which threshold moved? compare_bundles
answers from the two bundles alone: score deltas, flipped calls,
threshold status changes, and the audit and retry deltas. It compares
records, not reputations: two bundles over different case sets are
compared on their shared cases for flips and flagged as different
sets, so a comparison never quietly pretends the runs were alike.
"""
from __future__ import annotations

import json
from pathlib import Path


def load_bundle_anywhere(path) -> dict:
    """Load a bundle from a bundle.json path or a run folder path."""
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "bundle.json"
    return json.loads(candidate.read_text(encoding="utf-8"))


def compare_bundles(a: dict, b: dict) -> dict:
    """Compare Gate 0 bundle a (earlier) with b (later)."""
    score_a = a.get("debate_score") or {}
    score_b = b.get("debate_score") or {}
    preds_a = a.get("predictions") or {}
    preds_b = b.get("predictions") or {}
    shared = sorted(set(preds_a) & set(preds_b))
    flipped = [cid for cid in shared if preds_a[cid] != preds_b[cid]]
    status_a = {c["threshold"]: c["status"]
                for c in (a.get("thresholds") or {}).get("checks", [])}
    status_b = {c["threshold"]: c["status"]
                for c in (b.get("thresholds") or {}).get("checks", [])}
    threshold_changes = [{"threshold": name,
                          "from": status_a.get(name), "to": status_b.get(name)}
                         for name in sorted(set(status_a) | set(status_b))
                         if status_a.get(name) != status_b.get(name)]

    def delta(key, source_a, source_b):
        """Integer delta (b minus a) for one field; None when either
        side is not an int, so missing data reads as n/a, not zero."""
        va, vb = source_a.get(key), source_b.get(key)
        if isinstance(va, int) and isinstance(vb, int):
            return vb - va
        return None

    return {
        "run_a": a.get("run_id"),
        "run_b": b.get("run_id"),
        "outcome_a": a.get("outcome"),
        "outcome_b": b.get("outcome"),
        "same_case_set": set(a.get("case_ids") or []) == set(b.get("case_ids") or []),
        "score_deltas": {
            "debate_correct": delta("correct_calls", score_a, score_b),
            "failures_killed": delta("failures_correctly_killed", score_a, score_b),
            "positives_advanced": delta("positives_correctly_advanced",
                                        score_a, score_b),
            "baseline_correct": delta(
                "correct_calls", a.get("baseline_score") or {},
                b.get("baseline_score") or {}),
        },
        "flipped_calls": flipped,
        "threshold_changes": threshold_changes,
        "audit_violations_delta": delta("audit_violations", a, b),
        "judge_swap_flips_delta": delta("judge_swap_flips", a, b),
    }


def comparison_to_text(comparison: dict) -> str:
    """A comparison as readable lines for the CLI."""
    lines = ["compare runs",
             "  A: " + str(comparison["run_a"]) + " (" + str(comparison["outcome_a"]) + ")",
             "  B: " + str(comparison["run_b"]) + " (" + str(comparison["outcome_b"]) + ")",
             "  same case set: " + ("yes" if comparison["same_case_set"] else "NO")]
    for name, change in comparison["score_deltas"].items():
        lines.append("  " + name + " delta: " + ("n/a" if change is None
                                                  else format(change, "+d")))
    lines.append("  flipped calls: "
                 + (", ".join(comparison["flipped_calls"]) or "none"))
    for change in comparison["threshold_changes"]:
        lines.append("  threshold " + change["threshold"] + ": "
                     + str(change["from"]) + " -> " + str(change["to"]))
    if not comparison["threshold_changes"]:
        lines.append("  threshold changes: none")
    return "\n".join(lines)
