"""Protocol mode tests: simple, dual, and dual_judge.

Modes count distinct models, not agents: every mode fields a panel
of at least two agents, and the modes differ in how many distinct
models the panel spans and whether a judge model sits over it.

All providers, dossiers, and claims here are invented test fixtures.
They test mode validation and protocol plumbing only; they are not
research and prove nothing about any real target.
"""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.config import build_providers, validate_config
from madd.consensus import run_consensus_tests
from madd.runner import run_frame, run_gate0

FRAME = {"artifact_type": "frame", "schema_version": "0.1.0",
         "frame_id": "TEST-FRAME-MODES", "question": "invented test question",
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


class StubProvider:
    """Stub provider with a settable model identity."""

    def __init__(self, name, model_version, dossier_dict):
        """Initialize the test double."""
        self.name = name
        self.model_version = model_version
        self.cost_per_call_usd = 0.0
        self._dossier = dossier_dict
        self.calls = 0

    def research(self, frame):
        """Return the double's fixed research result."""
        self.calls += 1
        return copy.deepcopy(self._dossier)


def agent(name, model, focus="FOCUS-A", cid=None):
    """One stub agent on the given model proposing the given focus."""
    cid = cid or ("C-" + name)
    return StubProvider(name, model,
                        dossier("D-" + name, "agent-" + name, focus,
                                [good_claim(cid)]))


def stability_result(bundle):
    """The stability entry of a frame bundle's consensus results."""
    results = bundle["record"]["consensus"]["results"]
    return [r for r in results if r["test"] == "stability"][0]


class TestModeValidation(unittest.TestCase):
    """Mode shape errors raise before any provider is called."""

    def test_unknown_mode_rejected(self):
        """Unknown mode rejected."""
        with self.assertRaises(ValueError):
            run_frame(FRAME, [agent("a", "m1"), agent("b", "m1")], mode="trio")

    def test_simple_rejects_mixed_models(self):
        """Simple rejects a panel spanning two models."""
        with self.assertRaises(ValueError):
            run_frame(FRAME, [agent("a", "m1"), agent("b", "m2")], mode="simple")

    def test_simple_rejects_a_judge(self):
        """Simple rejects a judge provider."""
        with self.assertRaises(ValueError):
            run_frame(FRAME, [agent("a", "m1"), agent("b", "m1")],
                      judge_provider=agent("j", "m1"), mode="simple")

    def test_dual_rejects_one_model(self):
        """Dual rejects a panel on a single model."""
        with self.assertRaises(ValueError):
            run_frame(FRAME, [agent("a", "m1"), agent("b", "m1")], mode="dual")

    def test_dual_rejects_a_judge(self):
        """Dual rejects a judge provider."""
        with self.assertRaises(ValueError):
            run_frame(FRAME, [agent("a", "m1"), agent("b", "m2")],
                      judge_provider=agent("j", "m3"), mode="dual")

    def test_dual_judge_requires_the_judge(self):
        """Dual_judge requires the judge provider."""
        with self.assertRaises(ValueError):
            run_frame(FRAME, [agent("a", "m1"), agent("b", "m2")],
                      mode="dual_judge")

    def test_dual_judge_rejects_three_models_on_the_panel(self):
        """Dual_judge rejects a panel spanning three models."""
        with self.assertRaises(ValueError):
            run_frame(FRAME, [agent("a", "m1"), agent("b", "m2"),
                              agent("c", "m3")],
                      judge_provider=agent("j", "m3"), mode="dual_judge")


class TestModeRuns(unittest.TestCase):
    """Each mode runs its protocol end to end on a frame."""

    def test_simple_locks_with_same_model_agents(self):
        """Simple: several agents, one model, agreement locks."""
        bundle = run_frame(FRAME, [agent("a", "m1"), agent("b", "m1"),
                                   agent("c", "m1")], mode="simple")
        self.assertEqual(bundle["mode"], "simple")
        self.assertEqual(bundle["outcome"], "locked")
        stability = stability_result(bundle)
        self.assertEqual(stability["status"], "not_applied")
        self.assertTrue(stability["passed"])

    def test_dual_locks_across_two_models(self):
        """Dual: agents across two models lock without a judge."""
        bundle = run_frame(FRAME, [agent("a", "m1"), agent("b", "m1"),
                                   agent("c", "m2")], mode="dual")
        self.assertEqual(bundle["mode"], "dual")
        self.assertEqual(bundle["outcome"], "locked")
        self.assertEqual(stability_result(bundle)["status"], "not_applied")

    def test_dual_disagreement_is_no_go(self):
        """Dual: a split panel does not lock."""
        bundle = run_frame(FRAME, [agent("a", "m1", focus="FOCUS-A"),
                                   agent("b", "m2", focus="FOCUS-B")],
                           mode="dual")
        self.assertEqual(bundle["outcome"], "no_go")

    def test_dual_judge_applies_stability(self):
        """Dual_judge: the judge swap is run and passes on agreement."""
        bundle = run_frame(FRAME, [agent("a", "m1"), agent("b", "m2")],
                           judge_provider=agent("j", "m3"), mode="dual_judge")
        self.assertEqual(bundle["mode"], "dual_judge")
        self.assertEqual(bundle["outcome"], "locked")
        self.assertEqual(stability_result(bundle)["status"], "passed")

    def test_dual_judge_swap_flip_is_no_go(self):
        """Dual_judge: a judge naming another focus fails stability."""
        bundle = run_frame(FRAME, [agent("a", "m1"), agent("b", "m2")],
                           judge_provider=agent("j", "m3", focus="FOCUS-B"),
                           mode="dual_judge")
        self.assertEqual(bundle["outcome"], "no_go")
        self.assertEqual(stability_result(bundle)["status"], "failed")


class TestConsensusNotApplied(unittest.TestCase):
    """The consensus layer reports a skipped stability test honestly."""

    def _inputs(self):
        """Two agreeing dossiers and a spec that passes the rest."""
        dossiers = [dossier("D-A", "agent-a", "FOCUS-A", [good_claim("C-A1")]),
                    dossier("D-B", "agent-b", "FOCUS-A", [good_claim("C-B1")])]
        spec = {"focus_id": "FOCUS-A", "claims": [good_claim("C-A1")],
                "dissent_log": [], "dissent_none_reason": "invented reason"}
        return dossiers, spec

    def test_stability_not_applied_when_not_required(self):
        """stability_required=False reports not_applied, not a pass."""
        dossiers, spec = self._inputs()
        out = run_consensus_tests(dossiers, spec, stability_required=False)
        stability = [r for r in out["results"] if r["test"] == "stability"][0]
        self.assertEqual(stability["status"], "not_applied")
        self.assertTrue(out["all_passed"])

    def test_stability_failed_by_default_without_a_swap(self):
        """The default keeps the original rule: no swap, stability fails."""
        dossiers, spec = self._inputs()
        out = run_consensus_tests(dossiers, spec)
        stability = [r for r in out["results"] if r["test"] == "stability"][0]
        self.assertEqual(stability["status"], "failed")
        self.assertFalse(stability["passed"])


def http_entry(name, model):
    """One openai-compatible config entry on the given model id."""
    return {"name": name, "kind": "openai-compatible", "model": model,
            "api_key_env": "TEST_KEY_ENV"}


def mock_entry(name):
    """One mock config entry (every mock is the same model)."""
    return {"name": name, "kind": "mock", "label": name}


class TestConfigModes(unittest.TestCase):
    """Config-level mode validation mirrors the runner's rules."""

    def test_simple_accepts_a_same_model_panel(self):
        """Two agents on one model is a valid simple config."""
        config = {"mode": "simple",
                  "providers": [http_entry("a", "m1"), http_entry("b", "m1")],
                  "judge": None, "baseline": mock_entry("base")}
        self.assertEqual(validate_config(config), [])

    def test_simple_config_rejects_two_models(self):
        """Simple config rejects a two-model panel."""
        config = {"mode": "simple",
                  "providers": [http_entry("a", "m1"), http_entry("b", "m2")],
                  "judge": None, "baseline": None}
        errors = validate_config(config)
        self.assertTrue(any("simple" in e for e in errors), errors)

    def test_dual_config_rejects_mocks_only(self):
        """Dual config rejects a panel of mocks (one distinct model)."""
        config = {"mode": "dual",
                  "providers": [mock_entry("a"), mock_entry("b")],
                  "judge": None, "baseline": None}
        errors = validate_config(config)
        self.assertTrue(any("dual" in e for e in errors), errors)

    def test_dual_judge_config_requires_and_accepts_a_judge(self):
        """Dual_judge config needs the judge entry and accepts it."""
        base = {"mode": "dual_judge",
                "providers": [http_entry("a", "m1"), http_entry("b", "m2")],
                "baseline": None}
        errors = validate_config(dict(base, judge=None))
        self.assertTrue(any("judge" in e for e in errors), errors)
        self.assertEqual(validate_config(dict(base, judge=mock_entry("j"))), [])

    def test_unknown_mode_is_a_config_error(self):
        """An unknown mode string is a config error."""
        config = {"mode": "trio",
                  "providers": [mock_entry("a"), mock_entry("b")],
                  "judge": None, "baseline": None}
        self.assertTrue(any("mode" in e for e in validate_config(config)))

    def test_build_providers_returns_the_mode(self):
        """build_providers surfaces the declared mode."""
        config = {"mode": "simple",
                  "providers": [mock_entry("a"), mock_entry("b")],
                  "judge": None, "baseline": mock_entry("base")}
        self.assertEqual(build_providers(config)["mode"], "simple")


class TestGate0ModeRuns(unittest.TestCase):
    """Full Gate 0 runs under declared modes, on the real packs."""

    def test_simple_mode_gate0_run(self):
        """A simple-mode run scores all eight cases and records the mode."""
        providers = [agent("a", "m1", cid="C-A"), agent("b", "m1", cid="C-B")]
        baseline = agent("base", "m9", cid="C-BASE")
        bundle = run_gate0(providers, baseline_provider=baseline, mode="simple")
        self.assertEqual(bundle["mode"], "simple")
        self.assertEqual(len(bundle["predictions"]), 8)
        record = bundle["case_records"]["ivacaftor-cftr-cf"]
        stability = [r for r in record["consensus"]["results"]
                     if r["test"] == "stability"][0]
        self.assertEqual(stability["status"], "not_applied")

    def test_dual_judge_mode_gate0_run(self):
        """A dual_judge run applies stability on every case."""
        providers = [agent("a", "m1", cid="C-A"), agent("b", "m2", cid="C-B")]
        judge = agent("j", "m3", cid="C-J")
        baseline = agent("base", "m9", cid="C-BASE")
        bundle = run_gate0(providers, judge_provider=judge,
                           baseline_provider=baseline, mode="dual_judge")
        self.assertEqual(bundle["mode"], "dual_judge")
        record = bundle["case_records"]["ivacaftor-cftr-cf"]
        stability = [r for r in record["consensus"]["results"]
                     if r["test"] == "stability"][0]
        self.assertEqual(stability["status"], "passed")


if __name__ == "__main__":
    unittest.main()
