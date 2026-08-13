"""A model id says who made the model; the endpoint it sits on does not.

``project_model_identity`` inferred the owner from one flat haystack that mixed
the endpoint's id, the host's label for it, and the model id together, then took
the first brand any of them mentioned. On an aggregator reached through a proxy
host — ``anthropic-<something>.example`` serving ``xiaomi/mimo-v2.5`` — the
proxy's hostname won, so a Xiaomi model was filed under ``anthropic`` and
``confidence`` reported ``high``. Measured against the live registry on
2026-08-13: 402 of 1352 routes took their owner from the endpoint, and 320 of
those carried a ``vendor/`` prefix that the code discarded before looking.

Two rules follow, and they are the whole fix:

- An origin the model DECLARES outranks one guessed from its surroundings, and
  a declared origin this package does not recognise still outranks the guess —
  "made by someone I don't know" is a true answer; "made by whoever runs the
  proxy" is not.
- ``confidence`` reports WHERE the answer came from, so a host can tell a name
  the model gave from one its neighbourhood suggested. Reading it off
  ``owner is not None`` made it the constant ``high``: every one of those 1352
  routes claimed high confidence.

``unknown_tokens`` had the same shape of defect. The tokens a name is built from
are classified in several places — the brand table, the owner and family
inference, the variant/capability sets, the release-snapshot rules the group
splitter owns — and the unknown list consulted none of them. It re-derived
"recognised" as ``{owner.lower(), family.lower()}``, so ``opus`` (the word that
proves the family is Claude) and ``doubao`` (the word that proves the owner is
ByteDance) were both reported as words the projector did not know. 1118 of 1352
routes reported at least one such token.
"""

from __future__ import annotations

import re

import pytest
from graph_agent_gateway.registry import ProviderEndpoint, ProviderRoute, project_model_identity

# A proxy whose HOSTNAME names a vendor that has nothing to do with the models
# it serves. Endpoint ids are derived from the base url, so this is the shape a
# real aggregator behind a vanity domain takes.
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


def _project(endpoint_id: str, provider_model_id: str, provider_label: str | None = None):
    return project_model_identity(
        route=_route(endpoint_id, provider_model_id),
        endpoint=_endpoint(endpoint_id),
        provider_label=provider_label,
    )


@pytest.mark.parametrize(
    ("provider_model_id", "section_label"),
    [
        ("xiaomi/mimo-v2.5", "xiaomi"),
        ("meituan/longcat-flash-lite", "meituan"),
        ("nvidia/nemotron-3-super-120b-a12b", "nvidia"),
    ],
)
def test_a_vendor_this_package_does_not_know_still_beats_the_proxy_it_is_served_from(
    provider_model_id: str, section_label: str
) -> None:
    projection = _project(PROXY_ENDPOINT_ID, provider_model_id)

    assert projection.section_label == section_label
    assert projection.confidence == "low"


@pytest.mark.parametrize(
    ("provider_model_id", "section_label"),
    [
        ("openai/o3-mini", "openai"),
        ("google/gemma-4-26b-a4b-it", "gemini"),
        ("mistralai/ministral-8b-2512", "mistral"),
    ],
)
def test_a_vendor_prefix_this_package_knows_names_the_model(
    provider_model_id: str, section_label: str
) -> None:
    projection = _project(PROXY_ENDPOINT_ID, provider_model_id)

    assert projection.section_label == section_label
    assert projection.confidence == "high"


def test_a_model_that_names_itself_needs_no_help_from_its_endpoint() -> None:
    projection = _project(PROXY_ENDPOINT_ID, "claude-opus-4-1-20250805")

    assert projection.section_label == "anthropic"
    assert projection.confidence == "high"


def test_an_id_that_declares_nothing_may_still_be_read_from_its_endpoint() -> None:
    """The host's own label for an endpoint stays a legitimate clue.

    ``large-2411`` names no brand and carries no vendor prefix. Reading
    "Mistral Cloud" off the endpoint is the best answer available — it is just
    not the same KIND of answer as one the model id gave itself, which is what
    ``confidence`` now says.
    """

    projection = _project("provider", "large-2411", provider_label="Mistral Cloud")

    assert projection.section_label == "mistral"
    assert projection.confidence == "medium"


@pytest.mark.parametrize(
    "provider_model_id",
    [
        "claude-opus-4-1-20250805",  # opus proves the family
        "doubao-1.5-vision-pro",  # doubao proves the owner
        "deepseek-r1-0528",  # r1 is a version, 0528 a release
        "qwen3-30b-a3b",  # qwen3 proves the owner
    ],
)
def test_the_words_that_produced_the_answer_are_not_reported_as_unrecognised(
    provider_model_id: str,
) -> None:
    projection = _project("provider", provider_model_id)

    used = {token for token in projection.tokens if token.lower() in {"opus", "doubao", "r1", "qwen3"}}
    assert used, "the fixture must contain a token the inference consumes"
    assert not {token.lower() for token in used} & set(projection.unknown_tokens)


def test_words_no_table_claims_are_still_reported() -> None:
    """The list must stay useful: it is where a maintainer learns what to add."""

    projection = _project("provider", "qwen3-235b-a22b-instruct-2507")

    assert set(projection.unknown_tokens) == {"235b", "a22b", "instruct", "2507"}


def test_a_bare_version_number_is_a_version_number() -> None:
    """``claude-fable-5`` splits to a lone ``5``; the group splitter already
    reads that as a version, so the unknown list may not call it a mystery."""

    projection = _project("anthropic-official", "claude-fable-5")

    assert projection.unknown_tokens == ("fable",)
