"""Tests for LLM config parsing."""

from __future__ import annotations

from graph_agent.config.llm_config import _parse_models


def test_parse_models_reads_max_input_tokens() -> None:
    """ModelDef.max_input_tokens is populated from yaml when present."""
    raw = {
        "BIG_MODEL": {
            "name": "Big Context Model",
            "max_input_tokens": 200000,
            "providers": {"PROV_X": "model-x"},
        }
    }

    result = _parse_models(raw)

    assert result["BIG_MODEL"].max_input_tokens == 200000


def test_parse_models_max_input_tokens_default_none() -> None:
    """ModelDef.max_input_tokens stays None when not specified."""
    raw = {
        "SMALL_MODEL": {
            "name": "Small Model",
            "providers": {"PROV_X": "model-x"},
        }
    }

    result = _parse_models(raw)

    assert result["SMALL_MODEL"].max_input_tokens is None
