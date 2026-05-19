---
status: Living
target_goal: "Studio MVP — 让 PM 可用"
---

# Google Gemini API Configuration Guide

## 1. Supported SDKs & Protocols

- **Primary Protocol Enum**:
  - `gemini_official` — native API, 走 `:generateContent` / `:streamGenerateContent`, 支持 grounding / Code Execution / Search 等 google-only 特性
  - 或 `openai_compatible` — **2024-11 起** Google 加了 OpenAI 协议兼容 endpoint, 直接用 `openai` SDK 改 base_url 即可调 Gemini
- **Native SDK**: `google-generativeai` Python ([docs](https://ai.google.dev/gemini-api/docs))
- **Alternative Endpoints**:
  - **Vertex AI**: GCP 部署, 走 `https://{region}-aiplatform.googleapis.com/...` + IAM/service account 鉴权 (v2.1 不支持)

## 2. Authentication

### Native (gemini_official)

- **Method**: API key 作为 query param, **或** Bearer header
- **Query param sample**:
  ```
  GET https://generativelanguage.googleapis.com/v1beta/models?key=<YOUR_KEY>
  ```
- **Header sample** (现也支持):
  ```
  Authorization: Bearer <YOUR_KEY>
  ```

### OpenAI 兼容 endpoint

- **Method**: 标准 Bearer
- **Header sample**:
  ```
  Authorization: Bearer <YOUR_KEY>
  ```

- **拿 key**: [aistudio.google.com](https://aistudio.google.com/app/apikey)

## 3. Base URL

- **Native**: `https://generativelanguage.googleapis.com/v1beta`
- **OpenAI 兼容**: `https://generativelanguage.googleapis.com/v1beta/openai/`
  - 用 openai SDK 时直接 `openai.OpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/", api_key="...")`

## 4. Notable Model IDs

v2.1 默认列表:

- `gemini-3.1-pro-preview` — 旗舰 (2026 当前)
- `gemini-2.5-pro` — 上一代旗舰
- `gemini-2.5-flash` — 平衡 / 快
- `gemini-2.0-flash` — legacy fast
- `gemini-2.0-flash-thinking-exp` — thinking 实验版

## 5. 能力维度

| Model | thinking | tool_calling | vision | max_context_tokens |
|---|---|---|---|---|
| `gemini-3.1-pro-preview` | ✓ | ✓ | ✓ | 2000000 (2M) |
| `gemini-2.5-pro` | ✓ | ✓ | ✓ | 2000000 |
| `gemini-2.5-flash` | ✓ | ✓ | ✓ | 1000000 |
| `gemini-2.0-flash-thinking-exp` | ✓ | ✓ | ✓ | 1000000 |

## 6. Known Quirks / Pitfalls

- **OpenAI 兼容 endpoint 不支持所有 native 特性** — grounding (Google Search 接入) / Code Execution / Function Declaration 高级模式只能走 native protocol
- **Native protocol 的 message format 不同** — `contents` 数组而非 `messages`, role 用 `model` 而非 `assistant`
- **System instruction 字段名** — native 是 `systemInstruction` (camelCase), 不是 `system`
- **`response_mime_type`** — native protocol 控制 JSON / structured output 的字段, 跟 OpenAI 的 `response_format` 不同
- **API key vs OAuth**: Studio v2.1 走 API key. OAuth (Workforce / Google One Ultra plan 类) 暂不支持
- **Free tier limits**: AI Studio 免费但 rate limit 严, 生产建议走付费 tier 或 Vertex AI
- **Region availability**: 部分模型在欧盟等 region 不可用, key 不变但请求会 403

## 7. Testing (cURL)

### Native protocol

```bash
# 拿 model 列表
curl "https://generativelanguage.googleapis.com/v1beta/models?key=$GEMINI_API_KEY"

# minimal generation 测 key
curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=$GEMINI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "contents": [{"parts": [{"text": "ping"}]}],
    "generationConfig": {"maxOutputTokens": 8}
  }'
```

### OpenAI 兼容 endpoint

```bash
curl https://generativelanguage.googleapis.com/v1beta/openai/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $GEMINI_API_KEY" \
  -d '{
    "model": "gemini-2.5-flash",
    "messages": [{"role": "user", "content": "ping"}],
    "max_tokens": 8
  }'
```

## 8. Error Code Reference

| HTTP / `error_code` | 含义 | 前端 toast 文案建议 |
|---|---|---|
| `400 INVALID_ARGUMENT` | 请求格式错 (常见: model id 拼错, message 字段错) | "请求格式错误 (检查 model id 或内部 bug)" |
| `401 UNAUTHENTICATED` | API key 无效 / 过期 | "Gemini API key 无效, 请重新生成 (key 通常以 `AIza` 开头)" |
| `403 PERMISSION_DENIED` | key 没该 model 权限 / region 限制 | "当前 key 没有此 model 权限, 或 region 不可用" |
| `429 RESOURCE_EXHAUSTED` | rate limit / quota 超 | "请求过快或额度耗尽, 稍后再试或升级 tier" |
| `500 INTERNAL` | Google 服务端错 | "Google 服务暂时异常, 稍后再试" |
| `503 UNAVAILABLE` | 服务临时不可用 | "Google 服务暂时不可用, 稍后再试" |
