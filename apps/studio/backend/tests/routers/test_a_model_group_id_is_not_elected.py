"""A model group's id is a pure function of what the group IS, never an election.

Settings merges routes that are "the same model to a person" into one card. The
merge key is a projection of the route's own identity
(`project_model_group_identity(...).key`), which is stable. But the id the card
was PUBLISHED under was a different value: the canonical id of one route ELECTED
from the group (official first, then shortest). Roles persist that published id
in `model_groups[].canonical_id`, so adding or removing any endpoint could
re-run the election, change the id, and orphan every role that referenced it.

Measured 2026-08-20 against the developer's real credentials: 400 of the groups
publish an id different from their own merge key, and the `analyst` role holds
three groups that no longer resolve — `deepseek-v4-flash-260425` (the id elected
BEFORE deepseek-official was added on 08-12), plus two raw model ids. All of
their routes still exist in the registry and all project to the same key,
`deepseek-v4-flash`, which is the id that `fast` and `copilot_deepseek_v4_flash`
reference successfully. So nothing was lost — only the label went stale.

Two halves, and neither works alone:

1. The published id becomes the merge key, so the id cannot move under a role's
   feet. On its own this would break the roles that reference a currently-elected
   id (`claude-haiku-4-5-20251001`, `claude-opus-4.8` in that same file).
2. A role's group is re-identified from the ROUTES IT HOLDS, so a stored id that
   no longer matches stops mattering. That is what makes (1) safe, and it is
   also what repairs the three analyst groups: a group is the routes it names,
   and the label beside them is derived, not authoritative.

Execution never depended on any of this — the fallback chain resolves by
`route_id` — which is why a role could show three dead cards and still run.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core import config
from app.models.llm_config import (
    CapabilityValue,
    LLMCredentialsFile,
    ProviderEndpoint,
    ProviderRoute,
    RoleEntry,
    RolesData,
)
from app.services.llm_credentials import credentials_path, load_credentials, save_credentials
from app.services.llm_roles import roles_path as active_roles_path
from app.services.llm_roles import save_roles_file
from fastapi.testclient import TestClient
from graph_agent_gateway.registry import RoleModelGroup, RoleProviderModel

_THIRD_PARTY_ROUTE = "aggregator:deepseek-v4-flash-260425"
_OFFICIAL_ROUTE = "deepseek-official:deepseek-v4-flash"


def _endpoints(*, with_official: bool) -> dict[str, ProviderEndpoint]:
    endpoints = {
        "aggregator": ProviderEndpoint(
            endpoint_id="aggregator",
            display_name="Aggregator",
            protocol="openai_compatible",
            base_url="https://api.aggregator.example/v1",
            api_key="secret",
            provider_kind="third_party",
        )
    }
    if with_official:
        endpoints["deepseek-official"] = ProviderEndpoint(
            endpoint_id="deepseek-official",
            display_name="DeepSeek",
            protocol="openai_compatible",
            base_url="https://api.deepseek.example/v1",
            api_key="secret",
            provider_kind="official",
        )
    return endpoints


def _routes(*, with_official: bool) -> dict[str, ProviderRoute]:
    routes = {
        _THIRD_PARTY_ROUTE: ProviderRoute(
            route_id=_THIRD_PARTY_ROUTE,
            endpoint_id="aggregator",
            route_slug="deepseek-v4-flash-260425",
            provider_model_id="deepseek-v4-flash-260425",
            canonical_id="deepseek-v4-flash-260425",
            display_name="DeepSeek V4 Flash 260425",
            status="verified",
        )
    }
    if with_official:
        routes[_OFFICIAL_ROUTE] = ProviderRoute(
            route_id=_OFFICIAL_ROUTE,
            endpoint_id="deepseek-official",
            route_slug="deepseek-v4-flash",
            provider_model_id="deepseek-v4-flash",
            canonical_id="deepseek-v4-flash",
            display_name="DeepSeek V4 Flash",
            status="verified",
            # An official endpoint's route is only listed once something has
            # measured it (`_include_route_in_model_groups` refuses to guess for
            # official providers), so the fixture states the modalities that the
            # real deepseek-official route carries.
            capabilities={
                "input_modalities": CapabilityValue(value=["text"], source="provider_doc"),
                "output_modalities": CapabilityValue(value=["text"], source="provider_doc"),
            },
        )
    return routes


def _write_credentials(*, with_official: bool) -> None:
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints=_endpoints(with_official=with_official),
            provider_routes=_routes(with_official=with_official),
        ),
        credentials_path(),
    )


@pytest.fixture()
def settings_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", directory)
    return directory


def _group_ids(client: TestClient) -> list[str]:
    body = client.get("/api/llm/registry").json()
    return sorted(group["canonical_id"] for group in body["model_groups"])


def _the_one_group(client: TestClient) -> dict:
    body = client.get("/api/llm/registry").json()
    groups = body["model_groups"]
    assert len(groups) == 1, f"the fixture's routes are one model; got {_group_ids(client)}"
    return groups[0]


def test_a_group_id_survives_a_sibling_endpoint_appearing(
    settings_dir: Path,
    client: TestClient,
) -> None:
    _write_credentials(with_official=False)
    before = _the_one_group(client)["canonical_id"]

    _write_credentials(with_official=True)
    after = _the_one_group(client)["canonical_id"]

    assert after == before, (
        "adding an endpoint re-ran the election and moved the group's id — every role "
        f"referencing {before!r} just lost its link (now {after!r})"
    )


def test_the_id_is_the_key_the_routes_are_merged_by(
    settings_dir: Path,
    client: TestClient,
) -> None:
    """Not just stable — stable BECAUSE it is what the grouping already computed.

    Any other stable value would be a second identity to keep in step with the
    first. The merge key is already the answer to "are these the same model".
    """
    from app.routers.llm import _model_group_identity_key

    _write_credentials(with_official=True)
    credentials = load_credentials()
    keys = {
        _model_group_identity_key(route, credentials)
        for route in credentials.provider_routes.values()
    }

    assert _the_one_group(client)["canonical_id"] in keys


def _role_with_groups(*groups: RoleModelGroup) -> None:
    save_roles_file(
        active_roles_path(),
        RolesData(roles={"analyst": RoleEntry(model_groups=list(groups))}),
        known_route_ids=set(_routes(with_official=True)),
    )


def _analyst_groups(client: TestClient) -> list[dict]:
    body = client.get("/api/llm/roles").json()
    return body["roles_data"]["roles"]["analyst"]["model_groups"]


def test_a_role_group_is_re_identified_from_the_routes_it_holds(
    settings_dir: Path,
    client: TestClient,
) -> None:
    _write_credentials(with_official=True)
    _role_with_groups(
        RoleModelGroup(
            canonical_id="deepseek-v4-flash-260425",  # the id elected before the official endpoint existed
            display_name="deepseek-v4-flash-260425",
            provider_models=[RoleProviderModel(route_id=_THIRD_PARTY_ROUTE)],
        )
    )

    groups = _analyst_groups(client)
    live = _the_one_group(client)["canonical_id"]

    assert [group["canonical_id"] for group in groups] == [live], (
        "the stored label went stale but the routes it names are alive — the group "
        "should link up by what it references, not by what it was once called"
    )


def test_two_stale_groups_naming_one_model_become_one(
    settings_dir: Path,
    client: TestClient,
) -> None:
    """The analyst case: several dead labels, all pointing at the same live model."""
    _write_credentials(with_official=True)
    _role_with_groups(
        RoleModelGroup(
            canonical_id="deepseek-v4-flash-260425",
            display_name="deepseek-v4-flash-260425",
            provider_models=[RoleProviderModel(route_id=_THIRD_PARTY_ROUTE)],
        ),
        RoleModelGroup(
            canonical_id="deepseek.deepseek-v4-flash",
            display_name="deepseek.deepseek-v4-flash",
            provider_models=[RoleProviderModel(route_id=_OFFICIAL_ROUTE)],
        ),
    )

    groups = _analyst_groups(client)

    assert len(groups) == 1, f"one model, one card; got {[g['canonical_id'] for g in groups]}"
    assert sorted(model["route_id"] for model in groups[0]["provider_models"]) == sorted(
        [_OFFICIAL_ROUTE, _THIRD_PARTY_ROUTE]
    ), "merging the cards must keep every route both of them named"


def test_a_group_that_names_no_routes_is_dropped(
    settings_dir: Path,
    client: TestClient,
) -> None:
    """An empty group references nothing, so there is nothing to re-identify.

    The real file has one (`deepseek.deepseek-v4-flash-202605`, zero routes). It
    cannot be materialized into a fallback chain and cannot ever resolve, so
    keeping it only produces a card that is permanently broken.
    """
    _write_credentials(with_official=True)
    _role_with_groups(
        RoleModelGroup(
            canonical_id="deepseek.deepseek-v4-flash-202605",
            display_name="deepseek.deepseek-v4-flash-202605",
            provider_models=[],
        )
    )

    assert _analyst_groups(client) == []
