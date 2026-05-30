# skill-compilation 运行逻辑人话版

署名：Codex  
日期：2026-05-26
定位：解释 V0.3.0 skill 编译真实怎么运行，不做源码导览，不讲实现细节。

## 1. 一句话结论

`skill-compilation` 把一个磁盘上的 graph skill 目录变成结构化的 `CompiledSkill`。

它不运行 LLM，不执行 Python action，不调用业务工具，也不跑 LangGraph。它只做静态工作：

- 确认目录形状像一个 graph skill。
- 读取 `GRAPH.md` 的 `schema_version: "v0.3.0"`、inline `io` 和 phase 注册表。
- 从 `GRAPH.md` body `<phase>` 标签读取 DAG 拓扑。
- 用物理文件名推导每个 phase 的类型。
- 把 `LOGIC.md`、`SUBGRAPH.md`、`SKILL.md` 解析成 AST。
- 发现 actions、tools、subagents、references、examples。
- 做 schema、DAG、mention、SUBGRAPH IO、禁用旧字段等静态校验。
- 返回运行时可以装配的编译产物。

## 2. 编译入口做什么

公开编译入口接收 skill root 和 `SkillResolverProtocol`。resolver 用来解析 `target_skill`，所以只要图里有 SUBGRAPH phase、Agent subagent 或 Agent subgraph registry，编译期就必须能通过 resolver 找到 child skill root。

编译过程最终交给 loader。loader 返回的不是运行结果，而是 `CompiledSkill`：

```text
skill 目录
  -> 编译器读文件和校验声明
  -> CompiledSkill
  -> execution-runtime 后续再装配和运行
```

## 3. 一个 skill 目录必须长什么样

当前 graph skill 根目录至少需要：

```text
my_skill/
  GRAPH.md
  phases/
    prepare/
      LOGIC.md
      actions/
        normalize.py
    analyze/
      SKILL.md
```

根目录必须存在 `GRAPH.md` 和 `phases/`。每个 phase 子目录下面只能有一种 phase 文件：

- `LOGIC.md`
- `SUBGRAPH.md`
- `SKILL.md`

如果一个 phase 目录里同时出现两种 phase 文件，编译器抛 `[F-v3-graph-phase-mode-ambiguous]`。如果没有任何 phase 节点文件，抛 `[F-v3-graph-phase-node-missing]`。phase 文件 frontmatter 不能写 `mode:`，类型只由文件名决定；写了会按对应 domain 的 unknown field 失败。

phase 文件也不能写 `schema_version`、`graph_skill_id`、`phase_id`。这些是旧 metadata，出现即按对应 domain 的 schema unknown field 失败，避免一个 phase 自己伪造 graph 身份。

## 4. GRAPH.md 怎么被理解

`GRAPH.md` 是双轨制：

- frontmatter `phases:` 只注册 phase 名字。
- body `<phase>` 标签只描述 `depends_on` 拓扑和 `output` 结束标记。

两轨都必须存在，且必须与物理目录三方一致。

```yaml
schema_version: "v0.3.0"
name: demo
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
  outputs:
    type: object
    properties:
      summary:
        type: string
phases:
  - prepare
  - analyze
```

```xml
<phase depends_on="input">prepare</phase>
<phase depends_on="prepare" output>analyze</phase>
```

校验点：

| 校验什么 | 为什么 | 失败错误码 |
|---|---|---|
| `schema_version` 精确等于 `"v0.3.0"` | 防止旧 V2.1 graph 被新 engine 误跑 | `[F-v3-graph-schema-version-mismatch]` |
| 缺少 frontmatter `phases` | 没有 phase 注册表无法建立图 | `[F-v3-graph-phases-missing]` |
| 缺少 body `<phase>` | 没有拓扑无法排序执行 | `[F-v3-graph-phase-id-invalid]` |
| `phases` 列表重复 | 重复名字会让 AST/目录/trace 映射不唯一 | `[F-v3-graph-phase-id-duplicate]` |
| body name 或注册名与物理目录不一致 | 防止一个 phase 在不同层叫不同名字 | `[F-v3-graph-phase-name-mismatch]` |
| `depends_on` 引用未知 phase 或入口不用 `input` | 保证依赖边可解析 | `[F-v3-graph-depends-unknown]` |
| DAG 有环 | 运行时无法确定先后 | `[F-v3-graph-phase-cycle]` |
| 有从 `input` 不可达的孤岛 | 防止声明了永远不会运行的 phase | `[F-v3-graph-phase-island]` |
| `output` 标记无效或无法确定输出 phase | 保证 graph 输出来自明确结束节点 | `[F-v3-graph-output-phase-invalid]` |

## 5. 根级 IO schema 怎么来

根级 IO 只来自 `GRAPH.md` frontmatter 的 inline `io.inputs` / `io.outputs`。旧的 `io/inputs.json`、`io/outputs.json`、`io_inputs_ref`、`io_outputs_ref` 已退役，出现即失败。

校验点：

| 校验什么 | 为什么 | 失败错误码 |
|---|---|---|
| `io.inputs` / `io.outputs` 都是 object schema | 运行入口和最终输出必须结构化 | `[F-v3-graph-io-not-object]` / `[F-v3-graph-io-schema-invalid]` |
| 物理 IO 文件或 ref 字段不存在 | 防止 schema 分散到多处后漂移 | `[F-v3-graph-io-physical-file-deprecated]` |

## 6. phase 文件怎么被解析

phase 类型由文件名推导，loader 注入内部 AST discriminator：

| 文件 | 内部类型 | 作者写 `mode:` 吗 |
|---|---|---|
| `LOGIC.md` | `logic` | 不写 |
| `SUBGRAPH.md` | `subgraph` | 不写 |
| `SKILL.md` | `agent` | 不写 |

`SKILL.md` 不再支持 legacy `mode: skill` / `SkillNodeAST`。它总是 Agent phase，解析成 `AgentNodeAST`。

旧 V2.1 persona 入口也不在当前 active 编译链路里。`adopted_persona`、`PersonaSkillDef`、`resolve_persona` 以及旧 `skill_builder.build_graph_nodes` 死码簇已经从运行代码中拆除；V0.3 graph root 的真实编译入口是 loader/compiler 生成 `CompiledSkill`，再由 runtime 的 `graph_assembler` 装配。

## 7. LOGIC.md 怎么工作

`LOGIC.md` frontmatter 声明 phase-level `io`、`actions` 可选字段和 `validator` boolean；body 用一组 `<action>name</action>` 决定执行顺序。实现以 body `<action>` 顺序为准，frontmatter `actions` 若写出必须与 body 顺序一致。

```yaml
---
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties:
      summary:
        type: string
validator: false
---
<action>prepare</action>
```

校验点：

| 校验什么 | 为什么 | 失败错误码 |
|---|---|---|
| 至少一个 `<action>` | LOGIC 没有 action 就无事可做 | `[F-v3-logic-actions-empty]` |
| action 名合法且可找到实现 | 防止路径逃逸和拼错函数 | `[F-v3-logic-action-name-invalid]` / `[F-v3-logic-action-not-found]` |
| action 输出 key 不超出声明的 `io.outputs` | 防止脏字段写回黑板 | `[F-v3-logic-output-field-undeclared]` |
| `validator` 必须是 YAML boolean | 字符串 `"true"` 会造成配置歧义 | `[F-v3-logic-validator-type-invalid]` |
| `validator: true` 时 validator 文件和入口存在 | 输出后置校验必须可执行 | `[F-v3-logic-validator-missing]` / `[F-v3-logic-validator-entrypoint-missing]` |

## 8. SKILL.md / Agent 怎么工作

Agent phase 的业务 prompt 来自 body 5 类扁平标签：

- `<role>`
- `<goal>`
- `<step>`
- `<protocol>`
- `<example>`

`<steps>` 这类壳标签和 `<exit_contract>` 禁止出现。`exit_contract` 是 cognitive template 的系统内置块，不由业务 skill 自定义。

校验点：

| 校验什么 | 为什么 | 失败错误码 |
|---|---|---|
| 缺 `<role>` 或 `<goal>` | Agent 身份和目标是最小 prompt 契约 | `[F-v3-agent-role-missing]` / `[F-v3-agent-goal-missing]` |
| 顶层标签不在 5 类白名单 | 防止 body 结构重新变成不受控 XML | `[F-v3-agent-body-tag-unknown]` |
| `<step>` / `<protocol>` / `<example>` id 合法且可引用 | mention 和模板插槽需要稳定 id | `[F-v3-agent-step-invalid]` / `[F-v3-agent-protocol-invalid]` / `[F-v3-agent-example-invalid]` |
| `validator` 必须是 YAML boolean | Agent 输出后置校验开关不能含糊 | Pydantic validation fatal |

## 9. mentions 和资源检查

Agent body 里的 `@type:NAME` 会被静态扫描。编译器必须证明每个 mention 在对应 registry 中可达，不能把无法解析的 mention 留给 LLM。

| Mention | 查询域 | 失败错误码 |
|---|---|---|
| `@reference:R1` | frontmatter `references[].id` | `[F-v3-mention-target-not-found]` |
| `@example:E1` | body inline `<example id>` + frontmatter document `examples[].id` | `[F-v3-mention-target-not-found]` |
| `@tool:finish_task` | frontmatter `tools[]` + framework builtin | `[F-v3-mention-target-not-found]` |
| `@subagent:NAME` | frontmatter `subagents[].name` | `[F-v3-mention-target-not-found]` |
| `@subgraph:NAME` | frontmatter `subgraphs[].name` + resolver | `[F-v3-mention-target-not-found]` / `[F-v3-skill-not-registered]` |
| `@protocol:P1` | body `<protocol id>` | `[F-v3-mention-target-not-found]` |
| `@step:S1` | body `<step id>` | `[F-v3-mention-target-not-found]` |

残缺 mention 或未知 mention type 会失败为 `[F-v3-mention-syntax-invalid]` / `[F-v3-mention-type-unknown]`。

## 10. SUBGRAPH target_skill 和 IO 怎么校验

`SUBGRAPH.md` 只用 `target_skill` 指向另一个 graph skill，不接受相对路径 include。

编译器会：

1. 用 `skill_resolver.resolve_skill(target_skill)` 找到 child root。
2. 递归编译 child graph。
3. 比较父图 SUBGRAPH phase 的 `io.inputs.properties` 与 child `GRAPH.md io.inputs.properties`。
4. 比较父图 SUBGRAPH phase 的 `io.outputs.properties` 与 child `GRAPH.md io.outputs.properties`。

字段集合必须双向 1:1 对齐，required 和同名字段 schema 也必须兼容。

| 校验什么 | 为什么 | 失败错误码 |
|---|---|---|
| resolver 缺失或接口不对 | 编译器不能猜 registry | `[F-v3-resolver-missing]` / `[F-v3-resolver-interface-invalid]` |
| `target_skill` 不合法或找不到 | 子图必须可解析 | `[F-v3-subgraph-target-skill-invalid]` / `[F-v3-skill-not-registered]` |
| 父子 IO properties 不一致 | 防止父图传参与子图入口/出口错位 | `[F-v3-subgraph-io-mismatch]` |
| 同名字段 schema 不兼容 | 防止同名不同义 | `[F-v3-subgraph-io-schema-incompatible]` |

## 11. actions 和 tools 怎么发现

编译器会扫描 phase-local 目录：

- LOGIC phase 使用同级 `actions/<name>.py`。
- Agent phase 可以使用同级 `tools/` 和内置 framework tools。
- SUBGRAPH phase 不能挂 actions/tools。

根级 `actions/` 或不属于当前 phase 类型的目录会被拒绝，避免工具或 action 跑到错误 runtime。

## 12. 编译产物里有什么

`CompiledSkill` 主要包含：

| 字段 | 人话解释 |
|---|---|
| `manifest` | 根图结构：名字、phase 注册表、根级 IO。 |
| `nodes` | 每个 phase 解析后的 AST。 |
| `actions` | LOGIC phase 可调用的 action registry。 |
| `tools` | Agent phase 可调用的 tool registry。 |
| `subagents_by_phase` | 每个 Agent phase 声明的 subagent metadata。 |
| `phase_tokens` | `GRAPH.md` body `<phase>` 标签的原文、行号和属性 span。 |
| `raw` | 编译器保留的原始解析结果、根 IO 和 `graph_topology`。 |

它不是运行状态，也不是最终输出。运行时会拿它继续装配 LangGraph。

## 13. 编译缓存怎么保证复水不漂移

公开 `compile_skill(..., cache=True)` 会先用 `compute_cache_key(root)` 计算磁盘缓存 key。当前 key payload 里有 `"format": "v2"`。这个字段不是业务信息，而是缓存格式开关：旧缓存曾经只保存 `raw`、`manifest`、`nodes`，会在命中后丢掉 subagent 和 phase token 信息。把格式号写进 key，相当于给旧缓存换门锁，避免旧 snapshot 被新 rehydrate 误读。

缓存脱水时保存这些字段：

| snapshot 字段 | 来自哪里 | 为什么要保存 |
|---|---|---|
| `raw` | `CompiledSkill.raw` | 保留 GRAPH frontmatter/body、根 IO、`graph_topology` 和 phase 原始解析片段，供后续装配与调试使用。 |
| `manifest` | `GraphManifest.model_dump(mode="json")` | 根图 schema、name、IO 和 phase 注册表是编译产物的根身份。 |
| `nodes[]` | 每个 `PhaseDocument` | 保存 `phase_name`、`path`、`mode`、`frontmatter`、`raw_blocks` 和 `ast`。其中 `ast` 用 Pydantic JSON 形态保存，cache hit 后能恢复成 `LogicNodeAST`、`SubgraphNodeAST` 或 `AgentNodeAST`。 |
| `subagents_by_phase` | `CompiledSkill.subagents_by_phase` | Agent phase 的 subagent metadata 不是可选装饰；它决定动态 `call_subagent_*` tool 能否存在。 |
| `phase_tokens` | `CompiledSkill.phase_tokens` | serializer 和编辑器定位需要知道 `<phase>` 原文、offset、行号和属性 span。 |

`subagents_by_phase` 逐项保存 `parent_phase_id`、`name`、`target_skill`、`description`、`root`、`input_schema`、`expected_schema`。其中 `root` 写成字符串，因为 JSON 没有 `Path` 类型；`input_model` 不保存，因为它是运行时动态生成的 Pydantic 类，既不可 JSON 序列化，也不能跨进程保留 Python identity。

`phase_tokens` 逐项保存 `phase_id`、`raw_text`、`start_offset`、`end_offset`、`line_start`、`line_end`、`attrs` 和 `attr_spans`。`attr_spans` 里面的每个 `PhaseAttributeSpan` 也逐字段拆开：`name`、`value`、`quote`、`attr_start`、`attr_end`、`value_start`、`value_end`、`line_start`、`line_end`。这里不能偷懒留成普通 dict；调用方会按 dataclass 对象读取 span 的属性，dict 会让 cache hit 和冷编译的对象契约不一致。

缓存复水时做的是“重建”，不是“解冻原对象”：

- `manifest` 用 `GraphManifest.model_validate()` 还原。
- `nodes[].ast` 用 `TypeAdapter[PhaseAST]` 还原成真实 AST 类型。
- `actions` 和基础 `tools` 重新跑 `_discover_actions_and_tools(root, discovered)`，因为函数对象和 tool wrapper 本来就应该从当前磁盘代码重新绑定。
- `PhaseTokenInfo` 和嵌套 `PhaseAttributeSpan` 用 dataclass 构造器还原，保证 `token.attr_spans["depends_on"].value` 这类访问在 cache hit 后仍成立。
- `CompiledSubagent.root` 从字符串还原成 `Path`。
- `CompiledSubagent.input_model` 用 `build_subagent_input_model(_subagent_input_model_name(parent_phase_id, name), input_schema)` 重建。这样模型命名和冷编译路径一致，而不是随便 `create_model` 一个相似类。
- subagent metadata 复原后，必须再调用 `_inject_subagent_tools(tools, subagents_by_phase)`。动态 `call_subagent_<name>` 工具不是 snapshot 里直接保存的函数，它依赖 subagent metadata 重新桥接到 `ToolRegistry`。

`CompiledSubagent.input_model` 标了 `field(compare=False)`。原因很具体：冷编译和 cache hit 会各自生成一个 Pydantic class，字段 schema 一样，但 Python class identity 不一样。如果它参与 dataclass equality，`hit.subagents_by_phase == cold.subagents_by_phase` 会永远失败。注意这只保证 subagent metadata 片段可比；整个 `CompiledSkill` 不承诺 `cold == hit`，因为 `actions` 和 `tools` 里的函数、动态 tool schema 也是每次重新绑定的运行时对象。

坏缓存的处理也有边界。`load_from_cache()` 遇到文件读取、JSON 解析、字段缺失、类型不匹配或复水校验失败时，会打 warning，然后返回 `None`，让上层冷编译。缓存是加速层，不应该把一个原本能编译的 skill 变成不可用。

## 14. 递归编译怎么防爆栈

`target_skill` 会让编译器递归进入另一个 skill root。没有防护时，A 的 subagent 指 B，B 又指 A，就会像两面镜子互照一样无限展开，最后裸漏 Python `RecursionError`。当前实现把递归状态显式传下去。

`SkillLoader.compile_skill()` 新增两个内部可选参数：

| 参数 | 类型 | 公开调用需要传吗 | 作用 |
|---|---|---|---|
| `_loading_stack` | `tuple[str, ...]` | 不需要 | 当前递归链路上已经进入但尚未完成的 skill root key。 |
| `_compilation_cache` | `dict[str, CompiledSkill] | None` | 不需要 | 一次顶级编译/装配生命周期内已完成的 skill root 结果。 |

它们是内部参数，默认值保持公开 API 兼容。key 统一用 `str(root.resolve())`，而不是用户传入的原始路径。这样相对路径、绝对路径和符号链接归一后指向同一个 root，不会让同一张图换个写法就绕过 guard 或重复编译。

进入编译时按固定顺序处理：

| 检查 | 条件 | 行为 | 失败错误码 |
|---|---|---|---|
| 环检测 | `root_key in _loading_stack` | 当前 root 已在递归链路中，内部抛 `SkillLoadError` leaf（IS-A `GraphCompileError`） | `[F-v3-compile-recursion-cycle]` |
| 深度上限 | `len(_loading_stack) >= 20` | push 当前 root 前拦截，避免第 21 层继续展开 | `[F-v3-compile-depth-exceeded]` |
| 同图去重 | `root_key in _compilation_cache` | 直接返回已编译的 `CompiledSkill` 引用 | 无 |

深度是在 push 当前 root 前检查的。这样 `_loading_stack` 表示“已经在栈上的父链路”，阈值语义稳定：当父链路已经有 20 层时，不再允许继续进入下一层。

loader 内部有两个递归点会透传更新后的 stack/cache：

- `_validate_subgraph_io_contracts()` 编译 child graph，用来比较父 SUBGRAPH phase IO 与 child `GRAPH.md` 根 IO。
- `_compile_subagent_metadata()` 编译 subagent target skill，用来读取 child `io.inputs` 并生成 subagent input model。

装配期也有递归编译，因此 `graph_assembler.py` 同步透传同一份状态：

- `_build_subgraph_node()` 解析 SUBGRAPH phase 的 `target_skill`，编译 child，再递归 `assemble_graph()`。
- `_subagent_runtime_map()` 为 Agent phase 的动态 subagent tool 准备 runtime graph，同样编译 child，再递归 `assemble_graph()`。

这两处在调用 loader 前也会先查 `_compilation_cache`。所以同一个 child root 在一次装配生命周期里只真实编译一次；后续引用直接复用已编译结果。

## 15. 最容易误解的点

### 编译不等于运行

编译只证明“目录、声明和静态依赖可装配”。它不会证明某次输入一定能成功，也不会调用 LLM。

### GRAPH.md 是双轨，不是二选一

frontmatter `phases:` 和 body `<phase>` 都必须有。frontmatter 管注册，body 管拓扑。

### inline IO 是唯一来源

没有 inline `io.inputs` / `io.outputs` 不会 fallback 到物理 JSON 文件；旧物理 IO 是 fatal。

### `mode:` 不是作者字段

phase 类型由文件名决定。`mode:` 只存在于内部 AST discriminator。

### resolver 不只是 runtime 问题

`target_skill` 会在编译期 resolve，用于 SUBGRAPH IO 对齐和 Agent registry 可达性。

## 16. 总图

```text
skill root
  -> 检查 GRAPH.md 和 phases/
  -> 解析 GRAPH.md schema_version / inline io / phases 注册
  -> 解析 GRAPH.md body <phase> DAG topology
  -> 校验三方 name 一致、重复、unknown dep、cycle、island、output
  -> 由文件名推导 phase 类型并拒绝 mode/旧 metadata
  -> 解析每个 phase AST
  -> 发现 actions/tools/resources/subagents
  -> 带递归 guard 编译 target_skill metadata 并校验 SUBGRAPH IO 1:1
  -> 检查 mentions 和资源路径边界
  -> 返回 CompiledSkill
  -> cache=True 时以 v2 snapshot 保真保存/复水
```
