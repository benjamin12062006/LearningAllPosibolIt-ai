"""Respuestas de modelo guionizadas que pasan por el FunctionAgent real."""

from collections.abc import Sequence
from typing import Any

from llama_index.core.base.llms.types import ChatMessage, ToolCallBlock
from llama_index.core.llms.mock import MockFunctionCallingLLM

from ktsu_ai.domain.agent.agent_run import JsonValue


def tool_call(name: str, /, **arguments: JsonValue) -> ChatMessage:
    return ChatMessage(
        role="assistant",
        blocks=[
            ToolCallBlock(tool_call_id="test", tool_name=name, tool_kwargs=arguments)
        ],
    )


class ScriptedResponses:
    def __init__(self, *replies: ChatMessage) -> None:
        self._replies = iter(replies)
        self.messages: list[tuple[ChatMessage, ...]] = []
        self.schemas: list[dict[str, object]] = []
        self.llm = MockFunctionCallingLLM(response_generator=self._next_reply)

    def _next_reply(
        self, messages: Sequence[ChatMessage], **kwargs: Any
    ) -> ChatMessage:
        self.messages.append(tuple(messages))
        self.schemas = [tool.metadata.to_openai_tool() for tool in kwargs["tools"]]
        return next(self._replies)
