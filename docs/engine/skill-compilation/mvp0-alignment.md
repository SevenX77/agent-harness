# skill-compilation (engine) — MVP0 Alignment (V0.3.0 graph_skill)

> **Status**: Rewritten by a1 (Codex) for V0.3.0 graph_skill, 2026-05-23
> **Scope**: V0.3.0 `docs/engine/skill-spec/` 文件标准、Loader AST 构建、Phase 物理布局校验、DAG / IO / Mention 静态校验、Agent cognitive template 装配、SkillResolverProtocol DI。
> **配套**: 见 [skill-spec README](../skill-spec/README.md) 与 [MVP0 decisions explained](../MVP0-DECISIONS-EXPLAINED-2026-05-21.md)。

## V0.3.0 改造摘要

本文件从 V2.1 编译规划改写为 V0.3.0 graph_skill 编译规划。以下旧段落被完全推翻并重写:

| 旧语义 | V0.3.0 新语义 | 原因 / 决议来源 |
|---|---|---|
| `mode: skill` / phase frontmatter `mode:` | 文件名推导内部 `mode="agent"` | SKILL.md 是 Agent phase; 作者不写 `mode:`, 见 [Agent SKILL.md Spec](../skill-spec/05-agent-md-spec.md#frontmatter-字段解析表) |
| `SkillNodeAST` | `AgentNodeAST` | Agent frontmatter + body XML 被强类型拆分, 不再用 `system_prompt` 字符串承载全部内容 |
| V2.1 `GRAPH.md` self-closing body `<phase id src depends_on />` | `GRAPH.md` 双轨: frontmatter `phases:` 注册 + body `<phase depends_on output>name</phase>` 拓扑 | 注册与 DAG 分离但必须三方一致, 见 [GRAPH Phase DAG](../skill-spec/02-graph-md-spec.md#phases-注册与-body-拓扑校验-phase-registration--dag) |
| `io/inputs.json` / `io/outputs.json` | inline `io.inputs` / `io.outputs` dict | 物理 IO 文件退役, 见 [Root IO Schema](../skill-spec/02-graph-md-spec.md#根-io-契约-root-io-schema) |
| `_resolve_subagent_root` 相对路径扫描 | `SkillResolverProtocol.resolve_skill(skill_id) -> Path` DI | 子图 / 子 Agent 全局 registry 寻址, 见 [Skill Resolver Protocol](../skill-spec/10-skill-resolver-protocol-spec.md#protocol-interface-定义) |
| LOGIC `python_callable` | body `<action>` 顺序 + phase-local `actions/<name>.py` | PR G / round-18 清掉残留 golden/fixture/tests; 当前以 phase 内 action 链为准 |
| output_schema 独立插槽 | 系统内置 exit contract 末尾 inline output_schema | recency bias, 见 [Cognitive Template](../skill-spec/06-cognitive-template-spec.md#8-大插槽布局拓扑) |

本文件只描述 skill-compilation 需要实现的编译 / 装配边界, 不改 runtime 执行策略本身。

## UI/UX

N/A — 此模块为纯 backend Python library, 无 UI / 无前端调用面。

V0.3.0 后, 编译器对 Studio 的价值是返回可定位的结构化错误: phase 目录错、IO 字段接不上、`@reference:R1` 找不到、`target_skill` 未注册, 都必须在运行前被发现。Studio Canvas、Assets Panel 和 CompileErrorPanel 可以消费这些错误, 但 UI 渲染不属于本 feature。

## 前端逻辑

N/A — 此模块为纯 backend Python library, 无 React 逻辑。

Studio 编辑器的 `@-mention` 自动补全、subgraph asset panel 标红导入、Canvas 内 `<step>` 顺序展示, 都依赖编译器产出的 AST / issue / resolver 状态。编译模块只提供结构化结果, 不规定前端交互细节。

## 后端功能

### 1. AgentNodeAST 替换 SkillNodeAST (C2)

MVP0 MUST 把 V2.1 `SkillNodeAST` 替换为 V0.3.0 `AgentNodeAST`。`SKILL.md` 仍是物理文件名, 但作者不得在 frontmatter 写 `mode:`；Loader 由文件名推导并注入内部 `mode="agent"`。`mode: skill` 不再支持。

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `name` | string | 否 | phase 目录名 | `^[a-z][a-z0-9_-]*$` | `[F-v3-agent-name-invalid]` | phase / trace / Studio 展示名 |
| 内部 `mode` | `Literal["agent"]` | Loader 注入 | `agent` | 作者不得写 `mode:`; 写入即 unknown field | `[F-v3-agent-schema-unknown-field]` | 区分 Agent phase 与 LOGIC / SUBGRAPH |
| `role` | string | 是 | 无 | 从 body `<role>` 提取, trim 后非空 | `[F-v3-agent-role-missing]` | Agent 专业身份 |
| `goal` | string | 是 | 无 | 从 body `<goal>` 提取, trim 后非空 | `[F-v3-agent-goal-missing]` | Agent 任务目标 |
| `io` | `PhaseIOSchema` | 是 | 无 | `inputs` / `outputs` 均为 JSON Schema object | `[F-v3-agent-io-schema-invalid]` | StateMapper 切片与 finish_task 输出校验 |
| `tools` | list[string] | 否 | `[]` | 每项必须是 builtin 或 tool registry 已注册名 | `[F-v3-agent-tool-unknown]` | 暴露给 ReAct 循环主动调用 |
| `subagents` | list[AgentRegistryItem] | 否 | `[]` | 每项含 `name` / `target_skill` / `description` | `[F-v3-agent-subagent-invalid]` | `@subagent:NAME` 静态绑定域 |
| `subgraphs` | list[AgentRegistryItem] | 否 | `[]` | 每项含 `name` / `target_skill` / `description` | `[F-v3-agent-subgraph-invalid]` | `@subgraph:NAME` 静态绑定域 |
| `references` | list[ReferenceSpec] | 否 | `[]` | 每项含 `id` / `path` / `summary` | `[F-v3-resource-reference-invalid]` | reference 三机制入口 |
| `examples` | list[ExampleSpec] | 否 | `[]` | document example 只含 `id/path/summary`; inline example 放 body `<example id>` | `[F-v3-resource-example-invalid]` / `[F-v3-agent-example-invalid]` | examples 插槽与 runtime `read_example` |
| `max_iterations` | integer | 否 | `10` | `1 <= n <= 50` | `[F-v3-agent-max-iterations-invalid]` | Agent ReAct 上限 |

Loader MUST 把 body XML 解析成 5 类结构化字段: `<role>`, `<goal>`, `<step>`, `<protocol>`, `<example>`。这些字段进入 cognitive template 静态插槽, 不允许继续把整个 body 拼成 `system_prompt`。`<exit_contract>` 与 `<steps>` 壳标签必须 FATAL `[F-v3-agent-body-tag-unknown]`。字段标准见 [Agent Frontmatter 字段解析表](../skill-spec/05-agent-md-spec.md#frontmatter-字段解析表)。

### 2. 编译期 Schema 解析强制增强 (A7)

MVP0 MUST 要求每个 phase 节点声明 phase-level `io`。根 `GRAPH.md io` 只描述整图入口 / 出口, 不能替代节点自己的输入输出契约。

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `io.inputs` | JSON Schema object | 是 | 无 | 顶层 `type: object`; `required` 只能引用 `properties` | `[F-v3-agent-io-schema-invalid]` / `[F-v3-logic-io-schema-invalid]` / `[F-v3-subgraph-io-schema-invalid]` | 声明 phase 运行前需要哪些 state 字段 |
| `io.outputs` | JSON Schema object | 是 | 无 | 顶层 `type: object`; `properties` 必须存在 | 同上 | 声明 phase 运行后可写回哪些字段 |
| `required` | list[string] | 否 | `[]` | 每项必须是同 schema `properties` key | domain-specific `*-io-schema-invalid` | 静态数据流校验的输入需求 |
| `properties` | dict | 是 | 无 | 必须是 JSON Schema properties dict | domain-specific `*-io-schema-invalid` | 字段集合真相源 |

编译器在 phase AST 构建时就要完成 schema 解析, 后续 A8 数据流校验、StateMapper runtime 切片和 Agent output_schema inline 都读取同一份 AST, 避免各模块重复解析。

### 3. 编译期 Phase 物理布局与 DAG 校验 (NEW-1, C1, C4)

V0.3.0 的 phase 类型是三值: `agent`, `logic`, `subgraph`。物理目录必须是 `phases/<id>/{SKILL.md,LOGIC.md,SUBGRAPH.md}` 三选一, 且类型只由文件名推导。phase frontmatter 中的 `mode`、`schema_version`、`graph_skill_id`、`phase_id` 均禁止出现。

| 校验项 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `GRAPH.md` | file | 是 | 无 | skill root 下必须存在 | `[F-v3-graph-root-missing]` | 编译入口 |
| `phases:` | YAML list | 是 | 无 | 从 `GRAPH.md` frontmatter 读取 phase name 注册; 不含拓扑字段 | `[F-v3-graph-phases-missing]` / `[F-v3-graph-phase-id-invalid]` | phase 稳定注册表 |
| body `<phase>` | XML tag | 是 | 无 | `<phase depends_on="input|phase_a" output?>name</phase>`; name 必须与注册表和物理目录一致 | `[F-v3-graph-phase-id-invalid]` / `[F-v3-graph-phase-name-mismatch]` | DAG 节点拓扑 |
| phase name | string | 是 | 无 | `^[a-z][a-z0-9_-]*$`; frontmatter 内唯一; 有对应目录 | `[F-v3-graph-phase-id-invalid]` / `[F-v3-graph-phase-id-duplicate]` / `[F-v3-graph-phase-dir-missing]` | phase 稳定 id |
| body `depends_on` | string | 是 | 无 | 入口使用 `input`; 其他依赖必须引用已声明 phase; 支持空格/逗号多依赖 | `[F-v3-graph-depends-unknown]` | DAG 执行依赖 |
| node file | file | 是 | 无 | 每个 phase 目录恰好一个 `SKILL.md` / `LOGIC.md` / `SUBGRAPH.md` | `[F-v3-graph-phase-node-missing]` / `[F-v3-graph-phase-mode-ambiguous]` | phase 类型边界 |
| forbidden metadata | YAML key | 禁止 | — | phase frontmatter 不得出现 `mode` / `schema_version` / `graph_skill_id` / `phase_id` | domain-specific `*-schema-unknown-field` | 防止旧契约污染 |
| DAG | graph | 是 | 无 | 无环 + 无孤岛 + output 可确定 | `[F-v3-graph-phase-cycle]` / `[F-v3-graph-phase-island]` / `[F-v3-graph-output-phase-invalid]` | 运行前拓扑闭合 |

Loader MUST 同时提取 YAML `phases` 行号与 body `<phase>` token 行号, 用于 compile issue 定位。frontmatter `phases` 不承载 `depends_on`; body `<phase>` 是 DAG 真相源。

规范终点: [Physical Layout](../skill-spec/01-physical-layout.md#物理结构拓扑-directory-tree), [GRAPH phases 字段结构](../skill-spec/02-graph-md-spec.md#phases-字段结构), [DAG 校验算法](../skill-spec/02-graph-md-spec.md#dag-校验算法-编译期-loader-必跑)。

### 4. 根 IO inline 化与旧物理 IO 退役 (C3)

MVP0 MUST 删除对 `io/inputs.json`、`io/outputs.json`、`io_inputs_ref`、`io_outputs_ref` 的编译支持。根 IO 必须 inline 写在 `GRAPH.md` frontmatter。

| 字段 / 路径 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `GRAPH.md io.inputs` | JSON Schema object | 是 | 无 | 顶层 `type: object`; Draft 2020-12 schema 自身合法 | `[F-v3-graph-io-not-object]` / `[F-v3-graph-io-schema-invalid]` | graph invoke 入口契约 |
| `GRAPH.md io.outputs` | JSON Schema object | 是 | 无 | 同上 | `[F-v3-graph-io-not-object]` / `[F-v3-graph-io-schema-invalid]` | graph 最终输出契约 |
| `<root>/io/inputs.json` | deprecated file | 禁止 | — | 一旦发现即 FATAL | `[F-v3-graph-io-physical-file-deprecated]` | 防止 IO schema 与 GRAPH.md 漂移 |
| `<root>/io/outputs.json` | deprecated file | 禁止 | — | 一旦发现即 FATAL | `[F-v3-graph-io-physical-file-deprecated]` | 同上 |
| `io_inputs_ref` / `io_outputs_ref` | deprecated field | 禁止 | — | 任意 frontmatter 出现即 FATAL | `[F-v3-graph-io-physical-file-deprecated]` | 禁止间接引用旧路径 |

这项变更让编译器可以在一个 YAML AST 内同时定位 graph metadata、phase DAG 和根 IO, 避免跨文件 schema 漂移。规范终点见 [Root IO Schema](../skill-spec/02-graph-md-spec.md#根-io-契约-root-io-schema)。

PR-4 shipped 健壮性补强: V0.3.0 编译缓存现在以 v2 snapshot 保真 round-trip `subagents_by_phase` 与 `phase_tokens`, 并在 subgraph/subagent 递归编译链路上增加环检测和 20 层深度上限。这是对既有编译缓存与 `target_skill` 解析路径的可靠性收口, 不引入新的业务 feature 或作者可见 DSL 契约。

### 5. 静态数据流拓扑连通性校验 (A8)

MVP0 MUST 在运行前证明每个 phase 的 required input 都有来源。来源只能是根 `io.inputs.properties` 或直接 / 间接上游 phase 的 `io.outputs.properties`。

| 输入 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| root inputs keys | set[string] | 是 | 无 | 来自 `GRAPH.md io.inputs.properties` | `[F-v3-graph-io-schema-invalid]` | 初始可见字段集合 |
| phase required inputs | set[string] | 是 | `[]` | 来自 `phase.io.inputs.required` | `[F-v3-graph-dataflow-source-missing]` | 当前 phase 需要的字段 |
| upstream outputs keys | set[string] | 是 | `[]` | 只收集 DAG 上游 phase outputs | `[F-v3-graph-dataflow-source-missing]` | 数据来源证明 |
| dataflow issue payload | object | 是 | 无 | 必含 `phase_id`, `field_name`, `source_phase_candidates`, `path`, `line` | `[F-v3-graph-dataflow-source-missing]` | UI 可定位错误 |

算法:

1. 按 DAG 拓扑序遍历 phases。
2. 对每个 phase, 计算其可见字段集合: root inputs + 所有上游 outputs。
3. 校验 `phase.io.inputs.required` 是否全部在可见集合内。
4. 当前 phase 校验通过后, 把 `phase.io.outputs.properties` 加入后续可见集合。
5. 聚合全部缺失字段后统一报 compile issues。

这项校验是运行时 StateMapper 的前置证明。运行时仍要做真实输入校验, 但编译期必须先排除静态上明显接不上的图。

### 6. SUBGRAPH target_skill 解析与静态绑定 (C5)

`SUBGRAPH.md` 必须声明 `target_skill`, 编译器不再接受隐式路径或“后续再决定”的子图引用。

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `name` | string | 否 | phase 目录名 | `^[a-z][a-z0-9_-]*$` | `[F-v3-subgraph-name-invalid]` | 子图 phase 展示和 trace 名 |
| 内部 `mode` | `Literal["subgraph"]` | Loader 注入 | `subgraph` | 作者不写 `mode:` | `[F-v3-subgraph-schema-unknown-field]` | Loader 类型断言 |
| `target_skill` | string | 是 | 无 | 必须是 registry skill id, 不能是路径 | `[F-v3-subgraph-target-skill-invalid]` | 指向被调用 graph skill |
| `io.inputs` | JSON Schema object | 是 | 无 | object schema; 后续与子图根 inputs 1:1 对齐 | `[F-v3-subgraph-io-schema-invalid]` | 父图传参契约 |
| `io.outputs` | JSON Schema object | 是 | 无 | object schema; 后续与子图根 outputs 1:1 对齐 | `[F-v3-subgraph-io-schema-invalid]` | 子图返回契约 |

父图 Agent `SKILL.md` frontmatter 里的 `subgraphs:` 是 mention / prompt 引用 registry; phase-level `SUBGRAPH.md` 是 DAG 节点。两者都用 `target_skill`, 但一个用于 Agent 可达性, 一个用于图执行节点。规范终点见 [SUBGRAPH 类型推导与节点契约](../skill-spec/04-subgraph-md-spec.md#类型推导与节点契约)。

### 7. Cognitive Template 认知模板装配 (NEW-3)

MVP0 MUST 在编译后的装配阶段把 Agent AST 渲染成 V0.3.0 cognitive template。`output_schema` 必须合并到系统内置 exit contract 末尾, 不再作为独立中部插槽; 业务 `SKILL.md` body 不得自定义 `<exit_contract>`。

| 模板变量 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `{skill_role}` | string | 是 | 无 | 来自 `<role>`; 非空 | `[F-v3-agent-role-missing]` | Agent 身份 |
| `{skill_goal}` | string | 是 | 无 | 来自 `<goal>`; 非空 | `[F-v3-agent-goal-missing]` | Agent 目标 |
| `{skill_steps_splat}` | string | 否 | `""` | 所有 `<step id name>` 按 body 顺序展开 | `[F-v3-agent-step-invalid]` | 行动步骤 |
| `{skill_protocols_splat}` | string | 否 | `"无显式协议"` | 所有 `<protocol id>` 展开 | `[F-v3-agent-protocol-invalid]` | 判断依据 |
| `{reference_reader_subagent_output_markdown}` | markdown | 否 | 降级 warning + 原文摘录 | 来自 [Builtin Reference Reader Subagent](../skill-spec/09-builtin-modules-spec.md#builtin-reference-reader-subagent-签名) | `[F-v3-reference-reader-failed]` (WARN) | 领域知识修正 |
| `{inline_examples_splat}` | markdown | 否 | `"无内联示例"` | body `<example id>` content | `[F-v3-agent-example-invalid]` | 短示例直接注入 |
| `{document_examples_registry}` | markdown list | 否 | `"无扩展案例"` | examples `type:document` id + summary | `[F-v3-resource-example-invalid]` | 长案例按需读取目录 |
| `{skill_exit_contract_inline}` | markdown | 是 | 无 | 固定的内置字符串文本追加 `io.outputs` schema | `[F-v3-cognitive-output-schema-render-failed]` | 输出契约 recency bias |

说明: Agent body XML AST 与 cognitive template 容器分层处理。Loader 从 SKILL.md body 提取 5 类顶层业务标签, 装配器再填充到 cognitive template 的固定容器。编译器执行时以 [Agent Body XML 扁平化容器](../skill-spec/05-agent-md-spec.md#body-xml-扁平化容器) 和 [Cognitive Template 8 大插槽](../skill-spec/06-cognitive-template-spec.md#8-大插槽布局拓扑) 为准。

### 8. Mention 语法静态可达性校验 (NEW-4)

MVP0 MUST 在 Agent body XML 解析后扫描 `@type:NAME`, 并在编译期证明目标可达。

| Mention 类型 | 查询域 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `@subagent:NAME` | `frontmatter.subagents[].name` | 否 | — | NAME 必须存在 | `[F-v3-mention-target-not-found]` | Agent 子技能引用 |
| `@tool:NAME` | `frontmatter.tools[]` + framework builtin | 否 | — | tool 必须可暴露给当前 Agent | `[F-v3-mention-target-not-found]` / `[F-v3-agent-tool-unknown]` | ReAct tool 引用 |
| `@subgraph:NAME` | `frontmatter.subgraphs[].name` | 否 | — | NAME 存在且 `target_skill` 可 resolve | `[F-v3-mention-target-not-found]` / `[F-v3-skill-not-registered]` | Agent 引用子图资产 |
| `@protocol:P1` | body `<protocol id>` | 否 | — | id 必须存在 | `[F-v3-mention-target-not-found]` | 判断协议引用 |
| `@step:S1` | body `<step id>` | 否 | — | id 必须存在 | `[F-v3-mention-target-not-found]` | 步骤引用 |
| `@reference:R1` | `frontmatter.references[].id` | 否 | — | id 必须存在 | `[F-v3-mention-target-not-found]` | 显式资料依赖 |
| `@example:E1` | `frontmatter.examples[].id` | 否 | — | id 必须存在 | `[F-v3-mention-target-not-found]` | 显式案例依赖 |

全局 regex 与错误语义见 [@-Mention 语法规范](../skill-spec/07-mention-syntax-spec.md#--mention-语法规范)。编译器 MUST 把残缺 mention 视为 FATAL `[F-v3-mention-syntax-invalid]`, 不能当普通文本忽略。

### 9. 子图 IO 强映射校验 (NEW-5)

MVP0 MUST 在 resolver 找到子图后, 编译子图根 `GRAPH.md`, 并校验父图 SUBGRAPH phase IO 与子图根 IO 1:1 对齐。

| 校验项 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| parent `SUBGRAPH.md io.inputs.properties` | set[string] | 是 | 无 | 必须等于 child `GRAPH.md io.inputs.properties` | `[F-v3-subgraph-io-mismatch]` | 父图传参字段闭合 |
| parent `SUBGRAPH.md io.outputs.properties` | set[string] | 是 | 无 | 必须等于 child `GRAPH.md io.outputs.properties` | `[F-v3-subgraph-io-mismatch]` | 子图返回字段闭合 |
| `required` 集合 | set[string] | 是 | `[]` | 父子同向 required 必须相等 | `[F-v3-subgraph-io-mismatch]` | 防止调用方少传必填 |
| 同名字段 schema | JSON Schema fragment | 是 | 无 | 结构等价; description 差异只 WARN | `[F-v3-subgraph-io-schema-incompatible]` | 防止同名不同义 |

失败 payload 必须包含 `parent_phase_id`, `target_skill`, `direction`, `parent_fields`, `child_fields`。规范终点见 [SUBGRAPH IO 严格 1:1 映射校验](../skill-spec/04-subgraph-md-spec.md#io-严格-11-映射校验-strict-mapping)。

### 10. LOGIC Actions 一级寻址校验 (NEW-6)

MVP0 MUST 把 LOGIC action 寻址收敛到 phase-local action chain:

```text
<skill_root>/phases/<phase_id>/actions/<action_name>.py
```

| 字段 / 文件 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `LOGIC.md` body `<action>` | XML tag list | 是 | 无 | 非空; 每项 `^[a-z][a-z0-9_]*$`; 不含路径分隔符 | `[F-v3-logic-actions-empty]` / `[F-v3-logic-action-name-invalid]` | action 执行顺序 |
| `LOGIC.md actions` | list[string] | 否 | body 顺序 | 若写出必须与 body `<action>` 顺序一致 | `[F-v3-logic-actions-empty]` | 机器可读 action 声明 |
| `<phase>/actions/` | directory | actions 非空时必填 | 无 | 必须存在 | `[F-v3-logic-action-dir-missing]` | phase-local action 目录 |
| `<action_name>.py` | file | 是 | 无 | 必须存在且一级放置 | `[F-v3-logic-action-not-found]` | 具体 action 实现 |
| callable | callable | 是 | 无 | 导出与 action 同名函数并接受 context/ctx | `[F-v3-logic-action-entrypoint-missing]` | Engine 静默执行入口 |

LOGIC actions 不走 Agent tool runtime, 也不从 `python_callable` 寻址。Action 和 Tool 的边界见 [LOGIC Actions](../skill-spec/03-logic-md-spec.md#actions-注册寻址与执行契约)。

### 11. 资源预读取与 Builtin Subagent 触发机制 (NEW-7)

MVP0 MUST 在 Agent 装配阶段主动触发 builtin reference reader subagent, 并按 examples 双模式填充模板。

| 资源 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `references[].id` | string | 是 | 无 | `^[A-Z][A-Za-z0-9_-]*$`; 唯一 | `[F-v3-resource-reference-id-invalid]` | reader / mention / tool key |
| `references[].path` | string | 是 | 无 | skill root 内可读文件 | `[F-v3-resource-reference-path-invalid]` | 原始资料 |
| `references[].summary` | string | 是 | 无 | 非空 | `[F-v3-resource-reference-summary-missing]` | registry listing |
| builtin reader output | markdown | 否 | fallback excerpt | 失败 WARN, 不阻断 Agent run | `[F-v3-reference-reader-failed]` | 注入 `<knowledge_base>` |
| body `<example id>` content | string | 否 | 无 | 非空; 直接注入 | `[F-v3-agent-example-invalid]` | 短案例 |
| document example `path` | string | document example 必填 | 无 | 可读; 不预读 | `[F-v3-resource-example-path-invalid]` | runtime `read_example` |
| document example `summary` | string | document example 必填 | 无 | 非空 | `[F-v3-resource-example-summary-missing]` | 扩展案例目录 |

Reference 三机制必须并存: 装配期预读、runtime `read_reference`、body `@reference:R1`。Example 分为 body inline `<example id>` 直接注入 + frontmatter document example 按需读取, document example 不预读。规范终点见 [Reference 三机制生命周期](../skill-spec/08-resource-mechanisms-spec.md#reference-三机制生命周期) 与 [Builtin Reference Reader Subagent 签名](../skill-spec/09-builtin-modules-spec.md#builtin-reference-reader-subagent-签名)。

### 12. 编译期错误信息的规范化结构

MVP0 MUST 将编译错误归一到 `[F-v3-*]`, 并携带机器可读 payload。

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 业务作用 |
|---|---|---|---|---|---|
| `code` | string | 是 | 无 | `[F-v3-<domain>-<specific>]` | 稳定错误码 |
| `severity` | enum | 是 | 无 | `FATAL` 或 `WARN` | 决定是否中断编译 |
| `stage` | enum | 是 | 无 | `compile` / `assembly` | 定位生命周期 |
| `phase_id` | string | 否 | `null` | phase 相关错误必须提供 | Canvas 定位节点 |
| `field_path` | string | 否 | `null` | 字段错误建议提供 | 表单定位 |
| `source_path` | string | 是 | 无 | 真实文件路径 | 编辑器打开文件 |
| `line` | integer | 否 | `null` | 能从 YAML/XML AST 获取时提供 | 编辑器定位行 |
| `message` | string | 是 | 无 | 人类可读 | CLI / UI 展示 |
| `doc_link` | string | 是 | 无 | 指向 skill-spec 锚点 | 修复入口 |

错误码全集以 [Error Code Spec](../skill-spec/11-error-code-spec.md#错误码速查全表) 为准。

### 13. 缓存元数据补全与写失败降级

MVP0 SHOULD 保留历史 V2.1 audit 中对 cache 的两个修复方向, 但缓存内容已经按 V0.3.0 AST 作为当前目标。PR G 后不再保留 V2.1 codemod / `python_callable` / `context_mapping` 迁移路径。

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `raw` | dict | 是 | 无 | 保存 GRAPH / phase 原始解析片段 | `[F-v3-runtime-phase-failed]` fallback | Debug 与 Studio 展示 |
| `manifest` | dict | 是 | 无 | V0.3.0 GraphManifest JSON | `[F-v3-graph-schema-version-mismatch]` | 根图 metadata |
| `nodes` | list[dict] | 是 | 无 | Agent / Logic / Subgraph AST JSON 子集 | domain-specific schema errors | cache hit 后与冷编译等价 |
| `subagents_by_phase` | dict | 否 | `{}` | 保存 `parent_phase_id` / `name` / `target_skill` / `description` / `root` / `input_schema` / `expected_schema`; 不保存动态 `input_model` Python 类 | `[F-v3-resolver-path-invalid]` | cache hit 后恢复动态 subagent tools |
| `phase_tokens` | dict | 否 | `{}` | 保存 `PhaseTokenInfo` 及嵌套 `PhaseAttributeSpan` 的 raw text、offset、行号、attrs、attr spans | — | cache hit 后保持 GRAPH body token 定位信息 |

Cache 写失败只 WARN, 不得让成功编译变失败。HOME 不可写、CI 只读目录、权限异常时, `compile_skill(cache=True)` 返回内存中的 compiled object, 并记录 warning。

PR-4 后 cache key payload 含 `"format": "v2"`。旧 snapshot 会自动 miss 并冷编译, 避免旧格式缺少 `subagents_by_phase` / `phase_tokens` 时复水出残缺 `CompiledSkill`。

## API

### 1. 静态数据流校验入口

```python
def _validate_phase_io_dataflow(
    manifest: GraphManifest,
    nodes: list[PhaseDocument],
    root_inputs_schema: dict[str, Any],
) -> list[CompileIssue]:
    """Validate required phase inputs against root inputs and upstream outputs."""
```

该函数运行在所有 phase AST 构建完成之后、runtime graph 装配之前。它只做静态证明, 不执行 action/tool/LLM。

### 2. 扩充的 CompileResult 返回值契约

`compile_skill()` 可以继续返回 `CompiledSkill`, 但异常必须能携带 `list[CompileIssue]`。长期可演进成:

```python
class CompileResult(BaseModel):
    compiled: CompiledSkill | None
    issues: list[CompileIssue] = Field(default_factory=list)
```

关键要求不是类名, 而是错误不能只停留在字符串。Studio 需要 `code`, `phase_id`, `field_path`, `source_path`, `line`。

### 3. 子图寻址 DI 注入 (C6)

编译入口必须接受 SkillResolverProtocol:

```python
def compile_skill(
    root: Path,
    *,
    skill_resolver: SkillResolverProtocol,
    chat_model: Any | None = None,
    cache: bool = True,
) -> CompiledSkill:
    ...
```

`SkillResolverProtocol` 只能有一个方法:

```python
def resolve_skill(skill_id: str) -> Path: ...
```

| 参数 / 返回 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `skill_resolver` | SkillResolverProtocol | 含 SUBGRAPH / subagent 时必填 | 无 | 必须实现 `resolve_skill` 单方法 | `[F-v3-resolver-missing]` / `[F-v3-resolver-interface-invalid]` | 子图 / 子 Agent registry 寻址 |
| `skill_id` | string | 是 | 无 | `^[a-z][a-z0-9_-]*$` | `[F-v3-resolver-skill-id-invalid]` | resolver 查询 key |
| return Path | Path | 是 | 无 | 目录存在且含 `GRAPH.md` | `[F-v3-skill-not-registered]` / `[F-v3-resolver-path-invalid]` | 子 skill root |

V2.1 `_resolve_subagent_root` 相对路径扫描必须退役。编译期对子图 + subagent 寻址全量委托给 [SkillResolverProtocol](../skill-spec/10-skill-resolver-protocol-spec.md#protocol-interface-定义)。

## Data Model / State

### 1. CompiledSkill 缓存序列化边界

`CompiledSkill` 仍是编译产物核心 state, 但 V0.3.0 下它必须保存 graph_skill 的完整结构化 AST 和装配元数据。

缓存落盘不是单独的 Pydantic dehydrated model, 而是 `core/cache.py` 中 `_dehydrate_compiled_skill` / `_rehydrate_compiled_skill` 维护的普通 dict round-trip。`save_to_cache` 将 `CompiledSkill` 转为可 JSON 序列化的 snapshot, 再通过 `json.dumps(...)` 写盘; `load_from_cache` 用 `json.loads(...)` 读回 snapshot 后重建运行期对象。

当前 snapshot 顶层包含 `raw`、`manifest`、`nodes`、`subagents_by_phase`、`phase_tokens`。其中 `manifest` 通过 `GraphManifest.model_validate(...)` 复水, node AST 通过 `TypeAdapter(PhaseAST)` 复水, subagent 的动态 `input_model` 通过 `build_subagent_input_model(_subagent_input_model_name(parent_phase_id, name), input_schema)` 重建, 再调用 `_inject_subagent_tools` 重放 `call_subagent_*` 动态工具。snapshot 顶层没有额外的 `schema_version` 字段。

缓存格式版本由 cache key 承载: `compute_cache_key(...)` payload 含 `"format": "v2"`。旧 snapshot 会因 key 改变自动 miss 并冷编译, 避免旧格式缺少 `subagents_by_phase` / `phase_tokens` 时复水出残缺 `CompiledSkill`。递归编译状态由内部 `_loading_stack` 与 `_compilation_cache` 传递; 环路抛 `[F-v3-compile-recursion-cycle]`, 深度超过上限抛 `[F-v3-compile-depth-exceeded]`。

### 2. Node AST 数据结构边界扩展

```python
class PhaseIOSchema(BaseModel):
    inputs: dict[str, Any]
    outputs: dict[str, Any]


class AgentNodeAST(_BaseNodeAST):
    mode: Literal["agent"]
    io: PhaseIOSchema | None
    llm_role: str | None
    role: str
    goal: str
    steps: list[StepSpec] = Field(default_factory=list)
    protocols: list[ProtocolSpec] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    subagents: list[AgentRegistryItem] = Field(default_factory=list)
    subgraphs: list[AgentRegistryItem] = Field(default_factory=list)
    references: list[ReferenceSpec] = Field(default_factory=list)
    examples: list[ExampleSpec] = Field(default_factory=list)
    examples_inline: list[AgentExample] = Field(default_factory=list)
    validator: bool = False
    max_iterations: int = 10
```

`LogicNodeAST` 与 `SubgraphNodeAST` 也必须持有 `io: PhaseIOSchema`。这样 A8、SUBGRAPH IO 对齐、runtime StateMapper 都读同一份字段定义。

### 3. Agent Frontmatter 强类型反序列化 (NEW-2)

Loader MUST 把 `SKILL.md` 头部 YAML 强类型反序列化为 Agent config, body XML 只提供业务 prompt 原子块。

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `name` | string | 否 | phase 目录名 | `^[a-z][a-z0-9_-]*$` | `[F-v3-agent-name-invalid]` | phase 标识 |
| 内部 `mode` | `Literal["agent"]` | Loader 注入 | `agent` | 作者不写 `mode:` | `[F-v3-agent-schema-unknown-field]` | AST 类型断言 |
| `llm_role` | string | 否 | 继承 graph, 再无则 `analyst` | 必须注册 | `[F-v3-agent-llm-role-unknown]` | LLM routing |
| `io` | PhaseIOSchema | 是 | 无 | inputs / outputs object schema | `[F-v3-agent-io-schema-invalid]` | 输入输出契约 |
| `tools` | list[string] | 否 | `[]` | 已注册 tool | `[F-v3-agent-tool-unknown]` | ReAct tool set |
| `subagents` | list[AgentRegistryItem] | 否 | `[]` | name 唯一, target_skill 合法 | `[F-v3-agent-subagent-invalid]` | `@subagent` 域 |
| `subgraphs` | list[AgentRegistryItem] | 否 | `[]` | name 唯一, target_skill 合法 | `[F-v3-agent-subgraph-invalid]` | `@subgraph` 域 |
| `references` | list[ReferenceSpec] | 否 | `[]` | id/path/summary 完整 | `[F-v3-resource-reference-invalid]` | reference 三机制 |
| `examples` | list[ExampleSpec] | 否 | `[]` | document example `id/path/summary` 完整 | `[F-v3-resource-example-invalid]` | 文档案例 |
| `examples_inline` | list[AgentExample] | 否 | `[]` | 来自 body `<example id>`; id/content 非空 | `[F-v3-agent-example-invalid]` | 内联案例 |
| `validator` | boolean | 否 | `false` | 必须是 YAML boolean | Pydantic validation fatal | Agent 输出后置校验开关 |
| `max_iterations` | integer | 否 | `10` | 1..50 | `[F-v3-agent-max-iterations-invalid]` | ReAct 上限 |

字段表与 [Agent Frontmatter Spec](../skill-spec/05-agent-md-spec.md#frontmatter-字段解析表) 保持一致。

## Cross-feature interaction

### 1. 与 Studio trace-visualization 及 Canvas 的协同

编译错误 SHOULD 成为 Studio Canvas 的静态反馈源。A8 缺字段、DAG 环、phase 目录多选、mention 不可达、subgraph 未注册, 都应在 graph run 前转成可定位 issue。Studio 渲染方式另属前端 feature, 但本模块必须提供 `phase_id`、`field_path`、`source_path`、`line` 和 `doc_link`。

### 2. 对 State Contract 阶段过滤漏斗的直接支撑

state-and-io-contract 的 Runtime Input Funnel 和 phase-level sandbox 依赖本模块产出的 `io` AST。编译期证明字段来源, 运行期按同一 schema 切 `phase_input` 和 merge `phase_output`。运行侧规划见 [state-and-io-contract mvp0 alignment](../state-and-io-contract/mvp0-alignment.md#后端功能)。

### 3. 对 execution-runtime 装配层的输入

execution-runtime 不再自行解释 `SKILL.md` body。它接收已经解析好的 `AgentNodeAST`, 以及装配期生成的 cognitive template prompt、tool registry、subagent/subgraph resolved metadata。这样 runtime 只负责执行, 不重新做编译期 schema / mention / IO 判断。

## 与当前源码的对齐状态

round-18 / PR G 与后续的 PR-3 等节点后，本文件描述的 skill-compilation 主契约已经作为当前源码事实落地：

| 契约点 | 当前状态 |
|---|---|
| `GRAPH.md` 双轨拓扑 | frontmatter `phases` 注册 + body `<phase depends_on output>name</phase>` 拓扑均必需 |
| 版本号 | 只接受 `schema_version: "v0.3.0"` |
| phase 类型 | 文件名推导内部 `mode`; 作者 frontmatter 不写 `mode:` |
| `SkillNodeAST` 与 Persona 遗迹 | `SkillNodeAST` 已由 `AgentNodeAST` 替代；旧版的 Persona Schema 及相关的编译层死码簇（如 `build_graph_nodes`）已全数清理（PR-3） |
| `python_callable` | 已由 body `<action>` + phase-local actions 替代 |
| inline IO | 根 IO 与 phase IO 均来自 frontmatter; 物理 IO/ref 路径 fatal |
| Agent body | 只接受 `<role>` / `<goal>` / `<step>` / `<protocol>` / `<example>` 5 类业务标签 |
| Mention | Agent body `@type:NAME` 编译期静态可达校验 |
| SUBGRAPH | `target_skill` + resolver, 父子 IO properties 1:1 对齐 |
| 禁 phase metadata | `schema_version` / `graph_skill_id` / `phase_id` / `mode` 在 phase frontmatter 中按 unknown field 失败 |
| codemod / V2.1 validators | repo 内 codemod、`context_mapping`、5 个 dead validators 和隐藏死测试已由 PR G 删除 |
