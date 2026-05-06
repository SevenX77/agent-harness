# Skill Studio — Tauri 桌面外壳

Phase T1 (基础 Setup) 产物：把 `apps/studio/frontend` (Vite + React 19 + TS) 包进 Tauri 2.x WebView,
为后续 Phase T2 (Python sidecar 集成)、T3 (跨平台打包/签名)、T4 (原生体验) 打底。

设计文档：`docs/architecture/TAURI_KICKOFF_PLAN.md`

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

## 开发流程 (Linux 本地有 X server / Wayland 时)

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
cd apps/studio/frontend && npm run build  # 先生成 dist/
cd ../tauri && cargo tauri build      # 输出到 target/release/bundle/
```

T3 阶段会在 GitHub Actions 加 macOS / Windows / Linux 的构建矩阵。

## Headless / VPS 验证

本仓在 VPS (无 X server) 上 bootstrap 时,T1 验证只跑 `cargo check` (1m 41s 通过),
不跑 `cargo tauri dev` (没显示器)。GUI 烟测留给本地有桌面的开发者:

```bash
cd apps/studio/tauri && cargo tauri dev
# 期望: 窗口出现, 1400×900, 显示 Skill Studio 现有 UI
```

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
