# skill-compilation V0.3.0 代码逻辑翻译

本文只解释 V0.3.0 完成态下 skill-compilation 子模块做什么、为什么这么做、字段如何被校验。它不是 baseline 的现状流水账, 也不是 mvp0-alignment 的改造清单。读者可以把它当作 `packages/graph-agent/src/graph_agent/core/` 中 loader / compiler / manifest / mention / graph assembly 代码的自然语言索引。

核心入口和锚点:

- `compile_skill()` 是公开入口, 接受 `root`, `cache`, `skill_resolver`, 并把模型参数留给装配/运行阶段处理: `packages/graph-agent/src/graph_agent/core/compiler.py:41`.
- `SkillLoader.compile_skill()` 是编译主流程, 从目录守卫、`GRAPH.md` 解析、phase AST 构建、action/tool/subagent 发现一直到 `CompiledSkill` 返回: `packages/graph-agent/src/graph_agent/core/loader.py:146`.
- AST 真相源在 `manifest.py`, 包括 `GraphManifest`, `GraphPhaseRef`, `PhaseIOSchema`, `LogicNodeAST`, `SubgraphNodeAST`, `AgentNodeAST`, resource 和 registry 模型: `packages/graph-agent/src/graph_agent/core/manifest.py:18`.
- `@type:NAME` 扫描由 `mentions.py` 提供统一 regex, loader 再按 Agent AST registry 做可达性校验: `packages/graph-agent/src/graph_agent/core/mentions.py:8`, `packages/graph-agent/src/graph_agent/core/loader.py:1210`.
- 编译产物交给 `assemble_graph()` 后才变成 LangGraph, phase IO 通过 `StateMapper` 包装 runtime node: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:68`, `packages/graph-agent/src/graph_agent/core/graph_assembler.py:158`.

## 一条主线: 目录变成 CompiledSkill

`compile_skill(root, cache=True, skill_resolver=None)` 先把 `root` 规整为 `Path`, 在没有 resolver 时才允许读写 cache, 因为 resolver 参与跨 skill 寻址, cache snapshot 不能把外部 registry 状态当成稳定常量: `packages/graph-agent/src/graph_agent/core/compiler.py:55`. cache miss 后进入 `SkillLoader().compile_skill(...)`, 最终返回 `CompiledSkill`: `packages/graph-agent/src/graph_agent/core/compiler.py:62`.

编译阶段不调用 LLM, 不执行业务图, 不读取 Studio registry 本身。它只把磁盘目录翻译成结构化 AST 和 registry, 并尽量把目录、schema、DAG、mention、resolver 这些静态错误提前暴露。

难点 1: **分界线**。编译器负责证明“这份图的结构和声明可装配”, runtime 负责证明“这次输入和真实执行结果满足声明”。如果把这条线混掉, Studio 会把运行时偶然失败误判成 skill 定义错误, 或把定义错误拖到运行中才暴露。

### 编译入口字段

| 字段 / 参数 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 失败错误码 |
|---|---|---|---|---|
| `root` | skill 根目录入口, 后续查 `GRAPH.md`, `phases/`, actions/tools/resources 都从这里开始 | 如果不是目录或缺根图, 后续所有相对路径都会失去基准 | 必须存在、是目录、含根级 `GRAPH.md`; 根级旧 `SKILL.md` 不再作为入口 | `[F-v3-route]` / spec 完成态归一为 `[F-v3-graph-root-missing]` |
| `chat_model` | 保持公开签名兼容; 编译阶段删除它, 模型交给 graph assembly/runtime | 编译期依赖模型会让静态检查不可复现, 也会污染 cache key | `compiler.py` 直接 `del chat_model`, 不参与 loader | 无; runtime 缺模型时由 graph assembly 抛 `[F-v3-graph]` |
| `cache` | 控制是否读写编译 snapshot | cache 只能加速, 不能改变冷编译语义 | `cache=True` 且 `skill_resolver is None` 时才读写; resolver 存在时跳过 cache | cache 读失败返回 miss; 写失败完成态应 WARN, 不应 FATAL |
| `skill_resolver` | V0.3.0 跨 skill DI, 用于 `target_skill` 找到子 graph skill 根目录 | Engine 不应该猜 Studio registry 或本地用户目录 | 必须实现单方法 `resolve_skill(skill_id)`; resolver 返回目录且有 `GRAPH.md` | `[F-v3-resolver-missing]` / `[F-v3-resolver-interface-invalid]` / `[F-v3-skill-not-registered]` / `[F-v3-resolver-path-invalid]` |

## 物理入口和 phase 目录

Loader 的第一层守卫是 `_guard_v21_root()`: 路径必须存在、必须是目录、根级 `GRAPH.md` 必须存在、`phases/` 必须存在且有 phase 子目录; 当前代码还禁止根级 `actions/`: `packages/graph-agent/src/graph_agent/core/loader.py:275`. phase 扫描由 `_discover_phase_files()` 完成, 每个 `phases/<id>/` 下只能出现 `LOGIC.md`, `SUBGRAPH.md`, `SKILL.md` 三者之一: `packages/graph-agent/src/graph_agent/core/loader.py:296`.

V0.3.0 的设计目标是让 phase 类型由物理文件和 frontmatter `mode` 双向锁定。这样 Studio 和 Engine 不需要猜一个目录到底是确定性代码、固定子图还是 LLM Agent。`_validate_mode_matches_filename()` 对 `LOGIC.md` / `SUBGRAPH.md` 做严格匹配, 对 `SKILL.md` 兼容 `agent` 和 legacy `skill`: `packages/graph-agent/src/graph_agent/core/loader.py:632`.

### 物理字段

| 字段 / 路径 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 失败错误码 |
|---|---|---|---|---|
| `<skill_root>/GRAPH.md` | 根图 manifest, graph metadata, 根 IO, phase DAG 的入口 | 没有根图就无法知道编译对象和执行顺序 | 文件必须存在且只能在根目录 | `[F-v3-graph-root-missing]` / 当前 helper 前缀 `[F-v3-route]` |
| `<skill_root>/phases/` | 所有执行 phase 的物理容器 | 没有 phase 则 graph 不可装配 | 必须是目录且至少有一个 phase 子目录 | `[F-v3-graph-phases-dir-missing]` / 当前 helper 前缀 `[F-v3-route]` |
| `phases/<id>/` | 单个 DAG 节点的目录, `<id>` 与 `phases[].id` 对齐 | DAG 声明和磁盘文件脱节会让 Canvas 与 runtime 对不上 | 每个 graph phase id 必须有对应目录; 目录名用于 `PhaseDocument.phase_name` | `[F-v3-graph-phase-dir-missing]` |
| `LOGIC.md` | 确定性 Python phase 声明 | 错装成 Agent/Subgraph 会改变执行语义 | 同目录三选一; frontmatter `mode` 必须是 `logic` | `[F-v3-graph-mode-path-mismatch]` / `[F-v3-logic-mode-invalid]` |
| `SUBGRAPH.md` | 固定子图调用 phase 声明 | 子图是主流程固定节点, 不能被误作 Agent 可选工具 | 同目录三选一; frontmatter `mode` 必须是 `subgraph` | `[F-v3-graph-mode-path-mismatch]` / `[F-v3-subgraph-mode-invalid]` |
| `SKILL.md` | Agent phase 声明, V0.3.0 `mode: agent` | Agent 进入 ReAct 和 cognitive template, 执行方式不同 | 同目录三选一; 完成态 `mode` 必须是 `agent`; 当前代码兼容 legacy `skill` | `[F-v3-graph-mode-path-mismatch]` / `[F-v3-agent-mode-invalid]` |
| phase 多节点文件 | 防止一个 phase 同时声明多种运行模式 | 多模式会让 AST discriminator 和 runtime node 类型冲突 | 同一目录出现两个或三个节点文件即 FATAL | `[F-v3-graph-phase-mode-ambiguous]` |
| phase 无节点文件 | 防止 DAG 节点没有可执行说明 | 有目录但无 node 文件无法构建 `PhaseDocument` | 三个节点文件都不存在即 FATAL | `[F-v3-graph-phase-node-missing]` |
| phase 内 `GRAPH.md` | 禁止在 phase 目录嵌套根图 | 嵌套根图会混淆当前 graph 与子 graph 的边界 | `phases/<id>/GRAPH.md` 一律 FATAL | `[F-v3-route]` / 完成态归入 `[F-v3-graph-mode-path-mismatch]` |

## GRAPH.md: 根图声明

`_build_graph_manifest()` 把 `GRAPH.md` frontmatter 变成 `GraphManifest`; 当前代码兼容旧 body `<input/>`, `<output/>`, `<phase/>`, 也能从 frontmatter `phases` 构造 raw attrs 用于拓扑校验: `packages/graph-agent/src/graph_agent/core/loader.py:644`. V0.3.0 完成态以 frontmatter `phases:` 和 inline `io:` 为准, 旧 `io_inputs_ref` / `io_outputs_ref` 和物理 `io/*.json` 退役。

`GraphManifest` 字段在 Pydantic 模型中定义: `schema_version`, `name`, `description`, `io_inputs_ref`, `io_outputs_ref`, `io`, `phases`, `metadata`: `packages/graph-agent/src/graph_agent/core/manifest.py:114`.

### GraphManifest 字段

| 字段 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 失败错误码 |
|---|---|---|---|---|
| `schema_version` | 声明 skill spec 版本 | 防止 V2.1/V0.3.0 字段语义混跑 | 完成态必须是 `"0.3.0"`; 当前模型兼容 `"2.1"` | `[F-v3-graph-schema-version-mismatch]` |
| `name` | graph skill 稳定标识, 也与 resolver skill id 对齐 | 名称进入 registry、trace、Studio 展示 | 完成态正则 `^[a-z][a-z0-9_-]*$`; 当前模型至少要求 1..128 字符 | `[F-v3-graph-name-invalid]` |
| `description` | 人类可读说明 | 不参与执行, 但 Studio/registry 需要展示 | 可选字符串, 默认 `""` | 无 |
| `llm_role` | graph 默认 LLM 路由角色, Agent 可覆盖 | 未注册角色会让装配后模型选择不可预测 | spec 要求角色存在于 `llm_roles.yaml`; 当前 `GraphManifest` 尚未持有该字段 | `[F-v3-graph-llm-role-unknown]` |
| `io` | inline `PhaseIOSchema`, 包含 graph inputs/outputs | 根 IO 是运行入口和最终输出的真相源 | 必填完成态; 当前代码如果存在则走 `_validate_inline_io_schema()` | `[F-v3-graph-io-not-object]` / `[F-v3-graph-io-schema-invalid]` |
| `io_inputs_ref` | legacy 输入 schema 文件引用 | V0.3.0 禁止跨文件 IO 漂移 | 完成态禁止出现; 当前默认 `io/inputs.json` 作为兼容 fallback | `[F-v3-graph-io-physical-file-deprecated]` |
| `io_outputs_ref` | legacy 输出 schema 文件引用 | 同上, 防止根输出与 GRAPH.md 漂移 | 完成态禁止出现; 当前默认 `io/outputs.json` 作为兼容 fallback | `[F-v3-graph-io-physical-file-deprecated]` |
| `phases` | DAG 节点列表 | 没有 DAG 就无法确定执行拓扑和数据流 | 完成态从 frontmatter YAML list 读取; 每项是 `GraphPhaseRef` | `[F-v3-graph-phase-id-invalid]` 等 graph domain 错误 |
| `metadata` | 扩展元数据 | 给非执行信息留扩展位, 避免污染核心字段 | 可选 dict, 默认 `{}`; 未知执行字段不能塞这里冒充 | `[F-v3-graph-schema-unknown-field]` |

### GraphPhaseRef 字段

| 字段 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 失败错误码 |
|---|---|---|---|---|
| `id` | phase 稳定 id, 用作 LangGraph node id、trace id、目录名 | 重复或非法会让边和错误定位失效 | 必填; 完成态正则 `^[a-z][a-z0-9_-]*$`; 列表内唯一 | `[F-v3-graph-phase-id-invalid]` / `[F-v3-graph-phase-id-duplicate]` |
| `depends_on` | DAG 上游依赖 | 决定执行顺序和数据流可见字段集合 | 必填 list; 每项必须引用已声明 phase, 不能自环 | `[F-v3-graph-depends-unknown]` / `[F-v3-graph-phase-cycle]` |
| `src` | legacy phase 物理路径 | V0.3.0 以 `phases/<id>/` 约束物理布局; legacy 仍需防逃逸 | 当前模型必填, 路径必须留在 skill root 且目标含节点文件 | `[F-v3-graph-phase-dir-missing]` / 当前 helper 前缀 `[F-v3-graph]` |

### PhaseIOSchema 字段

| 字段 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 失败错误码 |
|---|---|---|---|---|
| `inputs` | 声明 graph 或 phase 可读字段 | StateMapper、数据流校验、subgraph 参数对齐都依赖它 | dict, 非空; 完成态要求 JSON Schema 顶层 `type: object`, `required` 只能引用 `properties` | graph/logic/agent/subgraph 各自 `*-io-schema-invalid` |
| `outputs` | 声明 graph 或 phase 可写字段 | 防止 action/Agent/subgraph 写出未声明黑板字段 | dict, 非空; 完成态要求 JSON Schema object, `properties` 存在 | graph/logic/agent/subgraph 各自 `*-io-schema-invalid` |

## DAG 拓扑和数据流

拓扑校验在 `_validate_graph_topology()` 中完成: 缺 `id/src`, 重复 id, 缺 `depends_on`, 未知依赖, 自依赖, 环, 孤岛, phase src 路径都在这里拦截: `packages/graph-agent/src/graph_agent/core/loader.py:784`. 环检测是 DFS 灰黑标记: `packages/graph-agent/src/graph_agent/core/loader.py:828`; 孤岛检测把依赖边当无向图, 从第一个 phase 走可达性: `packages/graph-agent/src/graph_agent/core/loader.py:861`.

数据流校验解决另一个问题: 拓扑通不代表字段通。V0.3.0 完成态按拓扑序遍历, 用根 `io.inputs.properties` 加上所有上游 `phase.io.outputs.properties` 形成可见字段集合, 再检查当前 phase `io.inputs.required` 是否都在集合内。缺口报 `[F-v3-graph-dataflow-source-missing]`, payload 至少应包含 `phase_id`, `field_name`, `source_phase_candidates`, `path`, `line`, 以便 Studio 标红节点和字段。

难点 2: **管道试水**。DAG 拓扑只证明节点之间有边, 数据流校验证明字段真的能沿边到达。边存在但字段名错, 应该在编译期报错, 不该等 runtime 半路缺 key。

### DAG / dataflow 校验输入字段

| 字段 / 集合 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 失败错误码 |
|---|---|---|---|---|
| phase id 集合 | 建立 DAG 节点全集 | 重复或缺失会让边无法解析 | `phases[].id` 唯一且对应物理目录 | `[F-v3-graph-phase-id-duplicate]` / `[F-v3-graph-phase-dir-missing]` |
| `depends_on` 边集合 | 描述上游执行关系 | 未知边、自环、环会让调度无定义 | 每条边指向已声明 phase; DFS 无环; 不允许自依赖 | `[F-v3-graph-depends-unknown]` / `[F-v3-graph-phase-cycle]` |
| 入口 phase | 没有上游的 DAG 起点 | 所有非入口必须能从入口连通 | 完成态 `depends_on: []`; 当前 legacy 要显式 `depends_on=""` | `[F-v3-graph-phase-island]` |
| root input keys | graph 初始可见字段 | phase required input 的第一来源 | 来自 `GRAPH.md io.inputs.properties` | `[F-v3-graph-io-schema-invalid]` |
| phase required inputs | 当前 phase 启动前必须可见的字段 | 缺字段会导致 StateMapper/runtime 执行失败 | 来自 `phase.io.inputs.required`; 每项必须在 root inputs 或上游 outputs 中 | `[F-v3-graph-dataflow-source-missing]` |
| upstream output keys | 证明上游已经产出某字段 | 只看直接/间接上游, 不能偷看下游或无关孤岛 | 按拓扑序累计每个已通过 phase 的 `io.outputs.properties` | `[F-v3-graph-dataflow-source-missing]` |
| dataflow issue payload | 给 Studio 精准定位 | 纯字符串无法标红具体字段 | 必含 phase、字段、候选来源、文件、行号 | `[F-v3-graph-dataflow-source-missing]` |

## LOGIC.md: 确定性代码 phase

`LogicNodeAST` 当前模型包含 `mode` 和 `python_callable`, 并继承 `_BaseNodeAST` 的 `name`, `raw_blocks`, `metadata`: `packages/graph-agent/src/graph_agent/core/manifest.py:139`. loader 从 body block 补 `python_callable`: `packages/graph-agent/src/graph_agent/core/loader.py:1108`. V0.3.0 spec 进一步要求 `io`, `actions`, `validator`, 且 action 一级寻址到 `<skill_root>/actions/<name>.py`;当前实现仍有 phase-local `actions/` 扫描和单 callable 兼容逻辑, 文档按完成态解释其边界。

### LOGIC 字段

| 字段 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 失败错误码 |
|---|---|---|---|---|
| `name` | Logic phase 展示名和 trace 名 | 名称错会让 Studio 节点和错误定位不稳定 | 必填完成态; 建议等于 phase id; 当前 `_BaseNodeAST` 可为 `None`, loader 默认 phase dir name | `[F-v3-logic-name-invalid]` |
| `mode` | AST discriminator, 固定为 `logic` | 防止 `LOGIC.md` 被当成 Agent/Subgraph | 必须精确为 `"logic"` 且文件名是 `LOGIC.md` | `[F-v3-logic-mode-invalid]` / `[F-v3-graph-mode-path-mismatch]` |
| `io.inputs` | action 链可读取的 state slice | 没有输入边界, action 会退化成全黑板读取 | JSON Schema object; `required` 只引用 `properties` | `[F-v3-logic-io-schema-invalid]` |
| `io.outputs` | action 链允许写回的字段 | 防止确定性代码污染未声明 state | JSON Schema object; 返回 dict key 必须是 `properties` 子集 | `[F-v3-logic-io-schema-invalid]` / `[F-v3-logic-output-field-undeclared]` |
| `actions` | 完成态 action 名列表和执行顺序 | 多 action 串行时顺序是业务语义, 不能从目录猜 | 非空 list; 每项 `^[a-z][a-z0-9_]*$`; 一级寻址, 不含路径分隔符 | `[F-v3-logic-actions-empty]` / `[F-v3-logic-action-name-invalid]` |
| `python_callable` | 当前兼容字段, 指向一个 body block callable | legacy 编译需要知道调用哪个函数 | 当前 `LogicNodeAST` 要求非空字符串; runtime 用它从 registry resolve | `[F-v3-route]` / 完成态迁移为 action 错误 |
| `validator` | 完成态后置校验开关 | 防止候选输出在业务不变量失败时写回黑板 | 可选 boolean, 默认 `false`; `true` 时同级 `validator.py` 必须存在并导出 `validate()` | `[F-v3-logic-validator-type-invalid]` / `[F-v3-logic-validator-missing]` / `[F-v3-logic-validator-entrypoint-missing]` |
| `raw_blocks` | 保留 body 中抽取的原始 block | 便于调试和 legacy 字段补全 | dict, 由 `extract_raw_blocks()` 从允许标签抽取 | AST 校验失败归入 `[F-v3-route]` |
| `metadata` | 非执行扩展信息 | 不应该把执行契约塞进 metadata 绕过 schema | 可选 dict, 默认 `{}` | `[F-v3-logic-schema-unknown-field]` |

Action 加载还会做 Python 层校验: 模块必须可 import, action 第一参数必须是 `context` 或 `ctx` 且类型兼容 `Context`: `packages/graph-agent/src/graph_agent/core/loader.py:591`. 静态返回键扫描读取 Python AST, 对 `return {"key": ...}` 和单 Logic 图中的 `ctx.update(key=...)` 做 key 限制: `packages/graph-agent/src/graph_agent/core/loader.py:976`.

### Action / validator 物理字段

| 字段 / 文件 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 失败错误码 |
|---|---|---|---|---|
| `<skill_root>/actions/` | 完成态 skill 全局 action 目录 | 统一资产面板和一级寻址, phase 移动不破坏代码路径 | `actions` 非空时必须存在; 当前代码仍禁止 root-level actions 并扫描 phase-local actions | `[F-v3-logic-action-dir-missing]` / 当前 `[F-v3-actions]` |
| `<action_name>.py` | 具体 action 实现文件 | 找不到文件说明声明不可执行 | 文件必须一级存在, 不允许路径、多级目录或模块表达式 | `[F-v3-logic-action-not-found]` |
| `run` | 完成态标准 action 入口 | 统一 runtime 调用协议 | 必须导出 `def run(state_slice, **kwargs) -> dict` | `[F-v3-logic-action-entrypoint-missing]` |
| action 返回 dict | 写回 phase 输出 | 非 dict 无法 merge 到 state | runtime 返回必须是 dict | `[F-v3-logic-action-return-invalid]` |
| action 返回 key | 限制写回边界 | 未声明字段会污染全局黑板 | key 必须属于 `io.outputs.properties` | `[F-v3-logic-output-field-undeclared]` / 当前 `[F-v3-actions-keys]` |
| `validator.py` | 后置业务校验 | 防止半成品输出写回 | `validator: true` 时存在并导出 `validate(output, state_slice, **kwargs)` | `[F-v3-logic-validator-missing]` / `[F-v3-logic-validator-entrypoint-missing]` |

## SUBGRAPH.md: 固定子图 phase

`SubgraphNodeAST` 当前字段是 `mode`, `sub_skill_ref`, `target_skill`, `io`, 继承 `name/raw_blocks/metadata`: `packages/graph-agent/src/graph_agent/core/manifest.py:146`. 完成态以 `target_skill` 为主, 通过 `SkillResolverProtocol.resolve_skill()` 找子 skill, 不再把路径写进业务 manifest。`SkillResolverProtocol` 和校验 helper 在 `skill_resolver_protocol.py`: `packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py:31`.

### SUBGRAPH 字段

| 字段 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 失败错误码 |
|---|---|---|---|---|
| `name` | 子图 phase 展示和 trace 名 | 便于 Studio 区分主图节点和子图调用 | 必填完成态, 正则 `^[a-z][a-z0-9_-]*$`; 当前 loader 默认 phase dir name | `[F-v3-subgraph-name-invalid]` |
| `mode` | AST discriminator, 固定为 `subgraph` | 防止固定子流程被错装成 Agent 或 Logic | 必须精确为 `"subgraph"` 且文件名是 `SUBGRAPH.md` | `[F-v3-subgraph-mode-invalid]` / `[F-v3-graph-mode-path-mismatch]` |
| `target_skill` | registry skill id | 子图寻址应由 Studio registry/DI 控制, 不应暴露磁盘路径 | 必填完成态; 匹配 skill id 正则; resolver 必须能解析到含 `GRAPH.md` 的目录 | `[F-v3-subgraph-target-skill-invalid]` / `[F-v3-skill-not-registered]` |
| `sub_skill_ref` | legacy 相对路径引用 | 当前 runtime 仍用它 resolve 子图路径 | 当前 `SubgraphNodeAST` 要求非空; 完成态应退役 | `[F-v3-subgraph-target-skill-invalid]` / 当前 `[F-v3-route]` |
| `io.inputs` | 父图传给子图的实参 schema | 子图像函数调用, 父实参与子形参必须闭合 | JSON Schema object; 与 child `GRAPH.md io.inputs.properties` 1:1 对齐 | `[F-v3-subgraph-io-schema-invalid]` / `[F-v3-subgraph-io-mismatch]` |
| `io.outputs` | 子图返回父图的字段 schema | 防止子图内部临时字段泄漏回父图 | JSON Schema object; 与 child `GRAPH.md io.outputs.properties` 1:1 对齐 | `[F-v3-subgraph-io-schema-invalid]` / `[F-v3-subgraph-io-mismatch]` |
| `metadata` | 非执行扩展 | 避免把路径或 IO 映射塞进非 schema 字段 | 可选 dict | `[F-v3-subgraph-schema-unknown-field]` |

难点 3: **函数签名**。父 `SUBGRAPH.md io` 是调用方写出的实参形状, 子 `GRAPH.md io` 是被调用方声明的形参形状。V0.3.0 选择 1:1 严格映射, 是为了让字段错位在编译期就能定位, 而不是在子图内部运行到某个 phase 才失败。

### SkillResolverProtocol 字段

| 字段 / 项 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 失败错误码 |
|---|---|---|---|---|
| `skill_id` | resolver 查询 key, 来自 `target_skill` | 路径和 registry id 混用会破坏 Studio 导入/资产面板 | 当前正则 `^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$`; spec 完成态收敛到小写 id | `[F-v3-resolver-skill-id-invalid]` / 当前 `[F-v3-invalid-skill-id]` |
| `resolve_skill()` | 单方法 DI 接口 | Engine 只依赖协议, 不读取 Studio settings | resolver 必须有 `resolve_skill(skill_id) -> str | Path` | `[F-v3-resolver-interface-invalid]` |
| return Path | 子 skill 根目录 | 返回不可编译目录会让递归编译失败 | 必须是目录且含 `GRAPH.md` | `[F-v3-skill-not-registered]` / `[F-v3-resolver-path-invalid]` |

## Agent SKILL.md: frontmatter 变装配配置, body 变业务 AST

`AgentNodeAST` 是 V0.3.0 Agent phase 的核心模型: `mode`, `role`, `goal`, `steps`, `protocols`, `exit_contract`, `io`, `tools`, `subagents`, `subgraphs`, `references`, `examples`, `max_iterations`, `llm_role`, `system_prompt`: `packages/graph-agent/src/graph_agent/core/manifest.py:155`. Loader 对 `SKILL.md mode: agent` 会先规整 `phase_config`, 再解析 body XML, 再做 mention 可达性校验: `packages/graph-agent/src/graph_agent/core/loader.py:1114`.

V0.3.0 的关键决策是: Agent prompt 不再用一个大 `system_prompt` 承载全部业务内容。frontmatter 只描述装配配置和 registry; body 只写 5 类业务标签; graph assembly 用 `apply_v030_cognitive_template()` 填入固定模板: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:382`, `packages/graph-agent/src/graph_agent/cognitive/prompt.py:125`.

### Agent frontmatter / AST 字段

| 字段 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 失败错误码 |
|---|---|---|---|---|
| `name` | Agent 展示名、trace 名和诊断名 | 没有稳定名称, mention/trace/Studio 难定位 | 必填完成态; 正则 `^[a-z][a-z0-9_-]*$`; loader 默认 phase id | `[F-v3-agent-name-invalid]` |
| `mode` | AST discriminator, 固定为 `agent` | 区分 V0.3.0 Agent 与 legacy `skill` | 完成态必须是 `"agent"` 且文件名 `SKILL.md`; 当前兼容 `skill` | `[F-v3-agent-mode-invalid]` / `[F-v3-graph-mode-path-mismatch]` |
| `llm_role` | LLM routing 角色 | 角色不存在会导致装配时拿不到 policy/prefix | 可选; 继承 graph 后默认 `analyst`; 装配时解析 role prefix | `[F-v3-agent-llm-role-unknown]` |
| `io.inputs` | Agent 可读 state slice | Agent 不应看到整张黑板 | JSON Schema object; `required` 引用 `properties` | `[F-v3-agent-io-schema-invalid]` |
| `io.outputs` | Agent 允许通过 `finish_task` 产出的 schema | 输出 schema 要内嵌到 exit contract 末尾, 强化 recency | JSON Schema object; 终端/phase 输出需满足它 | `[F-v3-agent-io-schema-invalid]` / `[F-v3-cognitive-output-schema-render-failed]` |
| `tools` | 暴露给 ReAct 的工具名列表 | prompt 里提到不存在 tool 会诱导 LLM 乱调用 | list, 默认 `[]`; 每项必须是 builtin 或 registry tool, mention 域额外允许 `finish_task` | `[F-v3-agent-tool-unknown]` |
| `subagents` | Agent 可委托的子 Agent registry | 让 `@subagent:NAME` 和动态 `call_subagent_NAME` 有静态来源 | list, 默认 `[]`; 每项是 `SubagentSpec` 或完成态 registry item | `[F-v3-agent-subagent-invalid]` |
| `subgraphs` | Agent 可引用的子图资产 registry | 区分“Agent 可谈论/引用的子图”和 DAG 上固定 SUBGRAPH phase | list, 默认 `[]`; 每项含 `name/target_skill/description` | `[F-v3-agent-subgraph-invalid]` |
| `references` | 领域资料 registry | 支持预读、按需读取、正文显式引用三条路径 | list, 默认 `[]`; 每项含 `id/path/summary` | `[F-v3-resource-reference-invalid]` |
| `examples` | 案例 registry | inline 和 document 装配策略不同, 必须区分 | list, 默认 `[]`; 每项含 `id/type` 及模式字段 | `[F-v3-resource-example-invalid]` |
| `max_iterations` | ReAct 最大轮数 | 防止工具循环失控 | integer, 默认 `10`, 当前模型限制 `1..50` | `[F-v3-agent-max-iterations-invalid]` |
| `system_prompt` | legacy 兼容 prompt | 旧 runtime 仍需要字符串; V0.3.0 由结构化字段渲染 | 当前若为空, validator 从 role/goal/steps/protocols 渲染 legacy prompt | 无; 完成态不应作为作者主输入 |
| `raw_blocks` | body 原始 block 快照 | 调试 AST 和模板渲染差异 | dict, 来自 `extract_raw_blocks()` | AST 校验失败归入 `[F-v3-route]` |
| `metadata` | 非执行扩展 | 防止未知执行配置绕过 schema | dict, 默认 `{}` | `[F-v3-agent-schema-unknown-field]` |

### Agent body XML 字段

| 标签 / 字段 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 失败错误码 |
|---|---|---|---|---|
| `<role>` | Agent 专业身份, 进入 `{skill_role}` | 缺身份会退化成泛化 Agent | 恰好 1 个; trim 后非空 | `[F-v3-agent-role-missing]` / duplicate 完成态 `[F-v3-agent-role-duplicate]` |
| `<goal>` | Agent 任务目标, 进入 `{skill_goal}` | 没有目标则 finish_task 无判断标准 | 恰好 1 个; trim 后非空 | `[F-v3-agent-goal-missing]` / duplicate 完成态 `[F-v3-agent-goal-duplicate]` |
| `<step id>` | 步骤稳定引用 id | `@step:S1` 和模板步骤列表都依赖它 | 每个 `<step>` 必须有 id, 正则合法, 同域唯一 | `[F-v3-agent-step-invalid]` |
| `<step name>` | 步骤人类可读名称 | 模板里需要短标题帮助 LLM 规划 | 每个 `<step>` 必须有非空 name | `[F-v3-agent-step-invalid]` |
| `<step>` body | 具体步骤说明 | 没有正文的步骤对执行无帮助 | trim 后非空; 按 body 顺序进入 template | `[F-v3-agent-step-invalid]` |
| `<protocol id>` | 判断协议 id | `@protocol:P1` 和 protocol citation 依赖它 | 每个 `<protocol>` 必须有 id, 正则合法, 同域唯一 | `[F-v3-agent-protocol-invalid]` |
| `<protocol>` body | 规则/判断依据正文 | Agent 需要可引用的业务协议 | trim 后非空; 装配为 `[protocol:id] ...` | `[F-v3-agent-protocol-invalid]` |
| `<exit_contract>` | 输出契约正文 | finish_task 前最后看到的约束应该靠近 prompt 末尾 | 恰好 1 个; trim 后非空; 装配时追加 `io.outputs` | `[F-v3-agent-exit-contract-missing]` / duplicate 完成态 `[F-v3-agent-exit-contract-duplicate]` |
| 顶层未知标签 | 防止作者自造容器 | 自造 `<steps>` 等会和 cognitive template 容器重复 | 只允许 `role/goal/step/protocol/exit_contract`; 当前代码显式拦 `<steps>` | `[F-v3-agent-body-tag-unknown]` |

难点 4: **扁平容器**。Agent body 只提供业务原子块, cognitive template 提供框架容器。这样每个 skill 不会自造一套 prompt 结构, Engine 也能稳定把 role、goal、steps、protocols、resources、exit contract 放到固定位置。

## Registry、resources 和 examples

`AgentRegistryItem` 定义 `name`, `target_skill`, `description`: `packages/graph-agent/src/graph_agent/core/manifest.py:46`. `ReferenceSpec` 定义 `id`, `path`, `summary`: `packages/graph-agent/src/graph_agent/core/manifest.py:56`. `ExampleSpec` 定义 `id`, `type`, `content`, `path`, `summary`: `packages/graph-agent/src/graph_agent/core/manifest.py:66`. 当前 runtime 在 Agent assembly 中为 references/examples 注入 `read_reference` / `read_example` 工具: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:418`.

### registry item 字段

| 字段 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 失败错误码 |
|---|---|---|---|---|
| `name` | 本 Agent body 内的本地引用名 | `@subagent:NAME` / `@subgraph:NAME` 必须查得到 | 必填; 当前正则 `^[A-Za-z_][A-Za-z0-9_]*$`; 完成态要求列表内唯一 | `[F-v3-agent-subagent-invalid]` / `[F-v3-agent-subgraph-invalid]` |
| `target_skill` | registry skill id | 指向实际子 Agent 或子图 skill | 必填完成态; 通过 `SkillResolverProtocol` 解析 | `[F-v3-skill-not-registered]` / `[F-v3-resolver-skill-id-invalid]` |
| `description` | 给 LLM 和 Studio 的用途说明 | 没有说明, 自动补全和 tool 描述不可用 | 必填非空字符串 | `[F-v3-agent-subagent-invalid]` / `[F-v3-agent-subgraph-invalid]` |

### subagent 兼容字段

| 字段 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 失败错误码 |
|---|---|---|---|---|
| `SubagentSpec.name` | 动态工具名的一部分: `call_subagent_<name>` | 冲突会覆盖已有工具或混淆 trace | 必填, 正则合法; 注入时不能与已有 tool 同名 | `[F-v3-agent-subagent-invalid]` / 当前 `[F-v3-actions]` |
| `SubagentSpec.target_skill` | V0.3.0 子 Agent registry id | 子 Agent 应由 resolver 寻址 | 有值时必须提供 `skill_resolver`, 并解析到 skill root | `[F-v3-resolver-missing]` / `[F-v3-skill-not-registered]` |
| `SubagentSpec.path` | legacy 相对路径 | 当前代码仍兼容旧子技能路径 | 只能相对 phase root, 不可逃逸 skill root, 目标含 `GRAPH.md` | 当前 `[F-v3-route]`; 完成态退役 |
| `SubagentSpec.description` | 动态 tool 描述 | LLM 需要知道何时调用子 Agent | 必填非空 | `[F-v3-agent-subagent-invalid]` |

### reference 字段

| 字段 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 失败错误码 |
|---|---|---|---|---|
| `references[].id` | reference 稳定 key | `@reference:R1` 和 `read_reference("R1")` 都用它 | 必填; 当前/规范正则 `^[A-Z][A-Za-z0-9_-]*$`; list 内唯一完成态校验 | `[F-v3-resource-reference-id-invalid]` |
| `references[].path` | 原始资料相对路径 | reader/tool 必须能安全读取, 不能逃逸 skill root | 必填; skill root 内可读文件; runtime `_read_skill_root_file()` 也做逃逸校验 | `[F-v3-resource-reference-path-invalid]` |
| `references[].summary` | registry listing 和 tooltip | LLM 需要先知道资料内容范围再决定是否读取 | 必填, trim 后非空 | `[F-v3-resource-reference-summary-missing]` |

Reference 三机制并存: 编译/装配期可预读提炼, runtime 可用 `read_reference`, body 可写 `@reference:R1` 做静态依赖。三者解决的问题不同: 预读让模型先获得知识修正, tool 允许细读原文, mention 让具体步骤依赖可审计。

### example 字段

| 字段 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 失败错误码 |
|---|---|---|---|---|
| `examples[].id` | example 稳定 key | `@example:E1` 和 `read_example("E1")` 都用它 | 必填; 正则 `^[A-Z][A-Za-z0-9_-]*$`; list 内唯一完成态校验 | `[F-v3-resource-example-id-invalid]` |
| `examples[].type` | 区分 inline/document 模式 | 两种模式装配行为不同 | 必填; 只能是 `inline` 或 `document` | `[F-v3-resource-example-type-invalid]` |
| `examples[].content` | inline 示例正文 | 短示例要直接进入 prompt | `type:inline` 时必填非空; `type:document` 时禁止 | `[F-v3-resource-example-invalid]` |
| `examples[].path` | document 示例路径 | 长示例只按需读取 | `type:document` 时必填, 文件可读且不逃逸 skill root; inline 禁止 | `[F-v3-resource-example-path-missing]` / `[F-v3-resource-example-path-invalid]` |
| `examples[].summary` | document 示例目录说明 | LLM 需要判断是否值得读取 | document 必填非空; inline 可选 | `[F-v3-resource-example-summary-missing]` |

Example 双模式的原因是控制 prompt 体积: inline 短案例直接注入, document 长案例只列 id/summary, Agent 需要时再用 `read_example` 拉取。

## @type:NAME mention 静态校验

`mentions.py` 的合法 token regex 是 `@(subagent|tool|subgraph|protocol|step|reference|example):([A-Za-z0-9_-]+)`: `packages/graph-agent/src/graph_agent/core/mentions.py:8`. 残缺 mention 用另一个 regex 检查缺冒号场景: `packages/graph-agent/src/graph_agent/core/mentions.py:11`. Loader 对 Agent body 先查残缺 token, 再构建 7 个可达域并逐个验证: `packages/graph-agent/src/graph_agent/core/loader.py:1210`.

### mention 字段和 7 类查询域

| 字段 / 类型 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 失败错误码 |
|---|---|---|---|---|
| `type` | 决定查哪个 registry | 跨域 fallback 会掩盖作者写错类型 | 只能是 `subagent`, `tool`, `subgraph`, `protocol`, `step`, `reference`, `example` | `[F-v3-mention-type-unknown]` |
| `NAME` | registry key | 拼写错应编译期发现 | `^[A-Za-z0-9_-]+$`, 大小写敏感 | `[F-v3-mention-syntax-invalid]` / `[F-v3-mention-target-not-found]` |
| 完整 token | Studio 自动补全和 Loader 扫描的共同格式 | 残缺 token 留给 LLM 会变成不可控自然语言 | 必须无空格且形如 `@reference:R1`; 缺冒号 FATAL | `[F-v3-mention-syntax-invalid]` |
| `@subagent:NAME` | 引用 Agent 可委托子技能 | 子 Agent 未注册就无法注入动态工具 | `NAME` 必须在 `frontmatter.subagents[].name` | `[F-v3-mention-target-not-found]` |
| `@tool:NAME` | 引用 ReAct tool | prompt 提到不存在 tool 会导致 LLM 乱调用 | `NAME` 在 `tools[]` 或 framework builtin; 当前域额外含 `finish_task` | `[F-v3-mention-target-not-found]` / `[F-v3-agent-tool-unknown]` |
| `@subgraph:NAME` | 引用 Agent 可见子图资产 | 未注册子图不能在提示里当可用资产 | `NAME` 在 `subgraphs[].name`, target 可 resolve 完成态校验 | `[F-v3-mention-target-not-found]` / `[F-v3-skill-not-registered]` |
| `@protocol:P1` | 引用当前 body protocol | 规则引用必须可审计 | `P1` 在 `<protocol id>` | `[F-v3-mention-target-not-found]` |
| `@step:S1` | 引用当前 body step | 步骤互相引用不能悬空 | `S1` 在 `<step id>` | `[F-v3-mention-target-not-found]` |
| `@reference:R1` | 引用 reference registry | 文档改名或删除应静态报错 | `R1` 在 `references[].id` | `[F-v3-mention-target-not-found]` |
| `@example:E1` | 引用 example registry | 案例依赖应可审计 | `E1` 在 `examples[].id` | `[F-v3-mention-target-not-found]` |

## cognitive template 装配交接

编译模块产出的 `AgentNodeAST` 被 graph assembly 消费。`_agent_system_prompt()` 从 Agent AST 读取 `role`, `goal`, `steps`, `protocols`, `exit_contract`, `io.outputs`, `examples`, `llm_role`, 然后调用 `apply_v030_cognitive_template()`: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:382`. 这不是编译阶段调用 LLM, 而是把 AST 渲染为 runtime 将要发给模型的 system prompt。

### template 输入字段

| 字段 / slot | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 失败错误码 |
|---|---|---|---|---|
| `phase_name` | prompt 中标识当前 phase | trace 和 prompt 诊断需要对应节点 | 来自 phase id | 无 |
| `role` / `{skill_role}` | Agent 身份 | 缺失会使 LLM 角色泛化 | 来自 `<role>`, 非空 | `[F-v3-agent-role-missing]` |
| `goal` / `{skill_goal}` | Agent 目标 | 缺失会让 finish_task 标准不清 | 来自 `<goal>`, 非空 | `[F-v3-agent-goal-missing]` |
| `steps` / `{skill_steps_splat}` | 业务步骤列表 | 指导规划, 支持 `@step` 引用 | 按 body 顺序展开; 可为空 | `[F-v3-agent-step-invalid]` |
| `protocols` / `{skill_protocols_splat}` | 判断协议列表 | 输出诊断需要引用依据 | 按 body 顺序展开; 空时写无显式协议 | `[F-v3-agent-protocol-invalid]` |
| `knowledge_base` | reference reader 预读结果 | 让模型先获得领域知识修正 | 可为空; reader 失败完成态 WARN 降级 | `[F-v3-reference-reader-failed]` |
| `inline_examples` | inline 案例正文 | 短案例直接进入 prompt | 来自 `examples[type=inline].content` | `[F-v3-resource-example-invalid]` |
| `document_examples` | document 案例目录 | 长案例不预读, 只给 id/summary | 来自 `examples[type=document].id/summary` | `[F-v3-resource-example-invalid]` |
| `role_prefix` | llm_role 对应 system prefix | 路由角色可能带方法论约束 | `resolve_role_prefix_from_llm_role()` 找不到时当前只 warning 并返回空 | `[F-v3-agent-llm-role-unknown]` 完成态 |
| `exit_contract` / `{skill_exit_contract_inline}` | 最终输出契约 | 放在 prompt 末尾提升模型遵守概率 | 来自 `<exit_contract>`, 追加 `output_schema` | `[F-v3-agent-exit-contract-missing]` |
| `output_schema` | finish_task 结构化输出 schema | runtime 要把 Markdown 转成声明输出 | 优先 phase `io.outputs`, 终端兼容 graph outputs | `[F-v3-cognitive-output-schema-render-failed]` |

## CompiledSkill: 编译结果交给 runtime 的形状

`CompiledSkill` 是 loader 返回的内存对象, 定义字段包括 `raw`, `manifest`, `nodes`, `actions`, `tools`, `subagents_by_phase`, `phase_tokens`: `packages/graph-agent/src/graph_agent/core/loader.py:69`. Runtime assembly 用它建立 LangGraph 节点和边: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:77`.

### CompiledSkill 相关字段

| 字段 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 失败错误码 |
|---|---|---|---|---|
| `raw` | 保存 graph/io/phases 原始解析片段 | Studio/debug 需要看到源数据, cache 也依赖它 | dict, 包含 graph frontmatter/body, io schema, phase raw blocks | cache 恢复失败则 miss; runtime fallback `[F-v3-runtime-phase-failed]` |
| `manifest` | `GraphManifest` 强类型根图 | assembly 读取 `phases` 建节点和边 | 必须通过 Pydantic 校验 | `[F-v3-graph-schema-version-mismatch]` 等 graph schema 错误 |
| `nodes` | `PhaseDocument` 列表 | 每个 phase 的 path/mode/frontmatter/raw_blocks/ast 都在这里 | 每个 discovered phase 对应一个文档 | phase domain schema 错误 |
| `actions` | Logic action registry | runtime Logic node resolve callable | Python 模块加载、签名、纯净性扫描通过 | `[F-v3-actions]` / `[F-v3-purity]` / 完成态 logic action 错误 |
| `tools` | Agent tool registry | runtime Agent `bind_tools()` 的业务工具来源 | root/phase tools + subagent dynamic tools 注入 | `[F-v3-agent-tool-unknown]` / 当前 `[F-v3-actions]` |
| `subagents_by_phase` | 每个 Agent phase 的已解析子 Agent metadata | dynamic `call_subagent_<name>` 和 runtime 子图调用依赖它 | 编译 subagent root, 生成 input model 和 expected schema | `[F-v3-skill-not-registered]` / `[F-v3-resolver-path-invalid]` |
| `phase_tokens` / `source_spans` | 源码定位信息 | Studio 需要打开文件到具体行 | 当前保存 body `<phase/>` token; 完成态应迁移到 YAML spans | 无; 定位缺失不应改变业务语义 |

### PhaseDocument 字段

| 字段 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 失败错误码 |
|---|---|---|---|---|
| `phase_name` | phase id / directory name | assembly 用它把 manifest phase id 映射到 AST | 来自 `phases/<id>/` | `[F-v3-graph-phase-dir-missing]` |
| `path` | phase node file 路径 | 错误定位、resource root 推断都需要它 | 必须是三选一节点文件 | `[F-v3-graph-phase-node-missing]` |
| `mode` | discovered 物理模式 | 决定构建 Logic/Subgraph/Agent AST | 来自 `_PHASE_FILE_TO_MODE` | `[F-v3-graph-mode-path-mismatch]` |
| `frontmatter` | phase YAML 原文 dict | AST 和 Studio 表单都从这里读配置 | parse 后必须符合对应 AST | phase-specific schema error |
| `raw_blocks` | body block 原文 | legacy 补字段和 debug | 由允许标签抽取 | `[F-v3-agent-body-tag-unknown]` / AST validation |
| `ast` | 强类型 phase AST | runtime 不再解释 Markdown 原文 | `LogicNodeAST | SubgraphNodeAST | AgentNodeAST | SkillNodeAST` discriminator 校验 | phase-specific schema error |

### CompiledSubagent 字段

| 字段 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 失败错误码 |
|---|---|---|---|---|
| `parent_phase_id` | 子 Agent 属于哪个 Agent phase | dynamic tool 只能注入到父 phase | 来自当前 `PhaseDocument.phase_name` | `[F-v3-agent-subagent-invalid]` |
| `name` | 子 Agent 本地名 | 生成 `call_subagent_<name>` | 来自 subagent spec, 与工具名不冲突 | `[F-v3-agent-subagent-invalid]` |
| `target_skill` | 子 Agent skill id | trace 和 resolver metadata 需要稳定 id | 来自 `target_skill` 或 legacy path | `[F-v3-resolver-skill-id-invalid]` |
| `description` | tool 描述 | LLM 调 tool 前需要用途说明 | 非空 | `[F-v3-agent-subagent-invalid]` |
| `root` | 已解析子 skill 根目录 | runtime 要递归 assemble 子图 | resolver/path 得到目录且含 `GRAPH.md` | `[F-v3-skill-not-registered]` / `[F-v3-resolver-path-invalid]` |
| `input_schema` | 子 Agent 根输入 schema | 构造工具参数模型 | 必须是非空 dict | 当前 `[F-v3-route]`; 完成态 `[F-v3-agent-io-schema-invalid]` |
| `input_model` | Pydantic 参数模型 | 让工具调用参数可校验 | 由 `build_subagent_input_model()` 从 schema 生成 | `[F-v3-agent-subagent-invalid]` |
| `expected_schema` | 工具提示给 LLM 的 JSON Schema | LLM 知道调用参数形状 | `input_model.model_json_schema()` | `[F-v3-agent-subagent-invalid]` |

## graph assembly 如何消费编译结果

`assemble_graph()` 先把 `compiled.nodes` 建成 `node_by_phase`, 再按 `compiled.manifest.phases` 添加 LangGraph node 和 edge: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:77`. Logic/Subgraph/Agent 分别进入不同 builder; 有 `io` 的 phase 被 `PhaseWrapper(StateMapper(io.inputs, io.outputs))` 包起来: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:158`.

这就是为什么编译期必须把 phase IO 写进 AST: runtime 的 StateMapper、Agent `finish_task` output_schema、Subgraph IO 对齐、数据流静态证明都读同一份字段。重复解析会让这些模块产生不同真相源。

## cache: 加速但不改变语义

cache key 由 root、Python 版本、包版本和 skill 文件元数据组成: `packages/graph-agent/src/graph_agent/core/cache.py:22`. 当前 `_collect_skill_files()` 收 `GRAPH.md`, `io/*.json`, `phases/**/*.md`: `packages/graph-agent/src/graph_agent/core/cache.py:55`. snapshot 当前保存 `raw`, `manifest`, `nodes`, 不保存动态 Python 类: `packages/graph-agent/src/graph_agent/core/cache.py:84`.

### cache 字段

| 字段 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 失败错误码 |
|---|---|---|---|---|
| `raw` | cache 恢复 debug/source 信息 | cache hit 应与冷编译可观察结果接近 | JSON 可序列化 dict | cache 读失败 miss |
| `manifest` | 根图 AST snapshot | 恢复后 assembly 直接读 DAG | `GraphManifest.model_validate()` | `[F-v3-graph-schema-version-mismatch]` 等 |
| `nodes` | phase AST snapshot | 恢复 phase docs | `TypeAdapter[PhaseAST]` 校验每个 ast | phase schema 错误; cache 读失败 miss |
| `subagents_by_phase` | 完成态保存 resolved metadata | cache hit 后也要能注入 subagent tools | 不保存动态 Python 类, 只保存可重建字段 | `[F-v3-resolver-path-invalid]` |
| `source_spans` | 完成态保存 YAML/XML 行号 | cache hit 后 Studio 仍能定位错误 | 可选 dict; 缺失只影响定位 | 无 |
| `schema_version` | cache snapshot 版本 | 防止旧 snapshot 被新 AST 误读 | 完成态固定 `"0.3.0"` | `[F-v3-graph-schema-version-mismatch]` |

## 错误码全清单: skill-compilation 相关

编译错误应使用 `[F-v3-*]` 稳定前缀。当前代码还有少量粗粒度 helper 前缀, 例如 `[F-v3-route]`, `[F-v3-graph]`, `[F-v3-io]`, `[F-v3-actions]`, `[F-v3-actions-keys]`, `[F-v3-purity]`; 完成态对外应按 spec 中 domain-specific code 归一。

### graph domain

- `[F-v3-graph-schema-unknown-field]`: `GRAPH.md` frontmatter 出现未知字段。
- `[F-v3-graph-name-invalid]`: `name` 缺失或命名非法。
- `[F-v3-graph-schema-version-mismatch]`: `schema_version` 不是 `"0.3.0"`。
- `[F-v3-graph-llm-role-unknown]`: `llm_role` 未注册。
- `[F-v3-graph-root-missing]`: 根 `GRAPH.md` 缺失。
- `[F-v3-graph-phases-dir-missing]`: `phases/` 缺失。
- `[F-v3-graph-phase-id-invalid]`: phase id 命名非法。
- `[F-v3-graph-phase-id-duplicate]`: phase id 重复。
- `[F-v3-graph-depends-unknown]`: `depends_on` 引用未知 phase。
- `[F-v3-graph-phase-cycle]`: DAG 存在环。
- `[F-v3-graph-phase-island]`: phase 与入口不可达。
- `[F-v3-graph-phase-dir-missing]`: phase 目录不存在。
- `[F-v3-graph-phase-mode-ambiguous]`: 同一 phase 下多个节点文件。
- `[F-v3-graph-phase-node-missing]`: phase 目录无节点文件。
- `[F-v3-graph-mode-path-mismatch]`: 文件名与 `mode` 不一致。
- `[F-v3-graph-io-not-object]`: 根 IO 顶层不是 object schema。
- `[F-v3-graph-io-schema-invalid]`: 根 IO JSON Schema 非法。
- `[F-v3-graph-io-physical-file-deprecated]`: 使用旧 `io/*.json` 或 `io_inputs_ref/io_outputs_ref`。
- `[F-v3-graph-dataflow-source-missing]`: phase required input 没有根输入或上游输出来源。

### logic domain

- `[F-v3-logic-schema-unknown-field]`: `LOGIC.md` frontmatter 未知字段。
- `[F-v3-logic-name-invalid]`: Logic `name` 非法。
- `[F-v3-logic-mode-invalid]`: `mode` 不是 `logic`。
- `[F-v3-logic-io-schema-invalid]`: Logic IO schema 非法。
- `[F-v3-logic-actions-empty]`: `actions` 为空。
- `[F-v3-logic-action-name-invalid]`: action 名非法。
- `[F-v3-logic-action-dir-missing]`: `<skill_root>/actions/` 缺失。
- `[F-v3-logic-action-not-found]`: action py 文件不存在。
- `[F-v3-logic-action-entrypoint-missing]`: action 无 `run()`。
- `[F-v3-logic-action-return-invalid]`: action 返回非 dict。
- `[F-v3-logic-output-field-undeclared]`: 返回未声明输出字段。
- `[F-v3-logic-validator-type-invalid]`: `validator` 不是 boolean。
- `[F-v3-logic-validator-missing]`: `validator: true` 但无文件。
- `[F-v3-logic-validator-entrypoint-missing]`: validator 无 `validate()`。
- `[F-v3-logic-validator-failed]`: validator 抛异常。

### subgraph domain

- `[F-v3-subgraph-schema-unknown-field]`: `SUBGRAPH.md` 未知字段。
- `[F-v3-subgraph-name-invalid]`: `name` 非法。
- `[F-v3-subgraph-mode-invalid]`: `mode` 不是 `subgraph`。
- `[F-v3-subgraph-target-skill-invalid]`: `target_skill` 非法或像路径。
- `[F-v3-subgraph-io-schema-invalid]`: Subgraph IO schema 非法。
- `[F-v3-subgraph-io-mismatch]`: 父子 IO 字段集合不一致。
- `[F-v3-subgraph-io-schema-incompatible]`: 同名字段 schema 不兼容。

### agent / mention / resource / resolver / cognitive domain

- `[F-v3-agent-schema-unknown-field]`: Agent frontmatter 未知字段。
- `[F-v3-agent-name-invalid]`: Agent `name` 非法。
- `[F-v3-agent-mode-invalid]`: `mode` 不是 `agent`。
- `[F-v3-agent-llm-role-unknown]`: `llm_role` 未注册。
- `[F-v3-agent-io-schema-invalid]`: Agent IO schema 非法。
- `[F-v3-agent-tool-unknown]`: tool 未注册。
- `[F-v3-agent-subagent-invalid]`: subagents 项缺字段或结构错。
- `[F-v3-agent-subgraph-invalid]`: subgraphs 项缺字段或结构错。
- `[F-v3-agent-max-iterations-invalid]`: `max_iterations` 超范围。
- `[F-v3-agent-body-tag-unknown]`: body 顶层未知 XML 标签。
- `[F-v3-agent-role-missing]`: 缺 `<role>`。
- `[F-v3-agent-goal-missing]`: 缺 `<goal>`。
- `[F-v3-agent-exit-contract-missing]`: 缺 `<exit_contract>`。
- `[F-v3-agent-step-invalid]`: step id/name/content 非法或重复。
- `[F-v3-agent-protocol-invalid]`: protocol id/content 非法或重复。
- `[F-v3-mention-type-unknown]`: mention 类型不在 7 类内。
- `[F-v3-mention-syntax-invalid]`: mention token 残缺或含空格。
- `[F-v3-mention-target-not-found]`: mention 目标不在对应 registry。
- `[F-v3-mention-unused-registry-entry]`: 注册项未被 body 引用, WARN。
- `[F-v3-resource-reference-invalid]`: reference 项缺字段或结构错。
- `[F-v3-resource-reference-id-invalid]`: reference id 非法或重复。
- `[F-v3-resource-reference-path-invalid]`: reference path 不可读或逃逸 root。
- `[F-v3-resource-reference-summary-missing]`: reference summary 为空。
- `[F-v3-resource-reference-not-found]`: runtime `read_reference` id 不存在。
- `[F-v3-resource-example-invalid]`: example 项缺字段或结构错。
- `[F-v3-resource-example-id-invalid]`: example id 非法或重复。
- `[F-v3-resource-example-type-invalid]`: example type 非法。
- `[F-v3-resource-example-path-missing]`: document example 缺 path。
- `[F-v3-resource-example-path-invalid]`: example path 不可读。
- `[F-v3-resource-example-summary-missing]`: document example 缺 summary。
- `[F-v3-resource-example-not-found]`: runtime `read_example` id 不存在。
- `[F-v3-reference-reader-failed]`: builtin reader 失败, WARN 降级。
- `[F-v3-resolver-skill-id-invalid]`: skill id 非法。
- `[F-v3-skill-not-registered]`: resolver 查不到 skill。
- `[F-v3-resolver-path-invalid]`: resolver 返回路径无 `GRAPH.md`。
- `[F-v3-resolver-interface-invalid]`: resolver 接口不符合单方法协议。
- `[F-v3-resolver-missing]`: 需要 resolver 但未注入。
- `[F-v3-cognitive-slot-render-failed]`: template slot 序列化失败。
- `[F-v3-cognitive-output-schema-render-failed]`: output schema 无法嵌入 exit contract。
- `[F-v3-reference-reader-input-invalid]`: reader 输入 JSON 非法。
- `[F-v3-reference-reader-output-invalid]`: reader 输出 JSON 非法。
- `[F-v3-tool-argument-invalid]`: builtin tool 参数非法。
- `[F-v3-runtime-state-mapping-failed]`: StateMapper 切片或回写失败。
- `[F-v3-runtime-phase-failed]`: phase 执行异常且无法归入更细错误。

### 结构化 issue 字段

| 字段 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 失败错误码 |
|---|---|---|---|---|
| `code` | 稳定错误码 | UI、测试、文档链接都依赖稳定 code | 必须是 `[F-v3-<domain>-<specific>]` | schema 错误归入对应 domain |
| `severity` | FATAL/WARN | 决定是否中断编译 | FATAL 阻断, WARN 保留 compiled object | 无单独错误码 |
| `stage` | compile/assembly/runtime | 定位生命周期 | 编译模块主要产生 compile, template 产生 assembly | 无单独错误码 |
| `phase_id` | 关联 Canvas 节点 | 没有它就无法标红节点 | phase 相关错误必须提供 | 无单独错误码 |
| `field_path` | 表单字段定位 | Studio 需要定位到具体字段 | 字段错误建议提供 JSON path/YAML path | 无单独错误码 |
| `source_path` | 源文件路径 | 编辑器打开文件 | 必须是真实路径 | 无单独错误码 |
| `line` | 行号 | 编辑器跳转 | YAML/XML AST 能获取时提供 | 无单独错误码 |
| `message` | 人类可读说明 | CLI/面板需要解释 | 必填字符串 | 无单独错误码 |
| `doc_link` | 修复文档入口 | 用户能跳到 spec | 指向 skill-spec 锚点 | 无单独错误码 |

## V0.3.0 决策如何落到代码边界

这份文档覆盖 mvp0-alignment 的 13 个改造点:

1. `AgentNodeAST` 替换 `SkillNodeAST`: 解释 `AgentNodeAST` 字段和 legacy `system_prompt` 兼容边界。
2. phase-level `io`: 解释 `PhaseIOSchema` 如何支撑 dataflow、StateMapper、finish_task 和 subgraph 对齐。
3. phase 物理布局与 DAG: 解释 `GRAPH.md`, `phases/<id>/` 和三选一节点文件。
4. 根 IO inline 化: 解释 `io` 与 legacy `io_inputs_ref/io_outputs_ref` 退役原因。
5. 静态数据流校验: 解释 root inputs、upstream outputs、phase required inputs。
6. `SUBGRAPH.md target_skill`: 解释 resolver 寻址和父子 IO 1:1。
7. Cognitive Template: 解释 Agent body AST 如何渲染模板, `output_schema` 为什么贴到 exit contract 末尾。
8. Mention 静态可达性: 覆盖 7 类 `@type:NAME`。
9. 子图 IO 强映射: 解释父子 graph 函数签名式校验。
10. LOGIC actions 一级寻址: 解释完成态 action 目录、`run()`、返回 key。
11. Resource reader 与 examples: 覆盖 reference 三机制和 example 双模式。
12. 结构化错误: 覆盖 issue 字段和完整错误码域。
13. cache 元数据: 覆盖 raw/manifest/nodes/subagents/source_spans/schema_version 和写失败降级边界。

读这份文档时, 最重要的顺序是: 先看入口目录是否能成为 graph, 再看 graph 的 DAG 是否闭合, 再看每个 phase 是否能成为强类型 AST, 再看 Agent 的 mention/resource/resolver 是否静态可达, 最后看 `CompiledSkill` 是否给 runtime 足够的信息而不替 runtime 执行业务。
