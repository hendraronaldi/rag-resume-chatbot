"""History-enriched retrieval (ticket 02): a pronoun follow-up sent with
history must score on its antecedent terms, while retrieval without
history stays byte-identical.
"""

import sys
from types import ModuleType

from fastapi.testclient import TestClient

import retrieval
import router


def test_follow_up_with_history_retrieves_antecedent():
    ids = retrieval.retrieve(
        "Tell me more about it",
        history=["Rate limiting rejects abusive callers"],
    )
    assert ids[0] == "c17"


def test_same_query_without_history_falls_back_by_id():
    assert retrieval.retrieve("Tell me more about it") == ["c01", "c02", "c03"]


def test_non_string_history_dropped():
    ids = retrieval.retrieve(
        "Tell me more about it",
        history=[123, None, "Rate limiting rejects abusive callers"],
    )
    assert ids[0] == "c17"


def test_only_last_five_turns_score():
    history = ["Reindex automation fires webhooks"] + [
        "filler turn %d" % i for i in range(5)
    ]
    ids = retrieval.retrieve("Tell me more about it", history=history)
    assert "c13" not in ids


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


def test_endpoint_retrieval_query_carries_history(monkeypatch):
    captured = {}
    real_retrieve = retrieval.retrieve

    def _spy_retrieve(query, k=3, **kwargs):
        captured["query"] = query
        captured["history"] = kwargs.get("history")
        return real_retrieve(query, k=k, **kwargs)

    monkeypatch.setattr(main.router, "route_with_llm",
                        lambda *a, **k: router.RAG)
    monkeypatch.setattr(main.retrieval, "retrieve", _spy_retrieve)
    monkeypatch.setattr(main, "rag_agent", _FakeRAGAgent(settings=None))
    client = TestClient(main.app)
    resp = client.post("/query-resume/", json={
        "query": "Tell me more about it",
        "history": ["Rate limiting rejects abusive callers"],
    })
    assert resp.status_code == 200, resp.text
    assert captured["query"] == "Tell me more about it"
    assert captured["history"] == ["Rate limiting rejects abusive callers"]
