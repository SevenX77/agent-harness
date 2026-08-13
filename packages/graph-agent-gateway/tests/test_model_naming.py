"""What humans call a model, and which routes share that name."""

from __future__ import annotations

import inspect

from graph_agent_gateway.registry import (
    ProviderEndpoint,
    ProviderRoute,
    project_model_group_identity,
    project_model_identity,
)


def _route(provider_model_id: str) -> ProviderRoute:
    route_slug = provider_model_id.lower().replace("/", ".").replace("_", "-").replace(":", "-")
    return ProviderRoute(
        route_id=f"provider:{route_slug}",
        endpoint_id="provider",
        route_slug=route_slug,
        provider_model_id=provider_model_id,
    )


def _endpoint(endpoint_id: str = "provider") -> ProviderEndpoint:
    return ProviderEndpoint(
        endpoint_id=endpoint_id,
        protocol="openai_compatible",
        base_url="https://provider.example/v1",
    )


def test_naming_needs_nothing_the_gateway_endpoint_does_not_have() -> None:
    """The host's own label is passed in, never read off the endpoint.

    ``display_name`` is a label the USER typed into Studio; it lives on Studio's
    ``ProviderEndpoint`` subclass and is stripped before an endpoint reaches the
    gateway. Naming a model is still a gateway capability — it just has to ask
    for that label instead of assuming the field exists, or it would only work
    for hosts shaped like Studio.
    """

    assert "display_name" not in ProviderEndpoint.model_fields
    assert "provider_label" in inspect.signature(project_model_identity).parameters

    projection = project_model_identity(route=_route("gpt-5.5"), endpoint=_endpoint())

    assert projection.display_name == "GPT 5.5"


def test_the_model_names_itself_over_the_proxy_it_is_reached_through() -> None:
    projection = project_model_identity(
        route=_route("deepseek-r1"),
        endpoint=_endpoint("qiniu-anthropic"),
        provider_label="Qiniu Anthropic Proxy",
    )

    assert projection.display_name == "DeepSeek R1"
    assert projection.section_label == "deepseek"


def test_the_provider_label_names_a_model_its_own_id_cannot() -> None:
    """A bare model id with no brand token falls back to the host's label."""

    unbranded = project_model_identity(route=_route("large-2411"), endpoint=_endpoint())
    labelled = project_model_identity(
        route=_route("large-2411"),
        endpoint=_endpoint(),
        provider_label="Mistral Cloud",
    )

    assert unbranded.section_label != "mistral"
    assert labelled.section_label == "mistral"


def test_model_identity_projection_preserves_versions_dates_and_brands() -> None:
    examples = {
        "claude-opus-4-7": "Claude Opus 4.7",
        "claude-opus-4-1-20250805": "Claude Opus 4.1 20250805",
        "deepseek/deepseek-v3.1-terminus-thinking": "DeepSeek V3.1 Terminus Thinking",
        "gpt-5.5": "GPT 5.5",
        "antigravity-preview-05-2026": "Antigravity Preview 05 2026",
    }

    for provider_model_id, expected_display_name in examples.items():
        projection = project_model_identity(route=_route(provider_model_id), endpoint=_endpoint())

        assert projection.display_name == expected_display_name
        assert projection.section_label


def test_model_group_identity_omits_release_capability_and_channel_tokens() -> None:
    examples = {
        "claude-haiku-4-5-20251001": ("Claude Haiku 4.5", ("20251001",), (), ()),
        "claude-opus-4-1-20250805": ("Claude Opus 4.1", ("20250805",), (), ()),
        "deepseek/deepseek-v3-0324": ("DeepSeek V3", ("0324",), (), ()),
        "deepseek-v4-flash-260425": ("DeepSeek V4 Flash", ("260425",), (), ()),
        "deepseek/deepseek-v4-flash:free": ("DeepSeek V4 Flash", (), (), ("free",)),
        "deepseek/deepseek-v3.2-exp-thinking": ("DeepSeek V3.2 Exp", (), ("thinking",), ()),
        "deepseek/deepseek-v3.2-speciale-or": ("DeepSeek V3.2 Speciale", (), (), ("or",)),
        "antigravity-preview-05-2026": ("Antigravity Preview", ("05", "2026"), (), ()),
    }

    for provider_model_id, (
        expected_display_name,
        expected_release_tokens,
        expected_capability_tokens,
        expected_channel_tokens,
    ) in examples.items():
        projection = project_model_group_identity(
            route=_route(provider_model_id),
            endpoint=_endpoint(),
        )

        assert projection.display_name == expected_display_name
        assert projection.release_tokens == expected_release_tokens
        assert projection.capability_tokens == expected_capability_tokens
        assert projection.route_channel_tokens == expected_channel_tokens


def test_the_display_group_folds_what_the_execution_identity_keeps_apart() -> None:
    """Two grouping levels, on purpose — the coarse one must not be mistaken for
    the strict one.

    ``canonical_id`` (``registry/identity.py``) is the EXECUTION identity: it must
    stay byte-identical to the route id suffix, so a dated snapshot is its own
    group. The display group is deliberately coarser: it folds the snapshot away
    so a picker shows one row. Neither can stand in for the other.
    """

    dated = _route("claude-opus-4-1-20250805")
    undated = _route("claude-opus-4-1")

    assert dated.canonical_id != undated.canonical_id

    endpoint = _endpoint()
    dated_group = project_model_group_identity(route=dated, endpoint=endpoint)
    undated_group = project_model_group_identity(route=undated, endpoint=endpoint)

    assert dated_group.key == undated_group.key == "claude-opus-4-1"
    assert dated_group.route_display_name != undated_group.route_display_name
