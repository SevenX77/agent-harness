# Skill Studio — Tauri 桌面外壳

Phase T1 (基础 Setup) 产物：把 `apps/studio/frontend` (Vite + React 19 + TS) 包进 Tauri 2.x WebView,
为后续 Phase T2 (Python sidecar 集成)、T3 (跨平台打包/签名)、T4 (原生体验) 打底。

设计文档：`docs/architecture/TAURI_KICKOFF_PLAN.md`

桌面能力边界规范：`docs/development/STUDIO_DESKTOP_BOUNDARY_SPEC.md`

## 目录结构

```
apps/studio/tauri/
├── Cargo.toml          # crate name = skill-studio-tauri, Tauri 2.11.1
├── tauri.conf.json     # identifier = com.sevenx.skill-studio, 1400×900 窗口
├── build.rs            # tauri-build 脚手架
├── capabilities/       # ACL (sidecar 接入时再扩)
├── icons/              # 默认占位图标 (T3 替换为正式品牌)
└── src/
    ├── main.rs         # Windows release 入口
    └── lib.rs          # tauri::Builder + tauri-plugin-log
```

## 依赖

* Rust ≥ 1.77.2 (推荐 stable)
* Node ≥ 20 (frontend)
* Tauri CLI 2.x — 已通过 `npm install -g @tauri-apps/cli@^2` 安装,
  二进制在 `~/.npm-global/bin/tauri`
* 系统库: `webkit2gtk-4.1`, `libgtk-3-dev`, `libssl-dev` (Linux dev)

## 开发流程

### 标准启动方式

只启动一个 Tauri dev 会话，让 Tauri 自己通过 `beforeDevCommand` 拉起 Vite，
同时让 Tauri sidecar 拉起动态端口的 FastAPI 后端。

```bash
# from repo root — Windows
powershell -ExecutionPolicy Bypass -File .\scripts\studio-dev.ps1

# from repo root — macOS / Linux
scripts/studio-dev.sh
```

两个脚本是同一层薄壳（设 `PYTHONUTF8` + `STUDIO_SIDECAR_PORT` 后交给跨平台的
`apps/studio/tauri/scripts/dev_studio.js`）。Linux 桌面依赖见上文系统库清单。

默认配置来自 `apps/studio/tauri/tauri.conf.json`:

- frontend dev URL: `http://127.0.0.1:5173`
- frontend API base in Tauri runtime: 由 `get_sidecar_config` 改写为 `http://127.0.0.1:<dynamic>/api`
- backend sidecar port: Rust 主进程动态分配, 不固定为 `8787`
- backend auth: Rust 生成 `STUDIO_API_TOKEN`, frontend 通过 runtime config 带 `Authorization: Bearer <token>`
- backend code in dev: debug build 优先运行工作区源码 `apps/studio/backend`; 打包/找不到源码时才运行 `apps/studio/tauri/vendor/backend`

### 端口 5173 被占用时

优先停止旧的 Vite/Tauri 进程, 再用标准启动方式。不要长期手写临时端口命令。

```bash
lsof -nP -iTCP:5173 -sTCP:LISTEN
lsof -nP -iTCP:5174 -sTCP:LISTEN
```

如果确实需要临时使用 5174, 后端 CORS 也必须允许同一个 origin。当前后端默认已允许
`http://127.0.0.1:5174` 和 `http://localhost:5174`。其他临时端口必须显式传入:

```bash
cd apps/studio/tauri
STUDIO_CORS_EXTRA_ORIGINS=http://127.0.0.1:5175 \
cargo tauri dev --config '{"build":{"devUrl":"http://127.0.0.1:5175","beforeDevCommand":"cd /Users/sevenx/Documents/coding/agent-harness/apps/studio/frontend && env VITE_STUDIO_API_BASE_URL=/api npm run dev -- --host 127.0.0.1 --port 5175 --strictPort"}}'
```

### 启动后检查

1. DevTools Console 不应出现 `Preflight response is not successful` 或 `Missing Bearer token`。
2. Recent skills 不应显示 `Could not load skills`。
3. Tauri pane 日志应显示 `/health` 200, `/api/skills` 的 OPTIONS/GET 不应是 400。
4. `lsof -nP -iTCP -sTCP:LISTEN | rg "(5173|5174|uvicorn|python3)"` 只应看到当前需要的一组 Vite + sidecar。
5. 如果改过 backend, 不需要手动同步 `vendor/backend` 才能在 dev shell 生效；release 资源同步仍由 build pipeline 调 `node scripts/sync_resources.js` 完成。

## 旧式手动流程 (仅用于纯浏览器调试)

```bash
# Terminal 1: 起 Vite
cd apps/studio/frontend
npm run dev          # 监听 127.0.0.1:5173

# Terminal 2: 起 Tauri 窗口 (会内嵌 5173 的 frontend)
cd apps/studio/tauri
cargo tauri dev      # 或 ~/.npm-global/bin/tauri dev
```

## Build (生产)

```bash
cd apps/studio/tauri && node scripts/download_runtime.js  # T2: 下载并校验 portable Python
cd ../backend && python scripts/build_vendor.py            # T2: pip install --target ../tauri/vendor/site-packages
cd ../tauri && node scripts/sync_resources.js              # T2: 同步 backend/skills/config resources
cd ../frontend && npm run build  # 先生成 dist/
cd ../tauri && cargo tauri build      # 输出到 target/release/bundle/
```

Tauri sidecar 启动 backend 时使用 bundled Python 与 vendored dependencies:

```bash
cd apps/studio/tauri
PYTHONPATH="vendor/site-packages:vendor/backend" \
STUDIO_RESOURCE_DIR="vendor/resources" \
STUDIO_SHUTDOWN_TOKEN="<runtime-token>" \
vendor/python/<target-triple>/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port <dynamic-port>
```

## T2.1 Portable Python Runtime

T2 使用 Astral `python-build-standalone` 的 portable CPython distribution, 不采用
PyInstaller/Nuitka，也不把 Python 解释器提交进仓库。runtime 由
`python-runtime.lock.json` 固定到 CPython `3.12.13` / release tag `20260414`。

```bash
cd apps/studio/tauri
node scripts/download_runtime.js
vendor/python/$(node -e "console.log(require('./scripts/download_runtime').hostTargetTriple())")/bin/python --version
```

脚本按 target triple 选择 artifact，macOS/Linux 优先 `install_only_stripped`，Windows
x86_64 固定 `install_only` fallback。下载后本地重新计算 SHA256；URL 或 hash 与 lock
不一致会 fail closed 并阻断后续 Tauri build。动态产物写入 `vendor/downloads/` 与
`vendor/python/`，由 `.gitignore` 排除。

T3 阶段会在 GitHub Actions 加 macOS / Windows / Linux 的构建矩阵。

## Headless / VPS 验证

本仓在 VPS (无 X server) 上 bootstrap 时,T1 验证只跑 `cargo check` (1m 41s 通过),
不跑 `cargo tauri dev` (没显示器)。GUI 烟测留给本地有桌面的开发者:

```bash
cd apps/studio/tauri && cargo tauri dev
# 期望: 窗口出现, 1400×900, 显示 Skill Studio 现有 UI
```

## T2.6 Desktop Lifecycle Checklist

Headless CI / VPS:

```bash
DISABLE_GUI=1 uv run pytest apps/studio/tests-e2e/test_desktop_lifecycle.py -q
cargo check --manifest-path apps/studio/tauri/Cargo.toml
cargo test sidecar --lib --manifest-path apps/studio/tauri/Cargo.toml
```

Manual desktop smoke:

1. Keep `127.0.0.1:8787` occupied, then run `cd apps/studio/tauri && cargo tauri dev`.
2. Confirm the splash reaches the Studio UI and Network requests use `127.0.0.1:<dynamic>/api`, not `8787`.
3. Confirm `/health` responds on the dynamic sidecar port.
4. Close the window and verify `ps -eo pid,command | grep 'uvicorn app.main:app'` (or Task Manager on Windows) shows no sidecar Python process.
5. Break Python startup intentionally and confirm Splash Error renders recent sidecar stderr instead of a blank screen.

## "Open in Claude Code" (copilot 面板按钮)

按钮 (`open_claude_code` Tauri 命令, `src/lib.rs`) 把当前 skill 工作区交给
[`ah`](https://github.com/SevenX77/ah)(agent hypervisor)驱动的真实 Claude Code
跑。Windows 上 `ah` + `claude` 都活在 WSL2 里 —— 点按钮前得先把 WSL2 + Ubuntu +
tmux + claude CLI + ah + 订阅登录都装好。

`ah` 自己的安装命令(`ah-installer.sh`)**只装 `ah` 这一个二进制**——不装
WSL2/tmux/claude CLI,也不处理登录(`ah doctor` 只诊断,不安装/不修复;`ah --help`
的全部子命令里也没有 install/provision 类命令)。这些前置步骤由
`scripts/install-claude-code-wsl.ps1` 统一打包:

```powershell
# 从仓库根目录, Windows PowerShell
powershell -ExecutionPolicy Bypass -File scripts\install-claude-code-wsl.ps1
```

幂等,可反复重跑。装 WSL2 需要一次重启、首次登录 claude 需要你在浏览器里过一次
OAuth —— 这两步是 OS/安全层面的硬性人工步骤,脚本跑到这两处会打印清楚的下一步提示
然后干净退出(不是报错),按提示做完再重跑同一条命令即可继续。跑完最后会打印
`ah doctor` 的诊断结果自检。

脚本刻意分成两部分,对应所有权边界:

- **PART A — ah 的运行环境前置**(WSL2 / 发行版 / systemd / 镜像网络 / 时区/语言/代理 /
  tmux)。这些**架构上应归 ah 自己的安装器**,已作为需求提给 ah 仓库
  ([`docs/handoffs/ah-installer-provisioning-and-master-defaults.md`](../../../docs/handoffs/ah-installer-provisioning-and-master-defaults.md)
  Req 1)。在 ah 接管前,本脚本作为**临时桥**代劳;一旦 ah 的安装器自装运行环境,
  PART A 整段删掉,由 PART B 装 ah 时自动带出。
- **PART B — Studio 自己的 Claude Code provider 层**(装 ah、装 claude CLI、订阅登录)。
  这是 Studio 的**长期职责**,与 ah 无关地留在这里 —— provider CLI 和用户登录**明确不归
  ah 管**(见 handoff Non-Goals)。

同一份 handoff 还提了另外两条给 ah 的需求:修掉 ccbd-rust 时代那条坏掉的内置默认 master
命令(`claude --dangerously-skip-permissions --continue /remote-control`,新工作区/root/本机
attach 三处都会崩),以及无显式 `--config` 时不要擅自把当前目录当项目、eager 建全局状态。

## Phase 边界 (T1 不做)

* **T2 (Python sidecar)**: 用 Tauri 的 sidecar 机制 / `std::process::Command` 拉起
  `uvicorn app.main:app`,Rust 主进程动态分配端口传给 Python,
  React 通过 `@tauri-apps/api` 读 sidecar URL 替换 `VITE_STUDIO_API_BASE_URL`
* **T3 (打包/签名)**: macOS Notarization, Windows 证书, Linux AppImage
* **T4 (原生体验)**: Splash screen, Dock/Tray, 文件关联, 主题同步

## 跟 monorepo 的关系

这个 crate 不进 `Cargo workspace` (workspace 还没建),独立 build。
后续 T2 引入 sidecar 工具脚本 (Rust) 时再考虑要不要建 workspace。

`@tauri-apps/api` 已加入 `apps/studio/frontend/package.json` (`^2.11.0`),
用于 frontend 调用 Tauri 原生 API (T2 才会真正用)。

## T1 验收

| 验证 | 命令 | 结果 |
|---|---|---|
| Tauri scaffolding 生成 | `tauri init --ci ...` | 7 文件 + 3 目录 |
| Cargo 类型检查 | `cargo check` | `Finished dev profile in 1m 41s` |
| frontend build 不退化 | `npm run build` | 2052 modules, 1.13s, 891 kB |
| frontend 依赖加好 | `grep tauri-apps package.json` | `@tauri-apps/api: ^2.11.0` |
