"""Claim graph tests: the graph carries only what the record does."""

import json
import threading
import urllib.request
from pathlib import Path

from madd.claim_graph import build_claim_graph, claim_graph_of_bundle

ROOT = Path(__file__).resolve().parent.parent
MTCH2 = ROOT / "designer-output" / "target-mtch2-inhibition-2026-10-25"


def _mtch2_record():
    """The frozen MTCH2 inhibition debate record."""
    bundle = json.loads((MTCH2 / "bundle.json").read_text())
    return bundle["frame_run"]["record"]


def test_graph_of_the_real_record():
    """6 claims in spec citing 5 sources, 12 struck, 1 spec node."""
    graph = build_claim_graph(_mtch2_record())
    kinds = {}
    for node in graph["nodes"]:
        kinds.setdefault(node["data"]["kind"], 0)
        kinds[node["data"]["kind"]] += 1
    assert kinds == {"source": 5, "claim": 18, "spec": 1}
    labels = sorted(e["data"]["label"] for e in graph["edges"])
    assert labels == ["cites"] * 6 + ["in spec"] * 6
    struck = [n["data"] for n in graph["nodes"]
              if n["data"].get("status") == "struck"]
    assert len(struck) == 12
    assert all(s["reasons"] == ["quote_not_in_full_text"] for s in struck)
    assert graph["aggregated_struck"] == 0


def test_struck_claims_aggregate_past_the_threshold():
    """A synthetic 200-strike record collapses struck nodes by reason."""
    record = {"spec": {"spec_id": "S1", "claims": []},
              "strike_list": [
                  {"claim_id": f"c{i}", "dossier_id": "d1",
                   "reasons": ["quote_not_in_source"]}
                  for i in range(200)]}
    graph = build_claim_graph(record)
    struck = [n["data"] for n in graph["nodes"]
              if n["data"].get("status") == "struck"]
    assert len(struck) == 1
    assert struck[0]["count"] == 200
    assert graph["aggregated_struck"] == 200


def test_bundle_without_a_record_has_no_graph():
    """Design bundles return None rather than an empty graph."""
    assert claim_graph_of_bundle({"kind": "design_run"}) is None


def test_graph_endpoint_and_asset_are_served(tmp_path):
    """The console serves the graph JSON and the vendored library."""
    import os
    import shutil

    from madd import config
    from madd.gui import create_server
    saved_cache = os.environ.pop("MADD_REGISTRY_CACHE", None)
    runs = tmp_path / "runs"
    target = runs / "target-mtch2-inhibition-2026-10-25"
    target.mkdir(parents=True)
    shutil.copy(MTCH2 / "bundle.json", target / "bundle.json")
    server = create_server("127.0.0.1", 0, runs_dir=str(runs))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:" + str(server.server_address[1])
    try:
        with urllib.request.urlopen(
                base + "/api/runs/target-mtch2-inhibition-2026-10-25"
                       "/claim-graph", timeout=30) as resp:
            payload = json.loads(resp.read().decode())
        with urllib.request.urlopen(
                base + "/assets/cytoscape.min.js", timeout=30) as resp:
            asset = resp.read().decode()
    finally:
        server.shutdown()
        config._REGISTRY_FETCHER = None
        if saved_cache is None:
            os.environ.pop("MADD_REGISTRY_CACHE", None)
        else:
            os.environ["MADD_REGISTRY_CACHE"] = saved_cache
    assert len(payload["claim_graph"]["nodes"]) == 24
    assert "Cytoscape" in asset[:400]
