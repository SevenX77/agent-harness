# Studio Dev Tunnel Safety — Tasks

> **Status**: Draft, v0.1, 2026-05-14
> **Implementer**: a1 (Codex)
> **Spec link**: requirements.md / design.md / research.md
> **Branch**: feat/studio-dev-tunnel-safety (待 a1 创建)
> **预估**: 总 ≈ 8 小时 a1 工作时间

## 任务总览

```
T1  后端 middleware 改造 (双 token 接受, 推翻 dev bypass)        ── 2h
T2  WebSocket 鉴权扩展                                            ── 1h
T3  前端 token bootstrap (URL hash 读取 + replaceState 抹除)       ── 1.5h
T4  Vite proxy 配置 (vite.config.ts + /api + /ws + allowedHosts)   ── 1h
T5  启动脚本 scripts/dev-tunnel.py (生成 token + 拉子进程 + QR)     ── 2h
T6  端到端验证 (R1-R7 + R9-R10 验收清单)                            ── 1h
```

各 task 落地后, a1 写测试 + 自审 + a3 review e2e (按 SOP 矩阵)。

---

## T1: 后端 middleware 改造 (双 token + 拒绝 bypass)

### 文件 + 改动

**`apps/studio/backend/app/main.py`** (修改 `configure_api_auth`):

1. 同时读 `STUDIO_API_TOKEN` + `STUDIO_DEV_TUNNEL_TOKEN` env, 构 `valid_tokens` 列表
2. **两者都空 → `raise RuntimeError`, 拒绝启动** (推翻原 dev bypass)
3. middleware 内对每个 token 都用 `hmac.compare_digest` 比对, 任一匹配即放行 (短路 `any(...)`)
4. 注释里说明: 生产 Tauri 用 `STUDIO_API_TOKEN`, 开发 tunnel 用 `STUDIO_DEV_TUNNEL_TOKEN`

### 测试

**`apps/studio/backend/tests/test_main_auth_middleware.py`** (已有, 增加 case):
- 已有 case 保留 (单 `STUDIO_API_TOKEN` 鉴权)
- 新增 case: 只设 `STUDIO_DEV_TUNNEL_TOKEN`, 请求带 dev tunnel token Bearer 应 200, 不带应 401
- 新增 case: 两者都设, 两个 token 都能用
- 新增 case: 两者都空, app 启动应 raise RuntimeError (而不是静默 dev bypass)

### 验收

- `uv run pytest apps/studio/backend/tests/test_main_auth_middleware.py -v` 全部 pass
- Manual: backend 不设任何 token 启动 → 进程立即退出 + log "Refusing to start in insecure dev bypass mode"

---

## T2: WebSocket 鉴权扩展

### 文件 + 改动

**`apps/studio/backend/app/routers/websockets.py`** (修改 WS 端点):
- WS 不能 set `Authorization` header (浏览器 API 限制), 改用 query param `?token=xxx`
- 在 WS handshake 时提取 token, 用同一 `valid_tokens` 列表比对
- 不匹配 → `await websocket.close(code=4401, reason="Unauthorized")`

**`apps/studio/frontend/src/hooks/use-run-stream.ts`** (或 WS 调用方):
- 拼 WS URL 时附加 `?token=${tunnelToken}`
- 注意 token 不进浏览器 URL bar (只是 WS handshake 时网络层传输)

### 测试

**`apps/studio/backend/tests/test_websocket_auth.py`** (新文件):
- WS 不带 token → close 4401
- WS 带错 token → close 4401
- WS 带正确 token → 正常握手 + 推送 events

### 验收

- pytest pass
- Manual: 前端 SPA 加 token 后, run detail 页面 WS 流正常实时刷新

---

## T3: 前端 token bootstrap

### 文件 + 改动

**`apps/studio/frontend/src/config/tunnel-token.ts`** (新文件):
```typescript
export function bootstrapTunnelToken(): string | null {
  const hash = window.location.hash;
  const match = hash.match(/#?tkn=([A-Za-z0-9_-]+)/);
  let token: string | null = null;
  if (match) {
    token = match[1];
    sessionStorage.setItem('studio_tunnel_token', token);
    history.replaceState(null, '', window.location.pathname + window.location.search);
  } else {
    token = sessionStorage.getItem('studio_tunnel_token');
  }
  return token;
}
```

**`apps/studio/frontend/src/main.tsx`** (改, 在 ReactDOM.render 前):
```typescript
import { bootstrapTunnelToken } from './config/tunnel-token';
import { configureApiToken } from './api/client';

const token = bootstrapTunnelToken();
if (token) configureApiToken(token);
```

**`apps/studio/frontend/src/config/runtime.ts`** (改): 生产 Tauri 模式仍走 `getSidecarConfig` → `configureApiToken(config.api_token)`; dev tunnel 模式 main.tsx 已经设过, runtime.ts 不要覆盖。可以 `if (!currentApiToken) configureApiToken(...)` 保护。

### 测试

**`apps/studio/frontend/src/config/tunnel-token.test.ts`** (新):
- mock `window.location.hash = '#tkn=abc123'` → bootstrapTunnelToken 返回 'abc123' + sessionStorage 设了 + hash 抹了
- mock hash 空 + sessionStorage 已有 → 返回 sessionStorage 值
- mock hash 空 + sessionStorage 空 → 返回 null

### 验收

- `pnpm test tunnel-token` pass
- Manual: 浏览器访问 `https://<X>.trycloudflare.com/#tkn=fake-token`, 加载后 DevTools 看 `window.location.hash === ''`, sessionStorage 含 `studio_tunnel_token`, 后续 fetch 带 Authorization header

---

## T4: Vite proxy 配置

### 文件 + 改动

**`apps/studio/frontend/vite.config.ts`** (修改 server 配置):
```typescript
server: {
  host: '127.0.0.1',
  port: 5173,
  proxy: {
    '/api': {
      target: 'http://127.0.0.1:8787',
      changeOrigin: false,
    },
    '/ws': {
      target: 'ws://127.0.0.1:8787',
      ws: true,
      changeOrigin: false,
    },
  },
  allowedHosts: ['.trycloudflare.com', 'localhost', '127.0.0.1'],
},
```

**`apps/studio/frontend/.env.local`** (改):
```
VITE_STUDIO_API_BASE_URL=/api
```
(从绝对 backend tunnel URL 改回相对路径)

**`apps/studio/frontend/src/config/runtime.ts`** (verify): 已经用 `VITE_STUDIO_API_BASE_URL` 作为 axios baseURL, 不需要改

### 验收

- 后端 backend tunnel 关掉, 只起前端 tunnel + Vite + backend
- Manual: 浏览器访问前端 tunnel URL → SPA 加载 → `/api/skills` 走 Vite proxy 转到 backend → DevTools Network 看 200
- WS: `/ws/runs/{id}` 同样 200 + 持续 stream

---

## T5: 启动脚本 `scripts/dev-tunnel.py`

### 文件 + 改动

**`scripts/dev-tunnel.py`** (新文件, 约 100 行):
- 用 `secrets.token_urlsafe(32)` 生成 token
- 用 `subprocess.Popen` 起 3 个子进程: backend (with env), Vite, cloudflared (只 5173)
- 用 `qrcode` lib 生成 ASCII QR 打印
- 解析 cloudflared stdout 拿 tunnel URL (正则 `https://[a-z0-9-]+\.trycloudflare\.com`)
- KeyboardInterrupt 优雅 cleanup (terminate 三子进程)

**`pyproject.toml`** (改, 加 dev script): 注册 `make dev-tunnel` 或 `uv run dev-tunnel`

**`Makefile`** (新或改): target `dev-tunnel` 调用 `python scripts/dev-tunnel.py`

### 依赖

- `qrcode` (Python lib, 纯文本输出): `uv add --dev qrcode`

### 测试

**`scripts/test_dev_tunnel.py`** (轻量):
- Mock subprocess.Popen, 验证 env 正确 inject (含 `STUDIO_DEV_TUNNEL_TOKEN`)
- Mock cloudflared stdout, 验证 URL 解析正确
- Mock qrcode 输出, 验证 entry URL 拼接 `{tunnel_url}/#tkn={token}`

### 验收

- `python scripts/dev-tunnel.py` 一行起所有, 终端打出 QR + URL
- 用手机扫码 → 加载 SPA → fetch /api 200 → run detail WS stream 正常

---

## T6: 端到端验证 (DoD 清单逐条 verify)

### Test plan

按 `requirements.md §5` 验收清单逐条:

- [ ] **R1**: backend tunnel 不存在, 后端 8787 公网不可达 (`curl https://<Y>.trycloudflare.com` 应 ENOTFOUND)
- [ ] **R2**: 后端不带任何 token 启动 → 立即退出 + log "Refusing to start"
- [ ] **R3**: 重启 `scripts/dev-tunnel.py`, token 变, 旧 URL hash 401
- [ ] **R5**: backend access log + `/tmp/cf-frontend.log` 抓不到 token 字符串
- [ ] **R6**: 手机加载 URL → 30 秒后看地址栏, hash 已经空
- [ ] **R7**: production Tauri build, 设 `STUDIO_API_TOKEN`, 不设 `STUDIO_DEV_TUNNEL_TOKEN`, app 正常 work
- [ ] **R9**: 一行命令拉起全套
- [ ] **R10**: 两种模式跑同一份 backend 代码, 行为一致

### 报告

a1 写 `docs/studio-dev-tunnel-safety-validation.md` 记录:
- 每条 R 的实证截图 / log 摘录
- 任何 deviation 跟 spec 的对照
- a3 (Claude) 跑 e2e + 主控 PM 收敛

---

## Out of scope (本 spec 不做)

- Production Tauri 模式细节调整 (已存在, 兼容性测试即可)
- Cloudflare named tunnel + Access 集成 (未来 v2)
- 多用户支持
- Token rotate API
- SettingsPage 里展示当前 dev tunnel URL (UX nicety, brief #2 那边考虑)
