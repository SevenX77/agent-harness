"""Renaming a route is not a statement about what the route can do.

`PUT /llm/routes/{id}` is the editable-metadata endpoint: display name, canonical
id, status. Capabilities are not editable metadata — they are what probing
measured, and the only honest way to change one is to measure again. An endpoint
that replaces them wholesale lets a caller destroy measurements by omission,
which is exactly what its one caller did: `update_llm_route` sends three fields
and the request model defaults the rest to empty.

Decision: docs/design/2026-08-11-capability-evidence-tiers-decision.md D7.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from app.core import config
from app.models.llm_config import (
    CapabilityValue,
    LLMCredentialsFile,
    ProviderEndpoint,
    ProviderRoute,
)
from app.services.llm_credentials import credentials_path, load_credentials, save_credentials
from fastapi.testclient import TestClient

MEASURED = CapabilityValue(
    value={"supported": True, "values": ["low", "high"]},
    source="probed_verified",
)


def _seed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", tmp_path / "settings")
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "vendor": ProviderEndpoint(
                    endpoint_id="vendor",
                    display_name="Vendor",
                    protocol="openai_compatible",
                    base_url="https://vendor.example/v1",
                    api_key="secret",
                )
            },
            provider_routes={
                "vendor:thinker": ProviderRoute(
                    route_id="vendor:thinker",
                    endpoint_id="vendor",
                    route_slug="thinker",
                    provider_model_id="thinker",
                    canonical_id="thinker",
                    display_name="Thinker",
                    status="verified",
                    capabilities={"reasoning_effort": MEASURED},
                    metadata={"note": "kept"},
                )
            },
        ),
        credentials_path(),
    )


def _rename(client: TestClient) -> Any:
    return client.put(
        "/api/llm/routes/vendor:thinker",
        json={
            "display_name": "Thinker (renamed)",
            "canonical_id": "thinker",
            "status": "verified",
        },
    )


def test_renaming_a_route_keeps_the_capabilities_it_measured(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(tmp_path, monkeypatch)

    response = _rename(client)

    assert response.status_code == 200, response.text
    route = load_credentials().provider_routes["vendor:thinker"]
    assert route.display_name == "Thinker (renamed)"
    assert route.capabilities == {"reasoning_effort": MEASURED}
    assert route.metadata == {"note": "kept"}


def test_the_edit_endpoint_refuses_to_be_told_what_a_route_can_do(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Naming a capability here would be a measurement nobody took.

    Rejecting the field outright, rather than ignoring it, keeps a caller from
    believing it worked.
    """
    _seed(tmp_path, monkeypatch)

    response = client.put(
        "/api/llm/routes/vendor:thinker",
        json={
            "display_name": "Thinker",
            "canonical_id": "thinker",
            "status": "verified",
            "capabilities": {
                "reasoning_effort": {"value": {"supported": True, "values": ["max"]}, "source": "probed_verified"}
            },
        },
    )

    assert response.status_code == 422, response.text
    assert load_credentials().provider_routes["vendor:thinker"].capabilities == {
        "reasoning_effort": MEASURED
    }


def test_the_copilot_rename_tool_keeps_the_measurements_too(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The tool is the only caller this endpoint has, and it sends three fields.

    Driving the real handler rather than a stub is the point: the previous test
    for this tool asserted only that the router was reached, so the wipe it
    caused on every approved rename went unseen.
    """
    from app.services import copilot_tools

    _seed(tmp_path, monkeypatch)

    result = asyncio.run(
        copilot_tools.update_llm_route_tool.handler(
            {
                "route_id": "vendor:thinker",
                "display_name": "Thinker (renamed by copilot)",
                "canonical_id": "thinker",
                "status": "verified",
            }
        )
    )

    assert "is_error" not in result, result
    route = load_credentials().provider_routes["vendor:thinker"]
    assert route.display_name == "Thinker (renamed by copilot)"
    assert route.capabilities == {"reasoning_effort": MEASURED}
