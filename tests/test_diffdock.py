"""Tests for the DiffDock cross-check: centroid math on
hand-built pose files, agreement grading, the not_available
state with no installation configured, failure honesty, and
confidence pickup. A stub runner fabricates DiffDock's output
layout; no real DiffDock is installed here, which is exactly
the state the not_available tests pin down."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.diffdock import (agreement_for, cross_check)


def pdb_pose(points):
    """A minimal PDB text with HETATM lines at the given points."""
    lines = []
    for i, (x, y, z) in enumerate(points):
        lines.append(
            "HETATM%5d  C%-2d LIG A   1    %8.3f%8.3f%8.3f  1.00  0.00"
            % (i + 1, i + 1, x, y, z))
    return "\n".join(lines) + "\n"


def sdf_pose(points):
    """A minimal SDF text with the given atom points."""
    lines = ["fake pose", "  test", "",
             "%3d%3d  0  0  0  0  0  0  0  0999 V2000"
             % (len(points), len(points) - 1)]
    for x, y, z in points:
        lines.append("%10.4f%10.4f%10.4f C   0  0" % (x, y, z))
    for i in range(len(points) - 1):
        lines.append("%3d%3d  1  0" % (i + 1, i + 2))
    lines.append("M  END")
    return "\n".join(lines) + "\n"


def make_runner(pose_points, confidence=0.42, returncode=0):
    """A runner fabricating a DiffDock output layout."""
    def runner(home, protein_path, smiles, out_dir):
        """Write the fabricated pose and confidence output."""
        target = Path(out_dir) / "complex_0"
        target.mkdir(parents=True, exist_ok=True)
        (target / "rank1.sdf").write_text(sdf_pose(pose_points))
        if confidence is not None:
            (target / "results.csv").write_text(
                "rank,confidence\n1," + str(confidence) + "\n")

        class Result:
            """A subprocess-result-shaped object."""
        result = Result()
        result.returncode = returncode
        result.stderr = "boom" if returncode else ""
        result.stdout = ""
        return result
    return runner


def test_agreement_grades():
    """The distance grades are the recorded thresholds."""
    assert agreement_for(1.5) == "agree"
    assert agreement_for(2.0) == "agree"
    assert agreement_for(3.9) == "partial"
    assert agreement_for(4.1) == "disagree"


def test_cross_check_agree_and_disagree(tmp_path, monkeypatch):
    """A fabricated DiffDock pose at the Vina pose's centroid
    agrees; one placed far away disagrees; confidence is picked
    up from the run's CSV."""
    home = tmp_path / "diffdock-home"
    home.mkdir()
    monkeypatch.setenv("MADD_DIFFDOCK_HOME", str(home))
    vina = pdb_pose([(10.0, 10.0, 10.0), (12.0, 10.0, 10.0)])
    near = cross_check("RECEPTOR", "CCO", vina, tmp_path / "w1",
                        runner=make_runner([(11.0, 10.5, 10.0),
                                            (11.0, 9.5, 10.0)]))
    assert near["status"] == "completed"
    assert near["agreement"] == "agree"
    assert near["centroid_distance_a"] < 0.6
    assert near["diffdock_confidence"] == 0.42
    far = cross_check("RECEPTOR", "CCO", vina, tmp_path / "w2",
                      runner=make_runner([(40.0, 40.0, 40.0)]))
    assert far["agreement"] == "disagree"
    assert far["centroid_distance_a"] > 40


def test_not_available_without_installation(tmp_path, monkeypatch):
    """With no checkout configured the cross-check reports
    not_available and runs nothing."""
    monkeypatch.delenv("MADD_DIFFDOCK_HOME", raising=False)
    record = cross_check("RECEPTOR", "CCO", pdb_pose([(0, 0, 0)]),
                         tmp_path / "w", runner=make_runner([(0, 0, 0)]))
    assert record["status"] == "not_available"
    assert "MADD_DIFFDOCK_HOME" in record["detail"]


def test_failed_run_is_recorded(tmp_path, monkeypatch):
    """A DiffDock run that exits nonzero records failed with
    its error tail, and one producing no pose does the same."""
    home = tmp_path / "diffdock-home"
    home.mkdir()
    monkeypatch.setenv("MADD_DIFFDOCK_HOME", str(home))
    record = cross_check("RECEPTOR", "CCO", pdb_pose([(0, 0, 0)]),
                         tmp_path / "w1",
                         runner=make_runner([(0, 0, 0)], returncode=2))
    assert record["status"] == "failed"

    def empty_runner(home_, protein_path, smiles, out_dir):
        """Produce an output dir with no pose in it."""

        class Result:
            """A subprocess-result-shaped object."""
        result = Result()
        result.returncode = 0
        result.stderr = ""
        result.stdout = ""
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        return result

    record = cross_check("RECEPTOR", "CCO", pdb_pose([(0, 0, 0)]),
                         tmp_path / "w2", runner=empty_runner)
    assert record["status"] == "failed"
    assert "no ranked pose" in record["detail"]
