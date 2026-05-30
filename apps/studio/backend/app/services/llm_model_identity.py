"""Studio-owned model display projection helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.models.llm_config import ProviderEndpoint, ProviderRoute


@dataclass(frozen=True)
class ModelIdentityProjection:
    display_name: str
    section_label: str
    confidence: str
    tokens: tuple[str, ...] = ()
    display_tokens: tuple[str, ...] = ()
    unknown_tokens: tuple[str, ...] = ()


_BRAND_TOKENS = {
    "ai21": "AI21",
    "anthropic": "Anthropic",
    "api": "API",
    "aqa": "AQA",
    "ark": "Ark",
    "chatgpt": "ChatGPT",
    "claude": "Claude",
    "deepseek": "DeepSeek",
    "gemini": "Gemini",
    "glm": "GLM",
    "gpt": "GPT",
    "kimi": "Kimi",
    "llama": "Llama",
    "meta": "Meta",
    "mistral": "Mistral",
    "mixtral": "Mixtral",
    "moonshot": "Moonshot",
    "openai": "OpenAI",
    "qwen": "Qwen",
    "tts": "TTS",
    "xai": "xAI",
}

_VARIANT_TOKENS = {
    "base",
    "chat",
    "exp",
    "flash",
    "free",
    "large",
    "latest",
    "lite",
    "mini",
    "nano",
    "preview",
    "pro",
    "speciale",
    "small",
    "terminus",
    "turbo",
}
_CAPABILITY_TOKENS = {"audio", "image", "reasoning", "thinking", "tool", "tools", "vision"}
_MODEL_VERSION_CONTEXT_TOKENS = {
    "chatgpt",
    "claude",
    "deepseek",
    "gemini",
    "glm",
    "gpt",
    "grok",
    "haiku",
    "kimi",
    "llama",
    "mistral",
    "mixtral",
    "opus",
    "qwen",
    "sonnet",
}


def project_model_identity(
    *,
    route: ProviderRoute,
    endpoint: ProviderEndpoint,
) -> ModelIdentityProjection:
    raw_name = _first_non_empty(route.provider_model_id, route.canonical_id, route.route_slug)
    tokens = _tokenize_model_name(_strip_route_prefix(raw_name))
    owner = _infer_owner(
        [
            endpoint.endpoint_id,
            endpoint.display_name,
            route.provider_model_id,
            route.canonical_id,
        ],
        tokens,
    )
    family = _infer_family(owner, tokens)
    display_tokens = _compact_display_tokens(tokens, owner)
    display_name = " ".join(display_tokens) if display_tokens else _titleize_model_name(route.canonical_id)
    section_label = _section_for_owner(owner, family, tokens)
    known = _recognized_tokens(owner, family)
    unknown_tokens = tuple(
        dict.fromkeys(
            token.lower()
            for token in tokens
            if token.lower() not in known
            and token.lower() not in _VARIANT_TOKENS
            and token.lower() not in _CAPABILITY_TOKENS
            and not _is_version_or_snapshot(token)
        )
    )
    return ModelIdentityProjection(
        display_name=display_name,
        section_label=section_label,
        confidence="high" if owner else "medium" if family != "unknown" else "low",
        tokens=tuple(tokens),
        display_tokens=tuple(display_tokens),
        unknown_tokens=unknown_tokens,
    )


def _tokenize_model_name(value: str) -> list[str]:
    placeholders: list[str] = []

    def protect(token: str) -> str:
        placeholders.append(token)
        return f"QQMODEL{len(placeholders) - 1}QQ"

    protected = re.sub(
        r"\b(20\d{2})[-_.](\d{1,2})[-_.](\d{1,2})\b",
        lambda match: protect(
            f"{match.group(1)}-{match.group(2).zfill(2)}-{match.group(3).zfill(2)}"
        ),
        value.strip(),
    )
    protected = re.sub(
        r"\b([vV]?)(\d{1,2})[-_.](\d{1,2})(?![-_.]\d)\b",
        lambda match: protect(
            f"{'V' if match.group(1) else ''}{int(match.group(2))}.{int(match.group(3))}"
        ),
        protected,
    )
    raw_tokens = re.split(r"[^A-Za-z0-9]+", protected)
    titleized = [
        _titleize_token(_restore_placeholder(token, placeholders))
        for token in raw_tokens
        if token
    ]
    titleized = _merge_space_separated_version_tokens(titleized)
    deduped = [
        token
        for index, token in enumerate(titleized)
        if token and token.lower() != titleized[index - 1].lower()
    ]
    return deduped


def _restore_placeholder(token: str, placeholders: list[str]) -> str:
    match = re.fullmatch(r"QQMODEL(\d+)QQ", token)
    if not match:
        return token
    index = int(match.group(1))
    return placeholders[index] if index < len(placeholders) else token


def _titleize_model_name(value: str) -> str:
    return " ".join(_tokenize_model_name(_strip_route_prefix(value)))


def _titleize_token(token: str) -> str:
    if not token:
        return ""
    if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", token):
        return token
    if re.fullmatch(r"20\d{6}", token) or re.fullmatch(r"\d{6}", token):
        return token
    if re.fullmatch(r"[vV]\d+(?:\.\d+)?", token):
        return f"V{token[1:]}"
    if re.fullmatch(r"\d+(?:\.\d+)+", token):
        return token
    normalized = token.lower()
    if normalized in _BRAND_TOKENS:
        return _BRAND_TOKENS[normalized]
    return normalized[:1].upper() + normalized[1:]


def _merge_space_separated_version_tokens(tokens: list[str]) -> list[str]:
    merged: list[str] = []
    index = 0
    while index < len(tokens):
        current = tokens[index]
        next_token = tokens[index + 1] if index + 1 < len(tokens) else None
        if (
            next_token
            and re.fullmatch(r"\d{1,2}", current)
            and re.fullmatch(r"\d{1,2}", next_token)
            and _has_model_version_context(merged)
        ):
            merged.append(f"{int(current)}.{int(next_token)}")
            index += 2
            continue
        if (
            next_token
            and re.fullmatch(r"[vV]\d{1,2}", current)
            and re.fullmatch(r"\d{1,2}", next_token)
            and _has_model_version_context(merged)
        ):
            merged.append(f"V{int(current[1:])}.{int(next_token)}")
            index += 2
            continue
        merged.append(current)
        index += 1
    return merged


def _has_model_version_context(previous_tokens: list[str]) -> bool:
    return any(token.lower() in _MODEL_VERSION_CONTEXT_TOKENS for token in previous_tokens)


def _infer_owner(values: list[str], tokens: list[str]) -> str | None:
    token_owner = _infer_owner_from_text(" ".join(tokens))
    if token_owner:
        return token_owner
    return _infer_owner_from_text(" ".join(values))


def _infer_owner_from_text(value: str) -> str | None:
    haystack = value.lower()
    if "anthropic" in haystack or "claude" in haystack:
        return "Anthropic"
    if "deepseek" in haystack:
        return "DeepSeek"
    if "openai" in haystack or re.search(r"\bgpt[-_\s]?\d", haystack) or "chatgpt" in haystack:
        return "OpenAI"
    if "gemini" in haystack or "antigravity" in haystack or re.search(r"\baqa\b", haystack):
        return "Google"
    if "qwen" in haystack or "dashscope" in haystack or "alibaba" in haystack:
        return "Alibaba"
    if "doubao" in haystack or "volcengine" in haystack or "ark" in haystack:
        return "ByteDance"
    if "llama" in haystack or "meta-llama" in haystack:
        return "Meta"
    if "mistral" in haystack or "mixtral" in haystack:
        return "Mistral"
    if "grok" in haystack or "xai" in haystack:
        return "xAI"
    if "kimi" in haystack or "moonshot" in haystack:
        return "Moonshot"
    if "glm" in haystack or "zhipu" in haystack:
        return "Zhipu"
    return None


def _infer_family(owner: str | None, tokens: list[str]) -> str:
    lower_tokens = [token.lower() for token in tokens]
    if "claude" in lower_tokens or any(token in {"opus", "sonnet", "haiku"} for token in lower_tokens):
        return "Claude"
    if "gpt" in lower_tokens or any(token.startswith("gpt") for token in lower_tokens):
        return "GPT"
    if "chatgpt" in lower_tokens:
        return "ChatGPT"
    if "gemini" in lower_tokens or "antigravity" in lower_tokens or "aqa" in lower_tokens:
        return "Gemini"
    if owner == "DeepSeek":
        return "DeepSeek"
    if owner == "Alibaba":
        return "Qwen"
    if owner == "ByteDance":
        return "Ark"
    if owner == "Meta":
        return "Llama"
    if owner == "Mistral":
        return "Mixtral" if "mixtral" in lower_tokens else "Mistral"
    if owner == "xAI":
        return "Grok"
    if owner == "Moonshot":
        return "Kimi"
    if owner == "Zhipu":
        return "GLM"
    return "unknown"


def _compact_display_tokens(tokens: list[str], owner: str | None) -> list[str]:
    compacted = list(tokens)
    if owner == "Anthropic" and compacted[:1] == ["Anthropic"]:
        compacted = compacted[1:]
    if owner == "OpenAI" and compacted[:1] == ["OpenAI"]:
        compacted = compacted[1:]
    if owner == "Google" and compacted[:1] == ["Google"]:
        compacted = compacted[1:]
    return [
        token
        for index, token in enumerate(compacted)
        if token.lower() != compacted[index - 1].lower()
    ]


def _section_for_owner(owner: str | None, family: str, tokens: list[str]) -> str:
    if owner == "Anthropic":
        return "anthropic"
    if owner == "OpenAI":
        return "openai"
    if owner == "DeepSeek":
        return "deepseek"
    if owner == "Google":
        return "gemini"
    if owner == "Alibaba":
        return "qwen"
    if owner == "ByteDance":
        return "ark"
    if owner == "Meta":
        return "meta"
    if owner == "Mistral":
        return "mistral"
    if owner == "xAI":
        return "xai"
    if owner == "Moonshot":
        return "moonshot"
    if owner == "Zhipu":
        return "zhipu"
    if family != "unknown":
        return _normalize_key(family)
    return _normalize_key(tokens[0] if tokens else "unknown") or "unknown"


def _recognized_tokens(owner: str | None, family: str) -> set[str]:
    return {token.lower() for token in [owner or "", family] if token}


def _is_version_or_snapshot(token: str) -> bool:
    return bool(
        re.fullmatch(r"V?\d+(?:\.\d+)+", token)
        or re.fullmatch(r"20\d{2}-\d{2}-\d{2}", token)
        or re.fullmatch(r"20\d{6}", token)
        or re.fullmatch(r"\d{6}", token)
    )


def _strip_route_prefix(value: str) -> str:
    slash_index = value.find("/")
    return value[slash_index + 1 :] if slash_index >= 0 else value


def _first_non_empty(*values: str | None) -> str:
    return next((value.strip() for value in values if value and value.strip()), "")


def _normalize_key(value: str) -> str:
    return re.sub(r"(^-|-$)", "", re.sub(r"[^a-z0-9.]+", "-", value.strip().lower()))
