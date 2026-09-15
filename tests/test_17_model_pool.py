import asyncio
import importlib
import inspect
import sys
import threading

import httpx
import pytest


def _restore_real_dependency(package_name, required_attribute):
    """Discard a deficient collection stub before importing the real package."""
    module = sys.modules.get(package_name)
    if module is None or hasattr(module, required_attribute):
        return
    prefix = package_name.split(".", 1)[0]
    for name in tuple(sys.modules):
        if name == prefix or name.startswith(prefix + "."):
            sys.modules.pop(name, None)
    importlib.invalidate_caches()


_restore_real_dependency("google.genai", "errors")
_restore_real_dependency("llama_index.core", "VectorStoreIndex")
_restore_real_dependency("app.model_pool", "ModelPoolController")

from google.genai import errors
from llama_index.core import VectorStoreIndex
from llama_index.core.base.llms.types import CompletionResponse, MessageRole
from llama_index.core.chat_engine import ContextChatEngine
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.schema import TextNode

from app.model_pool import (
    CHAT_MODEL_POOL,
    RAG_MODEL_POOL,
    ROUTING_MODEL_POOL,
    ModelPoolController,
    ModelPoolExhaustedError,
    ModelPoolLLM,
)


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeModels:
    def __init__(self, outcomes, thread_ids=None):
        self.outcomes = iter(outcomes)
        self.calls = []
        self.thread_ids = thread_ids

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if self.thread_ids is not None:
            self.thread_ids.append(threading.get_ident())
        outcome = next(self.outcomes)
        if isinstance(outcome, BaseException):
            raise outcome
        return FakeResponse(outcome)


class FakeClient:
    def __init__(self, outcomes, thread_ids=None):
        self.models = FakeModels(outcomes, thread_ids)


def api_error(code, status, message="provider detail"):
    return errors.ClientError(
        code,
        {"error": {"code": code, "status": status, "message": message}},
    )


def make_llm(client, pool=RAG_MODEL_POOL, clock=None):
    kwargs = {}
    if clock is not None:
        kwargs["clock"] = clock
    return ModelPoolLLM(
        client=client,
        model_pool=pool,
        provider_request_timeout_s=10.0,
        default_remaining_budget_s=60.0,
        **kwargs,
    )


def test_exact_ordered_pools_are_runtime_constants():
    assert ROUTING_MODEL_POOL == (
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash-lite",
    )
    assert RAG_MODEL_POOL == (
        "gemini-3.5-flash",
        "gemini-3.6-flash",
        "gemini-3.7-flash",
        "gemini-3.8-flash",
    )
    assert CHAT_MODEL_POOL == (
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash-lite",
        "gemini-3-flash-preview",
    )


def test_retryable_errors_advance_in_order_and_bound_timeout_ms():
    client = FakeClient(
        [
            httpx.ReadTimeout("slow"),
            "done",
        ]
    )
    controller = ModelPoolController(client, ROUTING_MODEL_POOL, 10.0)

    assert controller.generate("prompt", remaining_budget_s=2.125) == "done"
    assert [call["model"] for call in client.models.calls] == list(
        ROUTING_MODEL_POOL
    )
    assert all(
        1 <= call["config"].http_options.timeout <= 2125
        for call in client.models.calls
    )
    assert all(
        call["config"].http_options.retry_options.attempts == 1
        for call in client.models.calls
    )


@pytest.mark.parametrize(
    ("provider_timeout_s", "remaining_budget_s", "expected_timeout_ms"),
    (
        (10.0, 0.0019999, 1),
        (10.0, 2.1250009, 2125),
        (0.0019999, 10.0, 1),
    ),
)
def test_fractional_millisecond_timeout_is_floored_within_budget(
    provider_timeout_s, remaining_budget_s, expected_timeout_ms
):
    client = FakeClient(["done"])
    controller = ModelPoolController(
        client, ROUTING_MODEL_POOL, provider_timeout_s
    )

    assert controller.generate("prompt", remaining_budget_s) == "done"

    timeout_ms = client.models.calls[0]["config"].http_options.timeout
    assert timeout_ms == expected_timeout_ms
    assert timeout_ms <= remaining_budget_s * 1000


def test_sub_millisecond_budget_exhausts_without_provider_attempt():
    client = FakeClient(["must not run"])
    controller = ModelPoolController(client, ROUTING_MODEL_POOL, 10.0)

    with pytest.raises(ModelPoolExhaustedError) as caught:
        controller.generate("prompt", remaining_budget_s=0.0009999)

    assert caught.value.attempted_models == ()
    assert isinstance(caught.value.terminal_error, TimeoutError)
    assert client.models.calls == []


def test_non_retryable_provider_error_propagates_immediately():
    unsupported = api_error(404, "NOT_FOUND")
    client = FakeClient([unsupported, "must not run"])
    controller = ModelPoolController(client, ROUTING_MODEL_POOL, 10.0)

    with pytest.raises(errors.ClientError) as caught:
        controller.generate("prompt", remaining_budget_s=3.0)

    assert caught.value is unsupported
    assert [call["model"] for call in client.models.calls] == [
        "gemini-3.1-flash-lite"
    ]


def test_exhaustion_reports_attempts_and_sanitized_terminal_failure():
    secret = "api-key-secret"
    terminal = api_error(429, "RESOURCE_EXHAUSTED", secret)
    client = FakeClient([httpx.ConnectTimeout("slow"), terminal])
    pool = ROUTING_MODEL_POOL[:2]
    controller = ModelPoolController(client, pool, 1.0)

    with pytest.raises(ModelPoolExhaustedError) as caught:
        controller.generate("prompt", remaining_budget_s=5.0)

    assert caught.value.attempted_models == pool
    assert caught.value.terminal_error is terminal
    assert list(pool).__repr__() in str(caught.value)
    assert "ClientError(code=429, status=RESOURCE_EXHAUSTED)" in str(
        caught.value
    )
    assert secret not in str(caught.value)


def test_expired_budget_stops_before_another_attempt():
    clock_values = iter((0.0, 0.0, 2.0))
    terminal = httpx.ReadTimeout("slow")
    client = FakeClient([terminal, "must not run"])
    controller = ModelPoolController(
        client, ROUTING_MODEL_POOL, 5.0, clock=lambda: next(clock_values)
    )

    with pytest.raises(ModelPoolExhaustedError) as caught:
        controller.generate("prompt", remaining_budget_s=1.0)

    assert caught.value.attempted_models == ("gemini-3.1-flash-lite",)
    assert caught.value.terminal_error is terminal


def test_positive_budget_and_timeout_are_required():
    client = FakeClient(["unused"])
    with pytest.raises(ValueError, match="provider_request_timeout_s"):
        ModelPoolController(client, ROUTING_MODEL_POOL, 0)
    controller = ModelPoolController(client, ROUTING_MODEL_POOL, 1.0)
    with pytest.raises(ValueError, match="remaining_budget_s"):
        controller.generate("prompt", remaining_budget_s=0)


def test_adapter_metadata_completion_and_public_private_state():
    client = FakeClient(["answer"])
    llm = make_llm(client)

    assert llm.model_pool == RAG_MODEL_POOL
    assert "_client" not in llm.model_dump()
    assert llm.metadata.context_window == 3900
    assert llm.metadata.num_output == 256
    assert llm.metadata.is_chat_model is False
    assert llm.metadata.is_function_calling_model is False
    assert llm.metadata.model_name == "gemini-model-pool"
    assert llm.metadata.system_role == MessageRole.SYSTEM
    response = llm.complete("hello", remaining_budget_s=4.0)
    assert isinstance(response, CompletionResponse)
    assert response.text == "answer"


def test_adapter_async_completion_offloads_sync_work():
    provider_threads = []
    client = FakeClient(["answer"], provider_threads)
    llm = make_llm(client)
    event_loop_thread = threading.get_ident()

    response = asyncio.run(llm.acomplete("hello"))

    assert response.text == "answer"
    assert len(provider_threads) == 1
    assert provider_threads[0] != event_loop_thread


def test_streaming_exception_timing_and_contract():
    llm = make_llm(FakeClient([]))
    with pytest.raises(NotImplementedError, match="Streaming is not supported"):
        llm.stream_complete("hello")
    with pytest.raises(NotImplementedError, match="Streaming is not supported"):
        llm.stream_chat([])

    async_completion = llm.astream_complete("hello")
    async_chat = llm.astream_chat([])
    assert inspect.iscoroutine(async_completion)
    assert inspect.iscoroutine(async_chat)

    async def await_failures():
        with pytest.raises(
            NotImplementedError, match="Streaming is not supported"
        ):
            await async_completion
        with pytest.raises(
            NotImplementedError, match="Streaming is not supported"
        ):
            await async_chat

    asyncio.run(await_failures())


def test_context_chat_engine_keeps_inert_adapter_without_provider_call():
    client = FakeClient([])
    llm = make_llm(client)
    index = VectorStoreIndex(
        [TextNode(text="resume context")],
        embed_model=MockEmbedding(embed_dim=8),
    )

    engine = ContextChatEngine.from_defaults(
        retriever=index.as_retriever(),
        llm=llm,
    )

    assert engine._llm is llm
    assert llm.model_pool == RAG_MODEL_POOL
    assert client.models.calls == []


def test_controller_tracks_winning_model_on_success():
    client = FakeClient(["done"])
    controller = ModelPoolController(client, ROUTING_MODEL_POOL, 10.0)

    assert controller.last_model is None
    assert controller.generate("prompt", remaining_budget_s=2.0) == "done"
    assert controller.last_model == "gemini-3.1-flash-lite"


def test_controller_tracks_fallback_winner_after_retryable_error():
    client = FakeClient([httpx.ReadTimeout("slow"), "done"])
    controller = ModelPoolController(client, ROUTING_MODEL_POOL, 10.0)

    assert controller.generate("prompt", remaining_budget_s=5.0) == "done"
    assert controller.last_model == "gemini-3.5-flash-lite"


def test_adapter_last_used_model_set_on_success_and_none_safe():
    client = FakeClient(["answer"])
    llm = make_llm(client)

    assert getattr(llm, "last_used_model", None) is None
    response = llm.complete("hello", remaining_budget_s=4.0)
    assert response.text == "answer"
    assert llm.last_used_model == "gemini-3.5-flash"


def test_adapter_last_used_model_reports_fallback_winner():
    client = FakeClient([httpx.ReadTimeout("slow"), "answer"])
    llm = make_llm(client, pool=ROUTING_MODEL_POOL)

    llm.complete("hello", remaining_budget_s=5.0)
    assert llm.last_used_model == "gemini-3.5-flash-lite"


def test_unavailable_advances_to_next_model():
    overloaded = api_error(503, "UNAVAILABLE")
    client = FakeClient([overloaded, "done"])
    controller = ModelPoolController(client, ROUTING_MODEL_POOL, 10.0)

    assert controller.generate("prompt", remaining_budget_s=5.0) == "done"
    assert [call["model"] for call in client.models.calls] == list(
        ROUTING_MODEL_POOL
    )


def test_all_unavailable_exhausts_after_every_model():
    terminal = api_error(503, "UNAVAILABLE")
    pool = ROUTING_MODEL_POOL[:2]
    client = FakeClient([terminal, terminal])
    controller = ModelPoolController(client, pool, 1.0)

    with pytest.raises(ModelPoolExhaustedError) as caught:
        controller.generate("prompt", remaining_budget_s=5.0)

    assert caught.value.attempted_models == pool
    assert caught.value.terminal_error is terminal
