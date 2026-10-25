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

from madd.gate0 import (APPROVED_THRESHOLDS, build_agent_pack,
                        evaluate_thresholds, leakage_scan, list_case_ids,
                        load_input_pack, load_sealed_outcome, score_run,
                        validate_dataset)

ROOT = Path(__file__).resolve().parent.parent
GATE0 = ROOT / "gate0"


class TestGate0Dataset(unittest.TestCase):
    """Tests for the Gate 0 dataset."""

    @classmethod
    def setUpClass(cls):
        """Set up the class fixtures."""
        cls.case_ids = list_case_ids(GATE0)
        cls.packs = {cid: load_input_pack(cid, GATE0) for cid in cls.case_ids}
        cls.outcomes = {cid: load_sealed_outcome(cid, GATE0) for cid in cls.case_ids}

    def test_case_ids_present(self):
        """Case ids present."""
        self.assertGreaterEqual(len(self.case_ids), 4)

    def test_every_input_claim_is_fully_cited(self):
        """Every input claim is fully cited."""
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
        """Leakage scan passes on all real packs."""
        for case_id, pack in self.packs.items():
            problems = leakage_scan(pack)
            self.assertEqual(problems, [], case_id + ": " + json.dumps(problems))

    def test_sealed_outcomes_exist_for_exactly_the_input_case_ids(self):
        """Sealed outcomes exist for exactly the input case ids."""
        sealed_files = sorted(p.name[: -len(".outcome.json")]
                                for p in (GATE0 / "sealed").glob("*.outcome.json"))
        self.assertEqual(sealed_files, self.case_ids)

    def test_outcome_classes_and_balance(self):
        """Outcome classes and balance."""
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
        """Dataset validation is clean."""
        report = validate_dataset(GATE0)
        self.assertTrue(report["ok"], json.dumps(report["errors"], indent=2))
        self.assertEqual(report["error_count"], 0)

    def test_build_agent_pack_returns_input_only(self):
        """Build agent pack returns input only."""
        sealed_keys = {"outcome_class", "pivotal_result", "outcome_source_identifier",
                       "outcome_source_type", "outcome_date", "reason_class"}
        for case_id in self.case_ids:
            pack = build_agent_pack(case_id, GATE0)
            self.assertEqual(pack["case_id"], case_id)
            self.assertTrue(sealed_keys.isdisjoint(pack.keys()), case_id)

    def test_build_agent_pack_refuses_leaky_pack(self):
        """Build agent pack refuses leaky pack."""
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
        """Score run with invented predictions."""
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
        """Score run kill alias and missing."""
        invented = {cid: "kill" for cid in self.case_ids[:2]}
        result = score_run(invented, GATE0 / "sealed")
        self.assertEqual(result["scored_count"], 2)
        self.assertEqual(len(result["missing_predictions"]), len(self.case_ids) - 2)
        expected_killed = sum(1 for cid in self.case_ids[:2]
                              if self.outcomes[cid]["outcome_class"] == "negative")
        self.assertEqual(result["failures_correctly_killed"], expected_killed)


def _score(correct, killed, advanced):
    # INVENTED score dicts for threshold tests only: plumbing fixtures in
    # the shape score_run returns, not results of any run.
    """Score a run from compact prediction maps."""
    return {"case_count": 8, "correct_calls": correct,
            "failures_correctly_killed": killed,
            "positives_correctly_advanced": advanced}


class TestEvaluateThresholds(unittest.TestCase):
    """Tests for evaluate thresholds."""
    def _statuses(self, report):
        """Extract per-check statuses from a threshold evaluation."""
        return {c["threshold"]: c["status"] for c in report["checks"]}

    def test_thresholds_match_approved_spec_values(self):
        """Thresholds match approved spec values."""
        self.assertEqual(APPROVED_THRESHOLDS["min_failures_killed"], 3)
        self.assertEqual(APPROVED_THRESHOLDS["min_positives_advanced"], 3)
        self.assertEqual(APPROVED_THRESHOLDS["min_baseline_margin"], 1)
        self.assertEqual(APPROVED_THRESHOLDS["max_audit_violations"], 0)
        self.assertEqual(APPROVED_THRESHOLDS["max_judge_swap_flips"], 1)

    def test_full_pass(self):
        """Full pass."""
        report = evaluate_thresholds(_score(7, 3, 4), baseline_score=_score(5, 2, 3),
                                     audit_violations=0, judge_swap_flips=1)
        self.assertTrue(report["passed"])
        self.assertTrue(all(s == "pass" for s in self._statuses(report).values()))

    def test_too_few_kills_fails(self):
        """Too few kills fails."""
        report = evaluate_thresholds(_score(6, 2, 4), baseline_score=_score(5, 2, 3),
                                     audit_violations=0, judge_swap_flips=0)
        self.assertFalse(report["passed"])
        self.assertEqual(self._statuses(report)["failure_kill_rate"], "fail")

    def test_too_few_advances_fails(self):
        """Too few advances fails."""
        report = evaluate_thresholds(_score(6, 4, 2), baseline_score=_score(5, 2, 3),
                                     audit_violations=0, judge_swap_flips=0)
        self.assertFalse(report["passed"])
        self.assertEqual(self._statuses(report)["positive_advance_rate"], "fail")

    def test_baseline_tie_fails_margin(self):
        """Baseline tie fails margin."""
        report = evaluate_thresholds(_score(6, 3, 3), baseline_score=_score(6, 3, 3),
                                     audit_violations=0, judge_swap_flips=0)
        self.assertFalse(report["passed"])
        self.assertEqual(self._statuses(report)["baseline_margin"], "fail")

    def test_one_audit_violation_fails(self):
        """One audit violation fails."""
        report = evaluate_thresholds(_score(8, 4, 4), baseline_score=_score(5, 2, 3),
                                     audit_violations=1, judge_swap_flips=0)
        self.assertFalse(report["passed"])
        self.assertEqual(self._statuses(report)["audit_integrity"], "fail")

    def test_two_judge_flips_fail(self):
        """Two judge flips fail."""
        report = evaluate_thresholds(_score(8, 4, 4), baseline_score=_score(5, 2, 3),
                                     audit_violations=0, judge_swap_flips=2)
        self.assertFalse(report["passed"])
        self.assertEqual(self._statuses(report)["judge_swap_stability"], "fail")

    def test_missing_inputs_are_not_evaluable_never_pass(self):
        """Missing inputs are not evaluable never pass."""
        report = evaluate_thresholds(_score(8, 4, 4))
        self.assertFalse(report["passed"])
        statuses = self._statuses(report)
        self.assertEqual(statuses["baseline_margin"], "not_evaluable")
        self.assertEqual(statuses["audit_integrity"], "not_evaluable")
        self.assertEqual(statuses["judge_swap_stability"], "not_evaluable")
        self.assertEqual(statuses["failure_kill_rate"], "pass")

    def test_missing_counts_are_not_evaluable_not_fail(self):
        """Missing counts are not evaluable not fail."""
        report = evaluate_thresholds({"case_count": 8, "scored_count": 8,
                                      "correct_calls": 8, "missing_predictions": []},
                                     baseline_score=_score(5, 2, 3),
                                     audit_violations=0, judge_swap_flips=0)
        self.assertFalse(report["passed"])
        statuses = self._statuses(report)
        self.assertEqual(statuses["failure_kill_rate"], "not_evaluable")
        self.assertEqual(statuses["positive_advance_rate"], "not_evaluable")

    def test_incomplete_run_cannot_pass(self):
        """Incomplete run cannot pass."""
        partial = _score(6, 3, 3)
        partial.update({"scored_count": 6,
                        "missing_predictions": ["case-x", "case-y"]})
        report = evaluate_thresholds(partial, baseline_score=_score(4, 2, 2),
                                     audit_violations=0, judge_swap_flips=0)
        self.assertFalse(report["passed"])
        self.assertEqual(self._statuses(report)["run_completeness"], "fail")
        self.assertEqual(self._statuses(report)["failure_kill_rate"], "pass")


if __name__ == "__main__":
    unittest.main()
