"""Experiment tree search: best-first expansion over design briefs.

The design stage (madd/design.py) runs one designer pass over one
brief and ranks what comes back. This module runs the stage as an
explicit search, in the shape the AI Scientist-v2 design reference
(docs/DESIGN-REFERENCES.md) names for its experiment stage,
implemented natively here under MADD's own rules: candidate paths
are nodes in a tree, a manager expands the most promising open
node first, and failure handling is stated as numbers in the
search config (a debug depth bound and a debug probability)
rather than left to agent judgment. No code is taken from that
project; the pattern is re-implemented against this pipeline's
own machinery.

Shape of the search:

- The root node carries the brief built from the locked spec,
  exactly as run_design builds it. Expanding a node is one
  designer pass over the node's brief, followed by the design
  stage's own enrichment (RDKit, then ADMET-AI, under the same
  flags) and its own audit and ranking (audit_candidate,
  rank_candidates). The search adds no second scoring rule: a
  node's score is its best ranked candidate's standing under the
  fixed ranking rule, audited load-bearing claim count first,
  then fewer unknown constraints.
- Children are seeded from a node's ranked candidates, up to
  num_seeds of them. A seed child's brief is the parent brief
  plus a tree_context block naming the seed candidate, its
  audited standing, and the instruction to develop that line
  further: vary it, strengthen its audited support, resolve its
  unknown constraints. The brief is data to the designer, under
  the same prompt discipline as every brief.
- A node whose expansion ranks nothing (every candidate
  excluded, or the designer returned none) is a failed node. The
  manager may open one debug child for it: a brief carrying the
  recorded exclusion reasons and the instruction to repair them.
  The attempt is bounded two ways, both from the config: the
  child's debug_depth, the count of consecutive failed ancestors
  it repairs, must stay within max_debug_depth, and the attempt
  is made with probability debug_prob, drawn from the run's
  seeded generator, so a recorded seed reproduces a recorded
  tree. A healthy expansion resets the lineage's debug_depth to
  zero: the bound counts consecutive failures, not lifetime ones.
- The search runs at most max_steps expansions, one at a time.
  Sequential expansion keeps the run's budget accounting and its
  audit trail in expansion order; num_seeds sets the breadth.
  Expansion stops early when the frontier empties, or when a
  ranked candidate reaches goal_audited_claims, when a goal is
  set in the config.

Candidate ids are scoped to their node (the node id prefixes the
designer's id, and the designer's own id is kept as
tree_origin_id), because a panel designer numbers its candidates
per call while the tree's audits and records are keyed by
candidate id across the whole tree.

Standing, stated plainly: the tree is a search over the design
stage's own outputs. Its gate mirrors the design gate (a locked
spec, at least one ranked candidate, at least one ranked
candidate that is real rather than synthetic) and adds two
self-checks of the manager: the step budget and the debug bound
were respected. A ranked candidate in the tree carries exactly
the standing it would carry in a single design run: audited
support, computed properties, and nothing more.
"""
from __future__ import annotations

import copy
import random
import re
import uuid
from datetime import datetime, timezone

from . import design_admet
from . import design_rdkit
from .artifacts import freeze_artifact
from .design import MockDesigner, audit_candidate, build_brief, rank_candidates


DEFAULT_CONFIG = {
    "max_steps": 6,
    "num_seeds": 3,
    "max_debug_depth": 2,
    "debug_prob": 0.5,
    "seed": 0,
    "goal_audited_claims": None,
}


def _slug(text: str) -> str:
    """Filesystem and id safe slug for ids built from spec ids."""
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "spec"


def validate_tree_config(config: dict = None) -> dict:
    """Normalize a tree search config against the defaults.

    Raises ValueError on an unknown key or an out-of-range value:
    the search's failure handling is stated as these numbers, so a
    config the manager cannot honour is refused up front rather
    than approximated mid-run.
    """
    cfg = dict(DEFAULT_CONFIG)
    if config:
        unknown = sorted(set(config) - set(DEFAULT_CONFIG))
        if unknown:
            raise ValueError("unknown tree config keys: "
                             + ", ".join(unknown))
        cfg.update(config)
    for key in ("max_steps", "num_seeds"):
        if not isinstance(cfg[key], int) or isinstance(cfg[key], bool) \
                or cfg[key] < 1:
            raise ValueError("tree config " + key + " must be an integer >= 1")
    if not isinstance(cfg["max_debug_depth"], int) \
            or isinstance(cfg["max_debug_depth"], bool) \
            or cfg["max_debug_depth"] < 0:
        raise ValueError("tree config max_debug_depth must be an integer >= 0")
    prob = cfg["debug_prob"]
    if not isinstance(prob, (int, float)) or isinstance(prob, bool) \
            or not 0.0 <= float(prob) <= 1.0:
        raise ValueError("tree config debug_prob must be a number in [0, 1]")
    cfg["debug_prob"] = float(prob)
    if not isinstance(cfg["seed"], int) or isinstance(cfg["seed"], bool):
        raise ValueError("tree config seed must be an integer")
    goal = cfg["goal_audited_claims"]
    if goal is not None and (not isinstance(goal, int)
                             or isinstance(goal, bool) or goal < 1):
        raise ValueError("tree config goal_audited_claims must be None "
                         "or an integer >= 1")
    return cfg


def audit_score(audit: dict) -> list:
    """One candidate audit as a best-first score: audited
    load-bearing claims descending, unknown constraints ascending,
    in the fixed ranking rule's own order. Stored as a list so the
    tree record stays JSON-shaped."""
    return [int(audit.get("audited_load_bearing", 0)),
            -int(audit.get("unknown_constraints", 0))]


def _child_brief(parent_brief: dict, node_id: str, context: dict) -> dict:
    """A child node's brief: the parent brief plus its tree_context.

    The brief id gains the node suffix so designer candidate ids
    derived from it stay unique per node even before the tree's
    own id scoping. The instruction joins the question text, and
    the full context rides as data in the brief, where the design
    contract already treats brief content as data.
    """
    brief = copy.deepcopy(parent_brief)
    brief["brief_id"] = (parent_brief["brief_id"] + "-"
                         + node_id.replace("node-", "x"))
    brief["tree_context"] = context
    brief["question"] = (parent_brief.get("question", "") + " "
                         + context["instruction"]).strip()
    return brief


def run_experiment_tree(spec: dict, source: str, designer=None,
                        config: dict = None,
                        design_constraints: tuple = (),
                        target: str = None, disease: str = None,
                        use: str = "research", rdkit: bool = True,
                        admet: bool = True,
                        budget_tracker=None, on_event=None) -> dict:
    """Run the design stage as a best-first tree search and freeze
    the tree record.

    The gate passes only when the brief came from a locked spec
    (which build_brief enforces), at least one node ranked a
    candidate, at least one ranked candidate is real (not a
    synthetic mock or fixture), and the manager's own books are
    clean: no more expansions than max_steps, no debug lineage
    deeper than max_debug_depth. A mock-only tree therefore fails
    its gate while still recording the full search: the pipeline
    exercised is not a design result.
    """
    cfg = validate_tree_config(config)
    rng = random.Random(cfg["seed"])
    root_brief = build_brief(spec, source, design_constraints,
                             target=target, disease=disease)
    designer = designer or MockDesigner()
    tree_id = ("tree-" + _slug(spec.get("spec_id", "spec"))
               + "-" + uuid.uuid4().hex[:8])
    if on_event is not None:
        on_event({"event": "tree_started", "tree_id": tree_id,
                  "spec_id": spec.get("spec_id")})

    nodes = []
    by_candidate = {}

    def new_node(parent, kind, brief, priority, debug_depth,
                 seed_candidate_id=None):
        """Append one node record in creation order and return it.

        Ids are sequential (node-0001, node-0002, ...) so a node's
        position in the record is its creation order, which the
        manager's earliest-created tie-break relies on.
        """
        seq = len(nodes) + 1
        node = {
            "node_id": "node-%04d" % seq,
            "seq": seq,
            "parent_id": parent["node_id"] if parent else None,
            "kind": kind,
            "depth": (parent["depth"] + 1) if parent else 0,
            "debug_depth": debug_depth,
            "seed_candidate_id": seed_candidate_id,
            "brief": brief,
            "priority": list(priority),
            "status": "pending",
            "expansion_order": None,
            "candidates": [],
            "audits": [],
            "ranking": None,
            "score": None,
            "tool_runs": [],
        }
        nodes.append(node)
        return node

    root = new_node(None, "root", root_brief, [0, 0], 0)
    expansions = 0
    best = None
    stop_reason = None

    def expand(node):
        """One expansion: a designer pass, enrichment, audit, ranking.

        Mirrors run_design's ordering exactly, so a candidate's
        audit in the tree is the audit it would receive in a single
        design run. Budget exhaustion from the designer propagates:
        it is the run's hard stop, not a node failure.
        """
        node["expansion_order"] = expansions + 1
        raw = designer.design(copy.deepcopy(node["brief"]))
        if not isinstance(raw, list):
            raw = []
        candidates = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            cand = copy.deepcopy(item)
            origin = cand.get("candidate_id")
            cand["tree_origin_id"] = origin
            cand["candidate_id"] = node["node_id"] + "-" + str(origin)
            cand["tree_node_id"] = node["node_id"]
            candidates.append(cand)
        ids = [c["candidate_id"] for c in candidates]
        if len(set(ids)) != len(ids):
            raise ValueError(
                "duplicate candidate_id in one tree expansion at "
                + node["node_id"] + ": " + ", ".join(
                    str(x) for x in ids if ids.count(x) > 1)
                + "; audits and ranking are keyed by candidate_id, "
                  "so duplicates would silently merge two candidates")
        tool_runs = []
        if rdkit:
            tool_runs.append(
                design_rdkit.enrich_candidates(candidates, use=use))
        if admet:
            tool_runs.append(
                design_admet.enrich_candidates(candidates, use=use))
        audits = [audit_candidate(c) for c in candidates]
        ranking = rank_candidates(candidates, audits)
        node["candidates"] = candidates
        node["audits"] = audits
        node["ranking"] = ranking
        node["tool_runs"] = tool_runs
        for cand in candidates:
            by_candidate[cand["candidate_id"]] = cand
        audit_by_id = {a["candidate_id"]: a for a in audits}
        if ranking["ranked"]:
            node["status"] = "expanded"
            top = audit_by_id[ranking["ranked"][0]]
            node["score"] = audit_score(top)
        else:
            node["status"] = "failed"
        if on_event is not None:
            on_event({"event": "node_expanded",
                      "node_id": node["node_id"],
                      "ranked": len(ranking["ranked"]),
                      "excluded": len(ranking["excluded"])})
        return audit_by_id

    while True:
        pending = [n for n in nodes if n["status"] == "pending"]
        if not pending:
            stop_reason = "frontier_exhausted"
            break
        if expansions >= cfg["max_steps"]:
            stop_reason = "steps_exhausted"
            break
        # Best-first: highest priority, earliest created on a tie.
        node = max(pending, key=lambda n: (n["priority"][0],
                                           n["priority"][1], -n["seq"]))
        audit_by_id = expand(node)
        expansions += 1
        ranking = node["ranking"]
        if ranking["ranked"]:
            for cid in ranking["ranked"]:
                score = audit_score(audit_by_id[cid])
                if best is None or score > best["score"]:
                    best = {"candidate_id": cid,
                            "node_id": node["node_id"],
                            "score": score,
                            "audit": audit_by_id[cid]}
            goal = cfg["goal_audited_claims"]
            if goal is not None and best["score"][0] >= goal:
                stop_reason = "goal_reached"
                break
            cand_by_id = {c["candidate_id"]: c
                          for c in node["candidates"]}
            for cid in ranking["ranked"][:cfg["num_seeds"]]:
                cand = cand_by_id[cid]
                audit = audit_by_id[cid]
                context = {
                    "kind": "seed",
                    "parent_node_id": node["node_id"],
                    "seed_candidate_id": cid,
                    "seed_candidate": {
                        "candidate_id": cid,
                        "modality": cand.get("modality"),
                        "description": cand.get("description"),
                        "structure": cand.get("structure"),
                    },
                    "seed_audit": {
                        "audited_load_bearing":
                            audit.get("audited_load_bearing", 0),
                        "unknown_constraints":
                            audit.get("unknown_constraints", 0),
                    },
                    "instruction": (
                        "Develop the seed candidate " + str(cid)
                        + " further: keep its line of work, propose "
                          "candidates that strengthen its audited "
                          "support, and resolve its unknown "
                          "constraints (" + str(
                              audit.get("unknown_constraints", 0))
                        + " open)."),
                }
                child_seq = len(nodes) + 1
                new_node(node, "seed",
                         _child_brief(node["brief"],
                                      "node-%04d" % child_seq, context),
                         audit_score(audit), 0, seed_candidate_id=cid)
        else:
            # Failed expansion: one bounded debug attempt, made
            # with the configured probability. The draw happens
            # only when the depth bound allows an attempt, so the
            # recorded seed's draw sequence is a function of the
            # tree's shape alone.
            if node["debug_depth"] < cfg["max_debug_depth"] \
                    and rng.random() < cfg["debug_prob"]:
                reasons = []
                for entry in ranking["excluded"]:
                    reasons.extend(entry.get("reasons") or [])
                if not reasons:
                    reasons = ["the designer returned no candidates "
                               "for this brief"]
                if node["audits"]:
                    priority = max(audit_score(a)
                                   for a in node["audits"])
                else:
                    priority = [0, 0]
                context = {
                    "kind": "debug",
                    "parent_node_id": node["node_id"],
                    "debug_depth": node["debug_depth"] + 1,
                    "exclusion_reasons": reasons,
                    "instruction": (
                        "The previous expansion on this line ranked "
                        "no candidates. Repair the recorded failures "
                        "and propose candidates that pass audit: "
                        + "; ".join(reasons)),
                }
                child_seq = len(nodes) + 1
                new_node(node, "debug",
                         _child_brief(node["brief"],
                                      "node-%04d" % child_seq, context),
                         priority, node["debug_depth"] + 1)

    ranked_total = sum(len(n["ranking"]["ranked"]) for n in nodes
                       if n["ranking"])
    real_best = best is not None and not (
        by_candidate.get(best["candidate_id"]) or {}).get("_synthetic")
    max_debug_seen = max((n["debug_depth"] for n in nodes), default=0)
    checks = [
        {"name": "spec_locked", "status": "pass",
         "detail": "brief built from locked spec "
         + str(spec.get("spec_id"))},
        {"name": "candidates_ranked",
         "status": "pass" if ranked_total else "fail",
         "detail": str(ranked_total) + " ranked across "
         + str(expansions) + " expansion(s), best in "
         + (best["node_id"] if best else "no node")},
        {"name": "real_candidates_ranked",
         "status": "pass" if real_best else "fail",
         "detail": ("best ranked candidate "
                    + str(best["candidate_id"]) + " is not synthetic")
         if real_best else ("no real candidate was ranked: every "
                            "ranked candidate is synthetic (the mock "
                            "designer or a labelled fixture), so the "
                            "tree exercised the pipeline without "
                            "producing a design result")},
        {"name": "steps_within_budget",
         "status": "pass" if expansions <= cfg["max_steps"] else "fail",
         "detail": str(expansions) + " expansion(s) of "
         + str(cfg["max_steps"]) + " allowed"},
        {"name": "debug_depth_within_bound",
         "status": "pass"
         if max_debug_seen <= cfg["max_debug_depth"] else "fail",
         "detail": "deepest debug lineage " + str(max_debug_seen)
         + " of " + str(cfg["max_debug_depth"]) + " allowed"},
    ]
    result = "pass" if all(c["status"] == "pass" for c in checks) else "fail"
    if on_event is not None:
        on_event({"event": "tree_gate_evaluated", "result": result})
    bundle = {
        "kind": "experiment_tree",
        "tree_id": tree_id,
        "run_id": tree_id,
        "outcome": result,
        "stop_reason": stop_reason,
        "created_utc": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "designer": getattr(designer, "name", "unknown"),
        "config": cfg,
        "brief": root_brief,
        "nodes": nodes,
        "expansions": expansions,
        "best": best,
        "designer_notes": list(getattr(designer, "notes", []) or []),
        "gate_report": {
            "artifact_type": "gate_report",
            "schema_version": "0.1.0",
            "gate_id": tree_id,
            "gate_name": "phase2-experiment-tree",
            "subject_id": spec.get("spec_id"),
            "result": result,
            "checks": checks,
        },
    }
    if budget_tracker is not None:
        bundle["budget"] = budget_tracker.to_dict()
    bundle["frozen_bundle"] = freeze_artifact(
        {k: v for k, v in bundle.items() if k != "frozen_bundle"})
    return bundle
