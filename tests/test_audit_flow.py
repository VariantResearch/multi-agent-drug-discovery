"""Audit flow tests: the waterfall counts come from the record."""

import json
import threading
import urllib.request
from pathlib import Path

from madd.audit_flow import audit_flow, audit_flow_of_bundle, record_of_bundle

ROOT = Path(__file__).resolve().parent.parent
MTCH2 = ROOT / "designer-output" / "target-mtch2-inhibition-2026-10-25"


def _mtch2_record():
    """The frozen MTCH2 inhibition debate record."""
    bundle = json.loads((MTCH2 / "bundle.json").read_text())
    return bundle["frame_run"]["record"]


def test_flow_counts_the_real_record():
    """The MTCH2 flow: 12 struck (all one reason), 6 in spec, locked."""
    flow = audit_flow(_mtch2_record())
    stages = {s["key"]: s for s in flow["stages"]}
    assert stages["struck"]["count"] == 12
    assert stages["struck"]["by_reason"] == {"quote_not_in_full_text": 12}
    assert stages["spec"]["count"] == 6
    assert stages["outcome"]["value"] == "locked"
    assert stages["outcome"]["consensus_total"] >= 1
    assert stages["outcome"]["consensus_passed"] == \
        stages["outcome"]["consensus_total"]
    assert "contested" not in stages
    assert flow["claims_merged"] == 6


def test_contested_stage_appears_only_when_recorded():
    """A record carrying contested claims gains the contested stage."""
    record = {"strike_list": [], "outcome": "no_go",
              "spec": {"claims": [{"claim_id": "c1"}],
                       "contested_claims": [{"claim_id": "c2"},
                                            {"claim_id": "c3"}]},
              "evolution": {"contributing_dossiers": ["d1"]},
              "consensus": {"results": []}}
    flow = audit_flow(record)
    keys = [s["key"] for s in flow["stages"]]
    assert keys == ["dossiers", "struck", "contested", "spec", "outcome"]
    assert flow["stages"][2]["count"] == 2


def test_record_of_bundle_shapes():
    """Target and frame bundles resolve; design and Gate 0 do not."""
    bundle = json.loads((MTCH2 / "bundle.json").read_text())
    assert record_of_bundle(bundle) is bundle["frame_run"]["record"]
    frame = {"kind": "frame_run", "record": {"outcome": "no_go"}}
    assert record_of_bundle(frame) is frame["record"]
    assert record_of_bundle({"kind": "design_run"}) is None
    assert record_of_bundle({"kind": "gate0_run"}) is None
    assert audit_flow_of_bundle({"kind": "design_run"}) is None


def test_audit_flow_endpoint_serves_the_flow(tmp_path):
    """The console serves the flow for a target run, null for others.

    Starting a server points MADD_REGISTRY_CACHE at its runs
    directory by writing the process environment directly, so the
    test saves and restores that variable itself (a monkeypatch
    restore does not cover a direct write) and resets the config
    module's cached registry fetcher, so no later test inherits
    either.
    """
    import os
    import shutil

    from madd import config
    from madd.gui import create_server
    saved_cache = os.environ.pop("MADD_REGISTRY_CACHE", None)
    runs = tmp_path / "runs"
    target_dir = runs / "target-mtch2-inhibition-2026-10-25"
    target_dir.mkdir(parents=True)
    shutil.copy(MTCH2 / "bundle.json", target_dir / "bundle.json")
    server = create_server("127.0.0.1", 0, runs_dir=str(runs))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:" + str(server.server_address[1])
    try:
        with urllib.request.urlopen(
                base + "/api/runs/target-mtch2-inhibition-2026-10-25"
                       "/audit-flow", timeout=30) as resp:
            payload = json.loads(resp.read().decode())
    finally:
        server.shutdown()
        config._REGISTRY_FETCHER = None
        if saved_cache is None:
            os.environ.pop("MADD_REGISTRY_CACHE", None)
        else:
            os.environ["MADD_REGISTRY_CACHE"] = saved_cache
    stages = {s["key"]: s for s in payload["audit_flow"]["stages"]}
    assert stages["spec"]["count"] == 6
