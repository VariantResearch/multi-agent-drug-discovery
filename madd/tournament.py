"""Tournament ratings: judged pairwise comparisons between
proposal clusters, accumulated as Elo-style ratings.

The debate's own ranking is mechanical (audited focus scores).
A tournament adds the judged dimension the AI co-scientist's
tournament popularized: a judge provider compares two proposal
clusters head to head, on the evidence their representatives
actually survived with, and picks the stronger proposal. Wins
and losses accumulate into Elo-style ratings (start 1500,
K = 32) over a round-robin of cluster representatives.

Standing of the ratings, stated plainly: ADVISORY ONLY. They are
a model's preference ordering over the proposals as argued,
recorded as their own table on the run record. They do not
move the consensus tests, the lock, the spec, or the design
gate, none of which have ever rested on preference. Their use
is to show a reader (and the meta-review, item 5) where judged
preference and the mechanical ranking agree or diverge.

Discipline, mirroring the other judged checks: matches are
played between cluster representatives only, so near-duplicate
copies get no extra matches; a judge failure or unparseable
answer records the match as unverifiable and changes no
rating; the match count is capped and the cap is recorded;
judging calls are reserved against the run budget by the
config builder.
"""
import json

TOURNAMENT_SYSTEM_PROMPT = """You are a tournament judge in an evidence-audited research system. You are shown two PROPOSALS for the same research question, each summarized by its focus, its direction, and the claims its author kept after an independent evidence audit (struck claims are not shown). Judge which proposal is stronger AS ARGUED FROM THE MATERIAL SHOWN: the specificity and grounding of its surviving claims, and how directly they support its focus and direction. Do not use outside knowledge, do not judge which proposal is true in the world, and do not reward length or confidence.

Answer with exactly one JSON object: {"winner": "a" | "b" | "tie"} and nothing else. Use "tie" when the material shown gives no real basis to prefer one."""

START_RATING = 1500.0
K_FACTOR = 32.0
MAX_MATCHES = 45
_CLAIMS_SHOWN = 5
_CLAIM_CHARS = 300


def _parse_result(text):
    """Extract the winner word from a judge's response, or None."""
    if not isinstance(text, str):
        return None
    for candidate in (text, text[text.find("{"):text.rfind("}") + 1]):
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict) and parsed.get("winner") in (
                "a", "b", "tie"):
            return parsed["winner"]
    return None


def compare_proposals(summary_a: dict, summary_b: dict, judge) -> str:
    """Judge one head-to-head. Returns "a", "b", "tie", or
    "unverifiable"; any judge failure is unverifiable, which
    plays no match and changes no rating."""
    user = ("PROPOSAL A\n" + _render(summary_a)
            + "\n\nPROPOSAL B\n" + _render(summary_b))
    try:
        answer = judge.complete(TOURNAMENT_SYSTEM_PROMPT, user)
    except Exception:
        return "unverifiable"
    return _parse_result(answer) or "unverifiable"


def _render(summary: dict) -> str:
    """Render one proposal summary as the judge sees it."""
    lines = ["focus: " + str(summary.get("focus_id")),
             "direction: " + str(summary.get("direction")),
             "cluster size: " + str(summary.get("size"))
             + " dossier(s) arguing this proposal",
             "representative focus score: "
             + str(summary.get("focus_score"))
             + ", struck claims: " + str(summary.get("struck_count")),
             "surviving load-bearing claims:"]
    for text in summary.get("claim_texts") or []:
        lines.append("- " + text)
    return "\n".join(lines)


def cluster_summary(cluster: dict, audited_by_id: dict,
                    ranking_by_id: dict) -> dict:
    """The judged payload for one cluster: its representative's
    focus, direction, audit numbers, and surviving claim texts
    (capped, so the judging prompt stays bounded)."""
    representative = audited_by_id.get(
        cluster["representative_dossier_id"]) or {}
    summary = ranking_by_id.get(
        cluster["representative_dossier_id"]) or {}
    texts = []
    for claim in representative.get("surviving_claims") or []:
        if claim.get("load_bearing") and claim.get("text"):
            texts.append(str(claim["text"])[:_CLAIM_CHARS])
        if len(texts) >= _CLAIMS_SHOWN:
            break
    return {"cluster_id": cluster["cluster_id"],
            "focus_id": cluster.get("focus_id"),
            "direction": cluster.get("direction"),
            "size": cluster.get("size"),
            "focus_score": summary.get("focus_score"),
            "struck_count": summary.get("struck_count"),
            "claim_texts": texts}


def _expected(rating_a: float, rating_b: float) -> float:
    """Elo expected score of A against B."""
    return 1.0 / (1.0 + 10.0 ** (-(rating_a - rating_b) / 400.0))


def update_elo(rating_a: float, rating_b: float, score_a: float):
    """One Elo update. score_a is 1.0 (A wins), 0.0 (B wins), or
    0.5 (tie). Returns the two new ratings, rounded to 0.1."""
    expected_a = _expected(rating_a, rating_b)
    new_a = rating_a + K_FACTOR * (score_a - expected_a)
    new_b = rating_b + K_FACTOR * ((1.0 - score_a) - (1.0 - expected_a))
    return round(new_a, 1), round(new_b, 1)


def run_tournament(clusters: list, audited_dossiers: list,
                   ranking: list, comparator,
                   max_matches: int = MAX_MATCHES) -> dict:
    """Play the round-robin between cluster representatives.

    comparator is a callable(summary_a, summary_b) returning
    "a", "b", "tie", or "unverifiable" (see compare_proposals).
    Returns {"ratings": [...], "matches": [...],
    "matches_skipped": n, "note": ...}: ratings sorted best
    first with each cluster's match record; matches in the
    order played, unverifiable ones included and marked;
    matches_skipped counts pairs the cap left unplayed."""
    audited_by_id = {a["dossier_id"]: a for a in audited_dossiers}
    ranking_by_id = {s["dossier_id"]: s for s in ranking or []}
    summaries = {c["cluster_id"]: cluster_summary(c, audited_by_id,
                                                  ranking_by_id)
                 for c in clusters}
    ratings = {c["cluster_id"]: START_RATING for c in clusters}
    record = {c["cluster_id"]: {"wins": 0, "losses": 0, "ties": 0,
                                "unverifiable": 0} for c in clusters}
    matches = []
    skipped = 0
    ids = [c["cluster_id"] for c in clusters]
    for i, id_a in enumerate(ids):
        for id_b in ids[i + 1:]:
            if len(matches) >= max_matches:
                skipped += 1
                continue
            result = comparator(summaries[id_a], summaries[id_b])
            match = {"cluster_a": id_a, "cluster_b": id_b,
                     "result": result}
            if result in ("a", "b", "tie"):
                score_a = {"a": 1.0, "b": 0.0, "tie": 0.5}[result]
                ratings[id_a], ratings[id_b] = update_elo(
                    ratings[id_a], ratings[id_b], score_a)
                if result == "a":
                    record[id_a]["wins"] += 1
                    record[id_b]["losses"] += 1
                elif result == "b":
                    record[id_b]["wins"] += 1
                    record[id_a]["losses"] += 1
                else:
                    record[id_a]["ties"] += 1
                    record[id_b]["ties"] += 1
            else:
                record[id_a]["unverifiable"] += 1
                record[id_b]["unverifiable"] += 1
            matches.append(match)
    table = [{"cluster_id": cid, "rating": ratings[cid],
              **record[cid],
              "matches": (record[cid]["wins"] + record[cid]["losses"]
                          + record[cid]["ties"]
                          + record[cid]["unverifiable"])}
             for cid in ids]
    table.sort(key=lambda row: (-row["rating"], row["cluster_id"]))
    return {"ratings": table, "matches": matches,
            "matches_skipped": skipped,
            "note": ("advisory only: judged preference over the "
                     "proposals as argued; the ratings do not move "
                     "the consensus tests, the lock, or the spec")}
