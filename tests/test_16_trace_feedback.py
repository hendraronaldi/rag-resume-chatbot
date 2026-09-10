"""Trace sink + feedback tagging round-trip (ticket 04).

Live-path seams only: POST /query-resume/ persists one trace (router /
retrieval / generation spans with token cost + measured latency) to the
in-memory store with JSONL file backup; POST /feedback/ validates the
canonical event and tags the matching trace. Mismatched trace ids and
overlong text fail closed.
"""

import re
import sys
from contextlib import contextmanager
from types import ModuleType
from typing import Any

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
    llm: Any = None

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
import tracing  # noqa: E402


@pytest.fixture()
def client(monkeypatch, tmp_path):
    FakeRAGAgent.calls = []
    fake_llm = FakeLLM()
    monkeypatch.setattr(main.Settings, "llm", fake_llm)
    monkeypatch.setattr(main, "rag_agent", FakeRAGAgent(settings=None))
    backup = tmp_path / "traces.jsonl"
    monkeypatch.setenv("TRACE_BACKUP_PATH", str(backup))
    tracing.TRACE_STORE.clear()
    return TestClient(main.app), backup


def test_trace_persisted_per_request_with_three_spans(client):
    http, backup = client
    resp = http.post("/query-resume/", json={"query": RAG_QUERY})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert TRACE_RE.match(body["trace_id"]), body["trace_id"]
    assert body["mode"]

    stored = tracing.get_trace(body["trace_id"])
    assert stored is not None
    assert stored["trace_id"] == body["trace_id"]
    assert stored["intent"] == body["intent"]
    assert stored["mode"] == body["mode"]
    names = [s["name"] for s in stored["spans"]]
    assert names == ["router", "retrieval", "generation"]
    for span in stored["spans"]:
        assert isinstance(span["tokens"], int)
        assert isinstance(span["latency_ms"], (int, float))

    lines = backup.read_text().strip().splitlines()
    assert len(lines) == 1
    import json as _json

    entry = _json.loads(lines[0])
    assert entry["trace_id"] == body["trace_id"]


def test_feedback_event_round_trip_tags_correct_trace(client):
    http, _ = client
    trace_id = http.post("/query-resume/", json={"query": RAG_QUERY}).json()["trace_id"]
    resp = http.post(
        "/feedback/", json={"trace_id": trace_id, "vote": "down", "text": "too vague"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["trace_id"] == trace_id
    assert body["vote"] == "down"

    stored = tracing.get_trace(trace_id)
    assert stored is not None
    assert stored["feedback"]["vote"] == "down"
    assert stored["feedback"]["text"] == "too vague"
    assert stored["feedback"]["trace_id"] == trace_id


def test_mismatched_trace_id_fails_closed(client):
    http, _ = client
    trace_id = http.post("/query-resume/", json={"query": RAG_QUERY}).json()["trace_id"]
    assert trace_id
    resp = http.post(
        "/feedback/", json={"trace_id": "trace-deadbeef1234", "vote": "up"}
    )
    assert resp.status_code == 404
    assert resp.headers["X-Index-Build-Date"] == main.INDEX_BUILD_DATE


def test_overlong_text_rejected_never_truncated(client):
    http, _ = client
    trace_id = http.post("/query-resume/", json={"query": RAG_QUERY}).json()["trace_id"]
    resp = http.post(
        "/feedback/",
        json={"trace_id": trace_id, "vote": "down", "text": "x" * 2001},
    )
    assert resp.status_code == 400
    assert resp.headers["X-Index-Build-Date"] == main.INDEX_BUILD_DATE
    stored = tracing.get_trace(trace_id)
    assert stored is not None
    assert "feedback" not in stored


class _FakeObservation:
    """Stand-in for a v4 observation context manager (captures kwargs)."""

    def __init__(self, calls, kwargs):
        self._calls = calls
        self._kwargs = dict(kwargs)

    def __enter__(self):
        self._calls.append(("observation", dict(self._kwargs)))
        return self

    def __exit__(self, *exc):
        return False


class _FakeV4Client:
    """Stand-in for the v4 Langfuse client (captures observations)."""

    def __init__(self, calls, fail=False, flush_fail=False):
        self._calls = calls
        self._fail = fail
        self._flush_fail = flush_fail

    def auth_check(self):
        self._calls.append(("auth",))
        if self._fail:
            raise ConnectionError("sink down")
        return True

    def start_as_current_observation(self, **kwargs):
        if self._fail:
            raise ConnectionError("sink down")
        return _FakeObservation(self._calls, kwargs)

    def flush(self):
        self._calls.append(("flush",))
        if self._fail or self._flush_fail:
            raise ConnectionError("sink down")


@contextmanager
def _fake_propagate(calls, **kwargs):
    """Stand-in for langfuse.propagate_attributes (captures kwargs)."""
    calls.append(("propagate", dict(kwargs)))
    yield None


def _patch_v4_sink(monkeypatch, calls, fail=False, flush_fail=False):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_LIVE", "1")
    monkeypatch.setattr(
        tracing, "_make_client",
        lambda: _FakeV4Client(calls, fail=fail, flush_fail=flush_fail),
    )
    monkeypatch.setattr(
        "langfuse.propagate_attributes",
        lambda **kwargs: _fake_propagate(calls, **kwargs),
    )


def test_live_post_delivers_valid_batch_to_sink(client, monkeypatch):
    http, backup = client
    calls = []

    _patch_v4_sink(monkeypatch, calls)

    resp = http.post("/query-resume/", json={"query": RAG_QUERY})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mode"] == "live: posted to sink"

    assert ("auth",) in calls
    assert ("flush",) in calls
    observations = [c[1] for c in calls if c[0] == "observation"]
    assert [o["name"] for o in observations] == [
        "rag-chat [RAG]", "router", "retrieval", "generation"]
    root = observations[0]
    assert root["as_type"] == "span"
    assert root["input"] == RAG_QUERY
    assert "RAG answer to:" in root["output"]
    assert root["metadata"]["trace_id"] == body["trace_id"]
    assert root["metadata"]["intent"] == "RAG"
    for child in observations[1:]:
        assert child["input"] == RAG_QUERY
        assert isinstance(int(child["metadata"]["tokens"]), int)
        assert isinstance(float(child["metadata"]["latency_ms"]), (int, float))
    by_name = {o["name"]: o for o in observations[1:]}
    assert by_name["generation"]["as_type"] == "generation"
    assert by_name["generation"]["usage_details"]["total"] >= 0
    assert "RAG answer to:" in by_name["generation"]["output"]

    propagates = [c[1] for c in calls if c[0] == "propagate"]
    assert len(propagates) == 1
    assert propagates[0]["trace_name"] == "rag-chat [RAG]"
    assert propagates[0]["tags"] == ["RAG"]

    lines = backup.read_text().strip().splitlines()
    assert len(lines) == 1
    import json as _json

    assert _json.loads(lines[0])["trace_id"] == body["trace_id"]


def test_live_trace_carries_user_and_session_ids(client, monkeypatch):
    http, _ = client
    calls = []

    _patch_v4_sink(monkeypatch, calls)

    resp = http.post(
        "/query-resume/",
        json={"query": RAG_QUERY},
        headers={"X-User-Id": "user-123", "X-Session-Id": "session-456"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["mode"] == "live: posted to sink"

    propagates = [c[1] for c in calls if c[0] == "propagate"]
    assert len(propagates) == 1
    assert propagates[0]["user_id"] == "user-123"
    assert propagates[0]["session_id"] == "session-456"

    observations = [c[1] for c in calls if c[0] == "observation"]
    assert observations


def test_live_failure_falls_back_to_file_backup(client, monkeypatch):
    import json as _json

    http, backup = client
    _patch_v4_sink(monkeypatch, [], fail=True)

    resp = http.post("/query-resume/", json={"query": RAG_QUERY})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mode"] == "live: sink unreachable, file backup"

    lines = backup.read_text().strip().splitlines()
    assert len(lines) == 1
    assert _json.loads(lines[0])["trace_id"] == body["trace_id"]


def test_live_flush_failure_falls_back_to_file_backup(client, monkeypatch):
    import json as _json

    http, backup = client
    calls = []
    _patch_v4_sink(monkeypatch, calls, flush_fail=True)

    resp = http.post("/query-resume/", json={"query": RAG_QUERY})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mode"] == "live: sink unreachable, file backup"

    lines = backup.read_text().strip().splitlines()
    assert len(lines) == 1
    assert _json.loads(lines[0])["trace_id"] == body["trace_id"]


class _ModelLLM:
    def __init__(self, model):
        self.prompts = []  # type: list
        self.last_used_model = model

    def complete(self, prompt: str, **kwargs):
        self.prompts.append(prompt)
        return FakeLLM().complete(prompt)


class _ModelRoutingLLM:
    def __init__(self, model):
        self.last_used_model = model

    def complete(self, prompt, **kwargs):
        return '{"intent": "RAG"}'


def test_generation_spans_carry_winning_model(client, monkeypatch):
    http, _ = client
    monkeypatch.setattr(main, "routing_llm", _ModelRoutingLLM("gemini-3.1-flash-lite"))
    monkeypatch.setattr(main.Settings, "llm", _ModelLLM("gemini-3.5-flash-lite"))
    agent = FakeRAGAgent(settings=None)
    agent.llm = _ModelLLM("gemini-3.5-flash")
    monkeypatch.setattr(main, "rag_agent", agent)

    resp = http.post("/query-resume/", json={"query": RAG_QUERY})
    assert resp.status_code == 200, resp.text
    stored = tracing.get_trace(resp.json()["trace_id"])
    assert stored is not None
    by_name = {s["name"]: s for s in stored["spans"]}
    assert by_name["router"].get("model") == "gemini-3.1-flash-lite"
    assert by_name["generation"].get("model") == "gemini-3.5-flash"


def test_traces_carry_user_and_session_metadata(client):
    http, _ = client
    resp = http.post(
        "/query-resume/",
        json={"query": RAG_QUERY},
        headers={"X-User-Id": "u-123", "X-Session-Id": "s-456"},
    )
    assert resp.status_code == 200, resp.text
    stored = tracing.get_trace(resp.json()["trace_id"])
    assert stored is not None
    assert stored.get("user_id") == "u-123"
    assert stored.get("session_id") == "s-456"


def test_sink_carries_model_and_identity_metadata(client, monkeypatch):
    http, _ = client
    monkeypatch.setattr(main, "routing_llm", _ModelRoutingLLM("gemini-3.1-flash-lite"))
    agent = FakeRAGAgent(settings=None)
    agent.llm = _ModelLLM("gemini-3.5-flash")
    monkeypatch.setattr(main, "rag_agent", agent)

    resp = http.post(
        "/query-resume/",
        json={"query": RAG_QUERY},
        headers={"X-User-Id": "u-123", "X-Session-Id": "s-456"},
    )
    assert resp.status_code == 200, resp.text
    stored = tracing.get_trace(resp.json()["trace_id"])
    assert stored is not None
    specs = tracing.sink_event(stored)
    assert specs
    root, children = specs[0], specs[1:]
    assert root["user_id"] == "u-123"
    assert root["session_id"] == "s-456"
    assert root["trace_name"] == "rag-chat [RAG]"
    assert root["tags"] == ["RAG"]
    by_name = {s["name"]: s for s in children}
    assert by_name["router"]["metadata"]["model"] == "gemini-3.1-flash-lite"
    assert by_name["generation"]["model"] == "gemini-3.5-flash"
    assert by_name["generation"]["as_type"] == "generation"
    assert by_name["generation"]["usage_details"]["total"] >= 0
    assert "model" not in by_name["retrieval"]


def test_feedback_reposts_tagged_trace_to_sink(client, monkeypatch):
    http, _ = client
    trace_id = http.post("/query-resume/", json={"query": RAG_QUERY}).json()["trace_id"]
    delivered = []
    real_deliver = tracing.deliver

    def _capture(record):
        delivered.append(record)
        return real_deliver(record)

    monkeypatch.setattr(tracing, "deliver", _capture)
    resp = http.post(
        "/feedback/", json={"trace_id": trace_id, "vote": "up", "text": "helpful"}
    )
    assert resp.status_code == 200, resp.text
    assert delivered
    assert delivered[0].get("trace_id") == trace_id
    assert delivered[0].get("feedback", {}).get("vote") == "up"
    stored = tracing.get_trace(trace_id)
    assert stored is not None
    assert stored["feedback"]["vote"] == "up"


def test_feedback_post_includes_feedback_in_trace_metadata(client, monkeypatch):
    http, _ = client
    posted = []
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_LIVE", "1")
    monkeypatch.setattr(tracing, "post_trace", lambda record: posted.append(record) or True)
    trace_id = http.post("/query-resume/", json={"query": RAG_QUERY}).json()["trace_id"]
    resp = http.post("/feedback/", json={"trace_id": trace_id, "vote": "down"})
    assert resp.status_code == 200, resp.text
    assert posted
    assert posted[-1].get("feedback", {}).get("vote") == "down"
    specs = tracing.sink_event(posted[-1])
    assert specs
    import json as _json

    assert _json.loads(specs[0]["metadata"]["feedback"])["vote"] == "down"
