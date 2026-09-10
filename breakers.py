"""Deterministic harness loop circuit breakers (guide 02).

Real loop safety: the step cap breaks at exactly MAX_STEPS, an identical
consecutive tool-call hash breaks immediately, and elapsed time past
TIME_BUDGET_S breaks gracefully.

All predicates are total functions: they never raise on malformed input,
so a misbehaving loop step can never crash the safety check itself.
"""

import hashlib
import os

MAX_STEPS = 5


def _time_budget_s() -> float:
    try:
        return float(os.getenv("PORTFOLIO_TIME_BUDGET_S", "60.0"))
    except (TypeError, ValueError):
        return 60.0


TIME_BUDGET_S = _time_budget_s()


def call_hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stagnated(previous_hash: str, current_hash: str) -> bool:
    """True when the current tool-call request repeats the previous one."""
    if not previous_hash or not current_hash:
        return False
    return previous_hash == current_hash


def over_cost_cap(steps_taken: int) -> bool:
    try:
        return steps_taken >= MAX_STEPS
    except TypeError:
        return False


def over_time_budget(start_t: float, now_t: float) -> bool:
    try:
        return (now_t - start_t) > TIME_BUDGET_S
    except TypeError:
        return False


def should_break(steps_taken: int, previous_hash: str,
                 current_hash: str, start_t: float, now_t: float) -> bool:
    return bool(over_cost_cap(steps_taken)
                or stagnated(previous_hash, current_hash)
                or over_time_budget(start_t, now_t))
