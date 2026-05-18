# Tasks: Subagent Implementation

## Phase 1: Engine Core (a1, ~1 day, blocking Phase 2)

### T1.1 — SKILL.md parser 扩展支持 `phase_config.subagents` (~4h)
- Owner: a1
- Location: `packages/graph-agent/src/graph_agent/core/loader.py` (修改), `packages/graph-agent/tests/core/` (新增/修改测试)
- 工作:
  - 在 `mode: skill` 的 `phase_config` 中识别可选 `subagents:` 列表字段。
  - 字段 schema 固定为 `[{name: str, path: str, description: str}]`。
  - `name` 用于生成 tool 名称 `call_subagent_<name>`; 保持 deterministic, 非法名称编译期报错。
  - `path` 按 phase root 相对路径解析, 不引入新的 mode 类型。
  - 保持无 `subagents:` 的现存 skill 编译行为不变。
- 测试:
  - Unit: 解析带两个 subagents 的 `SKILL.md`, compiled phase 中保留规范化后的 name/path/description。
  - Unit: 无 `subagents:` 的现有 fixture 编译结果不变。
  - Unit: name/path/description 缺字段或类型错误时报 fatal compile error。
- 依赖: 无
- 验收:
  - FR-1 覆盖; `mode: skill` 可声明 subagents。

### T1.2 — sub-skill 存在性与 `io.inputs` 编译期校验 (~4h)
- Owner: a1
- Location: `packages/graph-agent/src/graph_agent/core/loader.py`, `packages/graph-agent/tests/core/`
- 工作:
  - 对每个 `subagents[].path` 检查目标目录存在且包含 `SKILL.md`。
  - 加载 sub-skill frontmatter, 确认其声明完整 `io.inputs` schema。
  - `io.inputs` 缺失、为空、无法解析时 loader 直接 fatal, 不允许运行期才失败。
  - fatal error 文案指向 parent phase、subagent name、sub-skill path。
- 测试:
  - Unit: sub-skill 目录不存在时报 fatal。
  - Unit: sub-skill 缺 `SKILL.md` 时报 fatal。
  - Unit: sub-skill 缺 `io.inputs` 或 schema 非法时报 fatal。
  - Unit: 合法 sub-skill 通过并暴露 input schema metadata。
- 依赖: T1.1
- 验收:
  - FR-1 与 design §7 "Pydantic schema 推导失败" 风险已在编译期阻断。

### T1.3 — 从 sub-skill `io.inputs` 生成 Pydantic input model (~6h)
- Owner: a1
- Location: `packages/graph-agent/src/graph_agent/core/loader.py` 或新建 engine-local schema helper, `packages/graph-agent/tests/core/`
- 工作:
  - 根据 sub-skill `io.inputs` 自动派生 Pydantic class, 用于 `call_subagent_<name>` 的单项 input 校验。
  - 支持 V2.1 现有 input schema 的基础类型、必填字段、可选字段、默认值与描述。
  - 生成模型名保持稳定, 便于错误信息与 trace 中定位。
  - 产出 expected schema 的 JSON/dict 表示, 供 informed retry message 使用。
  - 不要求支持 R/D 未声明的复杂 schema 语法。
- 测试:
  - Unit: string/int/bool/list/dict 等现有 schema 类型生成正确 Pydantic 字段。
  - Unit: 缺必填字段、字段类型错误、未知字段时返回可读 validation errors。
  - Unit: expected schema 包含字段名、类型、required 状态与 description。
- 依赖: T1.2
- 验收:
  - FR-4 的 schema validation 基础就绪。

### T1.4 — 动态构造 builtin tool `call_subagent_<name>` 并注入 phase tools (~6h)
- Owner: a1
- Location: `packages/graph-agent/src/graph_agent/core/loader.py`, 现有 tools registry/phase compile 相关模块, `packages/graph-agent/tests/core/`
- 工作:
  - 为每个 subagent 生成一个 builtin tool descriptor: `call_subagent_<name>`。
  - tool 参数为 `inputs: list[<SubagentInputModel>]`, 返回为 `list[SubagentResult]`。
  - tool description 注入 subagent description 与 "建议一次 <= 3 个 inputs" hint。
  - 在 loader 编译期将动态 tool 注入当前 phase 的 tools 列表, 与普通 tools 共存。
  - 避免与用户显式声明的同名 tool 冲突; 冲突时 fatal。
- 测试:
  - Unit: 一个 phase 声明两个 subagents 后 tools 列表出现两个 `call_subagent_*`。
  - Unit: 动态 tool 保留 expected schema 与 sub-skill path metadata。
  - Unit: 与现有 tool 同名时报 fatal。
- 依赖: T1.3
- 验收:
  - FR-2 覆盖; agent loop 能看到可调用的 subagent tools。

## Phase 2: Executor (a1, ~1 day, depends Phase 1)

### T2.1 — 实现 `call_subagent` runtime entry 与输入数组校验 (~4h)
- Owner: a1
- Location: `packages/graph-agent/src/graph_agent/core/` executor/tool runtime 相关模块, `packages/graph-agent/tests/core/`
- 工作:
  - 将 T1.4 生成的 tool descriptor 绑定到统一 engine dispatcher。
  - runtime 接收 LLM tool call JSON, 强制要求 `inputs` 为数组。
  - 对数组每一项使用 T1.3 的 Pydantic model 校验。
  - 输入不合法时返回明确 Validation Error + expected schema, 交给 agent loop informed retry。
  - retry 上限按 FR-4 设为 max=10, 超限后 task fail 并保留完整错误上下文。
- 测试:
  - Unit: 单个 dict 误传为 `inputs` 时返回 schema 指导错误。
  - Unit: list item 缺字段/错字段时返回 expected schema。
  - Unit: 连续 10 次错误后失败, 错误包含 retry count 与 tool name。
- 依赖: T1.4
- 验收:
  - FR-3 的数组入口与 FR-4 的 informed retry 行为可在 runtime 触发。

### T2.2 — Max Depth=1 runtime 防线与 depth tracking (~4h)
- Owner: a1
- Location: `packages/graph-agent/src/graph_agent/core/run_context.py`, executor/tool runtime 相关模块, `packages/graph-agent/tests/core/`
- 工作:
  - 在 RunContext 或等价 runtime state 中记录 `subagent_depth`。
  - parent phase 调用 subagent 时 depth 从 0 进入 1。
  - subagent 内部再次调用任何 `call_subagent_*` 时立即 raise FatalError。
  - FatalError 文案固定表达 "Max Depth 1 exceeded: subagent cannot call another subagent"。
  - 确保异常路径会恢复/隔离 depth, 不污染后续 run。
- 测试:
  - Unit: depth=0 时允许调用。
  - Unit: depth>=1 时调用 subagent tool 抛 FatalError。
  - Unit: 失败后新 run 的 depth 回到 0。
- 依赖: T2.1
- 验收:
  - FR-5 与 design §7 Max Depth 风险覆盖。

### T2.3 — 复用 `_subgraph_node` 语义执行隔离 sub-skill (~6h)
- Owner: a1
- Location: `packages/graph-agent/src/graph_agent/core/graph_assembler.py`, executor/tool runtime 相关模块, `packages/graph-agent/tests/core/`
- 工作:
  - 复用现有 `SkillLoader().compile_skill(sub_root)` 与 `assemble_graph(...)` 路径编译 sub-skill。
  - 调用 sub-skill graph 时传入 parent `data`/`flow`/`run_id`, 并保持 `messages: []`。
  - 子技能只返回自身 data delta, 不污染 parent agent messages。
  - trace id/run id 从 parent 透明传入 subgraph 执行。
  - 避免复制 DeerFlow ThreadPool executor。
- 测试:
  - Unit: subagent invoke 时传入 `messages: []`。
  - Unit: parent `run_id`/trace id 传递到 subgraph。
  - Unit: sub-skill 返回 data delta 后 parent messages 未被子图写入。
- 依赖: T2.2
- 验收:
  - NFR-2 与 NFR-3 覆盖。

### T2.4 — LangGraph Send fan-out 与 semaphore=3 并发限流 (~6h)
- Owner: a1
- Location: `packages/graph-agent/src/graph_agent/core/graph_assembler.py`, executor/tool runtime 相关模块, `packages/graph-agent/tests/core/`
- 工作:
  - 使用 LangGraph `Send` 或与现有 graph assembler 兼容的动态 fan-out 模式启动 N 个 sub-skill 分支。
  - 外层设置默认并发窗口 `semaphore=3`。
  - inputs 长度大于 3 时仅节流并发, 不做跨轮 batch 自动切割。
  - 顺序聚合结果时保持与 inputs 顺序一致。
  - 为未来 config override 保留内部参数入口, 默认仍硬设为 3。
- 测试:
  - Unit: 5 个 inputs 时最大并发不超过 3。
  - Unit: 结果顺序与输入顺序一致。
  - Unit: inputs 长度大于 3 不被拆成多次 agent loop 调用。
- 依赖: T2.3
- 验收:
  - FR-3 与 NFR-1 覆盖。

### T2.5 — Subagent result aggregator 与 traceable failure logging (~4h)
- Owner: a1
- Location: executor/tool runtime 相关模块, `packages/graph-agent/tests/core/`
- 工作:
  - 定义统一 `SubagentResult` 返回结构, 至少包含 input index、status、data delta、error 信息。
  - 聚合 N 个 sub-skill 执行结果为 list 返回 parent agent。
  - 单项失败时保留对应 input index 与 subagent name, 便于 LLM/PM 诊断。
  - informed retry max=10 仍失败时, log 关联 parent trace id 与 child run id。
  - 不引入 subagent memory 持久化或 A/B test 框架。
- 测试:
  - Unit: 多项成功返回 list, 每项含 data delta。
  - Unit: 单项失败时结果包含 index、status、error、trace id。
  - Unit: retry 超限日志包含 tool name、parent trace id、expected schema 摘要。
- 依赖: T2.4
- 验收:
  - FR-4、NFR-3 与 design §7 "informed retry max=10 仍 stuck" 风险覆盖。

### T2.6 — Minimal subagent fixture 端到端集成测试 (~6h)
- Owner: a1
- Location: `packages/graph-agent/tests/integration/` 或 `packages/graph-agent/tests/e2e/`, minimal fixture under tests only
- 工作:
  - 构造一个最小 parent skill, 声明一个最小 sub-skill 作为 subagent。
  - 覆盖 parent tool 注入、schema validation、fan-out、aggregation、trace id 透传。
  - 增加 Max Depth fixture: sub-skill 内声明二级 subagent 并验证 runtime FatalError。
  - fixture 仅用于 tests, 不修改真实 `skills/` 标杆目录。
- 测试:
  - Integration: parent agent 可看到并调用 `call_subagent_<name>`。
  - Integration: 3+ inputs fan-out 执行并返回按序 list。
  - Integration: schema 错误触发 informed retry message。
  - Integration: 二级 subagent 调用被 Max Depth=1 阻断。
- 依赖: T2.5
- 验收:
  - Phase 1 + Phase 2 的 engine path 有最小闭环。
  - 覆盖 FR-1 到 FR-5、NFR-1 到 NFR-3 的核心行为。

## Phase 3: Frontend Badge & Properties (apps master, ~0.5 day, parallel with Phase 1+2)

### T3.1 — Canvas phase node 显示 Toolbox badge (~4h)
- Owner: apps master
- Location: `apps/studio/frontend/src/` canvas node renderer 相关文件
- 工作:
  - 对声明了 `phase_config.subagents` 的 `mode: skill` phase 节点显示 `Toolbox` 小 badge。
  - badge 放在节点顶部 metadata 区域, 不改变节点主视觉层级。
  - 不改变双击行为; 双击仍打开当前 phase 的 `SKILL.md`。
  - 无 subagents 的普通 skill phase 不显示 badge。
- 测试:
  - Frontend unit/component: 带 subagents 的 phase 渲染 badge。
  - Frontend unit/component: 无 subagents 的 phase 不渲染 badge。
  - Frontend interaction: 双击节点仍走现有 SKILL.md nav。
- 依赖: 可与 T1/T2 并行; 需要前端可读到 phase subagents metadata
- 验收:
  - FR-6 Canvas badge 覆盖。
  - AssetsPanel 展示逻辑不变。

### T3.2 — Properties Tab 增加 Subagents 只读列表与 click nav (~4h)
- Owner: apps master
- Location: `apps/studio/frontend/src/` sidebar/properties tab/routing 相关文件
- 工作:
  - 选中带 subagents 的 phase 节点时, 在 Properties 的 Tools 列表下方显示 `Subagents` 栏。
  - 每项显示 `name | description`。
  - 点击条目触发现有 `canvas:open-phase-file` 或等价 R3 sidebar tab routing, 打开子 skill 的 `SKILL.md`。
  - 列表只读, 不在 UI 中编辑 subagents。
- 测试:
  - Frontend unit/component: Subagents 列表按 metadata 渲染。
  - Frontend interaction: 点击 subagent 打开目标 `SKILL.md`。
  - Frontend regression: AssetsPanel 不展示动态 subagent 关系。
- 依赖: T3.1 可并行; 需要 phase metadata 中包含 resolved subagent path
- 验收:
  - FR-6 Properties Tab 覆盖。
  - Studio 视觉化只表达关系, 不承担 dispatcher 配置逻辑。

## Phase 4: Validation (user, TBD, after Phase 1-3)

### T4.1 — 选择一个现存 V1 skill 作为 V2.1 subagent 标杆候选 (~4h)
- Owner: user
- Location: user 选择的 skill 工作区, 建议 `adaptation_v1_sandbox` 或同等复杂度 fixture
- 工作:
  - 从现存 V1 skill 中选择一个适合拆成 parent + sub-skill 的标杆。
  - 明确 parent phase 负责 agent loop 决策, sub-skill 负责单一专家任务。
  - 不要求旧 V1 skill 直接跑通; 目标是暴露 layout/rule 问题。
- 测试:
  - Manual: user 确认候选 skill 的输入/输出边界清晰。
  - Manual: user 标注哪些 V1 layout 需要改成 V2.1 layout。
- 依赖: Phase 1/2 engine 行为可用后开始
- 验收:
  - 有一个明确的 V2.1 subagent 标杆候选。
  - 该候选能覆盖 fan-out、schema validation、Max Depth 至少三条主路径。

### T4.2 — user 自调 V1→V2.1 layout 并实测 subagent 闭环 (~6h+)
- Owner: user
- Location: user 选择的标杆 skill 工作区 / Studio
- 工作:
  - 将候选 V1 skill 调整为 V2.1 parent skill + sub-skill layout。
  - 在 parent `phase_config.subagents` 中声明 sub-skill。
  - 实测 parent agent 调用 `call_subagent_<name>` fan-out。
  - 故意构造错误输入, 验证 schema validation + informed retry。
  - 构造二级 subagent 尝试, 验证 Max Depth 阻断。
  - 在 Studio 查看 Toolbox badge、Properties Subagents 列表与点击 nav。
- 测试:
  - Manual/E2E: 真实 skill fan-out 成功返回聚合结果。
  - Manual/E2E: 错误 schema 触发 expected schema retry 信息。
  - Manual/E2E: 二级 subagent 被 FatalError 阻断。
  - Manual/E2E: Studio 可视化行为符合 FR-6。
- 依赖: T2.6, T3.1, T3.2
- 验收:
  - user 得到一个 "对的 skill 和 engine" 的 subagent 标杆。
  - 发现的问题进入后续 spec/bugfix, 不在本 Phase 2B tasks.md 中扩 scope。
