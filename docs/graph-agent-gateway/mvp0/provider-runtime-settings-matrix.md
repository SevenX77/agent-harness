# Provider Runtime Settings Matrix

Archived note: this MVP0 matrix is retained as historical provider-runtime context. Current MVP1 module docs and the client-layer decision record are the active source of truth for invocation/runtime alignment.

Status: Draft, last verified 2026-05-25.

This matrix documents how Gateway maps the fixed normalized `RuntimeSettings` schema to provider protocols. Capabilities describe support, bounds, and defaults; user runtime settings remain role/profile route-entry data.

## Normalized Settings

| Normalized key | Type | Purpose |
|---|---:|---|
| `temperature` | number | Sampling temperature. |
| `top_p` | number | Nucleus sampling. |
| `max_output_tokens` | integer | Provider output-token cap. |
| `stop_sequences` | string list | Provider stop strings. |
| `seed` | integer | Deterministic sampling seed when supported. |
| `tool_choice` | string/object | Tool-call selection policy. |
| `parallel_tool_calls` | boolean | Parallel tool-call allowance. |
| `structured_output` | object | JSON object/schema response format. |
| `reasoning.enabled` | boolean | Provider thinking/reasoning mode. |
| `reasoning.effort` | string | Provider effort level when exposed as enum. |
| `reasoning.budget_tokens` | integer | Manual thinking/reasoning budget. |

## Protocol Mapping

| Protocol | Adapter | Request mapping | Important provider differences |
|---|---|---|---|
| `anthropic_compatible` | `Anthropic.messages.create` | `max_output_tokens` -> `max_tokens`; `stop_sequences` -> `stop_sequences`; `tool_choice` -> Anthropic tool choice; `reasoning.enabled/budget_tokens` -> `thinking`. | Manual extended thinking requires `budget_tokens >= 1024` and budget lower than `max_tokens`; current code prefers adaptive thinking for supported Claude 4.6/4.7 families and falls back to manual where allowed. |
| `openai_compatible` | `OpenAI.chat.completions.create` | `max_output_tokens` -> `max_tokens`; `stop_sequences` -> `stop`; `structured_output` -> `response_format`; `reasoning.effort` -> `reasoning_effort`. | OpenAI-compatible providers differ on `reasoning_effort`, `seed`, and structured output support. Capability descriptors must come from probe/doc metadata per route. |
| `google_genai` | `google.genai.Client.models.generate_content` | `max_output_tokens`, `temperature`, `top_p`, `stop_sequences`, `seed` -> generation config; `structured_output` -> JSON response config; `reasoning.effort/budget_tokens` -> `thinking_config`. | Gemini model families differ between thinking budget and thinking level. Gateway stores only normalized role settings; adapter owns provider names. |
| `ark_runtime` | `volcenginesdkarkruntime.Ark.chat.completions.create` | OpenAI-shaped chat args through Ark official SDK. | Ark OpenAI-compatible and Ark official SDK can expose different behavior/capabilities for the same model endpoint, so they are separate protocols and routes. |

## Runtime Defaults

Resolver default order is:

1. Route entry setting.
2. Copied model-profile default (`runtime_settings_source: profile_default`).
3. Route capability default.
4. Protocol default.
5. Studio safe default.

Each effective value is emitted as `effective_runtime_settings[key] = { value, source, message }` in response metadata, tracing fallback events, and registry role metadata.

## Live Observation

2026-05-25 local smoke used a temporary registry snapshot with:

- first route: `dead-net:claude-haiku`, Anthropic-compatible endpoint at `127.0.0.1:9`, expected network failure.
- fallback route: `anthropic-official:claude-haiku-4-5-20251001`, real Anthropic API key from local Studio credentials.

Result:

- resolver selected role `graph_agent`.
- first route emitted `llm_fallback` with `fallback_decision=fallback_allowed`.
- second route returned content `OK`.
- response metadata included route ID, provider model ID, and effective runtime settings.

The raw non-secret observation is recorded in `temp/llm-provider-intelligence-v2-real-e2e-2026-05-25.json`.

## Source Links

- Anthropic Messages and extended thinking docs: https://docs.anthropic.com/
- OpenAI API docs for chat/responses and reasoning effort: https://platform.openai.com/docs/
- Google GenAI SDK and Gemini thinking docs: https://ai.google.dev/gemini-api/docs
- Volcengine Ark Python SDK docs: https://www.volcengine.com/docs/82379/1544136?lang=zh
