"""Plain-language markdown report for a run bundle.

The bundle JSON is the record; this is the readable version of it.
Written for a person deciding whether to trust the run: what was
called, what the scores were, which thresholds passed or failed, and
what the auditors struck. It reports the bundle's contents and
nothing else - no new claims, no interpretation beyond the numbers.
"""
from __future__ import annotations


def _threshold_lines(thresholds):
    """One markdown line per threshold check: name, status, detail."""
    lines = []
    for check in (thresholds or {}).get("checks", []):
        lines.append("- " + check["threshold"] + ": " + check["status"]
                     + " (" + check["detail"] + ")")
    return lines


def _gate0_markdown(bundle):
    """Render a Gate 0 run bundle: result, both scores, every
    threshold check, per-case calls with verdicts, budget state."""
    debate = bundle.get("debate_score") or {}
    baseline = bundle.get("baseline_score") or {}
    incorrect = set(debate.get("incorrect_calls") or [])
    lines = [
        "# Gate 0 run report",
        "",
        "Run: " + str(bundle.get("run_id")),
        "Result: " + ("passed the approved thresholds"
                      if bundle.get("outcome") == "pass"
                      else "did not pass the approved thresholds"),
        "",
        "## Scores",
        "",
        "- Debate system: " + str(debate.get("correct_calls")) + " of "
        + str(debate.get("case_count")) + " calls correct; "
        + str(debate.get("failures_correctly_killed")) + " failures killed, "
        + str(debate.get("positives_correctly_advanced")) + " positives advanced.",
        "- Single-model baseline: " + str(baseline.get("correct_calls"))
        + " of " + str(baseline.get("case_count")) + " calls correct.",
        "- Audit violations in final specifications: "
        + str(bundle.get("audit_violations")),
        "- Judge-swap flips: " + str(bundle.get("judge_swap_flips")),
        "",
        "## Thresholds (" + str((bundle.get("thresholds") or {}).get("thresholds_source")) + ")",
        "",
    ]
    lines.extend(_threshold_lines(bundle.get("thresholds")))
    lines += ["", "## Case calls", ""]
    for case_id in bundle.get("case_ids", []):
        record = (bundle.get("case_records") or {}).get(case_id) or {}
        verdict = "wrong" if case_id in incorrect else "correct"
        lines.append("- " + case_id + ": debate called "
                     + str((bundle.get("predictions") or {}).get(case_id))
                     + ", baseline called "
                     + str((bundle.get("baseline_predictions") or {}).get(case_id))
                     + "; debate call was " + verdict
                     + "; strikes in debate: " + str(len(record.get("strike_list") or []))
                     + "; dissent entries: "
                     + str(len(((record.get("spec") or {}).get("dissent_log")) or [])))
    budget = bundle.get("budget")
    if budget:
        lines += ["", "## Budget", "",
                  "- Spent " + str(budget.get("spent_usd")) + " USD across "
                  + str(budget.get("calls_made")) + " calls (caps: cost "
                  + str(budget.get("max_cost_usd")) + ", calls "
                  + str(budget.get("max_calls")) + ")."]
    lines += ["", "Calls are judged against the sealed outcomes. A locked "
                  "specification counts as an advance call and a no_go as a "
                  "kill call, per the rule fixed in madd/runner.py.", ""]
    return "\n".join(lines)


def _frame_markdown(bundle):
    """Render a frame run bundle: outcome, focus, consensus test
    results, strike and dissent counts."""
    record = bundle.get("record") or {}
    spec = record.get("spec") or {}
    lines = [
        "# Frame run report",
        "",
        "Run: " + str(bundle.get("run_id")),
        "Frame: " + str(bundle.get("frame_id")),
        "Outcome: " + str(bundle.get("outcome")),
        "Focus: " + str(spec.get("focus_id")),
        "",
        "## Consensus tests",
        "",
    ]
    for test in ((record.get("consensus") or {}).get("results") or []):
        lines.append("- " + test["test"] + ": "
                     + ("pass" if test["passed"] else "FAIL")
                     + " (" + test["detail"] + ")")
    lines += ["", "Strikes at the evidence call: "
              + str(len(record.get("strike_list") or [])),
              "Dissent entries: " + str(len(spec.get("dissent_log") or [])),
              ""]
    return "\n".join(lines)


def _design_markdown(bundle: dict) -> str:
    """Markdown report for a Phase 2 design bundle."""
    brief = bundle.get("brief") or {}
    gate = bundle.get("gate_report") or {}
    lines = ["# Design run " + str(bundle.get("run_id")),
             "",
             "Target: " + str(brief.get("target")) + " | Disease: "
             + str(brief.get("disease")) + " | Spec: " + str(brief.get("spec_id")),
             "Designer: " + str(bundle.get("designer")) + " | Gate: "
             + str(gate.get("result")),
             "", "## Gate checks"]
    for check in gate.get("checks", []):
        lines.append("- " + str(check.get("name")) + ": " + str(check.get("status"))
                     + " (" + str(check.get("detail")) + ")")
    ranking = bundle.get("ranking") or {}
    audits = {a["candidate_id"]: a for a in bundle.get("audits", [])}
    cand_by_id = {c.get("candidate_id"): c for c in bundle.get("candidates", [])}
    lines += ["", "## Ranked candidates"]
    if ranking.get("ranked"):
        for i, cid in enumerate(ranking["ranked"], start=1):
            a = audits.get(cid) or {}
            marker = (" [SYNTHETIC placeholder - not a real candidate]"
                      if (cand_by_id.get(cid) or {}).get("_synthetic") else "")
            lines.append(str(i) + ". " + str(cid) + " - audited load-bearing claims: "
                         + str(a.get("audited_load_bearing")) + ", unverified predictions: "
                         + str(a.get("unverified_predictions")) + marker)
    else:
        lines.append("(none)")
    lines += ["", "## Excluded candidates"]
    if ranking.get("excluded"):
        for ex in ranking["excluded"]:
            lines.append("- " + str(ex.get("candidate_id")) + ": "
                         + "; ".join(ex.get("reasons") or []))
    else:
        lines.append("(none)")
    lines += ["", "## Tool runs"]
    if bundle.get("tool_runs"):
        for t in bundle["tool_runs"]:
            if "valid" in t:
                detail = ("checked " + str(t.get("checked")) + ", valid "
                          + str(t.get("valid")) + ", invalid "
                          + str(t.get("invalid")))
            elif "known" in t:
                detail = ("checked " + str(t.get("checked")) + ", known "
                          + str(t.get("known")) + ", no record "
                          + str(t.get("no_record")))
            else:
                detail = str(len(t.get("outputs") or [])) + " outputs"
            lines.append("- " + str(t.get("tool")) + ": " + str(t.get("status"))
                         + " (" + detail + ")")
    else:
        lines.append("(none)")
    if bundle.get("designer_notes"):
        lines += ["", "## Designer notes"]
        for note in bundle["designer_notes"]:
            lines.append("- " + str(note))
    lines.append("")
    return "\n".join(lines)


def bundle_to_markdown(bundle: dict) -> str:
    """Dispatch on bundle kind and return the markdown report."""
    if bundle.get("kind") == "gate0_run":
        return _gate0_markdown(bundle)
    if bundle.get("kind") == "design_run":
        return _design_markdown(bundle)
    return _frame_markdown(bundle)
