"""The Anthropic Messages wire, and the vendors that reimplement it.

One shape — ``POST /v1/messages`` with a ``messages`` array and a top-level
``max_tokens`` — differing between vendors only in where the secret goes and
whether a bare string is accepted as message content.
"""

from __future__ import annotations

from dataclasses import dataclass

from .reasoning import Reasoning
from .request import AbsolutePath, AuthScheme, Prompt, WireRequest

_MESSAGES_PATH = AbsolutePath("/v1/messages")
_API_VERSION = "2023-06-01"


@dataclass(frozen=True)
class AnthropicMessages:
    """Anthropic's own wire and its copies.

    ``content_as_blocks`` exists because some reimplementations reject the bare
    string form that Anthropic itself accepts; it says nothing about images,
    which always travel as blocks.
    """

    auth: AuthScheme
    content_as_blocks: bool

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
            "max_tokens": max_output_tokens,
            "messages": [{"role": "user", "content": self._content(prompt)}],
        }
        thinking = _thinking(max_output_tokens, reasoning)
        if thinking is not None:
            body["thinking"] = thinking
            if reasoning.effort:
                # How much to think and how hard to think are two dials here:
                # the budget rides on `thinking`, the word on `output_config`.
                body["output_config"] = {"effort": reasoning.effort}
        return WireRequest(
            url=_MESSAGES_PATH.url(base_url),
            headers={**self.auth.headers(secret), "anthropic-version": _API_VERSION},
            params=self.auth.params(secret),
            body=body,
        )

    def _content(self, prompt: Prompt) -> object:
        if prompt.image is not None:
            return [
                {"type": "text", "text": prompt.text},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": prompt.image.media_type,
                        "data": prompt.image.base64_data,
                    },
                },
            ]
        return [{"type": "text", "text": prompt.text}] if self.content_as_blocks else prompt.text


def _thinking(max_output_tokens: int, reasoning: Reasoning) -> dict[str, object] | None:
    if not reasoning.wanted:
        return None
    if reasoning.requested_type == "adaptive":
        return {"type": "adaptive"}
    budget = reasoning.budget_tokens
    if budget is None:
        # A budget must leave room for an answer. Below the floor the provider
        # picks the split itself rather than us starving the reply.
        if max_output_tokens <= 1024:
            return {"type": "adaptive"}
        budget = max(1024, min(4096, max_output_tokens - 1))
    return {"type": "enabled", "budget_tokens": budget}
