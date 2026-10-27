"""Tests for the generative designer seat: endpoint sampling
normalized into ordinary candidates, the not-configured and
failure notes, panel composition, and a full design run where
the seat's candidates flow through the normal pipeline."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd import design, design_generative
from madd.design_generative import (CompositeDesigner,
                                    GenerativeDesigner,
                                    with_generative_seat)
from tests.test_design import locked_spec

BRIEF = {"brief_id": "BRIEF-1", "spec_id": "SPEC-1", "target": "MTCH2",
         "disease": "obesity", "constraints": ["keep it small"]}


def stub_transport(url, payload):
    """Answer with two sampled molecules, recording the ask."""
    stub_transport.payload = payload
    return 200, {"smiles": ["CCO", "c1ccccc1O"]}


def test_seat_samples_become_candidates():
    """Samples are normalized into the design candidate shape
    with generative provenance and no claims."""
    seat = GenerativeDesigner(transport=stub_transport,
                              url="https://gen.example/sample",
                              model="sampler-x", samples=4)
    out = seat.design(BRIEF)
    assert len(out) == 2
    first = out[0]
    assert first["candidate_id"] == "generative-cand-1"
    assert first["design_tool"] == "generative:sampler-x"
    assert first["structure"] == {"format": "smiles", "value": "CCO"}
    assert first["claims"] == []
    assert first["spec_id"] == "SPEC-1"
    assert stub_transport.payload["n"] == 4
    assert stub_transport.payload["brief"]["target"] == "MTCH2"
    assert any("sampled 2" in note for note in seat.notes)


def test_seat_unconfigured_and_failing():
    """No endpoint: no candidates and the note says so. A dead
    or erroring endpoint: no candidates and the failure named."""
    seat = GenerativeDesigner(url="", transport=stub_transport)
    assert seat.design(BRIEF) == []
    assert any("no endpoint configured" in n for n in seat.notes)

    def dead(url, payload):
        """Raise like an unreachable endpoint."""
        raise RuntimeError("connection refused")

    seat = GenerativeDesigner(url="https://gen.example", transport=dead)
    assert seat.design(BRIEF) == []
    assert any("sampling call failed" in n for n in seat.notes)

    seat = GenerativeDesigner(
        url="https://gen.example",
        transport=lambda url, payload: (503, "busy"))
    assert seat.design(BRIEF) == []
    assert any("HTTP 503" in n for n in seat.notes)


def test_composition_and_env_gate(monkeypatch):
    """The composite unions its members' candidates and notes;
    the seat joins only when the environment configures one."""
    seat = GenerativeDesigner(transport=stub_transport,
                              url="https://gen.example",
                              model="sampler-x")
    panel = CompositeDesigner([design.MockDesigner(), seat])
    out = panel.design(BRIEF)
    ids = [c["candidate_id"] for c in out]
    assert "generative-cand-1" in ids and len(ids) > 2
    assert "generative:sampler-x" in panel.name

    monkeypatch.delenv("MADD_GENERATIVE_URL", raising=False)
    base = design.MockDesigner()
    assert with_generative_seat(base) is base
    monkeypatch.setenv("MADD_GENERATIVE_URL", "https://gen.example")
    joined = with_generative_seat(base)
    assert isinstance(joined, CompositeDesigner)


def test_design_run_includes_the_seat(monkeypatch):
    """End to end: with an endpoint configured, a design run's
    bundle carries the seat's candidates through the normal
    pipeline, with the seat named in the designer field."""
    monkeypatch.setenv("MADD_GENERATIVE_URL", "https://gen.example")
    monkeypatch.setattr(design_generative, "default_transport",
                        stub_transport)
    bundle = design.run_design(locked_spec(), "test")
    generative = [c for c in bundle["candidates"]
                  if str(c.get("design_tool", "")).startswith(
                      "generative:")]
    assert len(generative) == 2
    assert "generative:" in bundle["designer"]
    assert any("generative seat" in note
               for note in bundle["designer_notes"])
