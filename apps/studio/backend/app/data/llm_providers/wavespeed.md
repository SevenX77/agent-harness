---
status: Living
target_goal: "Studio MVP — 让 PM 可用"
---

# WaveSpeed API Configuration Guide

## 1. Supported SDKs & Protocols

- **Primary Protocol Enum**: `openai_compatible`
- **Native SDK**: 无; LLM 网关使用 OpenAI-compatible 协议

## §1.5 探测元数据 (round 3 新增, 用于 Studio 自动 Test 探测)

```yaml
compatible_sdks:
  - openai_compatible

models_endpoint_path: "/models"

auth_header_format: |
  Authorization: Bearer ${key}
```

## 2. Authentication

- **Method**: Bearer Token
- **Header 完整 sample**:
  ```
  Authorization: Bearer <YOUR_KEY>
  ```
- **拿 key 的位置**: `https://wavespeed.ai/`

## 3. Base URL

- **Official Endpoint**: `https://llm.wavespeed.ai/v1`

## 4. Notable Model IDs

- `openai/gpt-5`
- `anthropic/claude-opus-4`
- `anthropic/claude-sonnet-4`
- `google/gemini-3.1-pro`
- `deepseek/deepseek-v4`
- `meta-llama/llama-4`

## 5. 能力维度 (Test 成功后后端应当返回)

- `thinking`: ✗
- `tool_calling`: ✓
- `vision`: ✓
- `max_context_tokens`: 128000
- `max_output_tokens`: 4096

## 6. Known Quirks / Pitfalls

- 这是 WaveSpeed 的 LLM API 网关，协议与 OpenAI 兼容。

## 7. Testing (cURL)

```bash
curl https://llm.wavespeed.ai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_KEY>" \
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
| `401` | API key 错或过期 | 重新生成 |
