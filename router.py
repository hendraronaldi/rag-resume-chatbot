"""LLM-first router with a deterministic fallback: the DAG Router Node (guide 01).

Default path is route_with_llm(): it asks the routing model pool for an
intent and falls back to the deterministic regex route() below on any
failure, so the live request path classifies with the model while staying
offline-safe.

Intent purposes:
- RAG: resume and background questions answered from the knowledge base
  (skills, experience, projects, education, certifications) via retrieval.
- CHAT: smalltalk (greetings, thanks, jokes, how are you, goodbye) answered
  from the system prompt plus history with no retrieval.
- LEAD_CAPTURE: contact, job-offer, or partnership intent (email address,
  explicit contact request, or an offer to work together) that redirects to
  the Contact section without storing data.
- OTHER: anything outside the assistant's scope; answered with the
  out-of-scope capability reply instead of retrieval.

Deterministic fallback rules (in order):
0. Non-string query -> 400 (not routable; contract takes str only).
1. Blank query or raw size > 2000 bytes -> 400 (decided in grilling; guide silent).
2. Email address, explicit contact phrase, or job/partnership offer -> LEAD_CAPTURE.
3. Smalltalk pattern -> CHAT.
4. Anything else -> RAG (OTHER is decided by the LLM only, never by regex).
"""

import json
import re
from typing import Any, Optional

RAG = "RAG"
CHAT = "CHAT"
LEAD_CAPTURE = "LEAD_CAPTURE"
OTHER = "OTHER"

MAX_QUERY_BYTES = 2000

_VALID_INTENTS = frozenset((RAG, CHAT, LEAD_CAPTURE, OTHER))

_ROUTING_PROMPT = (
    "Classify the user query into exactly one intent: RAG, CHAT, "
    "LEAD_CAPTURE, or OTHER. Reply with JSON like {\"intent\": \"RAG\"}. "
    "RAG means a resume or background question about the person's skills, "
    "experience, projects, education, or certifications. "
    "LEAD_CAPTURE means the query contains an email address, an explicit "
    "contact request, or a job, partnership, collaboration, or freelance "
    "offer. CHAT means smalltalk (greetings, thanks, jokes, "
    "how are you, goodbye). OTHER means anything outside these topics. "
    "Query: "
)

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_CONTACT = re.compile(
    r"\b(contact me|call me|reach me|hire me|email me|write to)\b", re.IGNORECASE
)
_OPPORTUNITY = re.compile(
    r"\b(job offer|job opportunity|role for you|position for you"
    r"|work with you|work together|partner with|partnership"
    r"|collaborat\w*|freelance|contract work|we are hiring|we're hiring"
    r"|join (our|my) team|have a (job|role|position|opportunity) for you"
    r"|offer you|hiring for)\b",
    re.IGNORECASE,
)
_SMALLTALK = re.compile(
    r"\bhello\b|\bhi\b|\bhey\b|\bthanks?\b|\bthank you\b"
    r"|\bjoke\b|\bhow are you\b|\bgood morning\b|\bbye\b",
    re.IGNORECASE,
)


class Unroutable(Exception):
    """Raised with a 400-style message for queries outside the enum contract."""


def _parse_llm_intent(raw_text: str) -> Optional[str]:
    """Extract a valid intent from an LLM reply, or None when unusable."""
    if not isinstance(raw_text, str):
        return None
    candidate = raw_text.strip().upper()
    if candidate in _VALID_INTENTS:
        return candidate
    try:
        payload = json.loads(raw_text.strip())
    except (ValueError, TypeError):
        return None
    if isinstance(payload, dict):
        intent = payload.get("intent")
        if isinstance(intent, str) and intent.strip().upper() in _VALID_INTENTS:
            return intent.strip().upper()
    return None


def route(query: str) -> str:
    """Classify a query with the deterministic regex fallback path.

    Args:
        query: Raw user query string.

    Returns:
        One of RAG, CHAT, or LEAD_CAPTURE (OTHER is returned only by
        route_with_llm, never by this regex path).

    Raises:
        Unroutable: If the query is non-string, blank, or oversized.
    """
    if not isinstance(query, str):
        raise Unroutable("400: query is unroutable")
    if not query or not query.strip():
        raise Unroutable("400: empty query is unroutable")
    if len(query.encode("utf-8")) > MAX_QUERY_BYTES:
        raise Unroutable("400: query exceeds raw byte limit")
    if _EMAIL.search(query) or _CONTACT.search(query) or _OPPORTUNITY.search(query):
        return LEAD_CAPTURE
    if _SMALLTALK.search(query):
        return CHAT
    return RAG


def route_with_llm(query: str, llm: Any, **kwargs: Any) -> str:
    """Classify via an LLM pool first, falling back to regex on failure.

    Args:
        query: Raw user query string.
        llm: LLM-compatible object exposing complete(prompt, ...).
        **kwargs: Forwarded to llm.complete (e.g. remaining_budget_s).

    Returns:
        One of RAG, CHAT, LEAD_CAPTURE, or OTHER.

    Raises:
        Unroutable: If the query is non-string, blank, or oversized.
    """
    route(query)
    try:
        response = llm.complete(_ROUTING_PROMPT + query, **kwargs)
        text = getattr(response, "text", response)
        if not isinstance(text, str):
            text = str(text)
        intent = _parse_llm_intent(text)
        if intent is not None:
            return intent
    except Unroutable:
        raise
    except Exception:
        pass
    return route(query)
