"""Official provider capability source registry.

This module is intentionally data-heavy: it keeps first-party documentation
URLs next to the provider-doc rules that use them, so future model/catalog
updates have one place to refresh.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

OfficialCapabilitySource = Literal["api_list", "provider_doc"]


@dataclass(frozen=True)
class OfficialCapabilityRule:
    value: object
    source: OfficialCapabilitySource
    source_urls: tuple[str, ...]
    message: str | None = None


@dataclass(frozen=True)
class OfficialProviderSources:
    api_list: tuple[str, ...]
    topics: dict[str, tuple[str, ...]]


OFFICIAL_PROVIDER_CAPABILITY_SOURCES: dict[str, OfficialProviderSources] = {
    "claude": OfficialProviderSources(
        api_list=("https://docs.anthropic.com/en/api/models-list",),
        topics={
            "models": ("https://docs.anthropic.com/en/docs/about-claude/models/overview",),
            "vision": ("https://docs.anthropic.com/en/docs/build-with-claude/vision",),
            "pdf": ("https://docs.anthropic.com/en/docs/build-with-claude/pdf-support",),
            "thinking": (
                "https://docs.anthropic.com/en/docs/build-with-claude/extended-thinking",
            ),
            "tools": (
                "https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/overview",
            ),
        },
    ),
    "openai": OfficialProviderSources(
        api_list=(
            "https://developers.openai.com/api/docs/models",
            "https://api.openai.com/v1/models",
        ),
        topics={
            "models": ("https://developers.openai.com/api/docs/models",),
            "responses": (
                "https://developers.openai.com/api/reference/responses/overview",
            ),
            "vision": (
                "https://developers.openai.com/api/docs/guides/images-vision",
            ),
            "image": (
                "https://developers.openai.com/api/docs/guides/image-generation",
            ),
            "audio": ("https://developers.openai.com/api/docs/guides/audio",),
            "embedding": (
                "https://developers.openai.com/api/docs/guides/embeddings",
            ),
            "moderation": (
                "https://developers.openai.com/api/docs/guides/moderation",
            ),
            "files": (
                "https://developers.openai.com/api/docs/api-reference/files",
            ),
        },
    ),
    "gemini": OfficialProviderSources(
        api_list=("https://ai.google.dev/api/models",),
        topics={
            "models": ("https://ai.google.dev/gemini-api/docs/models",),
            "vision": ("https://ai.google.dev/gemini-api/docs/image-understanding",),
            "image": ("https://ai.google.dev/gemini-api/docs/image-generation",),
            "video": ("https://ai.google.dev/gemini-api/docs/video-generation",),
            "audio": ("https://ai.google.dev/gemini-api/docs/audio",),
            "embedding": ("https://ai.google.dev/gemini-api/docs/embeddings",),
            "tts": ("https://ai.google.dev/gemini-api/docs/speech-generation",),
        },
    ),
    "deepseek": OfficialProviderSources(
        api_list=("https://api-docs.deepseek.com/api/list-models",),
        topics={
            "models": ("https://api-docs.deepseek.com/quick_start/pricing",),
            "chat": ("https://api-docs.deepseek.com/api/create-chat-completion",),
            "anthropic": ("https://api-docs.deepseek.com/guides/anthropic_api",),
        },
    ),
    "ark": OfficialProviderSources(
        api_list=(
            "https://www.volcengine.com/docs/82379/1330310",
            "https://www.volcengine.com/docs/82379/1554709",
        ),
        topics={
            "models": ("https://www.volcengine.com/docs/82379/1554709",),
            "chat": ("https://www.volcengine.com/docs/82379/1298454",),
            "responses": ("https://www.volcengine.com/docs/82379/1594511",),
            "anthropic": ("https://www.volcengine.com/docs/82379/2160841?lang=zh",),
            "vision": ("https://www.volcengine.com/docs/82379/1362931?lang=zh",),
            "image": ("https://www.volcengine.com/docs/82379/1548482",),
            "video": ("https://www.volcengine.com/docs/82379/1520757",),
            "audio": ("https://www.volcengine.com/docs/82379/1239292",),
            "embedding": ("https://www.volcengine.com/docs/82379/1099522",),
            "translation": ("https://www.volcengine.com/docs/82379/1467466",),
            "3d": ("https://www.volcengine.com/docs/82379/1559865",),
        },
    ),
}


def official_api_list_source_urls(provider_key: str) -> tuple[str, ...]:
    provider = OFFICIAL_PROVIDER_CAPABILITY_SOURCES.get(provider_key)
    return provider.api_list if provider else ()


def official_doc_source_urls(
    provider_key: str,
    *,
    model_type: str | None = None,
    modalities: tuple[str, ...] = (),
    topics: tuple[str, ...] = (),
) -> tuple[str, ...]:
    provider = OFFICIAL_PROVIDER_CAPABILITY_SOURCES.get(provider_key)
    if provider is None:
        return ()
    selected_topics = ["models", *topics]
    if model_type in {"language_reasoning", "interactions_agent"}:
        selected_topics.append("responses" if provider_key == "openai" else "chat")
    if "image" in modalities:
        selected_topics.append("vision" if model_type == "language_reasoning" else "image")
    if "pdf" in modalities:
        selected_topics.append("pdf")
    if "file" in modalities:
        selected_topics.append("files")
    if "video" in modalities:
        selected_topics.append("video")
    if "audio" in modalities:
        selected_topics.append("audio")
    if "embedding" in modalities or model_type == "embedding":
        selected_topics.append("embedding")
    if "moderation" in modalities or model_type == "moderation":
        selected_topics.append("moderation")
    if "3d" in modalities or model_type == "3d_generation":
        selected_topics.append("3d")
    if model_type == "translation":
        selected_topics.append("translation")

    urls: list[str] = []
    for topic in selected_topics:
        for url in provider.topics.get(topic, ()):
            if url not in urls:
                urls.append(url)
    return tuple(urls)


def provider_doc_limit_rules(
    provider_key: str,
    model_id: str,
) -> dict[str, OfficialCapabilityRule]:
    model = model_id.lower()
    if provider_key == "deepseek" and (
        model.startswith("deepseek-v4")
        or model in {"deepseek-chat", "deepseek-reasoner"}
    ):
        urls = official_doc_source_urls(provider_key, topics=("chat",))
        return {
            "max_input_tokens": OfficialCapabilityRule(
                value=1_048_576,
                source="provider_doc",
                source_urls=urls,
                message="DeepSeek official docs list V4/chat/reasoner context at 1M tokens.",
            ),
            "max_output_tokens": OfficialCapabilityRule(
                value=393_216,
                source="provider_doc",
                source_urls=urls,
                message="DeepSeek official docs list V4/chat/reasoner max output at 384K tokens.",
            ),
        }
    if provider_key == "openai":
        openai_limits = _openai_gpt5_text_token_limits(model)
        if openai_limits is None:
            return {}
        max_input_tokens, max_output_tokens, model_doc_url = openai_limits
        urls = (
            *official_doc_source_urls(provider_key, model_type="language_reasoning"),
            model_doc_url,
        )
        return {
            "max_input_tokens": OfficialCapabilityRule(
                value=max_input_tokens,
                source="provider_doc",
                source_urls=urls,
                message="OpenAI model docs list this GPT-5 text/reasoning context window.",
            ),
            "max_output_tokens": OfficialCapabilityRule(
                value=max_output_tokens,
                source="provider_doc",
                source_urls=urls,
                message="OpenAI model docs list this GPT-5 text/reasoning max output limit.",
            ),
        }
    if provider_key == "claude" and model.startswith(("claude-opus-4-8", "claude-sonnet-4-6")):
        urls = official_doc_source_urls(provider_key, model_type="language_reasoning")
        return {
            "max_input_tokens": OfficialCapabilityRule(
                value=1_048_576,
                source="provider_doc",
                source_urls=urls,
                message="Anthropic model docs list this Claude family with a 1M-token context window.",
            ),
            "max_output_tokens": OfficialCapabilityRule(
                value=128_000 if model.startswith("claude-opus-4-8") else 64_000,
                source="provider_doc",
                source_urls=urls,
                message="Anthropic model docs list this Claude family max output token limit.",
            ),
        }
    return {}


def _openai_gpt5_text_token_limits(model: str) -> tuple[int, int, str] | None:
    if any(
        token in model
        for token in ("image", "realtime", "tts", "transcribe", "audio", "embedding")
    ):
        return None

    if _openai_model_alias_or_snapshot(model, ("gpt-5.5", "gpt-5.5-pro")):
        return (
            1_050_000,
            128_000,
            "https://developers.openai.com/api/docs/models/gpt-5.5",
        )
    if _openai_model_alias_or_snapshot(model, ("gpt-5.4", "gpt-5.4-pro")):
        return (
            1_050_000,
            128_000,
            "https://developers.openai.com/api/docs/models/gpt-5.4",
        )
    if _openai_model_alias_or_snapshot(model, ("gpt-5.4-mini", "gpt-5.4-nano")):
        return (
            400_000,
            128_000,
            "https://developers.openai.com/api/docs/models/gpt-5.4-mini",
        )
    if _openai_model_alias_or_snapshot(model, ("gpt-5-pro",)):
        return (
            400_000,
            272_000,
            "https://developers.openai.com/api/docs/models/gpt-5-pro",
        )
    if _openai_model_alias_or_snapshot(
        model,
        (
            "gpt-5",
            "gpt-5-mini",
            "gpt-5-nano",
            "gpt-5-codex",
            "gpt-5.1",
            "gpt-5.1-codex-max",
            "gpt-5.2",
            "gpt-5.2-pro",
        ),
    ):
        return (
            400_000,
            128_000,
            "https://developers.openai.com/api/docs/models/gpt-5",
        )
    if model == "gpt-5-chat-latest":
        return (
            128_000,
            16_384,
            "https://developers.openai.com/api/docs/models/gpt-5-chat-latest",
        )
    return None


def _openai_model_alias_or_snapshot(model: str, aliases: tuple[str, ...]) -> bool:
    for alias in aliases:
        if model == alias:
            return True
        if re.fullmatch(rf"{re.escape(alias)}-\d{{4}}-\d{{2}}-\d{{2}}", model):
            return True
    return False
