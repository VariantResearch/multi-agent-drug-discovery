"""Phase 2 design tests: briefs, mock designer, audit, ranking, tools, GUI."""
import hashlib
import json
import stat
import urllib.request
from pathlib import Path

import pytest

from madd import design, design_tools, schemas, storage
from madd.cli import main


def locked_spec():
    return {
        "artifact_type": "consensus_spec", "schema_version": "0.1.0",
        "spec_id": "SPEC-T-1", "frame_id": "F-T",
        "focus_id": "Target T",
        "direction": "advance",
        "outcome": "locked",
        "claims": [
            {"claim_id": "CLM-1", "text": "Human genetics supports target T.",
             "source_kind": "primary_study", "source_identifier": "12345678",
             "identifier_type": "pmid", "verification_status": "quote_checked",
             "supporting_quote": "variants in the target gene associate with disease",
             "evidence_tier": 1, "load_bearing": True},
            {"claim_id": "CLM-2", "text": "A side observation.",
             "source_kind": "primary_study", "source_identifier": "23456789",
             "identifier_type": "pmid", "verification_status": "quote_checked",
             "supporting_quote": "an observation", "evidence_tier": 4,
             "load_bearing": False},
        ],
        "consensus_tests": [], "dissent_log": [],
    }


def test_brief_from_locked_spec():
    brief = design.build_brief(locked_spec(), "test")
    assert brief["target"] == "Target T"
    assert [c["claim_id"] for c in brief["evidence_constraints"]] == ["CLM-1"]
    assert schemas.validate_artifact("design_brief", brief) == []


def test_brief_target_from_focus_id_and_overrides():
    # Regression: debate-locked specs carry a flat focus_id and no
    # disease field (verified against a real Gate 0 run record). The
    # brief must take its target from focus_id, leave disease empty
    # rather than guess, and accept operator overrides for both.
    brief = design.build_brief(locked_spec(), "test")
    assert brief["target"] == "Target T"
    assert brief["disease"] == ""
    brief2 = design.build_brief(locked_spec(), "test",
                                disease="Disease D", target="Target T2")
    assert brief2["disease"] == "Disease D"
    assert brief2["target"] == "Target T2"


def test_brief_refuses_unlocked_spec():
    spec = locked_spec()
    spec["outcome"] = "killed"
    with pytest.raises(ValueError):
        design.build_brief(spec, "test")
    with pytest.raises(ValueError):
        design.build_brief({"artifact_type": "frame"}, "test")


def test_mock_designer_candidates_are_honest():
    brief = design.build_brief(locked_spec(), "test")
    cands = design.MockDesigner().design(brief)
    assert len(cands) == 2
    for c in cands:
        assert c["_synthetic"] is True
        assert c["structure"] is None
        assert c["claims"] == []
        assert schemas.validate_artifact("candidate", c) == []


def test_run_design_bundle_and_gate():
    bundle = design.run_design(locked_spec(), "test",
                               design_constraints=("oral dosing preferred",))
    assert bundle["kind"] == "design_run"
    # The mock-only pipeline ranks its placeholders but the gate must
    # FAIL: no real candidate exists. This is the audit fix for a gate
    # that previously passed on synthetic candidates alone.
    assert bundle["gate_report"]["result"] == "fail"
    checks = {c["name"]: c["status"] for c in bundle["gate_report"]["checks"]}
    assert checks["real_candidates_ranked"] == "fail"
    assert checks["candidates_ranked"] == "pass"
    assert len(bundle["ranking"]["ranked"]) == 2
    assert bundle["ranking"]["excluded"] == []
    for audit in bundle["audits"]:
        assert audit["unverified_predictions"] == 1
        assert audit["hard_fail"] is False
    # The gate report validates against the project's own schema and
    # the bundle is frozen like every other run bundle.
    from madd.artifacts import verify_frozen
    assert schemas.validate_artifact("gate_report", bundle["gate_report"]) == []
    assert verify_frozen(bundle["frozen_bundle"])


def test_candidate_with_bad_load_bearing_claim_is_excluded():
    bad = {
        "artifact_type": "candidate", "schema_version": "0.1.0",
        "candidate_id": "BAD-1", "spec_id": "SPEC-T-1",
        "modality": "small_molecule", "design_tool": "test",
        "claims": [{"claim_id": "CLM-BAD", "text": "It binds, trust me.",
                    "source_kind": "primary_study", "source_identifier": "",
                    "identifier_type": "pmid",
                    "supporting_quote": "", "evidence_tier": 3, "load_bearing": True}],
        "predicted_properties": [], "constraint_results": [],
    }

    class OnlyBad:
        name = "only-bad"

        def design(self, brief):
            return [bad]

    bundle = design.run_design(locked_spec(), "test", designer=OnlyBad())
    assert bundle["ranking"]["ranked"] == []
    assert bundle["ranking"]["excluded"][0]["candidate_id"] == "BAD-1"
    assert bundle["gate_report"]["result"] == "fail"


def test_failed_constraint_excludes():
    cand = {
        "artifact_type": "candidate", "schema_version": "0.1.0",
        "candidate_id": "CF-1", "spec_id": "SPEC-T-1",
        "modality": "small_molecule", "design_tool": "test",
        "claims": [], "predicted_properties": [],
        "constraint_results": [{"constraint": "CLM-1", "kind": "evidence",
                                "status": "fail", "basis": "test"}],
    }
    audit = design.audit_candidate(cand)
    assert audit["hard_fail"] is True
    assert "CLM-1" in audit["failed_constraints"]


def test_ranking_prefers_audited_claims():
    brief = design.build_brief(locked_spec(), "test")
    good = {
        "artifact_type": "candidate", "schema_version": "0.1.0",
        "candidate_id": "GOOD-1", "spec_id": "SPEC-T-1",
        "modality": "small_molecule", "design_tool": "test",
        "claims": [dict(locked_spec()["claims"][0], claim_id="CLM-G")],
        "predicted_properties": [], "constraint_results": [],
    }
    bundle = design.run_design(locked_spec(), "test",
                               extra_candidates=(good,))
    assert bundle["ranking"]["ranked"][0] == "GOOD-1"


def test_blocked_tool_never_runs(tmp_path):
    manifest = design_tools.run_structure_tool(
        "AlphaFold 3", "commercial", tmp_path, input_path="x")
    assert manifest["status"] == "blocked_license"
    assert manifest["outputs"] == []


def test_cleared_tool_not_installed(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    manifest = design_tools.run_structure_tool(
        "Boltz-2", "research", tmp_path / "w", input_path="in.yaml")
    assert manifest["status"] == "not_installed"


def test_fake_tool_run_records_outputs(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "boltz"
    script.write_text(
        "#!/bin/sh\nout=''\nprev=''\nfor a in \"$@\"; do\n"
        "  if [ \"$prev\" = '--out_dir' ]; then out=\"$a\"; fi\n"
        "  prev=\"$a\"\ndone\nmkdir -p \"$out\"\n"
        "printf 'FAKECIF' > \"$out/model_0.cif\"\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", str(bin_dir))
    manifest = design_tools.run_structure_tool(
        "Boltz-2", "research", tmp_path / "work", input_path="input.yaml")
    assert manifest["status"] == "completed"
    assert len(manifest["outputs"]) == 1
    digest = manifest["outputs"][0]["sha256"]
    assert digest == hashlib.sha256(b"FAKECIF").hexdigest()
    cands = design_tools.candidates_from_tool_run(manifest, "SPEC-T-1")
    assert len(cands) == 1
    assert cands[0]["structure"]["sha256"] == digest
    assert cands[0]["claims"] == []
    assert schemas.validate_artifact("candidate", cands[0]) == []


def test_cli_design_flow(tmp_path, capsys):
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(locked_spec()))
    assert main(["design-brief", str(spec_path)]) == 0
    brief = json.loads(capsys.readouterr().out)
    assert brief["spec_id"] == "SPEC-T-1"
    out = tmp_path / "runs"
    # Mock-only design: bundle written, gate fails, exit code says so.
    assert main(["design-run", str(spec_path), "--out", str(out),
                 "--constraint", "no covalent binders"]) == 1
    text = capsys.readouterr().out
    assert "gate: fail" in text
    run_dir = out / "design-spec-t-1"
    assert (run_dir / "bundle.json").exists()
    report = (run_dir / "report.md").read_text()
    assert "Ranked candidates" in report
    assert "SYNTHETIC placeholder" in report
    assert "DESIGN" in (run_dir / "report.html").read_text()
    entries = storage.list_runs(out)
    assert entries[0]["kind"] == "design_run"
    assert entries[0]["outcome"] == "fail"


def test_cli_design_run_refuses_killed(tmp_path, capsys):
    spec = locked_spec()
    spec["outcome"] = "killed"
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec))
    assert main(["design-run", str(spec_path), "--out", str(tmp_path / "r")]) == 1
    assert "locked" in capsys.readouterr().err


@pytest.fixture()
def gui_server(tmp_path):
    from madd.gui import create_server
    runs = tmp_path / "runs"
    runs.mkdir()
    frame_bundle = {
        "kind": "frame_run", "run_id": "frame-t-1", "frame_id": "F-T",
        "outcome": "locked", "record": {"spec": locked_spec()},
    }
    storage.write_bundle(frame_bundle, runs)
    server = create_server("127.0.0.1", 0, runs_dir=str(runs), gate0_dir=None)
    import threading
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield "http://127.0.0.1:" + str(server.server_address[1])
    server.shutdown()


def _post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return json.loads(exc.read().decode())


def test_gui_design_from_locked_frame_run(gui_server, tmp_path):
    out = _post(gui_server + "/api/design-run",
                {"run_id": "frame-t-1", "disease": "Disease D"})
    assert out["ok"] is True
    # Mock designer only: the run is written, the gate honestly fails.
    assert out["gate"] == "fail"
    assert out["run_id"] == "design-spec-t-1"
    bundle = storage.load_bundle(tmp_path / "runs", "design-spec-t-1")
    assert bundle["brief"]["disease"] == "Disease D"
    with urllib.request.urlopen(gui_server + "/api/runs", timeout=5) as resp:
        runs = json.loads(resp.read().decode())["runs"]
    kinds = {r["run_id"]: r["kind"] for r in runs}
    assert kinds["design-spec-t-1"] == "design_run"
    page = urllib.request.urlopen(gui_server + "/", timeout=5).read().decode()
    assert "designFrom" in page
