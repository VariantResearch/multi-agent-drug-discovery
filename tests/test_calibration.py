"""Tests for the calibration report: agreement-bucketed accuracy
over Gate 0 bundles against the sealed outcomes.

Synthetic records pin the bucketing and counting math; a stub
Gate 0 run and the console endpoint cover the real shapes.
"""
import json
import threading
import urllib.request

import pytest

from madd import storage
from madd.calibration import (calibration_report, case_bucket,
                              format_calibration)
from madd.gui import create_server
from madd.runner import run_gate0
from tests.test_runner import CaseStub, DRUGS, GATE0

POS = "evolocumab-pcsk9-cvd"    # sealed positive
NEG = "verubecestat-bace1-alzheimer"   # sealed negative


def _record(outcome, proposals):
    """Build a minimal debate record with the given ranking shape."""
    return {"outcome": outcome,
            "ranking": [{"proposed_focus_id": focus} for focus in proposals]}


def test_case_bucket_shapes():
    """Unanimous, majority, split, and empty rankings bucket right."""
    assert case_bucket(_record("locked", ["A", "A"])) == "unanimous"
    assert case_bucket(_record("locked", ["A", "A", "B"])) == "majority"
    assert case_bucket(_record("locked", ["A", "B"])) == "split"
    assert case_bucket(_record("no_go", [])) == "no_proposals"
    assert case_bucket(_record("locked", [None, "A"])) == "unanimous"


def test_report_counts_buckets_and_modes():
    """Bucketed accuracy: unanimous advance on a positive scores,
    a split no-go on a positive misses, a majority lock on a
    negative misses."""
    bundle = {"kind": "gate0_run", "mode": "dual_judge",
              "case_records": {
                  POS: _record("locked", ["PCSK9", "PCSK9"]),
                  NEG: _record("locked", ["BACE1", "BACE1", "OTHER"])}}
    other = {"kind": "gate0_run", "mode": "simple",
             "case_records": {POS: _record("no_go", ["X", "Y"])}}
    report = calibration_report([bundle, other], gate0_dir=GATE0)
    assert report["runs"] == 2 and report["unscored"] == 0
    dual = report["modes"]["dual_judge"]
    assert dual["cases"] == 2 and dual["correct"] == 1
    assert dual["buckets"]["unanimous"] == {
        "cases": 1, "correct": 1, "accuracy": 1.0}
    assert dual["buckets"]["majority"]["accuracy"] == 0.0
    simple = report["modes"]["simple"]
    assert simple["buckets"]["split"] == {
        "cases": 1, "correct": 0, "accuracy": 0.0}
    assert report["overall"]["cases"] == 3
    text = format_calibration(report)
    assert "mode dual_judge: 1/2 correct" in text
    assert "not guarantees" in text


def test_report_over_a_real_stub_bundle():
    """Calibration over a real stub bundle agrees with the bundle's
    own debate score: the lock-everything stubs advance all eight
    cases, so the four positives score and the four negatives miss,
    every case unanimous."""
    a = CaseStub("a", set(DRUGS.values()))
    b = CaseStub("b", set(DRUGS.values()))
    bundle = run_gate0([a, b], judge_provider=CaseStub("j", set(DRUGS.values())),
                       baseline_provider=CaseStub("base", set()),
                       gate0_dir=GATE0, run_id="test-calib-real")
    report = calibration_report([bundle], gate0_dir=GATE0)
    group = report["modes"]["legacy"]
    assert group["cases"] == 8
    assert group["correct"] == bundle["debate_score"]["correct_calls"] == 4
    assert group["buckets"]["unanimous"] == {
        "cases": 8, "correct": 4, "accuracy": 0.5}


@pytest.fixture()
def gui_server(tmp_path):
    """Provide the console server with one stored stub Gate 0 run."""
    runs = tmp_path / "runs"
    runs.mkdir()
    a = CaseStub("a", set(DRUGS.values()))
    b = CaseStub("b", set(DRUGS.values()))
    bundle = run_gate0([a, b], judge_provider=CaseStub("j", set(DRUGS.values())),
                       baseline_provider=CaseStub("base", set()),
                       gate0_dir=GATE0, run_id="test-calib-gui")
    storage.write_bundle(bundle, runs)
    server = create_server("127.0.0.1", 0, runs_dir=str(runs),
                           gate0_dir=str(GATE0))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:" + str(server.server_address[1])
    server.shutdown()


def test_console_calibration_endpoint(gui_server):
    """The endpoint aggregates the stored Gate 0 bundles."""
    with urllib.request.urlopen(gui_server + "/api/calibration",
                                timeout=30) as resp:
        report = json.loads(resp.read().decode())
    assert report["runs"] == 1
    assert report["overall"]["cases"] == 8
    assert report["overall"]["accuracy"] == 0.5
