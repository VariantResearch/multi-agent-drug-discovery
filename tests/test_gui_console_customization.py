"""Tests for the console's customizable layout, its installable
PWA shell, and the setup panel's test-as-entered slot smoke test.

The tests boot the real HTTP server against a temporary runs
directory and drive it over HTTP, like the other console tests.
All providers are mocks: nothing here calls a network or a model.
"""
import json
import threading
import urllib.error
import urllib.request

import pytest

from madd.gui import create_server


@pytest.fixture()
def gui(tmp_path):
    """Provide the running console server and its runs directory."""
    runs = tmp_path / "runs"
    runs.mkdir()
    server = create_server("127.0.0.1", 0, runs_dir=str(runs))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:" + str(server.server_address[1]), runs
    server.shutdown()


def _get_json(url):
    """GET a JSON document from the console test server."""
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read().decode())


def _get_raw(url):
    """GET a response as (status, content type, body bytes)."""
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return resp.status, resp.headers.get_content_type(), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get_content_type(), exc.read()


def _post(url, payload):
    """POST a JSON payload to the console test server."""
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _form(**extra):
    """Build one setup form slot, mock by default."""
    form = {"kind": "mock", "model": "", "family": "",
            "base_url": "", "api_key_env": ""}
    form.update(extra)
    return form


def test_layout_defaults_to_builtin_order(gui):
    """With no saved layout the console reports the default order
    with nothing hidden."""
    base, _runs = gui
    layout = _get_json(base + "/api/layout")
    assert layout == {"order": ["setup", "target", "activity", "library"],
                      "hidden": []}


def test_layout_save_and_reload_round_trip(gui):
    """A saved layout is written to the runs directory and read
    back exactly."""
    base, runs = gui
    out = _post(base + "/api/layout",
                {"order": ["library", "setup", "target", "activity"],
                 "hidden": ["activity"]})
    assert out["ok"] is True
    assert (runs / "console-layout.json").exists()
    layout = _get_json(base + "/api/layout")
    assert layout["order"] == ["library", "setup", "target", "activity"]
    assert layout["hidden"] == ["activity"]


def test_layout_refuses_unknown_panel(gui):
    """An unknown panel id refuses the whole save."""
    base, runs = gui
    out = _post(base + "/api/layout",
                {"order": ["setup", "nope"], "hidden": []})
    assert out["ok"] is False
    assert any("nope" in e for e in out["errors"])
    assert not (runs / "console-layout.json").exists()


def test_layout_refuses_non_list_fields(gui):
    """Order and hidden must be lists."""
    base, _runs = gui
    out = _post(base + "/api/layout", {"order": "setup", "hidden": []})
    assert out["ok"] is False


def test_layout_status_completes_a_partial_saved_order(gui):
    """A layout file naming only some panels is completed with the
    remaining panels in their default relative order, so a panel
    added after the layout was saved is never stranded."""
    base, runs = gui
    (runs / "console-layout.json").write_text(
        json.dumps({"order": ["library"], "hidden": ["target"]}),
        encoding="utf-8")
    layout = _get_json(base + "/api/layout")
    assert layout["order"] == ["library", "setup", "target", "activity"]
    assert layout["hidden"] == ["target"]


def test_test_form_mock_slot_ok_and_saves_nothing(gui):
    """Test as entered smoke-tests the form's values and writes no
    setup file."""
    base, runs = gui
    out = _post(base + "/api/setup/test-form",
                {"slot": "primary", "form": _form()})
    assert out["ok"] is True
    assert out["provider"] == "mock"
    assert not (runs / "console-config.json").exists()


def test_test_form_judge_mock_ok(gui):
    """The judge slot can be tested as entered with no setup saved."""
    base, _runs = gui
    out = _post(base + "/api/setup/test-form",
                {"slot": "judge", "form": _form()})
    assert out["ok"] is True


def test_test_form_unassigned_slot_refused(gui):
    """A form with no kind picked is refused with a plain message."""
    base, _runs = gui
    out = _post(base + "/api/setup/test-form",
                {"slot": "secondary", "form": _form(kind="")})
    assert out["ok"] is False
    assert "not filled in" in out["error"]


def test_test_form_unknown_slot_refused(gui):
    """An unknown slot name is refused."""
    base, _runs = gui
    out = _post(base + "/api/setup/test-form",
                {"slot": "swap", "form": _form()})
    assert out["ok"] is False
    assert "unknown slot" in out["error"]


def test_test_form_missing_key_names_the_variable(gui):
    """An HTTP entry whose key variable is absent fails before any
    call, naming the variable and never a value."""
    base, _runs = gui
    out = _post(base + "/api/setup/test-form",
                {"slot": "primary",
                 "form": _form(kind="openai-compatible", model="m",
                               api_key_env="MADD_TEST_FORM_MISSING_KEY")})
    assert out["ok"] is False
    assert "MADD_TEST_FORM_MISSING_KEY" in out["error"]


def test_layout_status_survives_a_scalar_junk_file(gui):
    """A hand-written layout file whose order is a scalar, not a
    list, reads as the default layout instead of crashing the
    status endpoint."""
    base, runs = gui
    (runs / "console-layout.json").write_text(
        json.dumps({"order": 5, "hidden": True}), encoding="utf-8")
    layout = _get_json(base + "/api/layout")
    assert layout == {"order": ["setup", "target", "activity", "library"],
                      "hidden": []}


def test_test_form_judge_ignores_a_broken_saved_setup(gui):
    """Testing a judge as entered is judged on its own fields: a
    saved setup whose primary key variable is missing must not
    fail a valid mock judge."""
    base, _runs = gui
    saved = _post(base + "/api/setup", {
        "primary": _form(kind="openai-compatible", model="m",
                         api_key_env="MADD_TEST_FORM_MISSING_KEY"),
        "secondary": _form(), "judge": _form(kind=""),
        "mode": "dual",
        "budget": {"max_calls": "", "max_cost_usd": ""}, "switches": {}})
    assert saved["ok"] is True
    out = _post(base + "/api/setup/test-form",
                {"slot": "judge", "form": _form()})
    assert out["ok"] is True


def test_test_form_junk_field_types_return_json(gui):
    """A form field of the wrong JSON type (kind as a list) comes
    back as a JSON refusal, not a dropped request."""
    base, _runs = gui
    out = _post(base + "/api/setup/test-form",
                {"slot": "primary", "form": _form(kind=["mock"])})
    assert out["ok"] is False
    assert out["error"]


def test_manifest_route_shape(gui):
    """The manifest is valid JSON with the fields installability
    needs and icons for the served sizes."""
    base, _runs = gui
    status, ctype, body = _get_raw(base + "/manifest.webmanifest")
    assert status == 200
    assert ctype == "application/manifest+json"
    manifest = json.loads(body.decode())
    assert manifest["name"] == "MADD Console"
    assert manifest["start_url"] == "/"
    assert manifest["display"] == "standalone"
    sizes = {icon["sizes"] for icon in manifest["icons"]}
    assert "192x192" in sizes and "512x512" in sizes


def test_service_worker_never_caches_the_api(gui):
    """The service worker source keeps /api/ network-only."""
    base, _runs = gui
    status, ctype, body = _get_raw(base + "/sw.js")
    assert status == 200
    assert ctype == "text/javascript"
    text = body.decode()
    assert "madd-console-shell" in text
    assert "/api/" in text


def test_icon_asset_served_as_png(gui):
    """The icon files are served as real PNG bytes."""
    base, _runs = gui
    status, ctype, body = _get_raw(base + "/assets/icon-192.png")
    assert status == 200
    assert ctype == "image/png"
    assert body[:8] == b"\x89PNG\r\n\x1a\n"


def test_unknown_asset_still_refused(gui):
    """The asset whitelist still refuses anything not on it."""
    base, _runs = gui
    status, _ctype, _body = _get_raw(base + "/assets/gui.py")
    assert status == 404


def test_page_carries_pwa_and_layout_markup(gui):
    """The served page links the manifest, tags every panel with
    its layout id, and carries the layout editor and the
    test-as-entered button label."""
    base, _runs = gui
    status, _ctype, body = _get_raw(base + "/")
    assert status == 200
    page = body.decode()
    assert 'rel="manifest"' in page
    for pid in ("setup", "target", "activity", "library"):
        assert 'data-panel="' + pid + '"' in page
    assert 'id="layout-editor"' in page
    assert "TEST AS ENTERED" in page
