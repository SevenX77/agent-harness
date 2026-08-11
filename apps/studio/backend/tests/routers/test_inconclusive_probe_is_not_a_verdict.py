"""A probe that could not get an answer does not get to record one.

The effort question set already works this way — a batch containing any
inconclusive answer is voided rather than written as "this route refuses that
level" (gateway ``probing/questions.py``). The evidence writer had not learned
it: it split on ``status == "ok"`` and filed everything else as probe-failed,
so an exhausted balance or a dropped connection was recorded as a fact about
the model. Found live 2026-08-11 probing ark-official.
"""

from __future__ import annotations

import pytest
from app.services.model_probe import ModelProbeResult


@pytest.mark.parametrize(
    "status",
    ["rate_limited", "quota_exceeded", "network_error", "timeout", "invalid_key"],
)
def test_an_unanswerable_probe_writes_no_verdict_about_the_model(status: str) -> None:
    from app.routers.llm import _probe_answered_about_the_model

    result = ModelProbeResult(model_id="m", status=status)  # type: ignore[arg-type]

    assert _probe_answered_about_the_model(result) is False


@pytest.mark.parametrize("status", ["ok", "invalid_model", "protocol_unsupported"])
def test_an_answered_probe_is_recorded(status: str) -> None:
    from app.routers.llm import _probe_answered_about_the_model

    result = ModelProbeResult(model_id="m", status=status)  # type: ignore[arg-type]

    assert _probe_answered_about_the_model(result) is True
