"""Command line interface.

Subcommands:
  audit-claims <file>
  check-tool <tool> --use research|commercial
  focus-score <file>
  validate-artifact <schema-name> <file>

Output is human-readable. Exit status is non-zero when a check fails.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .citation_auditor import audit_citations
from .claims import audit_claims
from .focus import focus_score
from .license_registry import check_tool
from .schemas import SCHEMA_NAMES, validate_artifact


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="madd", description="MADD Phase 0 scaffold CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    p1 = sub.add_parser("audit-claims"); p1.add_argument("file"); p1.set_defaults(fn=_cmd_audit_claims)
    p2 = sub.add_parser("check-tool"); p2.add_argument("tool")
    p2.add_argument("--use", default="research", choices=["research", "commercial"])
    p2.set_defaults(fn=_cmd_check_tool)
    p3 = sub.add_parser("focus-score"); p3.add_argument("file"); p3.set_defaults(fn=_cmd_focus_score)
    p4 = sub.add_parser("validate-artifact"); p4.add_argument("schema_name"); p4.add_argument("file")
    p4.set_defaults(fn=_cmd_validate_artifact)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
