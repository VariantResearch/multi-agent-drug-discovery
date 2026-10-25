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
  providers-check --config <file>
  resolve-citations <file>
  run-frame <frame-file> --config <file> [--out <dir>]
  run-gate0 --config <file> [--out <dir>] [--gate0-dir <dir>]
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
from .runner import run_frame, run_gate0
from .schemas import SCHEMA_NAMES, validate_artifact
from .storage import write_bundle


def _load(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _cmd_audit_claims(args) -> int:
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
    result = check_tool(args.tool, args.use)
    print("tool:", result["tool"])
    print("use:", result["use"])
    print("license:", result["license"])
    print("status:", result["status"])
    print("allowed:", "yes" if result["allowed"] else "no")
    print("reason:", result["reason"])
    return 0 if result["allowed"] else 1


def _cmd_focus_score(args) -> int:
    doc = _load(args.file)
    result = focus_score(doc)
    print("focus score:", result["score"])
    print("audited claims:", result["audited_claim_count"], "of", result["total_claim_count"])
    print("per-tier counts:", json.dumps(result["per_tier_counts"], sort_keys=True))
    print("basis:", result["basis"])
    return 0


def _cmd_validate_artifact(args) -> int:
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
    report = validate_dataset(args.gate0_dir)
    print("cases:", report["case_count"])
    print("errors:", report["error_count"])
    for e in report["errors"]:
        print(" -", e.get("case_id", "-"), "|", e["code"], "|", e["message"])
    print("result:", "PASS" if report["ok"] else "FAIL")
    return 0 if report["ok"] else 1


def _cmd_gate0_list(args) -> int:
    for case_id in list_case_ids(args.gate0_dir):
        pack = load_input_pack(case_id, args.gate0_dir)
        print(case_id, "|", pack.get("disease", ""))
    return 0


def _cmd_gate0_report(args) -> int:
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


def _resolver_from_config(built):
    if not built["live_resolution"]:
        return None

    def resolver(identifier, identifier_type):
        return resolve_identifier(identifier, identifier_type)["status"]

    return resolver


def _built_from_config(args):
    config = load_config(args.config)
    return build_providers(config)


def _cmd_providers_check(args) -> int:
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


def _cmd_run_gate0(args) -> int:
    try:
        built = _built_from_config(args)
        bundle = run_gate0(built["providers"], judge_provider=built["judge"],
                           baseline_provider=built["baseline"],
                           budget=built["budget"], gate0_dir=args.gate0_dir,
                           resolver=_resolver_from_config(built))
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


def _cmd_debate_mock(args) -> int:
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
    p10.set_defaults(fn=_cmd_run_gate0)
    p11 = sub.add_parser("run-frame"); p11.add_argument("frame")
    p11.add_argument("--config", required=True)
    p11.add_argument("--out", default=None)
    p11.set_defaults(fn=_cmd_run_frame)
    p12 = sub.add_parser("providers-check"); p12.add_argument("--config", required=True)
    p12.set_defaults(fn=_cmd_providers_check)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
