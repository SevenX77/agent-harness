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
    source = {"business_data_parsed": {"items": [{"title": "Opening"}, {"title": "Turn"}]}}

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


# ---------------------------------------------------------------------------
# MVP-2 T8: branch coverage for IOManager edge cases
#
# The tests below pin previously-uncovered branches in the path resolver
# and ``validate_spec`` so the module hits ≥ 95% coverage. Each test
# names the scenario the engine actually faces in production rather
# than the source line number.
# ---------------------------------------------------------------------------


def test_resolve_hoist_with_dotted_path_anchored_on_source_field() -> None:
    """``hoist_path`` that begins with ``<source_field>.`` resolves
    against the whole source dict (anchored mode)."""
    manager = IOManager(
        [IODef(source_field="payload", target_field="story_title", hoist_path="payload.title")]
    )
    result = manager.resolve_hoist({"payload": {"title": "ok"}}, BusinessData())

    assert result.io_errors == []
    assert result.new_business_data.model_dump()["story_title"] == "ok"


def test_resolve_hoist_with_bracketed_anchored_path() -> None:
    """``hoist_path`` of the form ``<source_field>[i]`` indexes a list
    via the bracketed-anchor branch."""
    manager = IOManager([IODef(source_field="items", target_field="first", hoist_path="items[0]")])
    result = manager.resolve_hoist({"items": ["alpha", "beta"]}, BusinessData())

    assert result.io_errors == []
    assert result.new_business_data.model_dump()["first"] == "alpha"


def test_resolve_hoist_relative_path_when_source_present() -> None:
    """When source field exists, a path that does not start with the
    field name resolves *relative* to the field's value."""
    manager = IOManager([IODef(source_field="payload", target_field="title", hoist_path="title")])
    result = manager.resolve_hoist({"payload": {"title": "anchored"}}, BusinessData())

    assert result.io_errors == []
    assert result.new_business_data.model_dump()["title"] == "anchored"


def test_resolve_hoist_absolute_fallback_when_source_missing() -> None:
    """When the source field key is absent, fall back to absolute path
    resolution against the whole source dict."""
    manager = IOManager(
        [IODef(source_field="payload", target_field="title", hoist_path="other.title")]
    )
    result = manager.resolve_hoist({"other": {"title": "fallback"}}, BusinessData())

    assert result.io_errors == []
    assert result.new_business_data.model_dump()["title"] == "fallback"


def test_validate_spec_non_string_hoist_path() -> None:
    ok, errors = IOManager.validate_spec(
        {"source_field": "title", "target_field": "story", "hoist_path": 42}
    )

    assert ok is False
    assert "hoist_path must be a string" in errors[0]


def test_validate_spec_non_bool_required() -> None:
    ok, errors = IOManager.validate_spec(
        {"source_field": "title", "target_field": "story", "required": "yes"}
    )

    assert ok is False
    assert "required must be a bool" in errors[0]


def test_resolve_hoist_index_into_non_list_returns_missing() -> None:
    """Bracket index against a non-list value must surface as missing."""
    manager = IOManager(
        [IODef(source_field="payload", target_field="first", hoist_path="payload[0]")]
    )
    result = manager.resolve_hoist({"payload": {"not": "a list"}}, BusinessData())

    assert any("missing" in err.lower() for err in result.io_errors)


def test_resolve_hoist_empty_path_string_falls_back_to_source_field() -> None:
    """Empty hoist_path is falsy, so the bare ``source.get(source_field)``
    branch runs; the missing source field surfaces as a required miss."""
    manager = IOManager([IODef(source_field="title", target_field="story_title", hoist_path="")])
    result = manager.resolve_hoist({}, BusinessData())

    assert any("missing" in err.lower() for err in result.io_errors)


def test_resolve_hoist_double_dot_path_returns_missing() -> None:
    """``payload..title`` has an empty middle token — the parser must
    reject it without raising; resolver records a missing field."""
    manager = IOManager(
        [IODef(source_field="payload", target_field="title", hoist_path="payload..title")]
    )
    result = manager.resolve_hoist({"payload": {"title": "x"}}, BusinessData())

    assert any("missing" in err.lower() for err in result.io_errors)


def test_resolve_hoist_negative_index_returns_missing() -> None:
    """Negative indices are explicitly rejected by the path parser."""
    manager = IOManager(
        [IODef(source_field="payload", target_field="first", hoist_path="payload[-1]")]
    )
    result = manager.resolve_hoist({"payload": ["alpha"]}, BusinessData())

    assert any("missing" in err.lower() for err in result.io_errors)


def test_resolve_hoist_unclosed_bracket_returns_missing() -> None:
    """``payload[0`` — unclosed bracket; parser returns ``["invalid"]``,
    resolver surfaces missing field."""
    manager = IOManager(
        [IODef(source_field="payload", target_field="first", hoist_path="payload[0")]
    )
    result = manager.resolve_hoist({"payload": ["alpha"]}, BusinessData())

    assert any("missing" in err.lower() for err in result.io_errors)
