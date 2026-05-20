# docs/ — Studio Baseline Reset 2026-05-20 (WIP)

> **Branch**: `docs/baseline-reset-2026-05-20` (off `main`).
> **状态**: WIP — 结构已 lock (PM 2026-05-20 拍板), 内容由 a1 写 `baseline.md` / a2 写 `mvp0-alignment.md`, master PM 写 INDEX + final 整合。
> **旧 docs/ 全量备份**: `docs.backup-2026-05-20/` (165 文件, 全 git rename 不丢)。重整收敛 + ship 后由 PM 拍板是否删备份。

---

## 重整目标 (PM 2026-05-20)

1. 原 13 份单 `.md` 升级成 **feature-per-folder** 结构
2. **studio + engine 域**每个 feature folder 内含双时态 2 份: `baseline.md` (当下代码实现逻辑) + `mvp0-alignment.md` (下一步对齐 MVP0 的改造逻辑)
3. **architecture 域** 2 份核心文档也走双时态 (V2.1 重大演进, baseline ↔ MVP0 心智模型差距明显)
4. **development / references** 平铺单 `.md`, 不走双时态
5. 文档要**详细 + 用人话 + 术语必解释 + 不省字 + 引用代码用 `file:line`**

## MVP0 目标 (锁定, 出处见 docs.backup-2026-05-20/STUDIO-BASELINE-2026-05-17 + PM 2026-05-17 复述)

PM 不开终端、不写 YAML, **可视化编辑 / 改 / 跑 V2.1 skill, 跑完看每 phase 输入输出**。

---

## 目录树

```text
docs/
├── INDEX.md                                              ← 本文件
├── architecture/
│   ├── agent-cognitive-architecture/
│   │   ├── baseline.md
│   │   └── mvp0-alignment.md
│   └── prod-dev-separation/
│       ├── baseline.md
│       └── mvp0-alignment.md
├── engine/
│   ├── skill-compilation/{baseline,mvp0-alignment}.md
│   ├── execution-runtime/{baseline,mvp0-alignment}.md
│   ├── state-and-io-contract/{baseline,mvp0-alignment}.md
│   └── tracing-and-observability/{baseline,mvp0-alignment}.md
├── studio/
│   ├── system-level/
│   │   ├── ux-workflow/{baseline,mvp0-alignment}.md
│   │   ├── studio-layout/{baseline,mvp0-alignment}.md
│   │   └── workspace-file-system/{baseline,mvp0-alignment}.md
│   └── feature-folders/
│       ├── canvas-topology/{baseline,mvp0-alignment}.md
│       ├── copilot-assistance/{baseline,mvp0-alignment}.md
│       ├── trace-visualization/{baseline,mvp0-alignment}.md
│       ├── multi-file-editor/{baseline,mvp0-alignment}.md
│       ├── llm-provider-config/{baseline,mvp0-alignment}.md
│       └── skill-lifecycle/{baseline,mvp0-alignment}.md
├── development/
│   ├── CONTRIBUTING.md
│   └── FRONTEND_UI_SPEC.md
└── references/
    └── claude-agent-sdk.md
```

**统计**: 15 feature folder × 2 双时态 md = 30 + INDEX.md + 3 flat md = **34 个 .md**。

---

## Feature scope (一句话, 详见各 folder 内 baseline.md)

### Engine (4 个 feature, 全走双时态)

| Feature | Scope |
|---|---|
| [skill-compilation](./engine/skill-compilation/) | V2.1 技能目录解析、AST 构建、图拓扑校验、静态 IO 数据流校验 (audit A7/A8)、编译缓存策略 |
| [execution-runtime](./engine/execution-runtime/) | Graph 执行装配调度、主入口生命周期 `run_skill`、节点重试、subagent / `call_subgraph` 动态工具注入 (audit A4/A5) |
| [state-and-io-contract](./engine/state-and-io-contract/) | `BlackboardState` 规约 (data/flow/messages)、Reducer 并发冲突控制、阶段级 IO 隔离、Runtime Input 漏斗 (audit A1/A2/A3/A6) |
| [tracing-and-observability](./engine/tracing-and-observability/) | Predict 内部与 LangGraph 节点拦截、生命周期事件发出、结构化 Trace 日志 (audit P1-4) |

### Studio system-level (3 份系统级, 横切多 feature, 全走双时态)

| Feature | Scope |
|---|---|
| [ux-workflow](./studio/system-level/ux-workflow/) | 贯穿多个 feature (canvas → editor → trace) 的用户核心操作流蓝图 |
| [studio-layout](./studio/system-level/studio-layout/) | 全局 React Shell 区域切割、Resizable 面板通信、Context 派发 |
| [workspace-file-system](./studio/system-level/workspace-file-system/) | Tauri/Rust IPC 桥接真实文件系统 (Watcher + Dir R/W) + 前端内存 Draft Persist |

### Studio feature folders (6 个 feature, 全走双时态)

| Feature | Scope |
|---|---|
| [canvas-topology](./studio/feature-folders/canvas-topology/) | React Flow 画布微观 / 宏观拓扑展现、节点连接、布局流 |
| [copilot-assistance](./studio/feature-folders/copilot-assistance/) | 侧边栏对话驱动、智能 diff 气泡、代码补全、`@mentions` |
| [trace-visualization](./studio/feature-folders/trace-visualization/) | 历史溯源、瀑布流展示、图节点边级错误追踪 (Edge Inspection / Compile 结构化报错) |
| [multi-file-editor](./studio/feature-folders/multi-file-editor/) | 焦点联动 (split-editor)、VSCode 风格侧边文件树、代码编辑器核心 |
| [llm-provider-config](./studio/feature-folders/llm-provider-config/) | LLM Role 覆盖、多 Provider API Keys 本地存取、连通性测试面 |
| [skill-lifecycle](./studio/feature-folders/skill-lifecycle/) | 新技能引导创建向导、模板复用、批处理测试、Golden 历史对比、导入 / 导出 |

### Architecture (2 份核心, 走双时态)

| Doc | Scope |
|---|---|
| [agent-cognitive-architecture](./architecture/agent-cognitive-architecture/) | baseline: 旧 `GraphAgentHarness` 单文件线性控制流; MVP0: V2.1 LangGraph DAG + LOGIC/SUBGRAPH/SKILL 三态心智模型 |
| [prod-dev-separation](./architecture/prod-dev-separation/) | baseline: Harness / Callbacks / Schema 缠绕现状; MVP0: Engine 降为纯节点合集 + Studio 降为外部唤起壳 (audit A1-A8 整体解 conflict) |

### Development (平铺, 不双时态)

- [development/CONTRIBUTING.md](./development/CONTRIBUTING.md) — 贡献规范 / PR 约定 / 三 agent 分工
- [development/FRONTEND_UI_SPEC.md](./development/FRONTEND_UI_SPEC.md) — 前端 UI 规范 (design tokens / shadcn 风格 / 组件用法)

### References (平铺, 不双时态)

- [references/claude-agent-sdk.md](./references/claude-agent-sdk.md) — Anthropic Claude Agent SDK 原始 API 文档 (vendor ref, 我们引用的第三方 SDK)

---

## 5 维 section 模板 (双时态文档强制)

每个 `baseline.md` / `mvp0-alignment.md` 必须含以下 5 维 section, 按顺序排列。Engine 域允许把 `UI/UX` + `前端逻辑` 显式写 "N/A — 此模块为纯 backend library, 无 UI / 无前端调用面" 而不是省略 (让阅读者一眼看到不是漏写)。

````markdown
## UI/UX
本维描述从用户角度看到的视觉反馈、面板状态变迁、极端场景 (空、错误时) 的呈现模式。

例: Copilot 对话中流式输出时消息气泡的 typing 态效果与 Diff 组件弹出。

## 前端逻辑
React 侧基于用户操作如何触发状态流转 (Zustand Store / Context), 以及核心的渲染前置计算逻辑。

例: `useCopilotStore` 如何更新消息列表, 触发请求后端 API, 维护 `isLoading` 标志。

## 后端功能
Python (Studio Backend) / 底层引擎 (graph-agent) 在接收指令后的业务执行链路、文件操作、核心对象计算 (无网络外壳)。

例: 引擎 Compiler 在验证阶段读取 `io/inputs.json` 失败后抛 Error 的具体算法步骤。

## API
模块 / 系统之间的契约边界。前后端 REST 定义、Tauri IPC `invoke` 签名、或系统公开的 Python `def`。

例: `compile_skill(skill_root: Path) -> CompiledSkill` 函数签名 + 返回结构 + 错误返回。

## Data Model / State
决定运行机制的持久化 Schema、黑板内存态、跨周期实体。**5 维核心底座**。

例: V2.1 `BlackboardState` TypedDict (data / flow / messages) + Reducer 顺序覆盖语义。
````

---

## Cross-feature interaction 双向引用规则

某 feature 调用 / 影响另一 feature 时, 不在两边都写细节, 用**双向引用**:

**Owner 一侧** (谁实现 / 触发能力, 在本端 section 写完整细节 + 加锚点):

````markdown
### 节点生成触发 {#cross-copilot-node-gen}

当 LLM 确认需生成新阶段时, Copilot 后端发出 `Event<NodeCreated>`. 此时订阅端需...
````

**引用一侧** (被影响方, 只放 markdown link 不复述细节):

````markdown
画布通过监听 Event Bus 接收新节点插入通知并重绘排版, 此生成源头的详细机制请见:
[Copilot 辅助: 新拓扑节点生成机制](../../feature-folders/copilot-assistance/mvp0-alignment.md#cross-copilot-node-gen).
````

**锚点命名约定**: `#cross-{owner-feature-name}-{action}` (例 `#cross-copilot-node-gen`)。

---

## Writing conventions (写每份 baseline / mvp0-alignment 前必读)

1. **人话**: 不用业内黑话, 任何术语 / 项目代号 (例 `a1` / `a2` / `ccb` / `tmux pane` / `LangGraph` / `Tauri IPC`) 第一次出现给定义 + 例子。
2. **不省字**: 每概念展开到一个没读过代码的 PM 也能读懂。简洁不等于省字。
3. **`file:line` 引用**: 任何代码引用必须形如 `packages/graph-agent/src/graph_agent/core/runner.py:161`, 让读者能直接 jump。**写之前必须自己 `grep -n` 实证存在, 不许凭印象 / 不许照搬历史路径**。
4. **跨句因果完整连接词**: 用 "因为...所以..." 不用 "故" "即" 这种省略连接词。
5. **5 维**: 严格 5 个 section (`UI/UX` / `前端逻辑` / `后端功能` / `API` / `Data Model / State`), 顺序固定, 不漏 section (engine 无 UI 那 2 维显式写 `N/A — ...原因`)。
6. **Cross-feature**: 用上面的双向引用规则, 不在多份文档复述同一段细节。

---

## Dispatch 分工 (谁写什么, 何时写)

| 任务 | Owner | 依据 SOP |
|---|---|---|
| 全部 `baseline.md` (15 份) | **a1 (Codex)** — 主力编程 agent, 读代码最深 | [01-sop-role-delegation.md](~/.claude/rules/01-sop-role-delegation.md) §1 |
| 全部 `mvp0-alignment.md` (15 份) | **a2 (Gemini)** — 设计阶段思考 agent, 主管 next-step 设计 | [07-sop-design-phase-no-thinking.md](~/.claude/rules/07-sop-design-phase-no-thinking.md) |
| INDEX.md 整合 + final commit | master PM | — |
| 横切关注点 (`state-management` / `event-bus-and-websocket` / `tauri-ipc-bridge`) | 待 PM 拍板是否单独开 folder | — |

**派工方式**: master PM 用 `ccb ask --wait a1 / a2` 派, brief 文件落 `/tmp/`. 每次派完 capture pane 验证没越界 + reply 跟 pane 一致。

---

## 备份与回溯

旧 docs/ 全部 165 文件保留在 `docs.backup-2026-05-20/`, 包含:

- 原 13 份 baseline 主题 (architecture / engine / studio / development)
- 旧 `archive/` 152 份历史 (architecture_history / engine_history / studio_history / superpowers_history / v1-reset / e2e_traces 等)
- **engine code 全量审计**: `docs.backup-2026-05-20/engine/graph-agent-audit/graph-agent-audit-merged-authoritative__by-codex-2026-05-20.md` (1136 行, Codex 跑过 V2.1 主路径实测, 是 engine baseline / mvp0-alignment 写作的权威输入)
- **最新 cross-validation audit**: `docs.backup-2026-05-20/archive/2026-05-19-studio-baseline-audit.md` (PR #81)

写 baseline / mvp0-alignment 时, 可以引用这些备份文件路径作为论据。
