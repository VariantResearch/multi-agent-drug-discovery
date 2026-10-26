"""Tests for the console setup panel, the target form endpoint, and
the simple_judge protocol mode (Garrett's judge ablation cell).

The console tests boot the real HTTP server against a temporary
runs directory and drive it over HTTP, like the design endpoint
tests. All providers are mocks: nothing here calls a network or a
model.
"""
import json
import threading
import time
import urllib.request

import pytest

from madd import storage
from madd.config import validate_config
from madd.gui import create_server
from madd.runner import run_frame


@pytest.fixture()
def gui_server(tmp_path):
    """Provide the running console server on a temporary runs dir."""
    runs = tmp_path / "runs"
    runs.mkdir()
    server = create_server("127.0.0.1", 0, runs_dir=str(runs),
                           gate0_dir=None)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:" + str(server.server_address[1])
    server.shutdown()


def _get(url):
    """GET a JSON document from the console test server."""
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read().decode())


def _post(url, payload):
    """POST a JSON payload to the console test server."""
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _mock_slot(**extra):
    """Build one setup form slot for a mock provider."""
    slot = {"kind": "mock", "model": "", "family": "",
            "base_url": "", "api_key_env": ""}
    slot.update(extra)
    return slot


def _setup_payload(**overrides):
    """Build a full setup form payload with mock slots."""
    payload = {"primary": _mock_slot(), "secondary": _mock_slot(),
               "judge": _mock_slot(), "mode": "simple_judge",
               "budget": {"max_calls": "", "max_cost_usd": ""},
               "switches": {}}
    payload.update(overrides)
    return payload


def test_setup_starts_unconfigured(gui_server):
    """A fresh console reports no setup and not ready."""
    status = _get(gui_server + "/api/setup")
    assert status["configured"] is False
    assert status["ready"] is False
    assert status["slots"]["primary"] is None


def test_setup_save_roundtrip(gui_server):
    """Saving mock slots persists a valid config the status reflects."""
    out = _post(gui_server + "/api/setup", _setup_payload())
    assert out["ok"] is True
    status = out["status"]
    assert status["configured"] is True
    assert status["ready"] is True
    assert status["mode"] == "simple_judge"
    assert status["slots"]["judge"]["kind"] == "mock"
    again = _get(gui_server + "/api/setup")
    assert again["slots"]["secondary"]["name"] == "secondary"


def test_setup_rejects_invalid_mode_shape(gui_server):
    """dual_judge with a one-model panel fails validation, unsaved."""
    payload = _setup_payload(secondary={"kind": ""}, mode="dual_judge")
    out = _post(gui_server + "/api/setup", payload)
    assert out["ok"] is False
    assert any("dual_judge" in e for e in out["errors"])
    assert _get(gui_server + "/api/setup")["configured"] is False


def test_setup_key_presence_from_environment(gui_server, monkeypatch):
    """Key presence is read by variable name from the environment."""
    monkeypatch.setenv("MADD_TEST_KEY_PRESENT", "x")
    slot = {"kind": "openai-compatible", "model": "m",
            "family": "fam", "base_url": "",
            "api_key_env": "MADD_TEST_KEY_PRESENT"}
    out = _post(gui_server + "/api/setup",
                _setup_payload(primary=slot, secondary={"kind": ""},
                               judge={"kind": ""}, mode="simple"))
    assert out["ok"] is True
    assert out["status"]["slots"]["primary"]["key_present"] is True
    assert out["status"]["ready"] is True
    slot["api_key_env"] = "MADD_TEST_KEY_ABSENT"
    out = _post(gui_server + "/api/setup",
                _setup_payload(primary=slot, secondary={"kind": ""},
                               judge={"kind": ""}, mode="simple"))
    assert out["status"]["slots"]["primary"]["key_present"] is False
    assert out["status"]["ready"] is False


def test_slot_smoke_test_mock(gui_server):
    """The per-slot test makes its one call against the saved setup."""
    _post(gui_server + "/api/setup", _setup_payload())
    out = _post(gui_server + "/api/setup/test", {"slot": "primary"})
    assert out["ok"] is True
    out = _post(gui_server + "/api/setup/test", {"slot": "judge"})
    assert out["ok"] is True
    out = _post(gui_server + "/api/setup/test", {"slot": "nope"})
    assert out["ok"] is False


def _wait_for_result(base):
    """Poll the console progress endpoint until the run settles."""
    for _ in range(120):
        progress = _get(base + "/api/progress")
        if not progress["running"]:
            return progress
        time.sleep(0.25)
    raise AssertionError("run did not settle")


def test_target_run_end_to_end_mock(gui_server):
    """A target run on mock slots lands a target_run bundle."""
    _post(gui_server + "/api/setup", _setup_payload())
    out = _post(gui_server + "/api/target-run",
                {"name": "MTCH2", "kind": "target", "target": "MTCH2",
                 "disease": "obesity", "retrieve": False,
                 "constraints": ""})
    assert out["started"] is True
    progress = _wait_for_result(gui_server)
    assert progress["error"] is None
    result = progress["result"]
    assert result["kind"] == "target_run"
    runs = _get(gui_server + "/api/runs")["runs"]
    assert any(r["run_id"] == result["run_id"] for r in runs)
    bundle = _get(gui_server + "/api/runs/" + result["run_id"])
    assert bundle["kind"] == "target_run"
    assert bundle["mode"] == "simple_judge"


def test_target_run_single_primary_clones_second_agent(gui_server):
    """One assigned model still fields the protocol's two agents."""
    payload = _setup_payload(secondary={"kind": ""},
                             judge={"kind": ""}, mode="simple")
    _post(gui_server + "/api/setup", payload)
    out = _post(gui_server + "/api/target-run",
                {"name": "KRAS G12C", "kind": "target",
                 "target": "KRAS G12C", "disease": "lung cancer",
                 "retrieve": False, "constraints": "oral only"})
    assert out["started"] is True
    progress = _wait_for_result(gui_server)
    assert progress["error"] is None
    assert progress["result"]["kind"] == "target_run"


class _Stub:
    """Research stub carrying one auditable claim per dossier."""

    def __init__(self, name):
        """Initialize the stub with a fixed mock model identity."""
        self.name = name
        self.model_version = "mock-1"

    def research(self, frame):
        """Return a dossier proposing the frame focus, with evidence."""
        return {"artifact_type": "dossier", "schema_version": "0.1.0",
                "dossier_id": "D-" + self.name,
                "frame_id": frame.get("frame_id"),
                "agent_id": self.name, "model_family": "mock",
                "proposed_focus_id": "MTCH2", "direction": "inhibition",
                "unverified_notes": [],
                "claims": [{"claim_id": "C-" + self.name,
                            "text": "invented claim",
                            "load_bearing": True, "evidence_tier": 2,
                            "source_kind": "journal_article",
                            "source_identifier": "12345678",
                            "identifier_type": "pmid",
                            "verification_status": "quote_checked",
                            "supporting_quote": "invented quote"}]}


def test_simple_judge_mode_validation():
    """simple_judge needs one panel model and a judge entry."""
    providers = [{"name": "a", "kind": "mock", "label": "a"},
                 {"name": "b", "kind": "mock", "label": "b"}]
    config = {"providers": providers, "mode": "simple_judge"}
    assert any("simple_judge" in e for e in validate_config(config))
    config["judge"] = {"name": "j", "kind": "mock", "label": "j"}
    assert validate_config(config) == []


def test_simple_judge_frame_run_uses_the_judge():
    """A one-model panel plus a judge locks and records the judge."""
    frame = {"frame_id": "F-SJ", "focus": "MTCH2", "focus_id": "MTCH2",
             "question": "invented"}
    bundle = run_frame(frame, [_Stub("a"), _Stub("b")],
                       judge_provider=_Stub("j"), mode="simple_judge")
    record = bundle["record"]
    assert record["spec"]["outcome"] == "locked"
    roles = [c["role"] for c in record["manifest"]["calls"]]
    assert "judge" in roles
