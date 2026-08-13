"""Which section a GROUP of same-model routes files under is decided once, here.

#779 made the route-level rule "a declaration outranks a guess", but the answer
for a whole group was still assembled by each host: Studio's backend re-derived
a section from the display name (overriding the gateway's answer), then fell
back to an equal-weight majority vote in which "the model said minimax" and
"the proxy's hostname says anthropic" counted the same — so MiniMax-M1, served
declared on OpenRouter and bare on two anthropic-named proxies, was filed under
``anthropic`` by two guesses outvoting one declaration. The frontend kept a
third copy of the same if-chain as its own fallback.

Decision record: docs/design/2026-08-13-gateway-role-model-and-section-truth-decision.md
(决策二): the projection now SAYS where its owner came from (``owner_source``),
and ``elect_model_group_section`` runs the group-level election in this package
— declarations vote first, guesses only speak when nobody declared anything,
majority within a tier, lexicographic order settling ties so the answer is
deterministic.
"""

from __future__ import annotations

import re

from graph_agent_gateway.registry import (
    ModelGroupIdentityProjection,
    ProviderEndpoint,
    ProviderRoute,
    elect_model_group_section,
    project_model_group_identity,
    project_model_identity,
)

# The measured 2026-08-13 shape: a proxy whose hostname-derived endpoint id
# names a vendor that has nothing to do with the models it serves.
PROXY_ENDPOINT_ID = "anthropic-qnaigc-com-anthropic-38963c9239"


def _route(endpoint_id: str, provider_model_id: str) -> ProviderRoute:
    slug = re.sub(r"[^a-z0-9._-]+", "-", provider_model_id.replace("/", ".").lower())
    return ProviderRoute(
        route_id=f"{endpoint_id}:{slug}",
        endpoint_id=endpoint_id,
        route_slug=slug,
        provider_model_id=provider_model_id,
    )


def _endpoint(endpoint_id: str) -> ProviderEndpoint:
    return ProviderEndpoint(
        endpoint_id=endpoint_id,
        protocol="openai_compatible",
        base_url="https://proxy.example/v1",
    )


def _group_projection(endpoint_id: str, provider_model_id: str) -> ModelGroupIdentityProjection:
    return project_model_group_identity(
        route=_route(endpoint_id, provider_model_id),
        endpoint=_endpoint(endpoint_id),
        provider_label=None,
    )


def _vote(owner_source: str, section_label: str) -> ModelGroupIdentityProjection:
    """A projection reduced to the two facts the election reads."""

    return ModelGroupIdentityProjection(
        key="k",
        display_name="d",
        section_label=section_label,
        owner_source=owner_source,  # type: ignore[arg-type]
        route_display_name="d",
    )


def test_the_projection_says_where_its_owner_came_from() -> None:
    named = project_model_identity(
        route=_route(PROXY_ENDPOINT_ID, "claude-opus-4-1"),
        endpoint=_endpoint(PROXY_ENDPOINT_ID),
    )
    declared = project_model_identity(
        route=_route(PROXY_ENDPOINT_ID, "xiaomi/mimo-v2.5"),
        endpoint=_endpoint(PROXY_ENDPOINT_ID),
    )
    guessed = project_model_identity(
        route=_route("provider", "large-2411"),
        endpoint=_endpoint("provider"),
        provider_label="Mistral Cloud",
    )

    assert named.owner_source == "model_id"
    assert declared.owner_source == "declared_vendor"
    assert guessed.owner_source == "endpoint_context"


def test_the_group_projection_carries_the_same_fact() -> None:
    """The group-level election runs over group projections, so the fact must
    survive the one step from identity to group."""

    assert _group_projection(PROXY_ENDPOINT_ID, "minimax/minimax-m1").owner_source == "declared_vendor"


def test_one_declaration_beats_many_guesses() -> None:
    """The MiniMax-M1 residual from the #779 verification, exactly: declared
    ``minimax/`` on OpenRouter, bare on two anthropic-named proxies. Equal-weight
    majority filed it under anthropic; the election must not."""

    projections = [
        _group_projection("openrouter", "minimax/minimax-m1"),
        _group_projection(PROXY_ENDPOINT_ID, "minimax-m1"),
        _group_projection("anthropic-other-proxy", "minimax-m1"),
    ]
    assert [projection.owner_source for projection in projections] == [
        "declared_vendor",
        "endpoint_context",
        "endpoint_context",
    ], "the fixture must reproduce the measured disagreement"

    assert elect_model_group_section(projections) == "minimax"


def test_a_model_that_named_itself_outranks_even_a_declaration() -> None:
    assert elect_model_group_section([_vote("declared_vendor", "someone"), _vote("model_id", "openai")]) == "openai"


def test_majority_rules_within_a_tier() -> None:
    votes = [_vote("model_id", "anthropic"), _vote("model_id", "anthropic"), _vote("model_id", "openai")]

    assert elect_model_group_section(votes) == "anthropic"


def test_a_tie_falls_to_lexicographic_order_so_the_answer_is_deterministic() -> None:
    assert elect_model_group_section([_vote("endpoint_context", "beta"), _vote("endpoint_context", "alpha")]) == "alpha"


def test_an_election_with_no_voters_answers_unknown() -> None:
    """The same word this module already uses when it has nothing to say."""

    assert elect_model_group_section([]) == "unknown"


def test_guesses_do_not_vote_when_anyone_declared() -> None:
    """Three guesses agreeing is still not evidence against one declaration —
    a proxy fleet sharing a vanity domain agrees with itself for free."""

    votes = [
        _vote("endpoint_context", "anthropic"),
        _vote("endpoint_context", "anthropic"),
        _vote("endpoint_context", "anthropic"),
        _vote("declared_vendor", "minimax"),
    ]

    assert elect_model_group_section(votes) == "minimax"
