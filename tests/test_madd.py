"""Phase 0 unittest suite. All fixtures are synthetic and labelled as such."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.artifacts import build_manifest, canonical_hash, freeze_artifact, thaw_artifact, verify_frozen
from madd.citation_auditor import audit_citations, check_identifier
from madd.claims import audit_claims
from madd.consensus import (check_dissent_log, run_consensus_tests,
                            test_agreement, test_evidence_floor, test_stability)
from madd.focus import focus_score
from madd.license_registry import check_tool
from madd.providers import MockProvider
from madd.schemas import validate_artifact

ROOT = Path(__file__).resolve().parent.parent

GOOD_CLAIM = {
    "claim_id": "SYN-T-GOOD", "text": "synthetic placeholder",
    "load_bearing": True, "evidence_tier": 2, "source_kind": "primary_source",
    "source_identifier": "10.0000/synthetic.example.100", "identifier_type": "doi",
    "verification_status": "quote_checked", "supporting_quote": "synthetic quote placeholder",
}
OPINION_CLAIM = {
    "claim_id": "SYN-T-OPINION", "text": "synthetic placeholder",
    "load_bearing": True, "evidence_tier": 0, "source_kind": "model_opinion",
    "source_identifier": None, "identifier_type": "doi",
    "verification_status": "unverified", "supporting_quote": "",
}
SOURCELESS_CLAIM = {
    "claim_id": "SYN-T-NOSRC", "text": "synthetic placeholder",
    "load_bearing": True, "evidence_tier": 3, "source_kind": "primary_source",
    "source_identifier": None, "identifier_type": "doi",
    "verification_status": "unverified", "supporting_quote": "",
}


def dossier(focus, claims):
    return {"artifact_type": "dossier", "schema_version": "0.1.0",
            "dossier_id": "SYN-D", "frame_id": "SYN-F", "agent_id": "synthetic",
            "proposed_focus_id": focus, "claims": claims}


def spec(focus, claims, dissent=None):
    return {"artifact_type": "consensus_spec", "schema_version": "0.1.0",
            "spec_id": "SYN-S", "frame_id": "SYN-F", "outcome": "locked",
            "focus_id": focus, "claims": claims,
            "dissent_log": dissent if dissent is not None else [{"agent_id": "synthetic", "objection": "synthetic placeholder objection"}]}


class TestHashing(unittest.TestCase):
    def test_canonical_hash_stable_under_key_order(self):
        a = {"b": 1, "a": {"y": [1, 2], "x": "synthetic"}}
        b = {"a": {"x": "synthetic", "y": [1, 2]}, "b": 1}
        self.assertEqual(canonical_hash(a), canonical_hash(b))

    def test_canonical_hash_changes_with_content(self):
        self.assertNotEqual(canonical_hash({"a": 1}), canonical_hash({"a": 2}))

    def test_freeze_thaw_roundtrip_and_tamper_detection(self):
        env = freeze_artifact({"a": 1, "b": "synthetic"})
        self.assertTrue(verify_frozen(env))
        self.assertEqual(thaw_artifact(env), {"a": 1, "b": "synthetic"})
        env["artifact"]["a"] = 99
        self.assertFalse(verify_frozen(env))


class TestClaims(unittest.TestCase):
    def test_good_claim_passes(self):
        report = audit_claims({"claims": [GOOD_CLAIM]})
        self.assertTrue(report["ok"], report)

    def test_model_opinion_fails_load_bearing(self):
        report = audit_claims({"claims": [OPINION_CLAIM]})
        codes = {e["code"] for e in report["errors"]}
        self.assertIn("non_evidence_source_kind", codes)
        self.assertIn("tier_zero_load_bearing", codes)
        self.assertFalse(report["ok"])

    def test_sourceless_fails(self):
        report = audit_claims({"claims": [SOURCELESS_CLAIM]})
        codes = {e["code"] for e in report["errors"]}
        self.assertIn("missing_source_identifier", codes)

    def test_all_errors_reported_not_first_only(self):
        report = audit_claims({"claims": [OPINION_CLAIM, SOURCELESS_CLAIM]})
        self.assertGreaterEqual(report["error_count"], 3)

    def test_duplicate_claim_id_flagged(self):
        report = audit_claims({"claims": [GOOD_CLAIM, dict(GOOD_CLAIM)]})
        codes = [e["code"] for e in report["errors"]]
        self.assertIn("duplicate_claim_id", codes)
        self.assertFalse(report["ok"])

    def test_synthetic_dossier_fixture_fails_as_designed(self):
        doc = json.loads((ROOT / "examples/synthetic/dossier.json").read_text())
        self.assertTrue(doc["_synthetic"])
        report = audit_claims(doc)
        self.assertFalse(report["ok"])
        bad = {e["claim_id"] for e in report["errors"]}
        self.assertIn("SYN-C-OPINION", bad)
        self.assertNotIn("SYN-C-GOOD", bad)


class TestCitationAuditor(unittest.TestCase):
    def test_doi_format(self):
        self.assertTrue(check_identifier("10.1234/synthetic.example", "doi")["ok"])
        self.assertFalse(check_identifier("not-a-doi", "doi")["ok"])

    def test_pmid_and_nct_format(self):
        self.assertTrue(check_identifier("12345678", "pmid")["ok"])
        self.assertFalse(check_identifier("12AB", "pmid")["ok"])
        self.assertTrue(check_identifier("NCT12345678", "nct")["ok"])
        self.assertFalse(check_identifier("NCT123", "nct")["ok"])

    def test_quote_checked_requires_quote(self):
        claim = dict(GOOD_CLAIM); claim["supporting_quote"] = ""
        report = audit_citations({"claims": [claim]})
        codes = {p["code"] for e in report["entries"] for p in e["problems"]}
        self.assertIn("quote_checked_without_quote", codes)

    def test_unverified_listed_for_live_resolution(self):
        report = audit_citations({"claims": [SOURCELESS_CLAIM]})
        self.assertIn("SYN-T-NOSRC", report["needs_live_resolution"])


class TestLicenses(unittest.TestCase):
    def test_alphafold3_blocked_for_commercial(self):
        r = check_tool("AlphaFold 3", "commercial")
        self.assertFalse(r["allowed"])

    def test_boltz2_allowed(self):
        self.assertTrue(check_tool("Boltz-2", "commercial")["allowed"])
        self.assertTrue(check_tool("Boltz-2", "research")["allowed"])

    def test_chai1_and_rdkit_allowed(self):
        self.assertTrue(check_tool("Chai-1", "commercial")["allowed"])
        self.assertTrue(check_tool("RDKit", "commercial")["allowed"])

    def test_esm3_blocked_for_commercial(self):
        self.assertFalse(check_tool("ESM3-open", "commercial")["allowed"])

    def test_verify_terms_blocked_until_verified(self):
        self.assertFalse(check_tool("ProteinMPNN", "research")["allowed"])
        self.assertFalse(check_tool("RFdiffusion", "commercial")["allowed"])

    def test_unknown_tool_blocked(self):
        self.assertFalse(check_tool("SYN-UNKNOWN-TOOL", "research")["allowed"])


class TestConsensus(unittest.TestCase):
    def test_agreement_fails_when_a_dossier_has_no_focus(self):
        # Regression: agreement used to pass when one dossier proposed a
        # focus and another proposed none, because missing focuses were
        # filtered out before the distinct count.
        out = test_agreement([{"proposed_focus_id": "T1"}, {"agent_id": "x"}])
        self.assertFalse(out["passed"])
        self.assertIn("without a focus", out["detail"])

    def test_agreement_pass_and_fail(self):
        ds = [dossier("SYN-T1", []), dossier("SYN-T1", [])]
        self.assertTrue(test_agreement(ds)["passed"])
        ds2 = [dossier("SYN-T1", []), dossier("SYN-T2", [])]
        self.assertFalse(test_agreement(ds2)["passed"])

    def test_evidence_floor_fails_on_tier5_only(self):
        tier5 = dict(GOOD_CLAIM); tier5["evidence_tier"] = 5
        self.assertFalse(test_evidence_floor(spec("SYN-T1", [tier5]))["passed"])

    def test_evidence_floor_passes_with_audited_tier2(self):
        self.assertTrue(test_evidence_floor(spec("SYN-T1", [GOOD_CLAIM]))["passed"])

    def test_evidence_floor_fails_when_claims_unaudited(self):
        unaudited = dict(GOOD_CLAIM); unaudited["verification_status"] = "unverified"
        self.assertFalse(test_evidence_floor(spec("SYN-T1", [unaudited]))["passed"])

    def test_stability(self):
        self.assertTrue(test_stability(spec("SYN-T1", []), spec("SYN-T1", []))["passed"])
        self.assertFalse(test_stability(spec("SYN-T1", []), spec("SYN-T2", []))["passed"])

    def test_dissent_log_required(self):
        s = spec("SYN-T1", []); del s["dissent_log"]
        self.assertFalse(check_dissent_log(s)["passed"])
        s2 = spec("SYN-T1", [], dissent=[])
        self.assertFalse(check_dissent_log(s2)["passed"])

    def test_full_consensus_run(self):
        ds = [dossier("SYN-T1", [GOOD_CLAIM]), dossier("SYN-T1", [GOOD_CLAIM])]
        s = spec("SYN-T1", [GOOD_CLAIM])
        out = run_consensus_tests(ds, s, swapped_spec=spec("SYN-T1", [GOOD_CLAIM]))
        self.assertTrue(out["all_passed"], out)


class TestFocus(unittest.TestCase):
    def test_only_audited_claims_count(self):
        unaudited = dict(GOOD_CLAIM); unaudited["verification_status"] = "unverified"
        out = focus_score({"claims": [GOOD_CLAIM, unaudited, OPINION_CLAIM]})
        self.assertEqual(out["audited_claim_count"], 1)
        self.assertEqual(out["score"], 70)

    def test_empty_is_zero(self):
        out = focus_score({"claims": []})
        self.assertEqual(out["score"], 0)

    def test_duplicate_claim_id_counts_once(self):
        # Regression: the same audited claim listed twice used to score
        # twice (140 for two copies of a tier-2 claim).
        out = focus_score({"claims": [GOOD_CLAIM, dict(GOOD_CLAIM)]})
        self.assertEqual(out["audited_claim_count"], 1)
        self.assertEqual(out["score"], 70)

    def test_boolean_tier_is_not_a_tier(self):
        # Regression: bool is a subclass of int in Python, so a claim with
        # evidence_tier True used to score as a tier-1 claim (weight 100).
        bool_claim = dict(GOOD_CLAIM); bool_claim["evidence_tier"] = True
        out = focus_score({"claims": [bool_claim]})
        self.assertEqual(out["audited_claim_count"], 0)
        self.assertEqual(out["score"], 0)


class TestProvidersAndManifest(unittest.TestCase):
    def test_mock_provider_output_is_synthetic(self):
        out = MockProvider().research({"frame_id": "SYN-FRAME-001"})
        self.assertTrue(out["_synthetic"])
        self.assertEqual(out["frame_id"], "SYN-FRAME-001")

    def test_mock_run_produces_valid_manifest(self):
        provider = MockProvider()
        provider.research({"frame_id": "SYN-FRAME-001"})
        manifest = build_manifest(provider.name, provider.model_version,
                                  "synthetic prompt placeholder",
                                  tool_versions={"mock-tool": "0"}, budget={"max_units": 1},
                                  declared_use="research", run_id="SYN-RUN-001")
        self.assertEqual(validate_artifact("run_manifest", manifest), [])
        self.assertEqual(len(manifest["prompt_hash"]), 64)


class TestSchemas(unittest.TestCase):
    def test_synthetic_frame_validates(self):
        doc = json.loads((ROOT / "examples/synthetic/frame.json").read_text())
        self.assertEqual(validate_artifact("frame", doc), [])

    def test_missing_required_field_fails(self):
        errors = validate_artifact("frame", {"artifact_type": "frame"})
        self.assertGreater(len(errors), 0)


if __name__ == "__main__":
    unittest.main()
