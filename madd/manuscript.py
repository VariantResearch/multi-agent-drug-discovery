"""Bundle-faithful manuscript drafts.

A run bundle is a record; a manuscript is a claim about the
record, and manuscripts are where numbers quietly change.
This renderer makes that structurally hard: the draft is
assembled from statements, each statement is rendered from
named bundle fields and carries the field path it came from,
and nothing enters the text that a statement did not bring.
The sections are the shape of a short computational paper:
title, abstract, background from the frame and the locked
brief, methods from the run's own configuration and audit
trail, results from the debate record and the design stage,
limitations stated as facts about the bundle's scope, and
references as the surviving claims' sources, deduplicated.

The draft describes a computational run. It says so, and it
says what the bundle does not contain: no synthesis, no
assay, no clinical result appears in a bundle, so none
appears here.
"""


def _statements(bundle: dict):
    """Yield (section, text, source_path) statements rendered
    strictly from the bundle's fields."""
    target = bundle.get("target") or {}
    name = target.get("name") or "the target"
    frame_run = bundle.get("frame_run") or {}
    record = frame_run.get("record") or {}
    design = bundle.get("design") or {}
    brief = design.get("brief") or {}
    yield ("title",
           "Computational design against " + str(name)
           + ": a multi-agent, evidence-audited target run",
           "target.name")
    yield ("abstract",
           "Outcome: " + str(bundle.get("outcome"))
           + ". Debate outcome: " + str(record.get("outcome"))
           + ". Protocol mode: " + str(bundle.get("mode")) + ".",
           "outcome, frame_run.record.outcome, mode")
    spec = record.get("spec") or {}
    if brief.get("question"):
        yield ("background", str(brief["question"]), "design.brief.question")
    for constraint in brief.get("evidence_constraints") or []:
        text = (constraint.get("text") if isinstance(constraint, dict)
                else constraint)
        yield ("background",
               "Evidence constraint: " + str(text),
               "design.brief.evidence_constraints")
    providers = record.get("providers") or []
    if providers:
        names = ", ".join(
            str(p.get("name")) + " (" + str(p.get("model_version")) + ")"
            if isinstance(p, dict) else str(p) for p in providers)
        yield ("methods", "Debate providers: " + names + ".",
               "frame_run.record.providers")
    claims = spec.get("claims") or []
    strikes = record.get("strike_list") or []
    yield ("methods",
           "Surviving claims in the locked specification: "
           + str(len(claims)) + ". Claims struck in audit: "
           + str(len(strikes)) + ".",
           "frame_run.record.spec.claims, frame_run.record.strike_list")
    if design.get("designer"):
        yield ("methods", "Designer: " + str(design["designer"]) + ".",
               "design.designer")
    if record.get("outcome"):
        yield ("results",
               "The debate closed with outcome "
               + str(record["outcome"]) + " on focus "
               + str(target.get("focus_id")) + ".",
               "frame_run.record.outcome, target.focus_id")
    reasons = {}
    for strike in strikes:
        for reason in strike.get("reasons") or []:
            reasons[reason] = reasons.get(reason, 0) + 1
    for reason, count in sorted(reasons.items()):
        yield ("results",
               "Strikes for " + str(reason) + ": " + str(count) + ".",
               "frame_run.record.strike_list")
    landscape = bundle.get("trial_landscape") or {}
    if landscape.get("total_trials") is not None:
        yield ("results",
               "Registered trials matching the disease query: "
               + str(landscape["total_trials"]) + ".",
               "trial_landscape.total_trials")
    candidates = {c.get("candidate_id"): c
                  for c in design.get("candidates") or []}
    ranked = (design.get("ranking") or {}).get("ranked") or []
    for candidate_id in ranked:
        candidate = candidates.get(candidate_id) or {}
        props = candidate.get("predicted_properties") or {}
        if isinstance(props, list):
            pairs = [(p.get("name"), p.get("value"))
                     for p in props if isinstance(p, dict)]
        else:
            pairs = list(props.items())
        rendered = ", ".join(str(k) + " " + str(v)
                             for k, v in sorted(pairs, key=lambda p: str(p[0])))
        yield ("results",
               "Candidate " + str(candidate_id) + " ("
               + str(candidate.get("modality")) + "): "
               + (rendered or "no recorded properties") + ".",
               "design.candidates, design.ranking.ranked")
    gate = design.get("gate_report") or {}
    if gate:
        yield ("results",
               "Design gate: " + str(gate.get("result")) + " ("
               + str(len(gate.get("checks") or [])) + " checks).",
               "design.gate_report")
    yield ("limitations",
           "This draft reports a computational run only. The "
           "bundle records no synthesis, assay, or clinical "
           "results, and no candidate named here has been made "
           "or tested.",
           "bundle scope (design and frame_run sections only)")
    seen = set()
    for claim in claims:
        identifier = claim.get("source_identifier")
        if not identifier or identifier in seen:
            continue
        seen.add(identifier)
        yield ("references",
               str(claim.get("identifier_type") or "source").upper()
               + " " + str(identifier),
               "frame_run.record.spec.claims")


_SECTIONS = ["title", "abstract", "background", "methods",
             "results", "limitations", "references"]
_HEADINGS = {"title": None, "abstract": "Abstract",
             "background": "Background", "methods": "Methods",
             "results": "Results", "limitations": "Limitations",
             "references": "References"}


def build_manuscript(bundle: dict) -> dict:
    """Render the manuscript draft for a target-run bundle.

    Returns the markdown plus the statement list, so a reader
    (or a test) can trace every sentence to its bundle field.
    """
    statements = [{"section": section, "text": text, "source": source}
                  for section, text, source in _statements(bundle)]
    lines = []
    for section in _SECTIONS:
        texts = [s["text"] for s in statements if s["section"] == section]
        if not texts:
            continue
        if section == "title":
            lines.append("# " + texts[0])
        else:
            lines.append("")
            lines.append("## " + _HEADINGS[section])
            lines.append("")
            if section == "references":
                lines.extend("- " + t for t in texts)
            else:
                lines.extend(texts)
    return {
        "artifact_type": "manuscript_draft",
        "schema_version": "0.1.0",
        "bundle_run_id": bundle.get("run_id"),
        "markdown": "\n".join(lines) + "\n",
        "statements": statements,
        "faithfulness": ("every statement in this draft was "
                         "rendered from the bundle field named "
                         "in its source; no other content was "
                         "admitted"),
    }
