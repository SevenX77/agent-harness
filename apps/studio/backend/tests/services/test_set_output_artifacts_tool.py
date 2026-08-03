"""Declaring a run product must be reachable through the tool surface.

exp-b-round3 (2026-08-03): a CLI session was asked to make the run write its
segmentation result to its own file. It found no tool, no knowledge-base entry,
and a compiler that silently accepted an invalid declaration — so it stopped and
asked a human to click the I/O panel. That is the "capability parity" gap the
decision names: an action the product surface offers must exist on the tool
surface too.

The other half of that decision is that both writers share one schema and one
service; these tests pin that as well, because a second hand-rolled validator is
how the two paths would quietly drift apart.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import register_skill_index_entry


def _call(args: dict[str, Any]) -> dict[str, Any]:
    from app.services.copilot_tools import set_output_artifacts_tool

    return asyncio.run(set_output_artifacts_tool.handler(args))


def _payload(result: dict[str, Any]) -> Any:
    import json

    text = result["content"][0]["text"]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _demo_skill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from app.core import config

    skill_dir = tmp_path / "skills" / "demo"
    (skill_dir / ".workspace").mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")
    monkeypatch.setattr(config, "SKILL_INDEX_PATH", tmp_path / "global-config" / "skill_index.json")
    register_skill_index_entry("demo.skill", skill_dir)
    return skill_dir


def test_declaring_an_artifact_writes_the_runtime_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    skill_dir = _demo_skill(tmp_path, monkeypatch)

    result = _call(
        {
            "skill_id": "demo.skill",
            "artifacts": [{"stem": "segmentation_result", "fields": ["segmentation_result"]}],
        }
    )

    assert not result.get("is_error")
    written = json.loads((skill_dir / ".workspace" / "runtime_config.json").read_text(encoding="utf-8"))
    assert written["artifacts"] == [
        {
            "stem": "segmentation_result",
            "mode": "single",
            "format": "json",
            "fields": ["segmentation_result"],
        }
    ]
    assert _payload(result)["artifacts"] == written["artifacts"]


def test_an_empty_list_clears_every_declaration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full replacement, not merge — otherwise a declaration could never be removed."""
    import json

    skill_dir = _demo_skill(tmp_path, monkeypatch)
    _call({"skill_id": "demo.skill", "artifacts": [{"stem": "a", "fields": ["x"]}]})

    result = _call({"skill_id": "demo.skill", "artifacts": []})

    assert not result.get("is_error")
    written = json.loads((skill_dir / ".workspace" / "runtime_config.json").read_text(encoding="utf-8"))
    assert written["artifacts"] == []


def test_an_unusable_shape_is_refused_at_the_boundary_with_the_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _demo_skill(tmp_path, monkeypatch)

    missing_stem = _call({"skill_id": "demo.skill", "artifacts": [{"fields": ["x"]}]})
    bad_mode = _call(
        {"skill_id": "demo.skill", "artifacts": [{"stem": "a", "fields": ["x"], "mode": "bogus"}]}
    )
    not_a_list = _call({"skill_id": "demo.skill", "artifacts": "segmentation_result"})

    for refused in (missing_stem, bad_mode, not_a_list):
        assert refused.get("is_error")
    assert "artifacts" in str(_payload(not_a_list))
    assert _payload(bad_mode)["errors"], "拒绝必须带上具体哪里不合法,不能只说一句失败"


def test_the_panel_route_and_the_tool_share_one_schema() -> None:
    """Two writers, one contract — a second validator is how they would drift."""
    from app.models.runtime_config import RuntimeArtifactsRequest
    from app.routers import runtime_config as router_module

    source = Path(router_module.__file__).read_text(encoding="utf-8")
    assert "class RuntimeArtifact(" not in source, "路由不得再自带一份产物 schema"
    assert RuntimeArtifactsRequest.__module__ == "app.models.runtime_config"
