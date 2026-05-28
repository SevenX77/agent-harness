# Official LLM Provider Call Methods

Status: Living
Last verified: 2026-05-28

This document records the official-provider API surfaces that Studio should treat as source-of-truth when seeding endpoints, routes, and model probes. It is based on:

- Local probe artifact: `temp/official-provider-model-probe-2026-05-27-160710.json`
- Official documentation linked in each provider section.

## Principles

- Do not expose protocol selection for official providers. Official cards should seed the provider's known base URL, auth style, model-list method, and capability-specific call methods.
- `Get Models` proves that credentials and model-list endpoint are reachable. It does not prove every returned model can satisfy a text chat probe.
- Route probing must be capability-aware. A text chat probe should only classify text/chat-capable models. Image, audio, embedding, video, realtime, TTS, transcription, and vendor tool-only models need their own route capability and probe method.
- Do not treat provider catalog entries as executable routes until they pass a probe for the relevant capability or are explicitly marked as catalog-only.

## Error Taxonomy From Probe

| Class | Meaning | Backend action |
|---|---|---|
| `text_chat_ok` | 1-token text generation succeeded. | Route can be `ready` for text chat. |
| `wrong_endpoint_or_api_family` | Model is usable, but not through the endpoint currently used by the probe. Examples: OpenAI Responses-only models, Gemini Interactions-only models, Ark Chat-only vs Responses-only models. | Add/select the correct call method; do not mark API key bad. |
| `wrong_parameter` | Endpoint is broadly right, but request parameters are wrong. Example: OpenAI o-series / newer models rejecting `max_tokens`. | Use provider-specific modern parameter (`max_output_tokens` on Responses; `max_completion_tokens` on OpenAI Chat Completions). |
| `not_text_chat_model` | Model is for embeddings, image generation/editing, audio, video, realtime, TTS, transcription, or another non-chat surface. | Keep as catalog model; create modality route only if Studio supports that modality. |
| `permission_or_not_enabled` | Account/key can list the model but cannot invoke it, or model has not been activated/opened in provider console. | Show account/model activation problem; user must enable model or billing. |
| `retired_or_unavailable` | Provider says model is no longer available or unsupported for the requested API version. | Hide by default or mark unavailable; refresh model list rules. |
| `provider_transient` | Provider returned 5xx/capacity error. | Retry with backoff; do not permanently mark route broken from one result. |

## Probe Summary

| Provider | Listed models | Text chat OK | Main failure categories |
|---|---:|---:|---|
| Anthropic Official | 7 | 7 | None in this run. |
| DeepSeek Official | 2 | 2 | None in this run. |
| Ark Official | 119 | 18 | Mostly model not opened / no account access; some models require a different API family such as image, video, embedding, or translation. |
| Gemini Official | 50 | 18 | Non-`generateContent` models, retired models, Interactions-only models, TTS/audio models, and two provider 500s. |
| OpenAI Official | 118 | 27 | Non-chat models, Responses-only models, wrong `max_tokens` parameter for newer/reasoning models, audio/image/video/realtime families, provider 5xx/capacity errors. |

## Chat Connectivity Result Interpretation

The API Keys page needs three separate facts instead of one provider-level "connected" flag:

| Fact | Meaning | UI/backend consequence |
|---|---|---|
| Credential/model-list reachable | The API key and provider model-list URL accepted the request. | Show credentials/base URL as reachable; do not claim a chat model works yet. |
| Catalog model listed | The provider returned a model ID in its catalog. | Show it as catalog data. It is not automatically a route. |
| Capability probe passed | A concrete call method for a concrete capability succeeded for that model. | Only then mark that route as ready for that capability. |

Text chat probe failures from the current run break down as follows:

| Provider | Failure type | Human explanation | Fix |
|---|---|---|---|
| OpenAI | Non-chat model | Embedding, image, audio, realtime, video, moderation, and legacy completion models are visible in `/v1/models`, but they are not valid `chat/completions` text-chat models. | Keep them in the catalog and create modality-specific routes only when Studio supports those modalities. |
| OpenAI | Responses-only model | Some newer/reasoning models must be called through `/v1/responses`; the old chat probe is the wrong API family. | Add an `openai_responses` text/multimodal probe and prefer it for modern OpenAI routes. |
| OpenAI | Wrong parameter | Current chat probe sends `max_tokens`; official Chat Completions docs deprecate it in favor of `max_completion_tokens` and mark it incompatible with o-series models. | Use `max_output_tokens` on Responses and `max_completion_tokens` on Chat Completions. |
| Gemini | Unsupported action | The Models API can list models that do not support `generateContent`; some are embeddings, image/video generation, Interactions-only, TTS/audio, or retired. | Retain `supported_actions` from `models.list` and only text-probe models with `generateContent`. |
| Gemini | Retired/unavailable | Provider explicitly says the model is no longer available to new users. | Mark unavailable and prefer current aliases/models. |
| Ark | API-family/account mismatch | Ark catalog includes model IDs across Responses, Chat, image, audio, video, embedding, and older families. A 404/403 can mean the model is not open for the account or not usable through the selected API family. | Parse/curate Ark capability data and probe with `ark_responses`, `ark_chat`, or modality routes as appropriate. |
| DeepSeek | None in this run | Both official listed models passed text chat. | Keep current text chat route. |
| Anthropic | None in this run | All listed Claude models passed Messages API text chat. | Keep current Messages route. |

## OpenAI Official

Official docs:

- Responses API: https://platform.openai.com/docs/api-reference/responses/create
- Migrate to Responses: https://platform.openai.com/docs/guides/migrate-to-responses
- Chat Completions: https://platform.openai.com/docs/api-reference/chat/create
- Images and vision: https://platform.openai.com/docs/guides/images-vision
- Image generation: https://platform.openai.com/docs/guides/image-generation
- Audio: https://platform.openai.com/docs/guides/audio
- Model comparison: https://platform.openai.com/docs/models/compare

Fixed official entrypoints:

| Capability | Endpoint / call method | Notes |
|---|---|---|
| Model list | `GET https://api.openai.com/v1/models` | Catalog only; does not encode enough capability information by itself. |
| Modern text / multimodal input | `POST https://api.openai.com/v1/responses` | Preferred for new integrations. Use `max_output_tokens`. Supports text/image/audio inputs depending on model. |
| Legacy chat text / vision / audio | `POST https://api.openai.com/v1/chat/completions` | Still supported. Use `max_completion_tokens`; `max_tokens` is deprecated and incompatible with o-series/reasoning models. |
| Image generation/editing | `POST https://api.openai.com/v1/images/generations` and related Images API endpoints, or Responses with image generation tool | Same OpenAI API key. GPT Image models may require org verification. |
| Audio | Audio endpoints or audio-capable Chat Completions requests | Same API key; requires audio-capable models and `modalities`/audio fields. |

Probe interpretation:

- `unsupported_parameter` for OpenAI is not a bad API key and not necessarily a bad model. It means current probe is using `max_tokens` on models that require `max_completion_tokens` or Responses `max_output_tokens`.
- `only supported in v1/responses` means the route should be probed with Responses, not Chat Completions.
- `not a chat model` means the model is not a text chat route. It may be embedding, audio, image, realtime, TTS, transcription, or legacy completion.

Backend recommendation:

- Add `openai_responses` as the primary official route protocol for modern OpenAI LLMs.
- Keep `openai_chat_completions` as a compatibility protocol for models that explicitly work there.
- Split modality routes: `openai_images`, `openai_audio`, `openai_embeddings`, `openai_realtime`, etc. Do not let text chat probe mark those as failed.

## Anthropic Official

Official docs:

- API overview / auth: https://docs.anthropic.com/en/api/overview
- Messages API examples: https://docs.anthropic.com/en/api/messages-examples
- List models: https://docs.anthropic.com/en/api/models-list
- Vision guide: https://docs.anthropic.com/en/docs/build-with-claude/vision
- Models overview: https://docs.anthropic.com/en/docs/about-claude/models/overview

Fixed official entrypoints:

| Capability | Endpoint / call method | Notes |
|---|---|---|
| Model list | `GET https://api.anthropic.com/v1/models` | Requires `x-api-key` and `anthropic-version`. |
| Text chat | `POST https://api.anthropic.com/v1/messages` | Requires same API key and `anthropic-version`. |
| Image understanding | `POST https://api.anthropic.com/v1/messages` with image content blocks | Same API key and protocol; Claude 3/4 family supports image input. |

Probe interpretation:

- All listed Anthropic models passed the text probe in the current run.
- Multimodal image understanding is not a separate protocol for Anthropic; it is Messages API with image content parts.

Backend recommendation:

- Keep one official `anthropic_messages` protocol for text and image-input routes.
- Capability classification should come from model metadata/docs and/or image-content probe, not from a separate user-selected protocol.

## Gemini Official

Official docs:

- Text generation: https://ai.google.dev/gemini-api/docs/text-generation
- Image understanding: https://ai.google.dev/gemini-api/docs/vision
- Models API: https://ai.google.dev/api/models

Fixed official entrypoints:

| Capability | Endpoint / call method | Notes |
|---|---|---|
| Model list | `GET https://generativelanguage.googleapis.com/v1beta/models` | Models API returns supported actions; filter for `generateContent` when probing text/image/audio/video generation. |
| Text / image / audio / video input to text | `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent` | Same Gemini API key (`x-goog-api-key` or `key` query param). |
| Files | Gemini File API | Used for larger media or reuse across requests. |

Probe interpretation:

- Gemini model list includes models that do not support `generateContent`, retired models, Interactions-only models, TTS/audio-specific models, image/video generation models, and embedding models.
- A 404 saying a model is not supported for `generateContent` is a capability mismatch, not an API key failure.
- The Models API exposes `supported_actions`; use it to avoid probing models with the wrong method.

Backend recommendation:

- Official protocol should be `google_genai_generate_content`, not a user choice.
- Model-list parsing should retain `supported_actions` and route only `generateContent` models to text/image/audio/video input probes.
- Add separate generated-media protocols if Studio later supports Gemini image/video generation surfaces.

## DeepSeek Official

Official docs:

- First API call / base URLs: https://api-docs.deepseek.com/
- Models and pricing: https://api-docs.deepseek.com/quick_start/pricing/
- Chat completion API: https://api-docs.deepseek.com/api/create-chat-completion
- List models: https://api-docs.deepseek.com/api/list-models
- Anthropic API compatibility: https://api-docs.deepseek.com/guides/anthropic_api
- Change log: https://api-docs.deepseek.com/updates/

Fixed official entrypoints:

| Capability | Endpoint / call method | Notes |
|---|---|---|
| Model list | `GET https://api.deepseek.com/models` | Bearer API key. |
| OpenAI-format chat | `POST https://api.deepseek.com/chat/completions` | Same API key; OpenAI-compatible. |
| Anthropic-format chat | `POST https://api.deepseek.com/anthropic/v1/messages` through Anthropic SDK/base URL | Same API key; DeepSeek documents image/document content as not supported in Anthropic compatibility. |

Probe interpretation:

- Both listed DeepSeek models passed text chat probe.
- Official docs currently describe text chat/function/tool/FIM compatibility; Anthropic compatibility explicitly marks image content as not supported.

Backend recommendation:

- Keep DeepSeek official as text-only until official docs expose an image/audio/video API.
- Seed both `deepseek_openai_chat` and optionally `deepseek_anthropic_messages` as fixed official call methods if we want both ecosystems; do not expose as user protocol selection.

## Ark Official

Official docs:

- Ark model list: https://www.volcengine.com/docs/82379/1554709
- Ark docs home / API reference navigation: https://www.volcengine.com/docs/82379/?lang=zh
- Responses API examples: https://www.volcengine.com/docs/82379/1338552
- Tool calling via Responses API: https://www.volcengine.com/docs/82379/1958524
- Image generation guide: https://www.volcengine.com/docs/82379/1548482
- Audio understanding guide: https://www.volcengine.com/docs/82379/2377589

Fixed official entrypoints:

| Capability | Endpoint / call method | Notes |
|---|---|---|
| Model list | `GET https://ark.cn-beijing.volces.com/api/v3/models` | Bearer API key. |
| Responses / agent / multimodal input | `POST https://ark.cn-beijing.volces.com/api/v3/responses` | Same Ark API key. Model list marks which models support Responses API / Chat API / multimodal understanding / tools. |
| Chat | `POST https://ark.cn-beijing.volces.com/api/v3/chat/completions` | Same Ark API key; some older/current models are Chat API only. |
| Image generation/editing | `POST https://ark.cn-beijing.volces.com/api/v3/images/generations` | Same Ark API key; image models like Seedream use this surface. |
| Other generated media / embeddings | Ark-specific video, 3D, embeddings APIs | Same Ark API key; should be separate route capabilities. |

Probe interpretation:

- Ark catalog contains many modalities and historical models. Listing a model is not enough to prove it is open for the account or supported by the current API family.
- 404 `InvalidEndpointOrModel.NotFound` often means the account has no access to that model/endpoint or the model is not invokable through the selected API family.
- 403 `AccessDenied` means the model exists but the account/model/API-family access is not enabled.
- `MissingParameter` for translation/image/etc. means the probe body is wrong for that modality.

Backend recommendation:

- Parse Ark model-list capability columns or maintain a curated model capability map from official model-list docs.
- Seed separate protocols/call methods: `ark_responses`, `ark_chat`, `ark_images`, `ark_audio`, `ark_embeddings_multimodal`, `ark_video`, etc.
- For official Ark, do not ask user for protocol. The provider card should manage multiple default routes under the same API key.

## UX Implication For API Keys Page

- Official provider cards should be account-key forms, not protocol forms.
- `Get Models` should fill catalog rows grouped by official capability family.
- Text `Endpoint test` should only offer text-chat candidates.
- Future multimodal route tests should be separate capability probes, for example:
  - Text chat test
  - Image input test
  - Image generation test
  - Audio input test
  - Embedding test
- A model can be "listed" but not "chat-ready"; UI should show this distinction rather than a single connected/failed status for the whole provider.
