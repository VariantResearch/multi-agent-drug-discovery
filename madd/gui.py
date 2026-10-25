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
  HTML report and per-case debate transcripts.

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

from .config import ConfigError, build_providers, load_config
from .design import ModelDesigner, run_design
from .gate0 import list_case_ids, load_input_pack, validate_dataset
from .html_report import bundle_to_html
from .runner import estimate_gate0_run, run_gate0
from .storage import list_runs, load_bundle, write_bundle
from .transcript import record_to_markdown


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
            bundle = run_gate0(
                built["providers"], judge_provider=built["judge"],
                baseline_provider=built["baseline"], budget=built["budget"],
                gate0_dir=self.gate0_dir,
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
                    if payload.get("config"):
                        built = build_providers(load_config(payload["config"]))
                        designer = ModelDesigner(built["providers"])
                    bundle = run_design(spec, source, designer=designer,
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
loadScoreboard(); loadLibrary();
</script></body></html>
"""
