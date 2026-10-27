"""Tests for stage checkpoints: the store's guard semantics,
and Gate 0 / target-run resume behavior - a resumed run
reuses finished stages with no provider calls for them, and
a changed input pack invalidates the checkpoint completely.
Providers here are counting stubs over the suites' fixtures.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.checkpoints import CheckpointStore
from madd.runner import run_gate0
from madd.target_run import build_target_frame, run_target
from tests.test_runner import CaseStub, DRUGS, GATE0
from tests.test_target_run import _StubDesigner, _frame, _panel as target_panel


def _panel():
    """A two-stub Gate 0 panel endorsing every case's drug."""
    return [CaseStub("a", set(DRUGS.values())),
            CaseStub("b", set(DRUGS.values()))]


def _judge():
    """A stub judge endorsing every case's drug."""
    return CaseStub("j", set(DRUGS.values()))


def _baseline():
    """A stub baseline endorsing nothing."""
    return CaseStub("base", set())


def test_store_guard_semantics(tmp_path):
    """A payload round-trips; a guard mismatch reads as
    absent; keys list what was saved."""
    store = CheckpointStore(tmp_path / "cp")
    store.save("run-1", "case-a", {"x": 1}, guard="h1")
    assert store.load("run-1", "case-a", guard="h1") == {"x": 1}
    assert store.load("run-1", "case-a", guard="h2") is None
    assert store.load("run-1", "missing") is None
    assert store.keys("run-1") == ["case-a"]


def test_gate0_resume_skips_finished_cases(tmp_path):
    """Run once with checkpoints, then resume with providers
    that fail if called for a finished stage: the resumed run
    completes from the checkpoints alone."""
    providers = _panel()
    bundle1 = run_gate0(providers, judge_provider=_judge(),
                        baseline_provider=_baseline(),
                        gate0_dir=GATE0, run_id="resume-me",
                        checkpoint_dir=str(tmp_path / "cp"))
    assert bundle1["run_id"] == "resume-me"

    class Exploding(CaseStub):
        """A provider that must never be called on resume."""

        def research(self, frame):
            """Raise: resume should not need research calls."""
            raise AssertionError("provider called during resume")

        def complete(self, system, user):
            """Raise: resume should not need completions."""
            raise AssertionError("provider called during resume")

    events = []
    bundle2 = run_gate0([Exploding("a"), Exploding("b")],
                        judge_provider=Exploding("j"),
                        baseline_provider=Exploding("base"),
                        gate0_dir=GATE0, run_id="resume-me",
                        checkpoint_dir=str(tmp_path / "cp"),
                        resume=True, on_event=events.append)
    assert bundle2["predictions"] == bundle1["predictions"]
    resumed = [e for e in events
               if e.get("event") == "case_checkpoint_resumed"]
    assert len(resumed) >= 8, "every case and baseline resumed"


def test_gate0_resume_without_checkpoints_computes(tmp_path):
    """Resume with an empty store is just a normal run."""
    bundle = run_gate0(_panel(), judge_provider=_judge(),
                       baseline_provider=_baseline(),
                       gate0_dir=GATE0, run_id="fresh",
                       checkpoint_dir=str(tmp_path / "cp"),
                       resume=True)
    assert len(bundle["predictions"]) == 8


def test_target_run_resume_reuses_stages(tmp_path, monkeypatch):
    """A target run resumed with the same id and inputs makes
    no debate or design calls: exploding seams prove it."""
    import madd.trials
    monkeypatch.setattr(madd.trials, "landscape",
                        lambda *a, **kw: {"total_trials": 0})
    frame = _frame()
    bundle1 = run_target(frame, target_panel(frame),
                         designer=_StubDesigner(), mode="simple",
                         run_id="target-resume",
                         checkpoint_dir=str(tmp_path / "cp"))
    assert bundle1["outcome"] == "designed"

    import madd.target_run as target_run_module

    def exploding_run_frame(*args, **kwargs):
        """Raise: the frame stage must come from checkpoint."""
        raise AssertionError("frame stage recomputed on resume")

    monkeypatch.setattr(target_run_module, "run_frame",
                        exploding_run_frame)
    events = []
    bundle2 = run_target(frame, target_panel(frame),
                         designer=_StubDesigner(), mode="simple",
                         run_id="target-resume",
                         checkpoint_dir=str(tmp_path / "cp"),
                         resume=True, on_event=events.append)
    assert bundle2["outcome"] == "designed"
    stages = [e.get("stage") for e in events
              if e.get("event") == "stage_checkpoint_resumed"]
    assert "frame" in stages and "design" in stages
