"""The dialect domain: how each official call method says the same thing.

A dialect is asked for one request and answers with the url, the auth and the
body that wire expects — it never sends anything, so every rule here is checked
by reading the rendered request, not by mocking a transport.
"""

from __future__ import annotations

import json
from importlib import resources

import pytest
from graph_agent_gateway.dialect import (
    Image,
    Prompt,
    Reasoning,
    WireRequest,
    dialect_for_method,
    official_wire_method_ids,
)

_BASE_URL = "https://host.example/v1"
_PROMPT = Prompt(text="Reply with one short word.")
_IMAGE_PROMPT = Prompt(
    text="Reply with one short word.",
    image=Image(media_type="image/png", base64_data="iVBORw0KGgo="),
)


def _officially_probeable_method_ids() -> set[str]:
    raw = json.loads(
        resources.files("graph_agent_gateway.registry")
        .joinpath("call_methods.json")
        .read_text(encoding="utf-8")
    )
    return {
        method["method_id"] for method in raw["methods"] if method.get("official_probe") is True
    }


def _generation(method_id: str, prompt: Prompt = _PROMPT, **kwargs: object) -> WireRequest:
    reasoning = kwargs.pop("reasoning", Reasoning())
    assert isinstance(reasoning, Reasoning)
    assert not kwargs
    return dialect_for_method(method_id).generation(
        base_url=_BASE_URL,
        secret="SECRET",
        model_id="m-1",
        prompt=prompt,
        max_output_tokens=16,
        reasoning=reasoning,
    )


def test_every_officially_probeable_method_speaks_exactly_one_known_dialect() -> None:
    # A method the catalog offers for probing but no dialect can render is a
    # method nobody can send: the two lists are one fact, so they must match.
    assert official_wire_method_ids() == _officially_probeable_method_ids()


def test_a_method_no_dialect_speaks_is_refused_by_name() -> None:
    with pytest.raises(ValueError, match="openrouter_anthropic_messages"):
        dialect_for_method("openrouter_anthropic_messages")


def test_the_anthropic_wire_names_its_version_and_carries_the_secret_where_each_vendor_wants_it() -> None:
    anthropic = _generation("anthropic_messages")
    ark = _generation("ark_anthropic_messages")

    assert anthropic.headers["x-api-key"] == "SECRET"
    assert ark.headers["Authorization"] == "Bearer SECRET"
    for request in (anthropic, ark):
        assert request.headers["anthropic-version"] == "2023-06-01"
        assert request.url.endswith("/v1/messages")


def test_the_google_wire_carries_the_secret_in_the_query_not_a_header() -> None:
    request = _generation("gemini_generate_content")

    assert request.params == {"key": "SECRET"}
    assert request.headers == {}
    assert request.url.endswith("/v1beta/models/m-1:generateContent")


def test_a_text_only_wire_refuses_an_image_instead_of_quietly_dropping_it() -> None:
    # Sending the text half of a multimodal probe would report "accepted" for a
    # model that never saw an image.
    with pytest.raises(ValueError, match="openai_completions"):
        _generation("openai_completions", _IMAGE_PROMPT)


def test_every_wire_but_the_legacy_completions_one_can_say_how_hard_to_think() -> None:
    effort = Reasoning(enabled=True, effort="high")
    speechless = set()
    for method_id in sorted(official_wire_method_ids()):
        plain = _generation(method_id).body
        asked = _generation(method_id, reasoning=effort).body
        if plain == asked:
            speechless.add(method_id)

    assert speechless == {"openai_completions"}


def test_an_image_changes_the_body_of_every_wire_that_has_an_image_channel() -> None:
    for method_id in sorted(official_wire_method_ids() - {"openai_completions"}):
        assert _generation(method_id).body != _generation(method_id, _IMAGE_PROMPT).body
