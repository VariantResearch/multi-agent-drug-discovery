"""Run configuration: who the providers are, in a file, not in code.

A run is described by a JSON config (see examples/run-config.example.json):

- providers: the research panel, at least two entries for a debate.
- judge and baseline: one provider entry each, or null.
- budget: a budget dict for madd/budget.py, or null.
- live_resolution: when true, the evidence call also strikes claims
  whose identifiers the live registries report as not found.
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

from .budget import BudgetTracker
from .providers import MockProvider
from .providers_http import AnthropicProvider, OpenAICompatibleProvider

KINDS = {"mock", "openai-compatible", "anthropic"}
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
    for role in ("judge", "baseline"):
        entry = config.get(role)
        if entry is not None:
            _check_entry(entry, role, errors)
            if isinstance(entry, dict) and entry.get("name"):
                names.append(entry["name"])
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        errors.append("provider names must be unique across providers, judge, "
                      "and baseline; duplicated: " + ", ".join(dupes))
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

    Returns {providers, judge, baseline, budget, live_resolution}.
    Raises ConfigError on any problem, including a missing key
    variable (named, never valued).
    """
    errors = validate_config(config)
    if errors:
        raise ConfigError("invalid run config: " + "; ".join(errors))
    env = os.environ if environ is None else environ
    return {
        "providers": [_build_one(e, env) for e in config["providers"]],
        "judge": _build_one(config["judge"], env) if config.get("judge") else None,
        "baseline": _build_one(config["baseline"], env)
        if config.get("baseline") else None,
        "budget": config.get("budget"),
        "live_resolution": bool(config.get("live_resolution", False)),
        "max_workers": int(config.get("parallel_cases", 1)),
    }
