---
status: Living
target_goal: "Studio MVP — 让 PM 可用 (api keys 配置准确性 / 一站式参考)"
linked_code_paths:
  - apps/studio/frontend/src/components/studio/SettingsPage.tsx
  - apps/studio/backend/app/services/llm_provider_test.py
linked_specs:
  - apps/studio/frontend/docs/api-keys-redesign-design.md
---

# LLM Providers — Configuration Matrix

本目录是 Studio 接入各家 LLM / 中转 API 的**配置规范单一真相**, 供:
- **前端** (Settings → API Keys 页) 读默认 base URL / auth 方式做 UI 默认值
- **后端** (`llm_provider_test.py` / 业务调用) 读协议 enum + auth header 实现 SDK adapter
- **PM / 用户** 查每个 vendor 的 model id / quirks / cURL 测试样本

## 当前 v2.1 scope (text-only LLM)

多模态 (Replicate / Fal.ai / Stability AI / BFL Flux / Midjourney / Runway) **不在 v2.1 范围内** — 它们走 async polling 协议跟当前 text-stream test path 不兼容, 延到 v2.2+ video-generation skill 上线时再加。

## Backend Provider Enum (v2.1 收敛后)

`apps/studio/backend/app/services/llm_provider_test.py:ProviderType` 应当收敛到 **3 个 enum**:

| Enum | 含义 | Auth | Test endpoint |
|---|---|---|---|
| `anthropic_compatible` | Anthropic native protocol | `x-api-key` + `anthropic-version` header | `GET /v1/models` (Anthropic 2024 加的) 或仅做 base URL 探活 |
| `openai_compatible` | OpenAI 标准 (最广支持) | `Authorization: Bearer <key>` | `GET /v1/models` |
| `gemini_official` | Google Gemini native (可选保留, native SDK 有 grounding 等特性) | API key query param 或 Bearer (兼容 endpoint) | `GET /v1/models` |

**之前的 `wavespeed_any_llm` 已干掉** — WaveSpeed 实测就是 `openai_compatible`, base URL 换成 `https://llm.wavespeed.ai/v1` 即可.

## Text / Chat Completion Providers 速查表

| Provider | Protocol Enum | Default Base URL | Auth | 备注 |
|---|---|---|---|---|
| **OpenAI** | `openai_compatible` | `https://api.openai.com/v1` | Bearer | defacto standard |
| **Anthropic** | `anthropic_compatible` | `https://api.anthropic.com` | `x-api-key` + `anthropic-version` | OpenAI 兼容层走 `/v1/messages`, 但 native SDK 有 Prompt Caching 等特性 |
| **Google Gemini** | `gemini_official` 或 `openai_compatible` | native: `https://generativelanguage.googleapis.com/v1beta` ; OpenAI 兼容: `https://generativelanguage.googleapis.com/v1beta/openai/` | API key (native) / Bearer (兼容) | 2024-11 起官方加了 OpenAI 兼容 endpoint |
| **DeepSeek** | `openai_compatible` | `https://api.deepseek.com/v1` | Bearer | 完全 OpenAI 协议 (历史无独立 SDK) |
| **Mistral** | `openai_compatible` | `https://api.mistral.ai/v1` | Bearer | `mistralai` SDK 底层也是 OpenAI 协议 |
| **xAI Grok** | `openai_compatible` | `https://api.x.ai/v1` | Bearer | 直接用 openai SDK 改 base_url |
| **Cohere** | `openai_compatible` | `https://api.cohere.ai/compatibility/v1` | Bearer | 官方提供 Compatibility API |
| **WaveSpeed** | `openai_compatible` | `https://llm.wavespeed.ai/v1` | Bearer | LLM 聚合中转, model id 带 vendor 前缀 (`anthropic/claude-opus-4.6`) |

## 中转 / 聚合 API

| 中转 | Protocol Enum | Base URL | 备注 |
|---|---|---|---|
| **OpenRouter** | `openai_compatible` | `https://openrouter.ai/api/v1` | 多 vendor 聚合 |
| **Together AI** | `openai_compatible` | `https://api.together.xyz/v1` | OSS model hosting |
| **OneChats** | `openai_compatible` | `https://chatapi.onechats.ai/v1` | 国内中转 |
| **Jiekou** | `openai_compatible` 或 `anthropic_compatible` | `https://api.jiekou.ai/openai/v1` 或 `https://api.jiekou.ai/anthropic` | 双协议入口, URL 区分 |

## 文件清单

- [`_template.md`](./_template.md) — 新增 vendor 文档模板
- [`anthropic.md`](./anthropic.md) — Anthropic 官方 / Vertex / Bedrock / 兼容层
- [`openai.md`](./openai.md) — OpenAI 官方 / Azure
- [`gemini.md`](./gemini.md) — Google Gemini native + OpenAI 兼容 endpoint

## 维护约定

1. 新增一个 vendor / 中转 → 拷贝 `_template.md` 改名为 `<vendor>.md`
2. 速查表 (本文件) 同步加一行
3. 后端 `llm_provider_test.py:DEFAULT_BASE_URLS` dict 跟本表对齐
4. 不要在本目录写**实现细节** (具体 Python adapter / TS UI 怎么渲染) — 那些归 `docs/studio/` 或代码注释; 本目录只放**协议事实**
