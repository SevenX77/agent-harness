from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from graph_agent.core.runner import run_skill


def test_run_skill_missing_graph_root_writes_error_diagnostics_snapshot(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    skill_dir = tmp_path / "not_v030_skill"
    skill_dir.mkdir()
    workspace_dir = tmp_path / "workspace"

    result = run_skill(
        skill_dir,
        workspace_dir=workspace_dir,
        thread_id="diagnostics-red",
        skill_resolver=mock_skill_resolver,
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "[F-v3-graph-root-missing]"

    dumped = result.model_dump(mode="json")
    assert dumped["error"]["code"] == result.error.code
    assert [item["code"] for item in dumped["diagnostics"]] == [result.error.code]
    assert dumped["diagnostics_truncated"] is False
    assert dumped["diagnostic_counts"] == {
        "total": 1,
        "by_level": {"FATAL": 1},
        "by_code": {result.error.code: 1},
    }

    result_path = workspace_dir / "runs" / "diagnostics-red" / "result.json"
    persisted = json.loads(result_path.read_text(encoding="utf-8"))
    assert persisted["error"]["code"] == result.error.code
    assert [item["code"] for item in persisted["diagnostics"]] == [result.error.code]
    assert persisted["diagnostic_counts"]["by_code"][result.error.code] == 1
