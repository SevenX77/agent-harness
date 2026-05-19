# Research Log & Decisions

## 1. Summary
- **Feature**: Skill Studio API Planning & MVP1 Scoping
- **Discovery Scope**: Front/Backend Refactoring, User Editing Patterns, API Surface expansion, Process Execution Models, File System Layout, IO Schema Validation.
- **Key Findings**: 
  - Kiro spec 设想的 "完全不让用户编辑 Markdown" 过于教条，PM 对于 Prompt 微调有着强烈的低摩擦（Monaco）诉求。
  - Pydantic 模型在底层已经完备，借此消除前端冗余的正则表达式可以极大降低代码腐化率。
  - 断点重试（Resume）和基线对比（Golden）的 API 结构必须在此版本一次性固定，防止未来破坏性改动。
  - 长耗时任务需要严格与主 FastAPI 进程隔离，避免占用事件循环。
  - File System 是 Studio 管理版本的唯一基石，不需要过度设计独立版本控制系统。

## 2. Architecture Pattern Evaluation

| Option | Approach | Assessment / Rationale | Status |
|--------|----------|------------------------|--------|
| A. 单进程内嵌 (In-process asyncio) | 直接在 FastAPI 进程 await `harness.run` | 会阻塞事件循环或引发多线程资源冲突。无法应对极长耗时 Agent 任务。 | Rejected |
| B. 子进程 + REST Callback | 拉起独立进程，通过 HTTP Hook 推送状态 | 引入多余的服务发现和端口分配复杂性，不符合桌面级工具定位。 | Rejected |
| C. Celery Worker / Redis | 重量级队列+Worker节点异步处理 | 过度设计，显著增加部署负担（需额外启动 Redis/Worker）。 | Rejected |
| **D. Multiprocessing + Asyncio Queue** | **`run_skill` 放子进程执行，通过 Queue 桥接，WebSocket 读取 Queue** | **简单轻量，无外部依赖，隔离长时计算，保障主循环响应性。** | **Selected** |

## 3. Decision Log

### D1: mvp0 处置方案
- **Context**: `/tmp/mvp0-prototype` 已经有一个界面丰满但核心逻辑为 mock 的版本。
- **Alternatives Considered**: 1. 完全基于其代码继续写；2. Frontend Refactor + Backend Rewrite；3. 全部抛弃重写 (Scrap)。
- **Selected Approach**: **Frontend Refactor + Backend Rewrite**。
- **Rationale**: UI 组件（ReactFlow/Monaco/Tailwind）价值很高，值得保留。而后端结构是纯 stub，且前端的数据获取逻辑为正则硬编码，无法支撑长远发展。
- **Trade-offs**: 需要花费数天剥离前端与正则的强耦合。
- **Follow-up**: 验证接入真实 `SkillManifest` API 后画布布局渲染的正确性。

### D2: Monaco vs Open CLI 双轨制裁决
- **Context**: Kiro spec 曾提倡“不内嵌代码编辑，纯粹依赖 Copilot”。
- **Alternatives Considered**: 1. 坚持纯 CLI 驱动；2. 提供完整的 Monaco 编辑；3. 双轨并行（两者都支持）。
- **Selected Approach**: **Dual-Track Editing (双轨制)**。
- **Rationale**: 调和 PM 习惯与 Copilot 哲学。复杂的阶段编排（Topology）交给 CLI，低摩擦的高频文本修改（Content）交给 Monaco。
- **Trade-offs**: 增加了状态同步复杂度，必须依赖 FileWatcher 来解决外部修改导致的前端数据陈旧问题。
- **Follow-up**: 确认 FileWatcher 触发更新时不会导致用户正在 Monaco 中未保存的内容意外丢失。

### D3: WebSocket Channel 拆分策略
- **Context**: 需要通过 WebSocket 传递 Agent Trace 事件、终端流以及系统的其他通知。
- **Alternatives Considered**: 1. 单 Channel 聚合所有消息；2. 按运行/终端/全局切分多 Channel (per-run / per-event-type)。
- **Selected Approach**: **多 Channel 拆分 (`/ws/runs/{run_id}`, `/ws/terminal/{term_id}`, `/ws/events`)**。
- **Rationale**: 职责清晰，减少消息路由判断。关闭终端不会影响正在推送的 Run Trace。
- **Trade-offs**: 客户端需要维护多个 WS 实例的生命周期。
- **Follow-up**: 前端使用统一的 WS Hook 封装处理重连和心跳。

### D4: Subprocess 隔离策略
- **Context**: 运行 `run_skill()` 可能长达几分钟，且可能含有死循环。
- **Alternatives Considered**: 1. In-process Asyncio Task；2. ThreadPoolExecutor；3. `multiprocessing` / OS Subprocess。
- **Selected Approach**: **OS Subprocess (`multiprocessing.Process` 或 `subprocess.Popen`)**。
- **Rationale**: Python GIL 限制了线程的隔离能力，极端异常可能导致 FastAPI 挂掉。子进程保证了运行失败或被强杀（Cancel）时彻底回收资源。
- **Trade-offs**: 进程间通信（IPC）需要序列化事件（如通过 pipe 或 queue 序列化 Pydantic 模型）。
- **Follow-up**: 保证事件流可以稳定地跨进程通过 Queue 发送至 FastAPI 的 WS 路由。

### D5: 前端状态管理选型
- **Context**: 剥离正则逻辑后，前端需要管理基于 API 结果的响应式状态。
- **Alternatives Considered**: 1. 原生 `useEffect` + `useState`；2. SWR；3. React Query；4. Zustand (全局状态)。
- **Selected Approach**: **SWR (或 React Query 等价库)**。
- **Rationale**: Studio 是典型的数据驱动面板应用，核心是对 `SkillManifest` 的获取和突变 (Mutation)。SWR 提供的缓存和自动重验非常符合 "FileWatcher 触发 -> 重新验证" 的场景。
- **Trade-offs**: 引入额外的第三方依赖库。
- **Follow-up**: 统一全局所有的 Fetch 逻辑到 custom hooks 中。

### D6: FileWatcher 选型
- **Context**: 必须检测到外部 CLI 对 `SKILL.md` 的修改。
- **Alternatives Considered**: 1. 轮询 (Polling)；2. `watchdog` (Python 跨平台)；3. OS 原生 (`inotify-tools`)。
- **Selected Approach**: **`watchdog`**。
- **Rationale**: 是 Python 生态的行业标准，无需依赖宿主 OS 的原生二进制工具，且响应延迟在接受范围内（通常 < 50ms）。
- **Trade-offs**: 在大规模目录下可能消耗较多文件句柄，但目前限定在特定 Skill 目录下可以接受。
- **Follow-up**: 优化去重逻辑（debounce），避免编辑器保存引发连续多次的 `skill_changed` 事件。

### D7: 版本管理选型
- **Context**: PM 需要追溯修改历史和版本锁定。
- **Alternatives Considered**: 1. Studio 内部构造专用的文件副本历史系统；2. 使用底层的 Git 命令行和引擎自动 Run ID 分配。
- **Selected Approach**: **Git-based (不内建系统，依托外部 Git 与目录锁)**。
- **Rationale**: 造轮子风险高，且 CLI 修改文件无法被内置逻辑全覆盖。直接在 Monaco 保存时触发系统级别的 `git commit` 可完美整合。对于执行结果，交给 `StorageManager` 基于时间的天然清理和 `.golden` 后缀锁定解决。
- **Trade-offs**: 回退与分支等高阶能力无法在简单的 Studio 界面展现，必须诉诸终端。
- **Follow-up**: 实现后台自动 Git Init 及 Commit 的无缝触发流程。

### D8: 输入输出 schema 校验时机
- **Context**: 数据格式错配极易导致 Agent 运行时崩溃，需要确立明确的校验拦截点。
- **Alternatives Considered**: 1. 只有 Agent 执行到了该阶段才进行模型报错；2. 贯穿数据生命的上传、运行前、运行后和保存时刻的多阶段校验。
- **Selected Approach**: **Upload-time + Run-time (前置) + Run-time (后置) + Golden-lock-time 全流水线校验**。
- **Rationale**: Fail-fast 原则，最早在 `POST /test_inputs` 端点就能基于 `io.inputs` 阻止错误进入。Run 前再次校验防止中间发生 DSL 变更。
- **Trade-offs**: 在多个 API 内都要进行 Pydantic Model Re-validation，略微增加了路由开销。
- **Follow-up**: 实现对 Pydantic `ValidationError` 的通用解析并友好高亮返回 `LintError` 格式。

## 4. Open Questions

**Blocking (Yes):**
- **Q1**: `graph_agent` 的 `compile_skill` 目前返回的是何种结构？后端如何将其精确映射到 `LintError` 格式以指明错误行号？ (需查阅 `core/compiler.py` 的具体 API 签名)。

**Non-Blocking (Future):**
- **Q2**: PTY (`ptyprocess`) 在非 POSIX 环境（如 Windows）下兼容性较差，这是否会阻碍未配置 WSL 用户的本地开发？
- **Q3**: 如何在不打断用户 Monaco 未保存编辑的情况下，优雅合并 FileWatcher 带来的远程代码更新（类似 VSCode 的合并冲突弹窗）？
