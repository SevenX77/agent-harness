---
status: Living
target_goal: "Studio MVP — 让 PM 可用"
---

# Anthropic API Configuration Guide

## 1. Supported SDKs & Protocols

- **Primary Protocol Enum**: `anthropic_compatible` (native)
- **Native SDK**: `anthropic` Python / TypeScript ([docs](https://docs.anthropic.com/))
- **Alternative Protocols**:
  - **OpenAI 兼容层**: Anthropic 近年正式支持, 通过 `/v1/messages` 走 OpenAI 协议格式 (但 native SDK 更推荐, 因为支持 Prompt Caching / Extended Thinking / Computer Use 等特性)
- **Alternative Endpoints**:
  - **Google Vertex AI**: `anthropic[vertex]` SDK, endpoint 走 GCP region (`us-east5-aiplatform.googleapis.com` etc.)
  - **AWS Bedrock**: `anthropic[bedrock]` SDK, IAM 鉴权

## §1.5 探测元数据 (round 3 新增, 用于 Studio 自动 Test 探测)

```yaml
compatible_sdks:
  - anthropic_compatible

models_endpoint_path: null
  # Anthropic 官方 API 没有 GET /models endpoint
  # Studio 走 §4 Notable Model IDs fallback

auth_header_format: |
  x-api-key: ${key}
  anthropic-version: 2023-06-01
```

## 2. Authentication

- **Method**: Custom headers (native)
- **Header sample**:
  ```
  x-api-key: <YOUR_KEY>
  anthropic-version: 2023-06-01
  content-type: application/json
  ```
- **拿 key**: [console.anthropic.com](https://console.anthropic.com/)

## 3. Base URL

- **Official**: `https://api.anthropic.com`
- **Vertex**: `https://{region}-aiplatform.googleapis.com/v1/projects/{project_id}/locations/{region}/publishers/anthropic/models/{model_id}:rawPredict`
- **Bedrock**: AWS SDK 内部封装, 不直接拼 URL

## 4. Notable Model IDs

v2.1 默认列表 (后端 `available_models` 应包含):

- `claude-opus-4-7` — flagship, 2026 旗舰 (高质量推理 / 长上下文)
- `claude-sonnet-4-6` — 平衡型, 速度 + 成本
- `claude-haiku-4-5-20251001` — 最快最便宜
- `claude-3-5-sonnet-20241022` — legacy, 仍可用
- `claude-3-5-haiku-20241022` — legacy fast

## 5. 能力维度

| Model | thinking | tool_calling | vision | max_context_tokens |
|---|---|---|---|---|
| `claude-opus-4-7` | ✓ | ✓ | ✓ | 200000 |
| `claude-sonnet-4-6` | ✓ | ✓ | ✓ | 200000 |
| `claude-haiku-4-5` | ✓ | ✓ | ✓ | 200000 |

(后端 `Test` 成功响应应当对每个 model 携带这些字段, 给 LlmRolesTab 用)

## 6. Known Quirks / Pitfalls

- **System prompt 位置**: native API 要求 `system` 作为 top-level parameter, 不能塞进 `messages` 数组. OpenAI 兼容层会自动翻译.
- **Strict JSON schema**: API 拒收 body 里含未知字段, 不要塞自定义 key.
- **max_tokens 必填**: native API `max_tokens` 是 required field, 不像 OpenAI 可选.
- **anthropic-version header**: 必填, 不带会 400.
- **rate limits**: 按 token / minute + request / minute 双限, console 里查具体配额.
- **Extended Thinking 模式**: 需要 `thinking: { type: "enabled", budget_tokens: N }` 显式开启, 默认关闭.

## 7. Testing (cURL)

```bash
curl https://api.anthropic.com/v1/messages \
  --header "x-api-key: $YOUR_API_KEY" \
  --header "anthropic-version: 2023-06-01" \
  --header "content-type: application/json" \
  --data '{
    "model": "claude-haiku-4-5-20251001",
    "max_tokens": 64,
    "messages": [{"role": "user", "content": "ping"}]
  }'
```

拿 model 列表 (Studio Test 用):

```bash
curl https://api.anthropic.com/v1/models \
  --header "x-api-key: $YOUR_API_KEY" \
  --header "anthropic-version: 2023-06-01"
```

## 8. Error Code Reference

| `error_code` (Anthropic 原始) | 含义 | 前端 toast 文案建议 |
|---|---|---|
| `invalid_x_api_key` | API key 无效 | "API key 无效, 请检查粘贴是否完整 (Anthropic key 通常以 `sk-ant-` 开头)" |
| `authentication_error` | 鉴权失败 (header 缺失等) | "鉴权失败, 请确认 x-api-key 和 anthropic-version header 都有" |
| `rate_limit_error` | 限流 | "请求过快, 稍后再试 (Anthropic per-minute limit)" |
| `overloaded_error` | API 临时过载 | "Anthropic 服务暂时过载, 稍后再试" |
| `not_found_error` | model id 不存在 | "model 不存在, 检查 model id 拼写或账户权限" |
| `invalid_request_error` | 请求 body 格式错 | "请求格式错误 (内部 bug, 请联系开发者)" |
