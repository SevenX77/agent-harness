from __future__ import annotations

import importlib
from typing import Any

import pytest
from graph_agent.tools.builtin.parallel_map import parallel_map

parallel_map_module = importlib.import_module("graph_agent.tools.builtin.parallel_map")


class Collector:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)


class StaticUuid:
    hex = "abcdef1234567890"


def test_parallel_map_empty_list_returns_empty_without_running_children(
    monkeypatch: pytest.MonkeyPatch,
    mock_skill_resolver: object,
) -> None:
    def fail_run_one_item(**kwargs: Any) -> dict[str, Any]:
        raise AssertionError(f"unexpected child run: {kwargs}")

    monkeypatch.setattr(parallel_map_module, "_run_one_item", fail_run_one_item)

    assert (
        parallel_map("child.skill", [], "item", skill_resolver=mock_skill_resolver)
        == []
    )


def test_parallel_map_runs_children_in_input_order_and_emits_group_events(
    monkeypatch: pytest.MonkeyPatch,
    mock_skill_resolver: object,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run_one_item(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {
            "item": kwargs["item"],
            "sub_run_id": kwargs["sub_run_id"],
            "group_key": kwargs["group_key"],
            "inputs": dict(kwargs["base_inputs"]),
        }

    monkeypatch.setattr(parallel_map_module.uuid, "uuid4", lambda: StaticUuid())
    monkeypatch.setattr(parallel_map_module, "_run_one_item", fake_run_one_item)
    collector = Collector()

    result = parallel_map(
        "child.skill",
        ["a", "b", "c"],
        "item",
        skill_resolver=mock_skill_resolver,
        max_concurrent=2,
        base_runtime_inputs={"shared": 1},
        callbacks=[collector],
        trace_dir="traces",
    )

    assert [item["item"] for item in result] == ["a", "b", "c"]
    assert [item["sub_run_id"] for item in result] == [
        "abcdef123456-0000",
        "abcdef123456-0001",
        "abcdef123456-0002",
    ]
    assert {item["group_key"] for item in result} == {"abcdef123456"}
    assert all(item["inputs"] == {"shared": 1} for item in result)
    assert [event.event_type for event in collector.events] == [
        "parallel_map_group_started",
        "parallel_map_group_ended",
    ]
    assert collector.events[0].item_count == 3
    assert collector.events[0].max_concurrent == 2
    assert collector.events[1].succeeded == 3
    assert collector.events[1].failed == 0
    assert {call["trace_dir"] for call in calls} == {"traces"}


def test_parallel_map_collects_child_errors_by_default(
    monkeypatch: pytest.MonkeyPatch,
    mock_skill_resolver: object,
) -> None:
    def fake_run_one_item(**kwargs: Any) -> dict[str, Any]:
        if kwargs["item"] == "bad":
            raise RuntimeError("boom")
        return {"ok": kwargs["item"]}

    monkeypatch.setattr(parallel_map_module.uuid, "uuid4", lambda: StaticUuid())
    monkeypatch.setattr(parallel_map_module, "_run_one_item", fake_run_one_item)

    result = parallel_map(
        "child.skill",
        ["good", "bad"],
        "item",
        skill_resolver=mock_skill_resolver,
    )

    assert result == [
        {"ok": "good"},
        {"error": "boom", "sub_run_id": "abcdef123456-0001"},
    ]


def test_parallel_map_validates_concurrency_and_item_name(mock_skill_resolver: object) -> None:
    with pytest.raises(ValueError, match="max_concurrent must be >= 1"):
        parallel_map("child.skill", ["x"], "item", skill_resolver=mock_skill_resolver, max_concurrent=0)

    with pytest.raises(ValueError, match="item_as must be a non-empty string"):
        parallel_map("child.skill", ["x"], "", skill_resolver=mock_skill_resolver)
