---
status: Living
target_goal: "Studio MVP — 让 PM 可用"
---

# OpenRouter API Configuration Guide

## 1. Supported SDKs & Protocols

- **Primary Protocol Enum**: `openai_compatible`
- **Native SDK**: `@openrouter/sdk`

## §1.5 探测元数据 (round 3 新增, 用于 Studio 自动 Test 探测)

```yaml
compatible_sdks:
  - openai_compatible

models_endpoint_path: "/api/v1/models"

auth_header_format: |
  Authorization: Bearer ${key}
```

## 2. Authentication

- **Method**: Bearer Token
- **Header 完整 sample**:
  ```
  Authorization: Bearer <YOUR_KEY>
  ```
- **拿 key 的位置**: `https://openrouter.ai/keys`

## 3. Base URL

- **Official Endpoint**: `https://openrouter.ai/api/v1`

## 4. Notable Model IDs

- `openai/gpt-5`
- `anthropic/claude-opus-4-7`
- `google/gemini-3.1-pro`
- `meta-llama/llama-4-405b`
- `~openai/gpt-latest`
- `~anthropic/claude-sonnet-latest`

## 5. 能力维度 (Test 成功后后端应当返回)

- `thinking`: ✓
- `tool_calling`: ✓
- `vision`: ✓
- `max_context_tokens`: 128000
- `max_output_tokens`: 4096

## 6. Known Quirks / Pitfalls

- 需要前缀如 `openai/`、`anthropic/` 等。支持 ~ 别名使用最新模型。

## 7. Testing (cURL)

```bash
curl https://openrouter.ai/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_KEY>" \
  -H "HTTP-Referer: <YOUR_SITE_URL>" \
  -H "X-Title: <YOUR_SITE_NAME>" \
  -d '{
    "model": "openai/gpt-5",
    "messages": [
      {"role": "user", "content": "ping"}
    ],
    "max_tokens": 1
  }'
```

## 8. Error Code Reference

| `error_code` | 含义 | 用户应做什么 |
|---|---|---|
| `401` | API key 错或过期 | 重新生成 / 检查粘贴是否截断 |
