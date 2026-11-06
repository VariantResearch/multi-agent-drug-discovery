"""Experiment tree tests: best-first expansion, seeding, bounded
debug retries, step budget, determinism, and the tree gate."""
import json

import pytest

from madd import design, experiment_tree, schemas
from madd.artifacts import verify_frozen
from madd.cli import main


def locked_spec():
    """Build a locked consensus spec record (mirrors test_design)."""
    return {
        "artifact_type": "consensus_spec", "schema_version": "0.1.0",
        "spec_id": "SPEC-T-1", "frame_id": "F-T",
        "focus_id": "Target T",
        "direction": "advance",
        "outcome": "locked",
        "claims": [
            {"claim_id": "CLM-1", "text": "Human genetics supports target T.",
             "source_kind": "primary_study", "source_identifier": "12345678",
             "identifier_type": "pmid", "verification_status": "quote_checked",
             "supporting_quote": "variants in the target gene associate with disease",
             "evidence_tier": 1, "load_bearing": True},
            {"claim_id": "CLM-2", "text": "A side observation.",
             "source_kind": "primary_study", "source_identifier": "23456789",
             "identifier_type": "pmid", "verification_status": "quote_checked",
             "supporting_quote": "an observation", "evidence_tier": 4,
             "load_bearing": False},
        ],
        "consensus_tests": [], "dissent_log": [],
    }


def good_candidate(cid, claim_ids=("CLM-1",), unknown=0):
    """A candidate whose claims all pass audit, with `unknown`
    unknown constraint results."""
    claims = []
    for i, claim_id in enumerate(claim_ids):
        claim = dict(locked_spec()["claims"][0])
        claim["claim_id"] = claim_id if i == 0 else claim_id + "-" + str(i)
        claims.append(claim)
    return {
        "artifact_type": "candidate", "schema_version": "0.1.0",
        "candidate_id": cid, "spec_id": "SPEC-T-1",
        "modality": "small_molecule", "design_tool": "test",
        "description": "test candidate " + cid,
        "claims": claims, "predicted_properties": [],
        "constraint_results": (
            [{"constraint": "open-" + str(j), "kind": "design",
              "status": "unknown", "basis": "test"}
             for j in range(unknown)]),
    }


def bad_candidate(cid):
    """A candidate whose load-bearing claim fails audit."""
    return {
        "artifact_type": "candidate", "schema_version": "0.1.0",
        "candidate_id": cid, "spec_id": "SPEC-T-1",
        "modality": "small_molecule", "design_tool": "test",
        "claims": [{"claim_id": "CLM-BAD-" + cid,
                    "text": "It binds, trust me.",
                    "source_kind": "primary_study", "source_identifier": "",
                    "identifier_type": "pmid",
                    "supporting_quote": "", "evidence_tier": 3,
                    "load_bearing": True}],
        "predicted_properties": [], "constraint_results": [],
    }


class ScriptedDesigner:
    """Designer double: returns the next scripted batch per call and
    records every brief it was shown."""

    name = "scripted"

    def __init__(self, batches):
        """batches: list of candidate lists, one per design() call."""
        self.batches = [list(b) for b in batches]
        self.briefs = []
        self.notes = []

    def design(self, brief):
        """Return the next scripted batch (empty once exhausted)."""
        self.briefs.append(brief)
        if self.batches:
            return self.batches.pop(0)
        return []


def run_tree(designer, config=None, **kwargs):
    """Run a tree over the locked spec with enrichment off, so the
    tests exercise the manager, not RDKit availability."""
    kwargs.setdefault("rdkit", False)
    kwargs.setdefault("admet", False)
    return experiment_tree.run_experiment_tree(
        locked_spec(), "test", designer=designer, config=config, **kwargs)


def test_tree_expands_root_and_seeds_ranked_candidates():
    """Root expansion ranks, seeds become children, ids are scoped."""
    designer = ScriptedDesigner([
        [good_candidate("A"), good_candidate("B", unknown=1)],
        [good_candidate("C")],
        [good_candidate("D")],
    ])
    bundle = run_tree(designer, {"max_steps": 3, "num_seeds": 2, "seed": 0})
    assert bundle["kind"] == "experiment_tree"
    assert bundle["expansions"] == 3
    assert bundle["stop_reason"] == "steps_exhausted"
    nodes = {n["node_id"]: n for n in bundle["nodes"]}
    root = nodes["node-0001"]
    assert root["kind"] == "root" and root["status"] == "expanded"
    # Candidate ids are scoped to their node; the designer's own id
    # is kept as the origin.
    scoped = {c["candidate_id"] for c in root["candidates"]}
    assert scoped == {"node-0001-A", "node-0001-B"}
    assert {c["tree_origin_id"] for c in root["candidates"]} == {"A", "B"}
    # Two seed children were created from the root's ranked pair,
    # best first: A (no unknowns) ahead of B (one unknown).
    seeds = [n for n in bundle["nodes"] if n["kind"] == "seed"]
    assert [s["seed_candidate_id"] for s in seeds[:2]] == [
        "node-0001-A", "node-0001-B"]
    assert seeds[0]["priority"] == [1, 0]
    assert seeds[1]["priority"] == [1, -1]
    # The seed brief carries the tree_context as data.
    ctx = designer.briefs[1]["tree_context"]
    assert ctx["kind"] == "seed"
    assert ctx["seed_candidate_id"] == "node-0001-A"
    # The best candidate overall is the root's A: same score as the
    # later batches, earliest expansion wins the tie.
    assert bundle["best"]["candidate_id"] == "node-0001-A"
    assert bundle["gate_report"]["result"] == "pass"
    assert schemas.validate_artifact(
        "gate_report", bundle["gate_report"]) == []
    assert verify_frozen(bundle["frozen_bundle"])


def test_best_first_expands_highest_priority_seed_first():
    """The manager expands the strongest open node, not the newest.

    After the root, the HIGH seed (priority [1, 0]) expands before
    the LOW seed ([1, -2]). The HIGH seed's own child then ties the
    LOW seed on audited claims and wins on fewer unknowns, which is
    the ranking rule's own order applied by the manager.
    """
    designer = ScriptedDesigner([
        [good_candidate("LOW", unknown=2), good_candidate("HIGH")],
        [good_candidate("FROM-HIGH")],
        [good_candidate("FROM-HIGH-2")],
    ])
    bundle = run_tree(designer, {"max_steps": 3, "num_seeds": 2})
    expanded = [n for n in bundle["nodes"]
                if n["expansion_order"] is not None]
    expanded.sort(key=lambda n: n["expansion_order"])
    assert expanded[1]["seed_candidate_id"] == "node-0001-HIGH"
    assert expanded[2]["seed_candidate_id"] == "node-0002-FROM-HIGH"
    low = [n for n in bundle["nodes"]
           if n["seed_candidate_id"] == "node-0001-LOW"]
    assert low and low[0]["status"] == "pending"


def test_goal_stops_the_search_early():
    """A ranked candidate reaching the goal ends expansion."""
    designer = ScriptedDesigner([
        [good_candidate("A", claim_ids=("CLM-1", "CLM-2"))],
        [good_candidate("NEVER-USED")],
    ])
    bundle = run_tree(designer, {"max_steps": 6,
                                 "goal_audited_claims": 2})
    # Both spec claims cited under distinct ids audit clean, so the
    # root's candidate carries two audited load-bearing claims.
    assert bundle["best"]["score"][0] == 2
    assert bundle["stop_reason"] == "goal_reached"
    assert bundle["expansions"] == 1


def test_failed_node_gets_bounded_debug_children():
    """Failures retry as debug children, bounded by max_debug_depth."""
    designer = ScriptedDesigner([
        [bad_candidate("X")], [bad_candidate("Y")], [bad_candidate("Z")],
        [bad_candidate("W")],
    ])
    bundle = run_tree(designer, {"max_steps": 6, "max_debug_depth": 2,
                                 "debug_prob": 1.0, "seed": 0})
    kinds = [(n["node_id"], n["kind"], n["debug_depth"], n["status"])
             for n in bundle["nodes"]]
    assert kinds == [
        ("node-0001", "root", 0, "failed"),
        ("node-0002", "debug", 1, "failed"),
        ("node-0003", "debug", 2, "failed"),
    ]
    # The third failure is at the bound: no fourth node, and the
    # search ends because the frontier is empty, within budget.
    assert bundle["expansions"] == 3
    assert bundle["stop_reason"] == "frontier_exhausted"
    checks = {c["name"]: c["status"]
              for c in bundle["gate_report"]["checks"]}
    assert checks["debug_depth_within_bound"] == "pass"
    assert checks["candidates_ranked"] == "fail"
    assert bundle["gate_report"]["result"] == "fail"
    # The debug brief carries the recorded exclusion reasons.
    ctx = designer.briefs[1]["tree_context"]
    assert ctx["kind"] == "debug" and ctx["debug_depth"] == 1
    assert any("CLM-BAD" in r for r in ctx["exclusion_reasons"])


def test_debug_probability_zero_means_no_retries():
    """debug_prob 0 records the failure and opens no debug child."""
    designer = ScriptedDesigner([[bad_candidate("X")],
                                 [good_candidate("NEVER")]])
    bundle = run_tree(designer, {"max_steps": 4, "debug_prob": 0.0})
    assert len(bundle["nodes"]) == 1
    assert bundle["expansions"] == 1
    assert bundle["stop_reason"] == "frontier_exhausted"


def test_debug_recovery_resets_the_lineage_depth():
    """A debug child that ranks resets its children's debug depth."""
    designer = ScriptedDesigner([
        [bad_candidate("X")],
        [good_candidate("FIXED")],
        [good_candidate("NEXT")],
    ])
    bundle = run_tree(designer, {"max_steps": 3, "max_debug_depth": 2,
                                 "debug_prob": 1.0})
    nodes = {n["node_id"]: n for n in bundle["nodes"]}
    assert nodes["node-0002"]["kind"] == "debug"
    assert nodes["node-0002"]["status"] == "expanded"
    seed = nodes["node-0003"]
    assert seed["kind"] == "seed" and seed["debug_depth"] == 0
    assert bundle["gate_report"]["result"] == "pass"


def test_mock_only_tree_fails_the_real_candidate_gate():
    """The mock designer's synthetic candidates can never pass."""
    bundle = run_tree(None, {"max_steps": 2})
    assert bundle["designer"] == "mock"
    checks = {c["name"]: c["status"]
              for c in bundle["gate_report"]["checks"]}
    assert checks["candidates_ranked"] == "pass"
    assert checks["real_candidates_ranked"] == "fail"
    assert bundle["gate_report"]["result"] == "fail"


def test_same_seed_reproduces_the_same_tree():
    """Determinism: identical config and designer, identical shape."""
    def build():
        """Run one tree with a failure first, so the debug draw is
        part of the reproduced shape."""
        designer = ScriptedDesigner([
            [bad_candidate("X")], [good_candidate("A")],
            [good_candidate("B")],
        ])
        return run_tree(designer, {"max_steps": 3, "debug_prob": 0.5,
                                   "seed": 7})
    one, two = build(), build()
    shape = lambda b: [(n["node_id"], n["kind"], n["parent_id"],
                        n["status"], n["score"]) for n in b["nodes"]]
    assert shape(one) == shape(two)
    assert one["stop_reason"] == two["stop_reason"]
    assert one["best"] == two["best"]


def test_config_validation_refuses_bad_numbers():
    """The manager's numbers are validated before any expansion."""
    with pytest.raises(ValueError):
        experiment_tree.validate_tree_config({"max_steps": 0})
    with pytest.raises(ValueError):
        experiment_tree.validate_tree_config({"debug_prob": 1.5})
    with pytest.raises(ValueError):
        experiment_tree.validate_tree_config({"bogus": 1})
    cfg = experiment_tree.validate_tree_config({"seed": 3})
    assert cfg["max_steps"] == experiment_tree.DEFAULT_CONFIG["max_steps"]
    assert cfg["seed"] == 3


def test_unlocked_spec_is_refused():
    """No tree grows from a spec the debate did not lock."""
    spec = locked_spec()
    spec["outcome"] = "killed"
    with pytest.raises(ValueError):
        experiment_tree.run_experiment_tree(spec, "test", rdkit=False,
                                            admet=False)


def test_duplicate_candidate_ids_in_one_batch_raise():
    """Two identical ids in one expansion would merge in the audit
    maps; the tree refuses, as run_design does."""
    designer = ScriptedDesigner([[good_candidate("A"),
                                  good_candidate("A")]])
    with pytest.raises(ValueError):
        run_tree(designer, {"max_steps": 1})


def test_cli_experiment_tree_flow(tmp_path, capsys):
    """The CLI writes a stored tree bundle and reports the gate."""
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(locked_spec()), encoding="utf-8")
    rc = main(["experiment-tree", str(spec_path), "--steps", "2",
               "--out", str(tmp_path / "runs")])
    out = capsys.readouterr().out
    # Mock-only: the bundle is written, the gate fails, the command
    # exits non-zero, exactly like design-run.
    assert rc == 1
    assert "experiment tree tree-" in out
    assert "gate: fail" in out
    run_dirs = list((tmp_path / "runs").glob("tree-*"))
    assert len(run_dirs) == 1
    bundle = json.loads(
        (run_dirs[0] / "bundle.json").read_text(encoding="utf-8"))
    assert bundle["kind"] == "experiment_tree"
    assert (run_dirs[0] / "report.md").exists()
    assert (run_dirs[0] / "report.html").exists()
