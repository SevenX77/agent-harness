"""Creds-gated LIVE integration test for the copilot SDK test (COPILOT_ASSIST-4).

The mocked unit tests in test_copilot_sdk_test.py verify the wiring/verdict/error
mapping — but they replace `_session_factory` with a FakeClient, so they do NOT
spawn the real `claude` CLI or inject `ANTHROPIC_BASE_URL`. The whole point of
COPILOT_ASSIST-4 (test-passes ⟺ run-works) is only truly discharged by a real
ClaudeSDKClient round-trip. This test does that, but is SKIPPED by default
because it requires real credentials and a real model call.

To run (with isolated credentials, never the user's real库 in CI):

    STUDIO_LIVE_COPILOT_TEST=copilot_chat \
    STUDIO_LLM_CREDENTIALS_PATH=/path/to/isolated/llm_credentials.json \
    uv run pytest tests/services/test_copilot_sdk_test_live.py -x -s

The env value is the copilot role name to resolve + test.
"""

from __future__ import annotations

import asyncio
import os

import pytest
from app.services import copilot
from app.services.gateway_resolver import build_gateway_model_resolver

_LIVE_ROLE = os.environ.get("STUDIO_LIVE_COPILOT_TEST")


@pytest.mark.skipif(
    not _LIVE_ROLE,
    reason="set STUDIO_LIVE_COPILOT_TEST=<copilot_role_name> to run the real SDK tool-call test",
)
def test_live_copilot_sdk_test_round_trips_a_real_tool_call() -> None:
    assert _LIVE_ROLE is not None
    resolver = build_gateway_model_resolver()
    resolved = resolver.resolve_routes(_LIVE_ROLE)
    assert resolved.routes, f"no routes resolved for role {_LIVE_ROLE}"

    # Test the first (primary) route end-to-end through the real ClaudeSDKClient.
    route = resolved.routes[0]
    result = asyncio.run(copilot.run_route_sdk_test(route, resolver.credential_provider))

    assert result.status == "ok", (
        f"live copilot SDK test failed for {route.route_id}: {result.message}"
    )
