"""Tests for the lead optimization loop, on real RDKit
computation: the objective vectors and verdicts below were
verified against describe_smiles on the installed RDKit
(aspirin lead; methyl salicylate improves on all three
objectives; the ethyl ester trades SA the wrong way;
dodecanoic acid drifts logP out of the neighborhood)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.optimize import improves, objective_vector, run_optimization
from madd.design_rdkit import describe_smiles

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
METHYL_SALICYLATE = "COc1ccccc1C(=O)O"
ETHYL_ESTER = "CCOC(=O)c1ccccc1OC(C)=O"
DODECANOIC_ACID = "CCCCCCCCCCCC(=O)O"


def candidate(cid, smiles):
    """One normalized candidate dict in the design shape."""
    return {"candidate_id": cid,
            "structure": {"format": "smiles", "value": smiles}}


class StubDesigner:
    """A designer returning a fixed analog list per round."""

    name = "stub-designer"

    def __init__(self, rounds):
        """Store the per-round candidate lists."""
        self.rounds = rounds
        self.briefs = []

    def design(self, brief):
        """Return this round's analogs, recording the brief."""
        self.briefs.append(brief)
        index = min(len(self.briefs) - 1, len(self.rounds) - 1)
        return list(self.rounds[index])


def test_objectives_and_pareto():
    """Objective vectors come from computed descriptors, and
    the Pareto test requires no-worse everywhere and better
    somewhere."""
    lead = objective_vector(describe_smiles(ASPIRIN))
    better = objective_vector(describe_smiles(METHYL_SALICYLATE))
    tradeoff = objective_vector(describe_smiles(ETHYL_ESTER))
    ok, deltas = improves(better, lead)
    assert ok and deltas["qed"] > 0 and deltas["sa_score"] < 0
    ok, _deltas = improves(tradeoff, lead)
    assert not ok  # SA score worsened: a trade, not an improvement
    ok, _deltas = improves(lead, lead)
    assert not ok  # identical is not an improvement


def test_loop_keeps_improvers_and_records_drops():
    """One round: the improver is kept and becomes best; the
    duplicate, the invalid structure, the logP drifter, and the
    trade-off are each dropped with their reason recorded."""
    lead = {"candidate_id": "lead-1",
            "structure": {"format": "smiles", "value": ASPIRIN}}
    designer = StubDesigner([[
        candidate("a-dup", ASPIRIN),
        candidate("a-bad", "not a smiles"),
        candidate("a-drift", DODECANOIC_ACID),
        candidate("a-trade", ETHYL_ESTER),
        candidate("a-good", METHYL_SALICYLATE),
    ]])
    record = run_optimization(lead, designer, rounds=1)
    assert record["status"] == "completed"
    assert record["proposed_total"] == 5
    assert record["kept_total"] == 1
    assert record["best"]["candidate_id"] == "a-good"
    verdicts = {e["candidate_id"]: (e["verdict"], e["reasons"])
                for e in record["rounds"][0]["proposed"]}
    assert verdicts["a-dup"][1] == ["duplicate_or_parent"]
    assert verdicts["a-bad"][1] == ["invalid_structure"]
    assert verdicts["a-drift"][1] == ["logp_drift"]
    assert verdicts["a-trade"][1] == ["no_pareto_improvement"]
    assert verdicts["a-good"][0] == "kept"
    assert "not a potency" in record["note"]


def test_loop_chains_parent_and_stops_without_improvement():
    """Round 2 optimizes the round-1 winner (the brief names it
    as parent), and a round with no improver stops the loop
    with the stop recorded."""
    lead = {"candidate_id": "lead-1",
            "structure": {"format": "smiles", "value": ASPIRIN}}
    designer = StubDesigner([
        [candidate("a-good", METHYL_SALICYLATE)],
        [candidate("a-trade", ETHYL_ESTER)],
    ])
    record = run_optimization(lead, designer, rounds=3)
    assert len(record["rounds"]) == 2  # stopped after round 2
    assert designer.briefs[1]["parent"]["candidate_id"] == "a-good"
    assert "stopped" in record["rounds"][1]
    assert record["best"]["candidate_id"] == "a-good"


def test_loop_honest_statuses():
    """Sequence leads are not applicable, and a designer
    proposing nothing yields no_analogs, not a success."""
    sequence = {"candidate_id": "seq-1",
                "structure": {"format": "sequence",
                              "value": "ACDEFGHIK"}}
    record = run_optimization(sequence, StubDesigner([[]]), rounds=1)
    assert record["status"] == "not_applicable"
    lead = {"candidate_id": "lead-1",
            "structure": {"format": "smiles", "value": ASPIRIN}}
    record = run_optimization(lead, StubDesigner([[]]), rounds=2)
    assert record["status"] == "no_analogs"
    assert record["kept_total"] == 0
