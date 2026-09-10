"""Deterministic Langfuse tracing: one trace per request (guide 04, see ADR-001).

Frozen contract (unchanged -- the eval harness pins this shape):
    REQUIRED_SPANS, Recorder, keyed_mode, ingestion_event, live_post_enabled

Real pipeline wrapper (ticket 09):
    trace_request(query, ...) opens one Recorder per backend request and
    records child spans for the real router call, the real retrieval, and
    the deterministic generation stub, each carrying token cost
    (word-split count via budget.count_tokens) and measured latency_ms.

    Operates degraded-offline until operator keys are provided, then builds
    valid ingestion payloads via ingestion_event(); the mode is always
    disclosed in the result ("mode" field, see mode_reason()).

    Generation is a deterministic stub (no LLM in this run -- Tier-3
    generation eval is out of scope per SPEC): it assembles context with
    budget.assemble_context over the system prompt (staleness-injected)
    plus retrieved chunk texts and renders a template answer. Token cost
    for the generation span is prompt + completion word count.

Stdlib only, no network -- repeated runs differ only in trace_id
(frozen uuid shape) and measured latencies. The live sink path posts
observations through the official ``langfuse`` SDK v4 OTEL-native client
(lazy import; absence degrades to file backup) via
``start_as_current_observation`` + ``propagate_attributes`` and only
reports posted when every observation posts and the final flush succeeds.
"""

import json
import os
import time
import uuid
from typing import Optional

REQUIRED_SPANS = ("router", "retrieval", "generation")

TRACE_STORE: dict = {}

MAX_TEXT_CHARS = 2000

VOTES = ("up", "down")


class Recorder:
    def __init__(self):
        self.trace_id = "trace-" + uuid.uuid4().hex[:12]
        self.spans = []

    def span(self, name: str, tokens: int, latency_ms: float,
             input=None, output=None, model: Optional[str] = None) -> dict:
        entry = {"trace_id": self.trace_id, "name": name,
                 "tokens": tokens, "latency_ms": latency_ms}
        if input is not None:
            entry["input"] = input
        if output is not None:
            entry["output"] = output
        if model is not None:
            entry["model"] = model
        self.spans.append(entry)
        return entry

    def span_names(self):
        return [s["name"] for s in self.spans]

    def shape_ok(self) -> bool:
        if not all(n in self.span_names() for n in REQUIRED_SPANS):
            return False
        return all(isinstance(s["tokens"], int) and
                   isinstance(s["latency_ms"], (int, float))
                   for s in self.spans)


def keyed_mode() -> bool:
    return bool(os.environ.get("LANGFUSE_PUBLIC_KEY")
                and os.environ.get("LANGFUSE_SECRET_KEY"))


def ingestion_event(recorder: Recorder) -> dict:
    return {"traceId": recorder.trace_id,
            "spans": [{"name": s["name"],
                       "metadata": {"tokens": s["tokens"],
                                    "latency_ms": s["latency_ms"]}}
                      for s in recorder.spans]}


def live_post_enabled() -> bool:
    return os.environ.get("LANGFUSE_LIVE") == "1" and keyed_mode()


def mode_reason() -> str:
    """Disclosed tracing mode per ADR-001. Never raises."""
    try:
        if live_post_enabled():
            return "live: payload valid, post deferred (no network in this run)"
        if keyed_mode():
            return "keyed: valid payload, no post without LANGFUSE_LIVE=1"
        return "degraded: no key; offline span-shape proof only"
    except Exception:
        return "degraded: no key; offline span-shape proof only"


def _now_ms(start_perf: float) -> float:
    """Elapsed milliseconds since start_perf. Never negative, never raises."""
    try:
        return max(0.0, (time.perf_counter() - start_perf) * 1000.0)
    except Exception:
        return 0.0


def _result(rec, intent, chunk_ids, answer, error=None) -> dict:
    """Assemble the trace_request response shape in one place.

    Ingestion payload is attached in keyed mode (None offline), so a
    keyed request yields a valid payload without further calls.
    The error key appears only on rejection/overflow paths.
    """
    try:
        payload = ingestion_event(rec) if keyed_mode() else None
    except Exception:
        payload = None
    try:
        mode = mode_reason()
    except Exception:
        mode = "degraded: no key; offline span-shape proof only"
    out = {"trace_id": rec.trace_id, "intent": intent,
           "chunks": chunk_ids, "answer": answer, "recorder": rec,
           "mode": mode, "ingestion": payload}
    if error is not None:
        out["error"] = error
    return out


def trace_request(query, k: int = 3, max_tokens: int = 2000,
                  history=None) -> dict:
    """Run one traced request through router -> retrieval -> generation.

    Returns a dict with trace_id, intent, chunks (retrieved ids), answer,
    recorder, mode, ingestion (valid payload in keyed mode, None offline),
    and (only on rejection/overflow) error. Unroutable queries
    (blank/oversize/non-string) produce a partial trace -- router span
    only -- with a 400-style error field instead of raising, so the
    failure stays diagnosable on the trace. Generation consumes the
    budget-pruned context, so the answer and its token cost reflect only
    content that survived the budget. Never raises on malformed input;
    fails closed with an error field.
    """
    # Lazy imports: keeps this module importable behind the frozen shape
    # even if a pipeline sibling is mid-edit, and avoids import cycles.
    import budget
    import retrieval
    import router as router_mod
    import staleness

    if history is None:
        history = []
    rec = Recorder()

    # --- Router span (real router.route) ---
    t0 = time.perf_counter()
    try:
        intent = router_mod.route(query)
    except Exception as exc:
        latency = _now_ms(t0)
        try:
            tokens = budget.count_tokens(query) if isinstance(query, str) else 0
        except Exception:
            tokens = 0
        rec.span("router", tokens=tokens, latency_ms=latency,
                 input=query if isinstance(query, str) else "",
                 output="UNROUTABLE")
        return _result(rec, None, [], None,
                       error=str(exc) or "400: query is unroutable")
    router_latency = _now_ms(t0)
    try:
        router_tokens = budget.count_tokens(query)
    except Exception:
        router_tokens = 0
    rec.span("router", tokens=router_tokens, latency_ms=router_latency,
             input=query, output=intent)

    # --- Retrieval span (real retrieval.retrieve; bypass recorded, not skipped) ---
    t0 = time.perf_counter()
    chunk_ids = []
    chunk_texts = []
    if intent == router_mod.RAG:
        try:
            ids = retrieval.retrieve(query, k=k)
            chunk_ids = [cid for cid in ids if isinstance(cid, str)]
            chunk_texts = [retrieval.CHUNKS[cid] for cid in chunk_ids
                           if cid in retrieval.CHUNKS]
        except Exception:
            chunk_ids = []
            chunk_texts = []
    retrieval_latency = _now_ms(t0)
    try:
        retrieval_tokens = budget.count_tokens(query) + sum(
            budget.count_tokens(t) for t in chunk_texts)
    except Exception:
        retrieval_tokens = 0
    rec.span("retrieval", tokens=retrieval_tokens,
             latency_ms=retrieval_latency, input=query,
             output=chunk_ids if intent == router_mod.RAG else "BYPASSED")

    # --- Generation span (deterministic stub; no LLM in this run) ---
    t0 = time.perf_counter()
    try:
        system = staleness.build_system_prompt()
    except Exception:
        system = ""
    chunks_for_budget = [{"rank": i + 1, "text": t}
                         for i, t in enumerate(chunk_texts)]
    try:
        ctx = budget.assemble_context(system, query, chunks_for_budget,
                                      [m for m in history if isinstance(m, str)],
                                      max_tokens)
    except Exception as exc:
        generation_latency = _now_ms(t0)
        try:
            err_tokens = budget.count_tokens(system + " " + str(query))
        except Exception:
            err_tokens = 0
        rec.span("generation", tokens=err_tokens,
                 latency_ms=generation_latency, input=query,
                 output="BUDGET_EXCEEDED")
        return _result(rec, intent, chunk_ids, None, error=str(exc))
    kept_texts = [c["text"] for c in ctx.get("chunks", [])
                  if isinstance(c, dict) and isinstance(c.get("text"), str)]
    if intent == router_mod.LEAD_CAPTURE:
        answer = "Thanks -- we've recorded your contact request."
    elif intent == router_mod.CHAT:
        answer = "Hello! How can I help with Elena's background?"
    elif kept_texts:
        answer = "Based on the knowledge base: " + " ".join(kept_texts)
    else:
        answer = "Based on the knowledge base: no chunks retrieved."
    generation_latency = _now_ms(t0)
    try:
        generation_tokens = (budget.count_tokens(system)
                             + budget.count_tokens(query)
                             + sum(budget.count_tokens(t)
                                   for t in kept_texts)
                             + budget.count_tokens(answer))
    except Exception:
        generation_tokens = 0
    rec.span("generation", tokens=generation_tokens,
             latency_ms=generation_latency, input=query, output=answer)

    return _result(rec, intent, chunk_ids, answer)


def _backup_path() -> str:
    try:
        path = os.environ.get("TRACE_BACKUP_PATH")
        if isinstance(path, str) and path.strip():
            return path
    except Exception:
        pass
    return "./traces.jsonl"


def _append_jsonl(entry: dict) -> None:
    """Append one trace record to the JSONL file backup. Never raises."""
    try:
        with open(_backup_path(), "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def validate_feedback(payload: dict) -> list:
    """Validate a canonical feedback event; ``[]`` means acceptable.

    Byte-mirror of the frozen contract in portfolio-ui/feedback.py:
    trace_id required non-blank, vote up/down, optional text capped at
    MAX_TEXT_CHARS (overlong rejected, never truncated). Never raises.
    """
    try:
        if not isinstance(payload, dict):
            return ["payload must be an object"]
        errors: list = []
        trace_id = payload.get("trace_id")
        if not isinstance(trace_id, str) or not trace_id.strip():
            errors.append("trace_id is required")
        if payload.get("vote") not in VOTES:
            errors.append("vote must be 'up' or 'down'")
        text = payload.get("text", None)
        if text is not None:
            if not isinstance(text, str):
                errors.append("text must be a string when present")
            elif len(text) > MAX_TEXT_CHARS:
                errors.append(
                    "text must be at most %d chars" % MAX_TEXT_CHARS)
        return errors
    except Exception:
        return ["malformed feedback event"]


def tag_trace(record: dict, event: dict) -> dict:
    """Attach a validated feedback event to its trace record (pure copy)."""
    try:
        if not isinstance(record, dict):
            return {"ok": False, "errors": ["trace record must be an object"]}
        errors = validate_feedback(event)
        if errors:
            return {"ok": False, "errors": errors}
        record_id = None
        for key in ("traceId", "trace_id"):
            try:
                candidate = record.get(key)
            except Exception:
                candidate = None
            if isinstance(candidate, str) and candidate:
                record_id = candidate
                break
        if (record_id is not None
                and event.get("trace_id") != record_id):
            return {"ok": False,
                    "errors": ["event trace_id does not match trace record"]}
        tagged = dict(record)
        attachment = {"trace_id": event.get("trace_id"),
                      "vote": event.get("vote")}
        if isinstance(event.get("text"), str) and event.get("text").strip():
            attachment["text"] = event.get("text")
        tagged["feedback"] = attachment
        return {"ok": True, "trace": tagged}
    except Exception:
        return {"ok": False, "errors": ["malformed trace record or event"]}


def tag_trace_with_feedback(record: dict, event: dict) -> dict:
    """Canonical alias for tag_trace used by the feedback endpoint."""
    try:
        return tag_trace(record, event)
    except Exception:
        return {"ok": False, "errors": ["malformed trace record or event"]}


def save_trace(record: dict) -> dict:
    """Store a trace in memory and append it to the JSONL file backup."""
    try:
        if not isinstance(record, dict):
            return {}
        trace_id = record.get("trace_id")
        if not isinstance(trace_id, str) or not trace_id:
            return {}
        stored = dict(record)
        stored["spans"] = [dict(s) for s in record.get("spans", [])
                           if isinstance(s, dict)]
        TRACE_STORE[trace_id] = stored
        _append_jsonl(stored)
        return stored
    except Exception:
        return {}


def get_trace(trace_id: str) -> Optional[dict]:
    """Return a copy of a stored trace, falling back to the file backup."""
    try:
        if not isinstance(trace_id, str) or not trace_id:
            return None
        found = TRACE_STORE.get(trace_id)
        if isinstance(found, dict):
            tagged = dict(found)
            tagged["spans"] = [dict(s) for s in found.get("spans", [])
                               if isinstance(s, dict)]
            if isinstance(found.get("feedback"), dict):
                tagged["feedback"] = dict(found["feedback"])
            return tagged
        return _lookup_backup(trace_id)
    except Exception:
        return None


def langfuse_base_url() -> str:
    """Langfuse instance base URL (no trailing slash). Never raises."""
    try:
        raw = os.environ.get("LANGFUSE_BASE_URL")
        if isinstance(raw, str) and raw.strip():
            return raw.strip().rstrip("/")
    except Exception:
        pass
    return "http://localhost:3000"


def _make_client():
    """Build the official Langfuse SDK v4 client, or None.

    The import is lazy so unit tests and offline runs without the
    ``langfuse`` package keep working; absence degrades to file backup.
    Returns None when no keys are configured (offline degraded mode).
    Never raises, never networks (construction alone sends nothing).
    """
    try:
        if not keyed_mode():
            return None
        from langfuse import Langfuse
    except Exception:
        return None
    try:
        return Langfuse(
            public_key=os.environ.get("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.environ.get("LANGFUSE_SECRET_KEY"),
            base_url=langfuse_base_url(),
        )
    except Exception:
        return None


def _clip_id(value) -> Optional[str]:
    """Clip a correlation id to the v4 200-char limit. Never raises.

    Overlong ids are dropped (None), never truncated mid-value and never
    raised; see
    https://langfuse.com/docs/observability/sdk/upgrade-path/python-v3-to-v4.
    """
    try:
        if not isinstance(value, str):
            return None
        if not value.strip():
            return None
        if len(value) > 200:
            return None
        return value
    except Exception:
        return None


def _coerce_metadata(raw: dict) -> dict:
    """Coerce metadata to v4 dict[str, str] with values <= 200 chars.

    Per https://langfuse.com/docs/observability/sdk/upgrade-path/python-v3-to-v4
    non-string values are coerced to strings and overlong values are
    dropped. Never raises.
    """
    try:
        clean: dict = {}
        if not isinstance(raw, dict):
            return clean
        for key, value in raw.items():
            try:
                if not isinstance(key, str):
                    key = str(key)
                if isinstance(value, str):
                    text = value
                elif isinstance(value, (dict, list)):
                    try:
                        text = json.dumps(value)
                    except Exception:
                        continue
                else:
                    text = str(value)
                if len(text) > 200:
                    continue
                clean[key] = text
            except Exception:
                continue
        return clean
    except Exception:
        return {}


def sink_event(record: dict) -> list:
    """Build v4-native observation specs for one trace. Never raises.

    Returns a list of plain-dict specs (root span first, then one per
    recorded span) posted by post_batch() through the v4 OTEL-native
    client (``start_as_current_observation`` + ``propagate_attributes``);
    see https://langfuse.com/docs/observability/sdk/upgrade-path/python-v3-to-v4
    and https://langfuse.com/docs/observability/sdk/instrumentation.
    The v3 Fern batch-ingestion envelope has no v4 equivalent, so
    this list-of-specs shape is the compatible shim. Returns [] when the
    record is malformed. Never networks.
    """
    try:
        if not isinstance(record, dict):
            return []
        trace_id = record.get("trace_id")
        spans = record.get("spans")
        if not isinstance(trace_id, str) or not trace_id:
            return []
        if not isinstance(spans, list):
            return []
        intent = record.get("intent", "")
        if not isinstance(intent, str):
            intent = ""
        query = record.get("query", "")
        answer = record.get("answer", "")
        user_id = _clip_id(record.get("user_id"))
        session_id = _clip_id(record.get("session_id"))
        trace_name = ("rag-chat [%s]" % intent) if intent else "rag-chat"
        tags = [intent] if intent else []
        try:
            feedback = record.get("feedback")
        except Exception:
            feedback = None
        base_meta = {"trace_id": trace_id,
                     "intent": intent,
                     "index_build_date": record.get("index_build_date", "")}
        if isinstance(feedback, dict):
            base_meta["feedback"] = feedback
        specs = [{
            "is_root": True,
            "as_type": "span",
            "name": trace_name,
            "input": query,
            "output": answer,
            "metadata": _coerce_metadata(base_meta),
            "user_id": user_id,
            "session_id": session_id,
            "trace_name": trace_name,
            "tags": tags,
        }]
        for span in spans:
            if not isinstance(span, dict):
                continue
            name = span.get("name")
            if not isinstance(name, str) or not name:
                name = "span"
            tokens = span.get("tokens")
            tokens = tokens if isinstance(tokens, int) else 0
            latency = span.get("latency_ms")
            if isinstance(latency, (int, float)) and latency > 0:
                latency_ms = float(latency)
            else:
                latency_ms = 0.0
            model = span.get("model", "")
            if not isinstance(model, str):
                model = ""
            meta = dict(base_meta)
            meta.update({"tokens": tokens,
                         "latency_ms": latency_ms,
                         "model": model})
            spec = {"is_root": False,
                    "as_type": ("generation" if name == "generation"
                                else "span"),
                    "name": name,
                    "input": span.get("input", ""),
                    "output": span.get("output", ""),
                    "metadata": _coerce_metadata(meta),
                    "user_id": user_id,
                    "session_id": session_id,
                    "trace_name": trace_name,
                    "tags": tags}
            if name == "generation":
                if model:
                    spec["model"] = model
                spec["usage_details"] = {"total": tokens}
            specs.append(spec)
        return specs
    except Exception:
        return []


def post_batch(events: list, client) -> bool:
    """Post v4 observation specs via start_as_current_observation.

    Never raises. Only True when every observation posts without error
    and the final flush succeeds; any failure leaves the JSONL file
    backup as the durable copy. Correlating attributes reach every
    observation through ``propagate_attributes(user_id, session_id)`` so
    the Sessions/Users tabs populate; see
    https://langfuse.com/docs/observability/sdk/instrumentation.
    """
    try:
        if not events or client is None:
            return False
        try:
            from langfuse import propagate_attributes
        except Exception:
            return False
        specs = [e for e in events
                 if isinstance(e, dict) and isinstance(e.get("name"), str)]
        if not specs:
            return False
        root = specs[0]
        children = specs[1:]
        try:
            with propagate_attributes(
                user_id=root.get("user_id"),
                session_id=root.get("session_id"),
                trace_name=root.get("trace_name"),
                tags=root.get("tags") or [],
            ):
                with client.start_as_current_observation(
                    as_type="span",
                    name=root.get("name"),
                    input=root.get("input"),
                    output=root.get("output"),
                    metadata=root.get("metadata") or {},
                ):
                    for spec in children:
                        kwargs = {"as_type": spec.get("as_type") or "span",
                                  "name": spec.get("name"),
                                  "input": spec.get("input"),
                                  "output": spec.get("output"),
                                  "metadata": spec.get("metadata") or {}}
                        if spec.get("model"):
                            kwargs["model"] = spec.get("model")
                        if spec.get("usage_details"):
                            kwargs["usage_details"] = spec.get(
                                "usage_details")
                        with client.start_as_current_observation(**kwargs):
                            pass
        except Exception:
            return False
        try:
            client.flush()
        except Exception:
            return False
        return True
    except Exception:
        return False


def post_trace(record: dict) -> bool:
    """Post one trace with child spans via the v4 SDK. Never raises.

    Returns True only after auth check plus an error-free post_batch run.
    """
    try:
        client = _make_client()
        if client is None:
            return False
        try:
            if not client.auth_check():
                return False
        except Exception:
            return False
        return bool(post_batch(sink_event(record), client))
    except Exception:
        return False


def deliver(record: dict) -> dict:
    """Persist via save_trace (file backup always) + SDK post when live.

    Returns {"stored": stored_record, "posted": bool, "mode": str}.
    Never raises.
    """
    try:
        stored = save_trace(record)
    except Exception:
        stored = {}
    try:
        if not live_post_enabled():
            try:
                mode = mode_reason()
            except Exception:
                mode = "degraded: no key; offline span-shape proof only"
            return {"stored": stored, "posted": False, "mode": mode}
        try:
            posted = bool(post_trace(record))
        except Exception:
            posted = False
        if posted:
            return {"stored": stored, "posted": True,
                    "mode": "live: posted to sink"}
        return {"stored": stored, "posted": False,
                "mode": "live: sink unreachable, file backup"}
    except Exception:
        try:
            return {"stored": stored, "posted": False, "mode": mode_reason()}
        except Exception:
            return {"stored": stored, "posted": False,
                    "mode": "degraded: no key; offline span-shape proof only"}


def _lookup_backup(trace_id: str) -> Optional[dict]:
    try:
        last = None
        with open(_backup_path(), "r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    entry = json.loads(line)
                except Exception:
                    continue
                if (isinstance(entry, dict)
                        and entry.get("trace_id") == trace_id):
                    last = entry
        if isinstance(last, dict):
            TRACE_STORE[trace_id] = dict(last)
            return dict(last)
    except Exception:
        pass
    return None
