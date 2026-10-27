"""Panel preset tests: the registry in madd/presets.py, the
"preset" run-config key in madd/config.py, the `presets` CLI
subcommand, and the console setup panel's preset chips.

All providers are mocks or carry invented key strings in a fake
environ: nothing here calls a network or a model.
"""
import json
import threading
import urllib.request

import pytest

from madd.cli import main
from madd.config import build_providers, effective_mode, validate_config
from madd.gui import create_server
from madd.presets import PRESETS, get_preset, list_presets

ENV = {"PRESET_TEST_KEY": "invented-key"}

EXPECTED_MODES = {"solo": "simple", "solo_judged": "simple_judge",
                  "pair": "dual", "pair_judged": "dual_judge"}


def _mock(name):
    """Build one mock provider entry."""
    return {"name": name, "kind": "mock"}


def _http(name):
    """Build one HTTP provider entry on a distinct model."""
    return {"name": name, "kind": "openai-compatible", "model": "model-a",
            "family": "fam-a", "api_key_env": "PRESET_TEST_KEY"}


def _config_for(preset_name):
    """Build a minimal valid run config for one preset's mode shape:
    one-model presets field two mocks, two-model presets field a
    mock plus an HTTP entry, judged presets add a mock judge."""
    preset = get_preset(preset_name)
    if preset["mode"] in ("simple", "simple_judge"):
        config = {"providers": [_mock("panel-a"), _mock("panel-b")]}
    else:
        config = {"providers": [_mock("panel-a"), _http("panel-b")]}
    if preset["judge_required"]:
        config["judge"] = _mock("judge")
    return config


def test_all_four_presets_expand_to_the_right_mode():
    """Each preset names the protocol mode the task assigns it."""
    assert set(PRESETS) == set(EXPECTED_MODES)
    assert [p["name"] for p in list_presets()] == list(EXPECTED_MODES)
    for name, mode in EXPECTED_MODES.items():
        assert get_preset(name)["mode"] == mode


def test_judge_flags_match_mode_rules():
    """Judge requirements and swap support follow the modes: only
    the judged modes require a judge, and only they support the
    judge-swap experiment. Every preset fields at least two agents."""
    for preset in list_presets():
        judged = preset["mode"] in ("simple_judge", "dual_judge")
        assert preset["judge_required"] is judged
        assert preset["judge_swap_supported"] is judged
        assert preset["min_agents"] == 2
        assert preset["label"] and preset["topology"] and preset["summary"]


def test_unknown_preset_errors():
    """An unknown preset name is an error naming the valid names,
    both from get_preset and from config validation."""
    with pytest.raises(ValueError) as excinfo:
        get_preset("trio")
    for name in EXPECTED_MODES:
        assert name in str(excinfo.value)
    config = _config_for("solo")
    config["preset"] = "trio"
    errors = validate_config(config)
    assert any("preset" in e and "trio" not in e for e in errors)
    assert any("solo" in e for e in errors)


def test_config_with_preset_only_validates_and_yields_mode():
    """A config naming only a preset validates against the preset's
    mode shape, and the built providers carry that mode."""
    for name, mode in EXPECTED_MODES.items():
        config = _config_for(name)
        config["preset"] = name
        assert validate_config(config) == [], name
        assert effective_mode(config) == mode
        built = build_providers(config, environ=dict(ENV))
        assert built["mode"] == mode


def test_config_with_preset_and_agreeing_mode_validates():
    """Preset plus its own mode declared alongside is valid."""
    for name, mode in EXPECTED_MODES.items():
        config = _config_for(name)
        config["preset"] = name
        config["mode"] = mode
        assert validate_config(config) == [], name


def test_config_with_preset_and_disagreeing_mode_fails():
    """Preset plus a different declared mode is a validation error
    naming the preset, its mode, and the declared mode."""
    config = _config_for("solo")
    config["preset"] = "solo"
    config["mode"] = "dual"
    errors = validate_config(config)
    assert errors
    joined = "; ".join(errors)
    assert "solo" in joined and "simple" in joined and "dual" in joined


def test_cli_presets_lists_all_four(capsys):
    """The presets subcommand prints every preset with its mode."""
    assert main(["presets"]) == 0
    out = capsys.readouterr().out
    for name, mode in EXPECTED_MODES.items():
        assert name in out and mode in out


@pytest.fixture()
def gui_server(tmp_path):
    """Provide the running console server on a temporary runs dir."""
    runs = tmp_path / "runs"
    runs.mkdir()
    server = create_server("127.0.0.1", 0, runs_dir=str(runs))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:" + str(server.server_address[1])
    server.shutdown()


def _get_text(url):
    """GET a page from the console test server as text."""
    with urllib.request.urlopen(url, timeout=10) as resp:
        return resp.read().decode()


def _get_json(url):
    """GET a JSON document from the console test server."""
    return json.loads(_get_text(url))


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


def _setup_payload(**overrides):
    """Build a full setup form payload with mock slots."""
    payload = {"primary": _mock_slot(), "secondary": _mock_slot(),
               "judge": _mock_slot(), "mode": "simple_judge",
               "budget": {"max_calls": "", "max_cost_usd": ""},
               "switches": {}}
    payload.update(overrides)
    return payload


def test_setup_page_has_preset_chips(gui_server):
    """The served setup page carries one preset chip per preset,
    each wired to its preset's mode."""
    page = _get_text(gui_server + "/")
    for name, mode in EXPECTED_MODES.items():
        assert 'data-name="' + name + '"' in page
        assert 'data-mode="' + mode + '"' in page
    assert "pickPreset" in page


def test_setup_save_with_preset_roundtrips(gui_server):
    """Saving from the panel with a preset stores it alongside the
    mode, and the setup status reports it back. A preset that
    disagrees with the chosen mode is refused."""
    out = _post(gui_server + "/api/setup",
                _setup_payload(preset="solo_judged"))
    assert out["ok"] is True
    assert _get_json(gui_server + "/api/setup")["preset"] == "solo_judged"
    out = _post(gui_server + "/api/setup",
                _setup_payload(preset="solo"))
    assert out["ok"] is False
