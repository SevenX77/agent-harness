# Requirements: Studio Next MVP

## Introduction

本规范定义了 Skill Studio 下一个 MVP（代号 MVP1-Extended）的交付标准。
基于 `graph_agent` 引擎在 Phase 0/1 的重构成果（`SkillManifest` 契约、`CallbackEvent` 类型化）以及 `mvp0` 前端原型的现有资产，我们将交付一个能真正驱动底层引擎、支持 PM “编辑-运行-观察” 闭环的完整工具。

本阶段的核心战略是**一次性规划完整的 API 表面**（覆盖 MVP1~MVP3），以避免后续频繁的破坏式改动，并在产品哲学上确立**“Dual-Track 双轨编辑”**模式，解决 Kiro spec 与实际工程（mvp0）的冲突。

## Objectives & Non-Goals

**Goals (In Scope):**
- 彻底废除前端正则解析 SKILL.md 的技术债，改为后端统一输出 `SkillManifest`。
- 接通真实的 `graph_agent` 引擎，替代 mvp0 的 Mock 数据。
- 确立 API 全集契约（包含为 MVP2 预留的重试和人工接入端点）。
- 提供 Monaco 与 CLI 双轨编辑模式，打通 Lint 与 Trace 实时流。
- 确立标准化的文件系统工作区布局与运行产物落盘结构。
- 提供基于 Git 的轻量级技能版本管理方案。

**Non-Goals (Out of Scope):**
- 暂不实现用户工作区隔离（P1.5 强制 Gate 任务）。
- 暂不实现画图连线修改 DSL 的能力（画布保持纯只读）。
- 暂不实现完整的意图偏离检测与双对话框 CCB（推迟至 MVP3）。
- 暂不实现团队协作功能（评论、diff 审批，P2+ 考虑）。
- **暂不在 Studio 内置复杂的版本回退 UI（依靠底层的 git 机制即可）。**

## Requirements List

### Requirement 1: API-Driven Skill Loading (替代前端正则解析)
**Objective:** The system shall 提供类型化的 `SkillManifest` API，消除前端通过正则硬解析 SKILL.md 的技术债。
1. **When** 前端请求一个 skill 详情时，the system shall 返回基于 `graph_agent` Pydantic `SkillManifest` 序列化的完整 JSON 描述。
2. **When** 前端渲染画布时，the system shall 根据 JSON 中的 `phases`、`subgraph` 及其关联关系来绘制节点，不再读取原始 Markdown 文本。
3. **When** 后端解析遇到语法错误时，the system shall 返回 422 错误及结构化错误原因，前端展示报错占位视图。

### Requirement 2: Real Engine Execution & Subprocess Isolation
**Objective:** The system shall 使用真实的 `run_skill` 和 `compile_skill` 替代现有的 Mock 实现，并保证运行时隔离。
1. **When** 用户点击 Lint，the system shall 调用引擎的 `compile_skill()`，并返回包含具体行号的结构化错误列表。
2. **When** 用户点击 Run，the system shall 在隔离的子进程中拉起 `run_skill()`，防止长耗时运行阻塞主线程，并通过 WebSocket 流式下发 `CallbackEvent` 结构体。
3. **When** 发生错误时，Trace Timeline shall 高亮异常节点，并支持展示 `SkillCompileError` 或 `RuntimeError` 细节。

### Requirement 3: Dual-Track Editing (Monaco Editor)
**Objective:** The system shall 保留 Monaco 以支持高频 Prompt 微调，调和 PM 使用习惯。
1. **When** PM 需要微调提示词时，the system shall 允许在 Monaco 编辑器中直接修改并按 `Ctrl+S` 保存。
2. **When** 文件保存时，the system shall 后端同步更新内容并自动触发 Lint，前端显示更新后的状态。

### Requirement 4: Dual-Track Editing (Open CLI)
**Objective:** The system shall 提供 Open CLI 支持结构性修改，满足 Copilot 优先的编辑哲学。
1. **When** PM 需要添加 Phase 或大幅调整结构时，the system shall 提供 Open CLI 按钮，唤起绑定当前目录的 PTY 终端。
2. **When** 终端启动，the system shall 预置好 `claude` 命令环境并支持在浏览器中双向输入输出。

### Requirement 5: FileWatcher & Event Notification
**Objective:** The system shall 监控本地文件变更，确保 UI 与磁盘状态一致。
1. **When** 通过 CLI 或外部工具修改了 SKILL.md 文件，the system shall 通过 FileWatcher 捕捉到文件系统事件 (inotify/fsevents)。
2. **When** 变更被捕捉，the system shall 通过 WebSocket 发送 `skill_changed` 事件，前端收到后弹出 Toast 提示并可选重新拉取数据。

### Requirement 6: Trace Persistence
**Objective:** The system shall 持久化每次运行的 Trace 数据，以便后续回放与分析。
1. **When** 运行进行中，the system shall 将接收到的 `CallbackEvent` 落盘为 `tracing.jsonl` 格式。
2. **When** 前端请求历史运行详情时，the system shall 读取落盘的文件并重构为完整的 Trace 流。

### Requirement 7: Unified API Surface (前瞻性设计)
**Objective:** The system shall 设计并实现覆盖 MVP1-MVP3 需求的完整 API 接口契约，避免反复破坏式更新。
1. **The system shall** 预先定义好 Golden Baseline、Test Inputs、Resume 等功能的 REST endpoint 路径及请求响应模型（对于暂未实现的功能返回 501 Not Implemented）。
2. **The system shall** 使用统一的 HTTP Status Code 规范和内部 `ErrorResponse` schema，明确区分校验错误、运行时错误与系统错误。

### Requirement 8: Resume & Human-in-the-Loop Readiness
**Objective:** The system shall 在 API 与 WebSocket 契约中预留断点重试和人工接入点支持，为 MVP2 打下基础。
1. **The system shall** 预留 `POST /api/skills/{id}/runs/{run_id}/resume` 接口的完整结构。
2. **The system shall** 在 WebSocket 协议中定义双向数据流：服务端能推送 `ask_human_input` 事件，客户端能发送 `human_input_response` 负载。

### Requirement 9: Workspace File System Layout
**Objective:** The system shall 确立标准化的工作空间与公共模板库的文件目录布局。
1. **When** Studio 启动时，the system shall 识别 `skills/` 为只读的公共模板库，并识别 `workspaces/<uid>/skills/` 为当前用户的私有读写区。
2. **When** PM 对某个技能产生新的测试素材、历史运行记录或 Golden Baseline 时，the system shall 严格按照约定的子目录结构 (`test_inputs/`, `runs/`, `golden/`) 将其落盘，避免污染技能自身的业务代码。

### Requirement 10: PM Skill Lifecycle Operations
**Objective:** The system shall 提供支撑 PM 从新建到测试、分享的完整技能生命周期流转 API。
1. **When** PM 需要新建技能时，the system shall 允许基于空白描述让 Copilot 初始化，或从公共库通过 `fork_from` 复制一个模板技能的全部目录内容。
2. **When** PM 需要导出技能分享给其他人时，the system shall 提供 API 将该技能目录（含测试输入和 Golden，但不含大体积的历史运行产物）打包为 `.tar.gz` 供下载。

### Requirement 11: Skill Version Management (light, git-based)
**Objective:** The system shall 依赖底层的 Git 机制提供轻量级的文本版本追踪，不自造冗余的历史管理系统。
1. **When** Studio 对私人技能目录进行第一次保存或初始化时，the system shall 提供快捷方式或自动执行 `git init`。
2. **When** PM 通过 Monaco (调用 PUT 接口) 保存 `SKILL.md` 时，the system shall 自动执行 `git commit`（如 "Studio edit at <ts>"），让所有修改都有追溯源。

### Requirement 12: Test IO + Schema Validation Pipeline
**Objective:** The system shall 提供多阶的 Schema 校验机制，确保输入输出数据符合 `SKILL.md` 声明的 Pydantic 模型契约。
1. **When** PM 上传一份测试输入 JSON，the system shall 立即读取该技能 `io.inputs` 的定义对其进行 Pydantic 校验，不通过则拒绝上传并返回 422 错误。
2. **When** 技能被提交执行 (Run) 前，the system shall 再次校验选择的测试输入是否符合当前的 `io.inputs` 声明，防止因 `SKILL.md` 变动导致的隐式失效。

## R1~R37 Requirement Mapping

| Feature / Requirement | Roadmap Phase | Endpoint/Component Coverage | Status |
|-----------------------|---------------|------------------------------|--------|
| R1, R2, R8, R9 (可视化/详情) | MVP1 | `GET /api/skills/{id}`, ReactFlow | In |
| R3, R4 (创建/修改) | MVP1 | `POST /api/skills`, `PUT /api/skills/{id}` | In |
| R5, R13, R23 (Prompt/参数展示) | MVP1 | `SkillManifest`, Prompt Inspector | In |
| R6, R10, R12, R19, R20 (运行/Trace) | MVP1 | `POST /api/skills/{id}/runs`, WS `/ws/runs/{run_id}` | In |
| Open CLI / Dual-Track 编辑 | MVP1 | `POST /api/skills/{id}/terminal` | In |
| FileWatcher 同步 | MVP1 | WS `/ws/events` | In |
| R11, R28, 新方法论 (Test/Golden) | MVP2 | `GET/POST /api/skills/{id}/golden`, `/test_inputs` | Deferred |
| R21, R22 (历史与回放) | MVP2 | `GET /api/skills/{id}/runs/{run_id}` | Deferred |
| 断点重试/人工接入 | MVP2 | `/resume` endpoint, WS bidir event | Deferred |
| R37 (User Isolation) | P1.5 | `X-Studio-User-ID` Header | Deferred |
| R26, R27 (偏离检测等) | MVP3/P2+ | `GET /api/skills/{id}/runs/{run_id}/audit` | Deferred |
