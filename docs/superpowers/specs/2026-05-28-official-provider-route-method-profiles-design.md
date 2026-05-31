# Official Provider Route Method And Profile Design

Status: Draft for review  
Date: 2026-05-28  
Scope: Studio API Keys Test flow, backend route generation, LLM Roles model availability, and official-provider runtime dispatch.

## Goal

The API Keys page should have one official-provider action named `Test` in the former `Get Models` position. That action must do both jobs:

1. Fetch the provider catalog.
2. Use catalog facts plus official-provider rules to test every plausible callable method/profile for every listed model.

The output is not "models were listed". The output is a verified route/profile graph:

- Which language/reasoning models are ready for LLM Roles.
- Which call method each model/profile must use.
- Which provider-specific mapper turns generic Studio intent such as `reasoning.enabled=true` into the actual request payload.
- Which fallback method/profile is available if the preferred method fails.
- Which generated multimodal, embedding, translation, video, 3D, audio, or other non-language assets belong in a separate capability library instead of LLM Roles.

## Source Evidence

This design is grounded in the live probe artifacts from 2026-05-28:

- `temp/official-provider-route-method-combined-2026-05-28-131811.json`
- `temp/official-provider-route-method-analysis-2026-05-28-131811.md`
- `temp/official-provider-profile-combinations-combined-2026-05-28-152620.json`
- `temp/official-provider-profile-combinations-analysis-2026-05-28-152620.md`

Headline probe results:

| Metric | Value |
|---|---:|
| Official providers tested | 5 / 5 |
| Catalog models listed | 296 |
| Probe-level method result rows | 863 |
| OK probe-level method rows | 464 |
| Verified LLM route records | 460 |
| Unique verified LLM models | 123 |
| Capability library records | 87 |
| Profile-combination rows | 299 |
| OK profile-combination rows | 231 |

Probe-level method IDs are intentionally more granular than the runtime/storage design. The probes tested 25 method IDs and 24 had at least one OK result. For production, those collapse into base call methods plus verified profiles.

## Key Distinction

Catalog, route, call method, and profile are different facts.

| Term | Meaning | Example |
|---|---|---|
| Catalog model | A model ID returned by the provider list endpoint. It proves discoverability only. | `gpt-5-pro`, `claude-opus-4-7`, `doubao-seed-2-0-pro-260215` |
| Provider endpoint | Credential, base URL, provider kind, and account-level test status. | OpenAI API key at `https://api.openai.com/v1` |
| Base call method | Official API family used to invoke a model. It maps to a concrete endpoint path and auth/header convention. | `openai_responses`, `anthropic_messages`, `ark_chat` |
| Verified profile | A tested combination of model, base call method, capability, and provider-specific mapper. | `claude-opus-4-7` + `anthropic_messages` + `thinking` + `anthropic_adaptive_thinking` |
| Provider route | A Studio-callable model entry that owns verified language profiles and fallback order. | `anthropic-official:claude-opus-4-7` |
| Capability library record | A discovered or verified non-LLM-role capability. | OpenAI image generation model, Ark Seedream image model, Gemini embedding model |

The existing `ProviderEndpoint` model is close to the account-level endpoint concept. The existing `ProviderRoute` can physically hold extra data in `capabilities` and `metadata`, but it is not expressive enough as a first-class schema because it does not define verified profiles, method fallback, or mapper IDs.

## Recommended Data Model

### ProviderEndpoint

Keep `ProviderEndpoint` as the account connection:

- `endpoint_id`
- `provider_kind`
- `protocol`
- `base_url`
- credential fields
- provider-level `status`
- `last_test_at`
- `last_test_message`
- account/catalog metadata

Do not duplicate credentials per call method. Call methods are children of the account connection.

### OfficialCallMethod

Add a first-class registry entry for official provider API families. This may live in code as a static registry plus serialized snapshots in endpoint metadata.

Required fields:

| Field | Purpose |
|---|---|
| `method_id` | Stable ID such as `openai_responses` or `anthropic_messages`. |
| `provider_kind` | `openai`, `anthropic`, `gemini`, `deepseek`, `ark`. |
| `api_family` | Human/API grouping such as Responses, Messages, Chat Completions, GenerateContent. |
| `path_template` | Relative path or provider-specific operation. |
| `supported_capability_kinds` | Candidate capabilities this method can test. |
| `request_mapper_id` | Default mapper used for generic Studio input. |
| `response_mapper_id` | Mapper used to normalize provider output. |
| `default_rank` | Provider-level preference before model-specific probe results. |

The base language call methods confirmed by probes are:

| Provider | Base call methods for LLM route use |
|---|---|
| Anthropic | `anthropic_messages` |
| OpenAI | `openai_responses`, `openai_chat_completions` |
| Gemini | `gemini_generate_content` |
| DeepSeek | `deepseek_chat_completions`, `deepseek_anthropic_messages` |
| Ark | `ark_chat`, `ark_responses`, `ark_anthropic_messages` |

Additional non-LLM-role methods belong to the capability library, for example `gemini_embed_content`, Ark translation, Ark/OpenAI/Gemini generated media, audio, video, embedding, moderation, realtime, and 3D families. Official provider catalog rows must keep `candidate_methods` even when they are excluded from LLM Roles.

### VerifiedProfile

Add verified profiles under a route. A route is model-level; profiles are invocation modes.

Suggested shape:

```json
{
  "profile_id": "thinking:anthropic_messages:adaptive",
  "capability": "thinking",
  "input_modalities": ["text"],
  "output_modalities": ["text"],
  "method_id": "anthropic_messages",
  "request_mapper_id": "anthropic_thinking_adaptive",
  "status": "ready",
  "default": true,
  "fallback_rank": 1,
  "runtime_overrides": {
    "reasoning": {
      "enabled": true,
      "effort": "low"
    }
  },
  "probe": {
    "tested_at": "2026-05-28T15:26:20Z",
    "latency_ms": 1959,
    "source_artifact": "temp/official-provider-profile-combinations-combined-2026-05-28-152620.json"
  }
}
```

Important rules:

- Store only profile-specific facts and mapper IDs.
- Do not store generic implementation details such as provider-specific token parameter names on every route.
- The mapper owns translation from Studio generic settings to provider payload parameters.
- Health and fallback should be tracked at profile granularity, not just route granularity.

Recommended identity key:

```text
endpoint_id + provider_model_id + method_id + profile_id + request_mapper_id
```

### ProviderRoute

Keep route identity model-level:

- `route_id`
- `endpoint_id`
- `provider_model_id`
- `canonical_id`
- `status`
- normalized capabilities summary for fast filtering
- `verified_profiles`
- route-level fallback policy
- catalog snapshot pointer

`ProviderRoute.status` should be ready if at least one language/text-output profile is ready. It should not become ready because an image/video generation model was listed.

### CapabilityLibraryRecord

Generated multimodal and non-role assets should not appear in LLM Roles. They need their own library records:

- image generation
- video generation
- audio generation/TTS/transcription
- embedding
- translation
- realtime
- moderation
- 3D generation
- provider-specific tool-only surfaces

These records can start as `catalog_candidate` and become `ready` only after their own official protocol probe succeeds.

## Test Button Flow

The single `Test` button should run this backend workflow:

1. Validate/save the endpoint draft enough to use credentials.
2. Fetch the provider catalog with the official model-list method.
3. Store the raw catalog snapshot and normalized catalog model rows.
4. Classify candidate capabilities from provider facts:
   - OpenAI: model ID families plus known official surfaces.
   - Anthropic: listed Claude model families.
   - Gemini: `supported_actions` from Models API.
   - DeepSeek: native OpenAI-compatible list plus official Anthropic-compatible surface.
   - Ark: official catalog metadata and curated model-family capability rules.
5. Build candidate profile probes for every plausible language route and capability-library record.
6. Probe official candidates first.
7. If a probe fails, classify the failure and retry only useful alternatives:
   - Same capability with corrected request shape.
   - Alternate official base method for the same capability.
   - Provider-specific compatibility method if documented and working.
8. Persist:
   - endpoint/account status,
   - catalog snapshot,
   - verified language routes,
   - verified profiles and fallback order,
   - capability library records,
   - non-OK attempts with human-readable causes.
9. Return a frontend-safe result summary for the API Keys page.

This replaces the old split between `Get Models` and endpoint test. The UI should still present the conceptual difference: catalog was fetched, routes were tested, and non-language capability candidates were separated.

## Runtime Selection Flow

Runtime should select by user/role intent, not by a hard-coded provider protocol.

1. Role request declares generic intent:
   - text chat,
   - image input,
   - reasoning/thinking off/preferred/required,
   - effort/budget preference,
   - output modality requirements.
2. Route resolver filters verified profiles that satisfy the intent.
3. Resolver sorts by:
   - explicit role fallback order,
   - verified default profile,
   - provider/method preference,
   - latency/health,
   - downgrade policy.
4. Runtime invokes the profile's base call method.
5. Request mapper converts generic runtime settings to provider-specific payload.
6. Response mapper normalizes provider output.
7. If invocation fails in a retryable way, fallback moves to the next verified profile that still satisfies the intent.

If a role requires thinking, fallback must not silently downgrade to no-thinking unless the role explicitly allows that downgrade.

## Thinking Example: Claude Opus

A Claude Opus route should not be forced to choose one of four probe-level Anthropic method IDs. It should reference one base call method, `anthropic_messages`, with multiple verified profiles.

Example for a newer Opus model such as `claude-opus-4-7`:

| Profile | Base method | Mapper | Runtime meaning |
|---|---|---|---|
| `text` | `anthropic_messages` | `anthropic_text` | No `thinking` field in the request. |
| `thinking_adaptive` | `anthropic_messages` | `anthropic_thinking_adaptive` | Send `thinking: {"type": "adaptive"}` and provider-specific effort config. |
| `image_input` | `anthropic_messages` | `anthropic_image_input` | Send image content blocks. |
| `image_input_thinking_adaptive` | `anthropic_messages` | `anthropic_image_input_thinking_adaptive` | Send image content plus adaptive thinking payload. |

Example for older/manual-thinking Claude models:

| Profile | Base method | Mapper | Runtime meaning |
|---|---|---|---|
| `text` | `anthropic_messages` | `anthropic_text` | No `thinking` field. |
| `thinking_manual` | `anthropic_messages` | `anthropic_thinking_manual_budget` | Send `thinking: {"type": "enabled", "budget_tokens": N}` and ensure budget is below max output. |
| `image_input_thinking_manual` | `anthropic_messages` | `anthropic_image_input_thinking_manual_budget` | Send image content plus manual thinking budget. |

Therefore, when the user preference says "enable thinking", the backend can inspect route profiles:

- If `thinking_adaptive` is verified and preferred, choose it.
- Else if `thinking_manual` is verified, choose it with budget defaults/limits.
- Else if thinking is required, reject the route for that role.
- Else if thinking is only preferred, fallback to the normal `text` profile if allowed.

The current storage can carry some of this in `capabilities` and `metadata`, but it cannot express this cleanly as first-class route behavior. The schema should add verified profiles or a typed equivalent.

## Provider Findings And Defaults

### Anthropic

Confirmed base method:

- `anthropic_messages`

Probe-level OK method counts:

| Probe-level method | OK |
|---|---:|
| `anthropic_messages_text` | 7 |
| `anthropic_messages_image_input` | 7 |
| `anthropic_messages_thinking` | 6 |
| `anthropic_messages_thinking_adaptive` | 1 |

Profile-combination follow-up showed adaptive thinking works for 3 newer Claude models and image plus thinking also works:

| Profile method | OK |
|---|---:|
| `anthropic_messages_thinking_adaptive_all` | 3 |
| `anthropic_messages_image_thinking_manual` | 6 |
| `anthropic_messages_image_thinking_adaptive` | 3 |

Default:

- Use `anthropic_messages` for text and image input.
- Use adaptive thinking when that profile is verified for the model.
- Use manual budget thinking when adaptive is not verified but manual thinking is verified.
- Thinking off is the same base method with no `thinking` field.

### OpenAI

Confirmed base methods:

- `openai_responses`
- `openai_chat_completions`

Probe-level OK method counts:

| Probe-level method | OK |
|---|---:|
| `openai_responses_text` | 62 |
| `openai_chat_completions_text_modern` | 56 |
| `openai_responses_image_input` | 56 |
| `openai_chat_completions_image_input` | 38 |
| `openai_responses_reasoning_low` | 32 |
| `openai_chat_completions_reasoning_low` | 24 |

Important relationships:

- Text: Responses OK 62, Chat OK 56, both OK 49.
- Reasoning: Responses OK 32, Chat OK 24, both OK 24.
- Image input: Responses OK 56, Chat OK 38, both OK 37.

Default:

- Prefer `openai_responses` for modern LLM routes when verified.
- Keep `openai_chat_completions` as fallback or default only for models where Chat is the only verified method.
- Use Responses for reasoning-first and newer/pro models when verified.
- Mapper owns parameter names:
  - Responses uses `max_output_tokens`.
  - Chat Completions uses `max_completion_tokens`.
  - Reasoning effort belongs under the provider-specific reasoning field for the chosen method.

### Gemini

Confirmed base method:

- `gemini_generate_content`

Probe-level OK method counts:

| Probe-level method | OK |
|---|---:|
| `gemini_generate_content_text` | 19 |
| `gemini_generate_content_image_input` | 19 |
| `gemini_generate_content_thinking_budget_0` | 12 |
| `gemini_generate_content_thinking_budget_128` | 15 |
| `gemini_generate_content_thinking_budget_512` | 1 in method probe, 16 in profile-combination probe |
| `gemini_embed_content` | 3 |

Important relationships:

- Some Gemini models support no-thinking (`thinkingBudget=0`).
- Some require thinking and fail no-thinking.
- `gemini-2.5-flash-lite` needs a larger budget for thinking than the first probe used.
- The Models API `supported_actions` must be preserved and used for candidate classification.

Default:

- Use `gemini_generate_content` for language and image-input LLM routes.
- Treat `thinkingBudget=0`, small positive budget, and larger positive budget as profile mapper choices.
- Do not list embedding/image/video generation models in LLM Roles; place them in the capability library.

### DeepSeek

Confirmed base methods:

- `deepseek_chat_completions`
- `deepseek_anthropic_messages`

Probe-level and profile findings:

| Probe/profile method | OK |
|---|---:|
| `deepseek_chat_completions_text` | 2 |
| `deepseek_chat_completions_reasoning_effort` | 2 |
| `deepseek_anthropic_messages_text` | 2 |
| `deepseek_anthropic_messages_thinking` | 2 |
| `deepseek_anthropic_messages_image_input` | 2 |
| `deepseek_anthropic_messages_image_thinking` | 2 |
| native `deepseek_chat_completions_image_input` | 0 |

Default:

- Keep native Chat Completions for plain text and native reasoning-effort profiles.
- Use the verified Anthropic-compatible method for image input and thinking/image-thinking profiles.
- Store both methods as alternatives under the same endpoint, not as separate user-visible protocol choices.

### Ark

Confirmed base methods for LLM route use:

- `ark_chat`
- `ark_responses`
- `ark_anthropic_messages` for the official Anthropic-compatible / Claude Code-compatible surface documented at `https://ark.cn-beijing.volces.com/api/compatible`

Probe-level OK method counts:

| Probe-level method | OK |
|---|---:|
| `ark_chat_text` | 22 |
| `ark_responses_text` | 18 |
| `ark_chat_image_input` | 14 |
| `ark_responses_image_input` | 13 |
| `ark_responses_thinking_disabled` | 18 |
| `ark_responses_thinking_enabled` | 18 |
| `ark_responses_translation_text` | 1 |
| `ark_embedding` | 0 |

Profile-combination follow-up:

| Profile method | OK |
|---|---:|
| `ark_chat_thinking_disabled` | 22 |
| `ark_chat_thinking_enabled` | 22 |
| `ark_chat_image_thinking_disabled` | 14 |
| `ark_chat_image_thinking_enabled` | 14 |
| `ark_responses_image_thinking_disabled` | 13 |
| `ark_responses_image_thinking_enabled` | 13 |

Important relationships:

- Text: Chat OK 22, Responses OK 18, both OK 18.
- Four Doubao 1.5 models are Chat-only in the probe.
- Image input: Chat OK 14, Responses OK 13, one model is Chat-only.
- Ark thinking enabled/disabled was verified on both Chat and Responses profile probes.
- Ark official docs also expose an Anthropic-compatible base URL for third-party tools and Claude Code. Treat that as a third candidate language method under the same Ark account connection, not as a separate provider.

Default:

- Prefer `ark_chat` for models where Chat is verified and Responses is not.
- Prefer `ark_responses` for models/features where Responses is verified and richer profile support is needed.
- Keep `ark_anthropic_messages` available for Claude Agent SDK / Claude Code compatibility probes and for role runtimes that explicitly require an Anthropic-compatible surface.
- Keep both verified profiles when both pass.
- Generated media, embedding, translation, video, and 3D belong in the capability library unless they are text-output LLM routes.

## LLM Roles Availability Rules

`LLM Roles` available models must show only language/reasoning models.

Include a model when it has at least one ready verified profile with:

- text input to text output,
- optional image input to text output,
- optional reasoning/thinking to text output.

Exclude from LLM Roles:

- pure image generation,
- video generation,
- audio generation/TTS/transcription,
- embeddings,
- moderation,
- realtime-only models,
- translation-only models unless they are also usable as general language routes,
- 3D generation,
- any catalog-only model with no ready language profile.

The LLM Roles UI may show a model once, with compact capability badges such as text, vision, thinking, and fallback method count. It should not show generated multimodal capability-library records as available LLM role models.

## Fallback Semantics

Fallback should be explicit and profile-aware.

Recommended policy fields:

| Field | Meaning |
|---|---|
| `fallback_rank` | Order among profiles that satisfy the same intent. |
| `satisfies_intent` | Whether this profile satisfies required role/runtime intent. |
| `downgrade_from` | Optional pointer when a weaker profile can be used only if downgrade is allowed. |
| `last_success_at` | Last runtime/probe success. |
| `last_failure_at` | Last runtime/probe failure. |
| `last_failure_class` | Normalized human-readable class. |

Examples:

- OpenAI model with both Responses and Chat text profiles:
  - default: Responses,
  - fallback: Chat,
  - both satisfy text intent.
- OpenAI model with Responses reasoning and Chat text:
  - if reasoning required, Chat text is not a fallback.
  - if reasoning preferred, Chat text can be a downgrade only when policy allows.
- Claude model with manual thinking and no-thinking:
  - if thinking required, no-thinking is not a fallback.
  - if thinking preferred, no-thinking is a downgrade fallback.

## Failure Classification

Raw provider errors must be translated into actionable human causes. The backend should persist both raw evidence and normalized class, but UI should primarily show the class message.

| Normalized class | User-facing meaning | Backend action |
|---|---|---|
| `model_not_found_or_no_access` | Your account can list or knows about this model family, but this specific model/API family is not enabled for this key or region. | Try other verified methods only if plausible; otherwise mark profile unavailable for this endpoint. |
| `wrong_capability_for_model` | This model is not for the tested capability. | Move it to the correct capability library or keep catalog-only. |
| `wrong_api_family_or_method` | The model may work, but not through this API family. | Try the alternate official method for the same capability. |
| `wrong_request_shape` | The selected API family is plausible, but parameters or content shape were wrong. | Retry corrected mapper/profile before final failure. |
| `retired_or_unavailable` | The provider says the model is retired or unavailable to this account/version. | Hide by default or mark unavailable. |
| `rate_limited_or_quota` | The key hit rate limit/quota. | Keep previous success if any; retry later. |
| `provider_transient` | Provider returned a temporary 5xx/capacity failure. | Retry with backoff; do not permanently downgrade from one failure. |
| `tool_required` | The model requires a tool/session/file flow, not the direct text probe. | Keep out of LLM Roles until that flow is implemented. |
| `auth_failed` | The API key or auth headers are invalid. | Mark endpoint account status failed. |

Ark examples:

- `InvalidEndpointOrModel.NotFound` should not be shown raw. Prefer "This model is not enabled for this account or not callable through the tested Ark API family."
- `AccessDenied` should not be shown raw. Prefer "This account does not have permission for this model/API family."

## Storage Framework Assessment

Current storage can carry a partial version of this design:

- `ProviderEndpoint.metadata` can store catalog snapshots and method summaries.
- `ProviderRoute.capabilities` can store summary booleans/descriptors.
- `ProviderRoute.metadata` can store verified profile arrays.
- `RuntimeSettings.reasoning` already has generic fields for `enabled`, `effort`, and `budget_tokens`.

But current storage is not sufficient as the final contract because:

- verified profiles are not typed,
- route health is not profile-specific,
- fallback is route-level rather than profile-level,
- call method IDs are not first-class,
- request mapper IDs are not first-class,
- role materialization cannot reliably know which provider-specific profile turns thinking on/off,
- current runtime dispatch is still too chat-oriented for OpenAI/Ark Responses and profile-specific method selection.

Recommended migration:

1. Introduce typed `OfficialCallMethod` and `VerifiedProfile` models.
2. Keep writing summary capabilities for frontend filtering during transition.
3. Store complete verified profile data in `ProviderRoute.metadata.verified_profiles` until schema migration is ready.
4. Move to first-class route profile fields once frontend/backend contracts are updated.

## Implementation Phases

### Phase 1: Protocol registry and probe result model

- Add official provider method registry.
- Add mapper IDs and probe profile definitions.
- Add normalized failure taxonomy.
- Add typed probe result objects.

### Phase 2: Backend `Test` endpoint

- Replace separate official Get Models and endpoint test behavior with one backend test orchestration.
- Fetch catalog first.
- Probe candidate methods/profiles.
- Persist verified route/profile results.
- Persist capability library records separately.
- Return a single frontend-safe test summary.

### Phase 3: Runtime route/profile dispatch

- Update resolver to select verified profiles based on role/user intent.
- Update client manager dispatch to invoke selected base call method.
- Move provider-specific reasoning/thinking mapping into request mappers.
- Enforce no silent downgrade when thinking is required.

### Phase 4: LLM Roles consumption

- Filter available models to ready language profiles only.
- Show model-level entries with verified profile badges.
- Use profile-aware fallback chains in role configs.
- Do not show generated multimodal library records.

### Phase 5: Capability library

- Add generated media, embedding, translation, audio, video, realtime, moderation, and 3D library records.
- Add safe/cost-controlled probes per capability.
- Keep these out of LLM Roles until a feature explicitly consumes them.

## Acceptance Criteria

- One `Test` button replaces separate official `Get Models` and endpoint test actions.
- After `Test`, LLM Roles can immediately show verified language/reasoning models.
- A model listed in the provider catalog is not treated as a route unless at least one relevant profile probe passed.
- Claude Opus routes can tell runtime exactly how to turn thinking off, manual thinking on, or adaptive thinking on.
- OpenAI routes can choose Responses by default when verified and fallback to Chat only when the profile satisfies the intent.
- Gemini routes preserve `supported_actions` and model-specific thinking budget behavior.
- DeepSeek stores both native and Anthropic-compatible verified methods where they work.
- Ark stores Chat, Responses, and Anthropic-compatible verified profiles separately with fallback.
- Generated multimodal models are stored outside LLM Roles in the capability library.
- Raw provider errors are translated to normalized human-readable causes.

## Review Decision Needed

Before implementation, decide only this schema boundary:

1. Transitional path: store `verified_profiles` in `ProviderRoute.metadata` first, then promote to typed schema.
2. Direct schema path: add typed `VerifiedProfile` fields to `ProviderRoute` now.

The runtime and UX design is the same either way. The direct schema path is cleaner; the transitional path is lower risk if existing frontend/backend tests assume the current route shape.
