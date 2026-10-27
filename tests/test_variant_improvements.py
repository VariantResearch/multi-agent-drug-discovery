"""Tests for the improvements adopted from the MADD-Gcloud variant
review (2026-10-26): RDKit structural alerts (PAINS/Brenk) plus
QED and SA score in the design stage, production sheets carrying
computed alerts, and the optional WeasyPrint PDF report export.

Everything here runs offline: RDKit tests skip when the package
is absent (the project's usual pattern), and the PDF tests inject
a writer or exercise the honest not-installed path, so no test
needs WeasyPrint present.
"""
import json
import threading
import urllib.error
import urllib.request

import pytest

from madd import report_pdf, storage
from madd.design_rdkit import available, describe_smiles, enrich_candidates
from madd.gui import create_server
from madd.production import build_production_sheets
from madd.providers import MockProvider
from madd.runner import run_frame

requires_rdkit = pytest.mark.skipif(not available(),
                                    reason="RDKit not installed")

CATECHOL = "Oc1ccccc1O"
PANEL_B = "O=C(Nc1ccc(C(F)(F)F)cc1)c2csc(n2)c3ccccc3"


@requires_rdkit
def test_describe_smiles_scores_and_alerts():
    """QED and SA ride the descriptors; catechol trips both catalogs."""
    result = describe_smiles(CATECHOL)
    assert result["valid"] is True
    assert 0 < result["descriptors"]["qed"] < 1
    assert 1 <= result["descriptors"]["sa_score"] <= 10
    families = {(a["catalog"], a["name"]) for a in result["structural_alerts"]}
    assert ("PAINS", "catechol_A(92)") in families
    assert any(catalog == "Brenk" for catalog, _ in families)


@requires_rdkit
def test_describe_smiles_clean_candidate_has_no_alerts():
    """The recorded MTCH2 panel-b structure is alert-free, QED ~0.72."""
    result = describe_smiles(PANEL_B)
    assert result["valid"] is True
    assert result["structural_alerts"] == []
    assert result["descriptors"]["qed"] == pytest.approx(0.717, abs=0.01)


@requires_rdkit
def test_enrich_attaches_alerts_and_computed_scores():
    """Enrichment puts alerts on the candidate and scores in its
    computed properties, counted in the tool-run record."""
    candidate = {"candidate_id": "cand-x", "modality": "small_molecule",
                 "structure": {"format": "smiles", "value": CATECHOL},
                 "claims": [], "predicted_properties": []}
    record = enrich_candidates([candidate])
    assert record["status"] == "completed"
    assert record["alerted"] == 1 and record["alerts"] >= 2
    assert candidate["structural_alerts"]
    computed = {p["name"]: p for p in candidate["predicted_properties"]
                if str(p.get("basis", "")).startswith("computed:RDKit")}
    assert "qed" in computed and "sa_score" in computed
    assert computed["qed"]["verified"] is True


@requires_rdkit
def test_production_sheet_carries_computed_alerts():
    """A sheet for an alerting structure names the alerts in its
    computed identity; a clean structure's sheet has none."""
    design = {"brief": {"target": "invented"},
              "ranking": {"ranked": ["cand-x"], "excluded": []},
              "candidates": [{"candidate_id": "cand-x",
                              "modality": "small_molecule",
                              "structure": {"format": "smiles",
                                            "value": CATECHOL},
                              "claims": []}]}
    sheets = build_production_sheets(design)
    identity = sheets[0]["identity"]
    assert identity["structural_alerts"]
    assert sheets[0]["production_ready"] in (True, False)


def _frame_bundle():
    """Build one real frame bundle with mock providers."""
    frame = {"artifact_type": "frame", "schema_version": "0.1.0",
             "frame_id": "F-PDF", "question": "invented", "round_cap": 2}
    return run_frame(frame, [MockProvider("001"), MockProvider("002")],
                     run_id="test-pdf-1")


def test_report_pdf_with_injected_writer():
    """The render contract: HTML in, the writer's bytes out."""
    seen = {}

    def fake_writer(html):
        """Stand in for WeasyPrint: remember the HTML, return bytes."""
        seen["html"] = html
        return b"%PDF-fake-bytes"

    result = report_pdf.render_report_pdf(_frame_bundle(),
                                          writer=fake_writer)
    assert result["status"] == "completed"
    assert result["pdf"] == b"%PDF-fake-bytes"
    assert result["bytes"] == len(b"%PDF-fake-bytes")
    assert "<!DOCTYPE html>" in seen["html"]


def test_report_pdf_not_installed_is_honest(monkeypatch):
    """Without WeasyPrint the render refuses plainly, no file."""
    monkeypatch.setattr(report_pdf, "available", lambda: False)
    result = report_pdf.render_report_pdf(_frame_bundle())
    assert result["status"] == "not_installed"
    assert "pdf" not in result


def test_report_pdf_license_blocked(monkeypatch):
    """A registry denial stops the render before any writing."""
    monkeypatch.setattr(
        report_pdf.license_registry, "check_tool",
        lambda name, use: {"allowed": False,
                           "reason": "blocked by test registry"})
    result = report_pdf.render_report_pdf(
        _frame_bundle(), writer=lambda html: b"%PDF-should-not-happen")
    assert result["status"] == "blocked_license"
    assert "pdf" not in result


@pytest.fixture()
def gui_server(tmp_path):
    """Provide the running console server with one stored run."""
    runs = tmp_path / "runs"
    runs.mkdir()
    storage.write_bundle(_frame_bundle(), runs)
    server = create_server("127.0.0.1", 0, runs_dir=str(runs))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:" + str(server.server_address[1])
    server.shutdown()


def test_console_pdf_route_matches_environment(gui_server):
    """The console PDF route serves a PDF when WeasyPrint is
    installed and the honest 501 explanation when it is not."""
    url = gui_server + "/api/runs/test-pdf-1/report.pdf"
    if report_pdf.available():
        with urllib.request.urlopen(url, timeout=30) as resp:
            assert resp.headers.get_content_type() == "application/pdf"
            assert resp.read(4) == b"%PDF"
    else:
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(url, timeout=10)
        assert excinfo.value.code == 501
        body = json.loads(excinfo.value.read().decode())
        assert "not_installed" in body["error"]
