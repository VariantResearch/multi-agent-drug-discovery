"""Real-designer tests: ModelDesigner, RDKit enrichment, end-of-cycle gate.

The end of a design cycle is a ranked candidate with a real structure,
computed properties, and an audited claim set - not a mock. These
tests pin that path with stub completers and the real RDKit engine.
"""
import json

import pytest

from madd import design, design_rdkit
from madd.cli import main
from madd.providers import MockProvider
from tests.test_design import locked_spec

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"


def _good_claim(cid):
    """Build a load-bearing claim that passes audit."""
    return {"claim_id": cid, "text": "supported", "load_bearing": True,
            "evidence_tier": 2, "source_kind": "journal_article",
            "source_identifier": "12345678", "identifier_type": "pmid",
            "verification_status": "quote_checked",
            "supporting_quote": "a real quote"}


class StubCompleter:
    """A provider-shaped stub answering complete() with canned text."""

    def __init__(self, name, text):
        """Initialize the test double."""
        self.name = name
        self._text = text

    def complete(self, system, user):
        """Return the double's fixed completion text."""
        return self._text


def _panel_payload():
    """Build a model-panel design payload."""
    return json.dumps({"candidates": [
        {"modality": "small_molecule",
         "structure": {"format": "smiles", "value": ASPIRIN},
         "description": "aspirin-like probe candidate",
         "claims": [_good_claim("CLM-P1")],
         "predicted_properties": [{"name": "solubility",
                                   "value": "moderate",
                                   "basis": "designer_prediction"}],
         "constraint_results": []},
        {"modality": "small_molecule",
         "structure": None,
         "description": "structureless, must be dropped",
         "claims": [], "predicted_properties": [], "constraint_results": []},
    ]})


def test_model_designer_normalizes_and_drops_structureless():
    """Model designer normalizes and drops structureless."""
    designer = design.ModelDesigner([StubCompleter("panel-a", _panel_payload())])
    brief = design.build_brief(locked_spec(), "test")
    cands = designer.design(brief)
    assert len(cands) == 1
    cand = cands[0]
    assert cand["candidate_id"] == "panel-a-cand-1"
    assert cand["design_tool"] == "model:panel-a"
    assert cand["structure"]["value"] == ASPIRIN
    assert "_synthetic" not in cand
    assert any("no structure" in n for n in designer.notes)


def test_model_designer_records_failures_without_repairing_them():
    """Model designer records failures without repairing them."""
    designer = design.ModelDesigner([
        StubCompleter("bad", "not json at all"),
        StubCompleter("down", None),
    ])

    class Down:
        """Provider double that always fails."""
        name = "down"

        def complete(self, system, user):
            """Return the double's fixed completion text."""
            raise RuntimeError("connection refused")

    designer.providers[1] = Down()
    brief = design.build_brief(locked_spec(), "test")
    assert designer.design(brief) == []
    assert len(designer.notes) == 2


def test_mock_provider_candidates_are_synthetic():
    """Mock provider candidates are synthetic."""
    designer = design.ModelDesigner([MockProvider("001")])
    brief = design.build_brief(locked_spec(), "test")
    cands = designer.design(brief)
    assert len(cands) == 1
    assert cands[0]["_synthetic"] is True


@pytest.mark.skipif(not design_rdkit.available(),
                    reason="RDKit not installed in this environment")
def test_rdkit_enrichment_computes_real_descriptors():
    """Rdkit enrichment computes real descriptors."""
    cand = {"candidate_id": "C1", "structure": {"format": "smiles",
                                                "value": ASPIRIN},
            "predicted_properties": [], "constraint_results": []}
    record = design_rdkit.enrich_candidates([cand])
    assert record["status"] == "completed"
    assert record["checked"] == 1 and record["valid"] == 1
    props = {p["name"]: p for p in cand["predicted_properties"]}
    assert props["molecular_weight"]["value"] == pytest.approx(180.158, abs=0.01)
    assert props["molecular_weight"]["basis"].startswith("computed:RDKit")
    assert props["molecular_weight"]["verified"] is True
    assert cand["structure"]["canonical_smiles"]
    assert cand["constraint_results"][0]["status"] == "pass"


def test_rdkit_unavailable_reports_not_installed(monkeypatch):
    """Rdkit unavailable reports not installed."""
    monkeypatch.setattr(design_rdkit, "available", lambda: False)
    cand = {"candidate_id": "C1", "structure": {"format": "smiles",
                                                "value": ASPIRIN},
            "predicted_properties": [], "constraint_results": []}
    record = design_rdkit.enrich_candidates([cand])
    assert record["status"] == "not_installed"
    assert cand["predicted_properties"] == []


@pytest.mark.skipif(not design_rdkit.available(),
                    reason="RDKit not installed in this environment")
def test_end_of_cycle_real_candidate_passes_the_gate():
    """End of cycle real candidate passes the gate."""
    designer = design.ModelDesigner([StubCompleter("panel-a", _panel_payload())])
    bundle = design.run_design(locked_spec(), "test", designer=designer)
    assert bundle["gate_report"]["result"] == "pass", bundle["gate_report"]
    ranked = bundle["ranking"]["ranked"]
    assert ranked == ["panel-a-cand-1"]
    cand = bundle["candidates"][0]
    computed = [p for p in cand["predicted_properties"]
                if str(p.get("basis", "")).startswith("computed:RDKit")]
    assert computed, "a real cycle end carries computed, not just predicted, properties"
    audit = bundle["audits"][0]
    assert audit["audited_load_bearing"] == 1
    assert audit["unverified_predictions"] == 1, "only the designer's own estimate is unverified"


@pytest.mark.skipif(not design_rdkit.available(),
                    reason="RDKit not installed in this environment")
def test_invalid_smiles_is_excluded_by_the_computed_constraint():
    """Invalid smiles is excluded by the computed constraint."""
    payload = json.dumps({"candidates": [
        {"modality": "small_molecule",
         "structure": {"format": "smiles", "value": "not-a-smiles((("},
         "description": "broken structure",
         "claims": [], "predicted_properties": [], "constraint_results": []}]})
    designer = design.ModelDesigner([StubCompleter("panel-a", payload)])
    bundle = design.run_design(locked_spec(), "test", designer=designer)
    assert bundle["ranking"]["ranked"] == []
    reasons = bundle["ranking"]["excluded"][0]["reasons"]
    assert any("structure_valid_smiles" in r for r in reasons)
    assert bundle["gate_report"]["result"] == "fail"


def test_cli_design_run_with_mock_config_stays_honest(tmp_path, capsys):
    """Cli design run with mock config stays honest."""
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(locked_spec()))
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "providers": [{"kind": "mock", "name": "panel-a", "label": "a"},
                      {"kind": "mock", "name": "panel-b", "label": "b"}],
        "budget": {"max_calls": 10}}))
    rc = main(["design-run", str(spec_path), "--config", str(config_path),
               "--out", str(tmp_path / "runs")])
    out = capsys.readouterr().out
    assert "model panel" in out
    assert rc == 1, "mock panel candidates are synthetic; the gate must fail"
    assert "gate: fail" in out
