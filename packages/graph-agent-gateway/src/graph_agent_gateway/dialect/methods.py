"""What a dialect is, and which one each official call method speaks.

The table below is the whole of the per-method wire knowledge: a method that is
not in it cannot be rendered, which is why lookup fails loudly instead of
falling back to whatever wire happens to be most common.
"""

from __future__ import annotations

from typing import Protocol

from .anthropic import AnthropicMessages
from .google import GeminiGenerateContent
from .openai import (
    OpenAIChatCompletions,
    OpenAICompletions,
    OpenAIResponses,
    ReasoningStyle,
)
from .reasoning import Reasoning
from .request import AbsolutePath, AuthScheme, Prompt, VersionedPath, WireRequest


class Dialect(Protocol):
    """Renders one request in one provider's wire language. It never sends it."""

    def generation(
        self,
        *,
        base_url: str,
        secret: str,
        model_id: str,
        prompt: Prompt,
        max_output_tokens: int,
        reasoning: Reasoning,
    ) -> WireRequest:
        """One turn of text, optionally a picture, asking for one short answer."""


_DIALECTS: dict[str, Dialect] = {
    "anthropic_messages": AnthropicMessages(
        auth=AuthScheme.API_KEY_HEADER,
        content_as_blocks=False,
    ),
    "deepseek_anthropic_messages": AnthropicMessages(
        auth=AuthScheme.API_KEY_HEADER,
        content_as_blocks=True,
    ),
    "ark_anthropic_messages": AnthropicMessages(
        auth=AuthScheme.BEARER_HEADER,
        content_as_blocks=True,
    ),
    "openai_chat_completions": OpenAIChatCompletions(
        path=VersionedPath("/chat/completions"),
        budget_field="max_completion_tokens",
        reasoning_style=ReasoningStyle.NATIVE_EFFORT,
    ),
    "deepseek_chat_completions": OpenAIChatCompletions(
        path=VersionedPath("/chat/completions"),
        budget_field="max_tokens",
        reasoning_style=ReasoningStyle.NATIVE_EFFORT,
    ),
    "ark_chat": OpenAIChatCompletions(
        path=AbsolutePath("/api/v3/chat/completions"),
        budget_field="max_tokens",
        reasoning_style=ReasoningStyle.ARK_THINKING,
    ),
    "openai_responses": OpenAIResponses(
        path=VersionedPath("/responses"),
        reasoning_style=ReasoningStyle.NATIVE_EFFORT,
        input_as_message_list=False,
    ),
    "ark_responses": OpenAIResponses(
        path=AbsolutePath("/api/v3/responses"),
        reasoning_style=ReasoningStyle.ARK_THINKING,
        input_as_message_list=True,
    ),
    "openai_completions": OpenAICompletions(path=VersionedPath("/completions")),
    "gemini_generate_content": GeminiGenerateContent(),
}


def dialect_for_method(method_id: str) -> Dialect:
    dialect = _DIALECTS.get(method_id)
    if dialect is None:
        raise ValueError(f"No dialect speaks the call method: {method_id}")
    return dialect


def official_wire_method_ids() -> frozenset[str]:
    """Every call method that can be rendered onto a wire."""

    return frozenset(_DIALECTS)
