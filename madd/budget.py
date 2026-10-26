"""Run budget tracking with a hard stop.

docs/PHASE1_SPEC.md requires per-run budgets that are set before the run
and enforced by stopping the run when they are hit. A run manifest can
carry a budget dict, but a recorded number enforces nothing on its own;
this tracker is the enforcement point. The flow for a caller is:
reserve() before the call - an atomic check-and-record under the
tracker's lock, so two threads sharing one tracker cannot both pass
the check and overshoot the cap together - and make the call only when
the reserve succeeds. record() remains for settling costs that only
become known after a call (transport retries of a reserved call); it
also refuses any entry that would cross a cap, so an over-cap entry is
never silently absorbed even by a caller that skipped the reserve.

Standard library only. Costs are plain numbers in US dollars as reported
by the caller; this module does no pricing lookups and invents no rates.
"""
from __future__ import annotations

import threading


class BudgetExceeded(Exception):
    """Raised when recording a call would cross a budget cap."""


def settle_transport_retries(tracker, provider, cost_usd: float,
                             note: str) -> None:
    """Charge a finished call's transport retries to the tracker.

    HTTP providers retry inside one logical call and report the
    attempt count on last_attempts. The reserve covered the first
    attempt; the retries are real provider calls too, so they are
    recorded here at the same per-call cost. Recording can raise
    BudgetExceeded, which stops the run with honest numbers rather
    than absorbing the overage silently. A None tracker (an
    unbudgeted run) settles nothing."""
    if tracker is None:
        return
    extra = int(getattr(provider, "last_attempts", 1) or 1) - 1
    if extra > 0:
        tracker.record(cost_usd * extra, calls=extra, note=note)


def _non_negative_number(value, name):
    """Validate one budget number: reject bools and non-numbers, reject
    negatives, return the value as a float."""
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
        """Parse the caps out of the budget dict. At least one cap must be
        present: an uncapped budget is rejected here, at construction,
        so no code path can run without one."""
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
        # One tracker is shared across a whole run, and parallel case
        # execution charges it from several threads at once.
        self._lock = threading.RLock()

    def would_exceed(self, cost_usd: float = 0.0, calls: int = 1) -> bool:
        """True when recording this call would cross a cap."""
        with self._lock:
            cost = _non_negative_number(cost_usd, "cost_usd")
            if self.max_cost_usd is not None and self.spent_usd + cost > self.max_cost_usd:
                return True
            if self.max_calls is not None and self.calls_made + calls > self.max_calls:
                return True
            return False

    def reserve(self, cost_usd: float = 0.0, calls: int = 1, note: str = "") -> dict:
        """Atomically check the caps and record a call BEFORE it is made.

        would_exceed() plus record() as separate steps is a race when
        several threads share one tracker: both can pass the check and
        overshoot together. reserve() holds the lock across check and
        record, so a call that would cross a cap raises BudgetExceeded
        here and is never made. The charge stands even if the call then
        fails: the attempt happened, and the budget accounts for it
        conservatively rather than pretending it was free.
        """
        with self._lock:
            return self.record(cost_usd, calls=calls, note=note)

    def record(self, cost_usd: float = 0.0, calls: int = 1, note: str = "") -> dict:
        """Record a call's actual cost. Raises BudgetExceeded over a cap.

        On a raise nothing is recorded: the spend figures stay at the
        last in-budget state, so a stopped run reports honest numbers.
        """
        with self._lock:
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
        """Headroom under each cap; None for a dimension that has no cap."""
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
