"""Executable protocol export: an assay plan rendered as a
bench-ready document.

The assay plan artifact is machine-readable; a bench scientist
works from a document. This module renders one plan into a
single Markdown protocol a person can execute and annotate:
purpose and hypotheses, per-candidate materials and controls,
numbered procedure steps, the acceptance criteria as a
checklist with their thresholds, and the plan's decision rule.

The export is a rendering of the plan, nothing more: every
number in it comes from the plan as written, and the footer
repeats the plan's own boundary - executing the protocol is
laboratory work, reagent identities and concentrations must
be verified against local SOPs, and this document does not
replace them. Results return through the assay-results
ingestion path and are graded against the checklist below.
"""


def _hypotheses(plan: dict) -> list:
    """The plan's hypotheses as readable lines."""
    out = []
    for item in plan.get("hypotheses") or []:
        if isinstance(item, dict):
            out.append("- [" + str(item.get("claim_id") or "?")
                       + "] " + str(item.get("text") or ""))
        else:
            out.append("- " + str(item))
    return out


def _criteria_lines(block: dict) -> list:
    """One block's acceptance criteria as checklist lines with
    their machine-checkable thresholds spelled out."""
    out = []
    for criterion in block.get("acceptance_criteria") or []:
        line = ("- [ ] **" + str(criterion.get("criterion"))
                + "**: " + str(criterion.get("rule")))
        check = criterion.get("check")
        if check:
            line += (" (graded on `" + str(check.get("metric"))
                     + "` " + str(check.get("op")) + " "
                     + str(check.get("value")))
            also = check.get("also")
            if also:
                line += (" and `" + str(also.get("metric")) + "` "
                         + str(also.get("op")) + " "
                         + str(also.get("value")))
            line += ")"
        out.append(line)
    return out


def _candidate_section(entry: dict, index: int) -> list:
    """The full bench section for one planned candidate."""
    block = entry.get("assay_block") or {}
    primary = block.get("primary_assay") or {}
    secondary = block.get("secondary_assay") or {}
    controls = block.get("controls") or {}
    lines = ["## Candidate " + str(index) + ": "
             + str(entry.get("candidate_id"))
             + " (" + str(entry.get("modality")) + ")",
             ""]
    structure = entry.get("structure") or {}
    if structure.get("value"):
        lines.append("Structure (" + str(structure.get("format")
                                         or "as recorded") + "): `"
                     + str(structure["value"]) + "`")
        lines.append("")
    lines += ["### Assays", "",
              "1. **Primary: " + str(primary.get("name")) + "**",
              "   - Readout: " + str(primary.get("readout")),
              "   - Purpose: " + str(primary.get("purpose")),
              "2. **Secondary: " + str(secondary.get("name")) + "**",
              "   - Readout: " + str(secondary.get("readout")),
              "   - Purpose: " + str(secondary.get("purpose")), ""]
    counters = block.get("counterscreens") or []
    if counters:
        lines.append("### Counterscreens")
        lines.append("")
        for item in counters:
            lines.append("3. " + str(item))
        lines.append("")
    lines += ["### Controls", ""]
    for name in ("vehicle", "positive", "negative"):
        if controls.get(name):
            lines.append("- **" + name.capitalize() + "**: "
                         + str(controls[name]))
    lines += ["", "### Acceptance criteria (checklist)", ""]
    lines += _criteria_lines(block)
    lines.append("")
    return lines


def export_protocol(plan: dict) -> str:
    """Render one assay plan as an executable Markdown
    protocol. Raises ValueError when the plan names no
    candidates."""
    candidates = (plan or {}).get("candidates") or []
    if not candidates:
        raise ValueError("the assay plan names no candidates "
                         "to write a protocol for")
    conduct = plan.get("conduct") or {}
    lines = ["# Assay protocol: " + str(plan.get("plan_id")),
             "",
             "Target: " + str(plan.get("target") or "")
             + (" | Disease context: " + str(plan.get("disease"))
                if plan.get("disease") else ""),
             "Spec: " + str(plan.get("spec_id") or ""),
             ""]
    hypotheses = _hypotheses(plan)
    if hypotheses:
        lines += ["## Hypotheses under test", ""] + hypotheses + [""]
    for i, entry in enumerate(candidates, start=1):
        lines += _candidate_section(entry, i)
    lines += ["## Conduct", ""]
    if conduct.get("replicates"):
        lines.append("- Replicates: " + str(conduct["replicates"]))
    if conduct.get("blinding"):
        lines.append("- Blinding: " + str(conduct["blinding"]))
    if conduct.get("decision_rule"):
        lines += ["", "## Decision rule", "",
                  str(conduct["decision_rule"]), ""]
    lines += ["## Notes and boundaries", "",
              str(plan.get("note") or ""),
              "",
              "Verify every reagent identity, concentration, "
              "and instrument setting against local SOPs before "
              "starting; this export does not replace them. "
              "Record the positive and negative control "
              "compounds actually used in the results file. "
              "Return results through the assay-grade command; "
              "they are graded against the checklist above, as "
              "written.", ""]
    return "\n".join(lines)
