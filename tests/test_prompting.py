"""Prompting contract tests. All model responses are invented text."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.prompting import (SYSTEM_PROMPT, build_user_prompt,
                            parse_dossier_response)
from madd.schemas import validate_artifact

GOOD_RESPONSE = {
    "dossier_id": "D-1", "proposed_focus_id": "TARGET-X",
    "direction": "invented direction",
    "claims": [{"claim_id": "C1", "text": "invented", "load_bearing": True,
                "evidence_tier": 2, "source_kind": "journal_article",
                "source_identifier": "12345678", "identifier_type": "pmid",
                "verification_status": "quote_checked",
                "supporting_quote": "invented quote"}],
    "unverified_notes": [],
}


class TestPrompting(unittest.TestCase):
    def test_system_prompt_states_the_contract(self):
        self.assertIn("source_identifier", SYSTEM_PROMPT)
        self.assertIn("Never invent an identifier", SYSTEM_PROMPT)
        self.assertIn("ONLY a JSON object", SYSTEM_PROMPT)

    def test_user_prompt_carries_the_frame(self):
        frame = {"frame_id": "F-1", "question": "invented?"}
        prompt = build_user_prompt(frame)
        self.assertIn("F-1", prompt)
        self.assertIn("invented?", prompt)

    def test_plain_json_parses_and_identity_is_callers(self):
        dossier = parse_dossier_response(json.dumps(GOOD_RESPONSE),
                                         "agent-a", "family-x", "F-1")
        self.assertEqual(dossier["agent_id"], "agent-a")
        self.assertEqual(dossier["model_family"], "family-x")
        self.assertEqual(dossier["frame_id"], "F-1")
        self.assertEqual(dossier["proposed_focus_id"], "TARGET-X")
        self.assertEqual(validate_artifact("dossier", dossier), [])
        self.assertNotIn("parse_error", dossier)

    def test_fenced_json_parses(self):
        text = "```json\n" + json.dumps(GOOD_RESPONSE) + "\n```"
        dossier = parse_dossier_response(text, "agent-a", "family-x", "F-1")
        self.assertEqual(dossier["proposed_focus_id"], "TARGET-X")

    def test_prose_around_json_is_tolerated(self):
        text = "Here is my dossier:\n" + json.dumps(GOOD_RESPONSE) + "\nDone."
        dossier = parse_dossier_response(text, "agent-a", "family-x", "F-1")
        self.assertEqual(len(dossier["claims"]), 1)

    def test_garbage_becomes_failure_dossier(self):
        dossier = parse_dossier_response("I could not decide, sorry.",
                                         "agent-a", "family-x", "F-1")
        self.assertTrue(dossier["parse_error"])
        self.assertEqual(dossier["claims"], [])
        self.assertIsNone(dossier.get("proposed_focus_id"))
        self.assertEqual(validate_artifact("dossier", dossier), [])

    def test_broken_json_becomes_failure_dossier(self):
        dossier = parse_dossier_response('{"claims": [oops]',
                                         "agent-a", "family-x", "F-1")
        self.assertTrue(dossier["parse_error"])

    def test_missing_claims_field_is_empty_not_invented(self):
        dossier = parse_dossier_response('{"proposed_focus_id": "T"}',
                                         "agent-a", "family-x", "F-1")
        self.assertEqual(dossier["claims"], [])
        self.assertEqual(dossier["proposed_focus_id"], "T")


if __name__ == "__main__":
    unittest.main()
