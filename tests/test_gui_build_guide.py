"""Build guide payload tests: the console build guide is the
design stage's production sheets, stored or built mechanically,
for design bundles and target-run bundles alike."""
from madd.gui import build_guide_payload

_CANDIDATES = [
    {"candidate_id": "mol", "modality": "small_molecule",
     "structure": {"format": "smiles", "value": "CCO"}},
    {"candidate_id": "aso", "modality": "biologic",
     "structure": {"format": "sequence", "value": "ACGTACGT"}},
]
_BRIEF = {"target": "TARGET-X", "disease": "condition-y"}


def _design(stored=None):
    """A minimal design bundle, optionally with stored sheets."""
    bundle = {"kind": "design_run", "brief": _BRIEF,
              "candidates": _CANDIDATES,
              "ranking": {"ranked": ["mol", "aso"], "excluded": []}}
    if stored is not None:
        bundle["production_sheets"] = stored
    return bundle


def test_payload_builds_sheets_when_not_stored():
    """Without stored sheets, the payload builds them from the
    bundle: the small molecule is ready, the sequence is not."""
    out = build_guide_payload(_design())
    assert [s["candidate_id"] for s in out["sheets"]] == ["mol", "aso"]
    assert out["sheets"][0]["production_ready"] is True
    assert out["sheets"][1]["production_ready"] is False


def test_payload_prefers_stored_sheets():
    """Stored sheets are served as-is, never rebuilt over."""
    stored = [{"candidate_id": "mol", "production_ready": True}]
    out = build_guide_payload(_design(stored=stored))
    assert out["sheets"] == stored


def test_payload_target_bundle_and_empty():
    """A target-run bundle reads its nested design; a bundle with
    no design stage yields an empty guide, not an error."""
    out = build_guide_payload({"kind": "target_run",
                               "design": _design()})
    assert len(out["sheets"]) == 2
    assert build_guide_payload({"kind": "frame_run"}) == {"sheets": []}
