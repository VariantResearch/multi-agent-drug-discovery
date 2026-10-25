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
  transcript <file>
  report-html <bundle-file>
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
from .config import ConfigError, build_providers, load_config
from .debate import run_debate
from .focus import focus_score
from .gate0 import (evaluate_thresholds, list_case_ids, load_input_pack,
                   score_run, validate_dataset)
from .license_registry import check_tool
from .providers import MockProvider
from .providers_http import ProviderError
from .resolve import resolve_document, resolve_identifier
from .runner import estimate_gate0_run, run_frame, run_gate0
from .schemas import SCHEMA_NAMES, validate_artifact
from .smoke import smoke_panel
from .html_report import bundle_to_html
from .storage import write_bundle
from .transcript import record_to_markdown


def _load(path: str):
    """Read and parse a JSON file argument."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


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
    identifiers against PubMed, Crossref, and ClinicalTrials.gov."""
    doc = _load(args.file)
    report = resolve_document(doc)
    for entry in report["entries"]:
        print(" -", entry["claim_id"], "|", entry["status"], "|",
              entry.get("title") or entry["detail"])
    print("counts:", json.dumps(report["status_counts"], sort_keys=True))
    all_resolved = report["claim_count"] > 0 and all(
        e["status"] == "resolved" for e in report["entries"])
    print("result:", "PASS" if all_resolved else "FAIL")
    return 0 if all_resolved else 1


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


def _resolver_from_config(built):
    """Return the evidence-call resolver when the config enables live
    resolution, else None (audits stay offline)."""
    if not built["live_resolution"]:
        return None

    def resolver(identifier, identifier_type):
        """Resolve one identifier live and return just its status string,
        the shape debate.audit_dossier expects from a resolver."""
        return resolve_identifier(identifier, identifier_type)["status"]

    return resolver


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
                                      built["baseline"], args.gate0_dir)
        print("cases:", estimate["case_count"])
        print("calls per case:", estimate["calls_per_case"])
        print("total calls:", estimate["total_calls"])
        print("estimated cost (USD):", estimate["estimated_cost_usd"])
        if not estimate["baseline_configured"]:
            print("note: no baseline configured; a real run would be refused")
        print("note:", estimate["note"])
        return 0
    try:
        bundle = run_gate0(built["providers"], judge_provider=built["judge"],
                           baseline_provider=built["baseline"],
                           budget=built["budget"], gate0_dir=args.gate0_dir,
                           resolver=_resolver_from_config(built),
                           max_workers=args.jobs or built["max_workers"],
                           on_event=_print_run_event)
    except (ConfigError, ProviderError, BudgetExceeded, ValueError) as exc:
        print("run stopped:", exc)
        return 2
    score = bundle["debate_score"]
    print("run:", bundle["run_id"])
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


def _cmd_run_frame(args) -> int:
    """run-frame handler: run one frame from a config, print the
    outcome, and optionally write the bundle."""
    frame = _load(args.frame)
    try:
        built = _built_from_config(args)
        bundle = run_frame(frame, built["providers"],
                           judge_provider=built["judge"],
                           budget=built["budget"],
                           resolver=_resolver_from_config(built))
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


def _cmd_gui(args) -> int:
    """gui handler: serve the MADD Console web interface locally
    until interrupted."""
    from .gui import serve
    serve(host=args.host, port=args.port, runs_dir=args.runs_dir,
          gate0_dir=args.gate0_dir)
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
    p16 = sub.add_parser("compare-runs"); p16.add_argument("bundle_a")
    p16.add_argument("bundle_b"); p16.set_defaults(fn=_cmd_compare_runs)
    p17 = sub.add_parser("gate0-new-case"); p17.add_argument("case_id")
    p17.add_argument("--gate0-dir", default=None)
    p17.set_defaults(fn=_cmd_gate0_new_case)
    p18 = sub.add_parser("gui"); p18.add_argument("--port", type=int, default=8765)
    p18.add_argument("--host", default="127.0.0.1")
    p18.add_argument("--runs-dir", default="runs")
    p18.add_argument("--gate0-dir", default=None)
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
