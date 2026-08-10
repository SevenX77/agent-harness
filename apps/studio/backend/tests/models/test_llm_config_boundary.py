from __future__ import annotations

from app.models.llm_config import (
    LLMCredentialsFile,
    ModelProfile,
    ProviderEndpoint,
    ProviderRoute,
    RoleEntry,
    RoleIntent,
    RoleRouteEntry,
    RolesData,
)
from graph_agent_gateway.registry.schema import RegistrySnapshot
from graph_agent_gateway.settings_bounds import AUTHORED_TEMPERATURE_MAX


def test_a_temperature_past_the_end_of_the_dial_is_stored_as_the_end_of_it() -> None:
    """Studio's dial is its own; a value off it has no meaning to keep.

    Refusing the write would make a setting fail a save, which is the same
    mistake as letting one fail a call. The dial's ends are the answer to
    "hotter than it goes", so the write lands there instead of being rejected
    or stored as a number nothing downstream can read.
    """
    assert RoleIntent(temperature=3.0).temperature == AUTHORED_TEMPERATURE_MAX
    assert RoleIntent(temperature=-1.0).temperature == 0.0
    assert RoleIntent(temperature=1.4).temperature == 1.4


def test_studio_display_fields_are_stripped_from_gateway_runtime_snapshot() -> None:
    credentials = LLMCredentialsFile(
        provider_endpoints={
            "openai-direct": ProviderEndpoint(
                endpoint_id="openai-direct",
                display_name="OpenAI",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                api_key="secret",
            )
        },
        provider_routes={
            "openai-direct:gpt-5": ProviderRoute(
                route_id="openai-direct:gpt-5",
                endpoint_id="openai-direct",
                route_slug="gpt-5",
                provider_model_id="gpt-5",
                canonical_id="gpt-5",
                display_name="GPT-5",
            )
        },
    )
    roles = RolesData(
        model_profiles={
            "GPT5": ModelProfile(
                model_profile_id="GPT5",
                display_name="GPT-5",
                canonical_id="gpt-5",
                fallback_chain=[RoleRouteEntry(route_id="openai-direct:gpt-5")],
            )
        },
        roles={
            "graph_agent": RoleEntry(
                fallback_chain=[RoleRouteEntry(route_id="openai-direct:gpt-5")]
            )
        },
    )

    snapshot = roles.to_registry_snapshot(credentials)
    payload = snapshot.model_dump(mode="json")

    assert "display_name" not in payload["provider_endpoints"]["openai-direct"]
    assert "display_name" not in payload["provider_routes"]["openai-direct:gpt-5"]
    assert "display_name" not in payload["model_profiles"]["GPT5"]
    RegistrySnapshot.model_validate(payload)
