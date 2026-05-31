"""Model group identity projection for Studio LLM route catalogs.

This module is the single backend home for deciding which provider routes are
the same user-facing model group. Routers should call this instead of applying
model-name cleanup rules inline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.models.llm_config import ProviderEndpoint, ProviderRoute
from app.services.llm_model_identity import project_model_identity


@dataclass(frozen=True)
class ModelGroupIdentityProjection:
    key: str
    display_name: str
    section_label: str
    route_display_name: str
    release_tokens: tuple[str, ...] = ()
    capability_tokens: tuple[str, ...] = ()
    route_channel_tokens: tuple[str, ...] = ()


_CAPABILITY_TOKENS = {
    "audio",
    "image",
    "reasoning",
    "thinking",
    "tool",
    "tools",
    "vision",
}
_ROUTE_CHANNEL_TOKENS = {
    "free",
    "or",
}


def project_model_group_identity(
    *,
    route: ProviderRoute,
    endpoint: ProviderEndpoint,
) -> ModelGroupIdentityProjection:
    """Return the group identity used by Available Models.

    The model group name keeps the model family and stable variant tokens, but
    strips release snapshots, capability tokens, and provider route channels.
    Exact execution still uses each route_id; this projection is display/group
    identity only.
    """

    identity = project_model_identity(route=route, endpoint=endpoint)
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
    return re.sub(r"(^-|-$)", "", re.sub(r"[^a-z0-9]+", "-", value.strip().lower()))


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
        and _has_model_version_context(tokens[:index])
    )


def _has_model_version_context(tokens: tuple[str, ...]) -> bool:
    return any(
        re.fullmatch(r"(?:V|R)?\d+(?:\.\d+)?", token, flags=re.IGNORECASE)
        for token in tokens
    )


def _is_preview_month_year_pair(tokens: tuple[str, ...], index: int) -> bool:
    token = tokens[index]
    next_token = tokens[index + 1]
    has_preview_context = any(previous.lower() == "preview" for previous in tokens[:index])
    return bool(
        has_preview_context
        and re.fullmatch(r"\d{1,2}", token)
        and re.fullmatch(r"20\d{2}", next_token)
    )
