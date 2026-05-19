# Studio Copilot LLM API Keys v1 — Requirements

> **Status**: Draft, v0.1, 2026-05-14
> **Owner**: PM (sevenx) + a2 (Gemini, UX/security design) + a1 (Codex, implementation)
> **Scope**: SettingsPage 里管理 4 个 LLM backend (claude / openai / deepseek / gemini) 的 API key, 含 test connection + 热加载
> **依赖**: studio-tunnel-safety (鉴权层) + studio-copilot-v1 (后端 copilot 模块)

## 1. 项目根本诉求 (Why)

Studio 的 Copilot feature 调用 Claude / DeepSeek / OpenAI / Gemini 这 4 个 LLM backend, 需要用户提供各自的 API key。当前 (commit 状态):
- 后端: `~/.studio/copilot.json` (0600) 存四个 backend 的 key + active 选择, atomic write 已实现
- 后端 API: `GET/PUT /api/copilot/credentials` (sanitized 状态读 + 写)
- 前端: API 客户端 `apps/studio/frontend/src/api/copilot.ts` 已有, **但 SettingsPage 还没接进 UI**

**痛点**:
- 用户没法在 UI 里配 Copilot key (只能手动改文件)
- 没 test connection 机制, 用户配完不知道 key 对不对
- 历史 `V1_5_PLACEHOLDER` 字段是 V1.5 占位语义, 没用了应砍

## 2. User 原话约束 (verbatim)

来自 user 2026-05-13 的 API key 4 问回复:
> "apikey: 1. 走方案 b rust 注入 env 2. 并进同一套后端底层, 但是 copilot 需要单独的 role 和测试功能, 在 settingpage 里要分隔开 ... 3. 2 个都要; 4. 重启会不会体验很不好啊, 肯定要热加载呀; 我的疑问: 一定是启动时把所有 key 一次性注入吗?"

来自 user 2026-05-14:
> "不要过度考虑向后兼容问题, 过去有不代表对, 现在是原型开发阶段, 做错了就要推翻"
> "思路就是 copy vs code 这种人家已经实现并且论证了的方案"
> "先把这些需求全部做完, 记得写 kiro 文档"

## 3. a2 对 user Scheme B 直觉的 push back (verified)

User 选 "Scheme B Rust 注入 env" 跟 STUDIO_API_TOKEN 模式对齐, **但 LLM key 不适合走 env 注入** (见 design.md §2):
- LLM key 是 "用户业务态配置", 用户随时改 (欠费 / 换账号 / 换 model)
- Env 注入意味着改完必重启 app, 违背 user "热加载"诉求
- Rust ↔ Python 状态同步负担重

**结论**: LLM key 走 **File-based + 每请求 fresh read** (业内 Continue.dev / Cursor / Aider 同模式), 跟 STUDIO_API_TOKEN 解耦。

## 4. 业务需求 (What)

### R1: SettingsPage 加 "AI & Copilot" section

- 左侧导航 (新): `General | AI & Copilot | Advanced` (现状 SettingsPage 已有 General/Studio User ID/Gitea Host, 这次重组)
- AI & Copilot section 列 4 个 backend 卡片 + 顶部 Active backend radio

### R2: 每个 backend 卡片显示

- Backend 名 (Claude / OpenAI / DeepSeek / Gemini)
- API Key 输入框 (mask, 已配的显示 `••••••••<last4>`)
- "Test" 按钮 + 状态 chip (✓ Connected / ⚠ Not configured / ✗ Invalid key / spinner)
- (可选) Active 标识

### R3: Active backend 切换

- 顶部 radio 一次只选一个
- 切换立即调 `PUT /api/copilot/credentials` (body: `set_active: true`)
- 切换后所有 `/api/copilot/query` 调用走新 active

### R4: Save 后立即生效 (隐式热加载)

- 用户改 key → Save → 不需要任何重启 / 重新加载
- 下一次 `/api/copilot/query` 自动用新 key (`read_credentials()` fresh read 已实现)

### R5: Test Connection 端到端

- 前端用户点 "Test" → spinner → 后端 `POST /api/copilot/credentials/test` body `{backend, api_key}`
- 后端用 candidate key (**不写盘**) 发轻量真实 LLM 请求 (Claude messages.create max_tokens=1 / OpenAI models list)
- 成功: 200 `{status: "ok", model_seen: "claude-3-5-sonnet"}`, UI ✓ Connected
- 失败: 4xx `{status: "invalid_key" | "rate_limited" | "network_error", message}`, UI ✗ + 文字提示

### R6: V1_5_PLACEHOLDER 字段砍掉

- `BackendCredentials.v1_5_placeholder` 字段移除 (schema + model)
- 历史 JSON 文件向前兼容 (PydanticAliasChoices 已有, 砍后忽略多余字段或自动跳过)
- 是否 "Not configured" 仅看 `api_key == ""`

### R7: Base URL / Proxy 配置 (PM 自决)

a2 followup 提出: OneAPI / Ollama / 国内中转用户的刚需。**PM 决定**: 本 v1 加上 `base_url` optional 字段, UI 显示 "Advanced" 折叠区, 默认空 = 用 official endpoint, 用户可填代理 URL。**不抛 user 拍板**, 因为 (a) 这是业内 gold standard (Continue.dev / Cursor 都支持), (b) 代价小 (+1 字段 + 1 UI 输入), (c) 跟 user "copy 业内方案" 直觉一致。

### R8: 鉴权层依赖 brief #1

`POST /api/copilot/credentials/test` 是高危 endpoint (任意人能往后端注入恶意 key 反向 sniff key), **必须** 走 brief #1 (`studio-tunnel-safety`) 建立的 Bearer token 鉴权。本 spec 不重复定义鉴权, 复用 c364440 落地的 `configure_api_auth`。

### R9: Tauri 同源 / Tunnel 同源 都正确

- Tauri 包: SPA fetch `127.0.0.1:8787/api/copilot/credentials/test`, 带 `STUDIO_API_TOKEN` Bearer, work
- Dev tunnel: SPA fetch `/api/copilot/credentials/test` (相对路径, Vite proxy 转发), 带 `STUDIO_DEV_TUNNEL_TOKEN` Bearer, work
- 同一份后端代码

## 5. 非业务需求 (Quality)

- **Key 保护**: Test endpoint **不写盘** candidate key, 仅过程内用; 错误响应**不回显** key (避免 attack reflection)
- **UI 反馈延迟**: Test 调用 timeout 8 秒, 8 秒内未返回 UI 显示 "Timeout, retry"
- **Mask 显示规则**: 已配 key 显示 `••••••••` + 末 4 位, 输入框 type="password"
- **Atomic write**: 保持现有 `write_credentials` 的 atomic 行为, 不引入 race

## 6. 验收标准 (DoD)

- [ ] R1: SettingsPage 左侧导航 3 个 tab; AI & Copilot tab 内有 Active radio + 4 个 backend 卡片
- [ ] R2: 已配 backend 显示 mask 末 4 位; 未配显示 "Enter your API key..."
- [ ] R3: 切 Active radio 立即 PUT, page reload 后仍 sticky
- [ ] R4: 改 Claude key → Save → 立即 `/api/copilot/query`, 后端 log 显示用新 key 调 LLM
- [ ] R5: Test 正确 key 显示绿勾; Test 错误 key 显示红叉 + "Invalid key"
- [ ] R6: `copilot.json` 不再含 `V1_5_PLACEHOLDER` 字段; 后端 schema 删除字段; 历史文件加载不报错
- [ ] R7: SettingsPage 有 "Advanced" 折叠区, 可填 base_url, 留空使用 official endpoint
- [ ] R8: Test endpoint 在 tunnel 场景下需要 `STUDIO_DEV_TUNNEL_TOKEN` 鉴权, 公网扫描调用应 401
- [ ] R9: e2e 测试覆盖 Tauri 和 tunnel 两种模式

## 7. 不做的事 (out of scope, 未来 v1.5+)

- ❌ OS keychain 存储 (Linux GNOME Keyring / macOS Keychain) — 现 ~/.studio/copilot.json 0600 已足够
- ❌ OAuth account 集成 (Claude Code OAuth) — v2
- ❌ Per-skill backend override — v2
- ❌ Backend quota / cost tracking UI — v2
- ❌ Auto-refresh key (Anthropic OAuth token rotate) — v2
