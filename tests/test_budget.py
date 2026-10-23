"""Budget tracker tests. All figures are invented test values."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.budget import BudgetExceeded, BudgetTracker


class TestBudgetTracker(unittest.TestCase):
    def test_records_within_cap(self):
        tracker = BudgetTracker({"max_cost_usd": 10.0, "max_calls": 3})
        tracker.record(2.50, note="first")
        tracker.record(2.50)
        self.assertEqual(tracker.spent_usd, 5.0)
        self.assertEqual(tracker.calls_made, 2)
        self.assertEqual(tracker.remaining(), {"cost_usd": 5.0, "calls": 1})

    def test_cost_cap_is_a_hard_stop_and_records_nothing(self):
        tracker = BudgetTracker({"max_cost_usd": 4.0})
        tracker.record(3.0)
        with self.assertRaises(BudgetExceeded):
            tracker.record(1.01)
        self.assertEqual(tracker.spent_usd, 3.0)
        self.assertEqual(tracker.calls_made, 1)

    def test_exact_cap_is_allowed_next_call_is_not(self):
        tracker = BudgetTracker({"max_cost_usd": 4.0})
        tracker.record(4.0)
        self.assertFalse(tracker.would_exceed(0.0, calls=0))
        self.assertTrue(tracker.would_exceed(0.01))
        with self.assertRaises(BudgetExceeded):
            tracker.record(0.01)

    def test_call_cap(self):
        tracker = BudgetTracker({"max_calls": 2})
        tracker.record(0.0)
        tracker.record(0.0)
        with self.assertRaises(BudgetExceeded):
            tracker.record(0.0)

    def test_uncapped_budget_rejected(self):
        with self.assertRaises(ValueError):
            BudgetTracker({})
        with self.assertRaises(ValueError):
            BudgetTracker({"max_cost_usd": None})

    def test_negative_and_bool_values_rejected(self):
        with self.assertRaises(ValueError):
            BudgetTracker({"max_cost_usd": -1})
        tracker = BudgetTracker({"max_cost_usd": 5.0})
        with self.assertRaises(ValueError):
            tracker.record(-0.5)
        with self.assertRaises(ValueError):
            tracker.record(True)

    def test_to_dict_shape_for_manifest(self):
        tracker = BudgetTracker({"max_cost_usd": 10.0, "max_calls": 5})
        tracker.record(1.25, note="research call")
        state = tracker.to_dict()
        self.assertEqual(state["spent_usd"], 1.25)
        self.assertEqual(state["calls_made"], 1)
        self.assertEqual(state["entries"][0]["note"], "research call")
        self.assertEqual(state["remaining"]["calls"], 4)


if __name__ == "__main__":
    unittest.main()
