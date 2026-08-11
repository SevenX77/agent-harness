"""AllProvidersFailedError must not be silent: every raise logs the per-candidate
failure records (error_type/message/status), because upstream wrappers currently
drop the payload — a crashed run surfaced `details: {}` with zero log lines,
leaving no way to see WHY the provider call failed (field evidence: run
2026-08-01T08-44-10, role=fast, "1 provider candidates failed", empty details).
"""

from __future__ import annotations

import logging

import pytest
from graph_agent_gateway.call.chat_model import _raise_all_providers_failed
from graph_agent_gateway.errors import AllProvidersFailedError


def test_raise_helper_logs_each_failure(caplog: pytest.LogCaptureFixture) -> None:
    failures = [
        {
            "provider": "deepseek-official:deepseek-v4-flash",
            "route_id": "deepseek-official:deepseek-v4-flash",
            "error_type": "BadRequestError",
            "message": "Error code: 400 - invalid tool message ordering",
            "fallback_decision": "fail_fast",
            "provider_status_code": 400,
        }
    ]

    with caplog.at_level(logging.WARNING, logger="graph_agent_gateway.gateway_chat_model"):
        with pytest.raises(AllProvidersFailedError):
            _raise_all_providers_failed("fast", failures, phase_name="segment")

    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert "deepseek-official:deepseek-v4-flash" in joined
    assert "BadRequestError" in joined
    assert "invalid tool message ordering" in joined
    assert "segment" in joined
