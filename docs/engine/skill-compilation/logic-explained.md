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
| `raw` | 编译器保留的原始解析结果、根 IO 和 `graph_topology`。 |

它不是运行状态，也不是最终输出。运行时会拿它继续装配 LangGraph。

## 13. 最容易误解的点

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

## 14. 总图

```text
skill root
  -> 检查 GRAPH.md 和 phases/
  -> 解析 GRAPH.md schema_version / inline io / phases 注册
  -> 解析 GRAPH.md body <phase> DAG topology
  -> 校验三方 name 一致、重复、unknown dep、cycle、island、output
  -> 由文件名推导 phase 类型并拒绝 mode/旧 metadata
  -> 解析每个 phase AST
  -> 发现 actions/tools/resources/subagents
  -> 编译 target_skill metadata 并校验 SUBGRAPH IO 1:1
  -> 检查 mentions 和资源路径边界
  -> 返回 CompiledSkill
```
