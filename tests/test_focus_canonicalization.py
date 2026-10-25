"""Focus canonicalization tests.

All frames, dossiers, and claims here are invented test fixtures. They
test the rule that when a frame declares a canonical focus_id, a
dossier's proposed focus is read against that identifier and the
frame's target string before any comparison: surface spellings of the
frame's own target (its full descriptive string, a shortening of it,
an abbreviation equal to the focus_id) count as the same focus, and
anything else is left exactly as written.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.debate import canonical_focus_id, run_debate
from madd.runner import frame_for_case

FRAME = {"artifact_type": "frame", "schema_version": "0.1.0",
         "frame_id": "TEST-FRAME-FOCUS", "question": "invented question",
         "round_cap": 2, "focus_id": "GENE9",
         "target": "GENE9 protein (invented descriptive expansion)"}


def good_claim(cid, tier=2):
    """Build a claim that passes the audit."""
    return {"claim_id": cid, "text": "invented claim " + cid,
            "load_bearing": True, "evidence_tier": tier,
            "source_kind": "journal_article", "source_identifier": "12345678",
            "identifier_type": "pmid", "verification_status": "quote_checked",
            "supporting_quote": "invented supporting quote"}


def dossier(dossier_id, agent_id, focus):
    """Build a dossier for the tests."""
    return {"artifact_type": "dossier", "schema_version": "0.1.0",
            "dossier_id": dossier_id, "frame_id": FRAME["frame_id"],
            "agent_id": agent_id, "model_family": "stub",
            "proposed_focus_id": focus, "direction": "advance",
            "claims": [good_claim(dossier_id + "-c1")],
            "unverified_notes": []}


class StubProvider:
    """Stub provider returning a fixed dossier."""

    def __init__(self, name, dossier_dict):
        """Initialize the test double."""
        self.name = name
        self.model_version = name + "-v1"
        self.cost_per_call_usd = 0.0
        self._dossier = dossier_dict

    def research(self, frame):
        """Return the fixed dossier, as the Provider interface requires."""
        import copy
        return copy.deepcopy(self._dossier)


class CanonicalFocusIdTests(unittest.TestCase):
    """The mapping itself: narrow, and only for frames with a focus_id."""

    def test_exact_focus_id_passes_through(self):
        """The canonical identifier itself is returned unchanged."""
        self.assertEqual(canonical_focus_id("GENE9", FRAME), "GENE9")

    def test_case_and_spacing_variant_maps(self):
        """Case and spacing differences on the identifier still map."""
        self.assertEqual(canonical_focus_id(" gene9 ", FRAME), "GENE9")

    def test_full_target_string_maps(self):
        """The frame's full descriptive target string maps to the id."""
        self.assertEqual(canonical_focus_id(
            "GENE9 protein (invented descriptive expansion)", FRAME), "GENE9")

    def test_shortening_of_target_maps(self):
        """A shortening whose tokens sit inside the target's maps."""
        self.assertEqual(canonical_focus_id("GENE9 protein", FRAME), "GENE9")

    def test_unrelated_focus_is_untouched(self):
        """A genuinely different target is not the frame's focus."""
        self.assertEqual(canonical_focus_id("OTHER7 kinase", FRAME),
                         "OTHER7 kinase")

    def test_frame_without_focus_id_changes_nothing(self):
        """Frames that declare no focus_id keep the old behaviour."""
        bare = {"frame_id": "X", "target": "GENE9 protein"}
        self.assertEqual(canonical_focus_id("GENE9 protein", bare),
                         "GENE9 protein")

    def test_null_and_nonstring_pass_through(self):
        """No focus stays no focus; odd values are not repaired."""
        self.assertIsNone(canonical_focus_id(None, FRAME))
        self.assertEqual(canonical_focus_id("", FRAME), "")


class DebateCanonicalizationTests(unittest.TestCase):
    """End to end: spelling variants of one target agree and lock."""

    def test_variant_spellings_agree_and_lock(self):
        """Three spellings of the frame target agree; the record keeps
        what each model actually wrote under proposed_focus_raw."""
        providers = [
            StubProvider("p1", dossier("d1", "a1", "GENE9")),
            StubProvider("p2", dossier("d2", "a2",
                                       "GENE9 protein (invented "
                                       "descriptive expansion)")),
            StubProvider("p3", dossier("d3", "a3", "GENE9 protein")),
        ]
        judge = StubProvider("judge", dossier("dj", "aj", "gene9"))
        record = run_debate(FRAME, providers, judge_provider=judge)
        self.assertEqual(record["outcome"], "locked")
        self.assertEqual(record["spec"]["focus_id"], "GENE9")
        raws = {r["dossier_id"]: r.get("proposed_focus_raw")
                for r in record["ranking"]}
        self.assertIsNone(raws["d1"])
        self.assertEqual(raws["d2"],
                         "GENE9 protein (invented descriptive expansion)")
        self.assertEqual(raws["d3"], "GENE9 protein")
        self.assertEqual(record["judge_swap"]["proposed_focus_id"], "GENE9")
        self.assertEqual(record["judge_swap"]["proposed_focus_raw"], "gene9")

    def test_different_focus_still_disagrees(self):
        """A dossier naming a different target is not canonicalized
        into agreement; the debate stays no_go."""
        providers = [
            StubProvider("p1", dossier("d1", "a1", "GENE9")),
            StubProvider("p2", dossier("d2", "a2", "GENE9 protein")),
            StubProvider("p3", dossier("d3", "a3", "OTHER7 kinase")),
        ]
        record = run_debate(FRAME, providers)
        self.assertEqual(record["outcome"], "no_go")
        agreement = [r for r in record["consensus"]["results"]
                     if r["test"] == "agreement"][0]
        self.assertFalse(agreement["passed"])
        self.assertIn("OTHER7 kinase", agreement["detail"])


class FrameFocusIdTests(unittest.TestCase):
    """The Gate 0 frame carries the pack's focus_id at the top level."""

    def test_frame_for_case_carries_focus_id(self):
        """A pack focus_id appears on the frame providers receive."""
        pack = {"case_id": "invented-case", "disease": "invented disease",
                "target": "GENE9 protein", "focus_id": "GENE9",
                "drug_name": "InventedDrug", "evidence_as_of": "2020-01-01",
                "claims": [], "forbidden_terms": ["invented outcome term"]}
        frame = frame_for_case("invented-case", pack)
        self.assertEqual(frame["focus_id"], "GENE9")
        self.assertNotIn("forbidden_terms", frame["case_pack"])


if __name__ == "__main__":
    unittest.main()
