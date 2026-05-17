# Configuration Reference

Complete reference for `graph_agent` configuration files.

## Overview

`graph_agent` uses two main configuration files:

- `llm_roles.yaml` — LLM role-based model selection
- `multimodal_roles.yaml` — Multimodal model configuration (optional)

Both support hot-reloading (no restart required).

---

## llm_roles.yaml

### File Structure

```yaml
models: { ... }      # Model registry
providers: { ... }   # Provider registry
roles: { ... }       # Role registry (entry point)
```

### Models Section

Each model defines capabilities and provider mappings.

| Field | Type | Description |
|-------|------|-------------|
| `code` | str | Model identifier (e.g., `CL46T`) |
| `name` | str | Human-readable name |
| `reasoning` | bool | Whether model supports reasoning content |
| `min_max_tokens` | int | Minimum max_tokens for this model |
| `fc_supported` | bool | Whether function calling is supported |
| `providers` | dict[str, str] | Provider code → model name mapping |
| `provider_options` | dict | Provider-specific options (e.g., `max_max_tokens`) |

Example:

```yaml
models:
  CL46T:
    name: "Claude Sonnet 4.6 Thinking"
    reasoning: true
    min_max_tokens: 8192
    fc_supported: true
    providers:
      OC_CL: "claude-sonnet-4-6-thinking"
      WS_LLM: "anthropic/claude-sonnet-4.6"
    provider_options:
      OC_CL:
        max_max_tokens: 8192
```

### Providers Section

Each provider defines connection details.

| Field | Type | Description |
|-------|------|-------------|
| `code` | str | Provider identifier (e.g., `OC_CL`) |
| `name` | str | Human-readable name |
| `type` | str | Provider type: `openai_compatible`, `wavespeed_any_llm`, `gemini_official`, `anthropic_compatible` |
| `api_key_env` | str | Environment variable for API key |
| `api_key_env_fallback` | str | Fallback env var if primary not set |
| `base_url` | str | Base URL for API calls |
| `llm_base_url` | str | Optional separate LLM base URL |
| `proxy_env` | str | Environment variable for proxy settings |
| `timeout` | int | Request timeout in seconds |
| `trust_env` | bool | Whether to trust system proxy env |
| `retry_strategy` | str | Retry strategy name |

Example:

```yaml
providers:
  OC_CL:
    name: "OneChats Claude"
    type: "anthropic_compatible"
    api_key_env: "OC_CLAUDE_API_KEY"
    api_key_env_fallback: "CLAUDE_API_KEY"
    base_url: "https://api.onechats.cn/v1"
    timeout: 120
    trust_env: false
    retry_strategy: "failover"
```

### Roles Section

Roles are the caller-facing entry point. Each role maps to models.

| Field | Type | Description |
|-------|------|-------------|
| `name` | str | Role name (used in SKILL.md `tier`) |
| `temperature` | float | Default temperature (0.0-1.0) |
| `model_fallback` | bool | Whether to try next model on failure |
| `active_model` | str | Primary model code |
| `system_prompt_prefix` | str | Prefix for all system prompts |
| `models` | dict | Model code → {providers: [...]} |

Example:

```yaml
roles:
  balanced:
    name: "Balanced"
    temperature: 0.7
    model_fallback: true
    active_model: "CL46T"
    system_prompt_prefix: ""
    models:
      CL46T:
        providers: ["OC_CL", "WS_LLM"]
      DS32R:
        providers: ["DS", "OC_DS"]
```

### Cross-Validation Rules

1. **Model references**: All `active_model` values must exist in `models`
2. **Provider references**: All provider codes in `models.*.providers` must exist in `providers`
3. **Role model references**: All model codes in `roles.*.models` must exist in `models`
4. **Provider lists**: Providers in role's model entry must be a subset of the model's providers

Validation errors prevent config loading and are logged with `[RoleConfig]` prefix.

### Minimal Working Example

```yaml
models:
  GPT4:
    name: "GPT-4"
    reasoning: false
    min_max_tokens: 4096
    fc_supported: true
    providers:
      OPENAI: "gpt-4"

providers:
  OPENAI:
    name: "OpenAI"
    type: "openai_compatible"
    api_key_env: "OPENAI_API_KEY"
    base_url: "https://api.openai.com/v1"
    timeout: 60

roles:
  default:
    name: "Default"
    temperature: 0.7
    model_fallback: false
    active_model: "GPT4"
    models:
      GPT4:
        providers: ["OPENAI"]
```

---

## multimodal_roles.yaml

Optional configuration for multimodal tools (image/video generation, etc.).

### File Structure

```yaml
models: { ... }      # Multimodal model registry
providers: { ... }   # Multimodal provider registry
roles: { ... }       # Multimodal role registry
```

### Models Section

| Field | Type | Description |
|-------|------|-------------|
| `code` | str | Model identifier |
| `name` | str | Human-readable name |
| `task_type` | str | Task type: `image_generation`, `video_generation`, etc. |
| `providers` | dict[str, str] | Provider code → model name mapping |
| `provider_options` | dict | Provider-specific options |

Example:

```yaml
models:
  SDXL:
    name: "Stable Diffusion XL"
    task_type: "image_generation"
    providers:
      WS_IMG: "stable-diffusion-xl"
```

### Providers Section

| Field | Type | Description |
|-------|------|-------------|
| `code` | str | Provider identifier |
| `name` | str | Human-readable name |
| `type` | str | Provider type |
| `api_key_env` | str | API key environment variable |
| `base_url` | str | API base URL |
| `proxy_env` | str | Proxy environment variable |
| `timeout` | int | Request timeout |
| `poll_interval` | int | Polling interval for async operations |

Example:

```yaml
providers:
  WS_IMG:
    name: "WaveSpeed Image"
    type: "wavespeed_any_llm"
    api_key_env: "WAVESPEED_API_KEY"
    base_url: "https://api.wavespeed.ai"
    timeout: 300
    poll_interval: 5
```

### Roles Section

| Field | Type | Description |
|-------|------|-------------|
| `name` | str | Role name |
| `model_fallback` | bool | Try next model on failure |
| `active_model` | str | Primary model code |
| `models` | dict | Model code → {providers: [...]} |

Example:

```yaml
roles:
  image_gen:
    name: "Image Generation"
    model_fallback: true
    active_model: "SDXL"
    models:
      SDXL:
        providers: ["WS_IMG"]
```

---

## Configuration Discovery

### llm_roles.yaml Search Order

1. Environment variable: `GRAPH_AGENT_ROLES_PATH`
2. Upward directory search (max 7 levels): `config/llm_roles.yaml`
3. Built-in minimal default config

### multimodal_roles.yaml Search Order

1. Environment variable: `MULTIMODAL_ROLES_CONFIG_PATH`
2. Upward directory search (max 7 levels): `config/multimodal_roles.yaml`
3. Built-in empty default (multimodal tools unavailable)

### Custom Config Path

```bash
export GRAPH_AGENT_ROLES_PATH=/path/to/custom_llm_roles.yaml
export MULTIMODAL_ROLES_CONFIG_PATH=/path/to/custom_multimodal_roles.yaml
```

---

## Hot Reload

Both configuration files support hot reloading:

- Config is checked for modification on each `get_role_config()` or `get_multimodal_role_config()` call
- Uses file `mtime_ns` for change detection
- Parse/validation errors: falls back to last valid config (logged as warning)
- File missing: falls back to built-in default (logged as warning)

Force reload:

```python
from graph_agent.config import reset_role_config, reset_multimodal_role_config

reset_role_config()           # Force reload on next get()
reset_multimodal_role_config()  # Force reload on next get()
```
