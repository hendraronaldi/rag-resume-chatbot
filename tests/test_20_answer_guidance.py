"""100-word answer guidance (ticket 03): generation prompts must carry
the length bound and the offer-to-elaborate directive. Model output
length itself is non-deterministic, so these tests pin the instruction,
not the wording of any answer.
"""

import sys
from types import ModuleType

from fastapi.testclient import TestClient

import router


def _ensure_module(name: str) -> ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = ModuleType(name)
        module.__path__ = []
        sys.modules[name] = module
    return module


class _CaptureLLM:
    def __init__(self):
        self.prompts = []

    def complete(self, prompt, **kwargs):
        self.prompts.append(prompt)

        class _Resp:
            def __str__(self):
                return "CHAT reply"

        return _Resp()


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
    if not hasattr(pool_mod, "ModelPoolExhaustedError"):
        class _FakeExhausted(RuntimeError):
            pass

        pool_mod.ModelPoolExhaustedError = _FakeExhausted
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


def _chat_prompt(monkeypatch, query, history=None):
    fake_llm = _CaptureLLM()
    monkeypatch.setattr(main.Settings, "llm", fake_llm)
    monkeypatch.setattr(main, "rag_agent", _FakeRAGAgent(settings=None))
    client = TestClient(main.app)
    payload = {"query": query}
    if history is not None:
        payload["history"] = history
    resp = client.post("/query-resume/", json=payload)
    assert resp.status_code == 200, resp.text
    assert resp.json()["intent"] == "CHAT"
    assert len(fake_llm.prompts) == 1
    return fake_llm.prompts[0]


def test_chat_prompt_carries_word_bound(monkeypatch):
    prompt = _chat_prompt(monkeypatch, "Hello! Who am I chatting with?",
                         ["earlier"])
    assert "100 words" in prompt
    assert "elaborate" in prompt.lower()


def test_chat_prompt_still_grounds_in_history_and_query(monkeypatch):
    prompt = _chat_prompt(monkeypatch, "Hello! Who am I chatting with?",
                         ["earlier"])
    assert "earlier" in prompt
    assert "Hello! Who am I chatting with?" in prompt
    assert main.INDEX_BUILD_DATE not in prompt
    assert "last updated" not in prompt
