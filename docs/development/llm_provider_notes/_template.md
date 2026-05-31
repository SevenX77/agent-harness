---
status: Living
target_goal: "Studio MVP — 让 PM 可用"
---

# [Vendor Name] API Configuration Guide

> 拷贝此文件为 `<vendor>.md`, 填完后到 `README.md` 速查表加一行索引.

## 1. Supported SDKs & Protocols

- **Primary Protocol Enum**: `openai_compatible` (改成实际的)
- **Native SDK** (如有): 包名 + 链接
- **Alternative Endpoints**: e.g., Azure / Vertex AI / Bedrock 部署变体

## §1.5 探测元数据 (round 3 新增, 用于 Studio 自动 Test 探测)

```yaml
compatible_sdks:
  # 该 vendor 的 API 兼容哪些 SDK enum
  # 已有 enum: anthropic_compatible / openai_compatible / google_genai
  - <sdk_enum>

models_endpoint_path: "<path>" | null
  # GET <base_url><path> 返回 models 列表 (e.g., OpenAI: "/v1/models")
  # null = 该 vendor 没有 models endpoint, Studio 走 §4 Notable Model IDs fallback (e.g., Anthropic)

auth_header_format: |
  Header1: <template>
  Header2: <template>
  # 含 ${key} 占位符, Studio Test handler 用 user 填的 key 填入
  # 例: OpenAI "Authorization: Bearer ${key}"
  # 例: Anthropic "x-api-key: ${key}\nanthropic-version: 2023-06-01"
```

## 2. Authentication

- **Method**: Bearer Token / `x-api-key` header / Query param
- **Header 完整 sample**:
  ```
  Authorization: Bearer <YOUR_KEY>
  ```
- **拿 key 的位置**: `[URL to dashboard / console]`

## 3. Base URL

- **Official Endpoint**: `https://api.vendor.com/v1`
- **变体** (region / cloud 部署 / OpenAI 兼容子路径):
  - Azure: `https://...`
  - Compatibility 子路径: `https://...`

## 4. Notable Model IDs

后端 API 接受的 exact string. v2.1 默认列表 (不穷举, 只列 ship-blocking 的常用):

- `model-id-1` — 描述 + 用例
- `model-id-2` — 描述 + 用例

## 5. 能力维度 (Test 成功后后端应当返回)

- `thinking`: ✓ / ✗ — 是否支持 thinking mode
- `tool_calling`: ✓ / ✗
- `vision`: ✓ / ✗
- `max_context_tokens`: 数字 (e.g., 200000)

## 6. Known Quirks / Pitfalls

- system prompt 处理差异 (e.g., 必须 top-level / 必须在 messages 数组 first)
- 严格 JSON schema 拒收未知字段?
- max_tokens 上限 / temperature 范围限制
- streaming 支持范围
- rate limit 默认值

## 7. Testing (cURL)

```bash
# 完整可复制的 minimal 测试请求, 检查 key 可用性
curl https://api.vendor.com/v1/...
```

## 8. Error Code Reference (Test 失败时前端展示)

| `error_code` | 含义 | 用户应做什么 |
|---|---|---|
| `invalid_x_api_key` | API key 错或过期 | 重新生成 / 检查粘贴是否截断 |
| `rate_limited` | 临时限流 | 稍后再试 |
| `quota_exceeded` | 账户额度耗尽 | 充值 / 升级 plan |
