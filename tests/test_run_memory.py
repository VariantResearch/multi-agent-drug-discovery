"""Tests for the fenced run memory: operational aggregation
over fixture bundles, and the fence itself - a bundle's claim
text, quotes, and structures must appear nowhere in the
memory the scan produces."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.run_memory import build_memory, target_history

SECRET_CLAIM = "ZZZ-UNIQUE-CLAIM-TEXT-9173"
SECRET_SMILES = "ZZZSECRETSTRUCTURE"


def write_run(root, run_id, bundle):
    """Write one bundle.json in the storage layout."""
    folder = Path(root) / run_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "bundle.json").write_text(json.dumps(bundle))


def target_bundle(run_id, outcome, strikes):
    """A target-run bundle carrying content the fence must
    keep out, beside the metadata it must carry."""
    return {
        "kind": "target_run", "run_id": run_id, "outcome": outcome,
        "target": {"name": "MTCH2"},
        "frame_run": {
            "record": {"outcome": "locked" if outcome == "designed"
                       else "no_go",
                       "strike_list": [{"claim_id": "c" + str(i)}
                                       for i in range(strikes)],
                       "dossiers": [{"claims": [
                           {"text": SECRET_CLAIM,
                            "supporting_quote": SECRET_CLAIM}]}]},
            "providers": [{"name": "panel-a"}]},
        "design": {"gate_report": {"result": "pass"},
                   "candidates": [{"structure": {
                       "value": SECRET_SMILES}}]},
    }


def test_memory_aggregates_outcomes(tmp_path):
    """Two runs for one target aggregate: counts, outcomes,
    strikes, provider participation, last outcome."""
    write_run(tmp_path, "r1", target_bundle("r1", "no_go", 5))
    write_run(tmp_path, "r2", target_bundle("r2", "designed", 2))
    memory = build_memory(tmp_path)
    assert memory["runs_scanned"] == 2
    history = target_history(memory, "MTCH2")
    assert history["runs"] == 2
    assert history["outcomes"] == {"no_go": 1, "designed": 1}
    assert history["total_strikes"] == 7
    assert history["last_outcome"] == "designed"
    assert memory["providers"]["panel-a"]["runs"] == 2
    assert target_history(memory, "NEVERSEEN") is None


def test_the_fence_holds(tmp_path):
    """Nothing but metadata crosses: the fixture's claim text
    and candidate structure are absent from the serialized
    memory, and the fence statement rides along."""
    write_run(tmp_path, "r1", target_bundle("r1", "designed", 1))
    memory = build_memory(tmp_path)
    blob = json.dumps(memory)
    assert SECRET_CLAIM not in blob
    assert SECRET_SMILES not in blob
    assert "never evidence" in memory["fence"]


def test_gate0_bundles_scan(tmp_path):
    """Gate 0 bundles contribute their kind-level metadata."""
    write_run(tmp_path, "g1", {
        "kind": "gate0_run", "run_id": "g1",
        "case_ids": ["c1", "c2"],
        "providers": [{"name": "panel-a"}, {"name": "panel-b"}],
        "thresholds": {"overall": "fail"}})
    memory = build_memory(tmp_path)
    assert memory["runs_scanned"] == 1
    assert memory["providers"]["panel-b"]["runs"] == 1
