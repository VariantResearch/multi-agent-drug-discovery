"""Debate transcript: a debate record rendered for a human reader.

The frozen record is the evidence; this is the reading copy. It lays
out what the record holds, in the order the debate happened: who the
providers were, what the evidence call struck and why, how the
dossiers ranked, the cross-examination and any red-team round, the
evolution merge, the consensus tests, the judge swap, and the final
specification with its dissent log. It renders the record's contents
only - no interpretation, no new claims - and tolerates partial
records by printing what is there.
"""
from __future__ import annotations


def _claim_line(claim):
    """One surviving claim as a markdown bullet with its citation."""
    return ("- [" + str(claim.get("evidence_tier")) + "] "
            + str(claim.get("claim_id")) + ": " + str(claim.get("text"))
            + " (" + str(claim.get("identifier_type")) + ": "
            + str(claim.get("source_identifier")) + ", "
            + str(claim.get("verification_status")) + ")")


def record_to_markdown(record: dict) -> str:
    """Render one debate record (see madd/debate.py) as markdown."""
    lines = ["# Debate transcript",
             "",
             "Frame: " + str(record.get("frame_id")),
             "Outcome: " + str(record.get("outcome")),
             ""]
    if record.get("red_team_round"):
        lines.append("Instant agreement triggered the red-team round.")
        lines.append("")
    lines += ["## Providers", ""]
    for provider in record.get("providers") or []:
        lines.append("- " + str(provider.get("name"))
                     + " (" + str(provider.get("model_version")) + ")"
                     + " | agent " + str(provider.get("agent_id"))
                     + " | dossier " + str(provider.get("dossier_id")))
    if not record.get("providers"):
        lines.append("- none recorded")
    lines += ["", "## Evidence call: struck claims", ""]
    strikes = record.get("strike_list") or []
    for strike in strikes:
        lines.append("- " + str(strike.get("dossier_id")) + " / "
                     + str(strike.get("claim_id")) + ": "
                     + ", ".join(strike.get("reasons") or []))
    if not strikes:
        lines.append("- nothing was struck")
    lines += ["", "## Ranking", "",
              "| dossier | focus score | struck | pairwise wins |",
              "| --- | --- | --- | --- |"]
    for row in record.get("ranking") or []:
        lines.append("| " + str(row.get("dossier_id")) + " | "
                     + str(row.get("focus_score")) + " | "
                     + str(row.get("struck_count")) + " | "
                     + str(row.get("wins")) + " |")
    lines += ["", "## Cross-examination", ""]
    objections = record.get("cross_examination") or []
    for objection in objections:
        lines.append("- " + str(objection.get("kind")) + ": "
                     + str(objection.get("objector_agent_id"))
                     + " -> " + str(objection.get("target_dossier_id"))
                     + " | claims: "
                     + (", ".join(objection.get("claim_ids") or []) or "none")
                     + " | " + str(objection.get("note")))
    if not objections:
        lines.append("- no objections recorded")
    evolution = record.get("evolution") or {}
    lines += ["", "## Evolution round", "",
              "Base dossier: " + str(evolution.get("base_dossier_id"))
              + " | contributing: "
              + (", ".join(evolution.get("contributing_dossiers") or []) or "none")
              + " | claims merged: " + str(evolution.get("claims_merged"))
              + " | duplicate claim ids skipped: "
              + str(evolution.get("duplicate_claim_ids_skipped")),
              "", "## Consensus tests", ""]
    for test in ((record.get("consensus") or {}).get("results") or []):
        label = ("not applied" if test.get("status") == "not_applied"
                 else "pass" if test.get("passed") else "FAIL")
        lines.append("- " + str(test.get("test")) + ": " + label
                     + " (" + str(test.get("detail")) + ")")
    judge = record.get("judge_swap")
    lines += ["", "## Judge swap", ""]
    if judge:
        lines.append("Judge provider: " + str(judge.get("provider"))
                     + " | judge focus: " + str(judge.get("proposed_focus_id"))
                     + " | judge claims struck: "
                     + str(len(judge.get("struck") or [])))
        for struck in judge.get("struck") or []:
            lines.append("- " + str(struck.get("claim_id")) + ": "
                         + ", ".join(struck.get("reasons") or []))
    else:
        lines.append("No judge was supplied; stability is unestablished.")
    spec = record.get("spec") or {}
    lines += ["", "## Specification and dissent", "",
              "Focus: " + str(spec.get("focus_id"))
              + " | outcome on the frame: " + str(spec.get("outcome")),
              "", "Claims carried into the specification:"]
    lines.extend(_claim_line(c) for c in spec.get("claims") or [])
    if not spec.get("claims"):
        lines.append("- none")
    lines.append("")
    lines.append("Dissent log:")
    for entry in spec.get("dissent_log") or []:
        lines.append("- " + str(entry.get("objector_agent_id")) + ": "
                     + str(entry.get("objection"))
                     + " [" + str(entry.get("status")) + "]")
    if not spec.get("dissent_log"):
        lines.append("- empty; reason recorded in the record: "
                     + str(spec.get("dissent_none_reason")))
    lines.append("")
    return "\n".join(lines)
