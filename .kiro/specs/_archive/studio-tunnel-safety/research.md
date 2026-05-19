# Studio Dev Tunnel Safety — Research

> **Status**: Draft, v0.1, 2026-05-14
> **Author**: a2 (Gemini) design, PM (sevenx) 整合
> **Purpose**: 业内 gold standard 调研 + 当前攻击面分析

## 1. 业内 Gold Standard 调研

### 1.1 Jupyter Notebook / JupyterLab

启动时 `secrets.token_urlsafe(32)` 生成 token, 打印入口 URL `http://localhost:8888/?token=xxx` 或 `#token=xxx`。SPA 读 token 后存 cookie / sessionStorage, 之后所有请求自动带。Jupyter 历史经验**已经从 query param 转向 URL hash**, 因为 query 会在反向代理 / Cloudflare 边缘的 access log 留痕。

### 1.2 Code-Server (VS Code Web)

跟 Jupyter 同模式。启动时生成随机 password / token, 通过 URL hash 投递。**SPA 第一时间 history.replaceState 抹掉 URL** 防截图泄露。Code-Server 支持 Cloudflare Access 接管鉴权 (named tunnel + zero-trust), 但 quick tunnel 不支持。

### 1.3 VS Code Remote Tunnels

`code tunnel` 命令拉起 tunnel, 需要登录 GitHub / Microsoft 账号绑定 tunnel 名, 浏览器访问 `vscode.dev/tunnel/<name>` 走 zero-trust 鉴权。**不适用本场景** — 我们用的是 quick tunnel, 不是 named tunnel + 账号体系, 引入账号体系成本太高。

### 1.4 GitHub Codespaces / Gitpod

每个 codespace 是独立 VM, 公网 URL 走 GitHub Auth (cookie session) 鉴权。**Token 与开发环境生命周期绑定** — VM 销毁就 token 失效, **阅后即焚, 重启即换**。本方案借鉴这个生命周期模式。

### 1.5 Cloudflare Access (Zero-Trust)

要求 named tunnel + DNS 配置 + Cloudflare Access policy, 用户登录 OneTimePin / Google / GitHub OAuth。**不适用 trycloudflare quick tunnel** — quick tunnel 没法挂 Access policy。如果未来切 named tunnel, 这是终极方案。

### 1.6 业内通行模式抽象

| 维度 | Jupyter / Code-Server | Codespaces | VS Code Remote Tunnels |
|---|---|---|---|
| Token 投递 | URL hash | Cookie 会话 | 浏览器 OAuth |
| 生命周期 | session-bound | VM-bound | 账号-bound |
| 复杂度 | 低 | 中 | 高 |
| Quick tunnel 兼容 | ✅ | ❌ | ❌ |

**结论**: Jupyter / Code-Server 的 URL hash + session-bound 模式是 **trycloudflare quick tunnel 场景下唯一可行 + 业内成熟的方案**。

## 2. 当前 agent-harness tunnel 拓扑下的攻击面

### 2.1 拓扑 (verify 后准确)

```
[User 手机] ──https──> [Cloudflare 前端 tunnel <X>.trycloudflare.com]
                              │
                              ▼ tunnel
                       [VPS:5173 Vite Dev Server]
                              │
                              ▼ SPA fetch /api/...
                              │ (当前: 浏览器 fetch 后端 tunnel URL)
                              ▼
        [Cloudflare 后端 tunnel <Y>.trycloudflare.com]
                              │
                              ▼ tunnel
                       [VPS:8787 FastAPI]
```

### 2.2 当前 dev bypass 下的攻击场景

`STUDIO_API_TOKEN` 未设 → 全局 middleware 放行所有请求 → 任意公网调用者扫到 `<Y>.trycloudflare.com` 后能:

1. **`GET /api/skills`**: 列举所有 skill ID + metadata (信息泄露)
2. **`POST /api/skills`**: 创建新 skill, 在 SKILL.md 里塞 `python: { code: "import os; os.system(...)" }` 类指令; 调用 `/api/skills/{id}/runs` 触发执行 → **任意命令执行 (RCE)**
3. **`PUT /api/copilot/credentials`**: 修改 Copilot LLM key, 把 user 的 Claude / OpenAI key 改成攻击者控制的代理 → **key 窃取 + 后续对话内容劫持**
4. **`POST /api/copilot/query`**: 用 user 已配 key 调 Claude API, 烧 user 配额或 prompt injection (信任域内 SPA 看到的内容)
5. **`GET /api/settings`**: 读 Studio User ID + Gitea Host, 进一步定位用户 Gitea 仓库 → social engineering 入口
6. **WebSocket `/ws/runs/{id}`**: 实时窃听 skill 运行流, 包括 LLM 流输出, 可能含敏感工作内容

### 2.3 损失等级

- **机密性**: 高 (LLM key 被改, Gitea host 泄露, 工作流被监听)
- **完整性**: 高 (任意 RCE, 文件系统污染, Gitea 仓库可能被改)
- **可用性**: 中 (烧 LLM 配额, 烧 VPS CPU)

**结论**: 当前 dev bypass = **生产级 RCE 暴露**, 必须废除。

## 3. URL Hash vs Query Parameter 安全对比

| | URL Hash (`#tkn=xxx`) | URL Query (`?tkn=xxx`) |
|---|---|---|
| 浏览器记录 history | ✅ 记录 (含 hash) | ✅ 记录 (含 query) |
| HTTP request 头中 | ❌ 不发送 | ✅ 发送 (Request-URI) |
| Cloudflare 边缘 access log | ❌ 不记录 | ✅ 记录 (Request-URI 完整 log) |
| 反向代理 / Nginx access log | ❌ 不记录 | ✅ 记录 |
| Referrer header 跨域泄露 | ❌ 不泄露 (浏览器策略) | ✅ 可能泄露 |
| JS 读取 | `window.location.hash` | `URLSearchParams(window.location.search)` |
| Server 可见 | ❌ 看不到 | ✅ 看得到 |

**结论**: 强烈倾向 hash, 业内 (Jupyter / Code-Server / OAuth implicit flow) 都用 hash 传 sensitive token。

## 4. Vite Proxy 同源模式可行性

Vite Dev Server 内置 `server.proxy` 配置 (基于 `http-proxy-middleware`), 可以把 `/api/*` 和 WebSocket 流量转发到本地 `127.0.0.1:8787`。SPA 在浏览器看来调的是 `https://<X>.trycloudflare.com/api/...` 同源请求, **不触发 CORS preflight**, **不需要后端 tunnel**。

WebSocket 也支持 (`ws: true`)。Vite 5+ 默认行为足够。

**生产 Tauri 模式**不走 Vite, SPA 直接调 `http://127.0.0.1:8787/api/...` (跟 Tauri 主进程同机)。**不需要 proxy**, 不需要 `STUDIO_DEV_TUNNEL_TOKEN`, 只用 `STUDIO_API_TOKEN`。

## 5. Token 命名: 单 env vs 双 env

| | 单 env (`STUDIO_API_TOKEN`) | 双 env (`STUDIO_API_TOKEN` + `STUDIO_DEV_TUNNEL_TOKEN`) |
|---|---|---|
| 命名清晰 | ❌ 同名跨场景, 易混淆 | ✅ 各负其责 |
| 中间件实现 | 简单 (一个 token) | 略复杂 (任一匹配即放行) |
| Production / Dev 隔离 | ❌ 同 env 名 | ✅ 独立 env 名 |
| Token rotate 影响面 | 同 token 跨场景 rotate 都受影响 | dev token 一次性, prod token 长寿 |

**结论**: 双 env 命名更干净, 跟 production Tauri 模式天然兼容。

## 6. Tauri-Only Caller 直觉的失效

**user 之前选了 "127.0.0.1 + Tauri 唯一 caller 就够"** — 这是 production Tauri 包 (Rust spawn Python, 进程间 IPC) 场景的对的判断。

**但 tunnel 场景下这个直觉根本不成立**:
- tunnel 把 `127.0.0.1:8787` 透到公网, "127.0.0.1 only" 物理上不存在
- 同机进程能扫端口的旧问题在 tunnel 场景下放大成 "全互联网都能扫端口"
- Tauri WebView 这一层在 tunnel 场景下根本不参与, browser 直接 SPA

a2 的设计推翻这个直觉是正确的 — **tunnel 安全独立于 Tauri caller 安全**, 必须按公网暴露面来防御。

## 7. 跟 brief #2 (API Key UI) 的交叉点

- API Key UI 写新 endpoint (`POST /api/copilot/credentials/test`) 时, 要跑在同一套 `configure_api_auth` 中间件下, 自动继承 token 鉴权
- SettingsPage 在 tunnel 场景下也是 SPA 同源调用, 不需要额外 CORS 调整
- 不冲突, brief #1 和 #2 在鉴权层共享同一 middleware

## 8. 参考链接

- Jupyter token model: https://jupyter-notebook.readthedocs.io/en/stable/security.html
- Code-Server: https://github.com/coder/code-server
- VS Code Remote Tunnels: https://code.visualstudio.com/docs/remote/tunnels
- GitHub Codespaces auth: https://docs.github.com/en/codespaces
- Cloudflare quick tunnel limitations: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/
- Vite server.proxy: https://vitejs.dev/config/server-options.html#server-proxy
