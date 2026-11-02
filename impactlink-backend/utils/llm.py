"""Shared OpenAI chat-model configuration and call metrics."""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

from dotenv import load_dotenv
from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_openai import ChatOpenAI

from utils.metrics import metrics_collector

load_dotenv()
log = logging.getLogger(__name__)

MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-6.1-sol")


def _record_call(result: ChatResult, duration_s: float, name: str) -> None:
    usage = (result.llm_output or {}).get("token_usage", {})
    metadata = {"model": MODEL_NAME}
    for source, target in (
        ("prompt_tokens", "prompt_tokens"),
        ("completion_tokens", "completion_tokens"),
        ("total_tokens", "total_tokens"),
    ):
        if source in usage:
            metadata[target] = usage[source]
    metrics_collector.record(
        category="llm_call",
        name=name,
        duration_s=duration_s,
        metadata=metadata,
    )


class InstrumentedChatOpenAI(ChatOpenAI):
    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        started = time.perf_counter()
        result = super()._generate(
            messages, stop=stop, run_manager=run_manager, **kwargs
        )
        _record_call(result, time.perf_counter() - started, "openai_generate")
        return result

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        started = time.perf_counter()
        result = await super()._agenerate(
            messages, stop=stop, run_manager=run_manager, **kwargs
        )
        _record_call(result, time.perf_counter() - started, "openai_generate_async")
        return result


def get_chat_model(*, json_mode: bool = False) -> InstrumentedChatOpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is required. Set it in the backend environment."
        )

    kwargs: dict[str, Any] = {
        "model": MODEL_NAME,
        "api_key": api_key,
        "timeout": 120,
        "max_retries": 2,
    }
    if json_mode:
        kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
    return InstrumentedChatOpenAI(**kwargs)
