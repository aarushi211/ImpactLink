"""Shared OpenAI chat-model configuration and call metrics."""

from __future__ import annotations

import logging
import json
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
from langchain_core.prompt_values import ChatPromptValue
from langchain_openai import ChatOpenAI

from utils.metrics import metrics_collector
from utils.privacy import configure_privacy, redact_text, redact_values

load_dotenv()
configure_privacy()
log = logging.getLogger(__name__)

MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-6.1-sol")


def _record_call(result: ChatResult, duration_s: float, name: str) -> None:
    usage = (result.llm_output or {}).get("token_usage") or {}
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
    @staticmethod
    def _private_messages(messages):
        cleaned = []
        for message in messages:
            message = message.model_copy(deep=True)
            if isinstance(message.content, str):
                message.content = redact_text(message.content).text
            else:
                for index, block in enumerate(message.content):
                    if isinstance(block, str):
                        message.content[index] = redact_text(block).text
                        continue
                    if not isinstance(block, dict) or block.get("type") not in {"text", "input_text", "output_text"} or not isinstance(block.get("text"), str):
                        raise ValueError("AI privacy protection supports text inputs only. Extract and review document text before AI processing.")
                    block["text"] = redact_text(block["text"]).text
            if getattr(message, "tool_calls", None):
                for call in message.tool_calls:
                    call["args"] = redact_values(call.get("args", {}))
            if getattr(message, "invalid_tool_calls", None):
                raise ValueError("Malformed tool-call history cannot be sent through AI privacy protection.")
            for call in message.additional_kwargs.get("tool_calls", []):
                function = call.get("function", {})
                if "arguments" in function:
                    function["arguments"] = json.dumps(redact_values(json.loads(function["arguments"])))
            if message.additional_kwargs.get("function_call"):
                function = message.additional_kwargs["function_call"]
                function["arguments"] = json.dumps(redact_values(json.loads(function.get("arguments", "{}"))))
            cleaned.append(message)
        return cleaned

    def _convert_input(self, input):
        prompt = super()._convert_input(input)
        return ChatPromptValue(messages=self._private_messages(prompt.to_messages()))

    def generate(self, messages, stop=None, callbacks=None, **kwargs):
        # Also cover callers that bypass invoke() and pass message batches directly.
        return super().generate([self._private_messages(batch) for batch in messages], stop=stop, callbacks=callbacks, **kwargs)

    async def agenerate(self, messages, stop=None, callbacks=None, **kwargs):
        return await super().agenerate([self._private_messages(batch) for batch in messages], stop=stop, callbacks=callbacks, **kwargs)

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        if payload.get("extra_body") or payload.get("previous_response_id") or payload.get("conversation"):
            raise ValueError("AI privacy protection does not support alternate request bodies or provider-stored conversation history.")
        payload["store"] = False
        for key in ("metadata", "user", "safety_identifier", "prompt_cache_key"):
            if key in payload:
                payload[key] = redact_values(payload[key])
        return payload

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


def get_chat_model(
    *, json_mode: bool = False, streaming: bool = False
) -> InstrumentedChatOpenAI:
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
        "streaming": streaming,
        "store": False,
        "cache": False,
        "verbose": False,
    }
    if json_mode:
        kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
    return InstrumentedChatOpenAI(**kwargs)
