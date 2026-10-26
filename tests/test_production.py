"""Production sheet tests: exact identity for SMILES candidates,
composition for sequence candidates, honest not_specified lists,
and integration into design bundles.

All structures here are invented test fixtures exercising plumbing;
they are not drug candidates and assert nothing about any target."""
from madd.design import MockDesigner, run_design
from madd.production import build_production_sheet, build_production_sheets

BRIEF = {"target": "TEST-TARGET", "disease": "test disease",
         "question": "Design candidates against TEST-TARGET.",
         "design_constraints": ["test constraint"]}


def _smiles_candidate():
    """A small-molecule candidate with a valid SMILES structure."""
    return {"candidate_id": "c-smiles", "modality": "small_molecule",
            "design_tool": "test",
            "structure": {"format": "smiles", "value": "CCO"},
            "predicted_properties": [], "production_notes": {}}


def _peptide_candidate():
    """A peptide candidate with an amino-acid sequence."""
    return {"candidate_id": "c-pep", "modality": "peptide",
            "design_tool": "test",
            "structure": {"format": "sequence", "value": "ACDEFGHIK"},
            "predicted_properties": [],
            "production_notes": {"modifications": "C-terminal amide",
                                 "confirmation_assay": "test assay"}}


def _oligo_candidate():
    """A biologic sequence candidate with no production notes."""
    return {"candidate_id": "c-oligo", "modality": "biologic",
            "design_tool": "test",
            "structure": {"format": "sequence", "value": "ACGTACGTAC"},
            "predicted_properties": [], "production_notes": {}}


def test_smiles_sheet_has_computed_identity():
    """SMILES sheets carry canonical form, formula, and InChIKey."""
    sheet = build_production_sheet(_smiles_candidate(), BRIEF, rank=1)
    identity = sheet["identity"]
    assert identity["canonical_smiles"] == "CCO"
    assert identity["molecular_formula"] == "C2H6O"
    assert identity["inchikey"] == "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"
    assert identity["structure_valid"] is True
    assert sheet["production_route"] == "chemical synthesis"
    assert sheet["targeted_process"]["target"] == "TEST-TARGET"
    assert sheet["production_ready"] is True


def test_sequence_sheets_composition_and_gaps():
    """Sequence sheets report composition and name missing details."""
    pep = build_production_sheet(_peptide_candidate(), BRIEF, rank=1)
    assert pep["identity"]["length"] == 9
    assert pep["identity"]["alphabet_check"] == "pass"
    assert pep["production_route"] == "solid-phase peptide synthesis"
    assert pep["production_ready"] is True
    oligo = build_production_sheet(_oligo_candidate(), BRIEF, rank=2)
    assert oligo["identity"]["length"] == 10
    assert any("modification pattern" in item
               for item in oligo["not_specified"])
    assert any("confirmation assay" in item
               for item in oligo["not_specified"])


def test_broken_candidates_are_not_production_ready():
    """Invalid structures and structureless candidates fail readiness."""
    bad = _smiles_candidate()
    bad["structure"] = {"format": "smiles", "value": "not-a-smiles((("}
    sheet = build_production_sheet(bad, BRIEF)
    assert sheet["production_ready"] is False
    empty = {"candidate_id": "c-none", "modality": "small_molecule",
             "structure": None, "predicted_properties": []}
    sheet = build_production_sheet(empty, BRIEF)
    assert sheet["production_ready"] is False
    assert any("structure" in item for item in sheet["not_specified"])


def test_sheets_follow_ranking_and_design_bundle():
    """Bundles carry sheets for ranked candidates only, in order."""
    spec = {"artifact_type": "consensus_spec", "spec_id": "SPEC-TEST",
            "outcome": "locked", "focus_id": "TEST-TARGET", "claims": []}
    bundle = run_design(spec, "test", designer=MockDesigner())
    sheets = bundle["production_sheets"]
    assert [s["candidate_id"] for s in sheets] == bundle["ranking"]["ranked"]
    assert all(s["rank"] == i + 1 for i, s in enumerate(sheets))
    direct = build_production_sheets(bundle)
    assert [s["candidate_id"] for s in direct] == [s["candidate_id"]
                                                   for s in sheets]
