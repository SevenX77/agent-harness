"""The Google Generative Language wire.

The odd one out in three ways: the model is part of the path, the secret is a
query parameter, and the generation knobs live under ``generationConfig``.
"""

from __future__ import annotations

from dataclasses import dataclass

from .reasoning import Reasoning
from .request import AuthScheme, Prompt, WireRequest, join_base_url_and_path

_AUTH = AuthScheme.QUERY_KEY


@dataclass(frozen=True)
class GeminiGenerateContent:
    """``POST /v1beta/models/{model}:generateContent``."""

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
        generation_config: dict[str, object] = {"maxOutputTokens": max_output_tokens}
        thinking_config = _thinking_config(reasoning)
        if thinking_config is not None:
            generation_config["thinkingConfig"] = thinking_config
        return WireRequest(
            url=join_base_url_and_path(base_url, f"/v1beta/models/{model_id}:generateContent"),
            params=_AUTH.params(secret),
            body={
                "contents": [{"parts": _parts(prompt)}],
                "generationConfig": generation_config,
            },
        )


def _parts(prompt: Prompt) -> list[dict[str, object]]:
    parts: list[dict[str, object]] = [{"text": prompt.text}]
    if prompt.image is not None:
        parts.append(
            {
                "inline_data": {
                    "mime_type": prompt.image.media_type,
                    "data": prompt.image.base64_data,
                }
            }
        )
    return parts


def _thinking_config(reasoning: Reasoning) -> dict[str, object] | None:
    if reasoning.effort:
        return {"thinkingLevel": reasoning.effort}
    if reasoning.budget_tokens is not None:
        return {"thinkingBudget": reasoning.budget_tokens}
    if not reasoning.wanted:
        return None
    return {}
