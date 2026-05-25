---
status: Draft
target_goal: "Define the LLM Provider Intelligence V2 hard-cut bootstrap and recovery path"
linked_specs:
  - .kiro/specs/llm-provider-intelligence-v2/requirements.md
  - .kiro/specs/llm-provider-intelligence-v2/design.md
  - .kiro/specs/llm-provider-intelligence-v2/tasks.md
linked_examples:
  - docs/development/examples/llm_credentials.v4.example.json
  - docs/development/examples/llm_roles.v2.example.yaml
---

# Credentials V4 Bootstrap

LLM Provider Intelligence V2 is a hard cut from the old `models/providers/roles` short-code config to an explicit endpoint/route registry.

The runtime source files are:

- `~/.studio/llm_credentials.json`: active endpoint credentials, physical routes, and `runtime_policy`.
- `config/llm_roles.yaml`: model profiles and role fallback chains by exact `route_id`.
- `~/.studio/llm_import_drafts.json` or backend job storage: transient Agent import drafts.

The active credentials file must use `schema_version: 4`. The roles file must use `schema_version: 2`.

## Startup Behavior

### Missing V4 Credentials File

If `~/.studio/llm_credentials.json` is missing, Studio Backend should not crash. It returns an empty registry plus a setup-required status so the UI can guide the user to create endpoints.

Expected empty runtime shape:

```json
{
  "schema_version": 4,
  "provider_endpoints": {},
  "provider_routes": {},
  "runtime_policy": {
    "provider_down_ttl_seconds": 60,
    "probe_timeout_seconds": 5,
    "token_escalation_rounds": 2
  }
}
```

Engine execution cannot start a role until the registry has at least one route referenced by that role.

### Legacy V3 Or Short-Code Config Detected

If the backend detects the old provider list or old `models/providers/roles` shape, it must fail with an actionable schema error. It must not load a legacy schema reader.

Recommended error payload:

```json
{
  "code": "llm_config_legacy_schema",
  "message": "LLM Provider Intelligence V2 requires credentials schema_version 4 and roles schema_version 2.",
  "docs_path": "docs/development/CREDENTIALS_V4_BOOTSTRAP.md"
}
```

Recovery is explicit:

1. Back up the old files.
2. Create a V4 credentials file from `docs/development/examples/llm_credentials.v4.example.json`.
3. Create a V2 roles file from `docs/development/examples/llm_roles.v2.example.yaml`.
4. Replace placeholder API keys and route IDs with real local values.
5. Start Studio and test each endpoint.
6. Probe routes used by roles with `error` lint requirements.

## Example Files

Use the checked-in examples as shape references only:

- [llm_credentials.v4.example.json](examples/llm_credentials.v4.example.json)
- [llm_roles.v2.example.yaml](examples/llm_roles.v2.example.yaml)

Do not copy real API keys into committed files. The `api_key` values in examples are placeholders and must be replaced only in local untracked/user config.

## Endpoint Naming

Use lowercase endpoint IDs with the pattern `<brand>-<protocol-or-channel>`.

Examples:

| Provider meaning | endpoint_id |
|---|---|
| Anthropic official API | `anthropic-official` |
| OpenAI official API | `openai-official` |
| OneChats OpenAI-compatible endpoint | `onechats-openai` |
| OneChats Anthropic-compatible endpoint | `onechats-anthropic` |
| WaveSpeed Any-LLM endpoint | `wavespeed-anyllm` |
| Qiniu OpenAI-compatible endpoint | `qiniu-openai` |
| Qiniu Anthropic-compatible endpoint | `qiniu-anthropic` |

Old uppercase short codes such as `OC_CL`, `WS_LLM`, and `GM_OFF` are not runtime identifiers in V2.

## Seed And Cutover Naming

When converting seed examples, docs, or local prototype configs, treat old labels as input hints only. Write new runtime files with lowercase endpoint IDs and exact route IDs.

| Old source label | V2 endpoint_id | Example route_id | Notes |
|---|---|---|---|
| `ANTHROPIC_OFFICIAL`, `ANTHROPIC`, `CLAUDE_*` | `anthropic-official` | `anthropic-official:claude-opus-4-7-thinking` | Official Anthropic protocol endpoint. |
| `OPENAI_OFFICIAL`, `OPENAI`, `GPT_*` | `openai-official` | `openai-official:gpt-5` | Official OpenAI-compatible endpoint. |
| `GM_OFF`, `GEMINI_*` | `gemini-official` | `gemini-official:gemini-3-1-pro` | Gemini native endpoint. |
| `OC_CL`, OneChats Claude labels | `onechats-anthropic` | `onechats-anthropic:claude-sonnet-4-6` | OneChats Anthropic-compatible endpoint. |
| `OC_OPENAI`, OneChats GPT labels | `onechats-openai` | `onechats-openai:gpt-5` | OneChats OpenAI-compatible endpoint. |
| `WS_LLM`, WaveSpeed labels | `wavespeed-anyllm` | `wavespeed-anyllm:anthropic-claude-opus-4-7` | WaveSpeed aggregation endpoint. |
| Qiniu OpenAI labels | `qiniu-openai` | `qiniu-openai:deepseek-r1` | Qiniu OpenAI-compatible endpoint. |
| Qiniu Anthropic labels | `qiniu-anthropic` | `qiniu-anthropic:anthropic-claude-opus-4-7` | Qiniu Anthropic-compatible endpoint. |

## Hard-Cut Rules

- Runtime must not read API keys from `.env`.
- Runtime must not parse old role short-code maps.
- Runtime must not keep old Studio DTOs or compatibility wrappers.
- `ModelProfile` is authoring-time only; roles execute saved `fallback_chain[*].route_id`.
- Capability probing may block invalid configs or fail fast, but it must not dynamically replace the chosen route.
