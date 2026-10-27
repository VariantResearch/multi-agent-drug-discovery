"""Tests for the console's live event stream (SSE), the per-run
event log, and its replay.

The stream replaces 700 ms polling as the primary transport: the
server replays the backlog after ?since=, pushes live events as
they land, and closes with a caught_up event when the run is
done. Polling remains the page's fallback, so /api/progress keeps
its contract throughout.
"""
import json
import threading
import time
import urllib.request

import pytest

from madd.gui import RunManager, create_server


@pytest.fixture()
def gui_server(tmp_path):
    """Provide the running console server on a temporary runs dir."""
    runs = tmp_path / "runs"
    runs.mkdir()
    server = create_server("127.0.0.1", 0, runs_dir=str(runs),
                           gate0_dir=None)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:" + str(server.server_address[1]), runs
    server.shutdown()


def _post(url, payload):
    """POST a JSON payload to the console test server."""
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _mock_slot():
    """Build one setup form slot for a mock provider."""
    return {"kind": "mock", "model": "", "family": "",
            "base_url": "", "api_key_env": ""}


def test_manager_wait_events_wakes_on_append(tmp_path):
    """wait_events returns promptly when an event lands mid-wait."""
    manager = RunManager(str(tmp_path), None)
    with manager.lock:
        manager.running = True

    def producer():
        """Append one event after a short delay, then stop."""
        time.sleep(0.2)
        manager._on_event({"event": "case_done", "case_id": "x"})
        with manager.lock:
            manager.running = False
        with manager.cond:
            manager.cond.notify_all()

    thread = threading.Thread(target=producer)
    thread.start()
    started = time.time()
    events, total, running = manager.wait_events(0, timeout=10)
    assert time.time() - started < 5
    assert events == [{"event": "case_done", "case_id": "x"}]
    assert total == 1 and running is False
    thread.join()


def test_manager_persist_events_writes_jsonl(tmp_path):
    """The run folder gains an events.jsonl replay of the stream."""
    manager = RunManager(str(tmp_path), None)
    manager._on_event({"event": "run_started", "run_id": "r1"})
    manager._on_event({"event": "debate_case_done", "case_id": "c1"})
    run_dir = tmp_path / "r1"
    run_dir.mkdir()
    manager.persist_events(run_dir)
    lines = (run_dir / "events.jsonl").read_text().splitlines()
    assert [json.loads(line)["event"] for line in lines] == [
        "run_started", "debate_case_done"]


def test_sse_stream_and_replay_over_http(gui_server):
    """End to end: a mock target run's events arrive over the SSE
    stream as data frames, the stream closes with caught_up, and
    the finished run's events replay from its run folder."""
    base, runs = gui_server
    setup = {"primary": _mock_slot(), "secondary": _mock_slot(),
             "judge": _mock_slot(), "mode": "simple_judge",
             "budget": {"max_calls": "", "max_cost_usd": ""},
             "switches": {}}
    assert _post(base + "/api/setup", setup)["ok"] is True
    started = _post(base + "/api/target-run",
                    {"name": "STREAMT", "kind": "target",
                     "target": "STREAMT", "disease": "invented",
                     "focus_id": "", "constraints": "",
                     "retrieve": False})
    assert started["started"] is True

    frames = []
    with urllib.request.urlopen(base + "/api/events?since=0",
                                timeout=60) as resp:
        assert resp.headers.get_content_type() == "text/event-stream"
        buffer = ""
        while "caught_up" not in buffer:
            line = resp.readline().decode()
            if not line:
                break
            buffer += line
    assert "data:" in buffer and "debate_case_started" in buffer
    assert "caught_up" in buffer
    for line in buffer.splitlines():
        if line.startswith("data: ") and line != "data: {}":
            frames.append(json.loads(line[6:]))
    assert frames and frames[0]["event"] == "debate_case_started"
    run_id = None
    deadline = time.time() + 60
    while time.time() < deadline and run_id is None:
        with urllib.request.urlopen(base + "/api/progress",
                                    timeout=10) as resp:
            progress = json.loads(resp.read().decode())
        if not progress["running"] and progress["result"]:
            run_id = progress["result"]["run_id"]
        else:
            time.sleep(0.5)
    assert run_id

    # The finished run's folder carries the replayable stream.
    replay = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                    base + "/api/runs/" + run_id + "/events",
                    timeout=10) as resp:
                replay = json.loads(resp.read().decode())
            break
        except Exception:
            time.sleep(0.5)
    assert replay is not None
    assert [e["event"] for e in replay["events"]] == \
        [e["event"] for e in frames]
    run_dir = runs / run_id
    assert (run_dir / "events.jsonl").exists()
