"""R-F1 + R-F10 — PUT/DELETE roles strong-refreshes the gateway snapshot
and publishes a ``roles_changed`` event on the studio events topic.

These tests use the unit-level approach (call the FastAPI route coroutines
directly) so they do not depend on the full sidecar TestClient fixture,
keeping them fast and hermetic. The websocket smoke path is exercised by
``test_api.test_events_ws_broadcasts_to_multiple_clients`` so we focus
here on: (1) the event payload shape and (2) the snapshot freshness
contract.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from app.core import config
from app.core.adapters.gateway_config_store_local import LocalGatewayConfigStore
from app.models.llm_config import (
    LLMCredentialsFile,
    ProviderEndpoint,
    ProviderRoute,
    RoleEntry,
    RoleRouteEntry,
    RolesData,
)
from app.routers import llm as llm_router
from app.services.event_bus import STUDIO_EVENTS_TOPIC, event_bus
from app.services.llm_credentials import save_credentials
from app.services.llm_roles import save_roles_file


def _seed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, str]:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    monkeypatch.delenv("STUDIO_LLM_CREDENTIALS_PATH", raising=False)
    monkeypatch.delenv("STUDIO_LLM_ROLES_PATH", raising=False)
    roles_path = settings_dir / "llm" / "llm_roles.yaml"
    route_id = "anthropic-official:claude-3-5-haiku"
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "anthropic-official": ProviderEndpoint(
                    endpoint_id="anthropic-official",
                    display_name="Anthropic",
                    protocol="anthropic_compatible",
                    base_url="https://api.anthropic.example",
                    api_key="secret",
                )
            },
            provider_routes={
                route_id: ProviderRoute(
                    route_id=route_id,
                    endpoint_id="anthropic-official",
                    route_slug="claude-3-5-haiku",
                    provider_model_id="claude-3-5-haiku",
                    canonical_id="claude-3-5-haiku",
                    display_name="Claude 3.5 Haiku",
                    status="verified",
                )
            },
        )
    )
    save_roles_file(
        roles_path,
        RolesData(roles={}),
        known_route_ids={route_id},
    )
    return roles_path, route_id


class _DirectSubscriber:
    """Register a raw asyncio.Queue under STUDIO_EVENTS_TOPIC directly so we
    survive ``asyncio.wait_for`` cancellations.

    The public ``InMemoryEventBus.subscribe`` API is an async generator that
    deregisters its queue in its ``finally``; if we cancel a pull via
    ``wait_for`` the queue gets removed before the publisher runs. The
    subscription topology is plain enough (a set of queues per topic) that
    a direct register/unregister keeps the test loop deterministic.
    """

    def __init__(self) -> None:
        self.queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()

    def __enter__(self) -> "_DirectSubscriber":
        event_bus._subscribers.setdefault(STUDIO_EVENTS_TOPIC, set()).add(self.queue)
        return self

    def __exit__(self, *_exc) -> None:
        subscribers = event_bus._subscribers.get(STUDIO_EVENTS_TOPIC)
        if subscribers is not None:
            subscribers.discard(self.queue)
            if not subscribers:
                event_bus._subscribers.pop(STUDIO_EVENTS_TOPIC, None)

    async def receive(self, timeout: float = 1.0) -> dict[str, object]:
        return await asyncio.wait_for(self.queue.get(), timeout=timeout)


def test_put_llm_roles_publishes_roles_changed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roles_path, route_id = _seed(tmp_path, monkeypatch)

    request = RolesData(
        roles={
            "copilot_custom_test": RoleEntry(
                fallback_chain=[RoleRouteEntry(route_id=route_id)],
            )
        }
    )

    async def _run() -> dict[str, object]:
        with _DirectSubscriber() as sub:
            await llm_router.put_llm_roles(request)
            return await sub.receive()

    event = asyncio.run(_run())
    assert event["type"] == "roles_changed"
    assert event["source"] == "http_api"
    assert isinstance(event["timestamp"], str) and event["timestamp"]


def test_put_llm_roles_refreshes_gateway_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roles_path, route_id = _seed(tmp_path, monkeypatch)
    settings_dir = roles_path.parent.parent

    request = RolesData(
        roles={
            "copilot_custom_test": RoleEntry(
                fallback_chain=[RoleRouteEntry(route_id=route_id)],
            )
        }
    )

    asyncio.run(llm_router.put_llm_roles(request))

    config_store = LocalGatewayConfigStore(root=settings_dir)
    roles_record = config_store.get_config(config.DEFAULT_USER_ID, "roles")
    assert "copilot_custom_test" in roles_record.value["roles"]


def test_delete_llm_role_publishes_and_refreshes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roles_path, route_id = _seed(tmp_path, monkeypatch)
    settings_dir = roles_path.parent.parent

    # First seed a role via PUT, then delete it and assert both the event
    # and the snapshot reflect the removal.
    asyncio.run(
        llm_router.put_llm_roles(
            RolesData(
                roles={
                    "copilot_custom_test": RoleEntry(
                        fallback_chain=[RoleRouteEntry(route_id=route_id)],
                    )
                }
            )
        )
    )

    async def _delete() -> dict[str, object]:
        with _DirectSubscriber() as sub:
            await llm_router.delete_llm_role("copilot_custom_test")
            return await sub.receive()

    event = asyncio.run(_delete())
    assert event["type"] == "roles_changed"
    assert event["source"] == "http_api"

    config_store = LocalGatewayConfigStore(root=settings_dir)
    roles_record = config_store.get_config(config.DEFAULT_USER_ID, "roles")
    assert "copilot_custom_test" not in roles_record.value["roles"]


def test_publish_failure_does_not_break_save(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """R-F10.2 — if the event bus blows up, the endpoint still returns
    success and the failure is logged via ``logger.exception``.
    """
    roles_path, route_id = _seed(tmp_path, monkeypatch)
    settings_dir = roles_path.parent.parent

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("event bus offline")

    monkeypatch.setattr(event_bus, "publish", _boom)

    request = RolesData(
        roles={
            "copilot_custom_test": RoleEntry(
                fallback_chain=[RoleRouteEntry(route_id=route_id)],
            )
        }
    )

    with caplog.at_level("ERROR"):
        result = asyncio.run(llm_router.put_llm_roles(request))

    assert "copilot_custom_test" in result.roles
    config_store = LocalGatewayConfigStore(root=settings_dir)
    roles_record = config_store.get_config(config.DEFAULT_USER_ID, "roles")
    assert "copilot_custom_test" in roles_record.value["roles"]
    # The exception should have been logged but not raised.
    assert any(
        "publish_roles_changed" in record.getMessage() for record in caplog.records
    )
