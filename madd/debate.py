"""Debate engine: docs/DEBATE_PROTOCOL.md, steps 1 to 7, as code.

The protocol existed as a design document only. This module runs it
against any objects satisfying the Provider interface in
madd/providers.py (today that is the deterministic mock provider; real
providers sit behind the same interface once the Phase 1 roster is
chosen). The engine is deterministic wherever the protocol is
mechanical: the evidence call, the pairwise ranking, the evolution
merge, and the consensus tests are code, not agent judgement. Free-text
argument between live agents is a provider concern; what the engine
guarantees is the auditable structure around it: nothing enters a
locked specification without surviving the claim audit, and every run
ends in a frozen, hashed record.

What the engine does not do: it does not make agents argue in free
text. Cross-examination here is the structured objection record the
protocol's outcome depends on (who objected, to which dossier, over
which surviving claims). The argumentative prose of a live debate
belongs to the providers, when real ones are connected.

Steps, matching the protocol:
1. Blinded dossiers: each provider researches the frame alone.
2. Evidence call: every claim is audited; failures are struck and
   listed, and struck claims take no further part.
3. Cross-examination: recorded as structured objections between
   dossiers with different focuses. When every dossier agrees on the
   focus, the protocol's instant-agreement rule fires instead: a
   red-team round is recorded against the agreed focus.
4. Pairwise ranking on the pre-declared rubric: focus score from
   audited surviving claims, then fewer struck claims. Prose quality
   is not a rubric item and is never scored.
5. Evolution round: the top dossier is revised once, merging surviving
   claims from all dossiers (original claim identifiers kept), and the
   merged specification is what the consensus tests judge.
6. Consensus tests from madd/consensus.py, including judge swap when a
   judge provider is supplied.
7. Record: outcome (locked or no_go), the specification, the strike
   list, the ranking, the transcript, and the dissent log, frozen and
   hashed together with a run manifest.

An optional BudgetTracker (madd/budget.py) caps the run: provider calls
that would cross the cap are never made.
"""
from __future__ import annotations

import copy

from .artifacts import (build_manifest, canonical_hash, canonical_json,
                        freeze_artifact, prompt_hash)
from .budget import BudgetExceeded, BudgetTracker
from .citation_auditor import audit_citations
from .claims import validate_claim
from .consensus import run_consensus_tests
from .focus import focus_score


def audit_dossier(dossier: dict, resolver=None) -> dict:
    """Evidence call for one dossier: split claims into surviving/struck.

    A claim is struck when the claim ledger rules fail it (no source,
    model-opinion source, tier 0 load-bearing, already struck) or when
    its citation fails the offline auditor (bad identifier format, or a
    quote_checked claim carrying no quote). Struck claims are returned
    with their reason codes and take no further part in the debate.

    resolver, when given, is a callable(identifier, identifier_type)
    returning a live resolution status (see madd/resolve.py). A claim
    whose identifier the registry reports as not_found is struck with
    reason citation_not_found_live. Any other status (resolved,
    lookup_error, format problems already handled above) never strikes
    on its own: a registry that cannot be reached proves nothing about
    the claim.
    """
    claims = dossier.get("claims") if isinstance(dossier, dict) else None
    if not isinstance(claims, list):
        claims = []
    citation_entries = {}
    for entry in audit_citations({"claims": claims})["entries"]:
        citation_entries[entry["claim_id"]] = entry
    surviving = []
    struck = []
    for claim in claims:
        if not isinstance(claim, dict):
            struck.append({"claim_id": "<not an object>", "reasons": ["claim_not_object"]})
            continue
        reasons = [e["code"] for e in validate_claim(claim)]
        entry = citation_entries.get(claim.get("claim_id", "<missing claim_id>"))
        if entry is not None:
            if not entry["format"]["ok"]:
                reasons.append("citation_" + entry["format"]["code"])
            for problem in entry["problems"]:
                reasons.append(problem["code"])
        if resolver is not None and not reasons:
            status = resolver(claim.get("source_identifier"),
                              claim.get("identifier_type"))
            if status == "not_found":
                reasons.append("citation_not_found_live")
        if reasons:
            struck.append({"claim_id": claim.get("claim_id", "<missing claim_id>"),
                           "reasons": sorted(set(reasons))})
        else:
            surviving.append(copy.deepcopy(claim))
    return {"dossier_id": dossier.get("dossier_id"),
            "agent_id": dossier.get("agent_id"),
            "proposed_focus_id": dossier.get("proposed_focus_id"),
            "direction": dossier.get("direction"),
            "surviving_claims": surviving, "struck": struck}


def _rank_key(audited: dict) -> tuple:
    score = focus_score({"claims": audited["surviving_claims"]})["score"]
    return (score, -len(audited["struck"]))


def rank_dossiers(audited_dossiers: list) -> list:
    """Pairwise ranking on the protocol rubric. Returns ranked summaries.

    Each dossier scores a win against every dossier it beats on
    (focus score, then fewer struck claims) and half a win on a tie.
    Sorting is by wins, then rubric key, then dossier_id, so the result
    is fully deterministic for the same inputs.
    """
    keys = {a["dossier_id"]: _rank_key(a) for a in audited_dossiers}
    summaries = []
    for a in audited_dossiers:
        wins = 0.0
        for b in audited_dossiers:
            if b["dossier_id"] == a["dossier_id"]:
                continue
            if keys[a["dossier_id"]] > keys[b["dossier_id"]]:
                wins += 1.0
            elif keys[a["dossier_id"]] == keys[b["dossier_id"]]:
                wins += 0.5
        summaries.append({"dossier_id": a["dossier_id"], "agent_id": a["agent_id"],
                          "proposed_focus_id": a["proposed_focus_id"],
                          "focus_score": keys[a["dossier_id"]][0],
                          "struck_count": len(a["struck"]), "wins": wins})
    summaries.sort(key=lambda s: (-s["wins"], -s["focus_score"], s["struck_count"],
                                  str(s["dossier_id"])))
    return summaries


def _cross_examination(audited_dossiers: list, ranking: list) -> tuple:
    """Structured cross-examination record (protocol step 3).

    Focus disagreement produces an objection from each dossier against
    each dossier arguing a different focus, naming the rival's
    surviving load-bearing claims as the ground that must be answered.
    Instant agreement triggers the red-team rule instead.
    """
    focuses = {a["proposed_focus_id"] for a in audited_dossiers}
    transcript = []
    if len(focuses) == 1:
        top_id = ranking[0]["dossier_id"]
        for a in audited_dossiers:
            transcript.append({
                "kind": "red_team_assigned_attack",
                "objector_agent_id": a["agent_id"],
                "target_dossier_id": top_id,
                "agreed_focus_id": next(iter(focuses)),
                "note": "instant agreement: agent assigned to argue against the "
                        "agreed focus using surviving claims only",
                "claim_ids": [c.get("claim_id") for c in a["surviving_claims"]
                              if c.get("load_bearing")],
            })
        return transcript, True
    for a in audited_dossiers:
        for b in audited_dossiers:
            if a["dossier_id"] == b["dossier_id"]:
                continue
            if a["proposed_focus_id"] == b["proposed_focus_id"]:
                continue
            transcript.append({
                "kind": "focus_disagreement",
                "objector_agent_id": a["agent_id"],
                "objector_focus_id": a["proposed_focus_id"],
                "target_dossier_id": b["dossier_id"],
                "target_agent_id": b["agent_id"],
                "target_focus_id": b["proposed_focus_id"],
                "claim_ids": [c.get("claim_id") for c in b["surviving_claims"]
                              if c.get("load_bearing")],
            })
    return transcript, False


def _evolve_spec(frame: dict, audited_dossiers: list, ranking: list,
                 dissent_log: list, dissent_none_reason) -> tuple:
    """Evolution round (step 5): merge surviving claims, ranked order first."""
    by_id = {a["dossier_id"]: a for a in audited_dossiers}
    top = by_id[ranking[0]["dossier_id"]]
    merged = []
    seen = set()
    duplicates = 0
    contributors = []
    for summary in ranking:
        source = by_id[summary["dossier_id"]]
        contributed = False
        for claim in source["surviving_claims"]:
            cid = claim.get("claim_id")
            if cid in seen:
                duplicates += 1
                continue
            seen.add(cid)
            merged.append(copy.deepcopy(claim))
            contributed = True
        if contributed:
            contributors.append(source["dossier_id"])
    spec = {
        "artifact_type": "consensus_spec",
        "schema_version": "0.1.0",
        "spec_id": "SPEC-" + str(frame.get("frame_id", "FRAME")),
        "frame_id": frame.get("frame_id"),
        "focus_id": top["proposed_focus_id"],
        "direction": top.get("direction"),
        "claims": merged,
        "dissent_log": dissent_log,
        "outcome": "no_go",
    }
    if dissent_none_reason is not None:
        spec["dissent_none_reason"] = dissent_none_reason
    evolution = {"base_dossier_id": top["dossier_id"],
                 "contributing_dossiers": contributors,
                 "claims_merged": len(merged),
                 "duplicate_claim_ids_skipped": duplicates}
    return spec, evolution


def run_debate(frame: dict, providers: list, judge_provider=None,
               budget: dict | None = None, budget_tracker=None,
               resolver=None) -> dict:
    """Run the full debate protocol over a frame. Returns the run record.

    providers: at least two Provider objects (see madd/providers.py).
    judge_provider: optional third provider whose dossier, produced from
    the same frame, supplies the judge-swap stability comparison.
    budget: optional budget dict for madd.budget.BudgetTracker.
    budget_tracker: optional pre-built BudgetTracker, shared across
    calls by a runner so the cap applies to a whole multi-case run
    rather than to each debate separately. Takes precedence over
    budget when both are given.
    resolver: optional live citation resolver, callable(identifier,
    identifier_type) returning a status string; see audit_dossier.
    """
    if not isinstance(frame, dict) or not frame.get("frame_id"):
        raise ValueError("frame must be a dict with a frame_id")
    providers = list(providers)
    if len(providers) < 2:
        raise ValueError("the debate protocol needs at least two research providers")
    tracker = budget_tracker if budget_tracker is not None else (
        BudgetTracker(budget) if budget is not None else None)

    def research(provider):
        cost = float(getattr(provider, "cost_per_call_usd", 0.0) or 0.0)
        if tracker is not None and tracker.would_exceed(cost):
            raise BudgetExceeded("budget cap reached before a provider call; run stopped")
        dossier = provider.research(copy.deepcopy(frame))
        if not isinstance(dossier, dict):
            raise ValueError("provider " + str(getattr(provider, "name", "?"))
                             + " returned a non-dict dossier")
        if tracker is not None:
            tracker.record(cost, note="research:" + str(getattr(provider, "name", "?")))
        return dossier

    # Step 1: blinded dossiers. Providers receive only the frame.
    dossiers = [research(p) for p in providers]
    dossier_ids = [d.get("dossier_id") for d in dossiers]
    if len(set(dossier_ids)) != len(dossier_ids):
        raise ValueError("two providers returned the same dossier_id ("
                         + ", ".join(str(x) for x in dossier_ids)
                         + "); dossier identifiers must be unique within a run, "
                           "or the ranking and the record would silently merge them")
    # Step 2: evidence call.
    audited = [audit_dossier(d, resolver=resolver) for d in dossiers]
    strike_list = [{"dossier_id": a["dossier_id"], "claim_id": s["claim_id"],
                    "reasons": s["reasons"]}
                   for a in audited for s in a["struck"]]
    # Ranking (protocol step 4) is computed before the cross-examination
    # record (step 3) is written because the red-team target and the
    # evolution base are both the top-ranked dossier. The two steps use
    # disjoint inputs (audited claims; dossier focuses), so the order
    # changes nothing in either result.
    ranking = rank_dossiers(audited)
    # Step 3: cross-examination record.
    transcript, red_team = _cross_examination(audited, ranking)
    dissent_log = [{"objector_agent_id": t["objector_agent_id"],
                    "target_dossier_id": t["target_dossier_id"],
                    "objection": "focus disagreement: objector proposes "
                                 + str(t.get("objector_focus_id"))
                                 + ", target proposes " + str(t.get("target_focus_id")),
                    "claim_ids": t["claim_ids"]}
                   for t in transcript if t["kind"] == "focus_disagreement"]
    dissent_none_reason = None
    if not dissent_log:
        dissent_none_reason = ("no unresolved objections: every dossier proposed "
                               "the same focus, and the instant-agreement red-team "
                               "round was run and recorded")
    # Step 5: evolution round.
    spec, evolution = _evolve_spec(frame, audited, ranking, dissent_log,
                                   dissent_none_reason)
    # Step 6: consensus tests, with judge swap when a judge is supplied.
    swapped_spec = None
    judge_info = None
    if judge_provider is not None:
        judge_dossier = research(judge_provider)
        judge_audited = audit_dossier(judge_dossier, resolver=resolver)
        swapped_spec = dict(spec)
        swapped_spec["focus_id"] = judge_audited["proposed_focus_id"]
        judge_info = {"provider": getattr(judge_provider, "name", None),
                      "model_version": getattr(judge_provider, "model_version", None),
                      "dossier_id": judge_audited["dossier_id"],
                      "proposed_focus_id": judge_audited["proposed_focus_id"],
                      "struck": judge_audited["struck"]}
        if judge_audited["proposed_focus_id"] != spec["focus_id"]:
            spec["dissent_log"] = list(spec["dissent_log"]) + [{
                "objector_agent_id": judge_audited["agent_id"],
                "target_dossier_id": ranking[0]["dossier_id"],
                "objection": "judge swap selected a different focus: "
                             + str(judge_audited["proposed_focus_id"]),
                "claim_ids": [],
            }]
    consensus = run_consensus_tests(dossiers, spec, swapped_spec)
    outcome = "locked" if consensus["all_passed"] else "no_go"
    spec["outcome"] = outcome

    # Step 7: frozen record.
    frame_prompt_hash = prompt_hash(canonical_json(frame))
    calls = [{"role": "research",
              "provider": getattr(p, "name", None),
              "model_version": getattr(p, "model_version", None),
              "agent_id": a["agent_id"], "dossier_id": a["dossier_id"],
              "prompt_hash": frame_prompt_hash}
             for p, a in zip(providers, audited)]
    if judge_info is not None:
        calls.append({"role": "judge",
                      "provider": judge_info["provider"],
                      "model_version": judge_info["model_version"],
                      "agent_id": None, "dossier_id": judge_info["dossier_id"],
                      "prompt_hash": frame_prompt_hash})
    manifest = build_manifest(
        model_name=", ".join(str(getattr(p, "name", "?")) for p in providers),
        model_version=", ".join(str(getattr(p, "model_version", "?")) for p in providers),
        prompt_text=canonical_json(frame),
        budget=tracker.to_dict() if tracker is not None else {},
        declared_use="research")
    manifest["calls"] = calls
    record = {
        "artifact_type": "debate_record",
        "schema_version": "0.1.0",
        "frame_id": frame.get("frame_id"),
        "round_cap": frame.get("round_cap"),
        "providers": [{"name": getattr(p, "name", None),
                       "model_version": getattr(p, "model_version", None),
                       "agent_id": a["agent_id"], "dossier_id": a["dossier_id"]}
                      for p, a in zip(providers, audited)],
        "strike_list": strike_list,
        "ranking": ranking,
        "rubric": {"applied": ["tier-weighted audited focus score",
                               "struck claim count"],
                   "not_applied": ["frame coverage: named in the protocol "
                                   "rubric but not mechanically defined, "
                                   "so it is not scored"]},
        "cross_examination": transcript,
        "red_team_round": red_team,
        "evolution": evolution,
        "judge_swap": judge_info,
        "consensus": consensus,
        "spec": spec,
        "outcome": outcome,
        "manifest": manifest,
        "budget": tracker.to_dict() if tracker is not None else None,
    }
    record["frozen_record"] = freeze_artifact(record)
    record["record_hash"] = canonical_hash(record["frozen_record"]["artifact"])
    return record
