"""Run comparison tests over two stub bundles with different calls."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.compare import compare_bundles
from madd.gate0 import list_case_ids, load_input_pack
from madd.runner import run_gate0
from tests.test_runner import CaseStub, GATE0

CASE_IDS = list_case_ids(GATE0)
DRUGS = {cid: load_input_pack(cid, GATE0)["drug_name"] for cid in CASE_IDS}


def bundle_for(advance_drugs, run_id):
    return run_gate0(
        [CaseStub("a", advance_drugs), CaseStub("b", advance_drugs)],
        judge_provider=CaseStub("j", advance_drugs),
        baseline_provider=CaseStub("base", set()),
        gate0_dir=GATE0, run_id=run_id)


class TestCompare(unittest.TestCase):
    def test_identical_runs_have_no_changes(self):
        a = bundle_for(set(), "cmp-a")
        b = bundle_for(set(), "cmp-b")
        diff = compare_bundles(a, b)
        self.assertEqual(diff["flipped_calls"], [])
        self.assertEqual(diff["threshold_changes"], [])
        self.assertEqual(diff["score_deltas"]["debate_correct"], 0)
        self.assertTrue(diff["same_case_set"])

    def test_advancing_everything_flips_and_moves_thresholds(self):
        a = bundle_for(set(), "cmp-a")
        b = bundle_for(set(DRUGS.values()), "cmp-b")
        diff = compare_bundles(a, b)
        self.assertEqual(len(diff["flipped_calls"]), 8)
        self.assertEqual(diff["score_deltas"]["positives_advanced"], 4)
        changed = {c["threshold"] for c in diff["threshold_changes"]}
        self.assertIn("positive_advance_rate", changed)
        self.assertIn("failure_kill_rate", changed)


if __name__ == "__main__":
    unittest.main()
