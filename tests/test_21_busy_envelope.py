"""Busy envelope and neutral replies (ticket BE 02): provider exhaustion
must return a normal busy reply, the error path must never resolve
empty, and no reply text may mention update dates.
"""

import sys
from types import ModuleType

from fastapi.testclient import TestClient

import router


class _PoolExhausted(RuntimeError):
    pass


def _ensure_module(name: str) -> ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = ModuleType(name)
        module.__path__ = []
        sys.modules[name] = module
    return module


class _FakeRAGAgent:
    def __init__(self, settings=None, index_build_date=None):
        pass

    def query_resume(self, query: str) -> str:
        return "RAG answer to: " + query


class _ExhaustedRAGAgent:
    def __init__(self, settings=None, index_build_date=None):
        pass

    def query_resume(self, query: str) -> str:
        raise main.ModelPoolExhaustedError(
            "pool exhausted after ordered attempts")


def _stub_heavy_imports() -> None:
    _ensure_module("llama_index")
    core_mod = _ensure_module("llama_index.core")
    if not hasattr(core_mod, "Settings"):
        setattr(core_mod, "Settings", type("Settings", (), {"llm": None}))
    pool_mod = sys.modules.get("app.model_pool")
    if pool_mod is None:
        pool_mod = ModuleType("app.model_pool")
        sys.modules["app.model_pool"] = pool_mod
    if not hasattr(pool_mod, "ModelPoolLLM"):
        class _FakeModelPoolLLM:
            def __init__(self, *args, **kwargs):
                pass

        pool_mod.ModelPoolLLM = _FakeModelPoolLLM
    if not hasattr(pool_mod, "ModelPoolExhaustedError"):
        pool_mod.ModelPoolExhaustedError = _PoolExhausted
    if not hasattr(pool_mod, "ROUTING_MODEL_POOL"):
        pool_mod.ROUTING_MODEL_POOL = ("gemini-3.1-flash-lite",)
    if not hasattr(pool_mod, "RAG_MODEL_POOL"):
        pool_mod.RAG_MODEL_POOL = ("gemini-3.5-flash",)
    if not hasattr(pool_mod, "CHAT_MODEL_POOL"):
        pool_mod.CHAT_MODEL_POOL = ("gemini-3.1-flash-lite",)
    agent_mod = ModuleType("app.agent")
    agent_mod.ResumeRAGAgent = _FakeRAGAgent
    sys.modules["app.agent"] = agent_mod


_stub_heavy_imports()

import main  # noqa: E402


def _client(monkeypatch, rag_agent):
    monkeypatch.setattr(main.router, "route_with_llm",
                        lambda *a, **k: router.RAG)
    monkeypatch.setattr(main, "rag_agent", rag_agent)
    return TestClient(main.app)


def test_exhaustion_returns_200_busy_envelope(monkeypatch):
    client = _client(monkeypatch, _ExhaustedRAGAgent(settings=None))
    query = "What programming languages are listed on the resume?"
    resp = client.post("/query-resume/", json={"query": query})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["intent"] == "RAG"
    assert body["message"]
    assert body["answer"] == body["message"]
    assert body["message"] == main.BUSY_REPLY


def test_busy_reply_mentions_no_dates(monkeypatch):
    client = _client(monkeypatch, _ExhaustedRAGAgent(settings=None))
    body = client.post(
        "/query-resume/", json={"query": "Tell me about the background"}
    ).json()
    assert main.INDEX_BUILD_DATE not in body["message"]
    assert "last updated" not in body["message"]


def test_non_grpc_error_with_response_raises_500_not_null(monkeypatch):
    class _RestError(Exception):
        def __init__(self):
            super().__init__("503 upstream")
            self.response = object()

    class _RestRAGAgent:
        def __init__(self, settings=None, index_build_date=None):
            pass

        def query_resume(self, query: str) -> str:
            raise _RestError()

    client = _client(monkeypatch, _RestRAGAgent(settings=None))
    resp = client.post("/query-resume/",
                       json={"query": "Tell me about the background"})
    assert resp.status_code == 500
    assert resp.json()["detail"]
