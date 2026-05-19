# Studio Dev Tunnel Safety — Design

> **Status**: Draft, v0.1, 2026-05-14
> **Author**: a2 (Gemini) primary, PM (sevenx) 整合
> **Implementer**: a1 (Codex), 待 tasks.md 拆解
> **Pattern reference**: Jupyter Notebook + Code-Server + Vite proxy + GitHub Codespaces lifecycle

## 1. Architecture (新拓扑)

### 1.1 旧拓扑 (废除)

```
[手机/远程浏览器]
  ├─https→[前端 tunnel <X>.trycloudflare.com]→[VPS:5173 Vite]
  └─https→[后端 tunnel <Y>.trycloudflare.com]→[VPS:8787 FastAPI]   ← 公网暴露面
```

### 1.2 新拓扑 (Vite Proxy 同源模式)

```
[手机/远程浏览器]
  └─https─→[单 tunnel <X>.trycloudflare.com]
                     │
                     ▼ cloudflared
              [VPS:5173 Vite Dev Server]
                     │
                     ├─同源静态资源 (SPA index.html / *.js)
                     │
                     └─Vite proxy: /api/* + /ws/* ─→[VPS:127.0.0.1:8787 FastAPI]
                                                              ↑
                                                       从公网不可达
```

**安全收益**:
- 后端 8787 从公网彻底隐身, 物理上只接 Vite 进程的本地转发
- 浏览器同源, CORS preflight 不再触发
- 攻击面减半 (1 个 tunnel URL vs 2 个)

## 2. Token 鉴权 (Defense Layer 1)

### 2.1 投递模式: URL Hash (Jupyter / Code-Server 模式)

启动脚本生成 token → 拼装入口 URL `https://<X>.trycloudflare.com/#tkn=<random-token>` → 终端打印 + QR code。

**为什么用 hash 不用 query**: 见 `research.md §3` — hash 不发给 server, 不进 access log。

### 2.2 SPA 端 token 处理

```typescript
// apps/studio/frontend/src/config/tunnel-token.ts (新文件)
let tunnelToken: string | null = null;

export function bootstrapTunnelToken(): void {
  const hash = window.location.hash;  // "#tkn=xxx" or ""
  const match = hash.match(/#?tkn=([A-Za-z0-9_-]+)/);
  if (match) {
    tunnelToken = match[1];
    sessionStorage.setItem('studio_tunnel_token', tunnelToken);
    // 立刻擦除 URL hash 防截图泄露
    history.replaceState(null, '', window.location.pathname + window.location.search);
  } else {
    tunnelToken = sessionStorage.getItem('studio_tunnel_token');
  }
  if (tunnelToken) {
    configureApiToken(tunnelToken);  // 复用 c364440 已有的 axios interceptor
  }
}
```

**调用时机**: `main.tsx` 或 `App.tsx` `useEffect` 首次执行前。

### 2.3 后端 middleware 改造

`apps/studio/backend/app/main.py` 的 `configure_api_auth` 改为接受两套 env, 任一匹配即放行:

```python
def configure_api_auth(studio_app: FastAPI) -> None:
    api_token = os.environ.get("STUDIO_API_TOKEN", "").strip() or None
    dev_tunnel_token = os.environ.get("STUDIO_DEV_TUNNEL_TOKEN", "").strip() or None
    valid_tokens = [t for t in (api_token, dev_tunnel_token) if t]
    
    if not valid_tokens:
        # 推翻原 dev bypass — 没有任何 token 直接拒绝启动
        raise RuntimeError(
            "STUDIO_API_TOKEN or STUDIO_DEV_TUNNEL_TOKEN must be set. "
            "Refusing to start in insecure dev bypass mode."
        )
    
    @studio_app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        if request.url.path in ("/health", "/api/health"):
            return await call_next(request)
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(...)
        token = auth_header[7:]
        if not any(_constant_time_compare(token, t) for t in valid_tokens):
            return JSONResponse(...)
        return await call_next(request)
```

**WebSocket 鉴权**: WS 不能用 `Authorization` header (浏览器 WebSocket API 不支持 set header), 通常通过 subprotocol 或 query param 传 token。**研究后选**: query param + middleware 提取 (因为 WS 没经过 Cloudflare access log 的影响范围一致), 详 §5。

### 2.4 推翻 dev bypass

旧 `configure_api_auth`:
```python
if api_token is None:
    logger.warning("DEV MODE without auth")  # 静默放行
```
新策略: **拒绝启动**, 不允许 dev bypass。生产 Tauri 必有 `STUDIO_API_TOKEN` (Rust 注入), 开发 tunnel 必有 `STUDIO_DEV_TUNNEL_TOKEN` (启动脚本注入), 跑 unit test 必有 fixture 设 env。**没有一个合理路径会让 backend 在零 token 下启动**。

## 3. Vite Proxy 配置

```typescript
// apps/studio/frontend/vite.config.ts (改)
export default defineConfig({
  // ... existing ...
  server: {
    host: '127.0.0.1',  // 已有
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8787',
        changeOrigin: false,
        // 转发原 Authorization header (含 Bearer token)
      },
      '/ws': {
        target: 'ws://127.0.0.1:8787',
        ws: true,
        changeOrigin: false,
      },
    },
    // cloudflared 进来的 host 不在默认白名单, 显式 allow
    allowedHosts: ['.trycloudflare.com', 'localhost', '127.0.0.1'],
  },
})
```

**SPA 配置改动**: `VITE_STUDIO_API_BASE_URL` 改回**相对路径** `/api` (而不是绝对的 backend tunnel URL), 让浏览器同源调用。

## 4. Token 命名 & Env

| Env | 场景 | 谁生成 | 谁注入 |
|---|---|---|---|
| `STUDIO_API_TOKEN` | 生产 Tauri 包 | Tauri Rust (`generate_api_token`) | Rust spawn Python 时 `.env()` |
| `STUDIO_DEV_TUNNEL_TOKEN` | 开发 tunnel | 启动脚本 `secrets.token_urlsafe(32)` | shell env (脚本 export 给 backend + 拼 URL) |

**共存原则**: middleware 同时检查两者, 任一匹配即放行。两个不冲突, 因为通常只设一个。

## 5. 启动脚本设计

新文件 `scripts/dev-tunnel.py` (或 `Makefile` target `make dev-tunnel`):

```python
#!/usr/bin/env python
"""Studio dev tunnel: 一键拉起 backend + Vite + cloudflared + 投递入口 URL。"""

import secrets
import subprocess
import sys
import time
import re

def main() -> None:
    token = secrets.token_urlsafe(32)
    print(f"[1/4] Generated session token (len={len(token)})")
    
    # Backend (with token env)
    backend = subprocess.Popen(
        ["uv", "run", "--no-sync", "python", "-m", "app.main"],
        cwd="apps/studio/backend",
        env={**os.environ, "STUDIO_DEV_TUNNEL_TOKEN": token},
    )
    print(f"[2/4] Backend started, PID={backend.pid}")
    
    # Vite (default port 5173, no extra env)
    vite = subprocess.Popen(
        ["corepack", "pnpm", "dev"],
        cwd="apps/studio/frontend",
    )
    print(f"[3/4] Vite started, PID={vite.pid}")
    
    # Cloudflared (frontend only)
    cf = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", "http://127.0.0.1:5173", "--no-autoupdate"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    tunnel_url = wait_for_tunnel_url(cf)  # 解析 cloudflared stdout 拿 https://xxx.trycloudflare.com
    
    # Compose entry URL + QR code
    entry_url = f"{tunnel_url}/#tkn={token}"
    print(f"[4/4] Entry URL: {entry_url}")
    print_qr(entry_url)  # 用 `qrcode` lib 打印 ASCII QR
    
    # Wait
    try:
        backend.wait()
    except KeyboardInterrupt:
        for p in (backend, vite, cf):
            p.terminate()
```

**Mac/Linux 兼容**: 用 `subprocess.Popen` 不依赖 shell, KeyboardInterrupt 时优雅 terminate 三个子进程。

**QR Code 库**: `pip install qrcode` (纯 ASCII, no extra deps for terminal)。

## 6. Production Tauri 兼容性

Production Tauri 路径 (生产构建后 Tauri 安装包):
1. Tauri Rust 主进程启动, `generate_api_token()` 生成 64 字符 token
2. spawn Python 子进程, `.env("STUDIO_API_TOKEN", token)` 注入
3. `configure_api_auth` 看到 `STUDIO_API_TOKEN` set, `STUDIO_DEV_TUNNEL_TOKEN` 不存在, valid_tokens = `[api_token]`, 启动正常
4. WebView 加载本地 file:// SPA, Tauri invoke 提供 `get_sidecar_config` 返回 token, SPA `configureApiToken(token)` 设 axios 拦截
5. **跟 dev tunnel 模式无任何代码分支**, 同一份 middleware 就 work

Dev tunnel 路径 (本 spec):
1. 启动脚本生成 32 字符 token
2. env 注入 backend (`STUDIO_DEV_TUNNEL_TOKEN`)
3. `configure_api_auth` 看到 `STUDIO_DEV_TUNNEL_TOKEN` set, `STUDIO_API_TOKEN` 不存在, valid_tokens = `[dev_tunnel_token]`, 启动正常
4. SPA 通过 URL hash 拿 token, `configureApiToken(token)` 同一函数, 同一拦截器
5. 浏览器 → Vite proxy → backend, Authorization header 自动转发

## 7. CORS 退化 (痛点消除)

旧拓扑 (双 tunnel):
- SPA origin: `<X>.trycloudflare.com`
- backend origin: `<Y>.trycloudflare.com`
- → 跨域, 需要 `STUDIO_CORS_EXTRA_ORIGINS` 动态白名单

新拓扑 (单 tunnel + Vite proxy):
- SPA origin: `<X>.trycloudflare.com`
- backend 在浏览器看来也是 `<X>.trycloudflare.com` (Vite 同源转发)
- → 同源, **零 CORS 配置**

`STUDIO_CORS_EXTRA_ORIGINS` env 在 dev tunnel 场景下**不再需要**, 可以删除相关代码或保留作为 production 偶尔需要的转义 (低优先级)。

## 8. 安全验证 (Threat Model)

| 攻击 | 旧拓扑 (dev bypass) | 新拓扑 (本 spec) |
|---|---|---|
| 扫到 backend tunnel URL | RCE | N/A — 后端不暴露 |
| 扫到前端 tunnel URL | 加载 SPA 但 SPA 没 token, 看到空白页 | 加载 SPA, 没 token, fetch /api 返回 401 |
| URL 截图 / 复制泄露 | 完整 RCE 通道 | hash 已 replaceState 抹除, 截图后的 URL 无 token |
| CT log 扫 trycloudflare 子域名 | 列举所有 endpoint | 拿到 tunnel URL 但没 token → 401 wall |
| Brute force token | 64 字符 urlsafe (~380 bit entropy) | 计算上不可行 |
| Token rotate 攻击 | N/A | Session-bound, 重启换 token, 旧 token 永久失效 |

## 9. 残留风险 (acknowledged, 不做)

- **Vite Dev Server 自身漏洞**: Vite 进程被攻破 → backend 通过本地 proxy 也被攻破。**接受** — Vite 在 quickly developed mode, 用户接受这个信任边界
- **Cloudflare tunnel 中间人**: trycloudflare 是 Cloudflare 托管的 TLS 终端, Cloudflare 看得到明文请求。**接受** — 在 quick tunnel 模式下这是已知 tradeoff, 跟 Jupyter / Code-Server 一致
- **User 设备失窃**: 浏览器 sessionStorage 含 token, 设备被偷 token 泄露。**部分缓解** — sessionStorage 关闭 tab 自动清; 完整缓解需要短 TTL + 自动 logout, 不做

## 10. 不引入的复杂度

- ❌ `/auth/login` 用户名密码页面
- ❌ Cloudflare Access (需要 named tunnel + DNS)
- ❌ Token rotate / refresh
- ❌ JWT (token 是 opaque random, server-side stateful)
- ❌ HMAC-signed cookies
- ❌ CSRF token (SPA Bearer 模式不需要)
