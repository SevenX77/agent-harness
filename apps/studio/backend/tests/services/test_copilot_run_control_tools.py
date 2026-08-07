"""The copilot can end or pause a run it started, like the human's two buttons.

Round 6, verbatim: "No cancel tool is exposed on this CLI surface — I'll let
the doomed run expire." The human got Pause/Stop in P4-E6; the agent watching
the same doomed run had nothing. Both tools call the same run_manager methods
as the HTTP routes, so the gate broadcast — and with it the UI — follows for
free.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest
from app.services import copilot_tools


def _payload(result: dict[str, Any]) -> Any:
    return json.loads(result["content"][0]["text"])


def _metadata(status: str) -> SimpleNamespace:
    return SimpleNamespace(run_id="run-1", status=status)


def test_pause_run_reports_the_paused_state(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import run_manager as run_manager_module

    async def fake_pause(*, skill_id: str, run_id: str) -> SimpleNamespace:
        assert (skill_id, run_id) == ("s", "run-1")
        return _metadata("paused")

    monkeypatch.setattr(run_manager_module.run_manager, "pause_run", fake_pause)
    payload = _payload(
        asyncio.run(copilot_tools.pause_run_tool.handler({"skill_id": "s", "run_id": "run-1"}))
    )

    assert payload == {"run_id": "run-1", "status": "paused"}


def test_stop_run_reports_the_terminal_state(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import run_manager as run_manager_module

    async def fake_stop(*, skill_id: str, run_id: str) -> SimpleNamespace:
        return _metadata("cancelled")

    monkeypatch.setattr(run_manager_module.run_manager, "stop_run", fake_stop)
    payload = _payload(
        asyncio.run(copilot_tools.stop_run_tool.handler({"skill_id": "s", "run_id": "run-1"}))
    )

    assert payload == {"run_id": "run-1", "status": "cancelled"}


@pytest.mark.parametrize("tool_name", ["pause_run_tool", "stop_run_tool"])
def test_missing_ids_are_rejected_at_the_boundary(tool_name: str) -> None:
    tool = getattr(copilot_tools, tool_name)
    result = asyncio.run(tool.handler({"skill_id": "", "run_id": ""}))

    assert result["is_error"] is True


@pytest.mark.parametrize("tool_name", ["pause_run_tool", "stop_run_tool"])
def test_a_run_in_the_wrong_state_surfaces_the_manager_diagnosis(
    monkeypatch: pytest.MonkeyPatch, tool_name: str
) -> None:
    # run_manager owns the state rules (409 RUN_NOT_RUNNING); the tool boundary
    # relays that diagnosis instead of re-deriving its own.
    from app.services import run_manager as run_manager_module

    class _Conflict(Exception):
        detail = {"error_code": "RUN_NOT_RUNNING", "message": "Run is not running: run-1"}

    async def fake_control(*, skill_id: str, run_id: str) -> SimpleNamespace:
        raise _Conflict()

    manager_method = "pause_run" if tool_name == "pause_run_tool" else "stop_run"
    monkeypatch.setattr(run_manager_module.run_manager, manager_method, fake_control)
    result = asyncio.run(
        getattr(copilot_tools, tool_name).handler({"skill_id": "s", "run_id": "run-1"})
    )

    assert result["is_error"] is True
    assert "RUN_NOT_RUNNING" in result["content"][0]["text"]
