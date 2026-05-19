---
status: Living
target_goal: "Studio MVP — 让 PM 可用"
---

# Ark (火山方舟) API Configuration Guide

## 1. Supported SDKs & Protocols

- **Primary Protocol Enum**: `openai_compatible`
- **Native SDK**: `volcengine-python-sdk`

## §1.5 探测元数据 (round 3 新增, 用于 Studio 自动 Test 探测)

```yaml
compatible_sdks:
  - openai_compatible

models_endpoint_path: "/api/v3/models"

auth_header_format: |
  Authorization: Bearer ${key}
```

## 2. Authentication

- **Method**: Bearer Token
- **Header 完整 sample**:
  ```
  Authorization: Bearer <YOUR_KEY>
  ```
- **拿 key 的位置**: `https://console.volcengine.com/ark/`

## 3. Base URL

- **Official Endpoint**: `https://ark.cn-beijing.volces.com/api/v3`

## 4. Notable Model IDs

- `ep-xxxxxx` — 火山方舟的模型通常使用 Endpoint ID 而非直接模型名。
- `doubao-pro-128k`
- `doubao-lite-32k`

## 5. 能力维度 (Test 成功后后端应当返回)

- `thinking`: ✗
- `tool_calling`: ✓
- `vision`: ✓ (视具体模型)
- `max_context_tokens`: 128000 (Source: https://www.volcengine.com/docs/82379)
- `max_output_tokens`: 4096

## 6. Known Quirks / Pitfalls

- 需要配置 Endpoint ID 而非通用 model string。

## 7. Testing (cURL)

```bash
curl https://ark.cn-beijing.volces.com/api/v3/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_KEY>" \
  -d '{
    "model": "ep-xxxxx",
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
