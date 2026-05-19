---
status: Living
target_goal: "Studio MVP — 让 PM 可用"
---

# OpenAI API Configuration Guide

## 1. Supported SDKs & Protocols

- **Primary Protocol Enum**: `openai_compatible`
- **Native SDK**: `openai` Python / TypeScript ([docs](https://platform.openai.com/docs/))
- 这是业界 defacto standard, 大部分中转 API / OSS vLLM 部署 / DeepSeek / WaveSpeed / Mistral / xAI Grok / Cohere Compatibility 都走这套协议. 后端只要支持这个 enum, 就能覆盖 90% 文本 LLM.

## 2. Authentication

- **Method**: Bearer Token
- **Header sample**:
  ```
  Authorization: Bearer <YOUR_KEY>
  Content-Type: application/json
  ```
- **拿 key**: [platform.openai.com](https://platform.openai.com/api-keys)

## 3. Base URL

- **Official**: `https://api.openai.com/v1`
- **Azure OpenAI**: `https://{your-resource-name}.openai.azure.com/openai/deployments/{deployment-id}/`
  - **注意**: Azure 要求 `api-key` header 而不是 Bearer, 后端需要单独 adapter, **v2.1 不支持 Azure 部署** (PM 自己装 Azure 需要 patch backend)

## 4. Notable Model IDs

v2.1 默认列表:

- `gpt-4o` — flagship multimodal
- `gpt-4o-mini` — cost-effective fast
- `o1-preview` / `o1-mini` — reasoning models (legacy, 2024)
- `o3` / `o3-mini` — reasoning 2025 旗舰

## 5. 能力维度

| Model | thinking | tool_calling | vision | max_context_tokens |
|---|---|---|---|---|
| `gpt-4o` | ✗ | ✓ | ✓ | 128000 |
| `gpt-4o-mini` | ✗ | ✓ | ✓ | 128000 |
| `o1-preview` | ✓ (built-in reasoning) | ✗ | ✗ | 128000 |
| `o3` | ✓ | ✓ | ✓ | 200000 |

## 6. Known Quirks / Pitfalls

- **Reasoning models (`o1` / `o3` series)**:
  - 不支持 `system` prompt — 必须用 `user` role 包装 system 指令
  - 不支持 streaming (2024 末) — `o3` 已陆续放开, 但 default 仍可能 fallback to non-stream
  - `o1-mini` 不支持 tool calling
  - `max_completion_tokens` 替代了 `max_tokens` 字段名 (新版 SDK 自动处理, 直接调 raw API 注意)
- **`temperature` 在 reasoning 模型上无效** — 这些模型用 fixed temperature
- **Function calling vs Tools**: 新版用 `tools` 数组, legacy `functions` 字段 deprecated
- **rate limits**: 按 tier 分级 (free / tier-1...5), console "Limits" 页查具体配额
- **Structured Outputs (JSON mode)**: 需要 `response_format: { type: "json_schema", ... }` 显式开启

## 7. Testing (cURL)

```bash
# 测 key 可用 + 探活
curl https://api.openai.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "ping"}],
    "max_tokens": 8
  }'
```

拿 model 列表 (Studio Test 用):

```bash
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

## 8. Error Code Reference

| `error_code` (OpenAI 原始) | 含义 | 前端 toast 文案建议 |
|---|---|---|
| `invalid_api_key` | API key 错或被删 | "API key 无效, 请检查粘贴 (OpenAI key 通常以 `sk-` 开头, 长度 ~51 字符)" |
| `insufficient_quota` | 账户余额 / quota 用完 | "OpenAI 账户额度耗尽, 请充值或升级 plan" |
| `rate_limit_exceeded` | 限流 | "请求过快, 稍后再试" |
| `model_not_found` | model id 不存在或当前账户无权限 | "model 不存在或账户无权限, 检查 model id 或 tier 等级" |
| `invalid_request_error` | 请求 body 格式错 | "请求格式错误 (内部 bug)" |
| `context_length_exceeded` | 上下文超出 model 上限 | "上下文超出 model 容量上限" |
