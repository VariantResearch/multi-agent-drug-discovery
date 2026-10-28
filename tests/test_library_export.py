"""Library export tests: one honest screening table across runs."""

import csv
import json
import shutil
from pathlib import Path

from madd import cli
from madd.library_export import build_library, write_library_csv

ROOT = Path(__file__).resolve().parent.parent
MTCH2 = ROOT / "designer-output" / "target-mtch2-inhibition-2026-10-25"
KRAS = ROOT / "runs" / "target-kras-g12c-validation-2026-10-25"


def _runs(tmp_path):
    """A runs directory holding both designed runs on record."""
    runs = tmp_path / "runs"
    for source in (MTCH2, KRAS):
        target = runs / source.name
        target.mkdir(parents=True)
        shutil.copy(source / "bundle.json", target / "bundle.json")
    return runs


def test_library_spans_runs_with_computed_columns_only(tmp_path):
    """Rows from both runs; computed columns present, designer-only
    property names absent, ASO computed cells empty."""
    fieldnames, rows = build_library(_runs(tmp_path))
    assert {r["run_id"] for r in rows} == {
        "target-mtch2-inhibition-2026-10-25",
        "target-kras-g12c-validation-2026-10-25"}
    assert "admet:DILI" in fieldnames
    assert "molecular_weight" in fieldnames
    assert "estimated_molecular_weight" not in fieldnames
    assert "predicted_logP" not in fieldnames
    by_id = {r["candidate_id"]: r for r in rows
             if r["run_id"].startswith("target-mtch2")}
    assert by_id["panel-b-cand-1"]["rank"] == 1
    assert by_id["panel-b-cand-1"]["formula"] == "C17H11F3N2OS"
    assert float(by_id["panel-b-cand-1"]["molecular_weight"]) > 300
    assert by_id["panel-b-cand-2"]["molecular_weight"] is None
    assert by_id["panel-b-cand-2"]["admet:DILI"] is None


def test_csv_round_trip_and_cli(tmp_path, capsys):
    """The written CSV parses back with the same shape, via the CLI."""
    runs = _runs(tmp_path)
    out = tmp_path / "library.csv"
    code = cli.main(["export-library", "--runs", str(runs),
                     "--out", str(out)])
    text = capsys.readouterr().out
    assert code == 0
    assert "candidates: 8" in text
    with open(out, newline="", encoding="utf-8") as handle:
        parsed = list(csv.DictReader(handle))
    assert len(parsed) == 8
    assert parsed[0]["status"] == "ranked"
    summary = write_library_csv(runs, tmp_path / "again.csv")
    assert summary["runs_with_design"] == 2
    assert summary["property_columns"] >= 20
