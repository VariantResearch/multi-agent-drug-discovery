"""Tests for the target-selection proposal pack: verdicts
follow the declared conventions from stubbed scout and
landscape data, run history overrides scout-only grades,
charts carry the same numbers as the text, and the written
pack contains every promised file."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.proposal import (build_proposal, charts_for,
                           render_markdown, write_pack)


def fake_scout(disease, names):
    """A scout stand-in with one open, one occupied, and one
    unassociated target."""
    entries = {
        "OPENGENE": (0.42, 0, 12),
        "BUSYGENE": (0.87, 14, 5210),
        "GHOSTGENE": (None, None, None),
    }
    candidates = []
    for name in names:
        score, mechanisms, bioactivities = entries[name]
        candidates.append({
            "target_input": name,
            "resolved": {"ensembl_id": "ENSG-" + name,
                         "name": name, "chembl_id": "CHEMBL-" + name},
            "association": ({"score": score} if score else None),
            "signals": {"association_score": score,
                        "literature_score": 0.5,
                        "genetic_association_score": 0.25,
                        "known_mechanisms": mechanisms,
                        "bioactivity_records": bioactivities},
            "whitespace": "stub whitespace",
            "problems": []})
    return {"disease_resolved": {"id": "MONDO-1", "name": disease},
            "candidates": candidates}


def fake_trials(disease, focus_terms=(), queried_on=None):
    """A landscape stand-in with per-term mention counts."""
    return {"total_trials": 15097, "sample": None, "note": "stub",
            "focus": [{"term": t, "trials": 3}
                      for t in focus_terms]}


def _proposal(tmp_path, names=("OPENGENE", "BUSYGENE", "GHOSTGENE")):
    """Build a proposal over stubbed sources and no runs."""
    return build_proposal("obesity", "reduce fat mass", list(names),
                          runs_dir=str(tmp_path / "no-runs"),
                          scout_fn=fake_scout, trials_fn=fake_trials,
                          queried_on="2026-10-27")


def test_verdict_conventions(tmp_path):
    """Open and associated grades FIT FOR DEBATE, occupied
    grades PARTIAL, unassociated grades UNESTABLISHED."""
    proposal = _proposal(tmp_path)
    verdicts = {t["target"]: t["verdict"]
                for t in proposal["targets"]}
    assert verdicts == {"OPENGENE": "FIT FOR DEBATE",
                        "BUSYGENE": "PARTIAL FIT",
                        "GHOSTGENE": "UNESTABLISHED"}
    assert proposal["trial_landscape"]["total_trials"] == 15097
    assert all(t["trial_mentions"] == 3
               for t in proposal["targets"])


def test_run_history_decides_the_verdict(tmp_path):
    """A target with a designed run on record grades FIT
    whatever the scout alone would say, and its brief's
    evidence constraints ride into the breakdown."""
    runs = tmp_path / "runs" / "run-1"
    runs.mkdir(parents=True)
    (runs / "bundle.json").write_text(json.dumps({
        "kind": "target_run", "run_id": "run-1",
        "outcome": "designed",
        "target": {"name": "BUSYGENE"},
        "frame_run": {"record": {
            "outcome": "locked",
            "strike_list": [{"claim_id": "c1",
                             "reasons": ["quote_not_in_full_text"]}]}},
        "design": {"gate_report": {"result": "pass"},
                   "ranking": {"ranked": ["cand-1"]},
                   "brief": {"question": "Design against BUSYGENE.",
                             "evidence_constraints": [
                                 {"text": "Constraint one."}]}},
    }))
    proposal = build_proposal(
        "obesity", "reduce fat mass", ["BUSYGENE"],
        runs_dir=str(tmp_path / "runs"), scout_fn=fake_scout,
        trials_fn=fake_trials, queried_on="2026-10-27")
    target = proposal["targets"][0]
    assert target["verdict"] == "FIT"
    assert target["runs"][0]["strikes"] == 1
    markdown = render_markdown(proposal)
    assert "Constraint one." in markdown
    assert "FIT" in markdown


def test_charts_and_pack_files(tmp_path):
    """Charts embed the same values as the record, and the
    pack writes json, md, html, and the three SVGs."""
    proposal = _proposal(tmp_path)
    charts = charts_for(proposal)
    assert "0.42" in charts["chart-association.svg"]
    assert "5210" in charts["chart-bioactivity.svg"]
    written = write_pack(proposal, tmp_path / "pack")
    names = sorted(p.name for p in written)
    assert names == ["chart-association.svg",
                     "chart-bioactivity.svg",
                     "chart-trial-mentions.svg",
                     "proposal.html", "proposal.json",
                     "proposal.md"]
    html = (tmp_path / "pack" / "proposal.html").read_text()
    assert "FIT FOR DEBATE" in html
    assert "No target is locked in" in html
