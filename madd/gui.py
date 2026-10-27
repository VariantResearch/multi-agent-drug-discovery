"""MADD Console: the retro cyberpunk web interface.

A local web GUI over the same machinery the CLI drives, served by
the standard library's HTTP server - no new dependencies, nothing
leaves the machine. One page, six panels:

- SETUP: the model slots the console runs on - Primary, Secondary,
  and Judge - each a provider entry (kind, model, family, endpoint,
  and the NAME of the environment variable holding its API key;
  key values never enter the page or the saved file). The page
  loads to this panel until at least the Primary slot is assigned,
  each slot shows whether its key variable is present in the
  server's environment, and a per-slot Test button makes one small
  smoke call. The saved setup is a run config at
  runs/console-config.json, in the same format the CLI reads.
- TARGET RUN: the target-first form. Name the thing to aim at,
  pick its kind (disease, receptor, genetic disorder, molecular
  target), add the disease context, design constraints, and
  whether to retrieve Europe PMC evidence first; the run executes
  on the setup's models under the setup's protocol mode and lands
  in the run library like any other bundle.
- ACTIVITY: a live console that renders the runner's progress
  events as a run happens (streamed; see the streaming note in
  the RunManager docstring).
- RUN LIBRARY: the product runs in the runs directory (Gate 0
  validation bundles are CLI territory and are not listed here);
  click one for its detail, with links to its styled HTML report
  and debate transcripts. A completed design
  (a design run, or a target run whose design stage ran) also shows
  a fully rendered 3D structural view: the ranked drug candidate as
  a WebGL model (3Dmol.js, vendored under madd/assets/, geometry
  generated from its SMILES by madd/structure3d.py) beside the
  receptor structure for the target - none ships with the
  package, so the console fetches the AlphaFold predicted model
  on demand and registers it, labelled predicted. Molecule and
  receptor sit in separate views; an operator-triggered dock
  (madd/docking.py) adds a computed pose view, labelled as a
  scoring-function geometry, not evidence of binding. If the WebGL library
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
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .budget import BudgetExceeded
from .config import (ConfigError, build_providers,
                     contradiction_checker_from_config, meta_reviewer_from_config,
                     tournament_judge_from_config,
                     entailment_checker_from_config, load_config,
                     quote_checker_from_config, resolver_from_config,
                     run_budget_tracker, validate_config)
from .design import ModelDesigner, run_design
from .html_report import bundle_to_html
from .report_pdf import render_report_pdf
from .opentargets import evidence_for_frame
from .retrieval import retrieve_evidence
from .smoke import smoke_provider
from .storage import list_runs, load_bundle, write_bundle
from .runner import estimate_target_run
from .target_run import build_target_frame, run_target
from .transcript import record_to_markdown
from .production import build_production_sheets
from .structure3d import candidate_model3d, candidate_structure3d


class RunManager:
    """State of the one run the console drives at a time.

    A run executes on a background thread; its progress events
    stream to the page over server-sent events (with polling kept
    as the fallback transport) and are persisted into the finished
    run's folder as events.jsonl. Starting a second run while one
    is active is refused rather than queued: a console that
    silently stacks runs would spend money silently.
    """

    def __init__(self, runs_dir):
        """runs_dir receives finished bundles."""
        self.runs_dir = runs_dir
        # The console is the long-lived process the registry cache
        # exists for: enable it into the runs directory unless the
        # operator already pointed it somewhere (or disabled it by
        # pointing it at an empty string via their own setup).
        if "MADD_REGISTRY_CACHE" not in os.environ:
            os.environ["MADD_REGISTRY_CACHE"] = str(
                Path(runs_dir) / "registry-cache.sqlite3")
        self.setup_path = Path(runs_dir) / "console-config.json"
        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)
        self.running = False
        self.events = []
        self.result = None
        self.error = None
        self.stop_event = None
        self.started_at = None
        self.current_tracker = None

    def progress(self) -> dict:
        """Current snapshot for the polling page, including the
        live run header fields: start time, budget consumption,
        and whether a stop has been requested."""
        tracker = self.current_tracker
        with self.lock:
            return {"running": self.running, "events": list(self.events),
                    "result": self.result, "error": self.error,
                    "started_at": self.started_at,
                    "calls_made": (tracker.calls_made if tracker else None),
                    "spent_usd": (tracker.spent_usd if tracker else None),
                    "max_calls": (tracker.max_calls if tracker else None),
                    "max_cost_usd": (tracker.max_cost_usd
                                     if tracker else None),
                    "stopping": bool(self.stop_event
                                     and self.stop_event.is_set())}

    def request_stop(self) -> dict:
        """Ask the active run to stop cooperatively. The run
        checks the flag at phase boundaries and finishes with a
        partial bundle marked stopped rather than a verdict."""
        with self.lock:
            if not self.running or self.stop_event is None:
                return {"ok": False, "error": "no run is active"}
            self.stop_event.set()
            return {"ok": True, "stopping": True}

    def _on_event(self, event):
        """Append one runner progress event (called from the run thread)."""
        with self.cond:
            self.events.append(event)
            self.cond.notify_all()

    def wait_events(self, since: int, timeout: float = 15.0):
        """Wait for events past index `since`, then snapshot.

        Returns (new_events, total_count, running). Blocks on the
        condition for up to timeout seconds so the SSE endpoint is
        not a busy poll; wakes early when an event lands or the
        run state flips.
        """
        with self.cond:
            self.cond.wait_for(
                lambda: len(self.events) > since or not self.running,
                timeout=timeout)
            return (list(self.events[since:]), len(self.events),
                    self.running)

    def persist_events(self, run_dir):
        """Write this run's events into its run folder as
        events.jsonl, the replayable record the run detail reads
        back after the live stream is gone."""
        with self.lock:
            events = list(self.events)
        lines = "".join(json.dumps(event) + "\n" for event in events)
        (Path(run_dir) / "events.jsonl").write_text(lines, encoding="utf-8")

    def _load_setup_config(self):
        """The saved console setup as a config dict, or None.

        A missing or unreadable setup file is simply "not set up":
        the page's setup panel is where that gets repaired.
        """
        try:
            data = json.loads(self.setup_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    def setup_status(self) -> dict:
        """What the setup panel shows: slots, key presence, readiness.

        Key presence is read from the server process's environment
        by variable NAME; key values are never read out or returned.
        Ready means the Primary slot is assigned and usable (a mock,
        or an HTTP entry whose key variable is present), which is
        the gate for the target form.
        """
        config = self._load_setup_config()
        slots = {"primary": None, "secondary": None, "judge": None}
        swap = None
        if config:
            providers = config.get("providers") or []
            if len(providers) > 0:
                slots["primary"] = _slot_view(providers[0])
            if len(providers) > 1:
                slots["secondary"] = _slot_view(providers[1])
            if config.get("judge"):
                slots["judge"] = _slot_view(config["judge"])
            if config.get("judge_swap"):
                swap = _slot_view(config["judge_swap"])
        primary = slots["primary"]
        ready = bool(primary and (primary["kind"] == "mock"
                                  or primary["key_present"]))
        return {"configured": config is not None, "ready": ready,
                "slots": slots, "judge_swap": swap,
                "mode": (config or {}).get("mode"),
                "preset": (config or {}).get("preset"),
                "budget": (config or {}).get("budget") or {},
                "switches": {
                    key: bool((config or {}).get(key))
                    for key in ("live_resolution", "live_quote_check",
                                "entailment_check", "contradiction_check",
                                "tournament", "meta_review",
                                "retrieval_first")}}

    def save_setup(self, payload) -> dict:
        """Validate and save the setup panel's slots as a run config.

        Slot entries are built from the form's fields (empty strings
        dropped); a judge_swap or baseline entry already in the file
        is preserved untouched, because the panel does not manage
        those slots. A config that fails validation is not saved.
        """
        providers = []
        for slot in ("primary", "secondary"):
            entry = _entry_from_form(payload.get(slot), slot)
            if entry is not None:
                providers.append(entry)
        if len(providers) == 1:
            # One assigned model still fields the protocol's two
            # agents: the saved config carries the second agent as a
            # clone entry on the same model, exactly as a hand
            # written config for a one-model mode would.
            clone = dict(providers[0])
            clone["name"] = str(providers[0]["name"]) + "-b"
            clone["label"] = clone["name"]
            providers.append(clone)
        judge = _entry_from_form(payload.get("judge"), "judge")
        config = {"providers": providers}
        if judge is not None:
            config["judge"] = judge
        old = self._load_setup_config() or {}
        for kept in ("judge_swap", "baseline"):
            if old.get(kept):
                config[kept] = old[kept]
        if payload.get("mode"):
            config["mode"] = payload["mode"]
        if payload.get("preset"):
            config["preset"] = payload["preset"]
        budget = {}
        given = payload.get("budget") or {}
        if given.get("max_calls"):
            budget["max_calls"] = int(given["max_calls"])
        if given.get("max_cost_usd"):
            budget["max_cost_usd"] = float(given["max_cost_usd"])
        if budget:
            config["budget"] = budget
        for key in ("live_resolution", "live_quote_check",
                    "entailment_check", "contradiction_check",
                    "tournament", "meta_review", "retrieval_first"):
            if (payload.get("switches") or {}).get(key):
                config[key] = True
        errors = validate_config(config)
        if errors:
            return {"ok": False, "errors": errors}
        self.setup_path.parent.mkdir(parents=True, exist_ok=True)
        self.setup_path.write_text(json.dumps(config, indent=2),
                                   encoding="utf-8")
        return {"ok": True, "status": self.setup_status()}

    def test_slot(self, slot) -> dict:
        """Smoke-test one assigned slot with a single research call.

        The call is the same one the CLI's smoke command makes (one
        small dossier request, retries disabled). Building the slot
        through build_providers means a missing key variable reports
        as a config error before any call is attempted.
        """
        config = self._load_setup_config()
        if not config:
            return {"ok": False, "error": "no setup saved yet"}
        providers = config.get("providers") or []
        # Build through the saved panel (a valid config by
        # construction) with the mode stripped: the slot is what is
        # being tested, not the saved mode's shape rules.
        temp = {"providers": providers}
        index = None
        if slot in ("primary", "secondary"):
            index = 0 if slot == "primary" else 1
            if len(providers) <= index:
                return {"ok": False,
                        "error": "slot not assigned: " + str(slot)}
        elif slot == "judge":
            if not config.get("judge"):
                return {"ok": False, "error": "slot not assigned: judge"}
            temp["judge"] = config["judge"]
        else:
            return {"ok": False, "error": "unknown slot: " + str(slot)}
        try:
            built = build_providers(temp)
        except ConfigError as exc:
            return {"ok": False, "error": str(exc)}
        provider = (built["judge"] if slot == "judge"
                    else built["providers"][index])
        return smoke_provider(provider)

    def start_target(self, payload) -> dict:
        """Begin a target run on a background thread, refusing overlaps."""
        with self.lock:
            if self.running:
                return {"started": False,
                        "error": "a run is already in progress"}
            if self._load_setup_config() is None:
                return {"started": False,
                        "error": "no setup saved yet: assign the model "
                                 "slots first"}
            self.running = True
            self.events = []
            self.result = None
            self.error = None
            self.stop_event = threading.Event()
            stop_event = self.stop_event
            import time as _time
            self.started_at = _time.time()
            self.current_tracker = None
        threading.Thread(target=self._run_target, args=(payload, stop_event),
                         daemon=True).start()
        return {"started": True}

    def _run_target(self, payload, stop_event=None):
        """The target run thread body: frame, retrieve, run, write.

        The panel comes from the saved setup. A setup with a single
        provider entry fields two agents on that one model (the
        protocol's simple shapes), by cloning the entry under a
        second agent name - the same arrangement a config file
        expresses with two identical entries.
        """
        try:
            config = self._load_setup_config()
            entries = list(config.get("providers") or [])
            if len(entries) == 1:
                clone = dict(entries[0])
                clone["name"] = str(entries[0].get("name")) + "-b"
                clone["label"] = clone["name"]
                entries.append(clone)
            built = build_providers({**config, "providers": entries})
            frame = build_target_frame(
                str(payload.get("name") or ""), str(payload.get("kind") or ""),
                target=payload.get("target") or None,
                disease=payload.get("disease") or None,
                focus_id=payload.get("focus_id") or None)
            retrieval_first = bool(built.get("retrieval_first"))
            if payload.get("retrieve", True):
                from .fulltext import retrieve_tiered_evidence
                frame["evidence"] = (
                    retrieve_tiered_evidence(
                        frame, built.get("retrieval_tier", "abstract"))
                    + evidence_for_frame(frame))
                retrieval_first = True
            tracker = run_budget_tracker(built)
            self.current_tracker = tracker
            constraints = tuple(
                line.strip() for line in str(
                    payload.get("constraints") or "").splitlines()
                if line.strip())
            bundle = run_target(
                frame, built["providers"], judge_provider=built["judge"],
                swap_judge_provider=built.get("judge_swap"),
                mode=built.get("mode"), budget_tracker=tracker,
                resolver=resolver_from_config(built),
                quote_checker=quote_checker_from_config(built),
                entailment_checker=entailment_checker_from_config(
                    built, tracker),
                contradiction_checker=contradiction_checker_from_config(
                    built, tracker),
                tournament_judge=tournament_judge_from_config(
                    built, tracker),
                meta_reviewer=meta_reviewer_from_config(
                    built, tracker),
                retrieval_first=retrieval_first,
                design_constraints=constraints,
                on_event=self._on_event,
                should_stop=(stop_event.is_set if stop_event else None),
                prereg_dir=self.runs_dir)
            run_dir = write_bundle(bundle, self.runs_dir)
            self.persist_events(run_dir)
            design = bundle.get("design") or {}
            with self.lock:
                self.result = {
                    "run_id": bundle["run_id"], "kind": "target_run",
                    "outcome": bundle["outcome"],
                    "focus": (bundle["frame_run"]["record"]["spec"]
                              .get("focus_id")),
                    "design_gate": (design.get("gate_report") or {})
                    .get("result"),
                    "run_dir": str(run_dir)}
        except Exception as exc:
            with self.lock:
                self.error = type(exc).__name__ + ": " + str(exc)
        finally:
            with self.lock:
                self.running = False


def _slot_view(entry) -> dict:
    """One setup slot as the page shows it: the entry's public shape
    plus whether its API key variable is present in this process's
    environment. Mock entries need no key. Values are never read."""
    env = entry.get("api_key_env")
    return {"name": entry.get("name"), "kind": entry.get("kind"),
            "model": entry.get("model"), "family": entry.get("family"),
            "base_url": entry.get("base_url"), "api_key_env": env,
            "key_present": True if entry.get("kind") == "mock"
            else bool(env and os.environ.get(env))}


def _entry_from_form(form, slot):
    """Build a config provider entry from one setup form slot.

    Returns None when the slot is unassigned (no kind). Empty fields
    are dropped so optional values stay absent from the config; the
    entry's name and label are the slot's, which keeps names unique
    across the panel and the judge by construction.
    """
    if not isinstance(form, dict) or not form.get("kind"):
        return None
    entry = {"name": slot, "kind": form["kind"], "label": slot}
    for key in ("model", "family", "base_url", "api_key_env"):
        value = form.get(key)
        if isinstance(value, str) and value.strip():
            entry[key] = value.strip()
    return entry


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
    """Send a text, HTML, or binary (PDF) response."""
    body = content if isinstance(content, bytes) else content.encode("utf-8")
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
            if path == "/api/setup":
                return _json(self, manager.setup_status())
            if path == "/api/runs":
                runs = [entry for entry in list_runs(manager.runs_dir)
                        if entry.get("kind") != "gate0_run"]
                return _json(self, {"runs": runs})
            if path == "/api/progress":
                return _json(self, manager.progress())
            if path == "/api/events":
                return self._events_stream(manager)
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

        def _events_stream(self, manager):
            """Stream the active run's progress as server-sent events.

            Sends the backlog after ?since= first, then live events
            as they land, with keep-alive comments while the run is
            quiet, and a final caught_up event once the run has
            finished and the backlog is drained. A client that
            disconnects mid-stream is routine, not an error.
            """
            from urllib.parse import parse_qs, urlparse
            query = parse_qs(urlparse(self.path).query)
            try:
                seq = max(0, int((query.get("since") or ["0"])[0]))
            except ValueError:
                seq = 0
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                while True:
                    new_events, total, running = manager.wait_events(
                        seq, timeout=15.0)
                    for event in new_events:
                        seq += 1
                        frame = ("id: " + str(seq) + "\ndata: " +
                                 json.dumps(event) + "\n\n")
                        self.wfile.write(frame.encode("utf-8"))
                        self.wfile.flush()
                    if not running and seq >= total:
                        self.wfile.write(b"event: caught_up\ndata: {}\n\n")
                        self.wfile.flush()
                        return
                    if not new_events:
                        self.wfile.write(b": keep-alive\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return

        def _run_file(self, path):
            """Serve one run's bundle, HTML report, or a case transcript."""
            parts = [unquote(p) for p in path.split("/") if p]
            # parts: api, runs, <run_id>[, report.html | transcript, <case>]
            try:
                bundle = load_bundle(manager.runs_dir, parts[2])
            except Exception:
                return _json(self, {"error": "no such run"}, 404)
            if len(parts) == 3:
                overlay_path = (Path(manager.runs_dir)
                                / "retraction-overlay.json")
                if overlay_path.exists():
                    try:
                        overlay = json.loads(
                            overlay_path.read_text(encoding="utf-8"))
                        notices = [f for f in
                                   overlay.get("findings") or []
                                   if parts[2] in
                                   (f.get("cited_by") or {})]
                        if notices:
                            bundle = dict(bundle)
                            bundle["retraction_notices"] = notices
                            bundle["retraction_checked_on"] = \
                                overlay.get("checked_on")
                    except Exception:
                        pass
                return _json(self, bundle)
            if parts[3] == "report.html":
                return _text(self, bundle_to_html(bundle),
                             "text/html; charset=utf-8")
            if parts[3] == "report.pdf":
                result = render_report_pdf(bundle)
                if result["status"] != "completed":
                    return _json(self, {"error": "PDF not rendered (" +
                                        result["status"] + "): " +
                                        (result.get("reason") or "")}, 501)
                return _text(self, result["pdf"], "application/pdf")
            if parts[3] == "build-guide" and len(parts) == 4:
                return _json(self, build_guide_payload(bundle))
            if parts[3] == "model3d" and len(parts) == 5:
                payload = candidate_model3d(
                    bundle, parts[4], fetch_missing=True,
                    cache_dir=Path(manager.runs_dir) / "structures")
                if payload.get("status") == "ok":
                    from .docking import load_docking_record
                    record = load_docking_record(
                        Path(manager.runs_dir) / parts[2], parts[4])
                    if record and record.get("status") == "completed":
                        payload["docked_pose"] = {
                            "pose": record["pose"],
                            "affinity_kcal_mol": record.get(
                                "affinity_kcal_mol"),
                            "note": record["note"],
                            "box": record.get("box"),
                            "cross_check": record.get("cross_check")}
                return _json(self, payload)
            if parts[3] == "structure3d" and len(parts) == 5:
                return _json(self, candidate_structure3d(bundle, parts[4]))
            if parts[3] == "events" and len(parts) == 4:
                events_path = (Path(manager.runs_dir) / parts[2]
                               / "events.jsonl")
                if not events_path.exists():
                    return _json(self, {"error": "no recorded events"}, 404)
                events = [json.loads(line) for line in
                          events_path.read_text(encoding="utf-8").splitlines()
                          if line.strip()]
                return _json(self, {"events": events})
            if parts[3] == "audit-flow" and len(parts) == 4:
                from .audit_flow import audit_flow_of_bundle
                return _json(self, {
                    "audit_flow": audit_flow_of_bundle(bundle)})
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
            """Route POST actions: setup save and slot tests, target
            run start and design runs."""
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length") or 0)
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
            except Exception:
                return _json(self, {"error": "body must be JSON"}, 400)
            if path == "/api/setup":
                try:
                    return _json(self, manager.save_setup(payload))
                except (TypeError, ValueError) as exc:
                    return _json(self, {"ok": False,
                                        "errors": [str(exc)]})
            if path == "/api/setup/test":
                return _json(self, manager.test_slot(
                    str(payload.get("slot") or "")))
            if path == "/api/stop":
                return _json(self, manager.request_stop())
            if path == "/api/target-preflight":
                config = manager._load_setup_config()
                if config is None:
                    return _json(self, {"ok": False, "problems": [
                        "no setup saved yet: assign the model slots first"]})
                try:
                    built = build_providers(config)
                except ConfigError as exc:
                    return _json(self, {"ok": False,
                                        "problems": ["setup problem: " + str(exc)]})
                estimate = estimate_target_run(
                    built["providers"], built["judge"],
                    swap_judge_provider=built.get("judge_swap"),
                    retrieval_tier=built.get("retrieval_tier",
                                             "abstract"))
                budget = config.get("budget") or {}
                problems = []
                if budget.get("max_calls") is not None and \
                        estimate["total_calls"] > budget["max_calls"]:
                    problems.append(
                        "the budget call cap (" + str(budget["max_calls"])
                        + ") is below the estimated calls ("
                        + str(estimate["total_calls"]) + ")")
                if budget.get("max_cost_usd") is not None and \
                        estimate["estimated_cost_usd"] > budget["max_cost_usd"]:
                    problems.append(
                        "the budget cost cap is below the estimated cost")
                return _json(self, {"ok": not problems,
                                    "estimate": estimate,
                                    "budget": {"max_calls": budget.get("max_calls"),
                                               "max_cost_usd": budget.get("max_cost_usd")},
                                    "problems": problems})
            if path == "/api/target-run":
                if not payload.get("name") or not payload.get("kind"):
                    return _json(self, {"started": False, "error":
                                        "a target name and kind are required"})
                return _json(self, manager.start_target(payload))
            if path.startswith("/api/runs/") and path.endswith("/dock"):
                run_id = path.split("/")[3]
                candidate_id = payload.get("candidate_id")
                if not candidate_id:
                    return _json(self, {"error": "candidate_id required"}, 400)
                try:
                    bundle = load_bundle(manager.runs_dir, run_id)
                except Exception:
                    return _json(self, {"error": "no such run"}, 404)
                from .docking import (dock_candidate,
                                      docking_record_path)
                from .structure3d import (_find_candidate, fetch_receptor,
                                          receptor_for_target)
                design, candidate = _find_candidate(bundle, candidate_id)
                if candidate is None:
                    return _json(self, {"ok": False,
                                        "error": "no such candidate"})
                structure = candidate.get("structure") or {}
                if str(structure.get("format") or "").lower() != "smiles":
                    return _json(self, {"ok": False, "error":
                                        "only SMILES candidates can dock"})
                brief = (design or {}).get("brief") or {}
                receptor = receptor_for_target(brief.get("target"))
                if receptor is None:
                    receptor = fetch_receptor(
                        brief.get("target"),
                        cache_dir=Path(manager.runs_dir) / "structures")
                if receptor is None:
                    return _json(self, {"ok": False, "error":
                                        "no receptor on file for this "
                                        "target and none could be fetched"})
                run_dir = Path(manager.runs_dir) / run_id
                record = dock_candidate(
                    receptor["data"], structure.get("value"),
                    run_dir / ("dockwork-" + str(candidate_id)))
                if record.get("status") == "completed":
                    # A configured DiffDock installation cross-checks
                    # the Vina pose with an independent method; with
                    # none configured the record simply carries no
                    # cross-check, which never reads as a failure.
                    from .diffdock import configured_home, cross_check
                    if configured_home() is not None:
                        record["cross_check"] = cross_check(
                            receptor["data"], structure.get("value"),
                            record.get("pose") or "",
                            run_dir / ("diffdock-" + str(candidate_id)))
                record["candidate_id"] = candidate_id
                record["receptor_label"] = receptor.get("label")
                docking_record_path(run_dir, candidate_id).write_text(
                    json.dumps(record, indent=2), encoding="utf-8")
                return _json(self, {"ok": record["status"] == "completed",
                                    "status": record["status"],
                                    "affinity_kcal_mol": record.get(
                                        "affinity_kcal_mol"),
                                    "detail": record.get("detail"),
                                    "problems": record.get("problems")})
            if path == "/api/design-run":
                run_id = payload.get("run_id")
                if not run_id:
                    return _json(self, {"error": "run_id required"}, 400)
                try:
                    src = load_bundle(manager.runs_dir, run_id)
                    if src.get("kind") == "frame_run":
                        spec = (src.get("record") or {}).get("spec")
                        source = "console, frame run " + str(run_id)
                    else:
                        spec = None
                        source = ""
                    if not spec:
                        return _json(self, {"ok": False, "error":
                                            "that run has no consensus spec to design from"})
                    designer = None
                    tracker = None
                    if payload.get("config") or manager.setup_path.exists():
                        built = build_providers(load_config(
                            payload.get("config") or str(manager.setup_path)))
                        tracker = run_budget_tracker(built)
                        designer = ModelDesigner(built["providers"],
                                                 budget_tracker=tracker)
                    design_events = []
                    bundle = run_design(spec, source, designer=designer,
                                        budget_tracker=tracker,
                                        target=payload.get("target") or None,
                                        disease=payload.get("disease") or None,
                                        on_event=design_events.append)
                except BudgetExceeded as exc:
                    return _json(self, {"ok": False, "error":
                                        "run stopped: " + str(exc)})
                except ValueError as exc:
                    return _json(self, {"ok": False, "error": str(exc)})
                except Exception:
                    return _json(self, {"error": "no such run"}, 404)
                design_dir = write_bundle(bundle, manager.runs_dir)
                write_events_jsonl(design_dir, design_events)
                return _json(self, {"ok": True, "run_id": bundle["run_id"],
                                    "gate": bundle["gate_report"]["result"],
                                    "ranked": bundle["ranking"]["ranked"]})
            return _json(self, {"error": "not found"}, 404)

    return Handler


def write_events_jsonl(run_dir, events):
    """Write an event stream into a run folder as events.jsonl,
    one JSON object per line. Shared by the run manager (target
    runs) and the synchronous design action, so every bundle the
    console writes carries its recorded activity."""
    import json as _json
    path = Path(run_dir) / "events.jsonl"
    lines = [_json.dumps(event) for event in events]
    path.write_text("\n".join(lines) + ("\n" if lines else ""))


def create_server(host="127.0.0.1", port=8765, runs_dir="runs"):
    """Create (but do not start) the console server."""
    manager = RunManager(runs_dir)
    server = ThreadingHTTPServer((host, port), make_handler(manager))
    server.madd_manager = manager
    return server


def serve(host="127.0.0.1", port=8765, runs_dir="runs"):
    """Start the console and serve until interrupted. Prints the URL."""
    server = create_server(host, port, runs_dir)
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
  .flow { display:flex; gap:6px; flex-wrap:wrap; align-items:stretch;
    margin:10px 0; }
  .fbox { border:1px solid #345; border-radius:6px; padding:8px 12px;
    min-width:120px; }
  .fbox b { display:block; font-size:20px; }
  .fbox .fl { font-size:11px; color:#9a9ab5; text-transform:uppercase; }
  .farrow { align-self:center; color:#9a9ab5; }
  a { color:#01cdfe; } .runlink { cursor:pointer; color:#01cdfe; }
  select, textarea { background:#0a0a16; color:#e8e8f2; border:1px solid #b967ff;
                     padding:8px; border-radius:4px; }
  textarea { display:block; margin-top:6px; }
  input[type=checkbox] { width:auto; }
</style></head><body>
<h1>MADD // CONSOLE</h1>
<div class="sub">MULTI-AGENT DRUG DISCOVERY - EVIDENCE AUDIT DIVISION</div>
<div class="scan"></div><hr class="laser">
<div class="panel"><h2>SETUP // MODEL SLOTS</h2>
  <div id="setup-status" class="mut">checking setup...</div>
  <div id="slot-primary"></div><div id="slot-secondary"></div><div id="slot-judge"></div>
  <div style="margin-top:10px">panel preset
    <button type="button" class="presetchip" data-name="solo" data-mode="simple" data-summary="Every research agent runs on one and the same model, and there is no judge." onclick="pickPreset(this)">solo</button>
    <button type="button" class="presetchip" data-name="solo_judged" data-mode="simple_judge" data-summary="Every research agent runs on one model, and a judge ranks the dossiers; the judge-swap experiment can run." onclick="pickPreset(this)">solo_judged</button>
    <button type="button" class="presetchip" data-name="pair" data-mode="dual" data-summary="The research panel is split across two models, and there is no judge." onclick="pickPreset(this)">pair</button>
    <button type="button" class="presetchip" data-name="pair_judged" data-mode="dual_judge" data-summary="The research panel is split across two models, and a judge ranks the dossiers; the judge-swap experiment can run." onclick="pickPreset(this)">pair_judged</button>
    <span id="preset-summary" class="mut"></span></div>
  <div style="margin-top:10px">protocol mode <select id="s-mode"></select>
    <span style="margin-left:14px">budget max calls <input id="s-budget-calls" style="width:90px"></span>
    <span style="margin-left:10px">max cost USD <input id="s-budget-cost" style="width:90px"></span></div>
  <div style="margin-top:8px">evidence switches:
    <label><input type="checkbox" id="s-sw-live_resolution"> live resolution</label>
    <label><input type="checkbox" id="s-sw-live_quote_check"> quote check</label>
    <label><input type="checkbox" id="s-sw-entailment_check"> entailment check</label>
    <label><input type="checkbox" id="s-sw-contradiction_check"> contradiction check</label>
    <label><input type="checkbox" id="s-sw-tournament"> tournament</label>
    <label><input type="checkbox" id="s-sw-meta_review"> meta-review</label>
    <label><input type="checkbox" id="s-sw-retrieval_first"> retrieval first</label></div>
  <p><button class="run" onclick="saveSetup()">SAVE SETUP</button>
  <span id="setup-msg" class="mut"></span></p>
  <div class="mut">Keys are never typed here: each slot names the environment variable that
  holds its API key on the machine running the console. Test buttons make one small
  research call against the SAVED setup, so save first after changing a slot.</div>
</div>
<div class="panel"><h2>TARGET RUN</h2>
  <div id="target-gate" class="mut"></div>
  <div>name <input id="t-name" style="width:300px">
    kind <select id="t-kind">
      <option value="target">molecular target</option>
      <option value="receptor">receptor</option>
      <option value="disease">disease</option>
      <option value="genetic_disorder">genetic disorder</option></select></div>
  <div style="margin-top:8px">molecular target <input id="t-target" style="width:280px">
    disease context <input id="t-disease" style="width:280px"></div>
  <div style="margin-top:8px">focus id (optional) <input id="t-focus" style="width:280px">
    <label><input type="checkbox" id="t-retrieve" checked> retrieve Europe PMC evidence first</label></div>
  <div style="margin-top:8px">design constraints, one per line
    <textarea id="t-constraints" rows="3" style="width:660px"></textarea></div>
  <p><button class="run" onclick="runTarget()">RUN TARGET</button>
  <button onclick="preflight()">PREFLIGHT</button>
  <span id="target-msg" class="mut"></span></p>
  <div id="preflight" class="mut"></div>
</div>
<div class="panel"><h2>ACTIVITY</h2>
  <div style="margin-bottom:6px"><span id="runbar" class="mut">no run active</span>
  <button id="stopbtn" style="display:none" onclick="stopRun()">STOP RUN</button></div>
  <div id="console">console ready.</div>
</div>
<div class="panel"><h2>RUN LIBRARY</h2>
  <div style="margin-bottom:8px">
    <select id="lib-kind"><option value="">all kinds</option><option value="target_run">target runs</option><option value="frame_run">frame runs</option><option value="design_run">design runs</option></select>
    <select id="lib-outcome"><option value="">all outcomes</option></select>
    <input id="lib-search" placeholder="search run id or target" style="width:240px">
    <select id="lib-sort"><option value="new">newest first</option><option value="old">oldest first</option><option value="id">run id</option></select>
  </div>
  <div id="library">loading...</div>
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
function eventLine(e) {
  return e.event + (e.case_id ? " | " + e.case_id : "") +
    (e.prediction ? " -> " + e.prediction : "") +
    (e.outcome ? " | " + e.outcome : "");
}
function watchProgress(onEvent, onDone) {
  let seen = 0, finished = false, es = null, iv = null;
  function stop() { if (es) es.close(); if (iv) clearInterval(iv); }
  function drain(p) {
    for (; seen < p.events.length; seen++) onEvent(p.events[seen]);
    if (!p.running && !finished) { finished = true; stop(); onDone(p); }
  }
  function startPoll() {
    if (iv) return;
    iv = setInterval(async () => {
      const p = await (await fetch('/api/progress')).json(); drain(p);
    }, 700);
  }
  if (window.EventSource) {
    try {
      es = new EventSource('/api/events?since=0');
      es.onmessage = function (msg) { seen++; onEvent(JSON.parse(msg.data)); };
      es.addEventListener('caught_up', async function () {
        const p = await (await fetch('/api/progress')).json(); drain(p);
      });
      es.onerror = function () { if (es.readyState === 2) startPoll(); };
      const safety = setInterval(async () => {
        if (finished) { clearInterval(safety); return; }
        const p = await (await fetch('/api/progress')).json();
        if (!p.running) drain(p);
      }, 4000);
    } catch (e) { startPoll(); }
  } else startPoll();
}
let _libRuns = [];
async function loadLibrary() {
  const out = await (await fetch('/api/runs')).json();
  _libRuns = out.runs || [];
  const outcomes = [...new Set(_libRuns.map(function (r) { return r.outcome; }).filter(Boolean))].sort();
  const sel = $('lib-outcome');
  const keep = sel.value;
  sel.innerHTML = "<option value=''>all outcomes</option>" + outcomes.map(function (o) {
    return "<option value='" + esc(o) + "'>" + esc(o) + "</option>"; }).join("");
  sel.value = keep;
  renderLibrary();
}
function renderLibrary() {
  const kind = $('lib-kind').value, outcome = $('lib-outcome').value;
  const q = $('lib-search').value.toLowerCase(), sort = $('lib-sort').value;
  let runs = _libRuns.filter(function (r) {
    return (!kind || r.kind === kind) && (!outcome || r.outcome === outcome) &&
      (!q || (r.run_id + " " + (r.target || "")).toLowerCase().includes(q));
  });
  runs.sort(function (a, b) {
    if (sort === "id") return a.run_id < b.run_id ? -1 : 1;
    const ka = a.created_utc || a.run_id, kb = b.created_utc || b.run_id;
    return sort === "new" ? (ka < kb ? 1 : -1) : (ka < kb ? -1 : 1);
  });
  if (!runs.length) {
    $('library').innerHTML = "<span class='mut'>" +
      (_libRuns.length ? "no runs match the filters" : "no runs yet") + "</span>";
    return;
  }
  let h = "<table><tr><th>run</th><th>kind</th><th>target</th><th>outcome</th></tr>";
  for (const r of runs) h += "<tr><td class='runlink' data-runid='" + esc(r.run_id) +
    "'>" + esc(r.run_id) + "</td><td>" + esc(r.kind) + "</td><td>" +
    esc(r.target || "") + "</td><td>" + esc(r.outcome) + "</td></tr>";
  $('library').innerHTML = h + "</table>";
  document.querySelectorAll('.runlink').forEach(function (el) {
    el.addEventListener('click', function () { show(el.dataset.runid); });
  });
}
function flowHtml(flow) {
  let h = "<div class='flow'>";
  flow.stages.forEach(function (s, i) {
    if (i) h += "<div class='farrow'>&rarr;</div>";
    h += "<div class='fbox'><span class='fl'>" + esc(s.label) + "</span>";
    if (s.key === 'outcome') {
      h += "<b>" + esc(s.value) + "</b><span class='mut'>consensus " +
        s.consensus_passed + "/" + s.consensus_total + " checks</span>";
    } else {
      h += "<b>" + s.count + "</b>";
      if (s.by_reason) {
        for (const r in s.by_reason) h += "<div class='mut'>" + esc(r) +
          ": " + s.by_reason[r] + "</div>";
      }
    }
    h += "</div>";
  });
  return h + "</div><div class='mut'>" + esc(flow.note) + "</div>";
}
async function show(runId) {
  const b = await (await fetch('/api/runs/' + encodeURIComponent(runId))).json();
  let h = "<h2>RUN " + esc(runId) + "</h2>";
  if (b.retraction_notices && b.retraction_notices.length) {
    for (const f of b.retraction_notices) {
      h += "<div style='border:1px solid #ff5470;border-radius:6px;"
        + "padding:8px 12px;margin:8px 0'><b>Post-publication notice ("
        + esc(f.severity) + ")</b>: " + esc(f.identifier_type) + " "
        + esc(f.identifier) + " - checked " +
        esc(b.retraction_checked_on || "") + "<br>";
      for (const n of f.notices) {
        h += "<span class='mut'>" + esc(n.source) + ": " +
          esc(n.type_label || n.severity) +
          (n.date ? " (" + esc(n.date) + ")" : "") +
          (n.notice_doi ? " <a href='https://doi.org/" +
            esc(n.notice_doi) + "' target='_blank'>notice</a>" : "") +
          "</span><br>";
      }
      h += "</div>";
    }
  }
  if (b.kind === 'design_run') {
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
    h += "<p><a href='/api/runs/" + encodeURIComponent(runId) + "/report.html' target='_blank'>HTML report</a> | <a href='/api/runs/" + encodeURIComponent(runId) + "/report.pdf' target='_blank'>PDF report</a></p>";
  } else if (b.kind === 'target_run') {
    const rec = b.frame_run.record; const tg = b.target || {};
    h += "<div>target <b>" + esc(tg.name) + "</b> (" + esc(tg.kind) + ")" +
      (tg.disease ? " in " + esc(tg.disease) : "") + " | mode " + esc(b.mode || "none") +
      " | debate outcome <b>" + esc(rec.outcome) + "</b> | focus " +
      esc(rec.spec.focus_id || "") + " | strikes " + rec.strike_list.length + "</div>";
    if (b.design) {
      h += "<div>design gate <b>" + esc(b.design.gate_report.result) + "</b> | ranked " +
        b.design.ranking.ranked.length + " | excluded " + b.design.ranking.excluded.length + "</div>";
    } else {
      h += "<div class='mut'>no design stage (the specification did not lock)</div>";
    }
    h += "<p><a href='/api/runs/" + encodeURIComponent(runId) + "/report.html' target='_blank'>HTML report</a> | <a href='/api/runs/" + encodeURIComponent(runId) + "/report.pdf' target='_blank'>PDF report</a></p>";
  } else {
    h += "<div>frame " + esc(b.frame_id) + " | outcome <b>" + esc(b.outcome) + "</b></div>";
    if (b.record && b.record.spec && b.record.spec.outcome === 'locked') {
      h += "<p><input id='design-target' placeholder='target override (optional)' style='width:260px'> "
        + "<input id='design-disease' placeholder='disease (specs record none)' style='width:260px'></p>"
        + "<p><button id='designbtn'>DESIGN CANDIDATES FROM THIS SPEC</button></p>"
        + "<div id='designmsg' class='mut'></div>";
    }
  }
  try {
    const af = await (await fetch('/api/runs/' + encodeURIComponent(runId) + '/audit-flow')).json();
    if (af.audit_flow) h += flowHtml(af.audit_flow);
  } catch (err) { }
  try {
    const ev = await (await fetch('/api/runs/' + encodeURIComponent(runId) + '/events')).json();
    if (ev.events && ev.events.length) {
      h += "<div class='mut'>run activity (recorded stream):</div>";
      for (const e of ev.events) h += "<div>" + esc(eventLine(e)) + "</div>";
    }
  } catch (err) { }
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
    '<div id="glpose-pane" style="display:none"><div class="mut">DOCKED POSE (COMPUTED)</div>' +
    '<div id="glpose" style="width:400px;height:340px;position:relative;background:#07071a;border:1px solid #2a2a4a"></div>' +
    '<div id="glpose-cap" class="mut"></div></div>' +
    '</div>' +
    '<div style="margin-top:8px"><button id="dockbtn">DOCK INTO RECEPTOR</button> ' +
    '<span id="dock-status" class="mut"></span></div>' +
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
  const dockBtn = div.querySelector('#dockbtn');
  if (dockBtn) dockBtn.addEventListener('click', function () { dockCurrent(runId); });
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
let _v3dCid = null;
async function dockCurrent(runId) {
  const st = $('dock-status');
  if (!_v3dCid) { if (st) st.textContent = "pick a candidate first"; return; }
  if (st) st.textContent = "docking (preparation plus search; can take a minute)...";
  const out = await post('/api/runs/' + encodeURIComponent(runId) + '/dock',
                         {candidate_id: _v3dCid});
  if (!out.ok) {
    if (st) st.textContent = "docking " + (out.status || "refused") + ": " +
      (out.error || out.detail || (out.problems || []).join("; ") || "unknown");
    return;
  }
  if (st) st.textContent = "docked | Vina score " + out.affinity_kcal_mol +
    " kcal/mol (a scoring-function value, not a measured affinity)";
  loadModel3d(runId, _v3dCid);
}
async function loadModel3d(runId, cid) {
  _v3dCid = cid;
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
  const ppane = $('glpose-pane');
  if (ppane) {
    if (out.docked_pose && out.receptor) {
      ppane.style.display = '';
      let pv = glViewers.pose;
      if (!pv) { pv = $3Dmol.createViewer(document.getElementById('glpose'), {backgroundColor: '#07071a'}); glViewers.pose = pv; }
      pv.removeAllModels();
      pv.addModel(out.receptor.data, 'pdb');
      pv.addModel(out.docked_pose.pose, 'pdb');
      pv.setStyle({}, {cartoon: {color: 'spectrum'}});
      pv.addStyle({resn: 'LIG'}, {stick: {radius: 0.25}, sphere: {scale: 0.4}});
      pv.zoomTo(); pv.render();
      if (st) st.textContent = out.note + ' A computed docked pose is shown in its own view below.';
      const pcap = $('glpose-cap');
      if (pcap) pcap.textContent = 'Vina score ' + out.docked_pose.affinity_kcal_mol +
        ' kcal/mol | ' + out.docked_pose.note + ' | box: ' +
        ((out.docked_pose.box || {}).source || '') +
        (out.docked_pose.cross_check && out.docked_pose.cross_check.status === 'completed' ?
          ' | DiffDock cross-check: ' + out.docked_pose.cross_check.agreement +
          ' (centroid ' + out.docked_pose.cross_check.centroid_distance_a + ' A)' : '');
    } else {
      ppane.style.display = 'none';
    }
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
let setupState = null;
const SLOT_LABELS = {primary: 'PRIMARY MODEL', secondary: 'SECONDARY MODEL', judge: 'JUDGE MODEL'};
function slotHtml(slot, view) {
  const v = view || {};
  const kinds = ['', 'mock', 'openai-compatible', 'anthropic'];
  let h = "<div style='border:1px solid #2a2a4a;padding:10px;margin:10px 0'>";
  h += "<div><b>" + SLOT_LABELS[slot] + "</b> ";
  if (view) {
    h += "<span class='mut'>" + esc(view.kind || '') + (view.model ? ' | ' + esc(view.model) : '') + "</span> ";
    h += view.key_present ? "<span class='pass'>key variable present</span>"
                          : "<span class='fail'>key variable missing</span>";
  } else {
    h += "<span class='mut'>not assigned</span>";
  }
  h += "</div><div style='margin-top:6px'>kind <select id='s-" + slot + "-kind'>";
  for (const k of kinds) {
    h += "<option value='" + k + "'" + (v.kind === k ? ' selected' : '') + '>' +
      (k || '(unassigned)') + "</option>";
  }
  h += "</select> model <input id='s-" + slot + "-model' style='width:220px' value='" + esc(v.model || '') + "'>";
  h += " family <input id='s-" + slot + "-family' style='width:150px' value='" + esc(v.family || '') + "'></div>";
  h += "<div style='margin-top:6px'>base url <input id='s-" + slot + "-base_url' style='width:250px' value='" + esc(v.base_url || '') + "'>";
  h += " api key env var <input id='s-" + slot + "-api_key_env' style='width:170px' value='" + esc(v.api_key_env || '') + "'>";
  h += " <button class='slottest' data-slot='" + slot + "'>TEST SAVED SLOT</button>" +
    " <span id='s-" + slot + "-test' class='mut'></span></div></div>";
  return h;
}
let chosenPreset = null;
function pickPreset(el) {
  chosenPreset = el.dataset.name;
  refreshModes();
  const sel = $('s-mode');
  let note = el.dataset.summary;
  const offered = Array.prototype.some.call(sel.options,
    function (o) { return o.value === el.dataset.mode; });
  if (offered) { sel.value = el.dataset.mode; }
  else { note += ' (mode ' + el.dataset.mode
    + ' is not offered for the current slot shapes)'; }
  $('preset-summary').textContent = 'preset ' + chosenPreset + ': ' + note;
}
function refreshModes() {
  const pk = $('s-primary-kind').value, sk = $('s-secondary-kind').value;
  const jud = $('s-judge-kind').value;
  // Two mock slots are one model (every mock is the same fixed
  // model), and two slots naming the same model id are one model;
  // anything else with a secondary assigned spans two.
  const twoModels = !!sk && !(pk === 'mock' && sk === 'mock') &&
    !($('s-primary-model').value &&
      $('s-primary-model').value === $('s-secondary-model').value);
  const opts = [['', '(no mode declared)']];
  if (!twoModels && !jud) opts.push(['simple', 'simple - 1 model, no judge']);
  if (!twoModels && jud) opts.push(['simple_judge', 'simple_judge - 1 model + judge']);
  if (twoModels && !jud) opts.push(['dual', 'dual - 2 models, no judge']);
  if (twoModels && jud) opts.push(['dual_judge', 'dual_judge - 2 models + judge']);
  const sel = $('s-mode');
  const keep = setupState && setupState.mode;
  if (keep && !opts.some(function (o) { return o[0] === keep; })) {
    opts.push([keep, keep + ' (saved)']);
  }
  sel.innerHTML = opts.map(function (o) {
    return "<option value='" + o[0] + "'>" + o[1] + "</option>"; }).join('');
  sel.value = keep ? keep : opts[opts.length - 1][0];
}
function renderSetup(st) {
  setupState = st;
  for (const slot of ['primary', 'secondary', 'judge']) {
    $('slot-' + slot).innerHTML = slotHtml(slot, st.slots[slot]);
  }
  document.querySelectorAll('.slottest').forEach(function (el) {
    el.addEventListener('click', function () { testSlot(el.dataset.slot); });
  });
  for (const slot of ['primary', 'secondary', 'judge']) {
    $('s-' + slot + '-kind').addEventListener('change', refreshModes);
  }
  $('s-budget-calls').value = st.budget.max_calls || '';
  $('s-budget-cost').value = st.budget.max_cost_usd || '';
  for (const key of ['live_resolution', 'live_quote_check', 'entailment_check', 'contradiction_check', 'tournament', 'meta_review', 'retrieval_first']) {
    $('s-sw-' + key).checked = !!st.switches[key];
  }
  chosenPreset = st.preset || null;
  const savedChip = chosenPreset
    ? document.querySelector(".presetchip[data-name='" + chosenPreset + "']")
    : null;
  $('preset-summary').textContent = savedChip
    ? 'preset ' + chosenPreset + ': ' + savedChip.dataset.summary : '';
  refreshModes();
  $('setup-status').innerHTML = !st.configured
    ? "<span class='fail'>NO SETUP SAVED</span> - assign at least the Primary model below, then save. The target form unlocks once the Primary slot is usable."
    : (st.ready
      ? "<span class='pass'>READY</span> - the target form runs on this setup." +
        (st.judge_swap ? " A judge_swap entry is also on file (managed by config file, not this panel)." : '')
      : "<span class='fail'>SETUP SAVED BUT PRIMARY NOT USABLE</span> - assign the Primary slot, or set its key variable in the console's environment.");
  $('target-gate').textContent = st.ready
    ? '' : 'Target runs need a saved setup with a usable Primary model (setup panel above).';
}
async function loadSetup() {
  renderSetup(await (await fetch('/api/setup')).json());
}
function collectSlot(slot) {
  return {kind: $('s-' + slot + '-kind').value,
          model: $('s-' + slot + '-model').value,
          family: $('s-' + slot + '-family').value,
          base_url: $('s-' + slot + '-base_url').value,
          api_key_env: $('s-' + slot + '-api_key_env').value};
}
async function saveSetup() {
  let presetName = null;
  if (chosenPreset) {
    const chip = document.querySelector(
      ".presetchip[data-name='" + chosenPreset + "']");
    if (chip && chip.dataset.mode === $('s-mode').value) {
      presetName = chosenPreset;
    }
  }
  const body = {primary: collectSlot('primary'), secondary: collectSlot('secondary'),
    judge: collectSlot('judge'), mode: $('s-mode').value || null,
    preset: presetName,
    budget: {max_calls: $('s-budget-calls').value, max_cost_usd: $('s-budget-cost').value},
    switches: {}};
  for (const key of ['live_resolution', 'live_quote_check', 'entailment_check', 'contradiction_check', 'tournament', 'meta_review', 'retrieval_first']) {
    body.switches[key] = $('s-sw-' + key).checked;
  }
  const out = await post('/api/setup', body);
  if (!out.ok) {
    $('setup-msg').textContent = 'not saved: ' + (out.errors || []).join('; ');
    return;
  }
  $('setup-msg').textContent = 'setup saved.';
  renderSetup(out.status);
}
async function testSlot(slot) {
  const el = $('s-' + slot + '-test');
  el.textContent = 'calling...';
  const out = await post('/api/setup/test', {slot: slot});
  el.textContent = out.ok
    ? ('OK | model ' + (out.model_returned || out.model_configured || '?') +
       ' | ' + out.latency_ms + ' ms')
    : ('failed: ' + (out.error || 'unknown'));
}
async function preflight() {
  const out = await post('/api/target-preflight', {});
  if (!out.estimate) {
    $('preflight').textContent = "preflight: " + ((out.problems || ["unknown problem"]).join("; "));
    return;
  }
  const e = out.estimate, b = out.budget || {};
  let s = "preflight: about " + e.total_calls + " calls (" + e.debate_calls +
    " debate + " + e.design_calls + " design if it locks), estimated $" +
    e.estimated_cost_usd.toFixed(4) +
    (e.retrieval_tier ? " | retrieval tier " + e.retrieval_tier +
      " (up to " + e.full_text_fetches + " full texts)" : "");
  if (b.max_calls != null) s += " | budget cap " + b.max_calls + " calls";
  if (b.max_cost_usd != null) s += " / $" + b.max_cost_usd;
  if (out.problems && out.problems.length) s += " | PROBLEMS: " + out.problems.join("; ");
  $('preflight').textContent = s;
}
let _runStartedAt = null, _runStage = "", _runTimer = null;
function runbarStart() {
  _runStartedAt = Date.now(); _runStage = "starting";
  $('stopbtn').style.display = "";
  if (_runTimer) clearInterval(_runTimer);
  _runTimer = setInterval(runbarTick, 1000);
  runbarTick();
}
async function runbarTick() {
  if (!_runStartedAt) return;
  const secs = Math.floor((Date.now() - _runStartedAt) / 1000);
  let calls = "";
  try {
    const p = await (await fetch('/api/progress')).json();
    if (p.calls_made != null) {
      calls = " | calls " + p.calls_made + (p.max_calls != null ? "/" + p.max_calls : "") +
        (p.spent_usd != null ? " | spent $" + p.spent_usd.toFixed(4) : "");
    }
    if (p.stopping) { $('stopbtn').textContent = "STOPPING..."; $('stopbtn').disabled = true; }
    if (!p.running && (p.result || p.error)) runbarStop();
  } catch (e) { /* stream fallback covers the run itself */ }
  $('runbar').textContent = "running | elapsed " + Math.floor(secs / 60) + ":" +
    String(secs % 60).padStart(2, "0") + " | stage " + _runStage + calls;
}
function runbarStop() {
  if (_runTimer) clearInterval(_runTimer);
  _runTimer = null; _runStartedAt = null;
  $('stopbtn').style.display = "none";
  $('stopbtn').textContent = "STOP RUN"; $('stopbtn').disabled = false;
  $('runbar').textContent = "no run active";
}
async function stopRun() {
  const out = await post('/api/stop', {});
  if (out.ok) { $('stopbtn').textContent = "STOPPING..."; $('stopbtn').disabled = true; }
}
async function runTarget() {
  const body = {name: $('t-name').value, kind: $('t-kind').value,
    target: $('t-target').value, disease: $('t-disease').value,
    focus_id: $('t-focus').value, constraints: $('t-constraints').value,
    retrieve: $('t-retrieve').checked};
  const out = await post('/api/target-run', body);
  if (!out.started) {
    $('target-msg').textContent = 'not started: ' + out.error;
    return;
  }
  log('target run started: ' + body.name);
  runbarStart();
  watchProgress(function (e) { _runStage = e.event; log(eventLine(e)); }, function (p) {
    runbarStop();
    if (p.error) {
      log('RUN STOPPED: ' + p.error);
      $('target-msg').textContent = 'stopped: ' + p.error;
    }
    if (p.result) {
      log('finished: ' + p.result.run_id + ' | outcome ' + p.result.outcome +
          ' | focus ' + p.result.focus +
          (p.result.design_gate ? ' | design gate ' + p.result.design_gate : ''));
      loadLibrary();
      show(p.result.run_id);
    }
  });
}
for (const id of ['lib-kind', 'lib-outcome', 'lib-sort'])
  $(id).addEventListener('change', renderLibrary);
$('lib-search').addEventListener('input', renderLibrary);
loadLibrary(); loadSetup();
</script></body></html>
"""
