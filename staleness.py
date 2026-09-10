"""Deterministic staleness mitigation: index build-date injection and refusal (guide 02).

Real mitigation: the index build date is baked into the compiled retrieval
artifact (``index.json`` ``build_date`` field, written by ``build_index.py``
at Docker compile time) and injected into the system prompt on every request.
Event questions dated after the build date get an explicit lack-of-information
refusal instead of a stale fact. The default prompt path and the refusal
threshold both resolve through the baked artifact, so the two can never
diverge after a re-bake.

Frozen contract (unchanged):
    INDEX_BUILD_DATE: str
    build_system_prompt(index_build_date: str = INDEX_BUILD_DATE) -> str
    answer_for_event_date(event_date: str) -> str

All entry points are total functions: they never raise on malformed input
and instead fail closed (fallback date, explicit refusal). Stdlib only, no
clocks, no randomness, no network -- repeated runs are byte-identical.
"""

import json
import os
from datetime import date

INDEX_BUILD_DATE = "2026-08-01"

_INDEX_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.json")

_REFUSAL_PHRASE = "do not have that information yet"


def _is_valid_date(value) -> bool:
    """True when value is a parseable ISO-8601 calendar date. Never raises."""
    try:
        if not isinstance(value, str) or not value.strip():
            return False
        date.fromisoformat(value)
        return True
    except (ValueError, TypeError):
        return False


def _load_baked_date():
    """Read the build date baked into index.json; None when absent/invalid."""
    try:
        with open(_INDEX_PATH, "r", encoding="utf-8") as fh:
            artifact = json.load(fh)
        candidate = artifact.get("build_date")
        if _is_valid_date(candidate):
            return candidate
        return None
    except (OSError, ValueError, AttributeError):
        return None


_BAKED_BUILD_DATE = _load_baked_date()

LIVE_BUILD_DATE_FILENAME = "build_date.json"


def _get_build_date() -> str:
    """Effective index build date: baked artifact wins, constant fallback."""
    try:
        if _BAKED_BUILD_DATE is not None:
            return _BAKED_BUILD_DATE
        return INDEX_BUILD_DATE
    except Exception:
        return INDEX_BUILD_DATE


def _coerce_build_date(candidate) -> str:
    """Usable build date for the prompt.

    The frozen-default path tracks the baked artifact so the prompt and the
    refusal threshold can never diverge; an explicit valid date is honored;
    anything else falls back to the effective build date.
    """
    try:
        if candidate == INDEX_BUILD_DATE:
            return _get_build_date()
        if _is_valid_date(candidate):
            return candidate
        return _get_build_date()
    except Exception:
        return INDEX_BUILD_DATE


def _refusal_message(effective: str) -> str:
    """Explicit lack-of-information refusal carrying the build date."""
    return ("I " + _REFUSAL_PHRASE + "; my knowledge base was "
            "last updated on " + effective + ".")


def build_system_prompt(index_build_date: str = INDEX_BUILD_DATE) -> str:
    """System prompt with the index build date injected. Never raises."""
    effective = _coerce_build_date(index_build_date)
    return (
        "Your knowledge base was last updated on "
        + effective
        + ". If the user asks about events after this date, "
        "state that you " + _REFUSAL_PHRASE + "."
    )


def _is_post_date(event_date: str) -> bool:
    """True when event_date is after the build date.

    Malformed event dates fail closed to True (refuse rather than risk a
    stale answer). Never raises.
    """
    try:
        if not _is_valid_date(event_date):
            return True
        return date.fromisoformat(event_date) > date.fromisoformat(_get_build_date())
    except (ValueError, TypeError):
        return True
    except Exception:
        return True


def answer_for_event_date(event_date: str) -> str:
    """Answer or explicitly refuse depending on the event date. Never raises."""
    try:
        if _is_post_date(event_date):
            return _refusal_message(_get_build_date())
        return "Here is what the knowledge base records about that date."
    except Exception:
        return _refusal_message(INDEX_BUILD_DATE)


def resolve_live_build_date(index_dir: str) -> str:
    """Build date stamped at boot for the live vector index. Never raises.

    Reads ``build_date.json`` written by ``builder.py`` next to the persisted
    live index. A missing or invalid artifact fails closed to the effective
    build date, so the query path never breaks for date reasons.

    Args:
        index_dir: Persisted live-index directory holding build_date.json.

    Returns:
        The live build date, or the effective build date as fallback.
    """
    try:
        with open(os.path.join(index_dir or "", LIVE_BUILD_DATE_FILENAME),
                   "r", encoding="utf-8") as fh:
            artifact = json.load(fh)
        candidate = artifact.get("build_date")
        if _is_valid_date(candidate):
            return candidate.strip()
        return _get_build_date()
    except (OSError, ValueError, AttributeError, TypeError):
        return _get_build_date()
