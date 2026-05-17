from __future__ import annotations

from graph_agent.core._predict_internal.path_diff import compute_diff


def test_compute_diff_identical_paths() -> None:
    diff = compute_diff(["start", "draft", "finish"], ["start", "draft", "finish"])

    assert diff.expected_path == ["start", "draft", "finish"]
    assert diff.actual_path == ["start", "draft", "finish"]
    assert diff.missing == []
    assert diff.extra == []
    assert diff.order_mismatch is False


def test_compute_diff_reports_missing_phase() -> None:
    diff = compute_diff(["start", "draft", "review", "finish"], ["start", "draft", "finish"])

    assert diff.missing == ["review"]
    assert diff.extra == []
    assert diff.order_mismatch is False


def test_compute_diff_reports_extra_phase() -> None:
    diff = compute_diff(["start", "finish"], ["start", "debug", "finish"])

    assert diff.missing == []
    assert diff.extra == ["debug"]
    assert diff.order_mismatch is False


def test_compute_diff_reports_order_mismatch() -> None:
    diff = compute_diff(
        ["start", "draft", "review", "finish"], ["start", "review", "draft", "finish"]
    )

    assert diff.missing == []
    assert diff.extra == []
    assert diff.order_mismatch is True


def test_compute_diff_preserves_duplicate_loop_visits() -> None:
    diff = compute_diff(
        ["start", "loop", "work", "loop", "finish"],
        ["start", "loop", "loop", "work", "loop", "finish"],
    )

    assert diff.missing == []
    assert diff.extra == ["loop"]
    assert diff.order_mismatch is False
