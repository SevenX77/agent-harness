"""Tests for reasoning_content LangChain monkey patches."""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage
import langchain_openai.chat_models.base as lc_openai_base

from graph_agent.models.reasoning_patch import _apply_reasoning_content_patch


def test_message_to_dict_echoes_ai_reasoning_content() -> None:
    _apply_reasoning_content_patch()
    message = AIMessage(
        content="answer",
        additional_kwargs={"reasoning_content": "hidden reasoning trace"},
    )

    payload = lc_openai_base._convert_message_to_dict(message)

    assert payload["role"] == "assistant"
    assert payload["content"] == "answer"
    assert payload["reasoning_content"] == "hidden reasoning trace"


def test_message_to_dict_does_not_add_reasoning_content_to_non_ai() -> None:
    _apply_reasoning_content_patch()
    message = HumanMessage(
        content="question",
        additional_kwargs={"reasoning_content": "should not be echoed"},
    )

    payload = lc_openai_base._convert_message_to_dict(message)

    assert payload["role"] == "user"
    assert "reasoning_content" not in payload
