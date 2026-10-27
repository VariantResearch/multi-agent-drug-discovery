"""Tests for the calibration report: agreement-bucketed accuracy
over Gate 0 bundles against the sealed outcomes.

Synthetic records pin the bucketing and counting math; a stub
Gate 0 run and the CLI cover the real shapes. (Calibration is a
CLI tool: the console carries no Gate 0 surface.)
"""
import json
import subprocess
import sys
from pathlib import Path

from madd.calibration import (calibration_report, case_bucket,
                              format_calibration)
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


def test_calibration_cli_over_a_bundle_file(tmp_path):
    """The CLI prints the table for a bundle file on disk."""
    a = CaseStub("a", set(DRUGS.values()))
    b = CaseStub("b", set(DRUGS.values()))
    bundle = run_gate0([a, b], judge_provider=CaseStub("j", set(DRUGS.values())),
                       baseline_provider=CaseStub("base", set()),
                       gate0_dir=GATE0, run_id="test-calib-cli")
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(bundle))
    out = subprocess.run(
        [sys.executable, "-m", "madd", "calibration", str(path)],
        capture_output=True, text=True,
        cwd=str(Path(__file__).resolve().parent.parent))
    assert out.returncode == 0
    assert "mode legacy: 4/8 correct (accuracy 0.5)" in out.stdout
    assert "unanimous    4/8 (accuracy 0.5)" in out.stdout
