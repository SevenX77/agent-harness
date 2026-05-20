---
status: Living
target_goal: "Studio MVP — 让 PM 可用"
---

# Qiniu (七牛云) API Configuration Guide

## 1. Supported SDKs & Protocols

- **Primary Protocol Enum**: `openai_compatible`
- **Native SDK**: 七牛云 SDK (Token Plan)

## §1.5 探测元数据 (round 3 新增, 用于 Studio 自动 Test 探测)

```yaml
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

- **Official Endpoint**: `https://api.qiniu.com/v1`

## 4. Notable Model IDs

- `deepseek-v4`
- `doubao-pro`
- `qwen-max`
- `kimi-latest`

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
curl https://api.qiniu.com/v1/chat/completions \
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

## 8. Error Code Reference

| `error_code` | 含义 | 用户应做什么 |
|---|---|---|
| `401` | API key 错或过期 | 重新生成 |
