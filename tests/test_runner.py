"""Runner tests: full Gate 0 runs and frame runs over stub providers.

The stubs decide advance or kill by an invented allowlist of drug
names written into this file. That is plumbing behaviour, not a model
and not a result: no score in here is evidence about any real program,
and nothing here is reported as a Gate 0 result anywhere.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.artifacts import verify_frozen
from madd.budget import BudgetExceeded
from madd.gate0 import list_case_ids, load_sealed_outcome
from madd.runner import gate_report, run_frame, run_gate0
from madd.schemas import validate_artifact

ROOT = Path(__file__).resolve().parent.parent
GATE0 = ROOT / "gate0"
CASE_IDS = list_case_ids(GATE0)
OUTCOMES = {cid: load_sealed_outcome(cid, GATE0)["outcome_class"] for cid in CASE_IDS}
DRUGS = {}
from madd.gate0 import load_input_pack
for _cid in CASE_IDS:
    DRUGS[_cid] = load_input_pack(_cid, GATE0)["drug_name"]


def good_claim(cid):
    """Build a claim that passes the audit."""
    return {"claim_id": cid, "text": "invented claim " + cid,
            "load_bearing": True, "evidence_tier": 2,
            "source_kind": "journal_article", "source_identifier": "12345678",
            "identifier_type": "pmid", "verification_status": "quote_checked",
            "supporting_quote": "invented supporting quote"}


class CaseStub:
    """Provider stub: endorses the cases whose drug is in advance_for."""

    def __init__(self, label, advance_for=(), cost=0.0, family="stub"):
        """Initialize the test double."""
        self.name = "case-stub-" + label
        self.model_version = "stub-v1"
        self.label = label
        self.advance_for = set(advance_for)
        self.cost_per_call_usd = cost
        self.family = family

    def research(self, frame):
        """Return the double's fixed research result."""
        drug = frame.get("drug_name")
        dossier_id = "D-" + self.label + "-" + str(drug)
        if drug in self.advance_for:
            return {"artifact_type": "dossier", "schema_version": "0.1.0",
                    "dossier_id": dossier_id, "frame_id": frame.get("frame_id"),
                    "agent_id": "agent-" + self.label, "model_family": self.family,
                    "proposed_focus_id": frame.get("target"),
                    "direction": "invented", "unverified_notes": [],
                    "claims": [good_claim("C-" + self.label + "-" + str(drug))]}
        return {"artifact_type": "dossier", "schema_version": "0.1.0",
                "dossier_id": dossier_id, "frame_id": frame.get("frame_id"),
                "agent_id": "agent-" + self.label, "model_family": self.family,
                "proposed_focus_id": None, "direction": "invented",
                "unverified_notes": ["stub declines to endorse"],
                "claims": []}


def providers_for(advance_drugs):
    """Build providers keyed by case outcome."""
    return (CaseStub("a", advance_drugs), CaseStub("b", advance_drugs),
            CaseStub("judge", advance_drugs))


class TestRunGate0(unittest.TestCase):
    """Tests for Gate 0 runs."""
    def test_advance_everything_fails_on_kills(self):
        """Advance everything fails on kills."""
        a, b, judge = providers_for(set(DRUGS.values()))
        baseline = CaseStub("base", set(DRUGS.values()))
        bundle = run_gate0([a, b], judge_provider=judge, baseline_provider=baseline,
                           gate0_dir=GATE0, run_id="test-run-1")
        self.assertEqual(bundle["outcome"], "fail")
        self.assertEqual(bundle["debate_score"]["positives_correctly_advanced"], 4)
        self.assertEqual(bundle["debate_score"]["failures_correctly_killed"], 0)
        statuses = {c["threshold"]: c["status"]
                    for c in bundle["thresholds"]["checks"]}
        self.assertEqual(statuses["failure_kill_rate"], "fail")
        self.assertEqual(statuses["run_completeness"], "pass")
        self.assertEqual(bundle["audit_violations"], 0)
        self.assertTrue(verify_frozen(bundle["frozen_bundle"]))
        self.assertEqual(len(bundle["input_pack_hashes"]), 8)

    def test_perfect_stub_passes_and_report_validates(self):
        """Perfect stub passes and report validates."""
        advance = {DRUGS[c] for c in CASE_IDS if OUTCOMES[c] == "positive"}
        a, b, judge = providers_for(advance)
        # A scored run's stability threshold needs the swap
        # experiment: a second judge from a different family whose
        # calls agree with the operative judge's.
        swap = CaseStub("swap", advance, family="stub-other")
        baseline = CaseStub("base", set())  # baseline kills everything: 4 correct
        bundle = run_gate0([a, b], judge_provider=judge,
                           swap_judge_provider=swap,
                           baseline_provider=baseline,
                           gate0_dir=GATE0, run_id="test-run-2")
        self.assertEqual(bundle["debate_score"]["correct_calls"], 8)
        self.assertEqual(bundle["outcome"], "pass")
        report = gate_report(bundle)
        self.assertEqual(validate_artifact("gate_report", report), [])
        self.assertEqual(report["result"], "pass")
        self.assertEqual(report["subject_id"], "test-run-2")

    def test_no_judge_run_records_swap_not_evaluable(self):
        """No judge means no swap ran: flips unknown, never a 0-flip pass."""
        a, b, _judge = providers_for(set())
        baseline = CaseStub("base", set())
        bundle = run_gate0([a, b], baseline_provider=baseline,
                           gate0_dir=GATE0, run_id="test-run-no-judge")
        self.assertIsNone(bundle["judge_swap_flips"])
        statuses = {c["threshold"]: c["status"]
                    for c in bundle["thresholds"]["checks"]}
        self.assertEqual(statuses["judge_swap_stability"], "not_evaluable")

    def test_baseline_is_required(self):
        """Baseline is required."""
        a, b, _judge = providers_for(set())
        with self.assertRaises(ValueError):
            run_gate0([a, b], gate0_dir=GATE0)

    def test_run_budget_is_shared_across_cases(self):
        """Run budget is shared across cases."""
        a, b, judge = providers_for(set(DRUGS.values()))
        for stub in (a, b, judge):
            stub.cost_per_call_usd = 1.0
        baseline = CaseStub("base", set(DRUGS.values()), cost=1.0)
        with self.assertRaises(BudgetExceeded):
            run_gate0([a, b], judge_provider=judge, baseline_provider=baseline,
                      budget={"max_cost_usd": 10.0}, gate0_dir=GATE0)


    def test_progress_events_fire_in_order(self):
        """Progress events fire in order."""
        a, b, judge = providers_for(set(DRUGS.values()))
        baseline = CaseStub("base", set())
        events = []
        run_gate0([a, b], judge_provider=judge, baseline_provider=baseline,
                  gate0_dir=GATE0, on_event=events.append, run_id="test-events")
        names = [e["event"] for e in events]
        self.assertEqual(names[0], "run_started")
        self.assertEqual(names[-1], "run_finished")
        self.assertEqual(names.count("baseline_case_done"), 8)
        self.assertEqual(names.count("debate_case_done"), 8)
        self.assertEqual(events[-1]["debate_correct"], 4)

    def test_parallel_matches_sequential(self):
        """Parallel matches sequential."""
        advance = {DRUGS[c] for c in CASE_IDS[:5]}
        a1, b1, j1 = providers_for(advance)
        seq = run_gate0([a1, b1], judge_provider=j1,
                        baseline_provider=CaseStub("base", set()),
                        gate0_dir=GATE0, run_id="test-seq")
        a2, b2, j2 = providers_for(advance)
        par = run_gate0([a2, b2], judge_provider=j2,
                        baseline_provider=CaseStub("base", set()),
                        gate0_dir=GATE0, run_id="test-par", max_workers=4)
        self.assertEqual(seq["predictions"], par["predictions"])
        self.assertEqual(list(par["case_records"].keys()), CASE_IDS)
        self.assertEqual(seq["debate_score"], par["debate_score"])


class TestRunFrame(unittest.TestCase):
    """Tests for frame runs."""
    def test_frame_run_with_mocks_is_no_go_and_frozen(self):
        """Frame run with mocks is no go and frozen."""
        from madd.providers import MockProvider
        frame = {"artifact_type": "frame", "schema_version": "0.1.0",
                 "frame_id": "TEST-FRAME", "question": "invented",
                 "round_cap": 2}
        bundle = run_frame(frame, [MockProvider("001"), MockProvider("002")],
                           judge_provider=MockProvider("003"), run_id="test-frame-1")
        self.assertEqual(bundle["outcome"], "no_go")
        self.assertTrue(verify_frozen(bundle["frozen_bundle"]))


if __name__ == "__main__":
    unittest.main()
