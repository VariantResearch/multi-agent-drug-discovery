"""Tests for contradiction detection: pair prefiltering, judged
verdicts, dispute annotation, the cross-examination naming, the
consensus-spec exclusion, and the config builder. All judges are
stubs; the suite stays offline."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.config import contradiction_checker_from_config
from madd.contradictions import (candidate_pairs, check_pair,
                                 find_disputes)
from madd.debate import run_debate
from tests.test_debate import FRAME, StubProvider, dossier, good_claim


class JudgeStub:
    """A judge provider answering one fixed verdict JSON."""

    def __init__(self, verdict):
        """Store the verdict word to answer with."""
        self.verdict = verdict
        self.name = "judge-stub"
        self.model_version = "judge-stub-v1"
        self.cost_per_call_usd = 0.0
        self.calls = 0

    def complete(self, system, user):
        """Answer with the fixed verdict as JSON."""
        self.calls += 1
        return '{"verdict": "' + self.verdict + '"}'


def claim(cid, agent, text, ident="12345678"):
    """One surviving-claim-shaped dict with an agent attached."""
    return {"claim_id": cid, "agent_id": agent, "text": text,
            "load_bearing": True, "source_identifier": ident,
            "identifier_type": "pmid"}


def test_check_pair_verdicts_and_failures():
    """Verdict words map as specified; judge failures and junk
    answers are unverifiable and create nothing."""
    a = claim("c1", "a1", "the target reduces fat mass")
    b = claim("c2", "a2", "the target increases fat mass")
    assert check_pair(a, b, JudgeStub("contradicts")) == "contradicts"
    assert check_pair(a, b, JudgeStub("compatible")) == "compatible"
    assert check_pair(a, b, JudgeStub("cannot_tell")) == "unverifiable"

    class BrokenJudge:
        """A judge whose completion raises."""

        def complete(self, system, user):
            """Raise like a dead provider."""
            raise RuntimeError("down")

    assert check_pair(a, b, BrokenJudge()) == "unverifiable"
    assert check_pair(a, b, JudgeStub("maybe")) == "unverifiable"
    assert check_pair({"text": ""}, b, JudgeStub("contradicts")) \
        == "unverifiable"


def test_candidate_pairs_prefilter():
    """Same-source pairs rank first; same-agent pairs and
    no-overlap pairs are not candidates."""
    a = claim("c1", "a1", "alpha beta gamma delta epsilon")
    b = claim("c2", "a2", "alpha beta gamma delta zeta")
    same_agent = claim("c3", "a1", "alpha beta gamma delta epsilon")
    unrelated = claim("c4", "a3", "omega sigma theta kappa lambda",
                      ident="87654321")
    pairs = candidate_pairs([a, b, same_agent, unrelated])
    pair_ids = [{x["claim_id"], y["claim_id"]} for _s, x, y in pairs]
    # Cross-agent same-source pairs only: c1-c2 and c3-c2. The
    # same-agent pair (c1, c3) is excluded, and the unrelated
    # claim appears in no pair.
    assert pair_ids == [{"c1", "c2"}, {"c2", "c3"}]
    assert all(score >= 1000 for score, _x, _y in pairs)


def test_find_disputes_annotates_and_counts():
    """A judged contradiction becomes a dispute; both original
    claims are annotated; screened and judged counts are kept."""
    audited = [
        {"agent_id": "a1", "dossier_id": "D1", "surviving_claims": [
            {"claim_id": "c1", "text": "inhibiting the target reduces "
             "fat mass in mice", "load_bearing": True,
             "source_identifier": "12345678", "identifier_type": "pmid"}]},
        {"agent_id": "a2", "dossier_id": "D2", "surviving_claims": [
            {"claim_id": "c2", "text": "inhibiting the target increases "
             "fat mass in mice", "load_bearing": True,
             "source_identifier": "12345678", "identifier_type": "pmid"}]},
    ]
    out = find_disputes(audited, lambda x, y: "contradicts")
    assert len(out["disputes"]) == 1
    assert out["pairs_screened"] == 1 and out["pairs_judged"] == 1
    assert audited[0]["surviving_claims"][0]["dispute_partners"] == ["c2"]
    assert audited[1]["surviving_claims"][0]["dispute_partners"] == ["c1"]
    clean = find_disputes(audited, lambda x, y: "compatible")
    assert clean["disputes"] == []


def test_config_builder_switch_and_judge_requirement():
    """Off means no checker; on without a judge is a config
    error; on with a judge yields pair verdicts."""
    assert contradiction_checker_from_config({}) is None
    assert contradiction_checker_from_config(
        {"contradiction_check": False}) is None
    try:
        contradiction_checker_from_config({"contradiction_check": True})
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    judge = JudgeStub("contradicts")
    checker = contradiction_checker_from_config(
        {"contradiction_check": True, "judge": judge})
    a = claim("c1", "a1", "one conclusion")
    b = claim("c2", "a2", "the opposite conclusion")
    assert checker(a, b) == "contradicts"
    assert judge.calls == 1


def test_debate_records_disputes_and_excludes_contested_claims():
    """End to end: a dispute is recorded, named in the
    cross-examination, and its claims are contested in the spec
    rather than merged as agreed material."""
    a = StubProvider("stub-a", dossier(
        "D-A", "agent-a", "FOCUS-A", [good_claim("C-A1"),
                                      good_claim("C-A2", tier=3)]))
    b = StubProvider("stub-b", dossier(
        "D-B", "agent-b", "FOCUS-A", [good_claim("C-B1")]))
    judge = StubProvider("stub-judge", dossier(
        "D-J", "agent-j", "FOCUS-A", [good_claim("C-J1")]))

    def checker(x, y):
        """Contradict only the C-A1 / C-B1 pair."""
        pair = {x.get("claim_id"), y.get("claim_id")}
        return "contradicts" if pair == {"C-A1", "C-B1"} else "compatible"

    record = run_debate(FRAME, [a, b], judge_provider=judge,
                        contradiction_checker=checker)
    assert len(record["disputes"]) == 1
    assert record["contradiction_check"]["disputes"] == 1
    kinds = [t["kind"] for t in record["cross_examination"]]
    assert "contradiction_dispute" in kinds
    contested = {c["claim_id"] for c in record["spec"]["contested_claims"]}
    assert contested == {"C-A1", "C-B1"}
    merged = {c["claim_id"] for c in record["spec"]["claims"]}
    assert "C-A1" not in merged and "C-B1" not in merged
    assert "C-A2" in merged


def test_debate_without_checker_records_no_disputes():
    """The default path is unchanged in shape: no disputes, and
    the summary records that no check ran."""
    a = StubProvider("stub-a", dossier(
        "D-A", "agent-a", "FOCUS-A", [good_claim("C-A1")]))
    b = StubProvider("stub-b", dossier(
        "D-B", "agent-b", "FOCUS-A", [good_claim("C-B1")]))
    record = run_debate(FRAME, [a, b])
    assert record["disputes"] == []
    assert record["contradiction_check"] is None
    assert "contested_claims" not in record["spec"]
