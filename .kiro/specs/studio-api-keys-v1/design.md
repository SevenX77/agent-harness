# Studio Copilot LLM API Keys v1 — Design

> **Status**: Draft, v0.1, 2026-05-14
> **Author**: a2 (Gemini) primary, PM (sevenx) 整合
> **Implementer**: a1 (Codex)
> **Pattern reference**: Continue.dev / Cursor settings.json file model

## 1. Architecture

### 1.1 Data flow

```
[SettingsPage UI]
       │
       ├─ GET  /api/copilot/credentials      ─→ sanitized 状态 (has_key, last4, base_url)
       ├─ PUT  /api/copilot/credentials      ─→ 写新 key / 切 active
       └─ POST /api/copilot/credentials/test ─→ 用 candidate key 拨 LLM 一下
                                                 │
                                                 ▼
                                          [LLM Provider]

[/api/copilot/query]
       │
       ▼
    read_credentials() ──fresh read──→ ~/.studio/copilot.json
       │
       ▼
    stream_query(active_backend, api_key, message)
```

**关键**: `/api/copilot/query` 每次 fresh read, **不 cache key 在 memory**, 保证 PUT 后下一个 query 立即用新 key (零重启热加载)。

## 2. Storage Schema 演进

### 2.1 现状 (`~/.studio/copilot.json`)

```json
{
  "backends": {
    "claude":   { "api_key": "", "V1_5_PLACEHOLDER": false },
    "deepseek": { "api_key": "", "V1_5_PLACEHOLDER": false },
    "gemini":   { "api_key": "", "V1_5_PLACEHOLDER": true  },
    "openai":   { "api_key": "", "V1_5_PLACEHOLDER": true  }
  },
  "active_backend": "claude"
}
```

### 2.2 v1 (本 spec)

```json
{
  "backends": {
    "claude":   { "api_key": "", "base_url": "" },
    "deepseek": { "api_key": "", "base_url": "" },
    "gemini":   { "api_key": "", "base_url": "" },
    "openai":   { "api_key": "", "base_url": "" }
  },
  "active_backend": "claude"
}
```

**变化**:
- 砍 `V1_5_PLACEHOLDER` 字段 (历史债)
- 加 `base_url: str = ""` (可选, 空表示用 official endpoint)

**向前兼容**: Pydantic 模型改 `extra="ignore"`, 老文件含 `V1_5_PLACEHOLDER` 加载时自动跳过, 不报错。

## 3. 后端 API

### 3.1 `GET /api/copilot/credentials` (已有, 改 schema)

Response:
```json
{
  "backends": {
    "claude":   { "has_key": true,  "last4": "4xyz", "base_url": "" },
    "deepseek": { "has_key": false, "last4": null,   "base_url": "https://api.deepseek.com" },
    "gemini":   { "has_key": false, "last4": null,   "base_url": "" },
    "openai":   { "has_key": false, "last4": null,   "base_url": "" }
  },
  "active_backend": "claude"
}
```

**变化**: 砍 `V1_5_PLACEHOLDER`, 加 `last4` (mask 末 4 位) + `base_url`。

### 3.2 `PUT /api/copilot/credentials` (已有, 改 schema)

Request:
```json
{
  "backend": "claude",
  "api_key": "sk-ant-...",     // null = 不改; "" = 清空; 其他 = 设值
  "base_url": null,            // null = 不改; "" = 清空; 其他 = 设值
  "set_active": false
}
```

Response: 同 GET schema (sanitized 后状态)。

### 3.3 `POST /api/copilot/credentials/test` (新)

Request:
```json
{
  "backend": "claude",
  "api_key": "sk-ant-...",     // candidate, 不写盘
  "base_url": ""               // candidate, 不写盘
}
```

Response (success):
```json
{
  "status": "ok",
  "latency_ms": 234,
  "model_seen": "claude-3-5-sonnet-20240620"   // (仅在 provider 返回 model name 时填; 否则省略)
}
```

Response (failure, 4xx):
```json
{
  "status": "invalid_key" | "rate_limited" | "quota_exceeded" | "network_error" | "timeout",
  "message": "Invalid API key (provider returned 401)"   // 后端构造, **不透传 provider raw error**
}
```

**实施细节**:
- 用 candidate key + base_url 各自 backend SDK 发轻量请求 (Claude messages max_tokens=1, OpenAI models list, DeepSeek messages max_tokens=1, Gemini models list)
- 8 秒 timeout
- 错误分类逻辑: HTTP 401 → invalid_key; HTTP 429 → rate_limited; HTTP 402 / quota error → quota_exceeded; ConnectionError → network_error; asyncio.TimeoutError → timeout
- **不写盘**, candidate 仅函数局部用
- Log: `logger.info("test_credentials backend=%s last4=%s status=%s latency=%dms")`, 不 log 完整 key

### 3.4 鉴权 (依赖 brief #1)

3 个 endpoint 全部走 `configure_api_auth` middleware (无新代码), Bearer token 校验通过才放行。tunnel 场景下没 `STUDIO_DEV_TUNNEL_TOKEN` Bearer 直接 401。

## 4. 前端

### 4.1 SettingsPage 重构

**`apps/studio/frontend/src/components/studio/settings-page.tsx`** 重写:

布局:
```
┌──────────┬──────────────────────────────────────────────────────┐
│ General  │                                                      │
│ AI & Co. │   (active tab 内容)                                  │
│ Advanced │                                                      │
└──────────┴──────────────────────────────────────────────────────┘
```

3 个 tab:

#### General tab (从现状抽出)
- Studio User ID 输入
- Gitea Host 输入

#### AI & Copilot tab (新)
```
Active Backend: ( ) Claude  (•) DeepSeek  ( ) OpenAI  ( ) Gemini

┌──────────────────────────────────────────────────────────────┐
│ Claude                                                       │
│ API Key:  [ •••••••••••••••4xyz                  ] [Test ✓] │
│ Base URL: [ ◀ Advanced (use official endpoint) ▶ ]          │
├──────────────────────────────────────────────────────────────┤
│ DeepSeek (Active)                                            │
│ API Key:  [ Enter your API key...                ] [Test]   │
│ Base URL: [ ◀ Advanced ▶ ]                                   │
│                                                              │
│   (展开后)                                                    │
│   ┌────────────────────────────────────────────────────┐    │
│   │ Custom Base URL (optional, OneAPI / Ollama / etc): │    │
│   │ [ https://api.openai.example.com                ] │    │
│   └────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
... (3 more backend cards)
```

每个卡片状态机:
- `idle`: 输入框可编辑, Test 按钮可点
- `testing`: Spinner + disabled
- `ok`: 绿勾 + "Connected" + Save 按钮高亮
- `error`: 红叉 + 错误描述 + Save 仍可 (用户决定)

#### Advanced tab (skeleton, 未来扩展)
- 占位空 tab, 显示 "More settings coming soon"
- 跟 General 一样可继续扩展 (e.g. Theme, Log level)

### 4.2 API 客户端

**`apps/studio/frontend/src/api/copilot.ts`** 增方法:
```typescript
export interface BackendStatus {
  has_key: boolean;
  last4: string | null;
  base_url: string;
}

export interface CredentialsResponse {
  backends: Record<CopilotBackend, BackendStatus>;
  active_backend: CopilotBackend;
}

export async function readCopilotCredentials(): Promise<CredentialsResponse> { ... }

export async function writeCopilotCredentials(req: {
  backend: CopilotBackend;
  api_key?: string | null;
  base_url?: string | null;
  set_active?: boolean;
}): Promise<CredentialsResponse> { ... }

export interface TestResult {
  status: 'ok' | 'invalid_key' | 'rate_limited' | 'quota_exceeded' | 'network_error' | 'timeout';
  latency_ms?: number;
  model_seen?: string;
  message?: string;
}

export async function testCopilotCredentials(req: {
  backend: CopilotBackend;
  api_key: string;
  base_url?: string;
}): Promise<TestResult> { ... }
```

### 4.3 SettingsPage 状态管理

每个 backend 独立 useState (4 个 backends × `{key_draft, base_url_draft, test_state, dirty}` state)。Save 按钮只在 dirty 时高亮 + diffs 提交。Active backend 切换不需要 Save, radio 改完立即 PUT。

## 5. 安全细节

### 5.1 Test endpoint 防 reflection

- Response 中**不回显** `api_key` (哪怕 hash)
- 错误 message 由后端构造, **不**透传 provider 的 raw response body (raw response 可能含 partial input echo)
- 后端 log mask: `f"backend={backend} last4={api_key[-4:]} status={status}"`, 不 log 完整 key

### 5.2 输入框 mask

- 已有 key: 显示 `••••••••<last4>`, 用户点 "Edit" 才显示输入框 (type="password")
- 输入框 type="password" 浏览器自动隐藏字符
- 浏览器 autofill 注意: input name 加 `autocomplete="off"`

### 5.3 Save → 立即生效, 无需重启

- Save → PUT → `write_credentials()` atomic write 写盘
- 下一次 `/api/copilot/query` → `read_credentials()` fresh read → 新 key 立即生效
- 不需要 Rust IPC, 不需要 Python 重启

## 6. Production Tauri 兼容性

| 场景 | 路径 |
|---|---|
| Tauri 包启动 | Rust spawn Python with `STUDIO_API_TOKEN` env |
| SPA 加载 | WebView 本地 file://, `getSidecarConfig` 拿 token, `configureApiToken(token)` |
| SettingsPage 调 `/api/copilot/credentials/test` | axios 自动加 Bearer, middleware 接受, 走 LLM provider |
| 改 key Save | PUT 写 `~/.studio/copilot.json`, 0600 perms |
| 下次 Copilot query | fresh read `~/.studio/copilot.json`, 用新 key |

**0 Rust 改动**, 跟 dev tunnel 模式共用同一份后端 + 前端代码。

## 7. 命名一致性 (跟 brief #1 对照)

| Env | 场景 | 跟本 spec 关系 |
|---|---|---|
| `STUDIO_API_TOKEN` | Tauri-only API auth | 本 spec 走鉴权依赖, 不变 |
| `STUDIO_DEV_TUNNEL_TOKEN` | Dev tunnel auth | 本 spec 走鉴权依赖, 不变 |
| (无新 env) | — | 本 spec **不引入新 env** |

LLM key 永远是文件 (`~/.studio/copilot.json`), **不**进 env。这是有意的, 见 research.md §2。

## 8. 不引入的复杂度

- ❌ Rust IPC 调用 backend 写文件 (Python 直接写就好)
- ❌ OS keychain 集成 (~/.studio/0600 已足够 v1)
- ❌ File watcher (fresh read 每请求已足够, watcher 是 over-engineering)
- ❌ Per-skill backend override (v2)
- ❌ Quota tracking UI (v2)
- ❌ OAuth flow (v2, 各家 LLM provider OAuth 都是单独工程)
