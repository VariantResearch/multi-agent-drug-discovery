"""Structural alert tests: curated catalogs, advisory only."""

import json
from pathlib import Path

import pytest

from madd import cli
from madd.structural_alerts import alerts_for_bundle, alerts_for_smiles
from madd.workbench import build_workbench

ROOT = Path(__file__).resolve().parent.parent
MTCH2 = ROOT / "designer-output" / "target-mtch2-inhibition-2026-10-25"

pytestmark = pytest.mark.skipif(
    alerts_for_smiles("CCO")["status"] == "unavailable",
    reason="RDKit not installed")


def test_catechol_matches_all_three_catalogs():
    """The classic PAINS motif is flagged by name in each set."""
    result = alerts_for_smiles("Oc1ccccc1O")
    assert result["status"] == "ok"
    sets = {a["set"] for a in result["alerts"]}
    assert sets == {"PAINS", "BRENK", "NIH"}
    assert any("catechol" in a["pattern"] for a in result["alerts"])


def test_clean_structures_have_no_alerts():
    """Caffeine and the recorded MTCH2 leads match nothing."""
    assert alerts_for_smiles("CN1C=NC2=C1C(=O)N(C(=O)N2C)C")["alerts"] == []
    bundle = json.loads((MTCH2 / "bundle.json").read_text())
    results = {r["candidate_id"]: r for r in alerts_for_bundle(bundle)}
    assert results["panel-b-cand-1"]["alerts"] == []
    assert results["panel-a-cand-1"]["alerts"] == []
    assert results["panel-b-cand-2"]["status"] == "not_applicable"
    assert results["panel-a-cand-2"]["status"] == "not_applicable"


def test_invalid_smiles_reports_invalid_not_empty():
    """An unparseable structure is 'invalid', never a quiet pass."""
    assert alerts_for_smiles("not-a-smiles")["status"] == "invalid"


def test_workbench_shows_the_alerts_row():
    """Small molecules get a computed alerts row reading 'none'."""
    workbench = build_workbench(
        json.loads((MTCH2 / "bundle.json").read_text()))
    row = next(r for r in workbench["rows"]
               if r["name"] == "structural_alerts")
    assert row["group"] == "Structural alerts (computed)"
    assert row["values"][0] == "none"
    assert row["values"][1] is None
    assert "advisory flags" in workbench["note"]


def test_cli_prints_per_candidate_lines(capsys):
    """The alerts command reports each candidate in recorded order."""
    code = cli.main(["alerts", str(MTCH2)])
    out = capsys.readouterr().out
    assert code == 0
    assert "panel-b-cand-1: none" in out
    assert "panel-b-cand-2: not applicable" in out
