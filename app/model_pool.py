"""Ordered Gemini model pools and a LlamaIndex compatibility adapter."""

import asyncio
import math
import time
from typing import Any, Callable, Sequence

import httpx
from google.genai import errors, types
from llama_index.core.base.llms.types import (
    ChatMessage,
    ChatResponseAsyncGen,
    CompletionResponse,
    CompletionResponseAsyncGen,
    CompletionResponseGen,
    LLMMetadata,
    MessageRole,
)
from llama_index.core.llms import CustomLLM
from llama_index.core.llms.callbacks import llm_completion_callback
from pydantic import Field, PrivateAttr


ROUTING_MODEL_POOL = (
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
)
# Optional Gemma fallbacks (uncomment to enable):
# "gemma-4-26b-a4b-it",
# "gemma-4-31b-it",

RAG_MODEL_POOL = (
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-3.8-flash",
)

CHAT_MODEL_POOL = (
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3-flash-preview",
)

_RETRYABLE_API_CODES = frozenset((408, 429, 504))
_RETRYABLE_API_STATUSES = frozenset(("DEADLINE_EXCEEDED", "RESOURCE_EXHAUSTED"))
_STREAMING_ERROR = "Streaming is not supported by ModelPoolLLM"


def is_retryable_provider_error(error: BaseException) -> bool:
    """Return whether an error is an audited provider timeout/rate limit."""
    if isinstance(error, httpx.TimeoutException):
        return True
    if not isinstance(error, errors.APIError):
        return False
    return (
        error.code in _RETRYABLE_API_CODES
        or error.status in _RETRYABLE_API_STATUSES
    )


class ModelPoolExhaustedError(RuntimeError):
    """Report ordered attempts after all permitted fallbacks fail."""

    def __init__(
        self,
        attempted_models: Sequence[str],
        terminal_error: BaseException,
    ) -> None:
        self.attempted_models = tuple(attempted_models)
        self.terminal_error = terminal_error
        terminal_kind = type(terminal_error).__name__
        if isinstance(terminal_error, errors.APIError):
            terminal_kind = (
                f"{terminal_kind}(code={terminal_error.code}, "
                f"status={terminal_error.status})"
            )
        super().__init__(
            "Model pool exhausted after ordered attempts "
            f"{list(self.attempted_models)}; terminal failure: {terminal_kind}"
        )


class ModelPoolController:
    """Generate through an exact ordered pool with bounded fallback."""

    def __init__(
        self,
        client: Any,
        model_pool: Sequence[str],
        provider_request_timeout_s: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not model_pool:
            raise ValueError("model_pool must not be empty")
        if provider_request_timeout_s <= 0:
            raise ValueError("provider_request_timeout_s must be positive")
        self._client = client
        self.model_pool = tuple(model_pool)
        self.provider_request_timeout_s = provider_request_timeout_s
        self._clock = clock
        self.last_model: str | None = None

    def generate(self, prompt: str, remaining_budget_s: float) -> str:
        """Generate text, advancing only after timeout or rate-limit errors."""
        if remaining_budget_s <= 0:
            raise ValueError("remaining_budget_s must be positive")

        started_at = self._clock()
        attempted_models = []
        terminal_error: BaseException | None = None

        for model in self.model_pool:
            remaining = remaining_budget_s - (self._clock() - started_at)
            if remaining <= 0:
                break
            timeout_ms = math.floor(
                min(self.provider_request_timeout_s, remaining) * 1000
            )
            if timeout_ms < 1:
                break
            config = types.GenerateContentConfig(
                http_options=types.HttpOptions(
                    timeout=timeout_ms,
                    retry_options=types.HttpRetryOptions(attempts=1),
                )
            )
            attempted_models.append(model)
            try:
                response = self._client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config,
                )
                self.last_model = model
                return response.text or ""
            except Exception as error:
                if not is_retryable_provider_error(error):
                    raise
                terminal_error = error

        if terminal_error is None:
            terminal_error = TimeoutError("remaining elapsed budget was exhausted")
        raise ModelPoolExhaustedError(attempted_models, terminal_error)


class ModelPoolLLM(CustomLLM):
    """Expose an ordered model pool through the LlamaIndex CustomLLM API."""

    model_pool: tuple[str, ...]
    provider_request_timeout_s: float = Field(gt=0)
    default_remaining_budget_s: float = Field(gt=0)
    _client: Any = PrivateAttr()
    _clock: Callable[[], float] = PrivateAttr()
    _last_used_model: Any = PrivateAttr(default=None)

    def __init__(
        self,
        *,
        client: Any,
        model_pool: Sequence[str],
        provider_request_timeout_s: float,
        default_remaining_budget_s: float,
        clock: Callable[[], float] = time.monotonic,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            model_pool=tuple(model_pool),
            provider_request_timeout_s=provider_request_timeout_s,
            default_remaining_budget_s=default_remaining_budget_s,
            **kwargs,
        )
        self._client = client
        self._clock = clock
        self._last_used_model = None

    @property
    def last_used_model(self) -> str | None:
        """Winning model ID from the most recent successful complete()."""
        return self._last_used_model

    @last_used_model.setter
    def last_used_model(self, value: str | None) -> None:
        self._last_used_model = value

    @property
    def metadata(self) -> LLMMetadata:
        """Describe conservative, model-neutral LlamaIndex capabilities."""
        return LLMMetadata(
            context_window=3900,
            num_output=256,
            is_chat_model=False,
            is_function_calling_model=False,
            model_name="gemini-model-pool",
            system_role=MessageRole.SYSTEM,
        )

    @llm_completion_callback()
    def complete(
        self,
        prompt: str,
        formatted: bool = False,
        **kwargs: Any,
    ) -> CompletionResponse:
        """Complete a prompt through the ordered fallback controller."""
        del formatted
        remaining_budget_s = kwargs.pop(
            "remaining_budget_s", self.default_remaining_budget_s
        )
        if kwargs:
            unexpected = ", ".join(sorted(kwargs))
            raise TypeError(f"Unexpected completion arguments: {unexpected}")
        controller = ModelPoolController(
            client=self._client,
            model_pool=self.model_pool,
            provider_request_timeout_s=self.provider_request_timeout_s,
            clock=self._clock,
        )
        text = controller.generate(prompt, remaining_budget_s)
        self._last_used_model = controller.last_model
        return CompletionResponse(text=text)

    @llm_completion_callback()
    async def acomplete(
        self,
        prompt: str,
        formatted: bool = False,
        **kwargs: Any,
    ) -> CompletionResponse:
        """Run blocking provider completion away from the event-loop thread."""
        return await asyncio.to_thread(
            self.complete,
            prompt,
            formatted=formatted,
            **kwargs,
        )

    def stream_complete(
        self,
        prompt: str,
        formatted: bool = False,
        **kwargs: Any,
    ) -> CompletionResponseGen:
        """Reject unsupported synchronous streaming immediately."""
        raise NotImplementedError(_STREAMING_ERROR)

    def stream_chat(
        self,
        messages: Sequence[ChatMessage],
        **kwargs: Any,
    ) -> Any:
        """Reject unsupported synchronous chat streaming immediately."""
        raise NotImplementedError(_STREAMING_ERROR)

    async def astream_complete(
        self,
        prompt: str,
        formatted: bool = False,
        **kwargs: Any,
    ) -> CompletionResponseAsyncGen:
        """Reject unsupported async streaming when the coroutine is awaited."""
        raise NotImplementedError(_STREAMING_ERROR)

    async def astream_chat(
        self,
        messages: Sequence[ChatMessage],
        **kwargs: Any,
    ) -> ChatResponseAsyncGen:
        """Reject unsupported async chat streaming when awaited."""
        raise NotImplementedError(_STREAMING_ERROR)
