---
status: FROZEN
---
<!-- DO NOT EDIT: Golden principle contract baseline. Any divergence is strictly prohibited unless explicitly approved. -->

> 🔖 **本文 = mvp0 迁移源档案，非当前 SSOT。** GRAPH.md 基础元数据、phase DAG、inline 根 IO 与静态数据流语法已迁入 [`mvp1 skill-syntax`](../../mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#22-graphmd-根语法契约)。mvp1 删除 mvp0 引用时，不得再把本文当权威。
<!-- 核对进度:已迁 4 块 / 未迁 0 块 / 2026-06-05 -->

~~# GRAPH.md Spec~~ → ✅[已迁入](../../mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#22-graphmd-根语法契约)

本文定义 graph_skill 根节点 `GRAPH.md` 的 Frontmatter 契约 / phase DAG 校验 / 根 IO Schema 入口。它依赖 [物理结构规范](./01-physical-layout.md), 并为 [运行时生命周期](./12-compile-runtime-flow-spec.md) 提供根拓扑。

~~## 基础元数据字段 (Metadata)~~ → ✅[已迁入](../../mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#221-基础元数据字段)

GRAPH.md frontmatter 必含以下基础字段, 未知字段编译期 FATAL `[F-v3-graph-schema-unknown-field]`:

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `name` | string | 是 | 无 | 正则 `^[a-z][a-z0-9_-]*$` (小写字母开头, 仅含 `[a-z0-9_-]`) | `[F-v3-graph-name-invalid]` | skill 唯一标识, 跟 SkillResolverProtocol `resolve_skill(name)` 输入对齐 |
| `schema_version` | string | 是 | 无 | 精确匹配 `"v0.3.0"` (字符串 quoted, 带 `v`) | `[F-v3-graph-schema-version-mismatch]` | 引擎版本断言, 不匹配时编译期立即 FATAL 避免错版本 graph 跑错版本 engine |
| `llm_role` | string | 否 | `"analyst"` | 必须是 `llm_roles.yaml` 内已注册角色 | `[F-v3-graph-llm-role-unknown]` | 整 graph 默认 LLM 角色, Agent phase frontmatter 可 override |
| `description` | string | 否 | `""` | 自由文本 | — | 文档用, 不参与执行 |

[错误码速查表](./11-error-code-spec.md) 覆盖根元数据缺失 / 版本不匹配 / 类型错误全集。

~~## phases 注册与 body 拓扑校验 (Phase Registration & DAG)~~ → ✅[已迁入](../../mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#222-phases-注册--body-dag-拓扑)

GRAPH.md 是双轨制: frontmatter `phases:` 只注册 phase 名字, body `<phase>` XML 才描述 DAG 拓扑。两者都必须存在, 且 phase name 必须一致。

~~### phases 字段结构~~ → ✅[已迁入](../../mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#222-phases-注册--body-dag-拓扑)

```yaml
schema_version: "v0.3.0"
phases: [extract_chapter, segment_text, producer_review]
```

```xml
<phase depends_on="input">extract_chapter</phase>
<phase depends_on="extract_chapter">segment_text</phase>
<phase depends_on="segment_text" output>producer_review</phase>
```

| 元素 | 类型 | 必填 | 校验规则 | 校验失败错误码 |
|---|---|---|---|---|
| frontmatter `phases` | list[string] | 是 | 每项正则 `^[a-z][a-z0-9_-]*$`; list 内不能重复; 必须有对应 `phases/<name>/` 物理目录 | `[F-v3-graph-phase-id-invalid]` / `[F-v3-graph-phase-id-duplicate]` / `[F-v3-graph-phase-dir-missing]` |
| body `<phase>` 文本 | string | 是 | 必须等于 frontmatter 注册名与物理目录名; 与目录名不一致时按 name mismatch 处理 | `[F-v3-graph-phase-name-mismatch]` |
| body `depends_on` | string | 是 | 第一个节点写 `input`; 其他节点引用已注册 phase; 多依赖用空格或逗号分隔 | `[F-v3-graph-depends-unknown]` |
| body `output` 属性 | flag | 否 | 标记结束节点, 可多个; 未标记时以无下游节点推导输出候选 | `[F-v3-graph-output-phase-invalid]` |

~~### DAG 校验算法 (编译期 Loader 必跑)~~ → ✅[已迁入](../../mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#222-phases-注册--body-dag-拓扑)

1. **唯一性**: frontmatter `phases` 列表内 name 不能重复 — 重复 → `[F-v3-graph-phase-id-duplicate]`
2. **双轨一致**: body `<phase>` name 集合必须等于 frontmatter `phases` 集合, 并等于 `phases/<name>/` 目录集合; 任一 body name 或注册名与物理目录不一致 → `[F-v3-graph-phase-name-mismatch]`
3. **依赖可达**: 每个 body `depends_on` 引用的 phase id 必须在 frontmatter `phases` 列表内存在; 入口节点依赖写保留字 `input` → `[F-v3-graph-depends-unknown]`
4. **无环**: DFS 拓扑排序, 检测到环 → `[F-v3-graph-phase-cycle]` (报具体环路径)
5. **无孤岛**: 从 `depends_on="input"` 入口节点不可达的 phase = 孤岛 → `[F-v3-graph-phase-island]`
6. **物理目录对齐**: 每个 phase name 必须有 `phases/<name>/{LOGIC,SUBGRAPH,SKILL}.md` 中**恰好一个文件** (3 选 1, 多选或缺失都 FATAL) → `[F-v3-graph-phase-dir-missing]` 或 `[F-v3-graph-phase-mode-ambiguous]`

[编译期校验流](./12-compile-runtime-flow-spec.md) 引用本节 DAG 构建与环检测结果。

~~## 根 IO 契约 (Root IO Schema)~~ → ✅[已迁入](../../mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#223-根-io-契约)

GRAPH.md frontmatter `io:` 必填, 含 `inputs` + `outputs` 两个子字段, 均为 JSON Schema 对象 (Draft 2020-12), **inline frontmatter, 禁止引用外部物理文件** (V0.3.0 退役 `io/inputs.json` / `io/outputs.json` 物理文件路径, 见 [物理布局](./01-physical-layout.md))。

~~### io 字段结构~~ → ✅[已迁入](../../mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#223-根-io-契约)

```yaml
io:
  inputs:
    type: object
    required: [chapter_path]
    properties:
      chapter_path:
        type: string
        description: 小说章节文件路径
  outputs:
    type: object
    required: [segments]
    properties:
      segments:
        type: array
        items: {type: object}
```

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 |
|---|---|---|---|---|---|
| `io.inputs` | JSON Schema object | 是 | 无 | 顶层 `type` 必须 `"object"`; 含 `properties`; `jsonschema` Draft 2020-12 解析通过 | `[F-v3-graph-io-not-object]` / `[F-v3-graph-io-schema-invalid]` |
| `io.outputs` | JSON Schema object | 是 | 无 | 同上 | 同上 |
| `io_inputs_ref` (V2.1 旧) | — | 禁止 | — | V0.3.0 编译期 FATAL | `[F-v3-graph-io-physical-file-deprecated]` |
| `io_outputs_ref` (V2.1 旧) | — | 禁止 | — | V0.3.0 编译期 FATAL | `[F-v3-graph-io-physical-file-deprecated]` |

~~### 静态数据流校验 (A8 补全 — 编译期)~~ → ✅[已迁入](../../mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#224-静态数据流校验)

Loader 把根 `io.inputs` 作为漏斗 schema 源 (Input Funnel, 见 [State and IO Contract MVP0 Alignment](../state-and-io-contract/mvp0-alignment.md)), 按 DAG 拓扑遍历每个 phase 的 `io.inputs` 必填字段, 校验它来自:

- 根 `io.inputs.properties` (整 graph 入口字段), 或
- 任一上游 phase (body `<phase depends_on>` 指向的 phase) 的 `io.outputs.properties`

来源缺失 → `[F-v3-graph-dataflow-source-missing]` (含 phase_id + field_name + 候选 source_phases 列表)。

~~[SUBGRAPH IO 严格映射](./04-subgraph-md-spec.md) 引用本节根 IO 契约 — 子图作为 phase 调用时, 子图根 io.inputs 跟父图 phase 声明的 io.inputs 必须 1:1 名字对齐。~~ → ✅[已按 mvp1 子图 io 放宽反转](../../mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#243-io-切片与合并规则mvp1-放宽)
