# Research & Design Decisions

## Summary

- **Feature**: `graph-agent-optimizations`
- **Discovery Scope**: Complex Integration（21 条需求跨引擎 Core、DeerFlow 同步、仓库结构、样板改造多个层次）
- **Key Findings**:
  - 现有 graph_agent 引擎已具备完整的 checkpoint + human-in-the-loop 基础设施，Studio 只需在 UI 层暴露
  - compiler 对 subgraph + tools/prompt 混写**静默丢弃不报错**是真实 bug，影响 PM 体验
  - DeerFlow 我们 vendored 版本（2026-03-28）相对于上游有至少 6 个未同步的重要 bug fix，**其中 #2251 Memory update 有 data loss 风险**
  - `adaptation_v1` 业务 skill 用 Python dispatcher 胶水绕过框架跑并发，说明"builtin 并发工具"是真实业务需求
  - DeerFlow Subagent 当前不继承父 agent 的 WorkingMemory / DeadEnd 中间件，高并发任务行为不可控

## Research Log

### Topic: checkpoint / human-in-the-loop 机制是否完整

- **Context**：Gemini Round A 认为 "Agent Loop 层 Checkpoint 还比较雏形"；要验证实际代码状态
- **Sources Consulted**：
  - `src/core/graph_agent/deerflow/config/checkpointer_config.py`
  - `src/core/graph_agent/deerflow/agents/checkpointer/provider.py` + `async_provider.py`
  - `src/core/graph_agent/deerflow/client.py` L104-134
  - `src/core/graph_agent/core/harness.py` L159-186, L320-380, L413
  - `src/core/graph_agent/deerflow/agents/middlewares/clarification_middleware.py` L84-151
- **Findings**：
  - Checkpointer 三种 backend（memory / sqlite / postgres）完整支持
  - `harness.resume(state, human_input, thread_id, ...)` 方法（L320-380）完整实现了人工接入后恢复
  - `ask_clarification` / `request_human_input` middleware 完整支持 LangGraph `Command(goto=END)` 异步等待
  - 多个 middleware（guardrails / tool_error_handling）保留 LangGraph 的 interrupt / pause / resume 控制流信号
- **Implications**：
  - Gemini Round A 的判断被推翻。断点重试 / 人工接入点的底层机制**生产级就绪**
  - Studio MVP2 可以直接在 UI 层暴露这三层能力（Graph 层 / Agent Loop 层 / Human-in-the-loop），无需对框架做额外改动
  - 本 spec 的 R14-R17 是关于"让机制更好用"（GC / 中间件继承 / Studio 默认配置），不是"从零新增机制"

### Topic: DeerFlow 上游更新状况

- **Context**：Owner 询问 DeerFlow 有没有更新、哪些功能可优化
- **Sources Consulted**：
  - `git log` on https://github.com/bytedance/deer-flow since 2026-03-28
  - GitHub API `gh api repos/bytedance/deer-flow/commits`
  - PR 详情：#2251, #2107, #2305, #2350, #2321, #2332
- **Findings**：
  - 我们 vendored 版本落后上游 1 个月（2026-03-28 到 2026-04-23）
  - 这期间约 40+ commits，**以 bug fix 为主**（只有 1 个 `feat` — Playwright E2E 测试）
  - **关键严重 bug**：#2251 — Memory update system cache corruption + data loss + thread-safety bugs（`FileMemoryStorage.load()` 返回 cache 直接引用，`_apply_updates()` 就地修改，save 失败时磁盘和内存不一致）
  - 其他重要修复：skill parser YAML 不一致（#2107）、subagent tool_groups 继承（#2305）、clarification 幂等（#2350）
- **Implications**：
  - 本地 copy 存在真实数据丢失风险，P0 优先同步 #2251
  - 上游几乎没有新 feature，同步主要目标是"吃到 bug fix"
  - 同步时要小心 3 个已修改文件（`models/factory.py` 等）带 `# MODIFIED` 标记，merge 保留本地改动

### Topic: adaptation_v1 dispatcher 模式是反模式还是业务场景

- **Context**：初始 Gemini 分析把 `adaptation_v1/tools/beat_dispatcher.py` 定性为"绕过框架的反模式"。Owner 明确纠正这是"应用场景展示不是标准答案"
- **Sources Consulted**：
  - `skills/adaptation_v1/SKILL.md` + `tools/beat_dispatcher.py` / `writer_dispatcher.py`
  - Gemini Round A 和 A+ 的综合分析
- **Findings**：
  - 现有 dispatcher 模式（Python tool 里读子 skill SKILL.md 提取 prompt + 绕过框架直接调 LLM + ThreadPoolExecutor 并发）**确实绕过了认知循环约束**
  - 但这种做法**满足真实业务需求**（并发处理 100 个 scene）
  - 框架当前缺少原生并发机制，业务只能自己写胶水
- **Implications**：
  - 真正的解法是**框架提供 builtin `parallel_map` 工具**（R4），让业务表达"并发调用子 skill"变成声明式
  - 不要"改造 adaptation_v1"或把它当反面教材，它是业务场景展示
  - 有了 R4 后，新业务 skill 的类似场景应该直接用 `parallel_map`，不再写 dispatcher
  - compiler 可以加一条 `W-python-glue-orchestrator` 的 Warning（见 R12），提示存在更好的 subgraph / parallel_map 表达方式

### Topic: Pipeline 是框架概念还是约定

- **Context**：Owner 提到 "pipeline 是生产端概念，skill 在 pipeline 上即插拔"
- **Sources Consulted**：
  - graph_agent 核心代码 grep `pipeline`
  - 项目里 `config/pipeline.yaml` 是否存在
- **Findings**：
  - graph_agent 核心代码（loader / harness / compiler / types）**完全没有 pipeline 这个概念**
  - `src/core/data_manager.py` 依赖 `config/pipeline.yaml`，但项目里**这个文件不存在**
  - DataManager 实际没在正常工作，是死代码
- **Implications**：
  - pipeline 只是"多 skill 组合"的约定，不是框架第一类概念
  - StorageManager 设计（R5）**不引入 pipeline_id / project_id** 到签名；pipeline 编号通过 `runtime_inputs._pipeline_prefix` 作为上下文传入
  - 原 DataManager 废弃（保留为 legacy）

## Architecture Pattern Evaluation

### Decision: StorageManager 放核心还是插件？

- **Context**：PM 用 Studio 时不写 Python，框架默认行为必须让产出能自动落盘；但 Kitchen-Pass 红线要求框架不依赖 host project 存储
- **Alternatives Considered**:
  1. **方案 A**：放 graph_agent 核心代码但作为 default saver 接入（caller 注入的 artifact_saver 优先级更高）
  2. **方案 B**：独立插件包（`pip install graph-agent-storage`），通过 plugin 接口加载
  3. **方案 C**：放核心但通过 `storage.yaml` 配置文件驱动
- **Selected Approach**：方案 A
- **Rationale**：
  - 开箱即用：PM 不写代码就能看到产出落盘（Studio MVP1 必须）
  - 不破坏 Kitchen-Pass：caller 仍可用 `artifact_saver` 注入覆盖（Host project 完全自由）
  - 方案 B 过度设计（不需要多个并行 Storage 实现）
  - 方案 C 违反"SKILL.md 是唯一数据源"理念（引入隐式依赖）
- **Trade-offs**：核心代码稍显臃肿，但通过接口隔离可控
- **Follow-up**：legacy DataManager / ArtifactManager 保留 3 个月后再评估是否删除

### Decision: Phase/node 术语统一方向 — 选 phase

- **Context**：SKILL.md 里用 `<node>` 标签、`nodes/` 目录；代码里 dataclass 叫 `Phase`
- **Alternatives Considered**:
  1. **方向 A**：全部统一成 `node`（改代码 Phase → Node dataclass）
  2. **方向 B**：全部统一成 `phase`（改 SKILL.md 标签 → `<phase>`、目录 `nodes/` → `phases/`）
- **Selected Approach**：方向 B（Gemini 推荐 + Owner 确认）
- **Rationale**：
  - `simple` 类型的 skill 直接写 `<phase_config>` 就能运行，说明 **Phase 是本质、Node 只是 Graph 模式的脚手架**
  - 代码侧 dataclass 已经叫 `Phase`，改 SKILL.md 方向和代码对齐
  - 工程量可控：parser 正则扩展（同时支持 `<phase>` 和 `<node>`）+ 6 个 skill 目录重命名
- **Trade-offs**：需要改 6 个 skill 的目录和标签，但新老并存期间不阻塞
- **Follow-up**：compiler 加 `W-node-to-phase-migration` Warning 引导老 skill 迁移

### Decision: `<step>` 标签不引入表达式求值

- **Context**：Owner 多次提到"step 规范化标签化"；初始讨论考虑过引入 `when` / `skip_if` 表达式
- **Alternatives Considered**:
  1. **方案 A**：`<step>` 标签支持 `when="context.xxx == true"` 表达式，framework 用 simpleeval 求值
  2. **方案 B**：`<step>` 标签只做 prompt 结构化片段，framework 不解释语义
- **Selected Approach**：方案 B
- **Rationale**：
  - compiler F006 规则明确禁止 framework 执行业务代码（`context_mapping` 禁 `$func()`）
  - 条件分支的正确表达是 code-only phase + Python 函数 + validator + retry_target，不是 framework 层表达式
  - `<step>` 只是给 LLM 看的结构化 prompt，framework 不关心它的语义
- **Trade-offs**：PM 想表达"第 3 步条件执行"必须用 phase 拆分，而不是在 step 里加 when
- **Follow-up**：skill_authoring_guide 说明正确的条件表达模式

### Decision: parallel_map 默认并发数 3

- **Context**：Owner 要求"保守起步"、对齐 DeerFlow 现有 subagent 默认值
- **Alternatives Considered**:
  1. 默认 1（完全串行，失去并发价值）
  2. 默认 3（对齐 DeerFlow SubagentExecutor 的 `max_workers=3`）
  3. 默认 10（和业务 dispatcher 的 ThreadPoolExecutor `max_workers=4` 同量级）
- **Selected Approach**：默认 3
- **Rationale**：
  - 和框架现有 subagent 并发数一致，减少"parallel_map 用到的资源池和 subagent 用到的资源池混淆"的可能
  - 先保守、稳定后再放开，避免一开始就压力测试未修好的 DeerFlow 并发 bug
  - Owner 明确偏好
- **Trade-offs**：对高并发业务（100 个 scene）需要显式设置 `max_concurrent=10` 以上
- **Follow-up**：文档里给 PM 示例说明如何调参

### Decision: DeerFlow 上游同步不采用"整体升级"策略

- **Context**：上游 1 个月 40+ commits，有两种同步方式
- **Alternatives Considered**:
  1. **整体升级**：把 vendored deerflow 目录整个替换成最新 main，重新应用本地 `# MODIFIED` 补丁
  2. **按 PR 挑选同步**：只同步确认重要的 6 个 PR，其他留 backlog
- **Selected Approach**：方案 2（按 PR 挑选）
- **Rationale**：
  - 整体升级风险高（40+ 改动，容易引入未察觉的 breaking change）
  - 本项目没有 DeerFlow 完整回归测试套件，整体升级 regress 难以察觉
  - 按 PR 同步更可控，每个 PR 同步后可以单独跑测试
- **Trade-offs**：长期积累的技术债（没同步的 commits 越来越多），需要周期性评估是否整体升级
- **Follow-up**：本 spec 完成后 3 个月再评估一次"整体升级 vs 继续挑选"

### Decision: 不引入 Rust 重写（明确拒绝）

- **Context**：Owner 早期询问 "用 Rust 重写整个项目对长远来说有没有好处"
- **Alternatives Considered**：整体 Rust 重写 / pyo3 局部扩展 / 保持 Python
- **Selected Approach**：保持 Python
- **Rationale**：
  - Agent 编排 99% 耗时在 LLM API 等待（网络 I/O），Rust 优化 CPU 对用户感知为零
  - LangGraph / DeerFlow / Pydantic / Anthropic SDK 主力在 Python，重写要扔掉 11k 行 DeerFlow
  - Rust 的 LLM 生态（async-openai / rig）功能不全
- **Trade-offs**：未来性能瓶颈确实出现时可以做 pyo3 局部扩展（如 md_to_json parser）
- **Follow-up**：明确列为 Non-Goal，不接受任何"为长远考虑重写"的讨论

## Risks & Mitigations

- **R1: DeerFlow PR #2251 同步破坏现有 working_memory 行为** — 迁移前 dump 一份现有 working_memory 状态，迁移后对比；发现不一致立刻回退 PR，分析
- **R2: StorageManager 破坏现有 host project (story_forge)** — 保留 legacy DataManager / ArtifactManager 作为 deprecated shim，现有代码不需要立即迁移
- **R3: `<phase>` 标签迁移导致老 skill 加载失败** — parser 同时支持 `<node>` 和 `<phase>`（兼容期至少半年），compiler 加 Warning 引导
- **R4: Harness.py 拆分引入隐藏 bug** — 拆分前录一遍现有所有业务 skill 的端到端 trace 作为 golden；拆分后所有 trace 必须一致
- **R5: parallel_map 并发跑崩 checkpoint** — 先跑低并发（2）测试，确认 checkpoint GC 策略（R15）工作正常后再放开
- **R6: Nudge 默认从 3 改到 1 让某些业务 skill 稳定性降低** — 跑现有业务 skill 的 regression 测，如有问题让它们显式声明 `max_nudges: 3`
- **R7: 仓库结构整理打乱现有 import 路径** — 兼容 shim 在 `src/core/graph_agent/__init__.py` re-export，保留 2 版本；引导新代码用 `from graph_agent import`
- **R8: Compiler 新增 FATAL 规则让现有业务 skill 跑不起来** — 先 Warning 模式发布 2 周，确认所有 skill 通过后再升级为 FATAL
- **R9: 同步上游 DeerFlow 的 MODIFIED 文件冲突** — 先 dry-run（三路 merge），冲突手动 resolve；保留详细 commit message 便于回溯

## References

- `docs/graph_agent_docs/FRAMEWORK_UNDERSTANDING.md` — 框架完整心智模型
- `docs/studio/README.md` — Studio 消费者视角
- `plan.md` — 原始需求记录
- DeerFlow 上游：https://github.com/bytedance/deer-flow
- LangGraph 文档：https://langchain-ai.github.io/langgraph/
- Anthropic Skill：https://docs.anthropic.com/en/docs/agents-and-tools/skills
