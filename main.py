import json
import os
import time
from typing import Any, List, Optional

import grpc
import uvicorn
from dotenv import find_dotenv, load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from llama_index.core import Settings
from google import genai
from pydantic import BaseModel

import breakers
import budget
import retrieval
import router
import staleness
import tracing
from app.agent import ResumeRAGAgent
from app.config import get_settings
from app.model_pool import ModelPoolLLM

load_dotenv(find_dotenv())
settings = get_settings()
_genai_client = genai.Client(api_key=settings.GOOGLE_API_KEY)
Settings.llm = ModelPoolLLM(
    client=_genai_client,
    model_pool=settings.CHAT_LLM_POOL,
    provider_request_timeout_s=settings.PROVIDER_REQUEST_TIMEOUT_S,
    default_remaining_budget_s=settings.LLM_REMAINING_BUDGET_S,
)
routing_llm = ModelPoolLLM(
    client=_genai_client,
    model_pool=settings.ROUTING_LLM_POOL,
    provider_request_timeout_s=settings.PROVIDER_REQUEST_TIMEOUT_S,
    default_remaining_budget_s=settings.LLM_REMAINING_BUDGET_S,
)

# Check if index exists, if not, provide guidance
if not os.path.exists(settings.INDEX_PATH):
    print("ERROR: Vector index not found!")
    print("Please run 'python builder.py' (or 'make reindex') to create the index before starting the API")
    raise SystemExit(1)

# Build date stamped once at boot: live artifact wins, staleness fallback.
INDEX_BUILD_DATE = staleness.resolve_live_build_date(settings.INDEX_PATH)

# Initialize the RAG agent
rag_agent = ResumeRAGAgent(settings=settings, index_build_date=INDEX_BUILD_DATE)

# FastAPI application
app = FastAPI(
    title="Resume RAG API",
    description="AI-powered API to query personal resume using Persistent RAG"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request model
# NOTE: `query`/`history` are intentionally `Any` (not `str`/`List[str]`)
# so non-string or missing queries map to HTTP 400 via `_fail` below.
# Strict Pydantic typing would return 422 instead, breaking the ticket 02
# fail-closed-with-400 contract for blank/oversized/non-string queries.
class QueryRequest(BaseModel):
    query: Any = None
    history: Optional[Any] = None


LEAD_CAPTURE_REPLY = (
    "Thanks for getting in touch! "
    "Please reach out through the Contact section below "
    "and we will get back to you soon."
)

OUT_OF_SCOPE_REPLY = (
    "I can't help with that — it's outside what I cover. "
    "I'm Hendra's portfolio assistant: I answer questions about his resume, "
    "skills, experience, and projects from the knowledge base, "
    "I can chat briefly, and I can point you to the Contact section "
    "to get in touch."
)

MAX_HISTORY_MESSAGES = 20
MAX_CONTEXT_TOKENS = 2000


def _fail(status_code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail,
                         headers={"X-Index-Build-Date": INDEX_BUILD_DATE})


def _sanitize_history(raw: Any) -> List[str]:
    """Keep the last MAX_HISTORY_MESSAGES string entries; reject non-lists with 400."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise _fail(400, "history must be a list of strings")
    kept = [m for m in raw if isinstance(m, str)]
    return kept[-MAX_HISTORY_MESSAGES:]


def _elapsed_ms(start_perf: float) -> float:
    try:
        return max(0.0, (time.perf_counter() - start_perf) * 1000.0)
    except Exception:
        return 0.0


def _count(text: Any) -> int:
    try:
        return budget.count_tokens(text) if isinstance(text, str) else 0
    except Exception:
        return 0


def _request_identity(http_request: Any) -> "tuple[str, str]":
    try:
        headers = getattr(http_request, "headers", {}) or {}
        try:
            user_id = headers.get("x-user-id", "")
        except Exception:
            user_id = ""
        try:
            session_id = headers.get("x-session-id", "")
        except Exception:
            session_id = ""
        if not isinstance(user_id, str):
            user_id = ""
        if not isinstance(session_id, str):
            session_id = ""
        return user_id, session_id
    except Exception:
        return "", ""


def _llm_model(llm: Any) -> Optional[str]:
    try:
        model = getattr(llm, "last_used_model", None)
    except Exception:
        return None
    return model if isinstance(model, str) else None


def _rag_llm_model() -> Optional[str]:
    try:
        return _llm_model(getattr(rag_agent, "llm", None))
    except Exception:
        return None


def _degraded_reply(query: str, rec: tracing.Recorder, intent: str,
                    user_id: str = "", session_id: str = "") -> JSONResponse:
    note = ("I stopped early to respect the loop/time limit instead of "
            "running on; my knowledge base was last updated on "
            + INDEX_BUILD_DATE + ". Please try a narrower question.")
    return _reply(query, note, rec, intent, user_id, session_id)


def _should_break_safe(history: List[str], query: str,
                       start_wall: float) -> bool:
    try:
        previous = breakers.call_hash(history[-1]) if history else ""
        current = breakers.call_hash(query)
        return bool(breakers.should_break(
            steps_taken=2, previous_hash=previous, current_hash=current,
            start_t=start_wall, now_t=time.time()))
    except Exception:
        return False


def _over_budget_safe(start_wall: float) -> bool:
    try:
        return bool(breakers.over_time_budget(start_wall, time.time()))
    except Exception:
        return False


def _persist_trace_safe(rec: tracing.Recorder, intent: str,
                        query: str = "", answer: str = "",
                        user_id: str = "", session_id: str = "") -> str:
    try:
        try:
            mode = tracing.mode_reason()
        except Exception:
            mode = "degraded: no key; offline span-shape proof only"
        try:
            ingestion = tracing.ingestion_event(rec) if tracing.keyed_mode() else None
        except Exception:
            ingestion = None
        try:
            result = tracing.deliver({
                "trace_id": rec.trace_id,
                "intent": intent,
                "query": query,
                "answer": answer,
                "spans": [dict(s) for s in rec.spans],
                "mode": mode,
                "ingestion": ingestion,
                "index_build_date": INDEX_BUILD_DATE,
                "user_id": user_id,
                "session_id": session_id,
            })
        except Exception:
            result = None
        if isinstance(result, dict) and isinstance(result.get("mode"), str):
            return result["mode"]
        return mode
    except Exception:
        pass
    try:
        return tracing.mode_reason()
    except Exception:
        return "degraded: no key; offline span-shape proof only"


def _reply(query: str, answer: str, rec: tracing.Recorder, intent: str,
           user_id: str = "", session_id: str = "") -> JSONResponse:
    mode = _persist_trace_safe(rec, intent, query, answer, user_id, session_id)
    return JSONResponse(
        status_code=200,
        content={"query": query, "message": answer, "answer": answer,
                 "trace_id": rec.trace_id, "intent": intent,
                 "index_build_date": INDEX_BUILD_DATE,
                 "mode": mode},
        headers={"X-Index-Build-Date": INDEX_BUILD_DATE},
    )


def _answer_chat(query: str, history: List[str]) -> str:
    """Answer smalltalk via LLM from system prompt + history only; no retrieval. Budget overflow maps to 400."""
    system = staleness.build_system_prompt(INDEX_BUILD_DATE)
    try:
        ctx = budget.assemble_context(system, query, [], history,
                                      MAX_CONTEXT_TOKENS)
    except budget.BudgetExceeded as exc:
        raise _fail(400, str(exc) or "400: context budget exceeded")
    prompt = (ctx["system"] + "\nAnswer in at most 100 words. "
              "If more detail would help, end with a one-line offer "
              "to elaborate.\n"
              + "\n".join(ctx["history"] + [ctx["query"]]))
    return str(Settings.llm.complete(
        prompt, remaining_budget_s=settings.LLM_REMAINING_BUDGET_S))


# API endpoint
@app.post("/query-resume/")
async def query_resume(request: QueryRequest, http_request: Request):
    """
    Endpoint to query the resume using natural language

    :param request: Query about the resume
    :return: Relevant information from the resume
    """
    req_start_wall = time.time()
    user_id, session_id = _request_identity(http_request)
    if not isinstance(request.query, str):
        raise _fail(400, "query must be a string")
    history = _sanitize_history(request.history)
    rec = tracing.Recorder()
    try:
        t0 = time.perf_counter()
        route_error = None
        try:
            intent = router.route_with_llm(
                request.query, routing_llm, history=history,
                remaining_budget_s=settings.LLM_REMAINING_BUDGET_S)
        except Exception as exc:
            route_error = exc
        rec.span("router", tokens=_count(request.query),
                 latency_ms=_elapsed_ms(t0), input=request.query,
                 output=intent if route_error is None else "UNROUTABLE",
                 model=_llm_model(routing_llm))
        if route_error is not None:
            raise route_error

        if intent == router.RAG:
            system = staleness.build_system_prompt(INDEX_BUILD_DATE)
            try:
                chunk_ids = retrieval.retrieve(
                    request.query, k=3, history=history)
            except Exception:
                chunk_ids = []
            chunks_for_budget = [
                {"rank": i + 1, "text": retrieval.CHUNKS[cid]}
                for i, cid in enumerate(chunk_ids)
                if isinstance(cid, str) and cid in retrieval.CHUNKS
            ]
            try:
                ctx = budget.assemble_context(
                    system, request.query, chunks_for_budget,
                    history, MAX_CONTEXT_TOKENS)
            except budget.BudgetExceeded as exc:
                raise _fail(400, str(exc) or "400: context budget exceeded")
            history = ctx["history"]
            if _should_break_safe(history, request.query, req_start_wall):
                t0 = time.perf_counter()
                rec.span("retrieval", tokens=_count(request.query),
                         latency_ms=_elapsed_ms(t0), input=request.query,
                         output="DEGRADED", model=None)
                t0 = time.perf_counter()
                rec.span("generation", tokens=_count(request.query),
                         latency_ms=_elapsed_ms(t0), input=request.query,
                         output="DEGRADED", model=None)
                return _degraded_reply(request.query, rec, intent,
                                       user_id, session_id)
            t0 = time.perf_counter()
            answer = str(rag_agent.query_resume(request.query))
            retrieval_latency = _elapsed_ms(t0)
            rec.span("retrieval",
                     tokens=_count(request.query) + _count(answer),
                     latency_ms=retrieval_latency, input=request.query,
                     output=chunk_ids, model=None)
            if _over_budget_safe(req_start_wall):
                t0 = time.perf_counter()
                rec.span("generation", tokens=_count(answer),
                         latency_ms=_elapsed_ms(t0), input=request.query,
                         output="DEGRADED", model=None)
                return _degraded_reply(request.query, rec, intent,
                                       user_id, session_id)
            t0 = time.perf_counter()
            rec.span("generation", tokens=_count(answer),
                     latency_ms=_elapsed_ms(t0), input=request.query,
                     output=answer, model=_rag_llm_model())
        elif intent == router.CHAT:
            t0 = time.perf_counter()
            rec.span("retrieval", tokens=_count(request.query),
                     latency_ms=_elapsed_ms(t0), input=request.query,
                     output="BYPASSED", model=None)
            if _should_break_safe(history, request.query, req_start_wall):
                t0 = time.perf_counter()
                rec.span("generation", tokens=_count(request.query),
                         latency_ms=_elapsed_ms(t0), input=request.query,
                         output="DEGRADED", model=None)
                return _degraded_reply(request.query, rec, intent,
                                       user_id, session_id)
            t0 = time.perf_counter()
            answer = _answer_chat(request.query, history)
            generation_latency = _elapsed_ms(t0)
            if _over_budget_safe(req_start_wall):
                rec.span("generation",
                         tokens=_count(answer) + _count(request.query),
                         latency_ms=generation_latency, input=request.query,
                         output="DEGRADED", model=None)
                return _degraded_reply(request.query, rec, intent,
                                       user_id, session_id)
            rec.span("generation",
                     tokens=_count(answer) + _count(request.query),
                     latency_ms=generation_latency, input=request.query,
                     output=answer, model=_llm_model(Settings.llm))
        elif intent == router.LEAD_CAPTURE:
            system = staleness.build_system_prompt(INDEX_BUILD_DATE)
            try:
                budget.assemble_context(system, request.query, [],
                                        history, MAX_CONTEXT_TOKENS)
            except budget.BudgetExceeded as exc:
                raise _fail(400, str(exc) or "400: context budget exceeded")
            if _should_break_safe(history, request.query, req_start_wall):
                t0 = time.perf_counter()
                rec.span("retrieval", tokens=_count(request.query),
                         latency_ms=_elapsed_ms(t0), input=request.query,
                         output="BYPASSED", model=None)
                t0 = time.perf_counter()
                rec.span("generation", tokens=_count(request.query),
                         latency_ms=_elapsed_ms(t0), input=request.query,
                         output="DEGRADED", model=None)
                return _degraded_reply(request.query, rec, intent,
                                       user_id, session_id)
            t0 = time.perf_counter()
            rec.span("retrieval", tokens=_count(request.query),
                     latency_ms=_elapsed_ms(t0), input=request.query,
                     output="BYPASSED", model=None)
            t0 = time.perf_counter()
            answer = LEAD_CAPTURE_REPLY
            rec.span("generation", tokens=_count(answer),
                     latency_ms=_elapsed_ms(t0), input=request.query,
                     output=answer, model=None)
        else:
            system = staleness.build_system_prompt(INDEX_BUILD_DATE)
            try:
                budget.assemble_context(system, request.query, [],
                                        history, MAX_CONTEXT_TOKENS)
            except budget.BudgetExceeded as exc:
                raise _fail(400, str(exc) or "400: context budget exceeded")
            if _should_break_safe(history, request.query, req_start_wall):
                t0 = time.perf_counter()
                rec.span("retrieval", tokens=_count(request.query),
                         latency_ms=_elapsed_ms(t0), input=request.query,
                         output="BYPASSED", model=None)
                t0 = time.perf_counter()
                rec.span("generation", tokens=_count(request.query),
                         latency_ms=_elapsed_ms(t0), input=request.query,
                         output="DEGRADED", model=None)
                return _degraded_reply(request.query, rec, intent,
                                       user_id, session_id)
            t0 = time.perf_counter()
            rec.span("retrieval", tokens=_count(request.query),
                     latency_ms=_elapsed_ms(t0), input=request.query,
                     output="BYPASSED", model=None)
            t0 = time.perf_counter()
            answer = OUT_OF_SCOPE_REPLY
            rec.span("generation", tokens=_count(answer),
                     latency_ms=_elapsed_ms(t0), input=request.query,
                     output=answer, model=None)
        return _reply(request.query, answer, rec, intent, user_id, session_id)
    except HTTPException:
        raise
    except router.Unroutable as e:
        raise _fail(400, str(e) or "400: query is unroutable")
    except Exception as e:
        if hasattr(e, "response"):
            if isinstance(e.response, grpc.RpcError):
                if e.response.code() == grpc.StatusCode.RESOURCE_EXHAUSTED:
                    print(f"Quota Exceeded Error:")
                    print(f"  Status Code: {e.response.code().name}") # This gives you "RESOURCE_EXHAUSTED"
                    print(f"  Details: {e.response.details()}") # This gives you the detailed message
                    print(f"  More info: {e.response.debug_error_string()}")
                    raise HTTPException(status_code=429, detail=str(e),
                                        headers={"X-Index-Build-Date": INDEX_BUILD_DATE})
        else:
            # Re-raise other exceptions
            raise HTTPException(status_code=500, detail=str(e),
                                headers={"X-Index-Build-Date": INDEX_BUILD_DATE})

# Feedback endpoint
@app.post("/feedback/")
async def receive_feedback(feedback_data: dict, http_request: Request):
    """
    Endpoint to validate a canonical feedback event and tag its trace.

    :param feedback_data: The feedback data as a JSON object.
    :return: A confirmation message with trace_id and vote.
    """
    try:
        _request_identity(http_request)
    except Exception:
        pass
    try:
        errors = tracing.validate_feedback(feedback_data)
    except Exception:
        errors = ["malformed feedback event"]
    if errors:
        raise _fail(400, "; ".join(errors))
    trace_id = feedback_data.get("trace_id")
    if not isinstance(trace_id, str) or not trace_id:
        raise _fail(404, "unknown trace_id")
    try:
        stored = tracing.get_trace(trace_id)
    except Exception:
        stored = None
    if not isinstance(stored, dict):
        raise _fail(404, "unknown trace_id")
    try:
        tagged = tracing.tag_trace_with_feedback(stored, feedback_data)
    except Exception:
        raise _fail(400, "malformed feedback event")
    if not isinstance(tagged, dict) or not tagged.get("ok"):
        errs = tagged.get("errors", []) if isinstance(tagged, dict) else []
        detail = "; ".join(errs) if errs else "feedback rejected"
        if any("does not match" in str(e) for e in errs):
            raise _fail(404, detail)
        raise _fail(400, detail)
    try:
        tracing.save_trace(tagged["trace"])
    except Exception:
        pass
    try:
        tracing.deliver(tagged["trace"])
    except Exception:
        pass
    print("Received feedback payload:")
    print(json.dumps(feedback_data, indent=4))
    return {"message": "Feedback received successfully",
            "trace_id": trace_id, "vote": feedback_data.get("vote")}

# Optional: Health check endpoint
@app.get("/")
async def health_check():
    return {"status": "healthy"}

# Run with: uvicorn main:app --reload
if __name__ == "__main__":
    uvicorn.run(
        "main:app", host="0.0.0.0"
    )
