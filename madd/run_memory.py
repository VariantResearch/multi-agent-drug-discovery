"""Run memory: operational history across runs, fenced to
outcomes metadata.

Systems that learn from their own runs usually learn the
wrong thing: their own prior output, recycled as if it were
knowledge. This memory is fenced against exactly that. It
reads finished run bundles and carries forward ONLY
operational metadata:

- per target: the runs attempted, their outcomes (locked,
  no_go, designed, gate results), and when;
- per provider: the runs it sat on, and how the debates it
  joined ended;
- per run: strike counts (numbers, never claim text).

Nothing else crosses the fence. No claim text, no supporting
quotes, no dossier content, no candidate structures are read
into the memory, and the memory is never supplied to a run
as evidence: it is surfaced to the operator at framing time
(and through the run-memory command) so a human can see
"this target no-go'd twice, both times on strike-heavy
debates" before staffing another run. Prior AI output is
not, and under this fence cannot become, a citable source.
"""
import json
from pathlib import Path


def _bundle_files(runs_dir):
    """Every bundle.json under a runs directory, sorted."""
    root = Path(runs_dir)
    if not root.is_dir():
        return []
    return sorted(root.glob("*/bundle.json"))


def _run_entry(bundle: dict) -> dict:
    """The operational metadata of one run bundle. Only the
    named fields are read; everything else in the bundle is
    invisible to the memory by construction."""
    kind = bundle.get("kind")
    record = ((bundle.get("frame_run") or {}).get("record")
              or bundle.get("record") or {})
    providers = []
    if kind == "gate0_run":
        providers = [p.get("name") for p in bundle.get("providers")
                     or [] if p.get("name")]
        return {
            "run_id": bundle.get("run_id"), "kind": kind,
            "created_utc": bundle.get("created_utc"),
            "outcome": (bundle.get("thresholds") or {}).get("overall"),
            "cases": len(bundle.get("case_ids") or []),
            "providers": providers,
            "strikes": None,
            "target": None,
        }
    target = (bundle.get("target") or {}).get("name")
    design = bundle.get("design") or {}
    return {
        "run_id": bundle.get("run_id"), "kind": kind,
        "created_utc": bundle.get("created_utc"),
        "outcome": bundle.get("outcome"),
        "debate_outcome": record.get("outcome"),
        "strikes": len(record.get("strike_list") or []),
        "design_gate": (design.get("gate_report") or {}).get("result"),
        "providers": [p.get("name") for p in
                      ((bundle.get("frame_run") or {}).get("providers")
                       or []) if isinstance(p, dict) and p.get("name")],
        "target": target,
    }


def build_memory(runs_dir) -> dict:
    """Scan a runs directory into the fenced memory digest."""
    runs = []
    for path in _bundle_files(runs_dir):
        try:
            bundle = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(bundle, dict) and bundle.get("kind"):
            runs.append(_run_entry(bundle))
    targets = {}
    providers = {}
    for run in runs:
        if run.get("target"):
            slot = targets.setdefault(run["target"], {
                "runs": 0, "outcomes": {}, "last_outcome": None,
                "last_run_id": None, "total_strikes": 0})
            slot["runs"] += 1
            outcome = run.get("outcome")
            if outcome:
                slot["outcomes"][outcome] = slot["outcomes"].get(
                    outcome, 0) + 1
            slot["last_outcome"] = outcome
            slot["last_run_id"] = run["run_id"]
            slot["total_strikes"] += run.get("strikes") or 0
        for name in run.get("providers") or []:
            slot = providers.setdefault(name, {
                "runs": 0, "debate_outcomes": {}})
            slot["runs"] += 1
            outcome = run.get("debate_outcome") or run.get("outcome")
            if outcome:
                slot["debate_outcomes"][outcome] = \
                    slot["debate_outcomes"].get(outcome, 0) + 1
    return {
        "artifact_type": "run_memory",
        "schema_version": "0.1.0",
        "runs_scanned": len(runs),
        "runs": runs,
        "targets": targets,
        "providers": providers,
        "fence": ("operational metadata only: outcomes, counts, "
                  "provider names, run ids. No claim text, "
                  "quotes, dossier content, or candidate "
                  "structures are carried, and this memory is "
                  "never evidence in a run."),
    }


def target_history(memory: dict, target_name: str):
    """One target's history entry from a built memory, or
    None when the target has never run."""
    if not target_name:
        return None
    return (memory.get("targets") or {}).get(target_name)
