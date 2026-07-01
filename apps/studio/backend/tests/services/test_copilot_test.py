from __future__ import annotations

from app.services.copilot_test import PingResult


def test_ping_result_retains_first_model_seen_for_compatibility() -> None:
    result = PingResult(latency_ms=12, model_ids=("gpt-5", "gpt-5-mini"))

    assert result.model_seen == "gpt-5"
