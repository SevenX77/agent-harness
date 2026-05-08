"""Tests for context_access builtin tools."""

from __future__ import annotations

from graph_agent.tools.builtin.context_access import (
    query_working_memory,
    read_artifact,
)


class TestQueryWorkingMemory:
    def test_returns_working_memory(self) -> None:
        ctx = {"_working_memory": "current plan: do X then Y"}

        assert "current plan" in query_working_memory(ctx)

    def test_returns_empty_when_unset(self) -> None:
        ctx = {}

        assert query_working_memory(ctx) == "(empty)"

    def test_returns_empty_for_blank(self) -> None:
        ctx = {"_working_memory": "   "}

        assert query_working_memory(ctx) == "(empty)"

    def test_truncates_oversized(self) -> None:
        ctx = {"_working_memory": "x" * 100_000}

        result = query_working_memory(ctx)

        assert "[truncated]" in result
        assert len(result) < 100_000


class TestReadArtifact:
    def test_reads_named_artifact(self) -> None:
        ctx = {"chapter_summary": "Chapter 1: ..."}

        assert "Chapter 1" in read_artifact(ctx, "chapter_summary")

    def test_underscore_keys_blocked(self) -> None:
        ctx = {"_working_memory": "secret framework state"}

        result = read_artifact(ctx, "_working_memory")

        assert "[read_artifact Error]" in result
        assert "framework-internal" in result

    def test_not_found_returns_hints(self) -> None:
        ctx = {"available_thing": "x"}

        result = read_artifact(ctx, "missing_thing")

        assert "[read_artifact Error]" in result
        assert "Available artifacts" in result
        assert "available_thing" in result

    def test_empty_name_rejected(self) -> None:
        ctx = {}

        result = read_artifact(ctx, "")

        assert "[read_artifact Error]" in result

    def test_repr_for_non_string_value(self) -> None:
        ctx = {"counts": {"a": 1, "b": 2}}

        result = read_artifact(ctx, "counts")

        assert "'a'" in result and "1" in result

    def test_truncates_oversized(self) -> None:
        ctx = {"big_data": "x" * 100_000}

        result = read_artifact(ctx, "big_data")

        assert "[truncated]" in result
        assert len(result) < 100_000

    def test_none_value_returns_none_marker(self) -> None:
        ctx = {"empty_field": None}

        assert read_artifact(ctx, "empty_field") == "(none)"
