"""P1 数据面读工具(决议 2026-08-03 PR-H/PR-I):

- `read_skill_file(skill_id, path, start_line?, end_line?)`:经 skill 索引解析、
  限定 skill 目录内、有界(D6)。
- `get_workspace_config(skill_id)`:runtime_config 的结构化投影(绑定存路径不存值,
  天然有界)。
- `list_run_artifacts(skill_id, run_id?)` / `read_run_artifact(skill_id, run_id, name)`:
  `.workspace/runs/<run_id>/artifacts/` 的枚举与有界读取。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest


def _call(monkeypatch: pytest.MonkeyPatch, skill_dir: Path, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    from app.services import copilot_tools, skills

    monkeypatch.setattr(skills, "ensure_workspace_skill_dir", lambda _skill_id: skill_dir)
    tool = getattr(copilot_tools, f"{tool_name}_tool")
    return asyncio.run(tool.handler({"skill_id": "data-skill", **args}))


def _payload(result: dict[str, Any]) -> Any:
    return json.loads(result["content"][0]["text"])


def test_read_skill_file_returns_content_and_honors_range(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skill_dir = tmp_path / "data-skill"
    skill_dir.mkdir()
    (skill_dir / "GRAPH.md").write_text("line-1\nline-2\nline-3\nline-4\n", encoding="utf-8")

    full = _payload(_call(monkeypatch, skill_dir, "read_skill_file", {"path": "GRAPH.md"}))
    assert full["content"] == "line-1\nline-2\nline-3\nline-4"
    assert full["total_lines"] == 4
    assert full["truncated"] is False

    sliced = _payload(
        _call(monkeypatch, skill_dir, "read_skill_file", {"path": "GRAPH.md", "start_line": 2, "end_line": 3})
    )
    assert sliced["content"] == "line-2\nline-3"
    assert sliced["start_line"] == 2 and sliced["end_line"] == 3


def test_read_skill_file_is_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # D6:只读工具一律有界——超长文件默认截断并如实标注,总行数照报。
    skill_dir = tmp_path / "data-skill"
    skill_dir.mkdir()
    (skill_dir / "big.md").write_text("\n".join(f"row-{i}" for i in range(1, 1001)), encoding="utf-8")

    payload = _payload(_call(monkeypatch, skill_dir, "read_skill_file", {"path": "big.md"}))
    assert payload["truncated"] is True
    assert payload["total_lines"] == 1000
    assert payload["content"].count("\n") < 500


def test_read_skill_file_rejects_escape_attempts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Fail fast 在边界:越出 skill 目录的路径一律拒绝,绝对路径同罪。
    skill_dir = tmp_path / "data-skill"
    skill_dir.mkdir()
    (tmp_path / "outside.txt").write_text("secret", encoding="utf-8")

    escaped = _call(monkeypatch, skill_dir, "read_skill_file", {"path": "../outside.txt"})
    assert escaped.get("is_error") is True

    absolute = _call(
        monkeypatch, skill_dir, "read_skill_file", {"path": str(tmp_path / "outside.txt")}
    )
    assert absolute.get("is_error") is True

    missing = _call(monkeypatch, skill_dir, "read_skill_file", {"path": "nope.md"})
    assert missing.get("is_error") is True


def test_get_workspace_config_projects_runtime_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skill_dir = tmp_path / "data-skill"
    (skill_dir / ".workspace").mkdir(parents=True)
    (skill_dir / ".workspace" / "runtime_config.json").write_text(
        json.dumps(
            {
                "schema_version": "studio.runtime_config.v2",
                "artifacts": [{"stem": "segments", "fields": ["segmentation_result"]}],
                "inputs": {
                    "active": {
                        "root": {
                            "chapters": {
                                "path": "import_files/in.json",
                                "type": "array",
                                "value_type": "json",
                                "json_path": ["chapters"],
                            }
                        },
                        "phases": {},
                    },
                    "removed": {},
                },
            }
        ),
        encoding="utf-8",
    )

    payload = _payload(_call(monkeypatch, skill_dir, "get_workspace_config", {}))
    assert payload["artifacts"] == [{"stem": "segments", "fields": ["segmentation_result"]}]
    assert payload["inputs"]["active"]["root"]["chapters"]["path"] == "import_files/in.json"


def test_run_artifact_tools_list_and_read_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skill_dir = tmp_path / "data-skill"
    artifacts = skill_dir / ".workspace" / "runs" / "run-1" / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "segments_latest_20260806.json").write_text(
        json.dumps({"segments": [1, 2, 3]}), encoding="utf-8"
    )

    listing = _payload(_call(monkeypatch, skill_dir, "list_run_artifacts", {}))
    [run] = listing["runs"]
    assert run["run_id"] == "run-1"
    assert run["artifacts"][0]["name"] == "segments_latest_20260806.json"
    assert run["artifacts"][0]["size_bytes"] > 0

    body = _payload(
        _call(
            monkeypatch,
            skill_dir,
            "read_run_artifact",
            {"run_id": "run-1", "name": "segments_latest_20260806.json"},
        )
    )
    assert json.loads(body["content"]) == {"segments": [1, 2, 3]}

    # name 越界(路径逃逸)一律拒绝。
    escape = _call(
        monkeypatch, skill_dir, "read_run_artifact", {"run_id": "run-1", "name": "../../secrets.json"}
    )
    assert escape.get("is_error") is True


def test_list_run_artifacts_without_runs_is_empty_not_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skill_dir = tmp_path / "data-skill"
    skill_dir.mkdir()
    payload = _payload(_call(monkeypatch, skill_dir, "list_run_artifacts", {}))
    assert payload["runs"] == []


def test_optional_params_are_declared_optional_in_the_tool_schema() -> None:
    # 真机 /mcp 抓到的缺陷:dict schema 里裸类型 = 必填,导致"不带 range 的整读"与
    # "不带 run_id 的枚举"被 SDK 的输入校验直接拒。可选参数必须用 (type, None) 声明。
    from app.services.copilot_tools import list_run_artifacts_tool, read_skill_file_tool

    read_schema = read_skill_file_tool.input_schema
    assert read_schema["start_line"] == (int, None)
    assert read_schema["end_line"] == (int, None)
    assert list_run_artifacts_tool.input_schema["run_id"] == (str, None)


def test_data_read_tools_are_pre_allowed_on_both_surfaces() -> None:
    # 三面注册:MCP 工具表、免审批清单、CLI allowlist(lib.rs 由 Rust 测试锁)。
    from app.services.copilot import _DECLARATIVE_ALLOWED_TOOLS
    from app.services.copilot_tools import _copilot_mcp_tools

    tool_names = {tool.name for tool in _copilot_mcp_tools()}
    for name in ("read_skill_file", "get_workspace_config", "list_run_artifacts", "read_run_artifact"):
        assert name in tool_names
        assert f"mcp__studio__{name}" in _DECLARATIVE_ALLOWED_TOOLS
