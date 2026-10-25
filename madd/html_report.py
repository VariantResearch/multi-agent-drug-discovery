"""HTML run report: the bundle as a styled, self-contained page.

Same contents as the markdown report, presented in the project's
synthwave theme (near-black background, neon pink, purple, and cyan,
laser gradient rules - the palette of the owner's other tools), with an
inline SVG score chart drawn by this module. Self-contained means
exactly that: no external fonts, scripts, or images, so a saved
report.html renders identically offline and can be sent as one file.
All bundle text is HTML-escaped before it reaches the page.
"""
from __future__ import annotations

import html

BG = "#0a0a16"
PANEL = "#12122b"
PINK = "#ff71ce"
PURPLE = "#b967ff"
CYAN = "#01cdfe"
TEXT = "#e8e8f2"
DIM = "#9a9ab5"

CSS = """
body { background: BG; color: TEXT; font-family: 'Segoe UI', system-ui, sans-serif;
       margin: 0; padding: 32px; }
h1 { color: PINK; letter-spacing: 2px; margin-bottom: 4px; }
h2 { color: CYAN; letter-spacing: 1px; margin-top: 28px; }
.laser { height: 3px; background: linear-gradient(90deg, PINK, PURPLE, CYAN);
         border: 0; margin: 14px 0; }
.card { background: PANEL; border: 1px solid PURPLE; border-radius: 8px;
        padding: 14px 18px; display: inline-block; margin: 6px 8px 6px 0; }
.card .big { font-size: 28px; color: CYAN; }
.pass { color: #3dff8f; } .fail { color: #ff5470; }
table { border-collapse: collapse; margin-top: 10px; }
th, td { border: 1px solid #2c2c54; padding: 6px 12px; text-align: left; }
th { color: PURPLE; }
.mut { color: DIM; }
""".replace("BG", BG).replace("TEXT", TEXT).replace("PINK", PINK) \
   .replace("PURPLE", PURPLE).replace("CYAN", CYAN).replace("PANEL", PANEL) \
   .replace("DIM", DIM)


def _esc(value) -> str:
    """Escape one bundle value for HTML text content."""
    return html.escape(str(value))


def _score_chart(debate_correct, baseline_correct, case_count) -> str:
    """Inline SVG horizontal bars: debate vs baseline correct calls."""
    total = max(int(case_count or 0), 1)
    width = 420

    def bar(y, label, value, color):
        """One labelled horizontal bar as an SVG fragment."""
        w = int(width * (int(value or 0) / total))
        return ("<text x='0' y='" + str(y + 13) + "' fill='" + TEXT
                + "' font-size='13'>" + _esc(label) + "</text>"
                "<rect x='90' y='" + str(y) + "' width='" + str(w)
                + "' height='16' fill='" + color + "'/>"
                "<text x='" + str(98 + w) + "' y='" + str(y + 13)
                + "' fill='" + TEXT + "' font-size='13'>"
                + _esc(value) + " / " + _esc(total) + "</text>")

    return ("<svg width='560' height='56' xmlns='http://www.w3.org/2000/svg'>"
            + bar(2, "Debate", debate_correct, CYAN)
            + bar(30, "Baseline", baseline_correct, PURPLE) + "</svg>")


def _gate0_html(bundle) -> str:
    """HTML page for a Gate 0 run bundle."""
    debate = bundle.get("debate_score") or {}
    baseline = bundle.get("baseline_score") or {}
    incorrect = set(debate.get("incorrect_calls") or [])
    passed = bundle.get("outcome") == "pass"
    parts = ["<h1>MADD // GATE 0 RUN REPORT</h1>",
             "<div class='mut'>Run " + _esc(bundle.get("run_id")) + "</div>",
             "<hr class='laser'>",
             "<div class='card'><div class='big "
             + ("pass" if passed else "fail") + "'>"
             + ("PASSED" if passed else "DID NOT PASS") + "</div>"
             "<div>the approved thresholds</div></div>",
             "<div class='card'><div class='big'>"
             + _esc(debate.get("correct_calls")) + "</div>"
             "<div>debate calls correct</div></div>",
             "<div class='card'><div class='big'>"
             + _esc(baseline.get("correct_calls")) + "</div>"
             "<div>baseline calls correct</div></div>",
             "<h2>SCORES</h2>",
             _score_chart(debate.get("correct_calls"),
                          baseline.get("correct_calls"),
                          debate.get("case_count")),
             "<h2>THRESHOLDS</h2><table><tr><th>check</th><th>status</th>"
             "<th>detail</th></tr>"]
    for check in (bundle.get("thresholds") or {}).get("checks", []):
        status = str(check.get("status"))
        parts.append("<tr><td>" + _esc(check.get("threshold")) + "</td>"
                     "<td class='" + ("pass" if status == "pass" else "fail")
                     + "'>" + _esc(status) + "</td><td>"
                     + _esc(check.get("detail")) + "</td></tr>")
    parts.append("</table><h2>CASE CALLS</h2><table><tr><th>case</th>"
                 "<th>debate</th><th>baseline</th><th>verdict</th></tr>")
    for case_id in bundle.get("case_ids", []):
        parts.append("<tr><td>" + _esc(case_id) + "</td><td>"
                     + _esc((bundle.get("predictions") or {}).get(case_id))
                     + "</td><td>"
                     + _esc((bundle.get("baseline_predictions") or {}).get(case_id))
                     + "</td><td class='"
                     + ("fail" if case_id in incorrect else "pass") + "'>"
                     + ("wrong" if case_id in incorrect else "correct")
                     + "</td></tr>")
    parts.append("</table>")
    retries = bundle.get("provider_retries") or {}
    if any(retries.values()):
        parts.append("<p class='mut'>Provider retries during the run: "
                     + _esc(retries) + "</p>")
    return "".join(parts)


def _frame_html(bundle) -> str:
    """HTML page for a frame run bundle."""
    record = bundle.get("record") or {}
    spec = record.get("spec") or {}
    parts = ["<h1>MADD // FRAME RUN REPORT</h1>",
             "<div class='mut'>Run " + _esc(bundle.get("run_id"))
             + " | frame " + _esc(bundle.get("frame_id")) + "</div>",
             "<hr class='laser'>",
             "<div class='card'><div class='big'>"
             + _esc(bundle.get("outcome")) + "</div>"
             "<div>outcome | focus " + _esc(spec.get("focus_id")) + "</div></div>",
             "<h2>CONSENSUS TESTS</h2><table><tr><th>test</th><th>result</th>"
             "<th>detail</th></tr>"]
    for test in ((record.get("consensus") or {}).get("results") or []):
        parts.append("<tr><td>" + _esc(test.get("test")) + "</td>"
                     "<td class='" + ("pass" if test.get("passed") else "fail")
                     + "'>" + ("pass" if test.get("passed") else "FAIL")
                     + "</td><td>" + _esc(test.get("detail")) + "</td></tr>")
    parts.append("</table><p class='mut'>Strikes at the evidence call: "
                 + _esc(len(record.get("strike_list") or [])) + "</p>")
    return "".join(parts)


def _design_html(bundle: dict) -> str:
    """HTML body for a Phase 2 design bundle."""
    brief = bundle.get("brief") or {}
    gate = bundle.get("gate_report") or {}
    audits = {a["candidate_id"]: a for a in bundle.get("audits", [])}
    ranking = bundle.get("ranking") or {}
    parts = ["<h1><span class='pink'>MADD</span> // DESIGN "
             + _esc(bundle.get("run_id")) + "</h1><div class='laser'></div>"
             "<p>Target <b>" + _esc(brief.get("target")) + "</b> &middot; "
             + _esc(brief.get("disease")) + " &middot; designer "
             + _esc(bundle.get("designer")) + " &middot; gate <b class='"
             + ("pass" if gate.get("result") == "pass" else "fail") + "'>"
             + _esc(gate.get("result")) + "</b></p>",
             "<h2>RANKED CANDIDATES</h2><table><tr><th>#</th><th>candidate</th>"
             "<th>audited claims</th><th>unverified predictions</th></tr>"]
    cand_by_id = {c.get("candidate_id"): c for c in bundle.get("candidates", [])}
    for i, cid in enumerate(ranking.get("ranked", []), start=1):
        a = audits.get(cid) or {}
        marker = (" <span class='mut'>SYNTHETIC placeholder</span>"
                  if (cand_by_id.get(cid) or {}).get("_synthetic") else "")
        parts.append("<tr><td>" + str(i) + "</td><td>" + _esc(cid) + marker + "</td><td>"
                     + _esc(a.get("audited_load_bearing")) + "</td><td>"
                     + _esc(a.get("unverified_predictions")) + "</td></tr>")
    parts.append("</table><h2>EXCLUDED</h2>")
    if ranking.get("excluded"):
        for ex in ranking["excluded"]:
            parts.append("<p class='mut'>" + _esc(ex.get("candidate_id")) + ": "
                         + _esc("; ".join(ex.get("reasons") or [])) + "</p>")
    else:
        parts.append("<p class='mut'>(none)</p>")
    parts.append("<h2>TOOL RUNS</h2>")
    if bundle.get("tool_runs"):
        for t in bundle["tool_runs"]:
            parts.append("<p class='mut'>" + _esc(t.get("tool")) + ": "
                         + _esc(t.get("status")) + " ("
                         + _esc(len(t.get("outputs") or [])) + " outputs)</p>")
    else:
        parts.append("<p class='mut'>(none)</p>")
    return "".join(parts)


def bundle_to_html(bundle: dict) -> str:
    """Return a complete, self-contained HTML document for a bundle."""
    if bundle.get("kind") == "gate0_run":
        body = _gate0_html(bundle)
    elif bundle.get("kind") == "design_run":
        body = _design_html(bundle)
    else:
        body = _frame_html(bundle)
    return ("<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
            "<title>MADD run report " + _esc(bundle.get("run_id"))
            + "</title><style>" + CSS + "</style></head><body>"
            + body + "</body></html>")
