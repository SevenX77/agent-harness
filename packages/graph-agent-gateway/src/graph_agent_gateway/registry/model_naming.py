"""What humans call a model, and which routes share that name.

Two projections over one raw provider model id:

- ``project_model_identity`` reads the id as a name — brand, family, readable
  form, and the tokens it could not account for.
- ``project_model_group_identity`` builds on it to answer "which routes are the
  same model to a person", folding release snapshots, capability suffixes and
  proxy channels away.

**Not to be confused with ``registry.identity``.** That module answers the
EXECUTION question — the ids a route is stored and called under — and its
``canonical_id`` must stay byte-identical to the route id suffix, so
``claude-opus-4-1-20250805`` and ``claude-opus-4-1`` are two different models
there. The grouping here is deliberately coarser: it folds the snapshot away so
a picker shows one row. Neither may stand in for the other; a caller that needs
to actually run a model wants ``canonical_id``, and a caller drawing a list
wants this.

The host's own label for a provider (whatever a user typed when adding it) is
passed in as ``provider_label`` rather than read off the endpoint — the gateway
``ProviderEndpoint`` has no display field, and a capability that assumed one
would only work for hosts shaped like Studio.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from graph_agent_gateway.registry.schema import ProviderEndpoint, ProviderRoute


@dataclass(frozen=True)
class ModelIdentityProjection:
    display_name: str
    section_label: str
    confidence: str
    tokens: tuple[str, ...] = ()
    display_tokens: tuple[str, ...] = ()
    unknown_tokens: tuple[str, ...] = ()


@dataclass(frozen=True)
class _OwnerReading:
    """Who made a model, and which text said so.

    ``source`` is one of ``model_id`` (the id names a maker this package knows),
    ``declared_vendor`` (the id carries a ``vendor/`` prefix no table here
    recognises), or ``endpoint_context`` (the id declares nothing, so the
    endpoint it is served from was consulted).
    """

    owner: str | None
    source: str
    declared_vendor: str


@dataclass(frozen=True)
class ModelGroupIdentityProjection:
    key: str
    display_name: str
    section_label: str
    route_display_name: str
    release_tokens: tuple[str, ...] = ()
    capability_tokens: tuple[str, ...] = ()
    route_channel_tokens: tuple[str, ...] = ()


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
_MODEL_BRAND_CONTEXT_TOKENS = {
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
# Tokens that say HOW a model was reached rather than which model it is, and so
# never belong to the group name — only when they end the id, where a proxy
# appends them.
_ROUTE_CHANNEL_TOKENS = {
    "free",
    "or",
}


def project_model_identity(
    *,
    route: ProviderRoute,
    endpoint: ProviderEndpoint,
    provider_label: str | None = None,
) -> ModelIdentityProjection:
    """Read a provider model id as a name: brand, family, and readable form.

    ``provider_label`` is the host's own user-facing label for the endpoint, used
    only as a fallback clue when the model id names no brand of its own.
    """

    raw_name = _first_non_empty(route.provider_model_id, route.canonical_id, route.route_slug)
    tokens = _tokenize_model_name(_strip_route_prefix(raw_name))
    reading = _read_owner(
        tokens=tokens,
        model_ids=[route.provider_model_id, route.canonical_id],
        declared_vendor=_declared_vendor(raw_name),
        context=[endpoint.endpoint_id, provider_label or ""],
    )
    family = _infer_family(reading.owner, tokens)
    display_tokens = _compact_display_tokens(tokens, reading.owner)
    display_name = " ".join(display_tokens) if display_tokens else _titleize_model_name(route.canonical_id)
    return ModelIdentityProjection(
        display_name=display_name,
        section_label=_section_for_owner(reading, family, tokens),
        confidence=_confidence(reading, family),
        tokens=tuple(tokens),
        display_tokens=tuple(display_tokens),
        unknown_tokens=_unrecognized_tokens(tokens, reading.owner, family),
    )


def project_model_group_identity(
    *,
    route: ProviderRoute,
    endpoint: ProviderEndpoint,
    provider_label: str | None = None,
) -> ModelGroupIdentityProjection:
    """Return which routes are the same model to a person.

    The group name keeps the model family and stable variant tokens, but strips
    release snapshots, capability tokens, and provider route channels. Running a
    model still goes by its own ``route_id``; this decides what a list shows.
    """

    identity = project_model_identity(route=route, endpoint=endpoint, provider_label=provider_label)
    split = _split_model_group_tokens(identity.display_tokens or identity.tokens)
    display_tokens = split["group_tokens"] or identity.display_tokens or identity.tokens
    display_name = " ".join(display_tokens).strip() or identity.display_name
    return ModelGroupIdentityProjection(
        key=normalize_model_group_key(display_name),
        display_name=display_name,
        section_label=identity.section_label,
        route_display_name=identity.display_name,
        release_tokens=split["release_tokens"],
        capability_tokens=split["capability_tokens"],
        route_channel_tokens=split["route_channel_tokens"],
    )


def normalize_model_group_key(value: str) -> str:
    return re.sub(r"(?:^-)|(?:-$)", "", re.sub(r"[^a-z0-9]+", "-", value.strip().lower()))


def _split_model_group_tokens(tokens: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    release_indexes = _release_token_indexes(tokens)
    group_tokens: list[str] = []
    release_tokens: list[str] = []
    capability_tokens: list[str] = []
    route_channel_tokens: list[str] = []

    for index, token in enumerate(tokens):
        normalized = token.lower()
        if _is_route_channel_token(normalized, index, len(tokens)):
            route_channel_tokens.append(normalized)
            continue
        if normalized in _CAPABILITY_TOKENS:
            capability_tokens.append(normalized)
            continue
        if index in release_indexes:
            release_tokens.append(token)
            continue
        group_tokens.append(token)

    return {
        "group_tokens": tuple(group_tokens),
        "release_tokens": tuple(release_tokens),
        "capability_tokens": tuple(capability_tokens),
        "route_channel_tokens": tuple(route_channel_tokens),
    }


def _is_route_channel_token(token: str, index: int, token_count: int) -> bool:
    return token in _ROUTE_CHANNEL_TOKENS and index == token_count - 1


def _release_token_indexes(tokens: tuple[str, ...]) -> set[int]:
    release_indexes: set[int] = set()
    for index, token in enumerate(tokens):
        if _is_release_snapshot_token(token) or _is_terminal_mmdd_release_token(tokens, index):
            release_indexes.add(index)

    for index in range(len(tokens) - 1):
        if _is_preview_month_year_pair(tokens, index):
            release_indexes.update({index, index + 1})

    return release_indexes


def _is_release_snapshot_token(token: str) -> bool:
    return bool(
        re.fullmatch(r"20\d{2}-\d{2}-\d{2}", token)
        or re.fullmatch(r"20\d{6}", token)
        or re.fullmatch(r"\d{6}", token)
    )


def _is_terminal_mmdd_release_token(tokens: tuple[str, ...], index: int) -> bool:
    token = tokens[index]
    return bool(
        index == len(tokens) - 1
        and re.fullmatch(r"(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])", token)
        and _tokens_include_version_number(tokens[:index])
    )


def _tokens_include_version_number(tokens: tuple[str, ...]) -> bool:
    return any(_is_version_number_token(token) for token in tokens)


def _is_preview_month_year_pair(tokens: tuple[str, ...], index: int) -> bool:
    token = tokens[index]
    next_token = tokens[index + 1]
    has_preview_context = any(previous.lower() == "preview" for previous in tokens[:index])
    return bool(
        has_preview_context
        and re.fullmatch(r"\d{1,2}", token)
        and re.fullmatch(r"20\d{2}", next_token)
    )


def _tokenize_model_name(value: str) -> list[str]:
    placeholders: list[str] = []

    def protect(token: str) -> str:
        placeholders.append(token)
        return f"QQMODEL{len(placeholders) - 1}QQ"

    protected = re.sub(
        r"\b(20\d{2})[-_.](\d{1,2})[-_.](\d{1,2})\b",
        lambda match: protect(f"{match.group(1)}-{match.group(2).zfill(2)}-{match.group(3).zfill(2)}"),
        value.strip(),
    )
    protected = re.sub(
        r"\b([vV]?)(\d{1,2})[-_.](\d{1,2})(?![-_.]\d)\b",
        lambda match: protect(f"{'V' if match.group(1) else ''}{int(match.group(2))}.{int(match.group(3))}"),
        protected,
    )
    raw_tokens = re.split(r"[^A-Za-z0-9]+", protected)
    titleized = [_titleize_token(_restore_placeholder(token, placeholders)) for token in raw_tokens if token]
    titleized = _merge_space_separated_version_tokens(titleized)
    deduped = [
        token for index, token in enumerate(titleized) if token and token.lower() != titleized[index - 1].lower()
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
            and _tokens_include_model_brand(merged)
        ):
            merged.append(f"{int(current)}.{int(next_token)}")
            index += 2
            continue
        if (
            next_token
            and re.fullmatch(r"[vV]\d{1,2}", current)
            and re.fullmatch(r"\d{1,2}", next_token)
            and _tokens_include_model_brand(merged)
        ):
            merged.append(f"V{int(current[1:])}.{int(next_token)}")
            index += 2
            continue
        merged.append(current)
        index += 1
    return merged


def _tokens_include_model_brand(previous_tokens: list[str]) -> bool:
    return any(token.lower() in _MODEL_BRAND_CONTEXT_TOKENS for token in previous_tokens)


def _read_owner(
    *,
    tokens: list[str],
    model_ids: list[str],
    declared_vendor: str,
    context: list[str],
) -> _OwnerReading:
    """Decide who made a model, and record what said so.

    The model's own text is asked first. A ``vendor/`` prefix it carries is an
    answer even when no table here recognises the vendor: "made by someone this
    package does not know" is true, while "made by whoever runs the host it is
    served from" is a guess that a proxy's vanity hostname can win outright.
    Only an id that declares nothing falls through to its surroundings.
    """

    owner = _infer_owner_from_text(" ".join([*tokens, *model_ids]))
    if owner:
        return _OwnerReading(owner=owner, source="model_id", declared_vendor=declared_vendor)
    if declared_vendor:
        return _OwnerReading(owner=None, source="declared_vendor", declared_vendor=declared_vendor)
    return _OwnerReading(
        owner=_infer_owner_from_text(" ".join(context)),
        source="endpoint_context",
        declared_vendor="",
    )


def _confidence(reading: _OwnerReading, family: str) -> str:
    """How the owner was arrived at, not how likely it is to be right.

    ``high`` is reserved for a model that named its maker. Anything read off the
    endpoint is a guess about the neighbourhood, however good, and a host that
    wants to show a name unedited needs to be able to tell the two apart.
    """

    if reading.source == "model_id":
        return "high"
    if reading.owner or family != "unknown":
        return "medium"
    return "low"


def _infer_owner_from_text(value: str) -> str | None:
    haystack = value.lower()
    if "anthropic" in haystack or "claude" in haystack:
        return "Anthropic"
    if "deepseek" in haystack:
        return "DeepSeek"
    if "openai" in haystack or re.search(r"\bgpt[-_\s]?\d", haystack) or "chatgpt" in haystack:
        return "OpenAI"
    if (
        "gemini" in haystack
        or "google" in haystack
        or "antigravity" in haystack
        or re.search(r"\baqa\b", haystack)
    ):
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
    return [token for index, token in enumerate(compacted) if token.lower() != compacted[index - 1].lower()]


def _section_for_owner(reading: _OwnerReading, family: str, tokens: list[str]) -> str:
    owner = reading.owner
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
    if reading.declared_vendor:
        return _normalize_key(reading.declared_vendor)
    return _normalize_key(tokens[0] if tokens else "unknown") or "unknown"


def _unrecognized_tokens(tokens: list[str], owner: str | None, family: str) -> tuple[str, ...]:
    """The words in a model id that no table here claims.

    This is what a maintainer reads to learn which token to teach the module
    next, so it must not name words the module already used. Every other
    classification is consulted rather than re-derived: the group splitter says
    which tokens are release snapshots, capabilities, or route channels, and the
    brand / model-line / variant tables and the owner inference say the rest.
    Re-deriving "recognised" as the owner and family NAMES was the whole defect
    — ``opus`` proves the family is Claude and does not spell it.
    """

    remaining = _split_model_group_tokens(tuple(tokens))["group_tokens"]
    claimed = {token.lower() for token in [owner or "", family] if token}
    return tuple(dict.fromkeys(token.lower() for token in remaining if not _is_claimed_token(token, claimed)))


def _is_claimed_token(token: str, claimed: set[str]) -> bool:
    normalized = token.lower()
    return (
        normalized in claimed
        or normalized in _BRAND_TOKENS
        or normalized in _MODEL_BRAND_CONTEXT_TOKENS
        or normalized in _VARIANT_TOKENS
        or _is_version_number_token(normalized)
        or _infer_owner_from_text(normalized) is not None
    )


def _is_version_number_token(token: str) -> bool:
    """A version component as this module writes them: ``4``, ``4.1``, ``V3``, ``R1``.

    Bounded to one or two digits because that is what every other version rule
    here reads — the tokenizer only merges ``\\d{1,2}`` pairs into a version, so
    a longer run of digits is a date or a marker this module does not model.
    """

    return bool(re.fullmatch(r"(?:V|R)?\d{1,2}(?:\.\d{1,2})?", token, flags=re.IGNORECASE))


def _declared_vendor(value: str) -> str:
    """The ``vendor/`` prefix a model id carries, or "" when it carries none."""

    slash_index = value.find("/")
    return value[:slash_index].strip().lower() if slash_index > 0 else ""


def _strip_route_prefix(value: str) -> str:
    slash_index = value.find("/")
    return value[slash_index + 1 :] if slash_index >= 0 else value


def _first_non_empty(*values: str | None) -> str:
    return next((value.strip() for value in values if value and value.strip()), "")


def _normalize_key(value: str) -> str:
    return re.sub(r"(?:^-)|(?:-$)", "", re.sub(r"[^a-z0-9.]+", "-", value.strip().lower()))


__all__ = [
    "ModelGroupIdentityProjection",
    "ModelIdentityProjection",
    "normalize_model_group_key",
    "project_model_group_identity",
    "project_model_identity",
]
