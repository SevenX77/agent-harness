from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

E2E_VENDORS_ENV = os.environ.get("LLM_E2E_VENDORS_TO_TEST", "")
E2E_VENDORS = [vendor.strip() for vendor in E2E_VENDORS_ENV.split(",") if vendor.strip()]
PARAM_VENDORS = E2E_VENDORS or ["__no_e2e_vendor__"]

VENDOR_TO_ENV_KEY = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "ark": "ARK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "wavespeed": "WAVESPEED_API_KEY",
    "qiniu": "QINIU_API_KEY",
}

VENDOR_TO_BASE_URL = {
    "openai": "https://api.openai.com",
    "anthropic": "https://api.anthropic.com",
    "deepseek": "https://api.deepseek.com",
    "gemini": "https://generativelanguage.googleapis.com",
    "ark": "https://ark.cn-beijing.volces.com/api/v3",
    "openrouter": "https://openrouter.ai/api/v1",
    "wavespeed": "https://llm.wavespeed.ai/v1",
}

VENDOR_TO_PROVIDER_TYPE = {
    "openai": "openai_compatible",
    "anthropic": "anthropic_compatible",
    "deepseek": "openai_compatible",
    "gemini": "google_genai",
    "ark": "openai_compatible",
    "openrouter": "openai_compatible",
    "wavespeed": "openai_compatible",
    "qiniu": "openai_compatible",
}


@pytest.mark.skipif(
    not E2E_VENDORS,
    reason="e2e skipped without LLM_E2E_VENDORS_TO_TEST env (set CSV like 'openai,deepseek')",
)
@pytest.mark.parametrize("vendor", PARAM_VENDORS)
def test_round3_probe_e2e_per_vendor(
    vendor: str,
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PUT credential, POST Test, then verify probe results are persisted."""

    monkeypatch.setenv("HOME", str(tmp_path))
    api_key_env = VENDOR_TO_ENV_KEY.get(vendor)
    assert api_key_env, f"No env mapping for vendor={vendor}"
    api_key = os.environ.get(api_key_env)
    assert api_key, f"Set {api_key_env} env var to run e2e for vendor={vendor}"

    provider_type = VENDOR_TO_PROVIDER_TYPE.get(vendor)
    assert provider_type, f"No provider_type mapping for vendor={vendor}"
    provider_id = f"{vendor}-e2e"
    base_url = VENDOR_TO_BASE_URL.get(vendor)

    put_provider: dict[str, Any] = {
        "id": provider_id,
        "name": f"{vendor} e2e",
        "api_key": api_key,
        "provider_type": provider_type,
    }
    if base_url:
        put_provider["base_url"] = base_url
    put_response = client.put("/api/llm/credentials", json={"providers": [put_provider]})
    assert put_response.status_code == 200, f"PUT failed: {put_response.text}"

    test_body = {
        "id": provider_id,
        "provider_type": provider_type,
        "api_key": api_key,
    }
    if base_url:
        test_body["base_url"] = base_url
    test_response = client.post("/api/llm/providers/test", json=test_body)
    assert test_response.status_code == 200, f"Test failed: {test_response.text}"
    body = test_response.json()

    assert body["status"] == "ok", f"vendor={vendor} test status not ok: {body}"
    assert body["available_sdks"], f"vendor={vendor} no available_sdks"
    assert body["available_models"], f"vendor={vendor} no available_models"

    get_response = client.get("/api/llm/credentials")
    assert get_response.status_code == 200, f"GET failed: {get_response.text}"
    provider_state = next(
        (provider for provider in get_response.json()["providers"] if provider["id"] == provider_id),
        None,
    )
    assert provider_state, f"Provider {provider_id} missing after PUT"
    assert provider_state["available_sdks"] == body["available_sdks"]
    assert provider_state["available_models"] == body["available_models"]
