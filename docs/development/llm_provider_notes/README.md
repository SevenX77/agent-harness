---
status: Archived Reference
target_goal: "Provider facts for Agent import drafts and human endpoint setup"
linked_specs:
  - .kiro/specs/llm-provider-intelligence-v2/design.md
  - docs/development/LLM_MODEL_CONFIGURATION_FLOW.md
---

# LLM Provider Notes Archive

This directory contains provider facts that can help a user or an Agent import workflow propose endpoint and route drafts.

It is not a runtime source of truth. Studio runtime code must not read these files to construct endpoints, routes, roles, credentials, or canonical aliases.

Active runtime state lives in:

- `~/.studio/llm_credentials.json` for V4 endpoints, routes, and runtime policy.
- `config/llm_roles.yaml` for V2 model profiles and role fallback chains.
- `config/llm_canonical_rules.yaml` for explicit canonical aliases.

## Supported Protocol Families

| Protocol | Auth pattern | Common model-list path |
|---|---|---|
| `openai_compatible` | `Authorization: Bearer <key>` | `/v1/models` |
| `anthropic_compatible` | `x-api-key` + `anthropic-version` | `/v1/models` or provider-specific |
| `google_genai` | API key or Google-compatible auth | `/v1beta/models` |

One vendor can expose multiple endpoint records when protocol or base URL differs. For example, Qiniu can be represented as `qiniu-openai` and `qiniu-anthropic`, each with its own routes.

## Files

- [`_template.md`](./_template.md) — provider note template.
- [`anthropic.md`](./anthropic.md) — Anthropic official and compatible notes.
- [`openai.md`](./openai.md) — OpenAI official and Azure notes.
- [`gemini.md`](./gemini.md) — Gemini native and OpenAI-compatible notes.
- [`openrouter.md`](./openrouter.md) — OpenRouter aggregation notes.
- [`qiniu.md`](./qiniu.md) — Qiniu dual-endpoint notes.

## Maintenance Rules

1. Keep these files as factual onboarding notes only.
2. Do not add code paths that parse this directory at runtime.
3. Do not treat moving aliases such as `~...latest` as canonical aliases here.
4. Promote only deliberate, tested aliases to `config/llm_canonical_rules.yaml`.
