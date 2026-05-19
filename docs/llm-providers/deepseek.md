---
status: Living
target_goal: "Studio MVP — 让 PM 可用"
---

# DeepSeek API Configuration Guide

## 1. Supported SDKs & Protocols

- **Primary Protocol Enum**: `openai_compatible`
- **Native SDK**: 无, 官方推荐使用 OpenAI SDK

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
- **拿 key 的位置**: `https://platform.deepseek.com/`

## 3. Base URL

- **Official Endpoint**: `https://api.deepseek.com`

## 4. Notable Model IDs

- `deepseek-chat`
- `deepseek-reasoner`

## 5. 能力维度 (Test 成功后后端应当返回)

- `thinking`: ✓ (仅 deepseek-reasoner)
- `tool_calling`: ✓ (仅 deepseek-chat)
- `vision`: ✗
- `max_context_tokens`: 64000 (Source: https://api-docs.deepseek.com/)
- `max_output_tokens`: 8000

## 6. Known Quirks / Pitfalls

- deepseek-reasoner 响应会多出 `reasoning_content` 字段。
- max_tokens 默认有差异。

## 7. Testing (cURL)

```bash
curl https://api.deepseek.com/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_KEY>" \
  -d '{
    "model": "deepseek-chat",
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
