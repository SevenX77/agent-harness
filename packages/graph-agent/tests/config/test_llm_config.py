"""Tests for LLM config parsing."""

from __future__ import annotations

from pathlib import Path

from graph_agent.config.llm_config import _parse_models, load_config


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


def test_resolve_role_copilot_chat_returns_active_model_and_fallback() -> None:
    """copilot_chat resolves to CL46T first and includes DS32R fallback."""
    cfg = load_config(_repo_root() / "config" / "llm_roles.yaml")

    role = cfg.resolve_role("copilot_chat")

    assert role.role_name == "copilot_chat"
    assert role.active_model_code == "CL46T"
    assert role.temperature == 0.7
    assert role.model_fallback is True
    assert [candidate.model_def.code for candidate in role.call_chain] == [
        "CL46T",
        "CL46T",
        "CL46T",
        "DS32R",
        "DS32R",
    ]


def test_resolve_model_cl46t_keeps_provider_order() -> None:
    """Direct CL46T resolution preserves provider order from the model registry."""
    cfg = load_config(_repo_root() / "config" / "llm_roles.yaml")

    model = cfg.resolve_model("CL46T")

    assert model.active_model_code == "CL46T"
    assert [candidate.provider_code for candidate in model.call_chain[:3]] == [
        "OC_CL_ANT",
        "OC_CL",
        "WS_LLM",
    ]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]
