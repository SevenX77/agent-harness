"""Tests for md_to_json metadata isolation."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from pydantic import BaseModel, ConfigDict

import graph_agent.tools.md_to_json as md_to_json_module
from graph_agent.tools.md_to_json import (
    BlockMeta,
    ParsedBlock,
    diagnose,
    md_to_json,
    parse_md,
)


class StrictSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    type: str
    content: str


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


def test_md_to_json_accepts_strict_schema_without_metadata_collision() -> None:
    items = md_to_json(
        """
## segment 1
- index: 1
- type: B
- content: opening beat
""",
        StrictSegment,
    )

    assert [item.model_dump() for item in items] == [
        {"index": 1, "type": "B", "content": "opening beat"}
    ]


def test_md_to_json_patch_path_sends_wrapped_error_items(monkeypatch) -> None:
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
    )

    assert [item.model_dump() for item in items] == [
        {"index": 1, "type": "B", "content": "opening beat"}
    ]
    assert calls[0]["error_items"] == [
        {"item_id": "segment 1", "fields": {"index": 1, "type": "B"}}
    ]


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
