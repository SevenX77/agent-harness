"""MoirAI can see a skill's output end well enough to judge what it should land."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest


def _payload(result: dict[str, Any]) -> Any:
    return json.loads(result["content"][0]["text"])


def _run(monkeypatch: pytest.MonkeyPatch, contract: dict[str, Any], runtime: dict[str, Any]) -> Any:
    from app.core.adapters import transport_factory
    from app.services import copilot_tools, runtime_config, skills

    class FakeAdapter:
        def get_output_contract(self, _skill_dir: str) -> dict[str, Any]:
            return contract

    monkeypatch.setattr(transport_factory, "build_engine_adapter", lambda: FakeAdapter())
    monkeypatch.setattr(skills, "ensure_workspace_skill_dir", lambda _skill_id: Path("."))
    monkeypatch.setattr(runtime_config, "refresh_runtime_config", lambda _dir: runtime)
    return _payload(asyncio.run(copilot_tools.get_skill_output_contract_tool.handler({"skill_id": "s"})))


def test_a_declared_output_that_lands_nowhere_is_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The exp-B round-4 shape: the run reports success and the artifacts directory
    # is empty, because nothing ever decided whether this skill should land a file.
    contract = {
        "fields": [
            {"name": "chapter_lines", "type": "array", "produced_by": "setup", "declared_output": False},
            {"name": "segmentation_result", "type": "object", "produced_by": "segment", "declared_output": True},
        ],
        "declared_but_unproduced": [],
    }

    payload = _run(monkeypatch, contract, {"artifacts": []})

    assert payload["declared_outputs_not_landed"] == ["segmentation_result"]
    assert [field["name"] for field in payload["declared_outputs"]] == ["segmentation_result"]


def test_a_declared_output_already_landed_is_not_flagged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = {
        "fields": [
            {"name": "segmentation_result", "type": "object", "produced_by": "segment", "declared_output": True},
        ],
        "declared_but_unproduced": [],
    }
    runtime = {"artifacts": [{"stem": "segmentation_result", "fields": ["segmentation_result"], "mode": "single", "format": "json"}]}

    payload = _run(monkeypatch, contract, runtime)

    assert payload["declared_outputs_not_landed"] == []


def test_the_whole_blackboard_is_offered_not_just_the_declared_part(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Deciding what to land needs the choices, not only the current answer.
    contract = {
        "fields": [
            {"name": "chapter_lines", "type": "array", "produced_by": "setup", "declared_output": False},
            {"name": "segments", "type": "array", "produced_by": "segment", "declared_output": True},
        ],
        "declared_but_unproduced": ["summary"],
    }

    payload = _run(monkeypatch, contract, {"artifacts": []})

    assert [field["name"] for field in payload["blackboard_at_output"]] == ["chapter_lines", "segments"]
    assert payload["declared_but_unproduced"] == ["summary"]
