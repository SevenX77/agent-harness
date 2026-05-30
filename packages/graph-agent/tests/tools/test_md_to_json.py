"""Tests for md_to_json metadata isolation."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pytest
from pydantic import BaseModel, ConfigDict, Field

import graph_agent.tools.md_to_json as md_to_json_module
from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.exceptions import make_error_payload
from graph_agent.core.result import WorkflowResult
from graph_agent.tools.md_to_json import (
    BlockMeta,
    ParsedBlock,
    _type_to_constraint,
    diagnose,
    md_to_json,
    parse_md,
)


class StrictSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    type: str
    content: str


class NestedPayload(BaseModel):
    title: str


def test_parse_md_separates_framework_meta_from_user_data() -> None:
    blocks = parse_md(
        """
## segment 1
- index: 1
- type: B
- content: opening beat
""",
        StrictSegment,
    )

    assert len(blocks) == 1
    assert blocks[0].meta.id == "segment 1"
    assert blocks[0].data == {
        "index": 1,
        "type": "B",
        "content": "opening beat",
    }
    assert "_md_id" not in blocks[0].data


def test_diagnose_validates_data_only_with_extra_forbid() -> None:
    report = diagnose(
        [
            ParsedBlock(
                meta=BlockMeta(id="segment 1"),
                data={"index": 1, "type": "B", "content": "opening beat"},
            )
        ],
        StrictSegment,
    )

    assert report.all_valid
    assert report.valid_items[0].model_dump() == {
        "index": 1,
        "type": "B",
        "content": "opening beat",
    }


def test_diagnose_reports_item_id_from_meta() -> None:
    report = diagnose(
        [
            ParsedBlock(
                meta=BlockMeta(id="segment 1"),
                data={"index": 1, "type": "B"},
            )
        ],
        StrictSegment,
    )

    assert not report.all_valid
    assert report.errors[0].item_id == "segment 1"
    assert report.errors[0].fields[0].field == "content"
    assert "item_id='segment 1'" in report.to_prompt_string()
    assert "_md_id" not in report.to_prompt_string()


def test_md_to_json_accepts_strict_schema_without_metadata_collision(
    mock_skill_resolver: object,
) -> None:
    items = md_to_json(
        """
## segment 1
- index: 1
- type: B
- content: opening beat
""",
        StrictSegment,
        skill_resolver=mock_skill_resolver,
    )

    assert [item.model_dump() for item in items] == [
        {"index": 1, "type": "B", "content": "opening beat"}
    ]


def test_md_to_json_patch_path_sends_wrapped_error_items(
    monkeypatch, mock_skill_resolver: object
) -> None:
    calls = []

    def fake_run_skill(*args, **kwargs):
        calls.append(kwargs)
        return {
            "context": {
                "final_results": [
                    {"index": 1, "type": "B", "content": "opening beat"},
                ]
            }
        }

    monkeypatch.setattr(md_to_json_module, "run_skill", fake_run_skill)

    items = md_to_json(
        """
## segment 1
- index: 1
- type: B
""",
        StrictSegment,
        skill_resolver=mock_skill_resolver,
    )

    assert [item.model_dump() for item in items] == [
        {"index": 1, "type": "B", "content": "opening beat"}
    ]
    assert calls[0]["error_items"] == [
        {"item_id": "segment 1", "fields": {"index": 1, "type": "B"}}
    ]


def test_md_to_json_patch_path_run_skill_failure_raises_skill_load_error(
    monkeypatch: pytest.MonkeyPatch, mock_skill_resolver: object
) -> None:
    def fake_run_skill(*args, **kwargs):
        del args, kwargs
        now = datetime.now(UTC)
        return WorkflowResult(
            success=False,
            run_id="r1",
            skill_id="md-patch",
            context={},
            error=make_error_payload(
                "[F-v3-graph-root-missing]",
                "[F-v3-graph-root-missing] missing required GRAPH.md",
            ),
            started_at=now,
            finished_at=now,
        )

    monkeypatch.setattr(md_to_json_module, "run_skill", fake_run_skill)

    expected_context = r"md_to_json|md-patch|deferred"
    with pytest.raises(SkillLoadError, match=expected_context):
        md_to_json(
            """
## segment 1
- index: 1
- type: B
""",
            StrictSegment,
            skill_resolver=mock_skill_resolver,
        )


def test_md_patch_finalize_outputs_business_dicts_only() -> None:
    package_root = Path(__file__).resolve().parents[2]
    patch_tools_path = (
        package_root / "src/graph_agent/skills/builtin/md-patch/script/patch_tools.py"
    )
    spec = importlib.util.spec_from_file_location("md_patch_tools_test", patch_tools_path)
    assert spec is not None
    assert spec.loader is not None
    patch_tools = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(patch_tools)

    context = {
        "schema": StrictSegment,
        "valid_results": [
            {"index": 1, "type": "B", "content": "opening beat"},
        ],
        "error_items": [
            {
                "item_id": "segment 2",
                "fields": {"index": 2, "type": "C"},
            }
        ],
        "patches": {"segment 2": {"content": "system beat"}},
    }

    patch_tools.finalize(context)

    assert context["final_results"] == [
        {"index": 1, "type": "B", "content": "opening beat"},
        {"index": 2, "type": "C", "content": "system beat"},
    ]
    assert all("item_id" not in item for item in context["final_results"])
    assert patch_tools.validate(context) == (True, "all items valid")


def test_type_to_constraint_pins_current_primitive_and_bound_rendering() -> None:
    class TypeSchema(BaseModel):
        text: str
        count: int = Field(ge=1, le=9)
        score: float = Field(ge=0.25, le=1.5)

    fields = TypeSchema.model_fields

    assert _type_to_constraint(fields["text"].annotation, fields["text"]) == "[文本]"
    assert _type_to_constraint(fields["count"].annotation, fields["count"]) == "[整数, >=1, <=9]"
    assert (
        _type_to_constraint(fields["score"].annotation, fields["score"])
        == "[小数, >=0.25, <=1.5]"
    )


def test_type_to_constraint_pins_current_collection_literal_and_optional_rendering() -> None:
    class TypeSchema(BaseModel):
        maybe_text: str | None
        tags: list[str]
        ratings: list[int]
        status: Literal["draft", "done"]
        nested: NestedPayload
        unknown: dict[str, str]

    fields = TypeSchema.model_fields

    assert _type_to_constraint(fields["maybe_text"].annotation, fields["maybe_text"]) == "[文本]"
    assert _type_to_constraint(fields["tags"].annotation, fields["tags"]) == "[列表，缩进子行或逗号分隔]"
    assert _type_to_constraint(fields["ratings"].annotation, fields["ratings"]) == "[列表，元素为 [整数]]"
    assert (
        _type_to_constraint(fields["status"].annotation, fields["status"])
        == "[字符串，限 'draft', 'done']"
    )
    assert _type_to_constraint(fields["nested"].annotation, fields["nested"]) == "[嵌套对象]"
    assert _type_to_constraint(fields["unknown"].annotation, fields["unknown"]) == "[未知]"
