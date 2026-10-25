"""Debate engine tests.

All providers, dossiers, and claims here are invented test fixtures in
the shape the protocol uses. They test the engine plumbing: strikes,
ranking, evolution, consensus wiring, budget stop, and the frozen
record. They are not research and prove nothing about any real target.
"""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.artifacts import verify_frozen
from madd.budget import BudgetExceeded
from madd.debate import audit_dossier, rank_dossiers, run_debate
from madd.schemas import validate_artifact

FRAME = {"artifact_type": "frame", "schema_version": "0.1.0",
         "frame_id": "TEST-FRAME-1", "question": "invented test question",
         "round_cap": 2}


def good_claim(cid, tier=2):
    return {"claim_id": cid, "text": "invented claim " + cid,
            "load_bearing": True, "evidence_tier": tier,
            "source_kind": "journal_article", "source_identifier": "12345678",
            "identifier_type": "pmid", "verification_status": "quote_checked",
            "supporting_quote": "invented supporting quote"}


def bad_claim(cid):
    return {"claim_id": cid, "text": "invented bad claim " + cid,
            "load_bearing": True, "evidence_tier": 0,
            "source_kind": "model_opinion", "source_identifier": None,
            "identifier_type": "pmid", "verification_status": "unverified",
            "supporting_quote": ""}


def dossier(dossier_id, agent_id, focus, claims):
    return {"artifact_type": "dossier", "schema_version": "0.1.0",
            "dossier_id": dossier_id, "frame_id": FRAME["frame_id"],
            "agent_id": agent_id, "model_family": "stub",
            "proposed_focus_id": focus, "direction": "invented direction",
            "claims": claims, "unverified_notes": []}


class StubProvider:
    def __init__(self, name, dossier_dict, cost=0.0):
        self.name = name
        self.model_version = name + "-v1"
        self.cost_per_call_usd = cost
        self._dossier = dossier_dict
        self.calls = 0

    def research(self, frame):
        self.calls += 1
        return copy.deepcopy(self._dossier)


def agreeing_providers():
    a = StubProvider("stub-a", dossier("D-A", "agent-a", "FOCUS-A",
                                       [good_claim("C-A1"), good_claim("C-A2", tier=3)]))
    b = StubProvider("stub-b", dossier("D-B", "agent-b", "FOCUS-A",
                                       [good_claim("C-B1")]))
    return a, b


class TestDebateEngine(unittest.TestCase):
    def test_agreement_with_judge_locks_and_freezes(self):
        a, b = agreeing_providers()
        judge = StubProvider("stub-judge", dossier("D-J", "agent-j", "FOCUS-A",
                                                   [good_claim("C-J1")]))
        record = run_debate(FRAME, [a, b], judge_provider=judge)
        self.assertEqual(record["outcome"], "locked")
        self.assertTrue(record["consensus"]["all_passed"])
        self.assertTrue(record["red_team_round"])
        self.assertEqual(record["spec"]["outcome"], "locked")
        self.assertEqual(validate_artifact("consensus_spec", record["spec"]), [])
        self.assertTrue(verify_frozen(record["frozen_record"]))
        self.assertEqual(record["spec"]["dissent_log"], [])
        self.assertIn("dissent_none_reason", record["spec"])
        merged_ids = {c["claim_id"] for c in record["spec"]["claims"]}
        self.assertEqual(merged_ids, {"C-A1", "C-A2", "C-B1"})

    def test_no_judge_means_stability_not_established(self):
        a, b = agreeing_providers()
        record = run_debate(FRAME, [a, b])
        self.assertEqual(record["outcome"], "no_go")
        stability = [r for r in record["consensus"]["results"]
                     if r["test"] == "stability"][0]
        self.assertFalse(stability["passed"])

    def test_disagreement_is_no_go_with_dissent(self):
        a = StubProvider("stub-a", dossier("D-A", "agent-a", "FOCUS-A", [good_claim("C-A1")]))
        b = StubProvider("stub-b", dossier("D-B", "agent-b", "FOCUS-B", [good_claim("C-B1")]))
        judge = StubProvider("stub-judge", dossier("D-J", "agent-j", "FOCUS-A",
                                                   [good_claim("C-J1")]))
        record = run_debate(FRAME, [a, b], judge_provider=judge)
        self.assertEqual(record["outcome"], "no_go")
        self.assertFalse(record["red_team_round"])
        self.assertTrue(len(record["spec"]["dissent_log"]) >= 2)
        kinds = {t["kind"] for t in record["cross_examination"]}
        self.assertEqual(kinds, {"focus_disagreement"})

    def test_struck_claim_is_out_and_listed(self):
        a = StubProvider("stub-a", dossier("D-A", "agent-a", "FOCUS-A",
                                           [good_claim("C-A1"), bad_claim("C-BAD")]))
        b = StubProvider("stub-b", dossier("D-B", "agent-b", "FOCUS-A", [good_claim("C-B1")]))
        record = run_debate(FRAME, [a, b])
        struck_ids = {s["claim_id"] for s in record["strike_list"]}
        self.assertIn("C-BAD", struck_ids)
        bad_entry = [s for s in record["strike_list"] if s["claim_id"] == "C-BAD"][0]
        self.assertIn("non_evidence_source_kind", bad_entry["reasons"])
        spec_ids = {c["claim_id"] for c in record["spec"]["claims"]}
        self.assertNotIn("C-BAD", spec_ids)

    def test_tier5_only_evidence_fails_the_floor(self):
        a = StubProvider("stub-a", dossier("D-A", "agent-a", "FOCUS-A",
                                           [good_claim("C-A1", tier=5)]))
        b = StubProvider("stub-b", dossier("D-B", "agent-b", "FOCUS-A",
                                           [good_claim("C-B1", tier=5)]))
        judge = StubProvider("stub-judge", dossier("D-J", "agent-j", "FOCUS-A",
                                                   [good_claim("C-J1", tier=5)]))
        record = run_debate(FRAME, [a, b], judge_provider=judge)
        self.assertEqual(record["outcome"], "no_go")
        floor = [r for r in record["consensus"]["results"]
                 if r["test"] == "evidence_floor"][0]
        self.assertFalse(floor["passed"])

    def test_judge_swap_flip_fails_stability_and_is_dissented(self):
        a, b = agreeing_providers()
        judge = StubProvider("stub-judge", dossier("D-J", "agent-j", "FOCUS-OTHER",
                                                   [good_claim("C-J1")]))
        record = run_debate(FRAME, [a, b], judge_provider=judge)
        self.assertEqual(record["outcome"], "no_go")
        stability = [r for r in record["consensus"]["results"]
                     if r["test"] == "stability"][0]
        self.assertFalse(stability["passed"])
        self.assertTrue(any("judge swap" in d["objection"]
                            for d in record["spec"]["dissent_log"]))

    def test_ranking_prefers_stronger_evidence(self):
        strong = audit_dossier(dossier("D-S", "agent-s", "FOCUS-A",
                                       [good_claim("C-S1", tier=1)]))
        weak = audit_dossier(dossier("D-W", "agent-w", "FOCUS-B",
                                     [good_claim("C-W1", tier=3)]))
        ranking = rank_dossiers([weak, strong])
        self.assertEqual(ranking[0]["dossier_id"], "D-S")
        self.assertEqual(ranking[0]["wins"], 1.0)

    def test_budget_stop_prevents_calls_past_the_cap(self):
        a = StubProvider("stub-a", dossier("D-A", "agent-a", "FOCUS-A",
                                           [good_claim("C-A1")]), cost=5.0)
        b = StubProvider("stub-b", dossier("D-B", "agent-b", "FOCUS-A",
                                           [good_claim("C-B1")]), cost=5.0)
        with self.assertRaises(BudgetExceeded):
            run_debate(FRAME, [a, b], budget={"max_cost_usd": 6.0})
        self.assertEqual(a.calls, 1)
        self.assertEqual(b.calls, 0)

    def test_fewer_than_two_providers_rejected(self):
        a, _b = agreeing_providers()
        with self.assertRaises(ValueError):
            run_debate(FRAME, [a])

    def test_live_resolver_strikes_not_found_claims(self):
        d = dossier("D-R", "agent-r", "FOCUS-A",
                    [good_claim("C-LIVE"), good_claim("C-GONE")])

        def fake_resolver(identifier, identifier_type):
            return "not_found" if identifier == "12345678" else "resolved"

        d["claims"][1]["source_identifier"] = "87654321"
        audited = audit_dossier(d, resolver=fake_resolver)
        surviving_ids = {c["claim_id"] for c in audited["surviving_claims"]}
        struck = {s["claim_id"]: s["reasons"] for s in audited["struck"]}
        self.assertEqual(surviving_ids, {"C-GONE"})
        self.assertIn("citation_not_found_live", struck["C-LIVE"])

    def test_live_resolver_lookup_error_never_strikes(self):
        d = dossier("D-R2", "agent-r", "FOCUS-A", [good_claim("C-LIVE")])
        audited = audit_dossier(d, resolver=lambda i, t: "lookup_error")
        self.assertEqual(len(audited["surviving_claims"]), 1)
        self.assertEqual(audited["struck"], [])

    def test_duplicate_dossier_ids_rejected(self):
        a = StubProvider("stub-a", dossier("DUP-ID", "agent-a", "FOCUS-A",
                                           [good_claim("C-A1")]))
        b = StubProvider("stub-b", dossier("DUP-ID", "agent-b", "FOCUS-A",
                                           [good_claim("C-B1")]))
        with self.assertRaises(ValueError):
            run_debate(FRAME, [a, b])

    def test_manifest_records_every_call(self):
        a, b = agreeing_providers()
        judge = StubProvider("stub-judge", dossier("D-J", "agent-j", "FOCUS-A",
                                                   [good_claim("C-J1")]))
        record = run_debate(FRAME, [a, b], judge_provider=judge)
        calls = record["manifest"]["calls"]
        self.assertEqual(len(calls), 3)
        self.assertEqual([c["role"] for c in calls], ["research", "research", "judge"])
        self.assertTrue(all(c["prompt_hash"] for c in calls))
        self.assertEqual(len({c["prompt_hash"] for c in calls}), 1)
        self.assertEqual(record["rubric"]["not_applied"][0].split(":")[0],
                         "frame coverage")

    def test_judge_strikes_are_recorded(self):
        a, b = agreeing_providers()
        judge = StubProvider("stub-judge", dossier("D-J", "agent-j", "FOCUS-A",
                                                   [good_claim("C-J1"), bad_claim("C-JBAD")]))
        record = run_debate(FRAME, [a, b], judge_provider=judge)
        struck_ids = {s["claim_id"] for s in record["judge_swap"]["struck"]}
        self.assertIn("C-JBAD", struck_ids)


if __name__ == "__main__":
    unittest.main()
