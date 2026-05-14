# Studio Dev Tunnel Safety — Requirements

> **Status**: Draft, v0.1, 2026-05-14
> **Owner**: PM (sevenx) + a2 (Gemini, security design) + a1 (Codex, implementation)
> **Scope**: 开发期 Studio 通过 Cloudflare quick tunnel 暴露后端 sidecar 时的完整安全方案
> **不在 scope**: 生产 Tauri 包 (无 tunnel) / Studio Skill 业务逻辑

## 1. 项目根本诉求 (Why)

Studio 是 **Tauri 桌面应用** (Rust 主进程 + Python FastAPI sidecar + React SPA WebView)。生产分发是 Tauri 安装包, 进程间通信走 `127.0.0.1:8787` Bearer token + `STUDIO_API_TOKEN` env, **不接公网**。

**但开发期** 主开发者 (sevenx) 需要在手机 / 远程浏览器看 Studio web 界面。当前手段:
- 后端 (8787 FastAPI) 通过 `cloudflared tunnel --url http://127.0.0.1:8787 --no-autoupdate` 暴露到 `https://<X>.trycloudflare.com`
- 前端 (5173 Vite) 通过另一条 `cloudflared` 暴露到 `https://<Y>.trycloudflare.com`
- 手机浏览器先打开前端 tunnel URL, SPA fetch 后端 tunnel URL

**风险**: `trycloudflare` quick tunnel 的 URL 是**随机 + 公网可达 + 证书透明度 (CT) 日志可索引**, 任意外部扫描者扫到 URL 就能调任何 backend endpoint, 当前 dev mode bypass (`STUDIO_API_TOKEN` 未设 → warn 一次 → 放行所有请求) **等于把 `POST /api/skills` (能写 SKILL.md 注入 Python 代码) 公开给互联网**。

## 2. User 原话约束 (verbatim, do not paraphrase)

- "不要过度考虑向后兼容问题, 过去有不代表对, 现在是原型开发阶段, 做错了就要推翻, 哪怕整个 app 也是" (2026-05-14)
- "思路就是 copy vs code 这种人家已经实现并且论证了的方案" (2026-05-14)
- "1、2 我都同意, 3 要问 gemini, 我不懂, 我感觉 tauri 唯一 caller 应该就够了" (2026-05-13) — *Tauri 单 caller 直觉在 tunnel 场景已被 verify 为不够, 见 design.md §1*
- "backend tunnel 安全问题让 Gemini 设计解决" (2026-05-14, 本任务触发)

## 3. 业务需求 (What)

### R1: 后端 `127.0.0.1:8787` 不暴露公网
后端 FastAPI 端口在浏览器看来不应该直接可触达。哪怕加了 Bearer token, **平白增加公网暴露面** = 攻击者拿到 token 后能直接打后端绕过任何前端层防御。

### R2: 强鉴权强制 (杜绝 dev bypass)
开发期 tunnel 启动时**必须**强制鉴权, 不允许 silent fallback 到无 token 模式。当前 `configure_api_auth` 在 `STUDIO_API_TOKEN` 未设时 "warn one + 放行所有请求" 的 dev bypass **必须废除**或**改为强制要求 dev tunnel token**。

### R3: Token 生命周期一次性
开发 session 启动 → 自动生成新 token → 进程注入 → 输出带 token 的入口 URL → 关闭终端 → token 失效。**不需要复杂 rotate 机制**。

### R4: User 拿 token 不能写代码
用户在手机或远程浏览器**只需要扫码 / 复制一次 URL**, token 已嵌在 URL hash 里, 无需手动输入。

### R5: Token 不能在 URL access log 泄露
不能用 `?tkn=xxx` 这种 query parameter, 因为 Cloudflare 边缘节点会记录到 access log。必须用 URL hash (`#tkn=xxx`), 因为 hash 不会发给中间节点。

### R6: SPA 拿到 token 后立刻擦除 URL
SPA 启动读 `window.location.hash`, 存内存 / sessionStorage, 然后 `history.replaceState` 把 token 从浏览器地址栏抹掉, 防止用户复制 URL 分享时泄露。

### R7: Token env 命名跟 production Tauri 隔离
生产 Tauri 用 `STUDIO_API_TOKEN`, 开发 tunnel 用独立的 `STUDIO_DEV_TUNNEL_TOKEN`, 互不污染。

### R8: 复用 brief #1 的鉴权中间件
不要重写鉴权层。`configure_api_auth` (apps/studio/backend/app/main.py) 已经在 c364440 落地, 改造为同时接受 `STUDIO_API_TOKEN` 或 `STUDIO_DEV_TUNNEL_TOKEN`, 任一匹配即放行。

### R9: 启动脚本一键拉起
单一命令完成: 生成 token → 启动 backend (env 注入) → 启动 Vite (proxy 配置生效) → 启动 1 条 cloudflared → 拼装入口 URL → 终端打印 QR code + URL。

### R10: 兼容生产 Tauri 模式
backend `configure_api_auth` 必须在生产 Tauri 包 (有 STUDIO_API_TOKEN, 无 STUDIO_DEV_TUNNEL_TOKEN) 和开发 tunnel 模式 (无 STUDIO_API_TOKEN, 有 STUDIO_DEV_TUNNEL_TOKEN) 两种场景都正确运作, **无需为开发期单独维护一份代码路径**。

## 4. 非业务需求 (Quality)

- **安全**: 推翻"URL 私密 = 安全"假设; 鉴权层是唯一防线, dev bypass 必须废除
- **简单**: 不引入 Cloudflare Access (quick tunnel 不支持) / 不引入 `/auth/login` 页面 (体验过重) / 不引入 token rotate 机制
- **本地无 CORS 痛点**: Vite proxy 模式下浏览器只看 1 个 tunnel origin, **不需要**继续维护 `STUDIO_CORS_EXTRA_ORIGINS` 动态白名单
- **手机扫码可用**: 终端打印 ASCII QR code 携带带 hash 的入口 URL

## 5. 验收标准 (DoD)

- [ ] R1 实证: 删除后端 tunnel, 浏览器从手机访问 backend tunnel URL 应 ENOTFOUND; 通过前端 tunnel URL 加载 SPA, SPA 经 Vite proxy 调 backend 正常
- [ ] R2 实证: backend 启动**不带** `STUDIO_DEV_TUNNEL_TOKEN` env 且**不带** `STUDIO_API_TOKEN` 应该**拒绝启动** (不是 warn one fallthrough)
- [ ] R3 实证: 关闭启动脚本终端 → 重启 → token 应该变化, 旧 URL hash 应该失效
- [ ] R5 实证: backend access log + cloudflared log 抓取应**不包含** token 字符串
- [ ] R6 实证: 手机浏览器加载 URL → `window.location.hash` 应该被 replaceState 抹掉
- [ ] R7 实证: production Tauri 包 (生产构建) 启动后只见 `STUDIO_API_TOKEN`, `STUDIO_DEV_TUNNEL_TOKEN` 不存在, `/api/copilot/query` 正常工作
- [ ] R9 实证: 一行 `make dev-tunnel` (或 `python scripts/dev-tunnel.py`) 完整启动 backend + Vite + cloudflared + 打印 QR

## 6. 不做的事

- ❌ Cloudflare Access 集成 (quick tunnel 不支持, named tunnel 太重)
- ❌ `/auth/login` 用户名密码页面 (体验过重)
- ❌ Token rotate (一次性, session-bound 就够)
- ❌ 多用户 / 团队访问 (sevenx 单人开发)
- ❌ 后端 tunnel (设计上彻底废除, 不只是关掉)
- ❌ 动态 CORS 白名单 (同源 proxy 后不需要)
