"""Debate transcript: a debate record rendered for a human reader.

The frozen record is the evidence; this is the reading copy. It lays
out the debate in the order it happened: the dossiers after the
evidence call (what survived, what was struck and why), the
cross-examination, the ranking, the evolution round, the consensus
tests, the judge swap, and the dissent log, ending at the outcome.
It renders the record's contents only - no interpretation, no new
claims - and tolerates partial records by printing what is there.
"""
from __future__ import annotations


def _claim_line(claim):
    return ("- [" + str(claim.get("evidence_tier")) + "] "
            + str(claim.get("claim_id")) + ": " + str(claim.get("text"))
            + " (" + str(claim.get("identifier_type")) + ": "
            + str(claim.get("source_identifier")) + ", "
            + str(claim.get("verification_status")) + ")")


def record_to_markdown(record: dict) -> str:
    """Render one debate record (see madd/debate.py) as markdown."""
    frame = record.get("frame") or {}
    lines = ["# Debate transcript",
             "",
             "Frame: " + str(frame.get("frame_id")),
             "Question: " + str(frame.get("question")),
             "Outcome: " + str(record.get("outcome")),
             "",
             "## Dossiers after the evidence call", ""]
    for dossier in record.get("dossiers") or []:
        score = (dossier.get("focus_score") or {}).get("score")
        lines.append("### " + str(dossier.get("dossier_id"))
                     + " (agent " + str(dossier.get("agent_id")) + ")")
        lines.append("")
        lines.append("Proposed focus: " + str(dossier.get("proposed_focus_id"))
                     + " | audited focus score: " + str(score))
        lines.append("")
        lines.append("Surviving claims:")
        lines.extend(_claim_line(c) for c in dossier.get("surviving_claims") or [])
        if not dossier.get("surviving_claims"):
            lines.append("- none")
        lines.append("")
        lines.append("Struck claims:")
        for struck in dossier.get("struck") or []:
            lines.append("- " + str(struck.get("claim_id")) + ": "
                         + ", ".join(struck.get("reasons") or []))
        if not dossier.get("struck"):
            lines.append("- none")
        lines.append("")
    cross = record.get("cross_examination") or {}
    lines += ["## Cross-examination", ""]
    if cross.get("red_team_round"):
        lines.append("Instant agreement triggered the red-team round.")
        lines.append("")
    for objection in cross.get("records") or []:
        lines.append("- " + str(objection.get("from_dossier"))
                     + " objected to " + str(objection.get("to_dossier"))
                     + " over claims: "
                     + ", ".join(objection.get("claim_ids") or []))
    if not cross.get("records"):
        lines.append("- no objections recorded")
    lines += ["", "## Ranking", "",
              "| dossier | focus score | struck | pairwise wins |",
              "| --- | --- | --- | --- |"]
    for row in record.get("ranking") or []:
        lines.append("| " + str(row.get("dossier_id")) + " | "
                     + str(row.get("focus_score")) + " | "
                     + str(row.get("struck_count")) + " | "
                     + str(row.get("pairwise_wins")) + " |")
    evolution = record.get("evolution") or {}
    lines += ["", "## Evolution round", ""]
    if evolution.get("applied"):
        lines.append("Merged the surviving claims of the top two dossiers "
                     "into dossier " + str(evolution.get("merged_dossier_id"))
                     + " (focus " + str(evolution.get("focus_id")) + ").")
    else:
        lines.append("No merge: " + str(evolution.get("reason")))
    lines += ["", "## Consensus tests", ""]
    for test in ((record.get("consensus") or {}).get("results") or []):
        lines.append("- " + str(test.get("test")) + ": "
                     + ("pass" if test.get("passed") else "FAIL")
                     + " (" + str(test.get("detail")) + ")")
    judge = record.get("judge_swap")
    lines += ["", "## Judge swap", ""]
    if judge:
        lines.append("Judge provider: " + str(judge.get("provider"))
                     + " | judge focus: " + str(judge.get("proposed_focus_id"))
                     + " | judge claims struck: "
                     + str(len(judge.get("struck") or [])))
    else:
        lines.append("No judge was supplied; stability is unestablished.")
    spec = record.get("spec") or {}
    lines += ["", "## Specification and dissent", "",
              "Focus: " + str(spec.get("focus_id"))
              + " | claims carried: " + str(len(spec.get("claims") or [])),
              ""]
    for entry in spec.get("dissent_log") or []:
        lines.append("- " + str(entry.get("agent_id")) + ": "
                     + str(entry.get("objection"))
                     + " [" + str(entry.get("status")) + "]")
    if not spec.get("dissent_log"):
        lines.append("- dissent log empty (reason recorded in the record)")
    lines.append("")
    return "\n".join(lines)
