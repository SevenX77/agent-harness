# 研发端 Tauri 迁移及全案架构重构记录 (Migration & Architecture Plan)

**日期**: 2026-05-05
**目标**: 记录将项目分离为研发端（Studio）、生产端（Cloud）以及核心引擎的代码仓库重组计划，同时确认研发端由 CLI 模式转向 Tauri 桌面应用。

---

## 1. 核心架构与部署形态决策

经过对体验和工程量的综合评估，我们决定调整系统的部署和交付形态：

1. **研发端 (Studio / Dev)**：废弃纯 CLI (`studio dev`) 启动方式，迁移为 **Tauri 桌面客户端应用**（内置便携版 Python）。这为内部 PM 提供了“双击即开”的极致原生体验，彻底消除了配置环境的壁垒。
2. **生产端 (Cloud / Prod)**：面向 C 端的纯 Web SaaS 应用，确保底层代码、prompt 和工具逻辑（`SKILL.md`）不被逆向或拆包窃取。
3. **核心引擎 (GraphAgent)**：剥离为独立的 Python 依赖包，被以上两端共同引用，保证两端逻辑绝对一致。

## 2. 项目文件架构调整 (Monorepo Reorganization)

为了支撑上述决策，解决当前单体代码混合带来的耦合，我们必须将当前的仓库结构进行**模块化隔离改造**，形成标准的 Monorepo 工作区结构：

### 目标目录结构规划

```text
agent-harness/
├── packages/
│   └── core-engine/           # 【独立包】纯净的 graph_agent 引擎核心库
│       ├── pyproject.toml     # 定义独立版本号 (如 v0.1.0)
│       └── src/graph_agent/   # 将目前的 src/core/graph_agent 迁移至此
│
├── apps/
│   ├── studio/                # 【研发端】给 PM 用的本地开发桌面应用
│   │   ├── studio-frontend/   # React/Vite 前端，包装进 Tauri 外壳
│   │   └── studio-backend/    # FastAPI 伴生进程 (Sidecar)，连接本地硬盘与内存队列
│   │
│   └── production/            # 【生产端】面向 C 端的云生产服务
│       ├── cloud-frontend/    # 面向 C 端的 Web 网页前端 (如 Next.js)
│       └── cloud-backend/     # FastAPI 网关 + Temporal/Celery Worker，连接 S3/Redis/PG
```

### 依赖与隔离原则：
1. **单向依赖（单一真相来源）**：`apps/studio` 和 `apps/production` 都将 `packages/core-engine` 作为其依赖项。所有 `SKILL.md` 协议模型、Graph 节点定义只能存在于引擎包内。
2. **应用层硬隔离**：`apps/studio` 和 `apps/production` 之间**严禁互相引用**。它们有各自的生命周期、部署方式和六边形架构适配器实现。
3. **运行一致性约束**：研发端 Tauri 打包和生产端云端部署，必须锁定同一个 `core-engine` 的精确版本。

## 3. 研发端 (Tauri) 工程化实施细节

在隔离完成后，针对 `apps/studio` 的 Tauri 化改造方向：

- **前端 (Tauri + React/Vite)**：
  - 核心逻辑复用当前的 `studio-frontend` 代码库。
  - 引入 `@tauri-apps/api` 与 `@tauri-apps/cli` 获得桌面原生能力（如窗体控制、托盘图标）。
  - UI 增加启动时的“环境自检/服务就绪”遮罩层动画。

- **后端引擎 (Python Portable Runtime)**：
  - 核心业务调用 `core-engine`，路由 API 复用 `studio-backend`。
  - 在 Tauri 打包阶段，自动下载对应系统架构（macOS/Windows）的 Standalone Python 构建版本。
  - 预先生成并打包好一个拥有锁定版 `site-packages` 的虚拟环境，随安装包分发。

- **进程桥接 (Tauri Sidecar)**：
  - Tauri 主进程（Rust）启动后，作为守护进程拉起内置的 Python 可执行文件，启动 FastAPI。
  - 前端 Webview 仍然通过 HTTP / WebSocket 与这个本地后台进程通信。
  - Tauri 监控 Python 子进程生命周期，当用户关闭应用时，优雅地清理后端进程，防止端口残留。

## 4. 当前状态
**Status: 规划与技术选型已确认，文档已归档。接下来将优先梳理现有 Web 前端的业务逻辑，为重构打底。**
