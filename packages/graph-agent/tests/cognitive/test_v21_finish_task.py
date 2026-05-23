from __future__ import annotations

from typing import Any

import pytest
from graph_agent.cognitive.finish_task import build_finish_task_tool
from graph_agent.cognitive.md2json import parse_finish_markdown
from graph_agent.cognitive.md_patch import FakeMdPatchClient, LLMMdPatchClient

TITLE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"title": {"type": "string"}},
    "required": ["title"],
    "additionalProperties": False,
}

COUNT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"count": {"type": "integer"}},
    "required": ["count"],
    "additionalProperties": False,
}

OBJECT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"payload": {"type": "object"}},
    "required": ["payload"],
    "additionalProperties": False,
}

TITLE_COUNT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "count": {"type": "integer"},
    },
    "required": ["title", "count"],
    "additionalProperties": False,
}


def test_finish_task_happy_path() -> None:
    tool = build_finish_task_tool(TITLE_SCHEMA, parse_finish_markdown)

    result = tool.invoke({"markdown": "## title\n\nbody"})

    assert result == {"ok": True, "data": {"title": "body"}, "repaired": False}


def test_finish_task_no_schema_skips_validate() -> None:
    patcher = FakeMdPatchClient(["## title\n\npatched"])
    tool = build_finish_task_tool(None, parse_finish_markdown, patcher=patcher)

    result = tool.invoke({"markdown": "## title\n\nbody"})

    assert result == {"ok": True, "data": {"title": "body"}, "repaired": False}
    assert patcher.calls == []


def test_finish_task_missing_fence_patched() -> None:
    patcher = FakeMdPatchClient(['## payload\n\n```json\n{"ok": true}\n```'])
    tool = build_finish_task_tool(OBJECT_SCHEMA, parse_finish_markdown, patcher=patcher)

    result = tool.invoke({"markdown": '## payload\n\n```json\n{"ok": true}'})

    assert result["ok"] is True
    assert result["data"] == {"payload": {"ok": True}}
    assert result["repaired"] is True
    assert result["attempts"] == 1
    assert patcher.calls[0]["attempt"] == 1


def test_finish_task_nested_fence_preserved() -> None:
    tool = build_finish_task_tool(TITLE_SCHEMA, parse_finish_markdown)
    markdown = "## title\n\nExample:\n```python\nprint('ok')\n```"

    result = tool.invoke({"markdown": markdown})

    assert result["ok"] is True
    assert "print('ok')" in result["data"]["title"]


def test_finish_task_int_field_coerced() -> None:
    tool = build_finish_task_tool(COUNT_SCHEMA, parse_finish_markdown)

    result = tool.invoke({"markdown": "## count\n\n42"})

    assert result["ok"] is True
    assert result["data"] == {"count": 42}


def test_finish_task_required_field_missing_patched() -> None:
    patcher = FakeMdPatchClient(["## title\n\nbody\n\n## count\n\n7"])
    tool = build_finish_task_tool(TITLE_COUNT_SCHEMA, parse_finish_markdown, patcher=patcher)

    result = tool.invoke({"markdown": "## title\n\nbody"})

    assert result["ok"] is True
    assert result["data"] == {"title": "body", "count": 7}
    assert result["repaired"] is True
    assert result["attempts"] == 1
    assert patcher.calls[0]["validation_errors"][0]["validator"] == "required"


def test_finish_task_3_retries_then_structured_error() -> None:
    patcher = FakeMdPatchClient(["## title\n\nbody"])
    tool = build_finish_task_tool(
        TITLE_COUNT_SCHEMA,
        parse_finish_markdown,
        patcher=patcher,
        max_patch_attempts=3,
    )

    result = tool.invoke({"markdown": "## title\n\nbody"})

    assert result["ok"] is False
    assert result["error"]["code"] == "F-v3-md2json"
    assert result["error"]["attempts"] == 3
    assert len(patcher.calls) == 3


def test_finish_task_patcher_unavailable_structured_error() -> None:
    tool = build_finish_task_tool(TITLE_COUNT_SCHEMA, parse_finish_markdown, patcher=None)

    result = tool.invoke({"markdown": "## title\n\nbody"})

    assert result["ok"] is False
    assert result["error"]["code"] == "F-v3-md2json"
    assert result["error"]["attempts"] == 0
    assert result["error"]["validation_errors"][0]["validator"] == "required"


def test_finish_task_invalid_output_schema_fatal() -> None:
    with pytest.raises(RuntimeError, match=r"\[F-v3-md2json\].*output_schema invalid"):
        build_finish_task_tool({"invalid": "schema"}, parse_finish_markdown)


def test_finish_task_empty_output_schema_is_allowed() -> None:
    tool = build_finish_task_tool({}, parse_finish_markdown)

    result = tool.invoke({"markdown": "## title\n\nbody"})

    assert result == {"ok": True, "data": {"title": "body"}, "repaired": False}


def test_finish_task_empty_input_structured_error() -> None:
    tool = build_finish_task_tool(TITLE_SCHEMA, parse_finish_markdown)

    result = tool.invoke({"markdown": ""})

    assert result["ok"] is False
    assert result["error"]["code"] == "F-v3-md2json"
    assert result["error"]["kind"] == "invalid_markdown"


def test_md2json_no_schema_returns_raw_dict() -> None:
    result = parse_finish_markdown("## title\n\nbody", output_schema=None)

    assert result.data == {"title": "body"}
    assert result.validation_errors == []
    assert result.repaired is False


def test_llm_md_patch_client_stub() -> None:
    client = LLMMdPatchClient()

    with pytest.raises(NotImplementedError, match="T1.5 LangGraph"):
        client.patch("## title\n\nbody", TITLE_SCHEMA, [], 1)
