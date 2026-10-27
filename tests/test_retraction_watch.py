"""Retraction watch tests: notices mapped, bundles never touched."""

import hashlib
import json
import shutil
from pathlib import Path

from madd import cli, retraction_watch
from madd.retraction_watch import collect_cited_sources, watch

ROOT = Path(__file__).resolve().parent.parent
MTCH2 = ROOT / "designer-output" / "target-mtch2-inhibition-2026-10-25"


def _runs_with_mtch2(tmp_path):
    """A runs directory holding the frozen MTCH2 target bundle."""
    runs = tmp_path / "runs"
    target = runs / "target-mtch2-inhibition-2026-10-25"
    target.mkdir(parents=True)
    shutil.copy(MTCH2 / "bundle.json", target / "bundle.json")
    return runs


def _epmc_retracted(url):
    """Fake Europe PMC: one PMID retracted, everything else quiet."""
    if "38882047" in url:
        return {"resultList": {"result": [{
            "pubTypeList": {"pubType": ["Journal Article",
                                        "Retracted Publication"]},
            "commentCorrectionList": {"commentCorrection": [
                {"id": "39000000", "source": "MED",
                 "type": "Retraction in"}]},
        }]}}
    return {"resultList": {"result": []}}


def test_collect_finds_the_records_pmids(tmp_path):
    """The MTCH2 record's surviving claims yield their PMIDs."""
    cited = collect_cited_sources(_runs_with_mtch2(tmp_path))
    pmids = {ident for (t, ident) in cited if t == "pmid"}
    assert "38882047" in pmids
    assert all(claims for slot in cited.values()
               for claims in slot["runs"].values())


def test_watch_reports_retraction_and_never_touches_bundles(tmp_path):
    """A retracted cited PMID lands in the overlay, bundle intact."""
    runs = _runs_with_mtch2(tmp_path)
    bundle_file = runs / "target-mtch2-inhibition-2026-10-25" / "bundle.json"
    before = hashlib.sha256(bundle_file.read_bytes()).hexdigest()
    report = watch(runs, fetch_json=_epmc_retracted, today="2026-10-27")
    after = hashlib.sha256(bundle_file.read_bytes()).hexdigest()
    assert before == after
    assert report["sources_checked"] == 4
    assert len(report["findings"]) == 1
    finding = report["findings"][0]
    assert finding["identifier"] == "38882047"
    assert finding["severity"] == "retraction"
    assert "target-mtch2-inhibition-2026-10-25" in finding["cited_by"]
    overlay = json.loads((runs / "retraction-overlay.json").read_text())
    assert overlay["checked_on"] == "2026-10-27"


def test_crossref_correction_is_informational_not_retraction(tmp_path):
    """A Crossref correction maps to the correction severity only."""
    runs = tmp_path / "runs"
    frame_dir = runs / "frame-doi-1"
    frame_dir.mkdir(parents=True)
    bundle = {"kind": "frame_run", "run_id": "frame-doi-1",
              "frame_id": "F-DOI",
              "record": {"outcome": "locked",
                         "spec": {"claims": [{
                             "claim_id": "c1",
                             "source_identifier": "10.1000/xyz",
                             "identifier_type": "doi"}]},
                         "strike_list": []}}
    (frame_dir / "bundle.json").write_text(json.dumps(bundle))

    def fake_crossref(url):
        """Fake Crossref: the DOI carries one correction notice."""
        assert "10.1000%2Fxyz" in url
        return {"message": {"updated-by": [{
            "type": "correction", "label": "Correction",
            "DOI": "10.1000/xyz-corr",
            "updated": {"date-parts": [[2026, 3, 4]]}}]}}

    report = watch(runs, fetch_json=fake_crossref, today="2026-10-27")
    assert len(report["findings"]) == 1
    finding = report["findings"][0]
    assert finding["severity"] == "correction"
    assert finding["notices"][0]["notice_doi"] == "10.1000/xyz-corr"
    assert finding["notices"][0]["date"] == "2026-3-4"


def test_quiet_sources_produce_no_findings(tmp_path):
    """No notices anywhere: empty findings, honest checked count."""
    report = watch(_runs_with_mtch2(tmp_path),
                   fetch_json=lambda url: {"resultList": {"result": []}},
                   today="2026-10-27")
    assert report["findings"] == []
    assert report["sources_checked"] == 4
    assert "no notice found" in report["note"]


def test_cli_prints_findings(monkeypatch, capsys, tmp_path):
    """The CLI reports the retraction against the citing run."""
    runs = _runs_with_mtch2(tmp_path)
    monkeypatch.setattr(retraction_watch, "default_fetch_json",
                        _epmc_retracted)
    code = cli.main(["retraction-watch", "--runs", str(runs)])
    out = capsys.readouterr().out
    assert code == 0
    assert "[retraction] pmid 38882047" in out
    assert "target-mtch2-inhibition-2026-10-25" in out
