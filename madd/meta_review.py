"""Meta-review: a structured critique of a finished run.

The audit judges claims; the meta-review judges the RUN. After
a debate completes, this module first computes a set of
deterministic signals from the finished record (strike
concentration, how few distinct sources the surviving case
rests on, unresolved disputes, whether the panel was really
one proposal repeated, whether judged preference diverged
from the mechanical ranking, and which consensus tests
failed). A reviewer provider then writes findings over those
signals, choosing from a closed pattern vocabulary, so
findings are comparable across runs and the reviewer cannot
invent facts: every detail must cite the signal values it was
shown, and any finding outside the vocabulary is dropped.

Standing: advisory, like the tournament. The meta-review is
recorded on the run and changes no outcome. Its purpose is to
make a run's weaknesses legible at a glance, including the
weakness of a clean-looking run: a reviewer that finds nothing
records an empty findings list and says so, and a reviewer
that cannot answer records the review as unavailable rather
than fabricating one.
"""
import json

PATTERNS = ("strike_concentration", "single_source_dependence",
            "unresolved_disputes", "preference_divergence",
            "cluster_collapse", "thin_evidence",
            "consensus_failure", "judge_instability")
SEVERITIES = ("note", "concern", "serious")
MAX_FINDINGS = 8

META_REVIEW_SYSTEM_PROMPT = """You are a meta-reviewer in an evidence-audited research system. You are shown SIGNALS mechanically computed from one finished research run: its audit strikes, surviving claims, disputes, proposal clusters, tournament result, and consensus outcome. Write a short structured critique of the RUN's reliability, using only the signals shown. Do not invent facts, numbers, or events; every finding's detail must cite the signal values it rests on.

Patterns (use only these):
- strike_concentration: strikes concentrated on one agent or one failure reason, suggesting a weak panel member or a systematic citation habit.
- single_source_dependence: the surviving case rests on very few distinct sources.
- unresolved_disputes: judged contradictions stood at the end of the run.
- preference_divergence: the tournament's top-rated cluster differs from the mechanical ranking's top cluster.
- cluster_collapse: most of the panel argued one proposal, so apparent agreement is repetition.
- thin_evidence: few surviving load-bearing claims overall.
- consensus_failure: one or more consensus tests failed.
- judge_instability: the judge-swap changed the outcome or the record shows instability.

Answer with exactly one JSON object: {"findings": [{"pattern": one of the patterns above, "severity": "note" | "concern" | "serious", "detail": "one or two sentences citing the signal values"}], "overall": "one sentence"} and nothing else. An empty findings list is a valid, respectable answer when the signals show a clean run."""


def compute_signals(audited_dossiers: list, strike_list: list,
                    disputes: list, clusters: list, tournament,
                    ranking: list, consensus: dict, outcome,
                    red_team: bool, judge_swap: dict = None) -> dict:
    """The deterministic facts of one finished debate, computed
    from its parts. Everything the reviewer may cite comes from
    here and nowhere else."""
    surviving = [c for a in audited_dossiers
                 for c in a.get("surviving_claims") or []
                 if c.get("load_bearing")]
    sources = {(str(c.get("identifier_type")).lower(),
                str(c.get("source_identifier")))
               for c in surviving if c.get("source_identifier")}
    strikes_by_agent = {}
    for a in audited_dossiers:
        strikes_by_agent[a.get("agent_id")] = len(a.get("struck") or [])
    total_strikes = sum(strikes_by_agent.values())
    top_share = (max(strikes_by_agent.values()) / total_strikes
                 if total_strikes else 0.0)
    sizes = [c.get("size", 1) for c in clusters or []]
    dossiers = max(1, len(audited_dossiers))
    tournament_top = None
    if tournament and tournament.get("ratings"):
        tournament_top = tournament["ratings"][0]["cluster_id"]
    ranking_top = None
    if ranking:
        ranking_top = ranking[0].get("cluster_id")
    failed_tests = [r.get("test") for r in (consensus or {}).get(
        "results") or [] if not r.get("passed")
        and r.get("status") not in ("not_applied", "not_evaluable")]
    return {
        "outcome": outcome,
        "consensus_all_passed": (consensus or {}).get("all_passed"),
        "failed_consensus_tests": failed_tests,
        "red_team_triggered": bool(red_team),
        "dossiers": len(audited_dossiers),
        "surviving_load_bearing_claims": len(surviving),
        "distinct_sources_surviving": len(sources),
        "strikes_total": total_strikes,
        "strikes_by_agent": strikes_by_agent,
        "top_agent_strike_share": round(top_share, 2),
        "disputes": len(disputes or []),
        "clusters": len(clusters or []),
        "largest_cluster_share": round(max(sizes) / dossiers, 2)
        if sizes else 0.0,
        "tournament_top_cluster": tournament_top,
        "ranking_top_cluster": ranking_top,
        "preference_divergence": (tournament_top is not None
                                  and ranking_top is not None
                                  and tournament_top != ranking_top),
        "judge_swap": judge_swap,
    }


def _parse_review(text):
    """Parse a reviewer answer into validated findings, or None.
    Entries outside the pattern and severity vocabularies are
    dropped, never repaired."""
    if not isinstance(text, str):
        return None
    for candidate in (text, text[text.find("{"):text.rfind("}") + 1]):
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if not isinstance(parsed, dict) \
                or not isinstance(parsed.get("findings"), list):
            continue
        findings = []
        for entry in parsed["findings"]:
            if not isinstance(entry, dict):
                continue
            if entry.get("pattern") not in PATTERNS:
                continue
            if entry.get("severity") not in SEVERITIES:
                continue
            detail = entry.get("detail")
            if not isinstance(detail, str) or not detail.strip():
                continue
            findings.append({"pattern": entry["pattern"],
                             "severity": entry["severity"],
                             "detail": detail.strip()})
        overall = parsed.get("overall")
        return {"findings": findings[:MAX_FINDINGS],
                "overall": overall if isinstance(overall, str)
                else None}
    return None


def review_run(signals: dict, reviewer):
    """Run the meta-review over computed signals.

    reviewer is a provider-like object with complete(system,
    user). Returns {"status": "completed", "findings",
    "overall"} on a parseable answer, or {"status":
    "unavailable", "findings": [], "overall": None} on any
    failure: an unavailable review is recorded as such, never
    replaced with invented findings."""
    user = ("SIGNALS FROM THE FINISHED RUN:\n"
            + json.dumps(signals, indent=1, sort_keys=True, default=str))
    try:
        answer = reviewer.complete(META_REVIEW_SYSTEM_PROMPT, user)
    except Exception:
        return {"status": "unavailable", "findings": [],
                "overall": None}
    parsed = _parse_review(answer)
    if parsed is None:
        return {"status": "unavailable", "findings": [],
                "overall": None}
    return {"status": "completed", **parsed}
