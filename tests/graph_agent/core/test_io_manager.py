"""Tests for MVP-2 T3 core IOManager hoist routing."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

from graph_agent.core.io_manager import HoistResult, IODef, IOManager
from graph_agent.core.state import BusinessData


def test_io_def_frozen() -> None:
    spec = IODef(source_field="title", target_field="story_title")

    try:
        spec.source_field = "other"  # type: ignore[misc]
    except FrozenInstanceError:
        pass
    else:  # pragma: no cover - defensive branch
        raise AssertionError("IODef must be frozen")


def test_io_manager_init_with_specs() -> None:
    specs = [IODef(source_field="title", target_field="story_title")]

    manager = IOManager(specs)

    assert manager.io_specs == specs
    assert manager.io_specs is not specs


def test_resolve_hoist_simple_field_copy() -> None:
    manager = IOManager([IODef(source_field="title", target_field="story_title")])
    target = BusinessData()

    result = manager.resolve_hoist({"title": "Opening"}, target)

    assert isinstance(result, HoistResult)
    assert result.io_errors == []
    assert result.new_business_data["story_title"] == "Opening"


def test_resolve_hoist_required_field_missing_returns_error() -> None:
    manager = IOManager([IODef(source_field="title", target_field="story_title")])
    target = BusinessData()

    result = manager.resolve_hoist({}, target)

    assert result.new_business_data is target
    assert result.io_errors == ["required io.output 'title' missing in source_data"]


def test_resolve_hoist_optional_field_missing_skipped() -> None:
    manager = IOManager(
        [IODef(source_field="summary", target_field="story_summary", required=False)]
    )
    target = BusinessData()

    result = manager.resolve_hoist({}, target)

    assert result.new_business_data is target
    assert result.io_errors == []
    assert "story_summary" not in result.new_business_data


def test_resolve_hoist_immutable_returns_new_data() -> None:
    manager = IOManager([IODef(source_field="title", target_field="story_title")])
    target = BusinessData(existing="kept")

    result = manager.resolve_hoist({"title": "Opening"}, target)

    assert result.new_business_data is not target
    assert "story_title" not in target
    assert result.new_business_data.model_dump() == {
        "existing": "kept",
        "story_title": "Opening",
    }


def test_resolve_hoist_multiple_specs() -> None:
    manager = IOManager(
        [
            IODef(source_field="title", target_field="story_title"),
            IODef(source_field="score", target_field="quality_score"),
        ]
    )

    result = manager.resolve_hoist(
        {"title": "Opening", "score": 9},
        BusinessData(),
    )

    assert result.io_errors == []
    assert result.new_business_data.model_dump() == {
        "story_title": "Opening",
        "quality_score": 9,
    }


def test_resolve_hoist_nested_path() -> None:
    manager = IOManager(
        [
            IODef(
                source_field="business_data_parsed",
                target_field="first_title",
                hoist_path="items[0].title",
            )
        ]
    )
    source = {
        "business_data_parsed": {"items": [{"title": "Opening"}, {"title": "Turn"}]}
    }

    result = manager.resolve_hoist(source, BusinessData())

    assert result.io_errors == []
    assert result.new_business_data["first_title"] == "Opening"


def test_resolve_hoist_nested_root_path() -> None:
    manager = IOManager(
        [IODef(source_field="items", target_field="first_title", hoist_path="items[0].title")]
    )

    result = manager.resolve_hoist(
        {"items": [{"title": "Opening"}]},
        BusinessData(),
    )

    assert result.io_errors == []
    assert result.new_business_data["first_title"] == "Opening"


def test_resolve_hoist_nested_path_missing_reports_required_error() -> None:
    manager = IOManager(
        [IODef(source_field="items", target_field="first_title", hoist_path="items[1].title")]
    )

    result = manager.resolve_hoist({"items": [{"title": "Opening"}]}, BusinessData())

    assert result.io_errors == ["required io.output 'items' missing in source_data"]
    assert "first_title" not in result.new_business_data


def test_resolve_hoist_invalid_nested_path_reports_required_error() -> None:
    manager = IOManager(
        [IODef(source_field="items", target_field="first_title", hoist_path="items[bad]")]
    )

    result = manager.resolve_hoist({"items": [{"title": "Opening"}]}, BusinessData())

    assert result.io_errors == ["required io.output 'items' missing in source_data"]
    assert "first_title" not in result.new_business_data


def test_resolve_hoist_type_mismatch_is_advisory_and_still_writes() -> None:
    manager = IOManager([IODef(source_field="score", target_field="score")])
    target = BusinessData(score=1)

    result = manager.resolve_hoist({"score": "high"}, target)

    assert result.new_business_data["score"] == "high"
    assert result.io_errors == [
        "io.output 'score' type mismatch for target 'score': expected int, got str"
    ]


def test_validate_spec_missing_source_field() -> None:
    ok, errors = IOManager.validate_spec({"target_field": "story_title"})

    assert ok is False
    assert errors == ["io.output spec missing source_field"]


def test_validate_spec_missing_target_field() -> None:
    ok, errors = IOManager.validate_spec({"source_field": "title"})

    assert ok is False
    assert errors == ["io.output spec missing target_field"]


def test_validate_spec_valid() -> None:
    ok, errors = IOManager.validate_spec(
        {
            "source_field": "business_data_parsed",
            "target_field": "story_title",
            "hoist_path": "items[0].title",
            "required": True,
        }
    )

    assert ok is True
    assert errors == []


def test_validate_spec_rejects_private_target() -> None:
    ok, errors = IOManager.validate_spec({"source_field": "title", "target_field": "_title"})

    assert ok is False
    assert errors == ["io.output target_field must not start with '_'"]
