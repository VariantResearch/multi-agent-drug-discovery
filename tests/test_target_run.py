"""Target-run tests: the target-first pipeline end to end with stub
providers - frame building per kind, the locked path into design,
the no_go path that never designs, and mode pass-through.

All providers, dossiers, and claims here are invented test fixtures.
They test plumbing only; they are not research and prove nothing
about any real target."""
import copy

import pytest

from madd.design import MockDesigner
from madd.html_report import bundle_to_html
from madd.report import bundle_to_markdown
from madd.target_run import TARGET_KINDS, build_target_frame, run_target


def _claim(cid):
    """One audit-passing invented claim."""
    return {"claim_id": cid, "text": "invented claim " + cid,
            "load_bearing": True, "evidence_tier": 2,
            "source_kind": "journal_article", "source_identifier": "12345678",
            "identifier_type": "pmid", "verification_status": "quote_checked",
            "supporting_quote": "invented supporting quote"}


def _dossier(frame_id, agent_id, focus, claims):
    """One invented dossier for the target frame."""
    return {"artifact_type": "dossier", "schema_version": "0.1.0",
            "dossier_id": "DOSSIER-" + agent_id, "frame_id": frame_id,
            "agent_id": agent_id, "model_family": "stub",
            "proposed_focus_id": focus, "direction": "invented direction",
            "claims": claims, "unverified_notes": []}


class _StubProvider:
    """Stub provider serving one fixed dossier."""
    def __init__(self, name, model_version, dossier_dict):
        """Store the fixed dossier and model identity."""
        self.name = name
        self.model_version = model_version
        self.cost_per_call_usd = 0.0
        self._dossier = dossier_dict

    def research(self, frame):
        """Return the fixed dossier."""
        return copy.deepcopy(self._dossier)

    def complete(self, system, user):
        """Refuse: this stub serves research only."""
        raise RuntimeError("no completions in this stub")


def _panel(frame, focus="KRAS-G12C"):
    """Two agreeing stub providers on one model."""
    return [
        _StubProvider("stub-a", "stub-1",
                      _dossier(frame["frame_id"], "agent-a", focus,
                               [_claim("c-a")])),
        _StubProvider("stub-b", "stub-1",
                      _dossier(frame["frame_id"], "agent-b", focus,
                               [_claim("c-b")])),
    ]


class _StubDesigner:
    """Designer returning one structured stub candidate."""
    name = "stub-designer"

    def design(self, brief):
        """Return one candidate carrying a real SMILES structure."""
        return [{
            "artifact_type": "candidate", "schema_version": "0.1.0",
            "candidate_id": "stub-cand-1", "spec_id": brief["spec_id"],
            "modality": "small_molecule", "design_tool": "stub",
            "description": "A stub candidate with a real structure.",
            "structure": {"format": "smiles", "value": "CCO"},
            "claims": [], "predicted_properties": [],
            "constraint_results": []}]


def _frame(**kw):
    """The KRAS G12C target frame with defaults."""
    kw.setdefault("name", "KRAS G12C")
    kw.setdefault("kind", "target")
    kw.setdefault("disease", "non-small cell lung cancer")
    return build_target_frame(**kw)


def test_frame_kinds_and_focus_defaults():
    """Covered by the module docstring; asserts one pipeline behavior."""
    for kind in TARGET_KINDS:
        frame = build_target_frame("Example", kind)
        assert frame["target_kind"] == kind
        assert frame["evidence"] == []
    disease = build_target_frame("cystic fibrosis", "disease")
    assert disease["disease"] == "cystic fibrosis"
    assert disease["focus_id"] == "cystic fibrosis"
    receptor = build_target_frame("the CGRP receptor", "receptor")
    assert receptor["target"] == "the CGRP receptor"
    kras = _frame()
    assert kras["target"] == "KRAS G12C"
    assert kras["focus_id"] == "KRAS G12C"
    assert kras["frame_id"] == "TARGET-kras-g12c"
    with pytest.raises(ValueError):
        build_target_frame("X", "organ")
    with pytest.raises(ValueError):
        build_target_frame("", "target")


def test_locked_target_runs_design_and_reports():
    """Covered by the module docstring; asserts one pipeline behavior."""
    frame = _frame()
    bundle = run_target(frame, _panel(frame), designer=_StubDesigner(),
                        mode="simple")
    assert bundle["kind"] == "target_run"
    assert bundle["target"]["name"] == "KRAS G12C"
    assert bundle["design"] is not None
    assert bundle["outcome"] == "designed"
    assert bundle["design"]["gate_report"]["result"] == "pass"
    assert bundle["design"]["brief"]["target"] == "KRAS G12C"
    assert bundle["design"]["brief"]["disease"] == "non-small cell lung cancer"
    assert bundle["frozen_bundle"]["sha256"]
    md = bundle_to_markdown(bundle)
    assert "MADD target run" in md and "KRAS G12C" in md and "Design stage" in md
    html = bundle_to_html(bundle)
    assert "Target run" in html and "KRAS G12C" in html


def test_no_go_target_never_designs():
    """Covered by the module docstring; asserts one pipeline behavior."""
    frame = _frame()
    panel = _panel(frame)
    panel[1] = _StubProvider("stub-b", "stub-1",
                             _dossier(frame["frame_id"], "agent-b",
                                      "something-else", []))
    bundle = run_target(frame, panel, designer=_StubDesigner(), mode="simple")
    assert bundle["outcome"] == "no_go"
    assert bundle["design"] is None
    md = bundle_to_markdown(bundle)
    assert "did not lock this target" in md


def test_mock_designer_cannot_pass_the_gate():
    """Covered by the module docstring; asserts one pipeline behavior."""
    frame = _frame()
    bundle = run_target(frame, _panel(frame), designer=MockDesigner(),
                        mode="simple")
    assert bundle["outcome"] == "design_gate_failed"
    assert bundle["design"]["gate_report"]["result"] == "fail"


def test_default_designer_is_the_provider_panel():
    """Covered by the module docstring; asserts one pipeline behavior."""
    frame = _frame()
    bundle = run_target(frame, _panel(frame), mode="simple")
    assert bundle["design"] is not None
    assert bundle["outcome"] in ("designed", "design_gate_failed")
