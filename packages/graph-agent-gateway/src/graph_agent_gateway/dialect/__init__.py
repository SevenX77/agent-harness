"""Dialects: the same request, said the way each provider's API expects it.

A dialect answers one question — what does this call method put on the wire for
this prompt, this model and this much thinking — and answers it as data, so the
probe that tests a route and the client that runs it can be shown to speak the
same words. It depends on nothing else in the gateway: no storage, no registry,
no HTTP client.

Which method exists, and which base url it uses, are the registry's facts; this
domain starts once those are decided.
"""

from __future__ import annotations

from .anthropic import AnthropicMessages
from .google import GeminiGenerateContent
from .methods import Dialect, dialect_for_method, dialect_method_ids
from .openai import (
    OpenAIChatCompletions,
    OpenAICompletions,
    OpenAIResponses,
    ReasoningStyle,
)
from .reasoning import Reasoning
from .request import (
    AbsolutePath,
    AuthScheme,
    Image,
    Prompt,
    VersionedPath,
    WirePath,
    WireRequest,
    join_base_url_and_path,
)

__all__ = [
    "AbsolutePath",
    "AnthropicMessages",
    "AuthScheme",
    "Dialect",
    "GeminiGenerateContent",
    "Image",
    "OpenAIChatCompletions",
    "OpenAICompletions",
    "OpenAIResponses",
    "Prompt",
    "Reasoning",
    "ReasoningStyle",
    "VersionedPath",
    "WirePath",
    "WireRequest",
    "dialect_for_method",
    "dialect_method_ids",
    "join_base_url_and_path",
]
