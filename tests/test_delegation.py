"""Delegation statement tests: acceptance conditions stated up front.

A frame may state, at delegation time, the conditions a delegated
contribution must satisfy (acceptance_conditions) and the boundary
of what it is responsible for (responsibility), in the pattern
recorded in docs/DESIGN-REFERENCES.md (the AutoSwarm entry). These
tests pin the contract: the statement is optional and defaults to
empty, it reaches the providers with the frame, it is frozen into
the run record and surfaced by the audit flow, malformed statements
are rejected, and no scoring surface changes because it exists.

All providers, dossiers, claims, and conditions here are invented
test fixtures. They test plumbing, not research.
"""
import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.artifacts import canonical_json, verify_frozen
from madd.audit_flow import audit_flow
from madd.debate import run_debate
from madd.runner import frame_for_case
from madd.schemas import validate_artifact

CONDITIONS = ["every load-bearing claim cites evidence from the "
              "supplied pack",
              "the dossier names one focus or declines to advance"]
RESPONSIBILITY = "judge the target and approach on the supplied evidence"

FRAME = {"artifact_type": "frame", "schema_version": "0.1.0",
         "frame_id": "TEST-DELEGATION-1", "question": "invented question",
         "round_cap": 2}


def good_claim(cid, tier=2):
    """Build a claim that passes the audit."""
    return {"claim_id": cid, "text": "invented claim " + cid,
            "load_bearing": True, "evidence_tier": tier,
            "source_kind": "journal_article", "source_identifier": "12345678",
            "identifier_type": "pmid", "verification_status": "quote_checked",
            "supporting_quote": "invented supporting quote"}


def dossier(dossier_id, agent_id, focus, claims):
    """Build a dossier for the tests."""
    return {"artifact_type": "dossier", "schema_version": "0.1.0",
            "dossier_id": dossier_id, "frame_id": FRAME["frame_id"],
            "agent_id": agent_id, "model_family": "stub",
            "proposed_focus_id": focus, "direction": "invented direction",
            "claims": claims, "unverified_notes": []}


class CapturingProvider:
    """Stub provider returning a fixed dossier, recording its frames."""

    def __init__(self, name, dossier_dict):
        """Initialize the test double."""
        self.name = name
        self.model_version = name + "-v1"
        self.cost_per_call_usd = 0.0
        self._dossier = dossier_dict
        self.frames = []

    def research(self, frame):
        """Record the frame received; return the fixed dossier."""
        self.frames.append(copy.deepcopy(frame))
        return copy.deepcopy(self._dossier)


def agreeing_providers():
    """Build stub providers that agree on a focus."""
    a = CapturingProvider("stub-a", dossier("D-A", "agent-a", "FOCUS-A",
                                            [good_claim("C-A1")]))
    b = CapturingProvider("stub-b", dossier("D-B", "agent-b", "FOCUS-A",
                                            [good_claim("C-B1")]))
    return a, b


def delegated_frame():
    """The shared test frame carrying a delegation statement."""
    frame = dict(FRAME)
    frame["acceptance_conditions"] = list(CONDITIONS)
    frame["responsibility"] = RESPONSIBILITY
    return frame


class DelegationRecordTests(unittest.TestCase):
    """The statement on the frozen record, and its absence by default."""

    def test_default_frame_records_an_empty_statement(self):
        """No statement on the frame: the record carries an empty one."""
        a, b = agreeing_providers()
        record = run_debate(dict(FRAME), [a, b])
        self.assertEqual(record["delegation"],
                         {"responsibility": None,
                          "acceptance_conditions": []})
        self.assertTrue(verify_frozen(record["frozen_record"]))

    def test_statement_is_recorded_verbatim_and_frozen(self):
        """A stated delegation is recorded exactly as the frame stated it."""
        a, b = agreeing_providers()
        record = run_debate(delegated_frame(), [a, b])
        self.assertEqual(record["delegation"],
                         {"responsibility": RESPONSIBILITY,
                          "acceptance_conditions": CONDITIONS})
        self.assertTrue(verify_frozen(record["frozen_record"]))

    def test_statement_reaches_every_provider_with_the_frame(self):
        """Delegation is stated at delegation time: providers see it."""
        a, b = agreeing_providers()
        run_debate(delegated_frame(), [a, b])
        for provider in (a, b):
            self.assertEqual(len(provider.frames), 1)
            seen = provider.frames[0]
            self.assertEqual(seen["acceptance_conditions"], CONDITIONS)
            self.assertEqual(seen["responsibility"], RESPONSIBILITY)

    def test_statement_round_trips_through_serialization(self):
        """The recorded statement survives canonical JSON unchanged."""
        a, b = agreeing_providers()
        record = run_debate(delegated_frame(), [a, b])
        restored = json.loads(canonical_json(record["delegation"]))
        self.assertEqual(restored, record["delegation"])

    def test_statement_changes_no_scoring_surface(self):
        """Ranking, strikes, spec, and outcome are identical with and
        without a statement: it is metadata, not a gate."""
        a1, b1 = agreeing_providers()
        plain = run_debate(dict(FRAME), [a1, b1])
        a2, b2 = agreeing_providers()
        stated = run_debate(delegated_frame(), [a2, b2])
        for key in ("outcome", "ranking", "strike_list", "consensus"):
            self.assertEqual(plain[key], stated[key], key)
        self.assertEqual(plain["spec"]["claims"], stated["spec"]["claims"])
        self.assertEqual(plain["spec"]["outcome"],
                         stated["spec"]["outcome"])


class DelegationValidationTests(unittest.TestCase):
    """Malformed statements are rejected before any provider is called."""

    def test_conditions_must_be_a_list_of_non_empty_strings(self):
        """A string, a non-string entry, and an empty entry all fail."""
        for bad in ("cite the pack", ["sound", 7], ["sound", "  "]):
            a, b = agreeing_providers()
            frame = dict(FRAME)
            frame["acceptance_conditions"] = bad
            with self.assertRaises(ValueError):
                run_debate(frame, [a, b])
            self.assertEqual(a.frames, [])

    def test_responsibility_must_be_a_string(self):
        """A non-string responsibility boundary fails."""
        a, b = agreeing_providers()
        frame = dict(FRAME)
        frame["responsibility"] = 42
        with self.assertRaises(ValueError):
            run_debate(frame, [a, b])
        self.assertEqual(a.frames, [])

    def test_frame_schema_types_the_statement(self):
        """The frame schema accepts the fields and rejects wrong types."""
        self.assertEqual(validate_artifact("frame", delegated_frame()), [])
        wrong = delegated_frame()
        wrong["acceptance_conditions"] = "cite the pack"
        self.assertTrue(validate_artifact("frame", wrong))
        wrong = delegated_frame()
        wrong["responsibility"] = ["not", "a", "string"]
        self.assertTrue(validate_artifact("frame", wrong))


class DelegationAuditSurfaceTests(unittest.TestCase):
    """The audit flow carries the statement next to the counts."""

    def test_audit_flow_surfaces_the_statement(self):
        """A judge or auditor reading the flow sees what was asked."""
        a, b = agreeing_providers()
        record = run_debate(delegated_frame(), [a, b])
        flow = audit_flow(record)
        self.assertEqual(flow["delegation"],
                         {"responsibility": RESPONSIBILITY,
                          "acceptance_conditions": CONDITIONS})

    def test_audit_flow_reads_old_records_as_an_empty_statement(self):
        """A record frozen before the statement existed reads empty."""
        record = {"strike_list": [], "outcome": "no_go",
                  "spec": {"claims": []},
                  "evolution": {"contributing_dossiers": ["d1"]},
                  "consensus": {"results": []}}
        flow = audit_flow(record)
        self.assertEqual(flow["delegation"],
                         {"responsibility": None,
                          "acceptance_conditions": []})


class Gate0FrameTests(unittest.TestCase):
    """frame_for_case passes a pack's statement onto the frame."""

    def _pack(self, **extra):
        """Build an invented case pack, with any extra top-level keys."""
        pack = {"case_id": "invented-case", "disease": "invented disease",
                "target": "GENE9 protein", "drug_name": "InventedDrug",
                "evidence_as_of": "2020-01-01", "claims": [],
                "forbidden_terms": ["invented outcome term"]}
        pack.update(extra)
        return pack

    def test_pack_statement_rides_at_the_frame_top_level(self):
        """A pack stating conditions produces a frame carrying them."""
        frame = frame_for_case("invented-case", self._pack(
            acceptance_conditions=list(CONDITIONS),
            responsibility=RESPONSIBILITY))
        self.assertEqual(frame["acceptance_conditions"], CONDITIONS)
        self.assertEqual(frame["responsibility"], RESPONSIBILITY)

    def test_pack_without_a_statement_produces_the_frame_it_always_did(self):
        """No statement in the pack: the keys are absent, not empty."""
        frame = frame_for_case("invented-case", self._pack())
        self.assertNotIn("acceptance_conditions", frame)
        self.assertNotIn("responsibility", frame)


if __name__ == "__main__":
    unittest.main()
