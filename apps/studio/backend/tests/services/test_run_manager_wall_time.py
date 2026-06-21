"""⑧a wall_time passthrough: engine metrics' wall_time_sec must survive the
Studio TokensMetrics projection (`_tokens_metrics`) and reach the RunMetadata DTO.

Regression guard: TokensMetrics declared `extra="forbid"` without `wall_time_sec`,
so `_tokens_metrics` silently dropped the field and the frontend read n/a.
"""

from __future__ import annotations

from datetime import UTC


def test_tokens_metrics_projection_carries_wall_time_sec() -> None:
    from app.services.run_manager import _tokens_metrics

    raw = {
        "total_input_tokens": 100,
        "total_output_tokens": 50,
        "total_tokens": 150,
        "cost_estimate": 0.42,
        "wall_time_sec": 3.14,
    }

    metrics = _tokens_metrics(raw)

    assert metrics is not None
    assert metrics.input_tokens == 100
    assert metrics.output_tokens == 50
    assert metrics.total_tokens == 150
    assert metrics.wall_time_sec == 3.14


def test_tokens_metrics_projection_wall_time_absent_is_none() -> None:
    from app.services.run_manager import _tokens_metrics

    metrics = _tokens_metrics({"input_tokens": 1, "output_tokens": 2, "total_tokens": 3})

    assert metrics is not None
    assert metrics.wall_time_sec is None


def test_run_metadata_serialization_exposes_wall_time_sec() -> None:
    """End-to-end: the value the frontend reads (RunMetadata.metrics.wall_time_sec)."""
    from datetime import datetime

    from app.models import RunMetadata
    from app.services.run_manager import _tokens_metrics

    raw = {
        "total_input_tokens": 10,
        "total_output_tokens": 20,
        "total_tokens": 30,
        "wall_time_sec": 2.5,
    }
    metadata = RunMetadata(
        run_id="run-1",
        status="success",
        started_at=datetime(2026, 6, 19, tzinfo=UTC),
        metrics=_tokens_metrics(raw),
    )

    dumped = metadata.model_dump(mode="json")

    assert dumped["metrics"]["wall_time_sec"] == 2.5
