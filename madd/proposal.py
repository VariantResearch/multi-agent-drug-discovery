"""Target-selection proposal pack.

Before MADD designs anything, someone has to answer for the
choice of target: what the recorded evidence says for each
candidate, where each fits the desired outcome and where it
does not, and what has already happened when the system ran
it. This module assembles that answer from the records the
system already trusts, and nothing else:

- the scout's live Open Targets and ChEMBL signals, with the
  datatype breakdown (association, literature, genetics,
  mechanisms, bioactivity volume) and its whitespace read;
- the ClinicalTrials.gov landscape for the disease, with a
  per-target intervention-mention count;
- the run record itself: every finished target run for the
  name, its debate outcome, strike tally by reason, design
  gate, and, for designed runs, the locked brief's evidence
  constraints verbatim.

The fit verdict per target is mechanical under conventions
declared in the pack itself: a target the debate locked and
designed is FIT on its recorded framing; one the debate
declined is DOES NOT FIT as framed; one never debated is
graded FIT FOR DEBATE, PARTIAL, WEAK, or UNESTABLISHED from
its association and whitespace alone, and the pack says
plainly that undated targets are proposals, not judgments.
Charts are generated from the same numbers (inline SVG, no
dependencies), so a figure can disagree with the text only
if the text disagrees with the records.
"""
import json
import math
from pathlib import Path

from .run_memory import _bundle_files
from .scout import scout_targets
from .trials import landscape as trial_landscape

VERDICT_CONVENTIONS = [
    "FIT: a recorded run for this target locked in debate "
    "and passed the design gate on the framing recorded in "
    "its bundle.",
    "DOES NOT FIT AS FRAMED: every recorded run for this "
    "target ended no_go; the debate declined to lock it.",
    "FIT FOR DEBATE: never debated; association at or above "
    "0.2 and comparatively open whitespace.",
    "PARTIAL FIT: never debated; association recorded but "
    "the whitespace is occupied, so differentiation is "
    "unproven.",
    "WEAK FIT: never debated; association below 0.2 on "
    "current records.",
    "UNESTABLISHED: no Open Targets association recorded "
    "for the pair, or the target did not resolve.",
]


def _run_records(runs_dir, target_name):
    """Every finished target run for one name, reduced to
    the fields the pack reports."""
    records = []
    wanted = str(target_name).strip().lower()
    for path in _bundle_files(runs_dir):
        try:
            bundle = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            continue
        if bundle.get("kind") != "target_run":
            continue
        target = bundle.get("target") or {}
        names = {str(target.get("name") or "").lower(),
                 str(target.get("target") or "").lower()}
        if wanted not in names:
            continue
        record = (bundle.get("frame_run") or {}).get("record") or {}
        design = bundle.get("design") or {}
        reasons = {}
        for strike in record.get("strike_list") or []:
            for reason in strike.get("reasons") or []:
                reasons[reason] = reasons.get(reason, 0) + 1
        brief = design.get("brief") or {}
        records.append({
            "run_id": bundle.get("run_id"),
            "created_utc": (bundle.get("created_utc")
                            or design.get("created_utc")),
            "outcome": bundle.get("outcome"),
            "debate_outcome": record.get("outcome"),
            "strikes": len(record.get("strike_list") or []),
            "strike_reasons": reasons,
            "design_gate": (design.get("gate_report") or {}).get("result"),
            "ranked_candidates": len(
                (design.get("ranking") or {}).get("ranked") or []),
            "brief_question": brief.get("question"),
            "evidence_constraints": [
                (c.get("text") if isinstance(c, dict) else c)
                for c in brief.get("evidence_constraints") or []],
        })
    return records


def _verdict(entry, runs):
    """The mechanical fit verdict for one target, from its
    scout entry and run record, under VERDICT_CONVENTIONS."""
    signals = entry.get("signals") or {}
    score = signals.get("association_score")
    if runs:
        if any(r["outcome"] == "designed" for r in runs):
            return "FIT"
        if all(r["outcome"] == "no_go" for r in runs):
            return "DOES NOT FIT AS FRAMED"
        return "PARTIAL FIT"
    if score is None:
        return "UNESTABLISHED"
    if score >= 0.2 and (signals.get("known_mechanisms") or 0) == 0:
        return "FIT FOR DEBATE"
    if score >= 0.2:
        return "PARTIAL FIT"
    return "WEAK FIT"


def build_proposal(disease, desired_outcome, target_names,
                   runs_dir="runs", scout_fn=None, trials_fn=None,
                   queried_on=None) -> dict:
    """Assemble the proposal record for a slate of targets.

    Live sources are injectable for testing; by default the
    real scout and trial landscape run.
    """
    scout_fn = scout_fn or scout_targets
    trials_fn = trials_fn or trial_landscape
    scout = scout_fn(disease, list(target_names))
    landscape = trials_fn(disease, focus_terms=list(target_names),
                          queried_on=queried_on)
    focus_counts = {f.get("term"): f.get("trials")
                    for f in landscape.get("focus") or []}
    targets = []
    for entry in scout.get("candidates") or []:
        name = entry.get("target_input")
        runs = _run_records(runs_dir, name)
        targets.append({
            "target": name,
            "resolved": entry.get("resolved"),
            "signals": entry.get("signals"),
            "whitespace": entry.get("whitespace"),
            "problems": entry.get("problems"),
            "trial_mentions": focus_counts.get(name),
            "runs": runs,
            "verdict": _verdict(entry, runs),
        })
    return {
        "artifact_type": "target_selection_proposal",
        "schema_version": "0.1.0",
        "disease": disease,
        "disease_resolved": scout.get("disease_resolved"),
        "desired_outcome": desired_outcome,
        "queried_on": queried_on,
        "trial_landscape": {
            "total_trials": landscape.get("total_trials"),
            "sample": landscape.get("sample"),
            "note": landscape.get("note"),
        },
        "targets": targets,
        "verdict_conventions": VERDICT_CONVENTIONS,
        "sources": ["Open Targets Platform", "ChEMBL",
                    "ClinicalTrials.gov", "MADD run bundles"],
        "standing_note": (
            "No target is locked in by this pack. Verdicts are "
            "mechanical readings of the cited records under "
            "the conventions above; a FIT FOR DEBATE target "
            "has not been judged by a debate, and a designed "
            "run's candidates are computational only, never "
            "synthesised or assayed."),
    }


# ------------------------------------------------------------
# Charts (inline SVG, standard library only)

_COLORS = ["#01cdfe", "#b967ff", "#ff71ce", "#3dff8f", "#ffd319",
           "#ff8a5c"]


def _svg_bars(title, rows, log_scale=False, note=""):
    """A horizontal bar chart as an SVG string. rows are
    (label, value) pairs; None values render as 'no record'."""
    width, row_h, label_w = 720, 30, 170
    height = 44 + row_h * max(len(rows), 1) + 18
    values = [v for _, v in rows if isinstance(v, (int, float))]
    if log_scale:
        scale_max = max((math.log10(v + 1) for v in values),
                        default=1.0) or 1.0
    else:
        scale_max = max(values, default=1.0) or 1.0
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="'
        + str(width) + '" height="' + str(height)
        + '" font-family="monospace" font-size="13">',
        '<rect width="100%" height="100%" fill="#0a0a16"/>',
        '<text x="10" y="24" fill="#e8e8f2" font-size="15">'
        + _esc(title) + "</text>",
    ]
    for i, (label, value) in enumerate(rows):
        y = 44 + i * row_h
        color = _COLORS[i % len(_COLORS)]
        parts.append('<text x="10" y="' + str(y + 15)
                     + '" fill="#9a9ab5">' + _esc(str(label))
                     + "</text>")
        if isinstance(value, (int, float)):
            span = (math.log10(value + 1) if log_scale else value)
            bar_w = max(2.0, (width - label_w - 110)
                        * span / scale_max)
            parts.append('<rect x="' + str(label_w) + '" y="'
                         + str(y) + '" width="' + format(bar_w, ".1f")
                         + '" height="18" fill="' + color + '"/>')
            parts.append('<text x="' + str(label_w + bar_w + 8)
                         + '" y="' + str(y + 15)
                         + '" fill="#e8e8f2">'
                         + _esc(_fmt(value)) + "</text>")
        else:
            parts.append('<text x="' + str(label_w) + '" y="'
                         + str(y + 15) + '" fill="#9a9ab5">'
                         "no record</text>")
    if note:
        parts.append('<text x="10" y="' + str(height - 4)
                     + '" fill="#9a9ab5" font-size="11">'
                     + _esc(note) + "</text>")
    parts.append("</svg>")
    return "\n".join(parts)


def _esc(text):
    """Escape the three characters SVG text cannot carry raw."""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _fmt(value):
    """Compact number formatting for chart labels."""
    if isinstance(value, float):
        return format(value, ".4g")
    return str(value)


def charts_for(proposal: dict) -> dict:
    """The pack's charts, keyed by filename stem."""
    targets = proposal["targets"]
    association = [(t["target"],
                    (t["signals"] or {}).get("association_score"))
                   for t in targets]
    bioactivity = [(t["target"],
                    (t["signals"] or {}).get("bioactivity_records"))
                   for t in targets]
    mentions = [(t["target"], t.get("trial_mentions"))
                for t in targets]
    return {
        "chart-association.svg": _svg_bars(
            "Open Targets association score (0 to 1)", association),
        "chart-bioactivity.svg": _svg_bars(
            "ChEMBL bioactivity records (log scale)", bioactivity,
            log_scale=True),
        "chart-trial-mentions.svg": _svg_bars(
            "ClinicalTrials.gov intervention mentions of the "
            "target name", mentions),
    }


# ------------------------------------------------------------
# Renders

def _target_lines(t, chart_refs):
    """Markdown lines for one target's full breakdown."""
    signals = t["signals"] or {}
    lines = ["## " + str(t["target"]) + " - verdict: " + t["verdict"],
             ""]
    resolved = t.get("resolved") or {}
    if resolved:
        lines.append("- Resolved: " + str(resolved.get("name"))
                     + " (" + str(resolved.get("ensembl_id"))
                     + ", ChEMBL " + str(resolved.get("chembl_id"))
                     + ")")
    lines.append("- Association score (Open Targets): "
                 + _fmt(signals.get("association_score")))
    lines.append("- Literature component: "
                 + _fmt(signals.get("literature_score")))
    lines.append("- Genetic association component: "
                 + _fmt(signals.get("genetic_association_score")))
    lines.append("- Known drug mechanisms (ChEMBL): "
                 + _fmt(signals.get("known_mechanisms")))
    lines.append("- Bioactivity records (ChEMBL): "
                 + _fmt(signals.get("bioactivity_records")))
    lines.append("- Whitespace read: " + str(t.get("whitespace")))
    lines.append("- Trial mentions of the target name "
                 "(ClinicalTrials.gov interventions): "
                 + _fmt(t.get("trial_mentions")))
    for problem in t.get("problems") or []:
        lines.append("- Recorded problem: " + str(problem))
    lines.append("")
    if t["runs"]:
        lines.append("### Run record")
        lines.append("")
        for run in t["runs"]:
            lines.append("- Run " + str(run["run_id"])
                         + ": outcome " + str(run["outcome"])
                         + ", debate " + str(run["debate_outcome"])
                         + ", strikes " + str(run["strikes"])
                         + " " + str(run["strike_reasons"])
                         + ", design gate "
                         + str(run["design_gate"])
                         + ", ranked candidates "
                         + str(run["ranked_candidates"]))
            if run.get("brief_question"):
                lines.append("  Brief: " + str(run["brief_question"]))
            for constraint in run.get("evidence_constraints") or []:
                lines.append("  Evidence constraint: "
                             + str(constraint))
        lines.append("")
    else:
        lines.append("No recorded run for this target: its "
                     "verdict is a proposal-stage reading of "
                     "the scout and registry records only.")
        lines.append("")
    return lines


def render_markdown(proposal: dict) -> str:
    """The proposal pack as Markdown, charts referenced as
    sibling SVG files."""
    lines = [
        "# Drug design candidate proposal: target selection for "
        + str(proposal["disease"]),
        "",
        "Desired outcome: " + str(proposal["desired_outcome"]),
        "Queried on: " + str(proposal.get("queried_on")),
        "Disease resolved as: "
        + str((proposal.get("disease_resolved") or {}).get("name")),
        "Registered trials for the disease: "
        + _fmt((proposal.get("trial_landscape") or {})
               .get("total_trials")),
        "",
        "## Verdict summary",
        "",
        "| Target | Association | Mechanisms | Bioactivities "
        "| Trial mentions | Runs | Verdict |",
        "|---|---|---|---|---|---|---|",
    ]
    for t in proposal["targets"]:
        signals = t["signals"] or {}
        lines.append(
            "| " + str(t["target"]) + " | "
            + _fmt(signals.get("association_score")) + " | "
            + _fmt(signals.get("known_mechanisms")) + " | "
            + _fmt(signals.get("bioactivity_records")) + " | "
            + _fmt(t.get("trial_mentions")) + " | "
            + str(len(t["runs"])) + " | " + t["verdict"] + " |")
    lines += ["", "## Charts", "",
              "![Association scores](chart-association.svg)",
              "",
              "![Bioactivity records](chart-bioactivity.svg)",
              "",
              "![Trial mentions](chart-trial-mentions.svg)",
              "", "## Target breakdowns", ""]
    for t in proposal["targets"]:
        lines.extend(_target_lines(t, None))
    lines += ["## Verdict conventions", ""]
    lines.extend("- " + c for c in proposal["verdict_conventions"])
    lines += ["", "## Standing note", "",
              proposal["standing_note"], "",
              "Sources: " + ", ".join(proposal["sources"]) + "."]
    return "\n".join(lines) + "\n"


def render_html(proposal: dict) -> str:
    """The proposal pack as one HTML page: the Markdown
    content rendered simply, charts inlined as SVG."""
    charts = charts_for(proposal)
    body = ['<div class="panel"><h2>VERDICT SUMMARY</h2><table>',
            "<tr><th>Target</th><th>Association</th>"
            "<th>Mechanisms</th><th>Bioactivities</th>"
            "<th>Trial mentions</th><th>Runs</th>"
            "<th>Verdict</th></tr>"]
    for t in proposal["targets"]:
        signals = t["signals"] or {}
        body.append(
            "<tr><td>" + _esc(t["target"]) + "</td><td>"
            + _esc(_fmt(signals.get("association_score")))
            + "</td><td>"
            + _esc(_fmt(signals.get("known_mechanisms")))
            + "</td><td>"
            + _esc(_fmt(signals.get("bioactivity_records")))
            + "</td><td>" + _esc(_fmt(t.get("trial_mentions")))
            + "</td><td>" + str(len(t["runs"])) + "</td><td>"
            + _esc(t["verdict"]) + "</td></tr>")
    body.append("</table></div>")
    for stem in ("chart-association.svg", "chart-bioactivity.svg",
                 "chart-trial-mentions.svg"):
        body.append('<div class="panel">' + charts[stem] + "</div>")
    for t in proposal["targets"]:
        body.append('<div class="panel"><h2>'
                    + _esc(str(t["target"]).upper()) + " - "
                    + _esc(t["verdict"]) + "</h2>")
        for line in _target_lines(t, None)[2:]:
            if line.startswith("- "):
                body.append("<div>" + _esc(line[2:]) + "</div>")
            elif line.startswith("### "):
                body.append("<h3>" + _esc(line[4:]) + "</h3>")
            elif line.strip():
                body.append("<div>" + _esc(line) + "</div>")
        body.append("</div>")
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>Target selection proposal: "
        + _esc(proposal["disease"]) + "</title><style>"
        "body{background:#0a0a16;color:#e8e8f2;font-family:monospace;"
        "margin:24px} .panel{border:1px solid #b967ff;padding:16px;"
        "margin:14px 0} h1{color:#ff71ce} h2{color:#01cdfe} "
        "table{border-collapse:collapse} td,th{border:1px solid "
        "#2a2a4a;padding:5px 11px;text-align:left} th{color:#b967ff}"
        "</style></head><body><h1>TARGET SELECTION PROPOSAL // "
        + _esc(str(proposal["disease"]).upper()) + "</h1>"
        "<div>Desired outcome: "
        + _esc(proposal["desired_outcome"]) + "</div>"
        "<div>Queried on: " + _esc(proposal.get("queried_on"))
        + " | registered trials for the disease: "
        + _esc(_fmt((proposal.get("trial_landscape") or {})
                     .get("total_trials"))) + "</div>"
        + "".join(body)
        + '<div class="panel"><h2>STANDING NOTE</h2><div>'
        + _esc(proposal["standing_note"]) + "</div></div>"
        "</body></html>")


def write_pack(proposal: dict, out_dir) -> list:
    """Write the pack: proposal.json, proposal.md,
    proposal.html, and the chart SVGs. Returns the paths."""
    folder = Path(out_dir)
    folder.mkdir(parents=True, exist_ok=True)
    charts = charts_for(proposal)
    written = []
    for name, svg in charts.items():
        path = folder / name
        path.write_text(svg, encoding="utf-8")
        written.append(path)
    for name, content in (
            ("proposal.json", json.dumps(proposal, indent=2)),
            ("proposal.md", render_markdown(proposal)),
            ("proposal.html", render_html(proposal))):
        path = folder / name
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written
