# TAURI_KICKOFF_PLAN (Tauri Migration)

**版本**: 1.0
**日期**: 2026-05-05
**作者**: a2 Gemini (资深 Tauri & Python 跨平台专家)

---

## 1. Executive Summary

本计划旨在将现有的 Skill Studio (Web) 完整封装为高性能、零配置的 **Tauri 桌面应用**。通过在 Tauri Rust 主进程中拉起便携式 Python (FastAPI Sidecar)，我们将为 PM 提供“双击即开”的原生体验，并彻底解决 Web 环境下本地文件读写的局限性。

*   **总周期**: 5 周
*   **核心 Milestone**: 
    *   M1: Tauri 基础外壳 (1w)
    *   M2: Python Sidecar 进程桥接 (2w)
    *   M3: 跨平台打包与签名 (1w)
    *   M4: 原生体验打磨 (1w)
*   **关键风险**: 跨平台 Python 运行时的兼容性与签名认证。

---

## 2. 现状评估与 Gap

### 2.1 现状优势
*   **架构就绪**: 经过 Monorepo 重构，Studio 已经实现了前后端解耦。
*   **API 稳定**: 后端基于 FastAPI，天然适合作为 Sidecar 运行。
*   **UI 现代**: 基于 Vite + React，与 Tauri 的 WebView 契合度极高。

### 2.2 核心 Gap
*   **Rust 基建**: 目前代码库完全没有 Rust 环境与 Tauri 配置。
*   **进程管控**: 需要编写 Rust 逻辑来启动、监控及优雅关闭 Python 伴生进程。
*   **便携化运行时**: 需要实现跨平台的 Python 运行时（Standalone Python）自动下载与分发。

---

## 3. Migration Phase 拆分

### Phase T1: 基础 Setup (1 周)
*   **环境安装**: 在 CI 和开发者机器部署 Rust 1.75+, Tauri CLI。
*   **初始化**: 运行 `cargo tauri init`，目录定为 `apps/studio/tauri`。
*   **前端接入**: 
    *   配置 `tauri.conf.json` 将 `devPath` 指向 Vite 的 5173 端口。
    *   在 React 中引入 `@tauri-apps/api` 处理窗口标题栏控制。
*   **验证**: `cargo tauri dev` 成功拉起桌面窗口并显示现有 Studio UI。

### Phase T2: Python Sidecar 集成 (2 周)
*   **运行时准备**: 
    *   引入 `python-build-standalone`。
    *   编写下载脚本（Rust 或 Python），根据 OS (x86_64/aarch64) 抓取对应的压缩包。
*   **Sidecar 桥接**:
    *   使用 Tauri 的 `Sidecar` 功能或 `std::process::Command` 拉起 `uvicorn app.main:app`。
    *   **自动分配端口**: Rust 寻找随机可用端口并传递给 Python，前端动态更新 `API_BASE_URL`。
*   **生命周期**: 监听 Tauri 窗口关闭事件，发送 SIGTERM 给 Python 进程，防止僵尸进程驻留。

### Phase T3: 跨平台 Build 与签名 (1 周)
*   **打包流水线**: 
    *   GitHub Actions 增加 macOS (.dmg), Windows (.msi), Linux (.AppImage) 构建矩阵。
*   **Code Signing**:
    *   配置 Apple Developer ID 证书进行 Notarization（防止 macOS 报毒）。
    *   Windows 证书配置（可选，提升安装信任度）。

### Phase T4: 原生体验优化 (1 周)
*   **启动遮罩**: 增加 Splash Screen 遮盖 Python 1-2 秒的冷启动时间。
*   **系统集成**: 
    *   Dock/Tray 图标开发。
    *   **文件关联**: 实现双击 `.skill` 或 `SKILL.md` 直接唤起 Studio。
*   **主题同步**: 监听系统深色模式切换，自动调用 Studio 的 `useTheme`。

---

## 4. 关键技术决策

### 4.1 Standalone Python 来源
**决策**: 优先使用 **Astral 的 `python-build-standalone`**。
*   *理由*: 该版本是预编译的、静态链接的，且 `uv` 内部也在使用，稳定性和体积平衡极佳。

### 4.2 进程通信
**决策**: 维持 **本地 HTTP (REST/WS)** 通信。
*   *理由*: 现有 React 前端已有完整的 Axios 和 WebSocket 实现，无需为了桌面化改写为 Rust IPC 或 gRPC，开发成本最低。

### 4.3 数据存储
**决策**: 遵循各平台标准数据目录。
*   macOS: `~/Library/Application Support/graph-agent-studio/`
*   Linux: `~/.config/graph-agent-studio/`
*   Windows: `%APPDATA%/graph-agent-studio/`

---

## 5. 风险与缓解

| 风险项 | 严重度 | 缓解策略 |
| :--- | :--- | :--- |
| **Python Sidecar 体积** | P1 | 压缩 Standalone Python 运行时，剔除不必要的标准库模块，控制在 40MB 以内。 |
| **端口冲突** | P0 | 由 Rust 动态寻找空闲端口，并通过命令行参数 `--port` 传递给 FastAPI。 |
| **病毒误报** | P0 | 必须执行正式的代码签名与苹果公证流程。 |
| **Rust 学习曲线** | P2 | 核心业务逻辑仍在 Python/TS，Rust 仅负责外壳和进程管理，由资深工程师封装备忘录。 |

---

## 6. 启动节奏推荐

**建议**: **先 Web 后桌面。**
1.  **本周**: 发布 PR #37 到 Main 分支，让 PM 先通过 Web 端预览。
2.  **下周**: a1 启动 Phase T1。
3.  **双轨期**: 维持 Web 与 Tauri 共存 2 周，收集 Web 反馈并快速同步至桌面版。

---

## 7. 验收 Checklist

- [ ] 产出三平台对应的安装包文件。
- [ ] 应用启动后 3 秒内进入主界面。
- [ ] 关闭窗口后，后台 `python` 进程消失（不残留端口）。
- [ ] 桌面版能正常读取电脑任意目录下的 `SKILL.md`（需配置 Tauri fs scope）。
- [ ] 状态栏（Tray）能够显示当前的运行状态（Running / Idle）。
