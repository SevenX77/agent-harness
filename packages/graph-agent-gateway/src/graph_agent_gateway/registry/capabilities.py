"""Provider route capability normalization.

Capabilities describe observed/provider-documented support and bounds. They
must not encode user runtime intent; role/profile route entries own that.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from graph_agent_gateway.registry.schema import (
    CapabilitySource,
    CapabilityValue,
    Protocol,
    ProviderRoute,
    RuntimeSettingDescriptor,
    VerifiedProfile,
)

_REASONING_CAPABILITIES = frozenset({"thinking", "reasoning"})
"""The capability names a probe candidate declares when it asks the model to think.

Reading the declared capability is what makes ``thinking_protocol`` measured: a
candidate declared ``thinking`` that came back ``ready`` means a request shaped
for thinking was accepted. Searching a profile's identifiers for the substring
"thinking" would not — a name is a label, and this conclusion is stamped
``probed_verified``.
"""

RUNTIME_SETTING_DESCRIPTORS: tuple[tuple[str, str, str], ...] = (
    ("temperature", "temperature", "number"),
    ("top_p", "top_p", "number"),
    ("max_output_tokens", "max_output_tokens", "integer"),
    ("stop_sequences", "stop_sequences", "string_list"),
    ("seed", "seed", "integer"),
    ("tool_choice", "tool_choice", "string"),
    ("parallel_tool_calls", "parallel_tool_calls", "boolean"),
    ("structured_output", "structured_output_protocol", "object"),
    ("reasoning.enabled", "thinking_protocol", "boolean"),
    ("reasoning.effort", "reasoning_effort", "string"),
    ("reasoning.budget_tokens", "reasoning_budget_tokens", "integer"),
)


def verified_profile_capabilities(
    profiles: Sequence[VerifiedProfile],
) -> dict[str, CapabilityValue]:
    """What the ready profiles among these PROVE about the route.

    Only ``ready`` profiles count: a failed or catalog-candidate profile is a
    question, not an answer, and everything returned here is stamped
    ``probed_verified``.
    """
    ready_profiles = [profile for profile in profiles if profile.status == "ready"]
    if not ready_profiles:
        return {}

    capabilities: dict[str, CapabilityValue] = {
        "verified_methods": CapabilityValue(
            value=sorted({profile.method_id for profile in ready_profiles}),
            source="probed_verified",
        ),
    }
    for direction in ("input", "output"):
        modalities = sorted(
            {
                modality
                for profile in ready_profiles
                for modality in (getattr(profile, f"{direction}_modalities") or [])
            }
        )
        if modalities:
            capabilities[f"{direction}_modalities"] = CapabilityValue(
                value=modalities,
                source="probed_verified",
            )
    if any(profile.capability in _REASONING_CAPABILITIES for profile in ready_profiles):
        capabilities["thinking_protocol"] = CapabilityValue(
            value=True,
            source="probed_verified",
        )
    return capabilities


def route_effective_capabilities(route: ProviderRoute) -> dict[str, CapabilityValue]:
    """The route's capabilities with what its ready profiles measured applied on top.

    Measurement outranks the claim: a route may be listed as not supporting
    thinking while a thinking probe on it came back ``ready``, and the probe is
    the one that actually asked.
    """
    return {**route.capabilities, **verified_profile_capabilities(route.verified_profiles)}


def normalize_route_capabilities(
    *,
    protocol: Protocol,
    provider_model_id: str,
    raw_capabilities: Mapping[str, Any] | None = None,
    source: CapabilitySource = "api_list",
) -> dict[str, CapabilityValue]:
    """Return normalized route capability records for one provider model."""
    raw = raw_capabilities or {}
    normalized: dict[str, CapabilityValue] = {
        "min_output_tokens": CapabilityValue(
            value=1,
            source="provider_doc",
            message=(
                "Common chat APIs accept at least one output token "
                "when no provider-specific floor is documented."
            ),
        )
    }

    raw_input_modalities = _modalities_from_raw(raw, "input")
    raw_output_modalities = _modalities_from_raw(raw, "output")
    if raw_input_modalities:
        normalized["input_modalities"] = CapabilityValue(value=raw_input_modalities, source=source)
    if raw_output_modalities:
        normalized["output_modalities"] = CapabilityValue(value=raw_output_modalities, source=source)

    max_output_runtime = _runtime_setting_capability(raw.get("max_output_tokens"))
    if max_output_runtime is not None:
        normalized["max_output_tokens"] = CapabilityValue(value=max_output_runtime, source=source)
    else:
        max_output = _first_int(
            raw,
            "max_output_tokens",
            "maxOutputTokens",
            "max_tokens",
            "output_token_limit",
            "outputTokenLimit",
            "output_token_limit",
        )
        if max_output is None:
            max_output = _first_int(
                _mapping_value(raw, "token_limits"),
                "max_output_token_length",
                "max_output_tokens",
                "output_token_limit",
                "outputTokenLimit",
            )
        if max_output is not None:
            normalized["max_output_tokens"] = CapabilityValue(value=max_output, source=source)
    max_input = _first_int(
        raw,
        "max_input_tokens",
        "maxInputTokens",
        "input_token_limit",
        "inputTokenLimit",
        "max_context_tokens",
        "max_context_length",
        "context_window",
        "context_length",
    )
    if max_input is None:
        max_input = _first_int(
            _mapping_value(raw, "token_limits"),
            "max_input_token_length",
            "max_input_tokens",
            "input_token_limit",
            "inputTokenLimit",
            "context_window",
            "context_length",
        )
    if max_input is not None:
        normalized["max_input_tokens"] = CapabilityValue(value=max_input, source=source)

    for runtime_key in (
        "temperature",
        "top_p",
        "stop_sequences",
        "seed",
        "tool_choice",
        "parallel_tool_calls",
        "reasoning_effort",
    ):
        runtime_capability = _runtime_setting_capability(raw.get(runtime_key))
        if runtime_capability is not None:
            normalized[runtime_key] = CapabilityValue(value=runtime_capability, source=source)

    if _supported(_provider_feature(raw, "structured_outputs")):
        normalized["structured_output_protocol"] = CapabilityValue(value=True, source=source)
    if (
        _supported(_provider_feature(raw, "image_input"))
        or _supported(_provider_feature(raw, "vision"))
        or "image" in raw_input_modalities
    ):
        normalized["vision"] = CapabilityValue(value=True, source=source)
    if (
        _supported(_provider_feature(raw, "tool_use"))
        or _supported(_provider_feature(raw, "tool_calling"))
        or _supported(_provider_feature(raw, "tools"))
    ):
        normalized["tool_protocol"] = CapabilityValue(value=True, source=source)

    if protocol == "anthropic_compatible" and "tool_protocol" not in normalized:
        normalized["tool_protocol"] = CapabilityValue(
            value=True,
            source="provider_doc",
            message="Anthropic Messages API supports tool use for supported Claude chat models.",
        )

    if protocol == "anthropic_compatible" and _supported(_provider_feature(raw, "thinking")):
        manual_budget_supported = _anthropic_manual_thinking_budget_supported(provider_model_id)
        adaptive_supported = _anthropic_adaptive_thinking_supported(provider_model_id)
        normalized["thinking_protocol"] = CapabilityValue(value=True, source=source)
        normalized["adaptive_thinking"] = CapabilityValue(
            value=adaptive_supported,
            source="provider_doc",
            message=(
                "Anthropic adaptive thinking is the preferred thinking mode for this Claude model."
                if adaptive_supported
                else "This Claude model uses manual thinking budgets instead of adaptive thinking."
            ),
        )
        normalized["manual_thinking_budget_supported"] = CapabilityValue(
            value=manual_budget_supported,
            source="provider_doc",
            message=(
                "Claude Opus 4.7 uses adaptive thinking instead of manual thinking budgets."
                if not manual_budget_supported
                else (
                    "Manual Anthropic thinking budgets are supported "
                    "but adaptive thinking is preferred."
                )
            ),
        )
        if manual_budget_supported:
            normalized["reasoning_budget_tokens"] = CapabilityValue(
                value={"min": 1024, "default": 4096},
                source="provider_doc",
                message=(
                    "Anthropic manual extended thinking requires a minimum "
                    "thinking budget of 1024 tokens; Studio defaults to 4096."
                ),
            )
            normalized["min_thinking_budget_tokens"] = CapabilityValue(
                value=1024,
                source="provider_doc",
                message=(
                    "Anthropic manual extended thinking requires a minimum "
                    "thinking budget of 1024 tokens."
                ),
            )
            normalized["default_thinking_budget_tokens"] = CapabilityValue(
                value=4096,
                source="provider_doc",
                message="Studio default for Anthropic manual thinking fallback.",
            )
            normalized["requires_thinking_budget_lt_max_output"] = CapabilityValue(
                value=True,
                source="provider_doc",
                message=(
                    "Anthropic manual thinking budget must be smaller "
                    "than max_output_tokens."
                ),
            )
    elif _supported(_provider_feature(raw, "thinking")):
        normalized["thinking_protocol"] = CapabilityValue(value=True, source=source)

    return normalized


def measured_effort_capability(levels: Sequence[str]) -> CapabilityValue:
    """The levels a route was measured to accept, as the record fitting reads.

    An empty measurement is recorded too: "it sells none of them" is an answer,
    while an absent capability reads as "nobody has asked yet" and invites the
    same spend again.
    """
    measured = [level for level in levels if isinstance(level, str)]
    return CapabilityValue(
        value={"supported": bool(measured), "values": measured},
        source="probed_verified",
        message=(
            "Measured by asking this route for each level: " + ", ".join(measured) + "."
            if measured
            else "This route refused every reasoning effort level it was offered."
        ),
    )


def measured_image_input(*, accepted: bool) -> dict[str, CapabilityValue]:
    """What sending a route one real image settles.

    Both answers are recorded, for the reason `measured_effort_capability` gives
    above: a refusal is an answer, while leaving the capability alone reads as
    "nobody has asked yet". Here the stakes are higher than an unspent probe — a
    catalog's `provider_doc` claim of image support would otherwise stand forever
    against a model that has said, in words, that it takes text only.

    The answer always lands on `vision`, because that capability holds a yes/no
    about image input and a measured `False` cannot be blended away. It lands on
    `input_modalities` only when the answer is yes, and that asymmetry is the
    point: a modality list is a lower bound (hosts union it — the docs list one
    modality, a verified profile proves another, the route does both), so adding
    `image` to it is a claim the probe can support, while writing `["text"]` into
    it would state a completeness this probe never established. A refusal bounds
    images from above, and `vision` is where an upper bound belongs.

    Text rides along in the accepted case because the probe uses the route's own
    verified call method: reaching the model at all is a text call that worked.
    """
    message = (
        "Measured by sending this route an image: it was accepted."
        if accepted
        else "Measured by sending this route an image: it answered that it takes text only."
    )
    measured = {
        "vision": CapabilityValue(value=accepted, source="probed_verified", message=message),
    }
    if accepted:
        measured["input_modalities"] = CapabilityValue(
            value=["text", "image"],
            source="probed_verified",
            message=message,
        )
    return measured


def measured_tool_calling(*, closed_the_loop: bool) -> dict[str, CapabilityValue]:
    """What watching a route call a tool settles.

    It lands on `tool_protocol`, the capability that until now could only ever
    be set from what a provider record claims (`tool_use` / `tool_calling` /
    `tools`, read above). A route that has been watched emitting a tool call has
    answered the same question by measurement, and `probed_verified` is where a
    measurement outranks a document.

    **This never records `False`, and that asymmetry is deliberate** — unlike
    `measured_image_input`, whose refusal is a provider saying in words that it
    takes text only. Here a failure to see a tool call has two indistinguishable
    causes: a protocol with no tools, and a model that simply answered in prose.
    Writing `False` would delete a capability the route may well have, and a
    capability that quietly shrinks is worse than one left unmeasured — the same
    rule `accepted_effort_levels` follows when it returns `None`.

    Closing the loop cannot change the value, because the capability is a yes/no
    about the protocol. It rides `message_code` instead — a token the host can
    render in the reader's own language — with the prose message kept alongside
    for logs. That split is what lets the stronger observation actually reach
    the reader deciding whether to hand this route an agent phase; while it
    lived only in the sentence below, no UI could tell the two rungs apart
    without matching English text.
    """
    message_code = "tool_loop_closed_the_loop" if closed_the_loop else "tool_loop_called_the_tool"
    message = (
        "Measured by giving this route a tool it needed: it called the tool and came "
        "back out of the loop carrying the result."
        if closed_the_loop
        else "Measured by giving this route a tool it needed: it called the tool."
    )
    return {
        "tool_protocol": CapabilityValue(
            value=True,
            source="probed_verified",
            message=message,
            message_code=message_code,
        )
    }


def build_runtime_setting_descriptors(
    route: ProviderRoute,
) -> dict[str, RuntimeSettingDescriptor]:
    """Build fixed frontend setting descriptors from normalized route capabilities."""
    return {
        key: _runtime_setting_descriptor(
            key,
            capability_key,
            value_type,
            route.capabilities.get(capability_key),
        )
        for key, capability_key, value_type in RUNTIME_SETTING_DESCRIPTORS
    }


def _runtime_setting_descriptor(
    key: str,
    capability_key: str,
    value_type: str,
    capability: CapabilityValue | None,
) -> RuntimeSettingDescriptor:
    supported: bool | None = None
    minimum: float | None = None
    maximum: float | None = None
    default: object | None = None
    allowed_values: list[str] = []
    source: CapabilitySource | Literal["unknown"] = "unknown"
    message: str | None = None

    if capability is not None:
        source = capability.source
        message = capability.message
        value = capability.value
        if isinstance(value, bool):
            supported = value
        elif isinstance(value, int | float) and not isinstance(value, bool):
            supported = True
            maximum = float(value) if key == "max_output_tokens" else None
            default = value if key.endswith("budget_tokens") else default
        elif isinstance(value, dict):
            raw_supported = value.get("supported")
            supported = raw_supported if isinstance(raw_supported, bool) else True
            raw_min = value.get("min")
            raw_max = value.get("max")
            raw_default = value.get("default")
            minimum = float(raw_min) if isinstance(raw_min, int | float) else None
            maximum = float(raw_max) if isinstance(raw_max, int | float) else None
            default = raw_default
            raw_values = value.get("values")
            if isinstance(raw_values, list):
                allowed_values = [item for item in raw_values if isinstance(item, str)]
        else:
            supported = bool(value)

    return RuntimeSettingDescriptor(
        key=key,
        value_type=value_type,  # type: ignore[arg-type]
        supported=supported,
        min=minimum,
        max=maximum,
        default=default,
        allowed_values=allowed_values,
        source=source,
        message=message,
    )


def _first_int(raw: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, int) and value > 0:
            return value
    return None


def _mapping_value(raw: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = raw.get(key)
    return value if isinstance(value, Mapping) else {}


def _provider_feature(raw: Mapping[str, Any], key: str) -> object:
    direct = raw.get(key)
    if direct is not None:
        return direct
    capabilities = _mapping_value(raw, "capabilities")
    if key in capabilities:
        return capabilities[key]
    features = _mapping_value(raw, "features")
    return features.get(key)


def _modalities_from_raw(raw: Mapping[str, Any], direction: Literal["input", "output"]) -> list[str]:
    snake_key = f"{direction}_modalities"
    camel_key = f"{direction}Modalities"
    candidates = [
        raw.get(snake_key),
        raw.get(camel_key),
        _mapping_value(raw, "modalities").get(snake_key),
        _mapping_value(raw, "modalities").get(camel_key),
    ]
    for candidate in candidates:
        modalities = _string_list(candidate)
        if modalities:
            return modalities
    return []


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        normalized = item.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _supported(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, Mapping):
        supported = value.get("supported")
        if isinstance(supported, bool):
            return supported
        return any(isinstance(child, bool) and child for child in value.values())
    return False


def _runtime_setting_capability(value: object) -> bool | dict[str, object] | None:
    if isinstance(value, bool):
        return {"supported": value}
    if not isinstance(value, Mapping):
        return None
    result: dict[str, object] = {}
    for key in ("supported", "min", "max", "default", "values"):
        if key in value:
            result[key] = value[key]
    return result or None


def _anthropic_manual_thinking_budget_supported(provider_model_id: str) -> bool:
    normalized = provider_model_id.strip().lower().replace("_", "-")
    return not normalized.startswith("claude-opus-4-7")


def _anthropic_adaptive_thinking_supported(provider_model_id: str) -> bool:
    normalized = provider_model_id.strip().lower().replace("_", "-")
    return normalized.startswith(
        (
            "claude-opus-4-7",
            "claude-opus-4-6",
            "claude-sonnet-4-6",
        )
    )


__all__ = [
    "build_runtime_setting_descriptors",
    "route_effective_capabilities",
    "measured_effort_capability",
    "measured_image_input",
    "measured_tool_calling",
    "normalize_route_capabilities",
    "verified_profile_capabilities",
]
