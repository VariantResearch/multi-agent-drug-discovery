"""License-gated runner for external structure design tools.

Nothing executes unless the license registry clears the tool for the
intended use. A blocked tool returns a blocked_license manifest and is
never run. A cleared tool that is not installed returns not_installed.
A tool that runs has every output file recorded by path and SHA-256
hash in the manifest, so a structure that enters a design bundle can
always be traced to the run that produced it.

The command lines below follow each tool's documented predict-style
CLI. An operator must verify the argv against the installed tool's own
--help before a first real run; this module reports what it ran rather
than assuming success, and a nonzero exit is a failed run, never
retried silently.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from . import license_registry

_EXECUTABLES = {"Boltz-2": "boltz", "Chai-1": "chai",
                "AutoDock Vina": "vina"}
_ARGV = {
    # exe is filled in at run time; {input} and {out} are substituted.
    "Boltz-2": ["{exe}", "predict", "{input}", "--out_dir", "{out}"],
    "Chai-1": ["{exe}", "fold", "{input}", "{out}"],
    # Vina's input is its config file: the config names the receptor
    # and ligand PDBQT files and the search box, which is how a
    # docking run is actually specified.
    "AutoDock Vina": ["{exe}", "--config", "{input}",
                      "--out", "{out}/docked.pdbqt"],
}


def _sha256(path: Path) -> str:
    """SHA-256 hex digest of a file, read in chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def run_structure_tool(tool_name: str, use: str, work_dir,
                       input_path=None, timeout_s: int = 900) -> dict:
    """Attempt one structure tool run and return its manifest.

    Statuses: blocked_license (registry refusal, nothing ran),
    not_installed (no executable found), no_input (cleared and
    installed but no input file supplied), failed (ran, nonzero exit
    or timeout), completed (ran, outputs recorded).
    """
    manifest = {"tool": tool_name, "use": use, "status": "not_run",
                "outputs": []}
    verdict = license_registry.check_tool(tool_name, use)
    manifest["license"] = verdict
    if not verdict.get("allowed"):
        manifest["status"] = "blocked_license"
        manifest["reason"] = verdict.get("reason") or "registry does not allow this use"
        return manifest
    exe_name = _EXECUTABLES.get(tool_name, tool_name.lower())
    exe = shutil.which(exe_name)
    manifest["executable"] = exe
    if not exe:
        manifest["status"] = "not_installed"
        manifest["reason"] = "no '" + exe_name + "' executable on PATH"
        return manifest
    if not input_path:
        manifest["status"] = "no_input"
        manifest["reason"] = "tool is installed but no input file was supplied"
        return manifest
    work = Path(work_dir)
    out_dir = work / "tool-output"
    out_dir.mkdir(parents=True, exist_ok=True)
    # Snapshot what is already in the output directory. The CLI reuses
    # a deterministic work dir per brief, so without this a later run
    # would claim an earlier run's leftover files as its own outputs.
    before = {}
    for path in sorted(out_dir.rglob("*")):
        if path.is_file():
            before[str(path)] = _sha256(path)
    template = _ARGV.get(tool_name, ["{exe}", "predict", "{input}", "{out}"])
    argv = [part.replace("{exe}", exe).replace("{input}", str(input_path))
            .replace("{out}", str(out_dir)) for part in template]
    manifest["argv"] = argv
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout_s)
        manifest["exit_code"] = proc.returncode
        manifest["stderr_tail"] = (proc.stderr or "")[-2000:]
        if proc.returncode != 0:
            manifest["status"] = "failed"
            return manifest
    except subprocess.TimeoutExpired:
        manifest["status"] = "failed"
        manifest["reason"] = "timed out after " + str(timeout_s) + "s"
        return manifest
    outputs = []
    skipped = []
    for path in sorted(out_dir.rglob("*")):
        if path.is_file():
            digest = _sha256(path)
            if before.get(str(path)) == digest:
                skipped.append(str(path))
                continue
            outputs.append({"path": str(path), "sha256": digest,
                            "bytes": path.stat().st_size})
    manifest["outputs"] = outputs
    manifest["pre_existing_outputs_skipped"] = skipped
    manifest["status"] = "completed"
    return manifest


STRUCTURE_SUFFIXES = {"cif", "mmcif", "pdb", "xyz", "mol2", "sdf", "mol", "pdbqt"}


def run_retrosynthesis(smiles: str, config_path, work_dir,
                       use: str = "research", timeout_s: int = 1800) -> dict:
    """Attempt one AiZynthFinder route search for a single molecule.

    AiZynthFinder does not fit the generic predict-style runner: it
    needs both a target (--smiles, a string or a file of SMILES) and a
    YAML config naming its downloaded model and stock files. This
    function writes the SMILES to a file inside work_dir, runs
    aizynthcli with the operator's config, and manifests the outcome
    like any other tool run. Statuses mirror run_structure_tool, plus
    no_config when the config file is absent (the usual first-run
    state: the tool is installed but its model files were never
    downloaded). A completed run's routes.json is parsed for a solved
    count when its shape allows; an unparseable output is recorded as
    completed with solved unknown, never guessed.
    """
    manifest = {"tool": "AiZynthFinder", "use": use, "status": "not_run",
                "outputs": [], "solved": None, "targets": 0}
    verdict = license_registry.check_tool("AiZynthFinder", use)
    manifest["license"] = verdict
    if not verdict.get("allowed"):
        manifest["status"] = "blocked_license"
        manifest["reason"] = verdict.get("reason") or "registry does not allow this use"
        return manifest
    exe = shutil.which("aizynthcli")
    manifest["executable"] = exe
    if not exe:
        manifest["status"] = "not_installed"
        manifest["reason"] = "no 'aizynthcli' executable on PATH"
        return manifest
    if not config_path or not Path(config_path).exists():
        manifest["status"] = "no_config"
        manifest["reason"] = ("no AiZynthFinder config file: the tool needs a "
                               "YAML config naming its downloaded model and "
                               "stock files before any route search can run")
        return manifest
    work = Path(work_dir)
    out_dir = work / "tool-output"
    out_dir.mkdir(parents=True, exist_ok=True)
    smiles_file = work / "target_smiles.txt"
    smiles_file.write_text(str(smiles).strip() + "\n")
    out_file = out_dir / "routes.json"
    argv = [exe, "--smiles", str(smiles_file), "--config", str(config_path),
            "--output", str(out_file)]
    manifest["argv"] = argv
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout_s)
        manifest["exit_code"] = proc.returncode
        manifest["stderr_tail"] = (proc.stderr or "")[-2000:]
        if proc.returncode != 0:
            manifest["status"] = "failed"
            return manifest
    except subprocess.TimeoutExpired:
        manifest["status"] = "failed"
        manifest["reason"] = "timed out after " + str(timeout_s) + "s"
        return manifest
    if out_file.exists():
        manifest["outputs"] = [{"path": str(out_file),
                                "sha256": _sha256(out_file),
                                "bytes": out_file.stat().st_size}]
        try:
            data = json.loads(out_file.read_text())
            entries = data if isinstance(data, list) else data.get("routes", [])
            manifest["targets"] = len(entries)
            solved = [e for e in entries
                      if isinstance(e, dict) and e.get("is_solved")]
            if entries and all(isinstance(e, dict) and "is_solved" in e
                                for e in entries):
                manifest["solved"] = len(solved)
        except Exception:
            manifest["solved"] = None
    manifest["status"] = "completed"
    return manifest


def candidates_from_tool_run(manifest: dict, spec_id: str) -> list[dict]:
    """Turn a completed tool run's structure outputs into candidates.

    One candidate per output file with a structure suffix; logs and
    other side files stay in the manifest's output list but do not
    become "structures". No claims, no predicted properties, and no
    constraint evaluations are invented: the tool produced a structure,
    and assessing it is later work under the same audit rules.
    """
    if manifest.get("status") != "completed":
        return []
    out = []
    tool = manifest.get("tool", "tool")
    slug = tool.lower().replace(" ", "-")
    structure_outputs = [o for o in manifest.get("outputs", [])
                         if Path(o["path"]).suffix.lstrip(".").lower()
                         in STRUCTURE_SUFFIXES]
    for i, output in enumerate(structure_outputs, start=1):
        suffix = Path(output["path"]).suffix.lstrip(".") or "structure"
        out.append({
            "artifact_type": "candidate",
            "schema_version": "0.1.0",
            "candidate_id": slug + "-output-" + str(i),
            "spec_id": spec_id,
            "modality": "structure_prediction",
            "design_tool": tool,
            "description": ("Structure output " + Path(output["path"]).name
                            + " from a recorded " + tool + " run."),
            "structure": {"format": suffix, "path": output["path"],
                          "sha256": output["sha256"]},
            "claims": [],
            "predicted_properties": [],
            "constraint_results": [],
            "provenance": {"tool_run_status": manifest["status"],
                           "argv": manifest.get("argv")},
        })
    return out


def manifest_json(manifest: dict) -> str:
    """A manifest as stable JSON text, for logs and bundles."""
    return json.dumps(manifest, indent=2, sort_keys=True)
