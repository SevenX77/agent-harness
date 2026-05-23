---
status: Living
target_goal: "Studio LLM provider configuration should be explicit, testable, and traceable"
linked_code_paths:
  - apps/studio/frontend/src/components/studio/settings/api-keys/ApiKeysTab.tsx
  - apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx
  - apps/studio/backend/app/routers/llm.py
  - apps/studio/backend/app/services/llm_credentials.py
  - apps/studio/backend/app/services/llm_provider_test.py
---

# LLM Model Configuration Flow

## 1. Provider input

When we onboard a provider or proxy, collect these facts separately:

- **API key**: the secret used for auth. Some providers reuse one key across multiple protocol endpoints.
- **Protocol**: one of `openai_compatible`, `anthropic_compatible`, or `google_genai`.
- **Base URL**: the endpoint root for that protocol. One provider may expose multiple base URLs.
- **Model catalog URL**: where users can see model IDs and availability. This may be a web page, not the API endpoint.
- **Docs URL**: protocol/auth reference, including required headers and known quirks.
- **Model ID shape**: plain IDs like `deepseek-r1`, vendor-prefixed IDs like `anthropic/claude-opus-4.7`, or provider-specific aliases.

Do not treat "provider brand" and "protocol endpoint" as the same thing. A brand such as Qiniu can have both an OpenAI-compatible endpoint and an Anthropic-compatible endpoint.

## 2. API Keys page

The API Keys page stores one provider card per protocol endpoint:

- `id`: stable local database key. Changing name, key, URL, or protocol must not change this ID.
- `name`: display label, for example `QiNiu-OpenAI` or `QiNiu-Anthropic`.
- `provider_type`: selected protocol. This controls request shape and auth headers.
- `api_key`: provider secret.
- `base_url`: endpoint root for the selected protocol.

If one provider gives two URLs, create two provider cards with the same API key:

| Card name | Protocol | Base URL |
|---|---|---|
| `QiNiu-OpenAI` | `openai_compatible` | `https://api.qnaigc.com/v1` |
| `QiNiu-Anthropic` | `anthropic_compatible` | `https://anthropic.qnaigc.com` |

The UI must display exactly the stored document state. For test outcomes, the cache key is:

```text
api_key + base_url + provider_type
```

If any of those values change, the visible status, SDK/protocol chips, and available models should fall back to the initial state unless the cached result for the new exact parameter tuple already exists.

Current credential storage file:

```text
~/.studio/llm_credentials.json
```

## 3. Test button semantics

The primary Test action should answer these questions, in this order:

1. **Can the API key and Base URL authenticate?**
2. **Can we retrieve a model catalog from this endpoint?**
3. **Which model IDs are available for role configuration?**
4. **Can we confirm a generation/chat protocol with a tiny request?** This is useful but diagnostic. It should not hide a valid model list.

The returned result should be organized as:

- `status`: connection/auth result for the selected parameter tuple.
- `available_models`: normalized model IDs from the endpoint or provider docs fallback.
- `available_sdks`: confirmed or selected protocol diagnostics. Do not use this list as the source of role model options.
- `error_code` and `message`: machine code plus human-readable explanation for UI toasts.

Manual model probing is a fallback:

- It is used when automatic model listing is unavailable, incomplete, or the user wants to verify one exact model ID.
- It sends a minimal one-token request for each entered model ID.
- It returns per-model statuses such as `Available`, `Model not found`, `Invalid API key`, `Rate limited`, `Network error`, or `Test failed`.
- Successful manual IDs are appended to the provider's available model list.

## 4. LLM Roles page

The LLM Roles page should not ask users to type raw API credentials. It should consume tested API Keys providers:

- Provider options come from the credential document's provider cards.
- Model options come from `available_models` for the selected provider.
- The value written into a role is the exact model ID returned by the provider, not a normalized display alias.
- If a provider has no available models, the role UI can show it as unavailable and point the user back to API Keys Test/manual probing.

Recommended role selection flow:

1. User tests provider endpoint on API Keys.
2. Backend persists `available_models` for that provider ID and parameter tuple.
3. LLM Roles reads providers and model lists from the credentials response.
4. User picks role, provider chain order, and model ID.
5. Runtime resolves provider ID to key/base URL/protocol and calls the selected adapter.

## 5. Current Qiniu note

`apps/studio/backend/app/data/llm_providers/qiniu.md` was originally added in commit `378c6795` by `SevenX77` on `2026-05-19`. It described only the older/default OpenAI-compatible profile. Current observed Qiniu configuration needs two endpoint profiles, so the doc now records both Base URLs and the Studio rule: create separate provider cards per protocol endpoint.
