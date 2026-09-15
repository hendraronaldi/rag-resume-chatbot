"""Endpoint contract for ticket 02: live POST /query-resume/ routes via
router.route_with_llm() (LLM first, deterministic regex fallback) into
RAG / CHAT / LEAD_CAPTURE / OTHER and returns the frozen reply
contract (query + message/answer + trace_id + intent + index_build_date).

Heavy third-party modules (llama_index) are stubbed before importing main,
mirroring tests/test_13_live_build_date.py; the fake RAG agent and fake LLM
record calls so each branch can prove it used its own engine and no other.
"""

import os
import re
import sys
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

TRACE_RE = re.compile(r"^trace-[0-9a-f]{12}$")


def _ensure_module(name: str) -> ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = ModuleType(name)
        module.__path__ = []
        sys.modules[name] = module
    return module


class FakeRAGAgent:
    calls = []  # type: list

    def __init__(self, settings=None, index_build_date=None):
        self.index_build_date = index_build_date

    def query_resume(self, query: str) -> str:
        FakeRAGAgent.calls.append(query)
        return "RAG answer to: " + query


class FakeLLM:
    def __init__(self):
        self.prompts = []  # type: list

    def complete(self, prompt: str, **kwargs):
        self.prompts.append(prompt)

        class _Resp:
            def __str__(self):
                return "CHAT reply"

        return _Resp()


class FakeGemini:
    def __init__(self, **kwargs):
        pass


def _stub_heavy_imports() -> None:
    _ensure_module("llama_index")
    core_mod = _ensure_module("llama_index.core")
    if not hasattr(core_mod, "Settings"):
        setattr(core_mod, "Settings", type("Settings", (), {"llm": None}))
    llms_mod = _ensure_module("llama_index.llms")
    gemini_mod = _ensure_module("llama_index.llms.gemini")
    if not hasattr(gemini_mod, "Gemini"):
        setattr(gemini_mod, "Gemini", FakeGemini)
    setattr(llms_mod, "gemini", gemini_mod)
    setattr(sys.modules["llama_index"], "core", core_mod)
    setattr(sys.modules["llama_index"], "llms", llms_mod)

    pool_mod = sys.modules.get("app.model_pool")
    if pool_mod is None:
        pool_mod = ModuleType("app.model_pool")
        sys.modules["app.model_pool"] = pool_mod
    if not hasattr(pool_mod, "ModelPoolLLM"):
        class FakeModelPoolLLM:
            def __init__(self, *args, **kwargs):
                pass

        pool_mod.ModelPoolLLM = FakeModelPoolLLM
    if not hasattr(pool_mod, "ModelPoolExhaustedError"):
        class FakeExhausted(RuntimeError):
            pass

        pool_mod.ModelPoolExhaustedError = FakeExhausted
    if not hasattr(pool_mod, "ROUTING_MODEL_POOL"):
        pool_mod.ROUTING_MODEL_POOL = (
            "gemini-3.1-flash-lite",
            "gemini-3.5-flash-lite",
        )
    if not hasattr(pool_mod, "RAG_MODEL_POOL"):
        pool_mod.RAG_MODEL_POOL = (
            "gemini-3.5-flash",
            "gemini-3.6-flash",
            "gemini-3.7-flash",
            "gemini-3.8-flash",
        )
    if not hasattr(pool_mod, "CHAT_MODEL_POOL"):
        pool_mod.CHAT_MODEL_POOL = (
            "gemini-3.1-flash-lite",
            "gemini-3.5-flash-lite",
            "gemini-3-flash-preview",
        )

    agent_mod = ModuleType("app.agent")
    agent_mod.ResumeRAGAgent = FakeRAGAgent
    sys.modules["app.agent"] = agent_mod


# Stubs must install before `import main` below, so the import sits after
# executable code by necessity.
_stub_heavy_imports()

import main  # noqa: E402
import tracing  # noqa: E402


@pytest.fixture()
def client(monkeypatch):
    FakeRAGAgent.calls = []
    fake_llm = FakeLLM()
    monkeypatch.setattr(main.Settings, "llm", fake_llm)
    monkeypatch.setattr(main, "rag_agent", FakeRAGAgent(settings=None))
    return TestClient(main.app), fake_llm


def _contract_ok(body: dict, query: str, intent: str) -> None:
    assert body["query"] == query
    assert body["message"]
    assert body["answer"] == body["message"]
    assert TRACE_RE.match(body["trace_id"]), body["trace_id"]
    assert body["intent"] == intent
    assert body["index_build_date"] == main.INDEX_BUILD_DATE


def test_rag_intent_uses_agent_only(client):
    http, fake_llm = client
    query = "What programming languages are listed on the resume?"
    resp = http.post("/query-resume/", json={"query": query, "history": ["hello"]})
    assert resp.status_code == 200, resp.text
    _contract_ok(resp.json(), query, "RAG")
    assert resp.headers["X-Index-Build-Date"] == main.INDEX_BUILD_DATE
    assert FakeRAGAgent.calls == [query]
    assert fake_llm.prompts == []


def test_chat_intent_uses_llm_only_with_system_prompt_and_history(client):
    http, fake_llm = client
    query = "Hello! Who am I chatting with?"
    resp = http.post("/query-resume/", json={"query": query, "history": ["earlier"]})
    assert resp.status_code == 200, resp.text
    _contract_ok(resp.json(), query, "CHAT")
    assert FakeRAGAgent.calls == []
    assert len(fake_llm.prompts) == 1
    assert "Chat briefly" in fake_llm.prompts[0]
    assert "do not have that information yet" not in fake_llm.prompts[0]
    assert query in fake_llm.prompts[0]


def test_lead_capture_intent_redirects_with_no_calls(client):
    http, fake_llm = client
    query = "Please get back to me at jane.doe@example.com about the role."
    resp = http.post("/query-resume/", json={"query": query})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    _contract_ok(body, query, "LEAD_CAPTURE")
    assert "Contact" in body["message"]
    assert "mailto:" in body["message"]
    assert "linkedin.com" in body["message"]
    assert FakeRAGAgent.calls == []
    assert fake_llm.prompts == []


def test_other_intent_returns_capability_reply_with_no_calls(client, monkeypatch):
    http, fake_llm = client

    class _OtherLLM:
        def complete(self, prompt, **kwargs):
            return '{"intent": "OTHER"}'

    monkeypatch.setattr(main, "routing_llm", _OtherLLM())
    query = "What is the capital of France?"
    resp = http.post("/query-resume/", json={"query": query})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    _contract_ok(body, query, "OTHER")
    assert "outside what I cover" in body["message"]
    assert "portfolio assistant" in body["message"]
    assert FakeRAGAgent.calls == []
    assert fake_llm.prompts == []


def test_blank_query_fails_closed(client):
    http, _ = client
    resp = http.post("/query-resume/", json={"query": "   "})
    assert resp.status_code == 400
    assert resp.json()["detail"]
    assert resp.headers["X-Index-Build-Date"] == main.INDEX_BUILD_DATE


def test_oversize_query_fails_closed(client):
    http, _ = client
    resp = http.post("/query-resume/", json={"query": "x" * 2001})
    assert resp.status_code == 400
    assert resp.headers["X-Index-Build-Date"] == main.INDEX_BUILD_DATE


def test_non_string_query_fails_closed(client):
    http, _ = client
    resp = http.post("/query-resume/", json={"query": 123})
    assert resp.status_code == 400
    assert resp.headers["X-Index-Build-Date"] == main.INDEX_BUILD_DATE


def test_history_without_strings_is_dropped(client):
    http, _ = client
    query = "What programming languages are listed on the resume?"
    resp = http.post(
        "/query-resume/", json={"query": query, "history": [1, None, {"x": 1}]}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["intent"] == "RAG"


def test_trace_ids_unique_per_request(client):
    http, _ = client
    query = "What programming languages are listed on the resume?"
    first = http.post("/query-resume/", json={"query": query}).json()["trace_id"]
    second = http.post("/query-resume/", json={"query": query}).json()["trace_id"]
    assert TRACE_RE.match(first) and TRACE_RE.match(second)
    assert first != second


def test_live_path_never_uses_offline_stub(client):
    http, _ = client
    query = "What programming languages are listed on the resume?"
    body = http.post("/query-resume/", json={"query": query}).json()
    assert "knowledge base:" not in body["message"]
    assert "no chunks retrieved" not in body["message"]


def test_headers_propagate_into_trace_record(client, monkeypatch, tmp_path):
    http, _ = client
    backup = tmp_path / "traces.jsonl"
    monkeypatch.setenv("TRACE_BACKUP_PATH", str(backup))
    tracing.TRACE_STORE.clear()
    query = "What programming languages are listed on the resume?"
    resp = http.post(
        "/query-resume/",
        json={"query": query},
        headers={"X-User-Id": "user-1", "X-Session-Id": "sess-1"},
    )
    assert resp.status_code == 200, resp.text
    stored = tracing.get_trace(resp.json()["trace_id"])
    assert stored is not None
    assert stored.get("user_id") == "user-1"
    assert stored.get("session_id") == "sess-1"


def test_spans_valid_without_last_used_model(client, monkeypatch, tmp_path):
    pytest.importorskip("langfuse.api.resources.ingestion.types.trace_body")
    http, fake_llm = client
    assert getattr(fake_llm, "last_used_model", None) is None
    backup = tmp_path / "traces.jsonl"
    monkeypatch.setenv("TRACE_BACKUP_PATH", str(backup))
    tracing.TRACE_STORE.clear()
    query = "What programming languages are listed on the resume?"
    resp = http.post("/query-resume/", json={"query": query})
    assert resp.status_code == 200, resp.text
    stored = tracing.get_trace(resp.json()["trace_id"])
    assert stored is not None
    assert [s["name"] for s in stored["spans"]] == ["router", "retrieval", "generation"]
    events = tracing.sink_event(stored)
    assert events
    for event in events[1:]:
        assert event.body.metadata["model"] == ""
