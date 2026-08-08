"""A run that succeeds without landing anything must say so at the moment of success.

Two real rounds hit the same wall: the run reported success, artifacts/ was an
empty directory, and nothing anywhere raised the question of what the skill
should have left behind. The passive tooling (get_skill_output_contract) only
helps an agent that already decided to ask; the trigger has to sit in the tool
result the agent is actually reading when the run finishes. Round 6 then showed
"the tool the agent is actually reading" is not one fixed tool: that session
never called wait_for_run and polled get_run_detail instead, so the reminder
never reached it. The terminal state is one fact — whichever tool reports it
carries the same reminder.
"""

from __future__ import annotations

import asyncio
import datetime
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

    async def fake_stream_run(_skill_id: str, _run_id: str) -> _Queue:
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


def _detail(monkeypatch: pytest.MonkeyPatch, *, status: str, artifacts: list[str]) -> Any:
    from types import SimpleNamespace

    from app.services import run_manager as run_manager_module

    detail = SimpleNamespace(
        metadata=SimpleNamespace(
            run_id="run-1",
            status=status,
            started_at=datetime.datetime(2026, 8, 7, tzinfo=datetime.UTC),
            metrics=None,
            input_summary=None,
        ),
        events=[],
        final_context=None,
        artifacts=artifacts,
    )
    monkeypatch.setattr(
        run_manager_module.run_manager, "get_run_detail", lambda **_kw: detail
    )
    return _payload(
        asyncio.run(
            copilot_tools.get_run_detail_tool.handler({"skill_id": "s", "run_id": "run-1"})
        )
    )


def test_get_run_detail_success_with_nothing_landed_raises_the_same_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Round 6: the session read the terminal state by polling get_run_detail and
    # never called wait_for_run — the reminder must live at this exit too.
    payload = _detail(monkeypatch, status="success", artifacts=[])

    assert payload["status"] == "success"
    assert payload["artifacts"] == []
    assert "get_skill_output_contract" in payload["output_contract_reminder"]
    assert "set_output_artifacts" in payload["output_contract_reminder"]


def test_get_run_detail_success_with_artifacts_stays_quiet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _detail(
        monkeypatch,
        status="success",
        artifacts=["artifacts/segmentation_result_latest_20260805.json"],
    )

    assert "output_contract_reminder" not in payload


def test_get_run_detail_failed_run_is_not_nagged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _detail(monkeypatch, status="failed", artifacts=[])

    assert "output_contract_reminder" not in payload


def test_both_exits_share_one_reminder_definition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # One business rule, one authoritative text: if the two exits ever grow
    # separate copies, they will drift apart exactly like the surfaces the
    # diagnostics-SSOT rule exists for.
    wait_payload = _wait(monkeypatch, status="success", artifacts=[])
    detail_payload = _detail(monkeypatch, status="success", artifacts=[])

    assert (
        wait_payload["output_contract_reminder"]
        == detail_payload["output_contract_reminder"]
    )
