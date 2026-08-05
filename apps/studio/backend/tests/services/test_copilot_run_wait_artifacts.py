"""A run that succeeds without landing anything must say so at the moment of success.

Two real rounds hit the same wall: the run reported success, artifacts/ was an
empty directory, and nothing anywhere raised the question of what the skill
should have left behind. The passive tooling (get_skill_output_contract) only
helps an agent that already decided to ask; the trigger has to sit in the tool
result the agent is actually reading when the run finishes — wait_for_run.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from app.services import copilot_tools


def _payload(result: dict[str, Any]) -> Any:
    return json.loads(result["content"][0]["text"])


class _Queue:
    """A stream whose run is already over: first get() returns the terminal None."""

    async def get(self) -> None:
        return None


def _wire(monkeypatch: pytest.MonkeyPatch, *, status: str, artifacts: list[str]) -> None:
    from types import SimpleNamespace

    from app.services import run_manager as run_manager_module

    async def fake_stream_run(_run_id: str) -> _Queue:
        return _Queue()

    detail = SimpleNamespace(
        metadata=SimpleNamespace(
            run_id="run-1",
            status=status,
            metrics=None,
        ),
        artifacts=artifacts,
    )
    monkeypatch.setattr(run_manager_module.run_manager, "stream_run", fake_stream_run)
    monkeypatch.setattr(
        run_manager_module.run_manager, "get_run_detail", lambda **_kw: detail
    )


def _wait(monkeypatch: pytest.MonkeyPatch, *, status: str, artifacts: list[str]) -> Any:
    _wire(monkeypatch, status=status, artifacts=artifacts)
    return _payload(
        asyncio.run(
            copilot_tools.wait_for_run_tool.handler({"skill_id": "s", "run_id": "run-1"})
        )
    )


def test_success_with_nothing_landed_raises_the_output_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _wait(monkeypatch, status="success", artifacts=[])

    assert payload["status"] == "success"
    assert payload["artifacts_landed"] == []
    # The nudge names the tools that answer the question, so the agent's next
    # step is a call, not a guess.
    assert "get_skill_output_contract" in payload["output_contract_reminder"]
    assert "set_output_artifacts" in payload["output_contract_reminder"]


def test_success_with_artifacts_lists_them_and_stays_quiet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _wait(
        monkeypatch,
        status="success",
        artifacts=["artifacts/segmentation_result_latest_20260805.json"],
    )

    assert payload["artifacts_landed"] == [
        "artifacts/segmentation_result_latest_20260805.json"
    ]
    assert "output_contract_reminder" not in payload


def test_a_failed_run_is_not_nagged_about_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A failed run landing nothing is expected; the defect to talk about is the
    # failure itself, and mixing the two would bury it.
    payload = _wait(monkeypatch, status="failed", artifacts=[])

    assert payload["status"] == "failed"
    assert "output_contract_reminder" not in payload
