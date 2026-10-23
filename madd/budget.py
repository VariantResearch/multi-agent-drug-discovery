"""Run budget tracking with a hard stop.

docs/PHASE1_SPEC.md requires per-run budgets that are set before the run
and enforced by stopping the run when they are hit. A run manifest can
carry a budget dict, but a recorded number enforces nothing on its own;
this tracker is the enforcement point. The flow for a caller is: check
the projected cost first with would_exceed, make the call only if it
fits, then record the actual cost. record() itself also refuses any
entry that would cross a cap, so an over-cap call is never silently
absorbed even by a caller that skipped the check.

Standard library only. Costs are plain numbers in US dollars as reported
by the caller; this module does no pricing lookups and invents no rates.
"""
from __future__ import annotations


class BudgetExceeded(Exception):
    """Raised when recording a call would cross a budget cap."""


def _non_negative_number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(name + " must be a number")
    if value < 0:
        raise ValueError(name + " must not be negative")
    return float(value)


class BudgetTracker:
    """Track spend and call count against caps fixed before the run.

    budget is a dict with at least one of:
      max_cost_usd (number): hard cap on total recorded cost.
      max_calls (int): hard cap on total recorded calls.
    """

    def __init__(self, budget: dict):
        if not isinstance(budget, dict):
            raise ValueError("budget must be a dict")
        self.max_cost_usd = None
        self.max_calls = None
        if "max_cost_usd" in budget and budget["max_cost_usd"] is not None:
            self.max_cost_usd = _non_negative_number(budget["max_cost_usd"], "max_cost_usd")
        if "max_calls" in budget and budget["max_calls"] is not None:
            calls = budget["max_calls"]
            if isinstance(calls, bool) or not isinstance(calls, int) or calls < 0:
                raise ValueError("max_calls must be a non-negative integer")
            self.max_calls = calls
        if self.max_cost_usd is None and self.max_calls is None:
            raise ValueError(
                "budget sets no cap: give max_cost_usd or max_calls. "
                "An uncapped run is exactly what the budget rule exists to prevent.")
        self.spent_usd = 0.0
        self.calls_made = 0
        self.entries = []

    def would_exceed(self, cost_usd: float = 0.0, calls: int = 1) -> bool:
        """True when recording this call would cross a cap."""
        cost = _non_negative_number(cost_usd, "cost_usd")
        if self.max_cost_usd is not None and self.spent_usd + cost > self.max_cost_usd:
            return True
        if self.max_calls is not None and self.calls_made + calls > self.max_calls:
            return True
        return False

    def record(self, cost_usd: float = 0.0, calls: int = 1, note: str = "") -> dict:
        """Record a call's actual cost. Raises BudgetExceeded over a cap.

        On a raise nothing is recorded: the spend figures stay at the
        last in-budget state, so a stopped run reports honest numbers.
        """
        cost = _non_negative_number(cost_usd, "cost_usd")
        if isinstance(calls, bool) or not isinstance(calls, int) or calls < 0:
            raise ValueError("calls must be a non-negative integer")
        if self.would_exceed(cost, calls):
            raise BudgetExceeded(
                "budget cap reached: spent " + format(self.spent_usd, ".4f")
                + " USD in " + str(self.calls_made) + " calls; recording "
                + format(cost, ".4f") + " USD / " + str(calls)
                + " calls would exceed the cap (max_cost_usd="
                + str(self.max_cost_usd) + ", max_calls=" + str(self.max_calls) + ")")
        self.spent_usd += cost
        self.calls_made += calls
        entry = {"cost_usd": cost, "calls": calls, "note": note,
                 "spent_after_usd": self.spent_usd, "calls_after": self.calls_made}
        self.entries.append(entry)
        return entry

    def remaining(self) -> dict:
        return {
            "cost_usd": (None if self.max_cost_usd is None
                         else round(self.max_cost_usd - self.spent_usd, 10)),
            "calls": (None if self.max_calls is None
                      else self.max_calls - self.calls_made),
        }

    def to_dict(self) -> dict:
        """Budget state in the shape a run manifest can carry."""
        return {"max_cost_usd": self.max_cost_usd, "max_calls": self.max_calls,
                "spent_usd": self.spent_usd, "calls_made": self.calls_made,
                "remaining": self.remaining(), "entries": list(self.entries)}
