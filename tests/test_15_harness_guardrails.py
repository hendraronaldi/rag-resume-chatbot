"""Harness guardrails on the live path (ticket 03): budget overflow maps to
400 before any model/agent cost on RAG/LEAD, history prunes oldest-first,
and loop breakers degrade to HTTP 200 with the full reply contract.
"""

import re
import sys
import time
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

TRACE_RE = re.compile(r"^trace-[0-9a-f]{12}$")

RAG_QUERY = "What programming languages are listed on the resume?"


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

    def complete(self, prompt: str):
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


_stub_heavy_imports()

import main  # noqa: E402


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
    assert body["mode"]


def test_rag_p1_overflow_returns_400_before_agent_cost(client, monkeypatch):
    http, fake_llm = client
    monkeypatch.setattr(main, "MAX_CONTEXT_TOKENS", 3)
    resp = http.post("/query-resume/", json={"query": RAG_QUERY})
    assert resp.status_code == 400
    assert resp.json()["detail"]
    assert resp.headers["X-Index-Build-Date"] == main.INDEX_BUILD_DATE
    assert FakeRAGAgent.calls == []
    assert fake_llm.prompts == []


def test_lead_p1_overflow_returns_400(client, monkeypatch):
    http, fake_llm = client
    monkeypatch.setattr(main, "MAX_CONTEXT_TOKENS", 3)
    query = "Please get back to me at jane.doe@example.com about the role."
    resp = http.post("/query-resume/", json={"query": query})
    assert resp.status_code == 400
    assert resp.headers["X-Index-Build-Date"] == main.INDEX_BUILD_DATE
    assert FakeRAGAgent.calls == []
    assert fake_llm.prompts == []


def test_rag_history_pruned_oldest_first(client, monkeypatch):
    http, _ = client
    monkeypatch.setattr(main, "MAX_CONTEXT_TOKENS", 60)
    seen = {}
    real_assemble = main.budget.assemble_context

    def spy(system, query, chunks, history, max_tokens):
        seen["in_history"] = list(history)
        ctx = real_assemble(system, query, chunks, history, max_tokens)
        seen["pruned"] = list(ctx["history"])
        return ctx

    monkeypatch.setattr(main.budget, "assemble_context", spy)
    history = ["note number %d about prior context" % i for i in range(12)]
    resp = http.post("/query-resume/", json={"query": RAG_QUERY, "history": history})
    assert resp.status_code == 200, resp.text
    _contract_ok(resp.json(), RAG_QUERY, "RAG")
    assert FakeRAGAgent.calls == [RAG_QUERY]
    pruned = seen["pruned"]
    assert len(pruned) < len(history)
    assert pruned == history[len(history) - len(pruned):]
    assert pruned[-1] == history[-1]


def test_stagnation_returns_degraded_200(client):
    http, fake_llm = client
    resp = http.post("/query-resume/", json={"query": RAG_QUERY, "history": [RAG_QUERY]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    _contract_ok(body, RAG_QUERY, "RAG")
    assert "loop" in body["message"] or "time limit" in body["message"]
    assert main.INDEX_BUILD_DATE not in body["message"]
    assert FakeRAGAgent.calls == []
    assert fake_llm.prompts == []


def test_time_budget_exceeded_returns_degraded_200(client, monkeypatch):
    http, _ = client
    wall_start = time.time()
    calls = {"n": 0}

    def fake_time():
        calls["n"] += 1
        if calls["n"] == 1:
            return wall_start
        return wall_start + 61.0

    monkeypatch.setattr(time, "time", fake_time)
    resp = http.post("/query-resume/", json={"query": RAG_QUERY})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    _contract_ok(body, RAG_QUERY, "RAG")
    assert "loop" in body["message"] or "time limit" in body["message"]
    assert main.INDEX_BUILD_DATE not in body["message"]
    assert FakeRAGAgent.calls == []
