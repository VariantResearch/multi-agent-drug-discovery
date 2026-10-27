"""Run configuration: who the providers are, in a file, not in code.

A run is described by a JSON config (see examples/run-config.example.json):

- mode: optional protocol mode, one of simple, dual, dual_judge.
  Modes count distinct models, not agents: every mode fields a
  research panel of at least two agents. simple puts every agent on
  one and the same model and allows no judge; dual spreads the panel
  across exactly two models and allows no judge; dual_judge spreads
  it across exactly two models and requires a judge. With no mode,
  the original rule stands: at least two providers, judge optional.
- providers: the research panel, at least two entries for a debate.
- judge and baseline: one provider entry each, or null.
- judge_swap: optional second judge entry, from a different model
  family than the judge; its dossier is the judge-swap stability
  experiment's second judging result. Requires a judge entry.
- budget: a budget dict for madd/budget.py, or null.
- live_resolution: when true, the evidence call also strikes claims
  whose identifiers the live registries report as not found.
- live_quote_check: when true, the evidence call additionally checks
  quote_checked claims against the source's open full text at Europe
  PMC and strikes a claim whose quote is absent from text that was
  actually retrieved (quote_not_in_full_text). Unavailable full text
  never strikes.
- entailment_check: when true, the evidence call asks the config's
  judge provider whether each surviving quote_checked claim is
  supported by the passage it cites, and strikes claims the judge
  finds refuted by their own quote. Requires a judge provider.
- contradiction_check: when true, surviving load-bearing claims
  from different dossiers are judged pairwise for contradiction;
  judged contradictions become named disputes and their claims
  are kept out of the consensus spec as contested. Requires a
  judge provider.
- tournament: when true, cluster representatives play judged
  head-to-head matches and Elo-style ratings are recorded on
  the run, advisory only. Requires a judge provider.
- retrieval_first: when true, load-bearing claims may cite only
  identifiers present in the evidence the run supplied (the case pack
  or the frame's evidence entries); anything else is struck as
  citation_not_in_evidence.
- parallel_cases: how many case debates may run at once (default 1).

A provider entry is {name, kind, model, family, base_url,
api_key_env, cost_per_call_usd, max_tokens, label}. kind is one of
mock, openai-compatible, anthropic. The config names the environment
variable holding the API key (api_key_env); the key itself never
appears in the config, in any output, or in any run record.
build_providers reads the variables from the process environment at
build time and fails with the variable's name when one is missing.

Choosing which models fill these slots is the project owner's
decision, recorded in docs/PHASE1_SPEC.md before a scored run. This
module only makes the choice executable.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .budget import BudgetTracker, settle_transport_retries
from .entailment import check_entailment
from .providers import MockProvider
from .resolve import check_quote_against_source, resolve_identifier
from .providers_http import AnthropicProvider, OpenAICompatibleProvider

KINDS = {"mock", "openai-compatible", "anthropic"}
MODES = ("simple", "simple_judge", "dual", "dual_judge")
DEFAULT_BASE_URLS = {"openai-compatible": "https://api.openai.com/v1",
                     "anthropic": "https://api.anthropic.com/v1"}


class ConfigError(ValueError):
    """Raised for any config problem, with the offending field named."""


def _check_entry(entry, where, errors):
    """Append any problems with one provider entry to errors: name
    present, kind known, and HTTP kinds carrying model and api_key_env."""
    if not isinstance(entry, dict):
        errors.append(where + ": entry must be an object")
        return
    if not entry.get("name"):
        errors.append(where + ": name is required")
    kind = entry.get("kind")
    if kind not in KINDS:
        errors.append(where + ": kind must be one of " + ", ".join(sorted(KINDS)))
        return
    cost = entry.get("cost_per_call_usd")
    if cost is not None and (isinstance(cost, bool)
                             or not isinstance(cost, (int, float)) or cost < 0):
        errors.append(where + ": cost_per_call_usd must be a non-negative number")
    max_tokens = entry.get("max_tokens")
    if max_tokens is not None and (isinstance(max_tokens, bool)
                                   or not isinstance(max_tokens, int)
                                   or max_tokens < 1):
        errors.append(where + ": max_tokens must be a positive integer")
    if kind == "mock":
        return
    if not entry.get("model"):
        errors.append(where + ": model is required for kind " + kind)
    if not entry.get("api_key_env"):
        errors.append(where + ": api_key_env is required for kind " + kind
                      + " (the name of the environment variable holding the key)")


def validate_config(config) -> list:
    """Return a list of problems with a run config (empty when valid)."""
    errors = []
    if not isinstance(config, dict):
        return ["config must be a JSON object"]
    providers = config.get("providers")
    if not isinstance(providers, list) or len(providers) < 2:
        errors.append("providers: at least two provider entries are required "
                      "for a debate")
        providers = providers if isinstance(providers, list) else []
    names = []
    for i, entry in enumerate(providers):
        _check_entry(entry, "providers[" + str(i) + "]", errors)
        if isinstance(entry, dict) and entry.get("name"):
            names.append(entry["name"])
    mode = config.get("mode")
    if mode is not None:
        if mode not in MODES:
            errors.append("mode: must be one of " + ", ".join(MODES))
        else:
            # A provider entry's model identity: the model id for HTTP
            # kinds, and the mock's fixed model_version for mocks.
            models = set()
            for entry in providers:
                if isinstance(entry, dict):
                    models.add("mock-0" if entry.get("kind") == "mock"
                               else entry.get("model"))
            judge = config.get("judge")
            if mode == "simple":
                if len(models) != 1:
                    errors.append("mode simple uses one model: the research "
                                  "panel must span exactly one distinct "
                                  "model, but it spans " + str(len(models)))
                if judge is not None:
                    errors.append("mode simple has no judge; remove the "
                                  "judge entry or choose dual_judge")
            elif mode == "dual":
                if len(models) != 2:
                    errors.append("mode dual uses two models: the research "
                                  "panel must span exactly two distinct "
                                  "models, but it spans " + str(len(models)))
                if judge is not None:
                    errors.append("mode dual has no judge; a judge belongs "
                                  "to dual_judge mode")
            elif mode == "simple_judge":
                if len(models) != 1:
                    errors.append("mode simple_judge uses one model plus "
                                  "a judge: the research panel must span "
                                  "exactly one distinct model, but it spans "
                                  + str(len(models)))
                if judge is None:
                    errors.append("mode simple_judge requires a judge entry")
            else:
                if len(models) != 2:
                    errors.append("mode dual_judge uses two models plus a "
                                  "judge: the research panel must span "
                                  "exactly two distinct models, but it spans "
                                  + str(len(models)))
                if judge is None:
                    errors.append("mode dual_judge requires a judge entry")
    if config.get("judge_swap") is not None and config.get("judge") is None:
        errors.append("judge_swap: a swap judge swaps the ranking judge, "
                      "so a judge entry is required alongside it")
    for role in ("judge", "judge_swap", "baseline"):
        entry = config.get(role)
        if entry is not None:
            _check_entry(entry, role, errors)
            if isinstance(entry, dict) and entry.get("name"):
                names.append(entry["name"])
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        errors.append("provider names must be unique across providers, judge, "
                      "judge_swap, and baseline; duplicated: " + ", ".join(dupes))
    budget = config.get("budget")
    if budget is not None:
        try:
            BudgetTracker(budget)
        except Exception as exc:
            errors.append("budget: " + str(exc))
    parallel = config.get("parallel_cases")
    if parallel is not None and (isinstance(parallel, bool)
                                 or not isinstance(parallel, int) or parallel < 1):
        errors.append("parallel_cases: must be a positive integer")
    return errors


def load_config(path) -> dict:
    """Read a run config file and return it; raise ConfigError listing
    every problem when it is invalid."""
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    errors = validate_config(config)
    if errors:
        raise ConfigError("invalid run config " + str(path) + ": "
                          + "; ".join(errors))
    return config


def _build_one(entry, environ):
    """Construct one provider object from its config entry, reading
    the API key from the environment variable the entry names."""
    kind = entry["kind"]
    if kind == "mock":
        return MockProvider(label=str(entry.get("label", entry["name"])))
    env_name = entry["api_key_env"]
    api_key = environ.get(env_name)
    if not api_key:
        raise ConfigError("environment variable " + env_name + " is not set "
                          "(needed by provider " + entry["name"] + "); set it "
                          "in the environment, never in the config file")
    base_url = entry.get("base_url") or DEFAULT_BASE_URLS[kind]
    common = {"family": entry.get("family"),
              "cost_per_call_usd": entry.get("cost_per_call_usd", 0.0),
              "max_tokens": entry.get("max_tokens", 4096)}
    if kind == "openai-compatible":
        return OpenAICompatibleProvider(entry["name"], entry["model"], api_key,
                                        base_url, **common)
    return AnthropicProvider(entry["name"], entry["model"], api_key,
                             base_url, **common)


def build_providers(config, environ=None) -> dict:
    """Construct provider objects from a validated config.

    Returns {providers, judge, judge_swap, baseline, budget,
    live_resolution, live_quote_check, entailment_check,
    retrieval_first, mode}.
    Raises ConfigError on any problem, including a missing key
    variable (named, never valued).
    """
    errors = validate_config(config)
    if errors:
        raise ConfigError("invalid run config: " + "; ".join(errors))
    env = os.environ if environ is None else environ
    return {
        "mode": config.get("mode"),
        "providers": [_build_one(e, env) for e in config["providers"]],
        "judge": _build_one(config["judge"], env) if config.get("judge") else None,
        "judge_swap": _build_one(config["judge_swap"], env)
        if config.get("judge_swap") else None,
        "baseline": _build_one(config["baseline"], env)
        if config.get("baseline") else None,
        "budget": config.get("budget"),
        "live_resolution": bool(config.get("live_resolution", False)),
        "live_quote_check": bool(config.get("live_quote_check", False)),
        "entailment_check": bool(config.get("entailment_check", False)),
        "contradiction_check": bool(config.get("contradiction_check", False)),
        "tournament": bool(config.get("tournament", False)),
        "retrieval_first": bool(config.get("retrieval_first", False)),
        "max_workers": int(config.get("parallel_cases", 1)),
    }


def run_budget_tracker(built: dict):
    """The one budget tracker for a run, built from the config's
    budget dict, or None when the config sets no budget. Every stage
    of a run (research, entailment judging, design) charges this
    same tracker, so the configured caps bound the run's total
    provider spend rather than one stage of it."""
    budget = built.get("budget")
    return BudgetTracker(budget) if budget is not None else None


_REGISTRY_FETCHER = None


def _registry_fetcher():
    """The shared registry transport for live evidence calls.

    Persistent connections always; the cross-run SQLite cache is
    added when the MADD_REGISTRY_CACHE environment variable names
    its file (the console sets it to its runs directory by
    default). Returns None when no cache is configured, in which
    case the resolve module's own pooled default applies.
    """
    global _REGISTRY_FETCHER
    if _REGISTRY_FETCHER is not None:
        return _REGISTRY_FETCHER
    cache_path = os.environ.get("MADD_REGISTRY_CACHE") or None
    if not cache_path:
        return None
    from .resolve import registry_fetcher
    _REGISTRY_FETCHER = registry_fetcher(cache_path=cache_path)
    return _REGISTRY_FETCHER


def resolver_from_config(built: dict):
    """Return the evidence-call resolver when the config enables live
    resolution, else None (audits stay offline)."""
    if not built["live_resolution"]:
        return None

    def resolver(identifier, identifier_type):
        """Resolve one identifier live and return just its status string,
        the shape debate.audit_dossier expects from a resolver. A
        resolved-but-retracted record reports as retracted so the
        evidence call strikes it."""
        fetcher = _registry_fetcher()
        if fetcher is None:
            result = resolve_identifier(identifier, identifier_type)
        else:
            result = resolve_identifier(identifier, identifier_type,
                                        fetcher=fetcher)
        if result["status"] == "resolved" and result.get("retracted"):
            return "retracted"
        return result["status"]

    return resolver


def quote_checker_from_config(built: dict):
    """Return the evidence-call quote checker when the config enables
    live quote checking, else None (quotes stay unchecked live)."""
    if not built.get("live_quote_check"):
        return None

    def quote_checker(claim):
        """Check one claim's quote against its source's open full text
        and return the status string debate.audit_dossier expects."""
        fetcher = _registry_fetcher()
        if fetcher is None:
            return check_quote_against_source(
                claim.get("source_identifier"), claim.get("identifier_type"),
                claim.get("supporting_quote"))["status"]
        return check_quote_against_source(
            claim.get("source_identifier"), claim.get("identifier_type"),
            claim.get("supporting_quote"), fetcher=fetcher)["status"]

    return quote_checker


def entailment_checker_from_config(built: dict, budget_tracker=None):
    """Return the evidence-call entailment checker when the config
    enables entailment checking, else None. The checker judges with
    the config's judge provider; enabling the check without one is a
    configuration error, raised as ValueError. When a budget tracker
    is given, every judging call reserves against it first, so
    entailment completions count toward the run budget like every
    other provider call, and the judging call's transport retries
    are settled against it afterwards; an exhausted budget raises
    BudgetExceeded out of the checker and stops the run."""
    if not built.get("entailment_check"):
        return None
    judge = built.get("judge")
    if judge is None:
        raise ValueError("entailment_check is on but the config names no "
                         "judge provider to judge entailment with")

    def entailment_checker(claim):
        """Judge one claim against its cited passage and return the
        verdict string debate.audit_dossier expects."""
        cost = float(getattr(judge, "cost_per_call_usd", 0.0) or 0.0)
        if budget_tracker is not None:
            budget_tracker.reserve(
                cost, note="entailment:" + str(getattr(judge, "name", "?")))
        verdict = check_entailment(claim, judge)
        settle_transport_retries(
            budget_tracker, judge, cost,
            "transport retries:entailment:"
            + str(getattr(judge, "name", "?")))
        return verdict

    return entailment_checker


def contradiction_checker_from_config(built: dict, budget_tracker=None):
    """Return the contradiction checker when the config enables
    contradiction checking, else None. The checker judges claim
    pairs with the config's judge provider; enabling the check
    without one is a configuration error, raised as ValueError.
    When a budget tracker is given, every judging call reserves
    against it first and settles transport retries afterwards,
    exactly as the entailment checker does."""
    if not built.get("contradiction_check"):
        return None
    judge = built.get("judge")
    if judge is None:
        raise ValueError("contradiction_check is on but the config names "
                         "no judge provider to judge contradictions with")

    def contradiction_checker(claim_a, claim_b):
        """Judge one pair of claims and return the verdict string
        madd.contradictions.find_disputes expects."""
        from .contradictions import check_pair
        cost = float(getattr(judge, "cost_per_call_usd", 0.0) or 0.0)
        if budget_tracker is not None:
            budget_tracker.reserve(
                cost, note="contradiction:"
                + str(getattr(judge, "name", "?")))
        verdict = check_pair(claim_a, claim_b, judge)
        settle_transport_retries(
            budget_tracker, judge, cost,
            "transport retries:contradiction:"
            + str(getattr(judge, "name", "?")))
        return verdict

    return contradiction_checker


def tournament_judge_from_config(built: dict, budget_tracker=None):
    """Return the tournament comparator when the config enables
    the tournament, else None. Matches are judged by the config's
    judge provider; enabling the tournament without one is a
    configuration error, raised as ValueError. Budget handling
    mirrors the other judged checks. The ratings the comparator
    feeds are advisory: they never move a consensus outcome."""
    if not built.get("tournament"):
        return None
    judge = built.get("judge")
    if judge is None:
        raise ValueError("tournament is on but the config names no "
                         "judge provider to judge matches with")

    def tournament_comparator(summary_a, summary_b):
        """Judge one head-to-head between two proposal summaries
        and return the result string madd.tournament expects."""
        from .tournament import compare_proposals
        cost = float(getattr(judge, "cost_per_call_usd", 0.0) or 0.0)
        if budget_tracker is not None:
            budget_tracker.reserve(
                cost, note="tournament:"
                + str(getattr(judge, "name", "?")))
        result = compare_proposals(summary_a, summary_b, judge)
        settle_transport_retries(
            budget_tracker, judge, cost,
            "transport retries:tournament:"
            + str(getattr(judge, "name", "?")))
        return result

    return tournament_comparator
