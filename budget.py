"""Deterministic context-budget policy: per-request assembly (guide 02).

Priority order: P1 system+query (never dropped; overflow -> 400),
P2 chunks (drop lowest-ranked first; rank 1 is best), P3 history
(FIFO, oldest first).
Token counting is a whitespace word split: deterministic and swappable.

Malformed inputs surface as 400 via BudgetExceeded; malformed chunks or
history entries are dropped (they are P2/P3, never P1).
"""

from typing import List


class BudgetExceeded(Exception):
    """Raised when P1 alone exceeds the budget (maps to 400 Bad Request)."""


def count_tokens(text: str) -> int:
    return len(text.split())


def assemble_context(system: str, query: str, chunks: List[dict],
                     history: List[str], max_tokens: int) -> dict:
    if not isinstance(system, str) or not isinstance(query, str):
        raise BudgetExceeded("400: system prompt and query must be strings")
    if (isinstance(max_tokens, bool) or not isinstance(max_tokens, int)
            or max_tokens <= 0):
        raise BudgetExceeded("400: max_tokens must be a positive integer")
    if not isinstance(chunks, list) or not isinstance(history, list):
        raise BudgetExceeded("400: chunks and history must be lists")

    p1 = count_tokens(system) + count_tokens(query)
    if p1 > max_tokens:
        raise BudgetExceeded("400: system prompt + query exceed MAX_TOKENS")
    remaining = max_tokens - p1

    ranked = sorted(
        [c for c in chunks
         if isinstance(c, dict)
         and isinstance(c.get("rank"), (int, float))
         and not isinstance(c.get("rank"), bool)
         and isinstance(c.get("text"), str)],
        key=lambda c: c["rank"],  # rank 1 is best; ascending
    )
    while ranked and sum(count_tokens(c["text"]) for c in ranked) > remaining:
        ranked.pop()  # drop lowest-ranked first
    kept_chunks = ranked

    kept_history = [m for m in history if isinstance(m, str)]
    while kept_history and sum(count_tokens(m) for m in kept_history) > remaining:
        kept_history.pop(0)  # FIFO: oldest first

    return {"system": system, "query": query,
            "chunks": kept_chunks, "history": kept_history}
