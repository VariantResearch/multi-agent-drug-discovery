"""Gate 0 dataset integrity tests.

These tests run against the REAL Gate 0 dataset in gate0/ (real drugs,
real primary sources). The only invented values are the prediction maps
in the score_run tests, which are labelled as invented there: they test
the scoring plumbing, not any research result.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.gate0 import (build_agent_pack, leakage_scan, list_case_ids,
                        load_input_pack, load_sealed_outcome, score_run,
                        validate_dataset)

ROOT = Path(__file__).resolve().parent.parent
GATE0 = ROOT / "gate0"


class TestGate0Dataset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case_ids = list_case_ids(GATE0)
        cls.packs = {cid: load_input_pack(cid, GATE0) for cid in cls.case_ids}
        cls.outcomes = {cid: load_sealed_outcome(cid, GATE0) for cid in cls.case_ids}

    def test_case_ids_present(self):
        self.assertGreaterEqual(len(self.case_ids), 4)

    def test_every_input_claim_is_fully_cited(self):
        for case_id, pack in self.packs.items():
            self.assertTrue(pack["claims"], case_id)
            for claim in pack["claims"]:
                label = case_id + "/" + claim.get("claim_id", "?")
                identifier = claim.get("source_identifier")
                self.assertIsInstance(identifier, str, label)
                self.assertNotEqual(identifier.strip(), "", label)
                self.assertIn(claim.get("identifier_type"), ("doi", "pmid", "nct"), label)
                tier = claim.get("evidence_tier")
                self.assertIsInstance(tier, int, label)
                self.assertGreaterEqual(tier, 1, label)
                self.assertLessEqual(tier, 5, label)
                self.assertEqual(claim.get("verification_status"), "quote_checked", label)
                quote = claim.get("supporting_quote")
                self.assertIsInstance(quote, str, label)
                self.assertNotEqual(quote.strip(), "", label)
                self.assertLessEqual(len(quote.split()), 25, label)

    def test_leakage_scan_passes_on_all_real_packs(self):
        for case_id, pack in self.packs.items():
            problems = leakage_scan(pack)
            self.assertEqual(problems, [], case_id + ": " + json.dumps(problems))

    def test_sealed_outcomes_exist_for_exactly_the_input_case_ids(self):
        sealed_files = sorted(p.name[: -len(".outcome.json")]
                                for p in (GATE0 / "sealed").glob("*.outcome.json"))
        self.assertEqual(sealed_files, self.case_ids)

    def test_outcome_classes_and_balance(self):
        counts = {"positive": 0, "negative": 0}
        for case_id, outcome in self.outcomes.items():
            self.assertIn(outcome.get("outcome_class"), ("positive", "negative"), case_id)
            counts[outcome["outcome_class"]] += 1
            self.assertTrue(outcome.get("pivotal_result"), case_id)
            self.assertTrue(outcome.get("outcome_source_identifier"), case_id)
            self.assertTrue(outcome.get("outcome_date"), case_id)
        self.assertGreaterEqual(counts["positive"], 2)
        self.assertGreaterEqual(counts["negative"], 2)

    def test_dataset_validation_is_clean(self):
        report = validate_dataset(GATE0)
        self.assertTrue(report["ok"], json.dumps(report["errors"], indent=2))
        self.assertEqual(report["error_count"], 0)

    def test_build_agent_pack_returns_input_only(self):
        sealed_keys = {"outcome_class", "pivotal_result", "outcome_source_identifier",
                       "outcome_source_type", "outcome_date", "reason_class"}
        for case_id in self.case_ids:
            pack = build_agent_pack(case_id, GATE0)
            self.assertEqual(pack["case_id"], case_id)
            self.assertTrue(sealed_keys.isdisjoint(pack.keys()), case_id)

    def test_build_agent_pack_refuses_leaky_pack(self):
        pack = load_input_pack(self.case_ids[0], GATE0)
        pack["claims"] = pack["claims"] + [{
            "claim_id": "TEST-LEAK", "text": "placeholder", "load_bearing": False,
            "evidence_tier": 2, "source_kind": "journal_article",
            "source_identifier": "12345678", "identifier_type": "pmid",
            "verification_status": "quote_checked", "supporting_quote": "placeholder",
        }]
        problems = leakage_scan(pack)
        self.assertEqual(problems, [])
        pack["outcome_class"] = "positive"
        problems = leakage_scan(pack)
        self.assertTrue(any(p["code"] == "sealed_field_present" for p in problems))

    def test_score_run_with_invented_predictions(self):
        # INVENTED prediction values, written for this test only: predict
        # every case positive. Against the real sealed set this must
        # advance exactly the real positives and miss the real negatives.
        invented = {cid: "positive" for cid in self.case_ids}
        result = score_run(invented, GATE0 / "sealed")
        positives = sum(1 for o in self.outcomes.values() if o["outcome_class"] == "positive")
        negatives = sum(1 for o in self.outcomes.values() if o["outcome_class"] == "negative")
        self.assertEqual(result["case_count"], len(self.case_ids))
        self.assertEqual(result["correct_calls"], positives)
        self.assertEqual(result["positives_correctly_advanced"], positives)
        self.assertEqual(result["failures_correctly_killed"], 0)
        self.assertEqual(len(result["incorrect_calls"]), negatives)
        self.assertEqual(result["missing_predictions"], [])

    def test_score_run_kill_alias_and_missing(self):
        # INVENTED prediction values, written for this test only.
        invented = {cid: "kill" for cid in self.case_ids[:2]}
        result = score_run(invented, GATE0 / "sealed")
        self.assertEqual(result["scored_count"], 2)
        self.assertEqual(len(result["missing_predictions"]), len(self.case_ids) - 2)
        expected_killed = sum(1 for cid in self.case_ids[:2]
                              if self.outcomes[cid]["outcome_class"] == "negative")
        self.assertEqual(result["failures_correctly_killed"], expected_killed)


if __name__ == "__main__":
    unittest.main()
