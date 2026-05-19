# Phase T2 Python Sidecar 集成 — 需求规范 (Round 1)

## 1. Background

在 Skill Studio 的演进过程中，Web 端架构已完成前后端解耦与 API 稳定化。为了进一步提升产品竞争力，根据 `docs/architecture/TAURI_KICKOFF_PLAN.md` §1 规划，项目需从 Web 应用封装为 Tauri 原生桌面应用，实现“双击即开”的原生体验，并彻底解决浏览器环境下本地文件系统访问受限的问题。

*   **T2 阶段定位**：在 5 周的 Tauri 桌面化总计划中，Phase T2 聚焦于 **Python Sidecar 集成 (2周)**。它承接 T1 的基础 Setup，并为 T3 跨平台打包与 T4 原生体验打磨奠定核心运行基石。
*   **Scope 声明**：本 spec **仅覆盖** T2 阶段的需求。T1 基础配置、T3 跨平台流水线、T4 细节优化以及 `packages/graph-agent/` SDK 本身的业务变更均不在本范围内。
*   **关键技术决策** (遵循 `TAURI_KICKOFF_PLAN.md` §4)：
    - **Standalone Python 来源**：采用 Astral 的 `python-build-standalone` 预编译便携式 distribution，确保跨平台运行时的稳定性与体积平衡。
    - **进程通信**：维持本地 HTTP (REST/WS) 通信，前端 API 调用链路保持一致。
    - **数据存储**：遵循各平台标准目录（Library / .config / APPDATA）。
*   **平台支持范围**：macOS x86_64, macOS aarch64, Linux x86_64, Linux aarch64, Windows x86_64。

## 2. 业务目标

Tauri Phase T2 旨在通过 Python Sidecar 的深度集成达成以下业务价值：

1.  **原生桌面化体验**：支持双击启动应用，由 Tauri Rust 主进程自动拉起 Python 后端，用户无需感知 Python 环境依赖。
2.  **本地文件系统访问**：通过 Tauri fs scope 与 Sidecar 运行环境，消除 Web Sandbox 局限，实现对本地 `SKILL.md` 的直接读写。
3.  **确定性的进程生命周期**：实现对 Sidecar 进程的强管控，确保应用退出时所有 Python 后端进程优雅关闭，“零容忍”僵尸进程与端口残留。
4.  **跨平台运行环境一致性**：为 5 个核心目标平台提供统一的 Python 运行时分发与校验逻辑。
5.  **高性能启动响应**：优化 Sidecar 启动流程，力求在应用窗口打开后 3 秒内进入可用主界面，并支持启动过渡效果。

## 3. EARS 需求

### 3.1 Python Runtime 分发与校验 (Runtime Distribution & Verification)

*   **Requirement 3.1.1: 自动化运行时下载 (Automated Runtime Download)**
    **When** 开发者或 CI 执行构建流程且本地缓存缺失时，**the build scripts shall** 根据当前目标平台 (Target Triple) 从 Astral 官方源下载对应的 `python-build-standalone` 压缩包。

*   **Requirement 3.1.2: 完整性校验 (Integrity Verification)**
    **The system shall** 在下载完成后通过 SHA256 摘要进行强校验，若校验失败则立即终止构建流程 (Fail Closed)。

*   **Requirement 3.1.3: 锁定版本机制 (Locking Mechanism)**
    **The system shall** 使用 `lock` 文件固定 Python 运行时的版本与发行版 Hash，防止构建过程中产生隐式版本漂移。

### 3.2 Backend Sidecar 启动入口 (Backend Sidecar Entrypoint)

*   **Requirement 3.2.1: 动态端口参数化 (Dynamic Port Parameterization)**
    **The Backend Sidecar (FastAPI) shall** 通过 `--port` 命令行参数支持任意可用端口的注入，不再硬编码或依赖固定的 `STUDIO_PORT=8787`。

*   **Requirement 3.2.2: 依赖隔离与 vendor 化 (Dependency Isolation)**
    **The system shall** 将 Python 后端依赖打包至 distribution 的 `vendor` 或特定 lib 目录中，确保其执行环境与宿主机全局 Python 环境完全隔离。

*   **Requirement 3.2.3: SDK 兼容性 (SDK Compatibility)**
    **The Backend implementation shall** 在不修改 `packages/graph-agent/` SDK 核心源码的前提下完成侧向集成。

### 3.3 Rust Sidecar 生命周期管理 (Rust Sidecar Lifecycle)

*   **Requirement 3.3.1: 随机端口发现 (Random Port Discovery)**
    **While** Tauri 主进程启动过程中，**the Rust logic shall** 扫描并获取一个当前系统随机可用的 TCP 端口。

*   **Requirement 3.3.2: Sidecar 进程拉起 (Sidecar Spawning)**
    **The Tauri main process shall** 使用 `std::process` 或 Tauri Sidecar API 拉起 Python 进程，并将上述随机端口作为启动参数传入。

*   **Requirement 3.3.3: 健康检查与就绪等待 (Health Check & Readiness)**
    **The Rust main process shall** 在拉起 Sidecar 后通过 HTTP `/health` 或等效探针验证后端就绪状态，并在就绪前向前端展示 Loading 或 Splash Screen。

*   **Requirement 3.3.4: 优雅关闭与资源清理 (Graceful Shutdown & Cleanup)**
    **When** 桌面窗口关闭或主进程收到退出信号时，**the Rust logic shall** 向 Python 子进程发送信号（Unix SIGTERM / Windows TerminateProcess），并确保进程树中无残留进程。

### 3.4 Frontend API 适配与动态端口 (Frontend API Adaptation & Dynamic Ports)

*   **Requirement 3.4.1: 启动端口透传 (Initial Port Handoff)**
    **The Rust main process shall** 在前端初始化阶段（如通过 `invoke` 或环境变量注入）将确定的 Sidecar 端口号告知前端 WebView。

*   **Requirement 3.4.2: 动态 API 基地址 (Dynamic API Base URL)**
    **The Frontend API Client shall** 根据获取到的端口动态拼装 `API_BASE_URL`，确保所有 Axios/WebSocket 请求准确指向本地 Sidecar 进程。

*   **Requirement 3.4.3: Web/Desktop 双轨模式 (Dual-Mode Fallback)**
    **The Frontend shall** 在无法通过 Tauri 注入获取端口时（如运行在纯浏览器环境），自动回退到默认的开发环境配置或报错提示。

### 3.5 Resource Path 动态寻址与打包 (Resource Path Resolution & Packaging)

*   **Requirement 3.5.1: 生产环境资源定位 (Production Resource Resolving)**
    **The Python Backend shall** 实现动态的资源路径解析逻辑，确保在生产环境打包（AppImage/DMG/MSI）后仍能正确访问 `skills/` 目录与 `config/` 文件。

*   **Requirement 3.5.2: 开发与生产环境对齐 (Env Alignment)**
    **The Path Resolver shall** 兼容 `cargo tauri dev`（源码运行）与 `cargo tauri build`（打包运行）两种模式，无需手动切换配置。

### 3.6 P0 回归测试与验收 (P0 Regression & Acceptance)

*   **Requirement 3.6.1: 端口冲突健壮性 (Port Conflict Resilience)**
    **The system shall** 在默认端口被占用的情况下仍能成功启动，通过 T2.3 的随机端口机制证明其健壮性。

*   **Requirement 3.6.2: 进程残留扫描 (Zombie Process Scan)**
    **The P0 test suite shall** 显式验证应用退出后宿主机上无 Python Sidecar 进程残留。

*   **Requirement 3.6.3: 基础业务流闭环 (Core Workflow Smoke)**
    **While** 在 Tauri 桌面环境下运行，**the system shall** 能够成功执行一次完整的 PM 工作流（打开 Skill、执行 Compile、查看结果）。

## 4. Out of Scope

1.  **Phase T3/T4/T5 相关需求**：如自动更新机制、多语言 i18n、系统托盘（Tray）深度定制等。
2.  **SDK 核心重构**：`graph_agent` 的算法逻辑或存储引擎变更。
3.  **生产环境副作用沙盒化**：T2 阶段关注“通不通”，暂不实现对 Python 代码的网络/文件写权限的细粒度沙盒审计。

## 5. Open Questions

1.  **P1 风险：打包体积**：Python Runtime + Backend 依赖的最终体积是否能严格控制在 40MB 以内？若超出，是否需要启动 T2 额外的裁剪任务。
2.  **CI/CD 验收环境**：目前的无头 (Headless) CI 环境如何有效跑通涉及 GUI 的 `cargo tauri dev` 验证？
3.  **Astral Artifact 命名漂移**：如何应对 Astral 发行版命名可能随版本产生的微小变化以确保下载脚本的长久有效？
