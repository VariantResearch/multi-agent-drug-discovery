"""Command line interface.

Subcommands:
  audit-claims <file>
  check-tool <tool> --use research|commercial
  debate-mock <frame-file> [--judge] [--out <file>]
  focus-score <file>
  gate0-list [--gate0-dir <dir>]
  gate0-report <predictions-file> [--baseline <file>]
               [--audit-violations <n>] [--judge-swap-flips <n>]
  gate0-validate [--gate0-dir <dir>]
  gate0-new-case <case-id> [--gate0-dir <dir>]
  providers-check --config <file>
  providers-smoke --config <file>
  resolve-citations <file>
  run-frame <frame-file> --config <file> [--out <dir>]
  run-gate0 --config <file> [--out <dir>] [--gate0-dir <dir>]
               [--dry-run] [--jobs <n>]
  compare-runs <bundle-a> <bundle-b>
  design-brief <source> [--case <case-id>] [--constraint <text>]...
  design-run <source> [--case <case-id>] [--constraint <text>]...
               [--out <dir>] [--config <file>] [--tool <name>]
               [--use research|commercial] [--tool-input <file>]
  transcript <file>
  report-html <bundle-file>
  report-pdf <bundle-file> --out <file.pdf> [--use research|commercial]
  calibration <bundle-file>... [--gate0-dir <dir>]
  prereg-verify <bundle-file>
  gui [--port 8765] [--host 127.0.0.1] [--runs-dir runs]
  validate-artifact <schema-name> <file>

Output is human-readable. Exit status is non-zero when a check fails.
debate-mock runs the debate engine on deterministic mock providers:
it exercises the plumbing and its outcome is never a research result.
resolve-citations makes live network calls to the public registries.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .budget import BudgetExceeded
from .citation_auditor import audit_citations
from .claims import audit_claims
from .config import (ConfigError, build_providers,
                     contradiction_checker_from_config,
                     tournament_judge_from_config,
                     entailment_checker_from_config, load_config,
                     quote_checker_from_config, resolver_from_config,
                     run_budget_tracker)
from .debate import run_debate
from .focus import focus_score
from .gate0 import (evaluate_thresholds, list_case_ids, load_input_pack,
                   score_run, validate_dataset)
from .design import ModelDesigner, build_brief, run_design
from .design_tools import candidates_from_tool_run, run_structure_tool
from .license_registry import check_tool
from .providers import MockProvider
from .providers_http import ProviderError
from .resolve import check_quote_against_source, resolve_document
from .opentargets import evidence_for_frame
from .retrieval import retrieve_evidence
from .runner import estimate_gate0_run, run_frame, run_gate0
from .target_run import TARGET_KINDS, build_target_frame, run_target
from .schemas import SCHEMA_NAMES, validate_artifact
from .smoke import smoke_panel
from .html_report import bundle_to_html
from .storage import write_bundle
from .transcript import record_to_markdown


def _load(path: str):
    """Read and parse a JSON file argument."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_spec_arg(path, case_id=None):
    """Load a consensus spec from a spec file or a run bundle.

    Accepts a consensus_spec artifact, a frame run bundle (its record's
    spec), or a Gate 0 bundle with --case naming the case whose spec to
    design from. Returns (spec, source label).
    """
    data = _load(path)
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object in " + str(path)
                         + " (a spec, a frame bundle, or a Gate 0 bundle)")
    if data.get("artifact_type") == "consensus_spec":
        return data, "spec file " + str(path)
    if data.get("kind") == "frame_run":
        spec = (data.get("record") or {}).get("spec")
        if spec:
            return spec, "frame run " + str(data.get("run_id"))
    if data.get("kind") == "gate0_run":
        if not case_id:
            raise ValueError("a Gate 0 bundle holds one spec per case; pass --case <case_id>")
        record = (data.get("case_records") or {}).get(case_id)
        if record and record.get("spec"):
            return record["spec"], "gate 0 case " + case_id
        raise ValueError("no record with a spec for case " + str(case_id))
    raise ValueError("could not find a consensus spec in " + str(path))


def _cmd_design_brief(args) -> int:
    """Print the design brief a locked spec produces."""
    try:
        spec, source = _load_spec_arg(args.source, args.case)
        brief = build_brief(spec, source, tuple(args.constraint or ()),
                            target=args.target, disease=args.disease)
    except (OSError, ValueError) as exc:
        print("design-brief failed: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(brief, indent=2, sort_keys=True))
    return 0


def _cmd_design_run(args) -> int:
    """Run the Phase 2 design stage for a locked spec and store the bundle."""
    try:
        spec, source = _load_spec_arg(args.source, args.case)
        constraints = tuple(args.constraint or ())
        brief = build_brief(spec, source, constraints,
                            target=args.target, disease=args.disease)
        designer = None
        tracker = None
        if args.config:
            built = build_providers(load_config(args.config))
            tracker = run_budget_tracker(built)
            designer = ModelDesigner(built["providers"],
                                     budget_tracker=tracker)
            print("designer: model panel from " + args.config + " ("
                  + ", ".join(getattr(p, "name", "?") for p in built["providers"]) + ")")
        tool_runs, extra = [], []
        if args.tool:
            work = Path(args.out) / ("toolwork-" + brief["brief_id"])
            manifest = run_structure_tool(args.tool, args.use, work,
                                          input_path=args.tool_input)
            manifest["requested"] = True
            tool_runs.append(manifest)
            extra = candidates_from_tool_run(manifest, spec.get("spec_id"))
            print("tool " + args.tool + ": " + manifest["status"]
                  + (" - " + str(manifest.get("reason")) if manifest.get("reason") else ""))
        bundle = run_design(spec, source, design_constraints=constraints,
                            designer=designer, budget_tracker=tracker,
                            tool_runs=tuple(tool_runs),
                            extra_candidates=tuple(extra),
                            target=args.target, disease=args.disease,
                            use=args.use,
                            source_check=bool(getattr(args, "source_check", False)),
                            retro_config=getattr(args, "retro_config", None),
                            retro_work_dir=(Path(args.out) / "retro-work"
                                            if getattr(args, "retro_config", None)
                                            else None))
    except BudgetExceeded as exc:
        print("run stopped: " + str(exc), file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print("design-run failed: " + str(exc), file=sys.stderr)
        return 1
    run_dir = write_bundle(bundle, args.out)
    ranking = bundle["ranking"]
    print("design run " + bundle["run_id"] + " written to " + str(run_dir))
    print("gate: " + bundle["gate_report"]["result"] + " | ranked: "
          + str(len(ranking["ranked"])) + " | excluded: "
          + str(len(ranking["excluded"])))
    for cid in ranking["ranked"]:
        print("  ranked: " + str(cid))
    for ex in ranking["excluded"]:
        print("  excluded: " + str(ex.get("candidate_id")) + " - "
              + "; ".join(ex.get("reasons") or []))
    # Like run-gate0, a failed gate is a failed command: the bundle is
    # written either way, but scripts must be able to see the failure.
    return 0 if bundle["gate_report"]["result"] == "pass" else 1


def _cmd_audit_claims(args) -> int:
    """audit-claims handler: print the claim and citation audits of a
    document; exit 1 when either audit finds errors."""
    doc = _load(args.file)
    report = audit_claims(doc)
    print("claims:", report["claim_count"])
    print("errors:", report["error_count"])
    for e in report["errors"]:
        print(" -", e["claim_id"], "|", e["code"], "|", e["message"])
    citations = audit_citations(doc)
    print("citation format problems:", citations["problem_count"])
    for entry in citations["entries"]:
        if not entry["format"]["ok"] or entry["problems"]:
            print(" -", entry["claim_id"], "|", entry["format"]["code"],
                  "|", entry["format"]["message"])
            for p in entry["problems"]:
                print("   ", p["code"], "|", p["message"])
    if citations["needs_live_resolution"]:
        print("still needs live resolution:", ", ".join(citations["needs_live_resolution"]))
    ok = report["ok"] and citations["problem_count"] == 0
    print("result:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def _cmd_check_tool(args) -> int:
    """check-tool handler: print the license registry verdict for a
    named tool; exit 0 only when the tool is allowed as registered."""
    result = check_tool(args.tool, args.use)
    print("tool:", result["tool"])
    print("use:", result["use"])
    print("license:", result["license"])
    print("status:", result["status"])
    print("allowed:", "yes" if result["allowed"] else "no")
    print("reason:", result["reason"])
    return 0 if result["allowed"] else 1


def _cmd_focus_score(args) -> int:
    """focus-score handler: print a document's deterministic focus
    score as JSON."""
    doc = _load(args.file)
    result = focus_score(doc)
    print("focus score:", result["score"])
    print("audited claims:", result["audited_claim_count"], "of", result["total_claim_count"])
    print("per-tier counts:", json.dumps(result["per_tier_counts"], sort_keys=True))
    print("basis:", result["basis"])
    return 0


def _cmd_validate_artifact(args) -> int:
    """validate-artifact handler: validate a file against a named
    schema; exit 1 on any error."""
    if args.schema_name not in SCHEMA_NAMES:
        print("unknown schema name:", args.schema_name)
        print("known:", ", ".join(SCHEMA_NAMES))
        return 2
    doc = _load(args.file)
    errors = validate_artifact(args.schema_name, doc)
    if errors:
        print("result: FAIL")
        for e in errors:
            print(" -", e["path"], "|", e["code"], "|", e["message"])
        return 1
    print("result: PASS -", args.schema_name, "structure ok")
    return 0


def _cmd_gate0_validate(args) -> int:
    """gate0-validate handler: validate the Gate 0 dataset; exit 1
    when any check fails."""
    report = validate_dataset(args.gate0_dir)
    print("cases:", report["case_count"])
    print("errors:", report["error_count"])
    for e in report["errors"]:
        print(" -", e.get("case_id", "-"), "|", e["code"], "|", e["message"])
    print("result:", "PASS" if report["ok"] else "FAIL")
    return 0 if report["ok"] else 1


def _cmd_gate0_list(args) -> int:
    """gate0-list handler: print each Gate 0 case id with its disease."""
    for case_id in list_case_ids(args.gate0_dir):
        pack = load_input_pack(case_id, args.gate0_dir)
        print(case_id, "|", pack.get("disease", ""))
    return 0


def _cmd_gate0_report(args) -> int:
    """gate0-report handler: score a predictions file and judge it
    against the approved thresholds; exit 0 only on a full pass."""
    predictions = _load(args.predictions)
    debate_score = score_run(predictions)
    print("debate score: correct", debate_score["correct_calls"], "of",
          debate_score["case_count"], "| killed", debate_score["failures_correctly_killed"],
          "| advanced", debate_score["positives_correctly_advanced"])
    baseline_score = None
    if args.baseline:
        baseline_score = score_run(_load(args.baseline))
        print("baseline score: correct", baseline_score["correct_calls"], "of",
              baseline_score["case_count"])
    report = evaluate_thresholds(
        debate_score, baseline_score=baseline_score,
        audit_violations=args.audit_violations,
        judge_swap_flips=args.judge_swap_flips)
    for check in report["checks"]:
        print(" -", check["threshold"], "|", check["status"], "|", check["detail"])
    print("thresholds:", report["thresholds_source"])
    print("result:", "PASS" if report["passed"] else "FAIL")
    return 0 if report["passed"] else 1


def _cmd_resolve_citations(args) -> int:
    """resolve-citations handler: live-resolve a document's claim
    identifiers against their registries (PubMed, Crossref,
    ClinicalTrials.gov, Europe PMC, GWAS Catalog, ChEMBL, PubChem,
    UniProt). With --check-quotes, also verify each quote_checked
    claim's quote against the source's open full text at Europe PMC;
    a quote absent from retrieved full text fails the result."""
    doc = _load(args.file)
    report = resolve_document(doc)
    for entry in report["entries"]:
        print(" -", entry["claim_id"], "|", entry["status"], "|",
              entry.get("title") or entry["detail"])
    print("counts:", json.dumps(report["status_counts"], sort_keys=True))
    quotes_bad = False
    if getattr(args, "check_quotes", False):
        from .claims import extract_claims
        print("quote checks (Europe PMC full text):")
        for claim in extract_claims(doc):
            if claim.get("verification_status") != "quote_checked":
                continue
            check = check_quote_against_source(
                claim.get("source_identifier"), claim.get("identifier_type"),
                claim.get("supporting_quote"))
            print(" -", claim.get("claim_id"), "|", check["status"], "|",
                  check["detail"])
            if check["status"] == "quote_not_found":
                quotes_bad = True
    all_resolved = report["claim_count"] > 0 and all(
        e["status"] == "resolved" for e in report["entries"])
    passed = all_resolved and not quotes_bad
    print("result:", "PASS" if passed else "FAIL")
    return 0 if passed else 1


def _print_run_event(event):
    """Render one runner progress event as a single CLI line."""
    kind = event.get("event")
    if kind == "run_started":
        print("run started:", event.get("run_id"), "| cases:",
              len(event.get("case_ids") or []), flush=True)
    elif kind == "baseline_case_done":
        print("  baseline", event.get("case_id"), "->", event.get("prediction"),
              flush=True)
    elif kind == "debate_case_done":
        print("  debate", event.get("case_id"), "->", event.get("prediction"),
              "| strikes:", event.get("strikes"), flush=True)
    elif kind == "run_finished":
        print("run finished:", event.get("outcome"), flush=True)


def _built_from_config(args):
    """Load the --config file and construct its providers."""
    config = load_config(args.config)
    return build_providers(config)


def _cmd_providers_check(args) -> int:
    """providers-check handler: validate a run config, report each
    provider and which key variables are set; makes no network calls."""
    try:
        config = load_config(args.config)
        built = build_providers(config)
    except ConfigError as exc:
        print("config problem:", exc)
        return 2
    entries = list(config["providers"])
    for role in ("judge", "baseline"):
        if config.get(role):
            entries.append(config[role])
    objects = list(built["providers"])
    for role in ("judge", "baseline"):
        if built[role] is not None:
            objects.append(built[role])
    for entry, obj in zip(entries, objects):
        kind = entry["kind"]
        if kind == "mock":
            key_line = "no key needed (mock)"
        else:
            key_line = "key variable " + entry["api_key_env"] + " is set"
        print(" -", entry["name"], "|", kind, "| model",
              getattr(obj, "model_version", "mock"), "|", key_line)
    print("budget:", config.get("budget"))
    print("live resolution:", "on" if built["live_resolution"] else "off")
    print("note: configuration builds cleanly. No network calls were made; "
          "a provider is only proven by an actual run.")
    return 0


def _cmd_providers_smoke(args) -> int:
    """providers-smoke handler: one billable call per configured
    provider (panel, judge, baseline), reported per provider. Exit 0
    only when every provider answers."""
    try:
        built = _built_from_config(args)
    except ConfigError as exc:
        print("config problem:", exc)
        return 2
    targets = list(built["providers"])
    for role in ("judge", "baseline"):
        if built[role] is not None:
            targets.append(built[role])
    print("This makes ONE billable API call per provider below ("
          + str(len(targets)) + " calls total).")
    results = smoke_panel(targets)
    all_ok = True
    for result in results:
        all_ok = all_ok and result["ok"]
        line = (" - " + str(result["provider"]) + " | "
                + ("OK" if result["ok"] else "FAILED")
                + " | " + str(result["latency_ms"]) + " ms"
                + " | model returned: " + str(result["model_returned"])
                + " | usage: " + str(result["usage"]))
        if result["retries"]:
            line += " | retries: " + str(result["retries"])
        if result["error"]:
            line += " | error: " + result["error"]
        print(line)
    return 0 if all_ok else 1


def _cmd_run_gate0(args) -> int:
    """run-gate0 handler: execute a full Gate 0 run from a config.
    Exit 0 on a pass, 1 on a fail, 2 when the run itself stopped.
    With --dry-run, print the call and cost estimate and stop."""
    try:
        built = _built_from_config(args)
    except ConfigError as exc:
        print("config problem:", exc)
        return 2
    if args.dry_run:
        estimate = estimate_gate0_run(built["providers"], built["judge"],
                                      built["baseline"], args.gate0_dir,
                                      swap_judge_provider=built.get("judge_swap"))
        print("cases:", estimate["case_count"])
        print("calls per case:", estimate["calls_per_case"])
        print("total calls:", estimate["total_calls"])
        print("estimated cost (USD):", estimate["estimated_cost_usd"])
        if not estimate["baseline_configured"]:
            print("note: no baseline configured; a real run would be refused")
        print("note:", estimate["note"])
        return 0
    try:
        tracker = run_budget_tracker(built)
        bundle = run_gate0(built["providers"], judge_provider=built["judge"],
                           swap_judge_provider=built.get("judge_swap"),
                           baseline_provider=built["baseline"],
                           mode=built.get("mode"),
                           budget_tracker=tracker, gate0_dir=args.gate0_dir,
                           resolver=resolver_from_config(built),
                           quote_checker=quote_checker_from_config(built),
                           entailment_checker=entailment_checker_from_config(built, tracker),
                           contradiction_checker=contradiction_checker_from_config(built, tracker),
                           tournament_judge=tournament_judge_from_config(built, tracker),
                           retrieval_first=bool(built.get("retrieval_first")),
                           max_workers=args.jobs or built["max_workers"],
                           on_event=_print_run_event)
    except (ConfigError, ProviderError, BudgetExceeded, ValueError) as exc:
        print("run stopped:", exc)
        return 2
    score = bundle["debate_score"]
    print("run:", bundle["run_id"])
    print("mode:", bundle.get("mode"))
    print("debate score: correct", score["correct_calls"], "of", score["case_count"],
          "| killed", score["failures_correctly_killed"],
          "| advanced", score["positives_correctly_advanced"])
    print("baseline score: correct", bundle["baseline_score"]["correct_calls"],
          "of", bundle["baseline_score"]["case_count"])
    for check in bundle["thresholds"]["checks"]:
        print(" -", check["threshold"], "|", check["status"], "|", check["detail"])
    print("outcome:", "PASS" if bundle["outcome"] == "pass" else "FAIL")
    if args.out:
        run_dir = write_bundle(bundle, args.out)
        print("bundle written to:", run_dir)
    return 0 if bundle["outcome"] == "pass" else 1


def _cmd_target_run(args) -> int:
    """target-run handler: name a target, run research and debate,
    and on a locked specification run the design stage, all under the
    config's protocol mode, writing one combined bundle."""
    try:
        built = _built_from_config(args)
        frame = build_target_frame(args.name, args.kind, target=args.target,
                                   disease=args.disease, focus_id=args.focus)
        retrieval_first = bool(built.get("retrieval_first"))
        if not args.no_retrieve:
            entries = retrieve_evidence(frame)
            ot_entries = evidence_for_frame(frame)
            frame["evidence"] = entries + ot_entries
            retrieval_first = True
            print("retrieved evidence:", len(entries),
                  "sources from Europe PMC,", len(ot_entries),
                  "association from Open Targets")
        tracker = run_budget_tracker(built)
        bundle = run_target(
            frame, built["providers"], judge_provider=built["judge"],
            swap_judge_provider=built.get("judge_swap"),
            mode=built.get("mode"), budget_tracker=tracker,
            resolver=resolver_from_config(built),
            quote_checker=quote_checker_from_config(built),
            entailment_checker=entailment_checker_from_config(built, tracker),
                           contradiction_checker=contradiction_checker_from_config(built, tracker),
                           tournament_judge=tournament_judge_from_config(built, tracker),
            retrieval_first=retrieval_first,
            design_constraints=tuple(args.constraint or ()),
            source_check=bool(args.source_check),
            on_event=_print_run_event,
            prereg_dir=(None if getattr(args, "no_prereg", False)
                        else args.out))
    except (ConfigError, ProviderError, BudgetExceeded, ValueError) as exc:
        print("run stopped:", exc)
        return 2
    record = bundle["frame_run"]["record"]
    print("run:", bundle["run_id"])
    print("target:", bundle["target"]["name"], "| mode:", bundle["mode"])
    print("debate outcome:", record["outcome"],
          "| focus:", record["spec"].get("focus_id"),
          "| strikes:", len(record["strike_list"]))
    design = bundle.get("design")
    if design is not None:
        ranking = design["ranking"]
        print("design gate:", design["gate_report"]["result"],
              "| ranked:", len(ranking["ranked"]),
              "| excluded:", len(ranking["excluded"]))
        for cid in ranking["ranked"]:
            print("  ranked:", cid)
    print("outcome:", bundle["outcome"])
    if args.out:
        run_dir = write_bundle(bundle, args.out)
        print("bundle written to:", run_dir)
    return 0 if bundle["outcome"] == "designed" else 1


def _cmd_run_frame(args) -> int:
    """run-frame handler: run one frame from a config, print the
    outcome, and optionally write the bundle."""
    frame = _load(args.frame)
    try:
        built = _built_from_config(args)
        retrieval_first = bool(built.get("retrieval_first"))
        if getattr(args, "retrieve", False):
            entries = retrieve_evidence(frame)
            ot_entries = evidence_for_frame(frame)
            frame["evidence"] = entries + ot_entries
            retrieval_first = True
            print("retrieved evidence:", len(entries),
                  "sources from Europe PMC,", len(ot_entries),
                  "association from Open Targets")
        tracker = run_budget_tracker(built)
        bundle = run_frame(frame, built["providers"],
                           judge_provider=built["judge"],
                           swap_judge_provider=built.get("judge_swap"),
                           mode=built.get("mode"),
                           budget_tracker=tracker,
                           resolver=resolver_from_config(built),
                           quote_checker=quote_checker_from_config(built),
                           entailment_checker=entailment_checker_from_config(built, tracker),
                           contradiction_checker=contradiction_checker_from_config(built, tracker),
                           tournament_judge=tournament_judge_from_config(built, tracker),
                           retrieval_first=retrieval_first)
    except (ConfigError, ProviderError, BudgetExceeded, ValueError) as exc:
        print("run stopped:", exc)
        return 2
    record = bundle["record"]
    print("run:", bundle["run_id"])
    print("frame:", bundle["frame_id"])
    print("outcome:", bundle["outcome"])
    print("focus:", record["spec"].get("focus_id"))
    print("strikes:", len(record["strike_list"]))
    if args.out:
        run_dir = write_bundle(bundle, args.out)
        print("bundle written to:", run_dir)
    return 0


def _cmd_prereg_verify(args) -> int:
    """prereg-verify handler: recompute a bundle's pre-registration
    hash and check the bundle answers the declared question."""
    import json as _json
    from pathlib import Path as _Path

    from .prereg import verify_preregistration
    bundle_path = _Path(args.bundle)
    bundle = _json.loads(bundle_path.read_text(encoding="utf-8"))
    ref = bundle.get("preregistration")
    if not ref:
        print("this bundle carries no pre-registration")
        return 1
    prereg_path = (bundle_path.parent.parent / "preregistrations"
                   / ref["file"])
    if not prereg_path.exists():
        print("pre-registration file not found:", prereg_path)
        return 1
    record = _json.loads(prereg_path.read_text(encoding="utf-8"))
    problems = []
    if not verify_preregistration(record):
        problems.append("the pre-registration record's hash does not "
                        "recompute: the record was altered after writing")
    if record.get("sha256") != ref.get("sha256"):
        problems.append("the bundle's hash does not match the record's")
    target = bundle.get("target") or {}
    declared = record.get("target") or {}
    for field in ("name", "kind", "target", "disease"):
        if target.get(field) != declared.get(field):
            problems.append("bundle target " + field + " differs from "
                            "the declared " + field)
    if bundle.get("mode") != record.get("mode"):
        problems.append("bundle mode differs from the declared mode")
    if problems:
        for problem in problems:
            print("MISMATCH:", problem)
        return 1
    print("pre-registration verified: declared", record.get("created_utc"),
          "| target", declared.get("name"), "| mode", record.get("mode"),
          "| hash", str(ref.get("sha256"))[:16])
    return 0


def _cmd_gui(args) -> int:
    """gui handler: serve the MADD Console web interface locally
    until interrupted."""
    from .gui import serve
    serve(host=args.host, port=args.port, runs_dir=args.runs_dir)
    return 0


def _cmd_gate0_new_case(args) -> int:
    """gate0-new-case handler: scaffold the three files for a new
    Gate 0 case. The dataset will fail validation until the case is
    completed with verified material; that is the point."""
    from .gate0 import scaffold_case
    try:
        created = scaffold_case(args.case_id, args.gate0_dir)
    except FileExistsError as exc:
        print(exc)
        return 2
    for path in created:
        print("created:", path)
    print("The dataset will FAIL gate0-validate until every TODO is replaced "
          "with primary-source-verified material and ledger rows are added.")
    return 0


def _cmd_compare_runs(args) -> int:
    """compare-runs handler: diff two Gate 0 run bundles (bundle.json
    paths or run folders) and print what changed."""
    from .compare import (compare_bundles, comparison_to_text,
                          load_bundle_anywhere)
    try:
        a = load_bundle_anywhere(args.bundle_a)
        b = load_bundle_anywhere(args.bundle_b)
    except Exception as exc:
        print("could not load a bundle:", exc)
        return 2
    if a.get("kind") != "gate0_run" or b.get("kind") != "gate0_run":
        print("compare-runs works on Gate 0 run bundles")
        return 2
    print(comparison_to_text(compare_bundles(a, b)))
    return 0


def _cmd_report_html(args) -> int:
    """report-html handler: print the styled HTML report for a bundle
    file (run bundles are also written with report.html at run time)."""
    bundle = _load(args.file)
    if not isinstance(bundle, dict) or "kind" not in bundle:
        print("not a run bundle:", args.file)
        return 2
    print(bundle_to_html(bundle))
    return 0


def _cmd_report_pdf(args) -> int:
    """report-pdf handler: render a bundle's HTML report to a PDF
    file through WeasyPrint, an optional dependency. Without it the
    command says so plainly and writes nothing."""
    from .report_pdf import render_report_pdf
    bundle = _load(args.file)
    if not isinstance(bundle, dict) or "kind" not in bundle:
        print("not a run bundle:", args.file)
        return 2
    result = render_report_pdf(bundle, use=args.use)
    if result["status"] != "completed":
        print("PDF not rendered (" + result["status"] + "):",
              result.get("reason") or "")
        return 2
    Path(args.out).write_bytes(result["pdf"])
    print("PDF written to:", args.out, "(" + str(result["bytes"]) + " bytes)")
    return 0


def _cmd_calibration(args) -> int:
    """calibration handler: agreement-bucketed accuracy over one or
    more Gate 0 bundles, judged against the sealed outcomes."""
    from .calibration import calibration_report, format_calibration
    bundles = []
    for file in args.files:
        bundle = _load(file)
        if not isinstance(bundle, dict) or "case_records" not in bundle:
            print("not a Gate 0 bundle:", file)
            return 2
        bundles.append(bundle)
    report = calibration_report(bundles, gate0_dir=args.gate0_dir)
    print(format_calibration(report))
    return 0


def _cmd_transcript(args) -> int:
    """transcript handler: render a debate record, or a frame run
    bundle's record, as a readable markdown transcript."""
    data = _load(args.file)
    record = data.get("record") if data.get("kind") == "frame_run" else data
    if not isinstance(record, dict) or "outcome" not in record \
            or "strike_list" not in record:
        print("not a debate record or frame run bundle:", args.file)
        return 2
    print(record_to_markdown(record))
    return 0


def _cmd_debate_mock(args) -> int:
    """debate-mock handler: run the debate over a frame with mock
    providers; exit 0 when a specification locks."""
    frame = _load(args.frame)
    providers = [MockProvider("001"), MockProvider("002")]
    judge = MockProvider("003") if args.judge else None
    record = run_debate(frame, providers, judge_provider=judge)
    print("frame:", record["frame_id"])
    print("outcome:", record["outcome"])
    print("red team round:", "yes" if record["red_team_round"] else "no")
    for row in record["ranking"]:
        print(" -", row["dossier_id"], "| focus", row["proposed_focus_id"],
              "| score", row["focus_score"], "| struck", row["struck_count"],
              "| wins", row["wins"])
    print("strikes:", len(record["strike_list"]))
    for test in record["consensus"]["results"]:
        print(" - test", test["test"], "|", "pass" if test["passed"] else "FAIL",
              "|", test["detail"])
    print("record hash:", record["record_hash"])
    if args.out:
        Path(args.out).write_text(json.dumps(record, indent=2, sort_keys=True),
                                  encoding="utf-8")
        print("record written to:", args.out)
    print("note: mock providers only; this run is plumbing, not research")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with one subcommand per operation."""
    parser = argparse.ArgumentParser(prog="madd", description="MADD command line interface")
    sub = parser.add_subparsers(dest="command", required=True)
    p1 = sub.add_parser("audit-claims"); p1.add_argument("file"); p1.set_defaults(fn=_cmd_audit_claims)
    p2 = sub.add_parser("check-tool"); p2.add_argument("tool")
    p2.add_argument("--use", default="research", choices=["research", "commercial"])
    p2.set_defaults(fn=_cmd_check_tool)
    p3 = sub.add_parser("focus-score"); p3.add_argument("file"); p3.set_defaults(fn=_cmd_focus_score)
    p4 = sub.add_parser("validate-artifact"); p4.add_argument("schema_name"); p4.add_argument("file")
    p4.set_defaults(fn=_cmd_validate_artifact)
    p5 = sub.add_parser("gate0-validate"); p5.add_argument("--gate0-dir", default=None)
    p5.set_defaults(fn=_cmd_gate0_validate)
    p6 = sub.add_parser("gate0-list"); p6.add_argument("--gate0-dir", default=None)
    p6.set_defaults(fn=_cmd_gate0_list)
    p7 = sub.add_parser("gate0-report"); p7.add_argument("predictions")
    p7.add_argument("--baseline", default=None)
    p7.add_argument("--audit-violations", type=int, default=None)
    p7.add_argument("--judge-swap-flips", type=int, default=None)
    p7.set_defaults(fn=_cmd_gate0_report)
    p8 = sub.add_parser("resolve-citations"); p8.add_argument("file")
    p8.add_argument("--check-quotes", action="store_true")
    p8.set_defaults(fn=_cmd_resolve_citations)
    p9 = sub.add_parser("debate-mock"); p9.add_argument("frame")
    p9.add_argument("--judge", action="store_true")
    p9.add_argument("--out", default=None)
    p9.set_defaults(fn=_cmd_debate_mock)
    p10 = sub.add_parser("run-gate0"); p10.add_argument("--config", required=True)
    p10.add_argument("--out", default=None)
    p10.add_argument("--gate0-dir", default=None)
    p10.add_argument("--dry-run", action="store_true")
    p10.add_argument("--jobs", type=int, default=None)
    p10.set_defaults(fn=_cmd_run_gate0)
    p11 = sub.add_parser("run-frame"); p11.add_argument("frame")
    p11.add_argument("--retrieve", action="store_true")
    p11.add_argument("--config", required=True)
    p11.add_argument("--out", default=None)
    p11.set_defaults(fn=_cmd_run_frame)
    p12 = sub.add_parser("providers-check"); p12.add_argument("--config", required=True)
    p12.set_defaults(fn=_cmd_providers_check)
    p13 = sub.add_parser("providers-smoke"); p13.add_argument("--config", required=True)
    p13.set_defaults(fn=_cmd_providers_smoke)
    p14 = sub.add_parser("transcript"); p14.add_argument("file")
    p14.set_defaults(fn=_cmd_transcript)
    p15 = sub.add_parser("report-html"); p15.add_argument("file")
    p15.set_defaults(fn=_cmd_report_html)
    p15b = sub.add_parser("report-pdf"); p15b.add_argument("file")
    p15b.add_argument("--out", required=True)
    p15b.add_argument("--use", default="research")
    p15b.set_defaults(fn=_cmd_report_pdf)
    p15c = sub.add_parser("calibration"); p15c.add_argument("files", nargs="+")
    p15d = sub.add_parser("prereg-verify"); p15d.add_argument("bundle")
    p15d.set_defaults(fn=_cmd_prereg_verify)
    p15c.add_argument("--gate0-dir", default=None)
    p15c.set_defaults(fn=_cmd_calibration)
    p16 = sub.add_parser("compare-runs"); p16.add_argument("bundle_a")
    p16.add_argument("bundle_b"); p16.set_defaults(fn=_cmd_compare_runs)
    p17 = sub.add_parser("gate0-new-case"); p17.add_argument("case_id")
    p17.add_argument("--gate0-dir", default=None)
    p17.set_defaults(fn=_cmd_gate0_new_case)
    p19 = sub.add_parser("design-brief"); p19.add_argument("source")
    p19.add_argument("--case", default=None)
    p19.add_argument("--constraint", action="append", default=None)
    p19.add_argument("--target", default=None)
    p19.add_argument("--disease", default=None)
    p19.set_defaults(fn=_cmd_design_brief)
    p20 = sub.add_parser("design-run"); p20.add_argument("source")
    p20.add_argument("--case", default=None)
    p20.add_argument("--constraint", action="append", default=None)
    p20.add_argument("--target", default=None)
    p20.add_argument("--disease", default=None)
    p20.add_argument("--config", default=None)
    p20.add_argument("--source-check", action="store_true")
    p20.add_argument("--retro-config", default=None)
    p20.add_argument("--out", default="runs")
    p20.add_argument("--tool", default=None)
    p20.add_argument("--use", default="research", choices=["research", "commercial"])
    p20.add_argument("--tool-input", default=None)
    p20.set_defaults(fn=_cmd_design_run)
    p21 = sub.add_parser("target-run"); p21.add_argument("--config", required=True)
    p21.add_argument("--name", required=True)
    p21.add_argument("--kind", required=True, choices=list(TARGET_KINDS))
    p21.add_argument("--target", default=None)
    p21.add_argument("--disease", default=None)
    p21.add_argument("--focus", default=None)
    p21.add_argument("--constraint", action="append", default=None)
    p21.add_argument("--no-retrieve", action="store_true")
    p21.add_argument("--no-prereg", action="store_true")
    p21.add_argument("--source-check", action="store_true")
    p21.add_argument("--out", default=None)
    p21.set_defaults(fn=_cmd_target_run)
    p18 = sub.add_parser("gui"); p18.add_argument("--port", type=int, default=8765)
    p18.add_argument("--host", default="127.0.0.1")
    p18.add_argument("--runs-dir", default="runs")
    p18.set_defaults(fn=_cmd_gui)
    return parser


def main(argv=None) -> int:
    """CLI entry point: parse arguments, dispatch to the handler,
    return its exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
