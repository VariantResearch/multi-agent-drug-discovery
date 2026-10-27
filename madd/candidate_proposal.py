"""Designed-candidate proposal pack.

The companion to the target-selection pack: that document
answers for the choice of target from the public records;
this one answers for the candidates a run designed, from
the run's own frozen bundle, and carries the target-choice
case inside it so the proposal stands alone.

Sections: why this target (the locked brief, the design
constraints, the debate's outcome and strike tally, and the
surviving claims with their sources and supporting quotes -
the evidence the lock rested on, plus the selection pack's
signals when one is supplied); the design run as recorded
(designer, notes including failures, tool runs with their
licences, gate checks, per-candidate audits); one full
section per ranked candidate (production-sheet identity as
computed from the structure, readiness with everything the
sheet names as not specified, every constraint result with
its basis, predicted properties as the designer recorded
them, and a structure depiction for small molecules);
the proposed validation assays from the assay planner; and
the standing limits.

Bundle-faithful throughout, like the manuscript renderer:
statements come from bundle fields, production identity is
computed from the bundle's own structures by the
production module, and nothing is added that the bundle
does not contain. Candidates are computational proposals;
no candidate here has been synthesised or assayed, and the
pack says so.
"""
import json
from pathlib import Path

from .assay import plan_assays
from .production import build_production_sheets
from .proposal import _esc, _fmt, _svg_bars


def _depiction_svg(smiles: str):
    """A 2D structure depiction as SVG via RDKit, or None
    when RDKit or the structure is unavailable."""
    try:
        from rdkit import Chem
        from rdkit.Chem.Draw import rdMolDraw2D
    except Exception:
        return None
    mol = Chem.MolFromSmiles(smiles or "")
    if mol is None:
        return None
    drawer = rdMolDraw2D.MolDraw2DSVG(340, 300)
    rdMolDraw2D.PrepareAndDrawMolecule(drawer, mol)
    drawer.FinishDrawing()
    return drawer.GetDrawingText()


def _selection_context(selection, target_name):
    """The target's entry from a selection proposal pack,
    when one was supplied and names this target."""
    if not selection:
        return None
    wanted = str(target_name or "").strip().lower()
    for entry in selection.get("targets") or []:
        if str(entry.get("target") or "").strip().lower() == wanted:
            return entry
    return None


def build_candidate_proposal(bundle: dict, selection: dict = None,
                             include_assay_plan: bool = True) -> dict:
    """Assemble the candidate proposal record for one
    designed target-run bundle."""
    target = bundle.get("target") or {}
    frame_run = bundle.get("frame_run") or {}
    record = frame_run.get("record") or {}
    design = bundle.get("design") or {}
    brief = design.get("brief") or {}
    spec_claims = (record.get("spec") or {}).get("claims") or []
    strikes = record.get("strike_list") or []
    reasons = {}
    for strike in strikes:
        for reason in strike.get("reasons") or []:
            reasons[reason] = reasons.get(reason, 0) + 1
    sheets = build_production_sheets(design)
    candidates = {c.get("candidate_id"): c
                  for c in design.get("candidates") or []}
    audits = {a.get("candidate_id"): a
              for a in design.get("audits") or []}
    candidate_sections = []
    depictions = {}
    for sheet in sheets:
        candidate = candidates.get(sheet["candidate_id"]) or {}
        identity = sheet.get("identity") or {}
        if identity.get("format") == "smiles":
            svg = _depiction_svg(identity.get("canonical_smiles")
                                 or identity.get("value_as_proposed"))
            if svg:
                depictions[sheet["candidate_id"]] = svg
        candidate_sections.append({
            "sheet": sheet,
            "description": candidate.get("description"),
            "design_tool": candidate.get("design_tool"),
            "predicted_properties":
                candidate.get("predicted_properties") or [],
            "constraint_results":
                candidate.get("constraint_results") or [],
            "audit": audits.get(sheet["candidate_id"]),
            "depiction_file": (
                "structure-" + str(sheet["candidate_id"]) + ".svg"
                if sheet["candidate_id"] in depictions else None),
        })
    assay_plan = None
    if include_assay_plan and design:
        try:
            assay_plan = plan_assays(
                design, top_n=max(len(sheets), 1))
        except Exception:
            assay_plan = None
    return {
        "artifact_type": "candidate_proposal",
        "schema_version": "0.1.0",
        "run_id": bundle.get("run_id"),
        "bundle_outcome": bundle.get("outcome"),
        "mode": bundle.get("mode"),
        "target": target,
        "why_this_target": {
            "brief_question": brief.get("question"),
            "design_constraints": brief.get("design_constraints") or [],
            "evidence_constraints": [
                (c.get("text") if isinstance(c, dict) else c)
                for c in brief.get("evidence_constraints") or []],
            "debate_outcome": record.get("outcome"),
            "claims_survived": len(spec_claims),
            "claims": spec_claims,
            "strikes": len(strikes),
            "strike_reasons": reasons,
            "selection_context": _selection_context(
                selection, target.get("name")),
        },
        "design_run": {
            "designer": design.get("designer"),
            "designer_notes": design.get("designer_notes") or [],
            "tool_runs": design.get("tool_runs") or [],
            "gate_report": design.get("gate_report") or {},
        },
        "candidates": candidate_sections,
        "assay_plan": assay_plan,
        "depictions": depictions,
        "standing_note": (
            "Every candidate in this pack is a computational "
            "proposal from a recorded run. None has been "
            "synthesised or assayed. Predicted properties are "
            "the designing model's own statements, carried "
            "with their recorded basis; computed identity "
            "comes from the structure itself. Production "
            "readiness follows the production sheet: a sheet "
            "marked not ready names what is still unspecified, "
            "and nothing here fills those gaps in."),
    }


def _mw_chart(proposal: dict) -> str:
    """Molecular-weight bars for the small-molecule
    candidates, from the computed production identity."""
    rows = []
    for section in proposal["candidates"]:
        identity = (section["sheet"].get("identity") or {})
        if identity.get("molecular_weight"):
            rows.append((section["sheet"]["candidate_id"],
                         identity["molecular_weight"]))
    if not rows:
        return ""
    return _svg_bars("Computed molecular weight (Da)", rows)


def _candidate_lines(section):
    """Markdown lines for one candidate's full section."""
    sheet = section["sheet"]
    identity = sheet.get("identity") or {}
    lines = ["## Rank " + str(sheet.get("rank")) + ": "
             + str(sheet["candidate_id"]), ""]
    lines.append("- Modality: " + str(sheet.get("modality"))
                 + " | design tool: " + str(sheet.get("design_tool"))
                 + " | production ready: "
                 + ("YES" if sheet.get("production_ready") else "NO")
                 + " | route: " + str(sheet.get("production_route")))
    if identity.get("format") == "smiles":
        lines.append("- Structure (as proposed): "
                     + str(identity.get("value_as_proposed")))
        lines.append("- Canonical SMILES: "
                     + str(identity.get("canonical_smiles")))
        lines.append("- Formula: "
                     + str(identity.get("molecular_formula"))
                     + " | molecular weight: "
                     + _fmt(identity.get("molecular_weight"))
                     + " | InChIKey: "
                     + str(identity.get("inchikey"))
                     + " | unspecified stereocenters: "
                     + str(identity.get("unspecified_stereocenters")))
    elif identity.get("format") == "sequence":
        lines.append("- Sequence: "
                     + str(identity.get("value_as_proposed"))
                     + " | length: " + str(identity.get("length"))
                     + " | composition: "
                     + str(identity.get("composition"))
                     + " | alphabet check: "
                     + str(identity.get("alphabet_check")))
    if section.get("depiction_file"):
        lines.append("- Depiction: " + section["depiction_file"])
    if sheet.get("not_specified"):
        lines.append("- Not specified (must be settled before "
                     "production):")
        lines.extend("  - " + str(item)
                     for item in sheet["not_specified"])
    if section.get("description"):
        lines += ["", str(section["description"]), ""]
    props = section.get("predicted_properties") or []
    if props:
        lines.append("Predicted properties (designer's own, "
                     "with recorded basis):")
        for prop in props:
            if isinstance(prop, dict):
                lines.append("- " + str(prop.get("name")) + ": "
                             + str(prop.get("value"))
                             + " [" + str(prop.get("basis")) + "]")
            else:
                lines.append("- " + str(prop))
        lines.append("")
    results = section.get("constraint_results") or []
    if results:
        lines.append("Constraint results:")
        for result in results:
            lines.append("- [" + str(result.get("status")) + "] "
                         + str(result.get("constraint"))
                         + " Basis: " + str(result.get("basis")))
        lines.append("")
    audit = section.get("audit") or {}
    if audit:
        lines.append("Audit: unverified predictions "
                     + str(audit.get("unverified_predictions"))
                     + ", unknown constraints "
                     + str(audit.get("unknown_constraints"))
                     + ", failed constraints "
                     + str(len(audit.get("failed_constraints")
                               or []))
                     + ", hard fail "
                     + str(audit.get("hard_fail")) + ".")
        lines.append("")
    return lines


def render_markdown(proposal: dict) -> str:
    """The candidate proposal as Markdown."""
    target = proposal["target"]
    why = proposal["why_this_target"]
    lines = [
        "# Drug design candidate proposal: "
        + str(target.get("name")) + " ("
        + str(target.get("target")) + ") in "
        + str(target.get("disease")),
        "",
        "Run: " + str(proposal["run_id"]) + " | outcome: "
        + str(proposal["bundle_outcome"]) + " | mode: "
        + str(proposal["mode"]),
        "",
        "## Why this target",
        "",
        "Brief: " + str(why.get("brief_question")),
        "",
    ]
    for constraint in why.get("design_constraints") or []:
        lines.append("- Design constraint: " + str(constraint))
    context = why.get("selection_context")
    if context:
        signals = context.get("signals") or {}
        lines += ["",
                  "Selection-pack context (live public records "
                  "at selection time): association "
                  + _fmt(signals.get("association_score"))
                  + ", mechanisms "
                  + _fmt(signals.get("known_mechanisms"))
                  + ", bioactivity records "
                  + _fmt(signals.get("bioactivity_records"))
                  + ", selection verdict "
                  + str(context.get("verdict")) + ". "
                  + str(context.get("whitespace") or ""), ""]
    lines += ["Debate outcome: " + str(why.get("debate_outcome"))
              + " | claims survived: "
              + str(why.get("claims_survived"))
              + " | claims struck: " + str(why.get("strikes"))
              + " " + str(why.get("strike_reasons")), "",
              "Surviving claims the lock rested on:", ""]
    for claim in why.get("claims") or []:
        lines.append("- [" + str(claim.get("claim_id")) + "] "
                     + str(claim.get("text")) + " (source: "
                     + str(claim.get("identifier_type")) + " "
                     + str(claim.get("source_identifier")) + ")")
        if claim.get("supporting_quote"):
            lines.append("  Quote: " + str(claim["supporting_quote"]))
    lines += ["", "Evidence constraints carried into the brief:", ""]
    lines.extend("- " + str(c)
                 for c in why.get("evidence_constraints") or [])
    design = proposal["design_run"]
    lines += ["", "## The design run", "",
              "Designer: " + str(design.get("designer")), ""]
    for note in design.get("designer_notes") or []:
        lines.append("- Designer note: " + str(note))
    for tool_run in design.get("tool_runs") or []:
        lines.append("- Tool run: " + str(tool_run.get("tool"))
                     + " (" + str(tool_run.get("kind")) + ") "
                     + str(tool_run.get("status"))
                     + ", licence "
                     + str((tool_run.get("license") or {})
                           .get("license")))
    gate = design.get("gate_report") or {}
    lines.append("- Design gate: " + str(gate.get("result")))
    for check in gate.get("checks") or []:
        lines.append("  - [" + str(check.get("status")) + "] "
                     + str(check.get("name")) + ": "
                     + str(check.get("detail")))
    chart = _mw_chart(proposal)
    if chart:
        lines += ["", "## Computed molecular weights", "",
                  "![Molecular weights](chart-molecular-weight.svg)",
                  ""]
    lines += ["", "## Candidates", ""]
    for section in proposal["candidates"]:
        lines.extend(_candidate_lines(section))
    plan = proposal.get("assay_plan")
    if plan:
        lines += ["## Proposed validation (assay plan)", "",
                  "Plan: " + str(plan.get("plan_id"))
                  + ". Hypotheses and criteria are the plan's "
                  "own; nothing here has been run.", ""]
        for block in plan.get("candidates") or []:
            assay_block = block.get("assay_block") or {}
            assay_names = [
                (assay_block.get(key) or {}).get("name")
                for key in ("primary_assay", "secondary_assay")]
            criteria = [(c.get("criterion") or c.get("name"))
                        if isinstance(c, dict) else str(c)
                        for c in assay_block.get(
                            "acceptance_criteria") or []]
            criteria = [c for c in criteria if c]
            lines.append("- " + str(block.get("candidate_id"))
                         + " (" + str(block.get("modality")) + ")"
                         + ": assays "
                         + ", ".join(n for n in assay_names if n)
                         + " | criteria "
                         + ", ".join(criteria))
        lines.append("")
    lines += ["## Standing note", "", proposal["standing_note"]]
    return "\n".join(lines) + "\n"


def render_html(proposal: dict) -> str:
    """The candidate proposal as one HTML page with charts
    and depictions inlined."""
    markdown = render_markdown(proposal)
    body = []
    for line in markdown.splitlines():
        if line.startswith("# "):
            body.append("<h1>" + _esc(line[2:]) + "</h1>")
        elif line.startswith("## "):
            body.append("<h2>" + _esc(line[3:]) + "</h2>")
        elif line.startswith("- "):
            body.append("<div>" + _esc(line[2:]) + "</div>")
        elif line.startswith("!["):
            continue
        elif line.strip():
            body.append("<div>" + _esc(line) + "</div>")
    chart = _mw_chart(proposal)
    if chart:
        body.append('<div class="panel">' + chart + "</div>")
    for candidate_id, svg in (proposal.get("depictions")
                              or {}).items():
        body.append('<div class="panel"><h3>' + _esc(candidate_id)
                    + "</h3>" + svg + "</div>")
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>Candidate proposal: "
        + _esc((proposal["target"] or {}).get("name"))
        + "</title><style>"
        "body{background:#0a0a16;color:#e8e8f2;font-family:monospace;"
        "margin:24px} .panel{border:1px solid #b967ff;padding:16px;"
        "margin:14px 0} h1{color:#ff71ce} h2{color:#01cdfe} "
        "h3{color:#b967ff}</style></head><body>"
        + "".join(body) + "</body></html>")


def write_pack(proposal: dict, out_dir) -> list:
    """Write the pack: candidate-proposal.json/.md/.html,
    the MW chart, and per-candidate depiction SVGs."""
    folder = Path(out_dir)
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    chart = _mw_chart(proposal)
    if chart:
        path = folder / "chart-molecular-weight.svg"
        path.write_text(chart, encoding="utf-8")
        written.append(path)
    for candidate_id, svg in (proposal.get("depictions")
                              or {}).items():
        path = folder / ("structure-" + str(candidate_id) + ".svg")
        path.write_text(svg, encoding="utf-8")
        written.append(path)
    record = {k: v for k, v in proposal.items() if k != "depictions"}
    for name, content in (
            ("candidate-proposal.json",
             json.dumps(record, indent=2)),
            ("candidate-proposal.md", render_markdown(proposal)),
            ("candidate-proposal.html", render_html(proposal))):
        path = folder / name
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written
