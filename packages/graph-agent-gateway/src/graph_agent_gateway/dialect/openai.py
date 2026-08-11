"""The three OpenAI-shaped wires, and the vendors that reimplement them.

``/chat/completions``, ``/responses`` and the legacy ``/completions`` all carry
a Bearer token and name the model in the body; they differ in how a turn is
written, what the output budget is called, and whether they have a word for
thinking at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .reasoning import Reasoning
from .request import AuthScheme, Prompt, WirePath, WireRequest

_AUTH = AuthScheme.BEARER_HEADER


class ReasoningStyle(Enum):
    """How an OpenAI-shaped wire is told to think harder."""

    NATIVE_EFFORT = "native_effort"
    """The wire's own effort field — a word like ``high``, defaulting to ``low``."""

    ARK_THINKING = "ark_thinking"
    """ARK's switch: a ``thinking`` block that is explicitly on or off."""


@dataclass(frozen=True)
class OpenAIChatCompletions:
    """``POST /chat/completions`` — a messages array and an output budget."""

    path: WirePath
    budget_field: str
    reasoning_style: ReasoningStyle

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
        body: dict[str, object] = {
            "model": model_id,
            "messages": [{"role": "user", "content": _chat_content(prompt)}],
            self.budget_field: max_output_tokens,
        }
        if self.reasoning_style is ReasoningStyle.NATIVE_EFFORT:
            effort = _native_effort(reasoning)
            if effort is not None:
                body["reasoning_effort"] = effort
        else:
            thinking = _ark_thinking(reasoning)
            if thinking is not None:
                body["thinking"] = thinking
        return WireRequest(url=self.path.url(base_url), headers=_AUTH.headers(secret), body=body)


@dataclass(frozen=True)
class OpenAIResponses:
    """``POST /responses`` — one ``input`` and a ``max_output_tokens`` budget.

    ``input_as_message_list`` is a per-vendor fact: OpenAI accepts a bare string
    for a single text turn, ARK expects the message-list form either way.
    """

    path: WirePath
    reasoning_style: ReasoningStyle
    input_as_message_list: bool

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
        body: dict[str, object] = {
            "model": model_id,
            "input": self._input(prompt),
            "max_output_tokens": max_output_tokens,
        }
        if self.reasoning_style is ReasoningStyle.NATIVE_EFFORT:
            effort = _native_effort(reasoning)
            if effort is not None:
                body["reasoning"] = {"effort": effort}
        else:
            thinking = _ark_thinking(reasoning)
            if thinking is not None:
                body["thinking"] = thinking
        return WireRequest(url=self.path.url(base_url), headers=_AUTH.headers(secret), body=body)

    def _input(self, prompt: Prompt) -> object:
        if not self.input_as_message_list and prompt.image is None:
            return prompt.text
        blocks: list[dict[str, object]] = [{"type": "input_text", "text": prompt.text}]
        if prompt.image is not None:
            blocks.append({"type": "input_image", "image_url": prompt.image.data_uri})
        return [{"role": "user", "content": blocks}]


@dataclass(frozen=True)
class OpenAICompletions:
    """The legacy ``POST /completions`` — one text prompt, no turns, no thinking."""

    path: WirePath

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
        if prompt.image is not None:
            # Sending the text half would answer a question about images with a
            # result that never involved one.
            raise ValueError(
                "openai_completions is a plain text prompt interface with no image channel"
            )
        return WireRequest(
            url=self.path.url(base_url),
            headers=_AUTH.headers(secret),
            body={"model": model_id, "prompt": prompt.text, "max_tokens": max_output_tokens},
        )


def _chat_content(prompt: Prompt) -> object:
    if prompt.image is None:
        return prompt.text
    return [
        {"type": "text", "text": prompt.text},
        {"type": "image_url", "image_url": {"url": prompt.image.data_uri}},
    ]


def _native_effort(reasoning: Reasoning) -> str | None:
    """The word to send, or None when the caller said nothing about thinking."""

    if not (reasoning.effort or reasoning.wanted):
        return None
    return reasoning.effort or "low"


def _ark_thinking(reasoning: Reasoning) -> dict[str, object] | None:
    if reasoning.enabled is None:
        return None
    return {"type": "enabled" if reasoning.enabled else "disabled"}
