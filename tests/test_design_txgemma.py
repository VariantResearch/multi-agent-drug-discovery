"""Tests for the TxGemma bridge: endpoint configuration,
conservative answer parsing, prediction attachment at the
unverified grade, and the license gate. A stub transport
stands in for the endpoint; no network is touched."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd import design_txgemma
from madd.design_txgemma import enrich_candidates, predict_smiles


def stub_transport(url, prompt):
    """Answer in the endpoint's shape, routed by the task named
    in the prompt."""
    if "mutagenic" in prompt:
        return 200, "Answer: Yes"
    if "hERG" in prompt:
        return 200, "Answer: No"
    if "solubility" in prompt:
        return 200, "Answer: -3.25"
    return 200, "Answer: unclear"


def candidate(cid="c1", smiles="CCO"):
    """One SMILES candidate in the design shape."""
    return {"candidate_id": cid,
            "structure": {"format": "smiles", "value": smiles},
            "predicted_properties": []}


def test_predict_and_parse(monkeypatch):
    """Classification answers parse to Yes/No, regression to a
    float, and the prompt echo is read after its Answer marker."""
    monkeypatch.setenv("MADD_TXGEMMA_URL", "https://endpoint.example/run")
    out = predict_smiles("CCO", transport=stub_transport)
    assert out["ames_mutagenicity"] == "Yes"
    assert out["herg_inhibition"] == "No"
    assert out["solubility_logS"] == -3.25

    def echo_transport(url, prompt):
        """Return the prompt echoed before the real answer."""
        return 200, prompt + " Yes"

    out = predict_smiles("CCO", transport=echo_transport)
    assert out["ames_mutagenicity"] == "Yes"


def test_enrich_attaches_unverified_predictions(monkeypatch):
    """With an endpoint configured, predictions land on the
    candidate labelled predicted:TxGemma and verified False,
    and the record counts them."""
    monkeypatch.setenv("MADD_TXGEMMA_URL", "https://endpoint.example/run")
    cand = candidate()
    record = enrich_candidates([cand], transport=stub_transport)
    assert record["status"] == "completed"
    assert record["predicted"] == 3
    assert record["endpoint"] == "endpoint.example"
    props = {p["name"]: p for p in cand["predicted_properties"]}
    assert props["txgemma:ames_mutagenicity"]["value"] == "Yes"
    assert props["txgemma:ames_mutagenicity"]["verified"] is False
    assert props["txgemma:solubility_logS"]["value"] == -3.25


def test_not_configured_predicts_nothing(monkeypatch):
    """No endpoint in the environment: the tool reports
    not_configured and attaches nothing."""
    monkeypatch.delenv("MADD_TXGEMMA_URL", raising=False)
    cand = candidate()
    record = enrich_candidates([cand], transport=stub_transport)
    assert record["status"] == "not_configured"
    assert record["predicted"] == 0
    assert cand["predicted_properties"] == []


def test_commercial_use_is_license_blocked(monkeypatch):
    """The registry entry allows research under the Gemma Terms
    and blocks commercial use, and enrichment honors that."""
    monkeypatch.setenv("MADD_TXGEMMA_URL", "https://endpoint.example/run")
    record = enrich_candidates([candidate()], use="commercial",
                               transport=stub_transport)
    assert record["status"] == "blocked_license"


def test_unparseable_endpoint_answers_fail_honestly(monkeypatch):
    """An endpoint that answers nothing parseable for any task
    records failed, with the unparseable count shown."""
    monkeypatch.setenv("MADD_TXGEMMA_URL", "https://endpoint.example/run")

    def junk_transport(url, prompt):
        """Return prose with no parseable answer."""
        return 200, "the compound looks interesting in several ways"

    cand = candidate()
    record = enrich_candidates([cand], transport=junk_transport)
    assert record["status"] == "failed"
    assert record["predicted"] == 0
    assert record["unparseable"] == 3
    assert cand["predicted_properties"] == []
