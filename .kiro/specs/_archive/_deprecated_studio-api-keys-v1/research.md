# Studio Copilot LLM API Keys v1 — Research

> **Status**: Draft, v0.1, 2026-05-14
> **Author**: a2 (Gemini) primary, PM (sevenx) 整合

## 1. 业内 Gold Standard 调研

### 1.1 VS Code GitHub Copilot

平台 OAuth + OS-keychain (Windows Credential Manager / macOS Keychain / libsecret). **不适用本场景** — Studio Copilot 是自带云服务模式, 但支持多家自定义 backend, 用户不走平台 OAuth。

### 1.2 Cursor

`~/.cursor/User/settings.json` (JSON file) + OS-level lockfile, 用户在 Settings UI 输入 OpenAI / Anthropic / Cursor 服务自家 key。**File-based + 0600 permission**。改 key 立即生效, 不重启 app。

### 1.3 Continue.dev (VS Code 插件 + Standalone)

`~/.continue/config.json` 含 backend 列表 + active model + 各自 `apiKey` 和 `apiBase`。文件 watcher 监听变化, 也支持每次请求时 fresh read。**File-based + 支持 apiBase 自定义** (OneAPI / Ollama 中转).

### 1.4 Aider

`~/.aider/config.yml` 或环境变量, 用户可在 CLI 启动时切, 也可改文件。**File-based + multi-backend**。

### 1.5 JetBrains AI Assistant

平台账号 OAuth → JetBrains 自家 cloud → 多 backend (含自托管 Ollama)。OS-keychain 存 OAuth token。**桌面 IDE 主流模式, 但对自托管业务过重**。

### 1.6 业内通行模式抽象

| 维度 | VS Code Copilot | Cursor | Continue.dev | Aider | Ollama 桌面 |
|---|---|---|---|---|---|
| Storage | OS-keychain | JSON file 0600 | JSON file 0600 | YAML file 0600 | JSON file |
| Hot reload | 重启 ext | 重启 / refresh | watcher / fresh read | restart CLI | 重启 |
| Multi-backend | 单一 (GitHub) | 多 | 多 | 多 | 单一 |
| apiBase 自定义 | ❌ | 部分 | ✅ | ✅ | ✅ |
| Test connection | (隐式 first request) | (隐式) | ❌ explicit | ❌ | (隐式) |
| OAuth | ✅ | ❌ | ❌ | ❌ | N/A |

**结论**: 对**自定义多 backend + 桌面 IDE**, **File-based + 0600 + fresh read + 可选 apiBase** 是 Continue.dev / Cursor 共同选择, **业内通行**。

## 2. User Scheme B (Rust 注入 env) 不适用本场景 — 已 push back

| | Rust env 注入 (Scheme B, user 直觉) | File-based + fresh read (a2 推荐) |
|---|---|---|
| Hot reload | ❌ 改 env 必重启 Python | ✅ 每次请求 fresh read 即生效 |
| Rust 同步负担 | ❌ Tauri 需保持 env 跟 file 一致 | ✅ Rust 不参与 |
| 跨场景兼容 | ❌ dev tunnel 没 Rust 参与 | ✅ 同一份代码两种场景都 work |
| 业内对齐 | ❌ env 注入是 CI/CD 模式, 不是 IDE 模式 | ✅ Continue.dev / Cursor / Aider 同 |

**结论**: User 直觉 Scheme B 对 `STUDIO_API_TOKEN` 这种"基建级密钥"是对的, 对"用户业务态 LLM key" 是错的。**两个不该混淆**。

## 3. Test Connection 端点设计

各家 LLM provider 的轻量 ping 方式:

| Provider | 推荐 ping 方式 | 成本 |
|---|---|---|
| Claude | `POST messages` `max_tokens: 1`, body `{"messages": [{"role": "user", "content": "."}]}` | ~$0.0001 |
| OpenAI | `GET /v1/models` (列模型, 不耗 token) | $0 |
| DeepSeek | `POST /v1/chat/completions` `max_tokens: 1` (DeepSeek 没 model list endpoint) | ~$0.00001 |
| Gemini | `GET /v1/models` (Google AI Studio 模式) | $0 |

**实施**: 用 SDK 各自的最小请求, 8 秒 timeout, 错误分类 invalid_key / rate_limited / network_error / quota_exceeded。

## 4. V1_5_PLACEHOLDER 历史债

`apps/studio/backend/app/services/copilot_credentials.py` 的 `BackendCredentials.v1_5_placeholder` 字段, 默认 `gemini` / `openai` 为 true 表示 "V1.5 占位"。

**现状**: 没代码消费这个字段 — UI 没读它, 后端 dispatch (`stream_query`) 也没读它。grep 显示只在 `BackendStatus.v1_5_placeholder` 返回字段被 `CredentialsReadResponse` 透传。

**结论**: 死字段, 砍掉 + UI 改用 `has_key` 判 "Not configured"。

**向前兼容**: 已有 `~/.studio/copilot.json` 文件可能含 `V1_5_PLACEHOLDER` 序列化别名, 删字段后 Pydantic 默认 `extra="forbid"` 会拒绝。需要在 model 端临时改 `extra="ignore"` 一次部署或者 a1 写 migration 跳过该字段。简单方案: 砍字段同时改 `extra="ignore"` (反正字段都消失, 多余字段忽略安全)。

## 5. SettingsPage 现状 (已有)

`apps/studio/frontend/src/components/studio/settings-page.tsx` (未追踪文件) 已有骨架 (T3.3 落地):
- 单 page 表单
- Studio User ID 输入
- Gitea Host 输入
- Save 按钮

**本 spec 的改造**: 加入左侧导航 (3 tabs), AI & Copilot tab 加 4 backend 卡片。

## 6. Base URL / Proxy 配置 (PM 自决加入)

a2 followup 提到 OneAPI / Ollama 等国内中转刚需。**PM 决定加入** v1 因为:

1. **业内对齐**: Continue.dev / Aider / 多数 LLM 客户端 都支持
2. **代价小**: schema +1 字段 `base_url: str = ""`, UI +1 折叠区 "Advanced" + 输入框, ~20 行额外代码
3. **国内场景刚需**: trycloudflare tunnel 模式下国内用户从国外 backend 用代理 (如 OneAPI gateway), 不支持 base_url = 不可用
4. **User "copy 业内方案" 直觉一致**

**默认值**: 空 (即用 official endpoint). 用户填了才走代理。**不抛 user 拍板**。

## 7. 跟 brief #1 (tunnel safety) 的交叉点

- Test endpoint 是高危: 攻击者拿 tunnel URL + 没 token 就能调 → 401 拒绝; 但拿到 token 后可以伪造 Test 注入恶意 key 反向 sniff 真 key (在错误响应里 leak 信息) → 后端 Test 响应**不回显 key**, 只回 status code 即可
- SettingsPage 的 PUT /api/copilot/credentials 同样高危 → 同样 Bearer 鉴权保护
- 不冲突, brief #2 直接依赖 brief #1 的鉴权层, 不重复定义

## 8. 跟 production Tauri 兼容性

- Production: Tauri Rust 启动 → `STUDIO_API_TOKEN` env → Python middleware 接受 → SPA Bearer → SettingsPage 调 /api/copilot/credentials 正常
- Tauri 不需要参与 LLM key 任何流程, **Rust 0 改动**
- 文件位置 `~/.studio/copilot.json` 跨场景一致, 用户在 Tauri 包里改 key 跟 dev tunnel 改 key 同一份文件

## 9. 安全考虑

- Test 响应**不能** echo back 输入的 api_key (避免 reflection attack 用 Test endpoint 当 oracle)
- Test 响应**不能** 把 LLM provider 报错原文 stack trace 完整透传 (有些 provider 错误里含 token 前缀, 例如 "Invalid key sk-***" 可能 leak partial input)
- 后端 log 写 Test 调用时 mask 末 4 位再 log; 不写完整 key
- 时序攻击: hmac.compare_digest 已用于 STUDIO_API_TOKEN 比对; LLM key 比对不存在 (用户输入 key 是直接发给 provider, 后端不自己比对 key)

## 10. 参考链接

- Cursor settings JSON: https://docs.cursor.com/configuration/settings
- Continue.dev config: https://docs.continue.dev/setup/configuration
- OneAPI gateway: https://github.com/songquanpeng/one-api
- Anthropic messages API: https://docs.anthropic.com/en/api/messages
- OpenAI models list: https://platform.openai.com/docs/api-reference/models/list
