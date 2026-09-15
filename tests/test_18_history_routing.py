"""History-aware routing (ticket 01): a follow-up sent with history must
classify against its conversational context, while single-turn behavior
stays byte-identical.
"""

import sys
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

import router


class _CaptureLLM:
    def __init__(self, text='{"intent": "RAG"}'):
        self.text = text
        self.prompts = []

    def complete(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return self.text


def test_history_reaches_routing_prompt():
    llm = _CaptureLLM()
    intent = router.route_with_llm(
        "What is its estimated proficiency level?",
        llm,
        history=["Tell me about the payments ledger service"],
    )
    assert intent == router.RAG
    assert len(llm.prompts) == 1
    assert "Tell me about the payments ledger service" in llm.prompts[0]
    assert "What is its estimated proficiency level?" in llm.prompts[0]


def test_no_history_prompt_unchanged():
    llm = _CaptureLLM()
    query = "What programming languages are listed on the resume?"
    assert router.route_with_llm(query, llm) == router.RAG
    assert llm.prompts == [router._ROUTING_PROMPT + query]


def test_only_last_five_turns_used():
    llm = _CaptureLLM()
    history = ["turn-%d about ledgers" % i for i in range(7)]
    router.route_with_llm("What about it?", llm, history=history)
    prompt = llm.prompts[0]
    assert "turn-0" not in prompt
    assert "turn-1" not in prompt
    for i in range(2, 7):
        assert ("turn-%d" % i) in prompt


def test_non_string_history_dropped():
    llm = _CaptureLLM()
    intent = router.route_with_llm(
        "What about it?", llm, history=[123, None, "real turn"]
    )
    assert intent == router.RAG
    assert "real turn" in llm.prompts[0]


def test_unroutable_still_rejected_with_history():
    llm = _CaptureLLM()
    with pytest.raises(router.Unroutable):
        router.route_with_llm("   ", llm, history=["earlier"])
    assert llm.prompts == []


class _FailingLLM:
    def complete(self, prompt, **kwargs):
        raise ConnectionError("provider down")


def test_fallback_ignores_history_for_smalltalk_and_contact():
    history = ["Tell me about the payments ledger service"]
    assert router.route_with_llm(
        "Hello! Who am I chatting with?", _FailingLLM(), history=history
    ) == router.CHAT
    assert router.route_with_llm(
        "Reach me at jane.doe@example.com please.", _FailingLLM(),
        history=history,
    ) == router.LEAD_CAPTURE
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


def test_endpoint_forwards_history_to_router(monkeypatch):
    captured = {}

    def _fake_route(query, llm, **kwargs):
        captured["query"] = query
        captured["history"] = kwargs.get("history")
        return router.RAG

    monkeypatch.setattr(main.router, "route_with_llm", _fake_route)
    monkeypatch.setattr(main, "rag_agent", _FakeRAGAgent(settings=None))
    client = TestClient(main.app)
    resp = client.post("/query-resume/", json={
        "query": "What is its estimated proficiency level?",
        "history": ["Tell me about the payments ledger service"],
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["intent"] == "RAG"
    assert captured["history"] == ["Tell me about the payments ledger service"]
