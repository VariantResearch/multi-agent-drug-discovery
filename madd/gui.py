"""MADD Console: the retro cyberpunk web interface.

A local web GUI over the same machinery the CLI drives, served by
the standard library's HTTP server - no new dependencies, nothing
leaves the machine. One page, four panels:

- RUN CONTROL: a config path, with Check, Dry run, and Run Gate 0
  buttons, and a live console that renders the runner's progress
  events as a run happens.
- GATE 0 SCOREBOARD: dataset validation state and the case list.
- RUN LIBRARY: every bundle in the runs directory; click one for its
  scores, threshold checks, and case calls, with links to its styled
  HTML report and per-case debate transcripts. A completed design
  (a design run, or a target run whose design stage ran) also shows
  a fully rendered 3D structural view: the ranked drug candidate as
  a WebGL model (3Dmol.js, vendored under madd/assets/, geometry
  generated from its SMILES by madd/structure3d.py) beside the
  receptor structure on file for the target when one is shipped -
  today the AlphaFold predicted model for MTCH2, labelled
  predicted, shown in its own view because no run docks the
  candidate and no binding pose is claimed. If the WebGL library
  cannot load, the view falls back to a canvas ball-and-stick
  rendering of the same coordinates. Sequence candidates have no
  small-molecule 3D form and say so. The run view also gains a
  build guide panel that renders each
  ranked candidate's production sheet as steps (make it by its
  route, confirm identity against the sheet, run the confirmation
  assay), naming anything the sheet records as unspecified rather
  than inventing it.

Theme is the synthwave palette of the owner's other tools (near-black
#0a0a16, neon pink #ff71ce, purple #b967ff, cyan #01cdfe), laser
gradient rules, a perspective grid backdrop, and a scanning laser
line over the header.

Security posture, plainly: this binds to 127.0.0.1 by default and has
no authentication, because it is a local tool for the machine's own
user. Running a config from the page executes that config exactly as
the CLI would. Do not expose it to a network you do not trust;
--host exists for the owner's own LAN decisions, not as a default.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .config import (ConfigError, build_providers,
                     entailment_checker_from_config, load_config,
                     quote_checker_from_config, resolver_from_config,
                     run_budget_tracker)
from .design import ModelDesigner, run_design
from .gate0 import list_case_ids, load_input_pack, validate_dataset
from .html_report import bundle_to_html
from .runner import estimate_gate0_run, run_gate0
from .storage import list_runs, load_bundle, write_bundle
from .transcript import record_to_markdown
from .production import build_production_sheets
from .structure3d import candidate_model3d, candidate_structure3d


class RunManager:
    """State of the one run the console drives at a time.

    A run executes on a background thread; the page polls progress.
    Events from the runner are appended verbatim. Starting a second
    run while one is active is refused rather than queued: a console
    that silently stacks runs would spend money silently.
    """

    def __init__(self, runs_dir, gate0_dir):
        """runs_dir receives finished bundles; gate0_dir locates the dataset."""
        self.runs_dir = runs_dir
        self.gate0_dir = gate0_dir
        self.lock = threading.Lock()
        self.running = False
        self.events = []
        self.result = None
        self.error = None

    def progress(self) -> dict:
        """Current snapshot for the polling page."""
        with self.lock:
            return {"running": self.running, "events": list(self.events),
                    "result": self.result, "error": self.error}

    def start_gate0(self, config_path) -> dict:
        """Validate the config path and launch a Gate 0 run thread."""
        with self.lock:
            if self.running:
                return {"started": False, "error": "a run is already in progress"}
            self.running = True
            self.events = []
            self.result = None
            self.error = None
        thread = threading.Thread(target=self._run_gate0,
                                  args=(config_path,), daemon=True)
        thread.start()
        return {"started": True}

    def _run_gate0(self, config_path):
        """The run thread body: config, run with events, write bundle."""
        try:
            config = load_config(config_path)
            built = build_providers(config)
            tracker = run_budget_tracker(built)
            bundle = run_gate0(
                built["providers"], judge_provider=built["judge"],
                baseline_provider=built["baseline"], mode=built.get("mode"),
                budget_tracker=tracker,
                gate0_dir=self.gate0_dir,
                resolver=resolver_from_config(built),
                quote_checker=quote_checker_from_config(built),
                entailment_checker=entailment_checker_from_config(built, tracker),
                retrieval_first=bool(built.get("retrieval_first")),
                on_event=self._on_event, max_workers=built["max_workers"])
            run_dir = write_bundle(bundle, self.runs_dir)
            with self.lock:
                self.result = {"run_id": bundle["run_id"],
                               "outcome": bundle["outcome"],
                               "debate_correct": bundle["debate_score"]["correct_calls"],
                               "baseline_correct": bundle["baseline_score"]["correct_calls"],
                               "run_dir": str(run_dir)}
        except Exception as exc:
            with self.lock:
                self.error = type(exc).__name__ + ": " + str(exc)
        finally:
            with self.lock:
                self.running = False

    def _on_event(self, event):
        """Append one runner progress event (called from the run thread)."""
        with self.lock:
            self.events.append(event)


def build_guide_payload(bundle: dict) -> dict:
    """The console build guide for a run bundle: one entry per
    ranked candidate, taken from the design stage's production
    sheets when the bundle stores them and built mechanically from
    the bundle when it does not (older bundles predate sheets being
    stored). A bundle with no design stage yields no sheets."""
    design = bundle if bundle.get("kind") == "design_run" \
        else bundle.get("design") or {}
    sheets = design.get("production_sheets")
    if sheets is None:
        sheets = build_production_sheets(design)
    return {"sheets": sheets}


def _json(handler, payload, status=200):
    """Send a JSON response."""
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _text(handler, content, content_type, status=200):
    """Send a text or HTML response."""
    body = content.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def make_handler(manager: RunManager):
    """Build the request handler class bound to one RunManager."""

    class Handler(BaseHTTPRequestHandler):
        """Routes the console's pages and JSON API. Quiet logging."""

        def log_message(self, *args):
            """Silence the default request logging."""
            pass

        def do_GET(self):
            """Route GET requests: the page, the JSON API, run files."""
            path = urlparse(self.path).path
            if path.startswith("/assets/"):
                return self._asset(path)
            if path == "/":
                return _text(self, PAGE, "text/html; charset=utf-8")
            if path == "/api/gate0":
                report = validate_dataset(manager.gate0_dir)
                cases = []
                for case_id in list_case_ids(manager.gate0_dir):
                    pack = load_input_pack(case_id, manager.gate0_dir)
                    cases.append({"case_id": case_id,
                                  "disease": pack.get("disease"),
                                  "drug_name": pack.get("drug_name"),
                                  "target": pack.get("target")})
                return _json(self, {"ok": report["ok"],
                                    "error_count": report["error_count"],
                                    "cases": cases})
            if path == "/api/runs":
                return _json(self, {"runs": list_runs(manager.runs_dir)})
            if path == "/api/progress":
                return _json(self, manager.progress())
            if path.startswith("/api/runs/"):
                return self._run_file(path)
            return _json(self, {"error": "not found"}, 404)

        def _asset(self, path):
            """Serve a vendored console asset (the WebGL viewer
            library), by whitelist so no other file is reachable."""
            from pathlib import Path
            known = {"3Dmol-min.js": "text/javascript",
                     "3Dmol-min.js.LICENSE.txt": "text/plain"}
            name = path[len("/assets/"):]
            if name not in known:
                return _json(self, {"error": "not found"}, 404)
            target = Path(__file__).parent / "assets" / name
            if not target.exists():
                return _json(self, {"error": "asset missing"}, 404)
            return _text(self, target.read_text(),
                         known[name] + "; charset=utf-8")

        def _run_file(self, path):
            """Serve one run's bundle, HTML report, or a case transcript."""
            parts = [unquote(p) for p in path.split("/") if p]
            # parts: api, runs, <run_id>[, report.html | transcript, <case>]
            try:
                bundle = load_bundle(manager.runs_dir, parts[2])
            except Exception:
                return _json(self, {"error": "no such run"}, 404)
            if len(parts) == 3:
                return _json(self, bundle)
            if parts[3] == "report.html":
                return _text(self, bundle_to_html(bundle),
                             "text/html; charset=utf-8")
            if parts[3] == "build-guide" and len(parts) == 4:
                return _json(self, build_guide_payload(bundle))
            if parts[3] == "model3d" and len(parts) == 5:
                return _json(self, candidate_model3d(bundle, parts[4]))
            if parts[3] == "structure3d" and len(parts) == 5:
                return _json(self, candidate_structure3d(bundle, parts[4]))
            if parts[3] == "transcript" and len(parts) == 5:
                record = (bundle.get("case_records") or {}).get(parts[4])
                if record is None and bundle.get("kind") == "frame_run":
                    record = bundle.get("record")
                if record is None:
                    return _json(self, {"error": "no such transcript"}, 404)
                return _text(self, record_to_markdown(record),
                             "text/plain; charset=utf-8")
            return _json(self, {"error": "not found"}, 404)

        def do_POST(self):
            """Route POST actions: run start, config check, dry run."""
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length") or 0)
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
            except Exception:
                return _json(self, {"error": "body must be JSON"}, 400)
            config_path = payload.get("config")
            if path == "/api/run-gate0":
                if not config_path:
                    return _json(self, {"error": "config path required"}, 400)
                return _json(self, manager.start_gate0(config_path))
            if path == "/api/design-run":
                run_id = payload.get("run_id")
                if not run_id:
                    return _json(self, {"error": "run_id required"}, 400)
                try:
                    src = load_bundle(manager.runs_dir, run_id)
                    if src.get("kind") == "frame_run":
                        spec = (src.get("record") or {}).get("spec")
                        source = "console, frame run " + str(run_id)
                    elif src.get("kind") == "gate0_run" and payload.get("case"):
                        spec = ((src.get("case_records") or {})
                                .get(payload["case"]) or {}).get("spec")
                        source = "console, gate 0 case " + str(payload["case"])
                    else:
                        spec = None
                        source = ""
                    if not spec:
                        return _json(self, {"ok": False, "error":
                                            "that run has no consensus spec to design from"})
                    designer = None
                    tracker = None
                    if payload.get("config"):
                        built = build_providers(load_config(payload["config"]))
                        tracker = run_budget_tracker(built)
                        designer = ModelDesigner(built["providers"],
                                                 budget_tracker=tracker)
                    bundle = run_design(spec, source, designer=designer,
                                        budget_tracker=tracker,
                                        target=payload.get("target") or None,
                                        disease=payload.get("disease") or None)
                except ValueError as exc:
                    return _json(self, {"ok": False, "error": str(exc)})
                except Exception:
                    return _json(self, {"error": "no such run"}, 404)
                write_bundle(bundle, manager.runs_dir)
                return _json(self, {"ok": True, "run_id": bundle["run_id"],
                                    "gate": bundle["gate_report"]["result"],
                                    "ranked": bundle["ranking"]["ranked"]})
            if path in ("/api/providers-check", "/api/dry-run"):
                try:
                    config = load_config(config_path)
                    built = build_providers(config)
                except ConfigError as exc:
                    return _json(self, {"ok": False, "error": str(exc)})
                if path == "/api/providers-check":
                    names = [getattr(p, "name", "?") for p in built["providers"]]
                    return _json(self, {"ok": True, "providers": names,
                                        "judge": built["judge"] is not None,
                                        "baseline": built["baseline"] is not None})
                estimate = estimate_gate0_run(built["providers"], built["judge"],
                                              built["baseline"],
                                              manager.gate0_dir)
                return _json(self, {"ok": True, "estimate": estimate})
            return _json(self, {"error": "not found"}, 404)

    return Handler


def create_server(host="127.0.0.1", port=8765, runs_dir="runs", gate0_dir=None):
    """Create (but do not start) the console server."""
    manager = RunManager(runs_dir, gate0_dir)
    server = ThreadingHTTPServer((host, port), make_handler(manager))
    server.madd_manager = manager
    return server


def serve(host="127.0.0.1", port=8765, runs_dir="runs", gate0_dir=None):
    """Start the console and serve until interrupted. Prints the URL."""
    server = create_server(host, port, runs_dir, gate0_dir)
    print("MADD Console: http://" + host + ":" + str(server.server_address[1])
          + " (local only by default; Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("console stopped")
    finally:
        server.server_close()


PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>MADD CONSOLE</title>
<style>
  body { background:#0a0a16; color:#e8e8f2; font-family:'Segoe UI',system-ui,sans-serif;
         margin:0; padding:28px;
         background-image:linear-gradient(rgba(185,103,255,.07) 1px,transparent 1px),
                          linear-gradient(90deg,rgba(1,205,254,.07) 1px,transparent 1px);
         background-size:36px 36px; }
  h1 { color:#ff71ce; letter-spacing:4px; margin:0; text-shadow:0 0 14px #ff71ce; }
  h2 { color:#01cdfe; letter-spacing:2px; }
  .sub { color:#9a9ab5; letter-spacing:2px; }
  .laser { height:3px; border:0; margin:14px 0;
           background:linear-gradient(90deg,#ff71ce,#b967ff,#01cdfe); }
  .scan { height:2px; background:linear-gradient(90deg,transparent,#01cdfe,transparent);
          animation:scan 3.2s linear infinite; }
  @keyframes scan { 0%{transform:translateX(-30%)} 100%{transform:translateX(30%)} }
  .panel { background:rgba(18,18,43,.92); border:1px solid #b967ff; border-radius:8px;
           padding:16px 20px; margin:18px 0; }
  button { background:#1b1b3a; color:#01cdfe; border:1px solid #01cdfe;
           padding:8px 16px; border-radius:4px; cursor:pointer; letter-spacing:1px; }
  button:hover { background:#01cdfe; color:#0a0a16; }
  button.run { border-color:#ff71ce; color:#ff71ce; }
  button.run:hover { background:#ff71ce; color:#0a0a16; }
  input { background:#0a0a16; color:#e8e8f2; border:1px solid #b967ff;
          padding:8px; width:420px; border-radius:4px; }
  #console { background:#05050f; border:1px solid #2c2c54; height:220px; overflow:auto;
             padding:10px; font-family:Consolas,monospace; font-size:13px;
             white-space:pre-wrap; }
  table { border-collapse:collapse; } th,td { border:1px solid #2c2c54;
          padding:5px 11px; text-align:left; } th { color:#b967ff; }
  .pass { color:#3dff8f; } .fail { color:#ff5470; } .mut { color:#9a9ab5; }
  a { color:#01cdfe; } .runlink { cursor:pointer; color:#01cdfe; }
</style></head><body>
<h1>MADD // CONSOLE</h1>
<div class="sub">MULTI-AGENT DRUG DISCOVERY - EVIDENCE AUDIT DIVISION</div>
<div class="scan"></div><hr class="laser">
<div class="panel"><h2>RUN CONTROL</h2>
  <input id="config" value="examples/run-config.example.json">
  <button onclick="check()">CHECK CONFIG</button>
  <button onclick="dry()">DRY RUN</button>
  <button class="run" onclick="run()">RUN GATE 0</button>
  <div id="console">console ready.</div>
</div>
<div class="panel"><h2>GATE 0 SCOREBOARD</h2><div id="scoreboard">loading...</div></div>
<div class="panel"><h2>RUN LIBRARY</h2><div id="library">loading...</div>
  <div id="detail"></div></div>
<script src="/assets/3Dmol-min.js"></script>
<script>
const $ = id => document.getElementById(id);
function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, function (ch) {
    return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[ch]; });
}
function log(line) { $('console').textContent += "\\n" + line; $('console').scrollTop = 1e6; }
async function post(path, body) {
  const r = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'},
                               body: JSON.stringify(body)});
  return r.json();
}
async function check() {
  const out = await post('/api/providers-check', {config: $('config').value});
  log(out.ok ? ("config OK | providers: " + out.providers.join(', ') +
                " | judge: " + out.judge + " | baseline: " + out.baseline)
             : ("config problem: " + out.error));
}
async function dry() {
  const out = await post('/api/dry-run', {config: $('config').value});
  if (!out.ok) return log("dry run problem: " + out.error);
  const e = out.estimate;
  log("dry run | cases: " + e.case_count + " | total calls: " + e.total_calls +
      " | estimated cost USD: " + e.estimated_cost_usd);
}
let polling = null;
async function run() {
  const out = await post('/api/run-gate0', {config: $('config').value});
  if (!out.started) return log("not started: " + out.error);
  log("run started...");
  let seen = 0;
  clearInterval(polling);
  polling = setInterval(async () => {
    const p = await (await fetch('/api/progress')).json();
    for (; seen < p.events.length; seen++) {
      const e = p.events[seen];
      log(e.event + (e.case_id ? " | " + e.case_id : "") +
          (e.prediction ? " -> " + e.prediction : "") +
          (e.outcome ? " | " + e.outcome : ""));
    }
    if (!p.running) {
      clearInterval(polling);
      if (p.error) log("RUN STOPPED: " + p.error);
      if (p.result) { log("finished: " + p.result.run_id + " | outcome " +
        p.result.outcome + " | debate " + p.result.debate_correct +
        " vs baseline " + p.result.baseline_correct); loadLibrary(); }
    }
  }, 700);
}
async function loadScoreboard() {
  const g = await (await fetch('/api/gate0')).json();
  let h = "<div>dataset validation: " + (g.ok ? "<span class='pass'>PASS</span>"
        : "<span class='fail'>FAIL (" + g.error_count + " errors)</span>") +
        "</div><table><tr><th>case</th><th>drug</th><th>target</th><th>disease</th></tr>";
  for (const c of g.cases) h += "<tr><td>" + esc(c.case_id) + "</td><td>" + esc(c.drug_name) +
    "</td><td>" + esc(c.target) + "</td><td>" + esc(c.disease) + "</td></tr>";
  $('scoreboard').innerHTML = h + "</table>";
}
async function loadLibrary() {
  const out = await (await fetch('/api/runs')).json();
  if (!out.runs.length) { $('library').innerHTML = "<span class='mut'>no runs yet</span>"; return; }
  let h = "<table><tr><th>run</th><th>kind</th><th>outcome</th></tr>";
  for (const r of out.runs) h += "<tr><td class='runlink' data-runid=\\"" + esc(r.run_id) +
    "\\">" + esc(r.run_id) + "</td><td>" + esc(r.kind) + "</td><td>" + esc(r.outcome) + "</td></tr>";
  $('library').innerHTML = h + "</table>";
  document.querySelectorAll('.runlink').forEach(function (el) {
    el.addEventListener('click', function () { show(el.dataset.runid); });
  });
}
async function show(runId) {
  const b = await (await fetch('/api/runs/' + encodeURIComponent(runId))).json();
  let h = "<h2>RUN " + esc(runId) + "</h2>";
  if (b.kind === 'gate0_run') {
    h += "<div>outcome: <b>" + esc(b.outcome) + "</b> | debate correct " +
      b.debate_score.correct_calls + "/" + b.debate_score.case_count +
      " | baseline correct " + b.baseline_score.correct_calls + "</div>";
    h += "<table><tr><th>threshold</th><th>status</th><th>detail</th></tr>";
    for (const c of b.thresholds.checks) h += "<tr><td>" + esc(c.threshold) + "</td><td class='" +
      (c.status === 'pass' ? 'pass' : 'fail') + "'>" + esc(c.status) + "</td><td>" +
      esc(c.detail) + "</td></tr>";
    h += "</table><p><a href='/api/runs/" + encodeURIComponent(runId) + "/report.html' target='_blank'>HTML report</a></p>";
    h += "<div class='mut'>transcripts:</div>";
    for (const cid of b.case_ids) h += "<div><a href='#' class='txlink' data-runid=\\"" +
      esc(runId) + "\\" data-caseid=\\"" + esc(cid) + "\\">" + esc(cid) + "</a></div>";
  } else if (b.kind === 'design_run') {
    const candById = {};
    for (const c of b.candidates) candById[c.candidate_id] = c;
    h += "<div>target <b>" + esc(b.brief.target) + "</b> | spec " + esc(b.brief.spec_id) +
      " | gate <b>" + esc(b.gate_report.result) + "</b> | designer " + esc(b.designer) + "</div>";
    h += "<table><tr><th>#</th><th>ranked candidate</th></tr>";
    b.ranking.ranked.forEach(function (cid, i) {
      const syn = candById[cid] && candById[cid]._synthetic;
      h += "<tr><td>" + (i + 1) + "</td><td>" + esc(cid) +
        (syn ? " <span class='mut'>(synthetic)</span>" : "") + "</td></tr>"; });
    h += "</table>";
    if (b.ranking.excluded.length) {
      h += "<div class='mut'>excluded:</div>";
      for (const ex of b.ranking.excluded) h += "<div>" + esc(ex.candidate_id) + " - " +
        esc(ex.reasons.join('; ')) + "</div>";
    }
    if (b.tool_runs.length) {
      h += "<div class='mut'>tool runs:</div>";
      for (const t of b.tool_runs) h += "<div>" + esc(t.tool) + ": " + esc(t.status) + "</div>";
    }
    h += "<p><a href='/api/runs/" + encodeURIComponent(runId) + "/report.html' target='_blank'>HTML report</a></p>";
  } else {
    h += "<div>frame " + esc(b.frame_id) + " | outcome <b>" + esc(b.outcome) + "</b></div>";
    if (b.record && b.record.spec && b.record.spec.outcome === 'locked') {
      h += "<p><input id='design-target' placeholder='target override (optional)' style='width:260px'> "
        + "<input id='design-disease' placeholder='disease (specs record none)' style='width:260px'></p>"
        + "<p><button id='designbtn'>DESIGN CANDIDATES FROM THIS SPEC</button></p>"
        + "<div id='designmsg' class='mut'></div>";
    }
  }
  $('detail').innerHTML = h;
  document.querySelectorAll('.txlink').forEach(function (el) {
    el.addEventListener('click', function (ev) {
      ev.preventDefault(); tx(el.dataset.runid, el.dataset.caseid); });
  });
  initViewer3d(runId, b);
  initBuildGuide(runId, b);
  const db = $('designbtn');
  if (db) db.addEventListener('click', function () { designFrom(runId); });
}
async function designFrom(runId) {
  const body = {run_id: runId};
  const t = $('design-target'), d = $('design-disease');
  if (t && t.value) body.target = t.value;
  if (d && d.value) body.disease = d.value;
  const cfg = $('config');
  if (cfg && cfg.value) body.config = cfg.value;
  const out = await (await fetch('/api/design-run', {method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)})).json();
  if (!out.ok) { $('designmsg').textContent = 'design refused: ' + (out.error || 'unknown'); return; }
  $('designmsg').textContent = 'design run ' + out.run_id + ' written, gate ' + out.gate;
  loadLibrary(); show(out.run_id);
}
async function tx(runId, caseId) {
  const t = await (await fetch('/api/runs/' + encodeURIComponent(runId) +
    '/transcript/' + encodeURIComponent(caseId))).text();
  $('detail').innerHTML = "<h2>TRANSCRIPT " + esc(caseId) + "</h2><pre>" +
    t.replace(/</g, '&lt;') + "</pre>";
}
let viewerState = null;
function stopViewer() {
  if (viewerState && viewerState.raf) cancelAnimationFrame(viewerState.raf);
  viewerState = null;
}
function viewer3dHtml(design) {
  const candById = {};
  for (const c of design.candidates) candById[c.candidate_id] = c;
  let h = '<h3>3D STRUCTURE</h3><div>';
  design.ranking.ranked.forEach(function (cid, i) {
    const c = candById[cid] || {}; const st = c.structure || {};
    const ok = (st.format === 'smiles');
    h += '<button class="v3dbtn" data-cid="' + esc(cid) + '"' +
      (ok ? '' : ' disabled title="sequence candidate: no small-molecule 3D form"') +
      '>' + (i + 1) + '. ' + esc(cid) + '</button> ';
  });
  h += '</div><div id="glwrap" style="display:flex;gap:14px;flex-wrap:wrap;margin-top:8px">' +
    '<div><div class="mut">MOLECULE</div>' +
    '<div id="glmol" style="width:400px;height:340px;position:relative;background:#07071a;border:1px solid #2a2a4a"></div>' +
    '<div>style <select id="glmol-style"><option value="ballandstick">ball and stick</option>' +
    '<option value="stick">sticks</option><option value="sphere">space filling</option>' +
    '<option value="line">lines</option></select> ' +
    '<button id="glmol-spin">spin: off</button></div><div id="glmol-cap" class="mut"></div></div>' +
    '<div id="glrec-pane"><div class="mut">RECEPTOR</div>' +
    '<div id="glrec" style="width:400px;height:340px;position:relative;background:#07071a;border:1px solid #2a2a4a"></div>' +
    '<div>style <select id="glrec-style"><option value="cartoon">cartoon</option>' +
    '<option value="stick">sticks</option><option value="sphere">space filling</option></select> ' +
    '<button id="glrec-spin">spin: off</button></div><div id="glrec-cap" class="mut"></div></div>' +
    '</div>' +
    '<canvas id="v3d" width="520" height="360" style="display:none;max-width:100%;background:#07071a;border:1px solid #2a2a4a"></canvas>' +
    '<div id="v3d-status" class="mut">loading 3D model...</div>';
  return h;
}
function initViewer3d(runId, bundle) {
  stopViewer();
  glViewers = {};
  const design = bundle.kind === 'design_run' ? bundle : bundle.design;
  if (!design || !design.ranking || !design.ranking.ranked.length) return;
  const div = document.createElement('div');
  div.innerHTML = viewer3dHtml(design);
  $('detail').appendChild(div);
  div.querySelectorAll('.v3dbtn').forEach(function (el) {
    el.addEventListener('click', function () { loadModel3d(runId, el.dataset.cid); });
  });
  const first = div.querySelector('.v3dbtn:not([disabled])');
  if (first) loadModel3d(runId, first.dataset.cid);
}
let glViewers = {};
function glMolStyle(name) {
  if (name === 'stick') return {stick: {radius: 0.22}};
  if (name === 'sphere') return {sphere: {scale: 1.0}};
  if (name === 'line') return {line: {}};
  return {stick: {radius: 0.18}, sphere: {scale: 0.32}};
}
function glRecStyle(name) {
  if (name === 'stick') return {stick: {radius: 0.15}};
  if (name === 'sphere') return {sphere: {scale: 0.9}};
  return {cartoon: {color: 'spectrum'}};
}
function glSpinWire(btnId, viewer) {
  const b = document.getElementById(btnId);
  if (!b) return;
  b.onclick = function () {
    const on = b.textContent.indexOf('off') >= 0;
    viewer.spin(on);
    b.textContent = on ? 'spin: on' : 'spin: off';
  };
}
async function loadModel3d(runId, cid) {
  const st = $('v3d-status');
  if (typeof $3Dmol === 'undefined') {
    const w = $('glwrap'); if (w) w.style.display = 'none';
    const cv = $('v3d'); if (cv) cv.style.display = '';
    return loadStructure(runId, cid);
  }
  if (st) st.textContent = 'loading 3D model...';
  const out = await (await fetch('/api/runs/' + encodeURIComponent(runId) +
    '/model3d/' + encodeURIComponent(cid))).json();
  if (!out || out.status !== 'ok') {
    if (st) st.textContent = '3D model unavailable: ' + ((out && out.reason) || 'unknown');
    return;
  }
  if (st) st.textContent = out.note;
  const cap = $('glmol-cap');
  if (cap) cap.textContent = out.candidate_id + ' - ' + out.smiles;
  let mv = glViewers.mol;
  if (!mv) { mv = $3Dmol.createViewer(document.getElementById('glmol'), {backgroundColor: '#07071a'}); glViewers.mol = mv; }
  mv.removeAllModels();
  mv.addModel(out.mol, 'sdf');
  const msel = $('glmol-style');
  mv.setStyle({}, glMolStyle(msel ? msel.value : 'ballandstick'));
  mv.zoomTo(); mv.render();
  if (msel) msel.onchange = function () { mv.setStyle({}, glMolStyle(msel.value)); mv.render(); };
  glSpinWire('glmol-spin', mv);
  const pane = $('glrec-pane');
  if (out.receptor) {
    if (pane) pane.style.display = '';
    const rcap = $('glrec-cap');
    if (rcap) rcap.textContent = out.receptor.label + ' - ' + out.receptor.detail + ' (' + out.receptor.source +
      '). Shown in its own view: the candidate has not been docked into it.';
    let rv = glViewers.rec;
    if (!rv) { rv = $3Dmol.createViewer(document.getElementById('glrec'), {backgroundColor: '#07071a'}); glViewers.rec = rv; }
    rv.removeAllModels();
    rv.addModel(out.receptor.data, 'pdb');
    const rsel = $('glrec-style');
    rv.setStyle({}, glRecStyle(rsel ? rsel.value : 'cartoon'));
    rv.zoomTo(); rv.render();
    if (rsel) rsel.onchange = function () { rv.setStyle({}, glRecStyle(rsel.value)); rv.render(); };
    glSpinWire('glrec-spin', rv);
  } else {
    if (pane) pane.style.display = 'none';
    if (st) st.textContent = out.note + ' No receptor structure is on file for this target.';
  }
}
async function loadStructure(runId, cid) {
  const st = $('v3d-status');
  if (!document.getElementById('v3d')) return;
  if (st) st.textContent = 'loading 3D structure...';
  const out = await (await fetch('/api/runs/' + encodeURIComponent(runId) +
    '/structure3d/' + encodeURIComponent(cid))).json();
  if (!out || out.status !== 'ok') {
    stopViewer();
    if (st) st.textContent = '3D structure unavailable: ' + ((out && out.reason) || 'unknown');
    return;
  }
  if (st) st.textContent = out.note + ' | ' + out.smiles;
  startViewer(out);
}
function startViewer(data) {
  stopViewer();
  const cv = document.getElementById('v3d');
  if (!cv) return;
  const g = cv.getContext('2d');
  let cx = 0, cy = 0, cz = 0;
  data.atoms.forEach(function (a) { cx += a.x; cy += a.y; cz += a.z; });
  const n = data.atoms.length; cx /= n; cy /= n; cz /= n;
  let maxr = 0.001;
  data.atoms.forEach(function (a) {
    const d = Math.hypot(a.x - cx, a.y - cy, a.z - cz); if (d > maxr) maxr = d;
  });
  const scale = Math.min(cv.width, cv.height) * 0.36 / maxr;
  const st3 = {angle: 0.4, tilt: 0.5, drag: null, raf: 0};
  viewerState = st3;
  function project(a) {
    const x = a.x - cx, y = a.y - cy, z = a.z - cz;
    const ca = Math.cos(st3.angle), sa = Math.sin(st3.angle);
    const ct = Math.cos(st3.tilt), sn = Math.sin(st3.tilt);
    const X = x * ca - z * sa, Z = x * sa + z * ca;
    const Y = y * ct - Z * sn, D = y * sn + Z * ct;
    return {sx: cv.width / 2 + X * scale, sy: cv.height / 2 + Y * scale, d: D};
  }
  function draw() {
    const P = data.atoms.map(project);
    g.clearRect(0, 0, cv.width, cv.height);
    const items = [];
    data.bonds.forEach(function (bd) { items.push({d: (P[bd.a].d + P[bd.b].d) / 2, t: 'b', bd: bd}); });
    data.atoms.forEach(function (a, i) { items.push({d: P[i].d, t: 'a', i: i}); });
    items.sort(function (p, q) { return p.d - q.d; });
    for (const it of items) {
      if (it.t === 'b') {
        const p = P[it.bd.a], q = P[it.bd.b];
        g.strokeStyle = '#8a8ab0'; g.lineWidth = it.bd.order >= 2 ? 3.4 : 2.2;
        g.beginPath(); g.moveTo(p.sx, p.sy); g.lineTo(q.sx, q.sy); g.stroke();
      } else {
        const a = data.atoms[it.i], p = P[it.i];
        const r = Math.max(5, 9.5 - p.d * 0.5);
        g.fillStyle = a.color;
        g.beginPath(); g.arc(p.sx, p.sy, r, 0, 6.2832); g.fill();
        g.fillStyle = '#0a0a16';
        g.font = 'bold ' + Math.max(8, Math.round(r)) + 'px monospace';
        g.textAlign = 'center'; g.textBaseline = 'middle';
        g.fillText(a.element, p.sx, p.sy + 0.5);
      }
    }
  }
  function frame() { st3.angle += 0.012; draw(); st3.raf = requestAnimationFrame(frame); }
  cv.onmousedown = function (e) { st3.drag = {x: e.offsetX, y: e.offsetY}; };
  cv.onmousemove = function (e) {
    if (st3.drag) {
      st3.angle += (e.offsetX - st3.drag.x) * 0.01;
      st3.tilt += (e.offsetY - st3.drag.y) * 0.01;
      st3.drag = {x: e.offsetX, y: e.offsetY};
      draw();
    }
  };
  cv.onmouseup = function () { st3.drag = null; };
  cv.onmouseleave = function () { st3.drag = null; };
  frame();
}
async function initBuildGuide(runId, bundle) {
  const design = bundle.kind === 'design_run' ? bundle : bundle.design;
  if (!design || !design.ranking || !design.ranking.ranked.length) return;
  const out = await (await fetch('/api/runs/' + encodeURIComponent(runId) + '/build-guide')).json();
  if (!out.sheets || !out.sheets.length) return;
  const div = document.createElement('div');
  let h = '<h3>BUILD GUIDE</h3>';
  h += '<div class="mut">Step by step from the production sheet of each ranked candidate. ' +
    'A sheet marked NOT READY names what is still unspecified; no step here invents it.</div>';
  for (const sh of out.sheets) {
    const idn = sh.identity || {};
    const tp = sh.targeted_process || {};
    const notes = sh.production_notes || {};
    h += '<div style="border:1px solid #2a2a4a;padding:10px;margin:10px 0">';
    h += '<div><b>' + sh.rank + '. ' + esc(sh.candidate_id) + '</b> - ' +
      (sh.production_ready ? '<span class="pass">PRODUCTION READY</span>'
                           : '<span class="fail">NOT READY</span>') + '</div>';
    h += '<div class="mut">target: ' + esc(tp.target || '') +
      (tp.disease ? ' (' + esc(tp.disease) + ')' : '') + ' | route: ' + esc(sh.production_route || '') + '</div>';
    h += '<ol style="margin:8px 0 4px 18px;padding:0">';
    if (idn.format === 'smiles') {
      h += '<li>Make the structure by ' + esc(sh.production_route || 'synthesis') + ': <span class="mut">' +
        esc(idn.canonical_smiles || idn.value_as_proposed || '') + '</span></li>';
      h += '<li>Confirm identity against the sheet: formula ' + esc(idn.molecular_formula || '') +
        ', MW ' + esc(String(idn.molecular_weight || '')) + ', InChIKey ' + esc(idn.inchikey || '') +
        (idn.unspecified_stereocenters ? ' (note: ' + idn.unspecified_stereocenters + ' unspecified stereocenters)' : '') + '</li>';
    } else if (idn.format === 'sequence') {
      h += '<li>Make the sequence by ' + esc(sh.production_route || 'synthesis') + ': <span class="mut">' +
        esc(idn.value_as_proposed || '') + '</span> (' + esc(String(idn.length || '')) + ' units, alphabet check ' +
        esc(idn.alphabet_check || '') + ')</li>';
      h += '<li>Confirm identity against the sheet: length and composition match the sheet exactly.</li>';
    } else {
      h += '<li>Make the candidate by ' + esc(sh.production_route || 'the route on its sheet') + '.</li>';
    }
    if (notes.confirmation_assay) {
      h += '<li>Run the confirmation assay from the design record: ' + esc(notes.confirmation_assay) + '</li>';
    } else {
      h += '<li>Confirmation assay: <span class="fail">not specified</span> - one must be defined before this candidate can be confirmed.</li>';
    }
    h += '</ol>';
    if (sh.not_specified && sh.not_specified.length) {
      h += '<div class="mut">still unspecified:</div>';
      for (const ns of sh.not_specified) h += '<div>- ' + esc(ns) + '</div>';
    }
    h += '</div>';
  }
  div.innerHTML = h;
  $('detail').appendChild(div);
}
loadScoreboard(); loadLibrary();
</script></body></html>
"""
