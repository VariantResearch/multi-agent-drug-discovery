"""Tests for the nine-item build of 2026-10-26: cooperative stop,
parallel design source checks, design event persistence,
pre-registration, AlphaFold fetch, docking records, preflight,
the run header fields, and the library index target field.

Network-shaped pieces run on canned fetchers; the docking
end-to-end path is covered by the recorded spike (indinavir
into HIV-1 protease, PDB 1HSG) and by the console live check,
not by this suite.
"""
import json
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd import docking, storage
from madd.prereg import (build_preregistration, verify_preregistration,
                         write_preregistration)
from madd.providers import MockProvider
from madd.runner import run_gate0
from madd.target_run import build_target_frame, run_target
from tests.test_runner import CaseStub, DRUGS, GATE0


def test_preregistration_hash_and_tamper():
    """A built pre-registration verifies; any edit breaks it."""
    frame = build_target_frame("PREREG-T", "target")
    record = build_preregistration(
        frame, [MockProvider("a"), MockProvider("b")], mode="dual")
    assert verify_preregistration(record)
    record["mode"] = "simple"
    assert not verify_preregistration(record)


def test_target_run_carries_preregistration(tmp_path):
    """A target run with a prereg dir writes the record before
    running and carries its reference in the bundle."""
    frame = build_target_frame("PREREG-RUN", "target")
    bundle = run_target(frame, [MockProvider("a1"), MockProvider("a2")],
                        prereg_dir=tmp_path)
    ref = bundle["preregistration"]
    path = tmp_path / "preregistrations" / ref["file"]
    assert path.exists()
    record = json.loads(path.read_text())
    assert record["sha256"] == ref["sha256"]
    assert verify_preregistration(record)


def test_stop_gate0_partial_bundle():
    """A stop requested after the first case check yields a
    stopped bundle with only completed cases and thresholds
    recorded as not evaluated."""
    checks = {"n": 0}

    def stop_after_first():
        """Trip after the first case starts."""
        checks["n"] += 1
        return checks["n"] > 1

    a = CaseStub("a", set(DRUGS.values()))
    b = CaseStub("b", set(DRUGS.values()))
    bundle = run_gate0([a, b],
                       judge_provider=CaseStub("j", set(DRUGS.values())),
                       baseline_provider=CaseStub("base", set()),
                       gate0_dir=GATE0, run_id="test-stop",
                       should_stop=stop_after_first)
    assert bundle["outcome"] == "stopped"
    assert bundle["stopped"]["total_cases"] == 8
    assert len(bundle["case_records"]) == bundle["stopped"]["completed_cases"]
    assert bundle["thresholds"]["overall"] == "not_evaluated"


def test_stop_target_run_skips_design():
    """A target run stopped before its judge phase ends with
    outcome stopped and no design stage."""
    frame = build_target_frame("STOP-T", "target")
    bundle = run_target(frame, [MockProvider("a1"), MockProvider("a2")],
                        should_stop=lambda: True)
    assert bundle["outcome"] == "stopped"
    assert bundle["design"] is None
    assert bundle["frame_run"]["record"]["stopped"] is True


def test_parallel_source_check_matches_serial():
    """The fanned-out design source check produces the same
    record and per-candidate results as the serial path."""
    from madd import design_sources

    def canned(url):
        """Canned registry answers keyed by URL shape."""
        if "pubchem" in url:
            return 200, '{"IdentifierList": {"CID": [123]}}'
        return 200, '{"molecules": []}'

    def fresh():
        """Two identical SMILES candidates."""
        return [{"candidate_id": "c1",
                 "structure": {"format": "smiles", "value": "CCO"}},
                {"candidate_id": "c2",
                 "structure": {"format": "smiles", "value": "CCO"}}]

    serial = design_sources.check_candidates(fresh(), fetcher=canned,
                                             max_workers=1)
    parallel_candidates = fresh()
    parallel = design_sources.check_candidates(
        parallel_candidates, fetcher=canned, max_workers=4)
    assert serial == parallel
    assert all(c["source_check"]["status"] == "known"
               for c in parallel_candidates)


def test_fetch_receptor_with_canned_services(tmp_path):
    """AlphaFold fetch: resolve, download, cache, register,
    all labelled predicted with the model identity."""
    import madd.structure3d as s3

    pdb = "ATOM      1  CA  ALA A   1       0.0     0.0     0.0\nEND\n"

    def canned(url):
        """Canned UniProt, AlphaFold, and PDB responses."""
        if "rest.uniprot.org" in url:
            return 200, '{"results": [{"primaryAccession": "P99999"}]}'
        if "alphafold.ebi.ac.uk/api" in url:
            return 200, ('[{"pdbUrl": "https://x.test/P99999.pdb",'
                         ' "modelEntityId": "AF-P99999-F1",'
                         ' "latestVersion": 6,'
                         ' "globalMetricValue": 91.2,'
                         ' "gene": "FETCHT"}]')
        if url.endswith("P99999.pdb"):
            return 200, pdb
        return 404, ""

    try:
        record = s3.fetch_receptor("FETCHT", fetcher=canned,
                                   cache_dir=tmp_path)
        assert record["kind"] == "predicted"
        assert "AF-P99999-F1" in record["detail"]
        assert (tmp_path / "P99999.pdb").exists()
        assert s3.receptor_for_target("FETCHT")["data"] == pdb
    finally:
        s3.RECEPTORS.pop("FETCHT", None)


def test_docking_availability_and_pose_parsing():
    """Docking reports availability honestly, and its PDBQT
    parsing reads a Vina result line and converts a pose."""
    check = docking.available()
    assert "available" in check and "problems" in check
    pdbqt = ("REMARK VINA RESULT: -8.5 0.000 0.000\n"
             "MODEL 1\n"
             "ATOM      1  C   LIG A   1       1.000   2.000   3.000"
             "  0.000  1.00 C\n"
             "ENDMDL\n")
    assert docking._best_affinity(pdbqt) == -8.5
    pose = docking._pose_pdb(pdbqt)
    assert "HETATM" in pose and "1.000" in pose


def test_library_index_carries_target(tmp_path):
    """Written bundles index their target name for the library's
    search and target column."""
    frame = build_target_frame("INDEX-T", "target")
    bundle = run_target(frame, [MockProvider("a1"), MockProvider("a2")])
    storage.write_bundle(bundle, tmp_path)
    entries = storage.list_runs(tmp_path)
    assert entries[0]["target"] == "INDEX-T"


def _serve(runs):
    """Start a console server on an ephemeral port."""
    from madd.gui import create_server
    server = create_server("127.0.0.1", 0, runs_dir=str(runs))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, "http://127.0.0.1:" + str(server.server_address[1])


def _post(base, path, payload):
    """POST JSON to the console test server."""
    req = urllib.request.Request(
        base + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _get(base, path):
    """GET JSON from the console test server."""
    with urllib.request.urlopen(base + path, timeout=30) as resp:
        return json.loads(resp.read().decode())


def test_preflight_endpoint_and_progress_fields(tmp_path):
    """Preflight prices the saved setup, and progress carries
    the run header fields."""
    from tests.test_gui_setup_target import _setup_payload
    runs = tmp_path / "runs"
    runs.mkdir()
    server, base = _serve(runs)
    try:
        _post(base, "/api/setup", _setup_payload())
        out = _post(base, "/api/target-preflight", {})
        assert out["ok"]
        assert out["estimate"]["total_calls"] == \
            out["estimate"]["debate_calls"] + out["estimate"]["design_calls"]
        progress = _get(base, "/api/progress")
        for field in ("started_at", "calls_made", "spent_usd",
                      "max_calls", "stopping"):
            assert field in progress
        stopped = _post(base, "/api/stop", {})
        assert stopped["ok"] is False  # no run is active
    finally:
        server.shutdown()
        server.server_close()


def test_design_run_persists_its_event_stream(tmp_path):
    """Designing from a locked frame run through the console
    writes events.jsonl with the design stage's events."""
    from tests.test_design import locked_spec
    bundle = {"kind": "frame_run", "run_id": "nine-frame",
              "frame_id": "F-NINE", "outcome": "locked",
              "record": {"spec": locked_spec()}}
    runs = tmp_path / "runs"
    storage.write_bundle(bundle, runs)
    server, base = _serve(runs)
    try:
        out = _post(base, "/api/design-run", {"run_id": "nine-frame"})
        assert out["ok"], out
        events_path = runs / out["run_id"] / "events.jsonl"
        assert events_path.exists()
        names = [json.loads(line)["event"]
                 for line in events_path.read_text().splitlines()]
        assert names == ["design_started", "candidates_designed",
                         "design_gate_evaluated"]
        replay = _get(base, "/api/runs/" + out["run_id"] + "/events")
        assert len(replay["events"]) == 3
    finally:
        server.shutdown()
        server.server_close()
