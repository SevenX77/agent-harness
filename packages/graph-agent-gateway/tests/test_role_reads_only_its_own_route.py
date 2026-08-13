"""Role materialization may only read fields the gateway's own route declares.

``role/materialization.py`` reaches for its inputs through a helper that accepts
"a dict or an object, whichever this is" and falls back to ``None``. Under that
helper a field that exists on nobody, and a field that exists only on the HOST's
subclass, both read exactly like a field that is simply unset — and
``mypy --strict`` reports success either way, because everything on the path is
``Any``.

Two things were hiding there:

- ``endpoint.secret_handle`` — no endpoint type in this repo has that field. It
  belongs to ``registry/credential_resolver.py``'s response. The branch reading
  it could never fire.
- ``route.evidence`` — declared on Studio's ``ProviderRoute`` subclass and
  stripped before an endpoint reaches this package, so the gateway was depending
  on a shape only one host happens to have. AGENTS.md forbids exactly that
  direction: studio-specific concerns must not leak INTO the SDKs.

Evidence is not a Studio idea — ``EvidenceRecord`` is defined in
``registry/schema.py`` and the probe catalog is this package's. So the fix is to
let the gateway's own route carry it, not to keep reading it off whatever the
host passed.
"""

from __future__ import annotations

import inspect

from graph_agent_gateway.registry import EvidenceRecord, ProviderEndpoint, ProviderRoute
from graph_agent_gateway.role import materialization


def _route_with_evidence(*trust_states: str) -> ProviderRoute:
    return ProviderRoute(
        route_id="openai:gpt-5",
        endpoint_id="openai",
        route_slug="gpt-5",
        provider_model_id="gpt-5",
        evidence=[
            EvidenceRecord(
                evidence_id=f"ev-{index}",
                evidence_type="probe",
                trust_state=state,
                content_hash=f"hash-{index}",
            )
            for index, state in enumerate(trust_states)
        ],
    )


def test_the_gateway_route_carries_its_own_evidence() -> None:
    assert "evidence" in ProviderRoute.model_fields

    route = _route_with_evidence("probe-verified")

    assert [record.evidence_id for record in route.evidence] == ["ev-0"]


def test_probe_verified_evidence_on_a_plain_gateway_route_is_read() -> None:
    """No Studio subclass involved: the evidence refs come off the gateway type."""

    refs = materialization._route_credential_evidence_refs(
        _route_with_evidence("probe-verified", "provider-list-observed", "probe-failed")
    )

    assert refs == ["hash-0"]


def test_a_route_with_no_evidence_yields_no_refs() -> None:
    route = ProviderRoute(
        route_id="openai:gpt-5",
        endpoint_id="openai",
        route_slug="gpt-5",
        provider_model_id="gpt-5",
    )

    assert materialization._route_credential_evidence_refs(route) == []


def test_credential_availability_asks_only_about_fields_an_endpoint_has() -> None:
    """``secret_handle`` is not an endpoint field anywhere in this repo."""

    assert "secret_handle" not in ProviderEndpoint.model_fields
    assert "secret_handle" not in inspect.getsource(materialization)

    without = ProviderEndpoint(
        endpoint_id="openai",
        protocol="openai_compatible",
        base_url="https://api.openai.com/v1",
    )
    with_ref = without.model_copy(update={"credential_ref": "cred://openai"})

    assert materialization._credential_available(without) is False
    assert materialization._credential_available(with_ref) is True
