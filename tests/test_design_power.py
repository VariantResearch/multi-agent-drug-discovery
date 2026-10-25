"""Design-power batch tests: ADMET-AI enrichment, PoseBusters pose
checks, the Vina runner, and the AiZynthFinder route runner.

Library tests skip cleanly when the optional packages are absent;
runner tests use fake executables on PATH so they run anywhere.
"""
import json
import os
import stat

import pytest

from madd import design, design_admet, design_pose, design_tools
from madd.license_registry import check_tool
from tests.test_design import locked_spec

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"


def test_new_tools_are_registered_and_cleared():
    for name in ("ADMET-AI", "AutoDock Vina", "PoseBusters", "AiZynthFinder"):
        assert check_tool(name, "research")["allowed"], name
        assert check_tool(name, "commercial")["allowed"], name


def _smiles_candidate(cid="C1"):
    return {"candidate_id": cid, "structure": {"format": "smiles",
                                               "value": ASPIRIN},
            "predicted_properties": [], "constraint_results": []}


@pytest.mark.skipif(not design_admet.available(),
                    reason="admet-ai not installed in this environment")
def test_admet_enrichment_records_unverified_tool_predictions():
    cand = _smiles_candidate()
    record = design_admet.enrich_candidates([cand])
    assert record["status"] == "completed"
    assert record["predicted"] > 0
    admet_props = [p for p in cand["predicted_properties"]
                   if p["name"].startswith("admet:")]
    assert admet_props
    for prop in admet_props:
        assert prop["basis"].startswith("computed:ADMET-AI")
        assert prop["verified"] is False, \
            "a model prediction must never be recorded as verified"


def test_admet_absent_reports_not_installed(monkeypatch):
    monkeypatch.setattr(design_admet, "available", lambda: False)
    record = design_admet.enrich_candidates([_smiles_candidate()])
    assert record["status"] == "not_installed"


def _write_sdf(path, smiles=ASPIRIN, scale=1.0, seed=7):
    from rdkit import Chem
    from rdkit.Chem import AllChem
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=seed)
    if scale != 1.0:
        conf = mol.GetConformer()
        for i in range(mol.GetNumAtoms()):
            pos = conf.GetAtomPosition(i)
            conf.SetAtomPosition(i, (pos.x * scale, pos.y * scale, pos.z * scale))
    writer = Chem.SDWriter(str(path))
    writer.write(mol)
    writer.close()


@pytest.mark.skipif(not design_pose.available(),
                    reason="posebusters not installed in this environment")
def test_posebusters_passes_a_clean_conformer(tmp_path):
    _write_sdf(tmp_path / "pose.sdf")
    _write_sdf(tmp_path / "ref.sdf")
    result = design_pose.bust_pose(tmp_path / "pose.sdf", tmp_path / "ref.sdf")
    assert result["status"] == "completed"
    assert result["passed"] is True
    assert len(result["checks"]) >= 10


@pytest.mark.skipif(not design_pose.available(),
                    reason="posebusters not installed in this environment")
def test_posebusters_catches_a_broken_pose(tmp_path):
    _write_sdf(tmp_path / "pose.sdf", scale=6.0)
    _write_sdf(tmp_path / "ref.sdf")
    result = design_pose.bust_pose(tmp_path / "pose.sdf", tmp_path / "ref.sdf")
    assert result["status"] == "completed"
    assert result["passed"] is False
    assert "bond_lengths" in result["detail"]


def _fake_vina(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    script = bindir / "vina"
    script.write_text(
        "#!/bin/sh\n"
        "out=\"\"\n"
        "prev=\"\"\n"
        "for a in \"$@\"; do if [ \"$prev\" = \"--out\" ]; then out=\"$a\"; fi; prev=\"$a\"; done\n"
        "mkdir -p \"$(dirname \"$out\")\"\n"
        "printf 'MODEL 1\\nREMARK VINA RESULT: -8.1 0.0 0.0\\nENDMDL\\n' > \"$out\"\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return bindir


def test_vina_runner_completes_with_a_fake_executable(tmp_path, monkeypatch):
    bindir = _fake_vina(tmp_path)
    monkeypatch.setenv("PATH", str(bindir))
    config = tmp_path / "config.txt"
    config.write_text("receptor = r.pdbqt\nligand = l.pdbqt\n")
    manifest = design_tools.run_structure_tool(
        "AutoDock Vina", "research", tmp_path / "work", input_path=config)
    assert manifest["status"] == "completed"
    assert manifest["outputs"][0]["path"].endswith("docked.pdbqt")
    cands = design_tools.candidates_from_tool_run(manifest, "SPEC-1")
    assert len(cands) == 1
    assert cands[0]["structure"]["format"] == "pdbqt"


def test_vina_runner_reports_not_installed(tmp_path, monkeypatch):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    manifest = design_tools.run_structure_tool(
        "AutoDock Vina", "research", tmp_path / "work", input_path="x")
    assert manifest["status"] == "not_installed"


def test_retrosynthesis_without_config_is_an_honest_status(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    exe = bindir / "aizynthcli"
    exe.write_text("#!/bin/sh\nexit 0\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ["PATH"])
    manifest = design_tools.run_retrosynthesis(
        ASPIRIN, tmp_path / "missing.yml", tmp_path / "work")
    assert manifest["status"] == "no_config"
    assert "model" in manifest["reason"]


def test_run_design_records_retrosynthesis_status():
    payload = json.dumps({"candidates": [
        {"modality": "small_molecule",
         "structure": {"format": "smiles", "value": ASPIRIN},
         "description": "probe", "claims": [],
         "predicted_properties": [], "constraint_results": []}]})

    class Stub:
        name = "panel"

        def complete(self, system, user):
            return payload

    bundle = design.run_design(locked_spec(), "test",
                               designer=design.ModelDesigner([Stub()]),
                               retro_config="/nonexistent/aizynth.yml",
                               admet=False)
    cand = bundle["candidates"][0]
    assert cand["retrosynthesis"]["status"] in ("no_config", "not_installed")
    retro_runs = [t for t in bundle["tool_runs"] if t.get("tool") == "AiZynthFinder"]
    assert len(retro_runs) == 1
    assert retro_runs[0]["requested"] is True
