---
status: Living
target_goal: "Studio MVP — 让 PM 可用"
---

# Qiniu (七牛云) API Configuration Guide

## 1. Supported SDKs & Protocols

- **Endpoint profile (OpenAI)**: `openai_compatible` at `https://api.qnaigc.com/v1`
- **Endpoint profile (Anthropic)**: `anthropic_compatible` at `https://anthropic.qnaigc.com`
- **Native SDK**: 七牛云 SDK (Token Plan)
- **Studio rule**: one Endpoint record represents one endpoint profile. If the same Qiniu key has both OpenAI and Anthropic URLs, create two endpoints with the same key, different Base URLs, and different Protocol values.

## §1.5 探测元数据 (round 3 新增, 用于 Studio 自动 Test 探测)

```yaml
# Default metadata profile. Endpoint-specific profiles are represented in
# Studio credentials by the provider_type + base_url pair.
compatible_sdks:
  - openai_compatible

models_endpoint_path: "/v1/models"

auth_header_format: |
  Authorization: Bearer ${key}
```

## 2. Authentication

- **Method**: Bearer Token
- **Header 完整 sample**:
  ```
  Authorization: Bearer <YOUR_KEY>
  ```
- **拿 key 的位置**: `https://portal.qiniu.com/`

## 3. Base URL

- **OpenAI Base URL**: `https://api.qnaigc.com/v1`
- **Anthropic Base URL**: `https://anthropic.qnaigc.com`

## 4. Notable Model IDs

- `deepseek-r1`
- `deepseek-v3`
- `deepseek/deepseek-v3.1-terminus`
- `qwen/qwen3.7-max`
- `moonshotai/kimi-k2.6`
- `anthropic/claude-opus-4.7`

## 5. 能力维度 (Test 成功后后端应当返回)

- `thinking`: ✓
- `tool_calling`: ✓
- `vision`: ✓
- `max_context_tokens`: 64000
- `max_output_tokens`: 4096

## 6. Known Quirks / Pitfalls

- 作为一个企业级 Token Plan 聚合服务，支持 50+ 款主流模型，统一接入。

## 7. Testing (cURL)

```bash
curl https://api.qnaigc.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_KEY>" \
  -d '{
    "model": "deepseek-v4",
    "messages": [
      {"role": "user", "content": "ping"}
    ],
    "max_tokens": 1
  }'
```

```bash
curl https://anthropic.qnaigc.com/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: <YOUR_KEY>" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "anthropic/claude-opus-4.7",
    "messages": [
      {"role": "user", "content": "ping"}
    ],
    "max_tokens": 1
  }'
```

## 8. Error Code Reference

| `error_code` | 含义 | 用户应做什么 |
|---|---|---|
| `401` | API key 错或过期 | 重新生成 |
