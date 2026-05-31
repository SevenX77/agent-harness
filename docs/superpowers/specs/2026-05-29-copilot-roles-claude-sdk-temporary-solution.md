# Temporary Solution: Copilot Roles and Claude SDK Compatibility

Date: 2026-05-29
Status: Temporary Implementation Plan

## Overview

This document outlines a lightweight, drop-in solution to handle Claude Agent SDK compatibility for Copilot roles. It addresses the issue of hardcoded provider environment mappings in `copilot.py` without requiring complex changes to the underlying LLM registry database schema.

The core strategy relies on:
1. **Filtering by Capability (`method_id`)**: Utilizing existing provider test results to only present Anthropic-compatible routes to the user.
2. **Adapter/Strategy Pattern**: Extracting environment and Base URL manipulation into pluggable strategy functions, selected manually by the user for third-party endpoints or inferred automatically for official endpoints.

## 1. Adapter Strategy Implementation

Introduce a simple strategy registry to handle vendor-specific Anthropic compatibility layers (e.g., DeepSeek's `/anthropic` endpoint, Ark's `/api/compatible`).

```python
# app/services/copilot_adapters.py

from typing import Any, Literal

AdapterType = Literal["standard_anthropic", "deepseek_compatible", "ark_compatible"]

def _build_standard_anthropic(base_url: str, api_key: str, model_id: str) -> tuple[str, dict[str, str]]:
    return base_url, {"ANTHROPIC_API_KEY": api_key}

def _build_deepseek_compatible(base_url: str, api_key: str, model_id: str) -> tuple[str, dict[str, str]]:
    normalized_url = base_url.rstrip("/")
    if normalized_url.endswith("/v1"):
        normalized_url = normalized_url[:-3]
    if not normalized_url.endswith("/anthropic"):
        normalized_url += "/anthropic"
    return normalized_url, {
        "ANTHROPIC_AUTH_TOKEN": api_key, 
        "ANTHROPIC_MODEL": model_id
    }

def _build_ark_compatible(base_url: str, api_key: str, model_id: str) -> tuple[str, dict[str, str]]:
    normalized_url = base_url.rstrip("/")
    if normalized_url.endswith("/api/v3"):
        normalized_url = normalized_url[:-7]
    if not normalized_url.endswith("/api/compatible"):
        normalized_url += "/api/compatible"
    return normalized_url, {
        "ANTHROPIC_AUTH_TOKEN": api_key, 
        "ANTHROPIC_MODEL": model_id
    }

ADAPTERS = {
    "standard_anthropic": _build_standard_anthropic,
    "deepseek_compatible": _build_deepseek_compatible,
    "ark_compatible": _build_ark_compatible,
}

def resolve_adapter_runtime(adapter_id: str, original_base_url: str, api_key: str, model_id: str) -> tuple[str, dict[str, str]]:
    """Returns (modified_base_url, injected_env_dict)"""
    builder = ADAPTERS.get(adapter_id, _build_standard_anthropic)
    return builder(original_base_url, api_key, model_id)
```

## 2. Refactoring Runtime Resolution

Modify `_resolve_route_runtime` in `apps/studio/backend/app/services/copilot.py` to use the new adapter registry instead of inline if-else statements.

```python
# In app/services/copilot.py
from app.services.copilot_adapters import resolve_adapter_runtime

def _resolve_route_runtime(route: ResolvedRoute, credential_provider: CredentialProviderProtocol, user_selected_adapter_id: str | None = None) -> tuple[str, str | None, dict[str, str]]:
    api_key = credential_provider.get(route.credential_ref).get_secret_value().strip()
    base_url = route.base_url.strip() or None
    
    # 1. Determine Adapter
    adapter_id = "standard_anthropic" 
    
    if user_selected_adapter_id:
        adapter_id = user_selected_adapter_id
    else:
        # Fallback to inference for official endpoints or legacy configs
        if route.call_method_id == "ark_anthropic_messages":
            adapter_id = "ark_compatible"
        elif route.call_method_id == "deepseek_anthropic_messages":
            adapter_id = "deepseek_compatible"
        elif route.call_method_id == "anthropic_messages":
            adapter_id = "standard_anthropic"
            
    # 2. Build configuration
    final_base_url, env_overrides = resolve_adapter_runtime(
        adapter_id=adapter_id,
        original_base_url=base_url or "https://api.anthropic.com",
        api_key=api_key,
        model_id=route.provider_model_id
    )
    
    return api_key, final_base_url, env_overrides
```

## 3. UI Filtering Endpoint

Add a new endpoint to provide pre-filtered dropdown options for the Copilot setup UI, ensuring only compatible configurations are selectable.

```python
# In app/routers/copilot.py
from fastapi import APIRouter
from app.services.llm_credentials import load_credentials

# Whitelist of methods proven to accept Anthropic-shaped requests
CLAUDE_SDK_COMPATIBLE_METHODS = {
    "anthropic_messages",
    "deepseek_anthropic_messages",
    "ark_anthropic_messages"
}

@router.get("/api/copilot/available-endpoints")
async def get_available_copilot_endpoints(model_keyword: str | None = None):
    """
    Returns valid Endpoint/Route combinations for Claude SDK.
    model_keyword: Used to filter for specific slots (e.g., 'opus', 'deepseek-v4').
    """
    credentials = load_credentials()
    available_options = []
    
    for route_id, route in credentials.provider_routes.items():
        if route.status != "verified":
            continue
            
        if model_keyword and model_keyword.lower() not in route.provider_model_id.lower():
            continue
            
        endpoint = credentials.provider_endpoints.get(route.endpoint_id)
        if not endpoint:
            continue
            
        # Core Filter: Look for a verified Anthropic-compatible profile
        compatible_profile = next(
            (p for p in route.verified_profiles if p.status == "ready" and p.method_id in CLAUDE_SDK_COMPATIBLE_METHODS), 
            None
        )
                
        if compatible_profile:
            # Third-party endpoints require manual adapter selection in UI
            needs_manual_adapter = endpoint.provider_kind != "official"
            
            available_options.append({
                "endpoint_id": endpoint.endpoint_id,
                "endpoint_name": endpoint.display_name,
                "route_id": route.route_id,
                "model_id": route.provider_model_id,
                "needs_manual_adapter": needs_manual_adapter,
                "inferred_method": compatible_profile.method_id 
            })
            
    return {"options": available_options}
```

## UX Workflow Result

1.  User selects the "DeepSeek V4 Pro" slot setup.
2.  UI calls `/api/copilot/available-endpoints?model_keyword=deepseek`.
3.  Pure OpenAI endpoints are naturally omitted because they lack a verified profile with an Anthropic compatible `method_id`.
4.  User selects an endpoint (e.g., a custom proxy).
5.  Because `needs_manual_adapter=True`, the UI prompts the user to select their provider's dialect ("Standard", "DeepSeek-style", or "Ark-style").
6.  The UI saves this `adapter_id` in the `CopilotRoleSettings.sdk_runtime` configuration.
