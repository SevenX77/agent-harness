from __future__ import annotations

from pathlib import Path


def test_engine_default_predict_resolver_uses_gateway_step4_contract() -> None:
    runner_source = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "graph_agent"
        / "core"
        / "runner.py"
    )

    source = runner_source.read_text(encoding="utf-8")

    assert "ModelResolver(registry_snapshot" not in source, (
        "Engine runner default predict resolver must construct Gateway ModelResolver "
        "with config_store=... and user_id=..., not the removed registry_snapshot=... "
        f"contract. Found old constructor use in {runner_source}."
    )
