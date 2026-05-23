# GRAPH.md Spec

本文定义 graph_skill 根节点 `GRAPH.md` 的 Frontmatter 契约 / phase DAG 校验 / 根 IO Schema 入口。它依赖 [物理结构规范](./01-physical-layout.md), 并为 [运行时生命周期](./12-compile-runtime-flow-spec.md) 提供根拓扑。

## 基础元数据字段 (Metadata)

GRAPH.md frontmatter 必含以下基础字段, 未知字段编译期 FATAL `[F-v3-graph-schema-unknown-field]`:

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `name` | string | 是 | 无 | 正则 `^[a-z][a-z0-9_-]*$` (小写字母开头, 仅含 `[a-z0-9_-]`) | `[F-v3-graph-name-invalid]` | skill 唯一标识, 跟 SkillResolverProtocol `resolve_skill(name)` 输入对齐 |
| `schema_version` | string | 是 | 无 | 精确匹配 `"0.3.0"` (字符串 quoted) | `[F-v3-graph-schema-version-mismatch]` | 引擎版本断言, 不匹配时编译期立即 FATAL 避免错版本 graph 跑错版本 engine |
| `llm_role` | string | 否 | `"analyst"` | 必须是 `llm_roles.yaml` 内已注册角色 | `[F-v3-graph-llm-role-unknown]` | 整 graph 默认 LLM 角色, Agent phase frontmatter 可 override |
| `description` | string | 否 | `""` | 自由文本 | — | 文档用, 不参与执行 |

[错误码速查表](./11-error-code-spec.md) 覆盖根元数据缺失 / 版本不匹配 / 类型错误全集。

## phases 列表与拓扑校验 (Phase DAG)

GRAPH.md frontmatter `phases:` 是 yaml list, 每条 phase 描述一个执行节点。Loader 解析后构建 DAG, 编译期做拓扑校验。

### phases 字段结构

```yaml
phases:
  - id: extract_chapter
    depends_on: []
  - id: segment_text
    depends_on: [extract_chapter]
  - id: producer_review
    depends_on: [segment_text]
```

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 |
|---|---|---|---|---|---|
| `id` | string | 是 | 无 | 正则 `^[a-z][a-z0-9_-]*$` + 必须有对应 `phases/<id>/` 物理目录 | `[F-v3-graph-phase-id-invalid]` / `[F-v3-graph-phase-dir-missing]` |
| `depends_on` | list[string] | 是 | `[]` | 每项必须是 `phases:` 列表内已声明的另一 phase id | `[F-v3-graph-depends-unknown]` |

### DAG 校验算法 (编译期 Loader 必跑)

1. **唯一性**: phases 列表内 `id` 不能重复 — 重复 → `[F-v3-graph-phase-id-duplicate]`
2. **依赖可达**: 每个 `depends_on` 引用的 phase id 必须在 phases 列表内存在 → `[F-v3-graph-depends-unknown]`
3. **无环**: DFS 拓扑排序, 检测到环 → `[F-v3-graph-phase-cycle]` (报具体环路径)
4. **无孤岛**: 跟入口节点 (`depends_on: []`) 不可达的 phase = 孤岛 → `[F-v3-graph-phase-island]`
5. **物理目录对齐**: 每个 `id` 必须有 `phases/<id>/{LOGIC,SUBGRAPH,SKILL}.md` 中**恰好一个文件** (3 选 1, 多选或缺失都 FATAL) → `[F-v3-graph-phase-dir-missing]` 或 `[F-v3-graph-phase-mode-ambiguous]`

[编译期校验流](./12-compile-runtime-flow-spec.md) 引用本节 DAG 构建与环检测结果。

## 根 IO 契约 (Root IO Schema)

GRAPH.md frontmatter `io:` 必填, 含 `inputs` + `outputs` 两个子字段, 均为 JSON Schema 对象 (Draft 2020-12), **inline frontmatter, 禁止引用外部物理文件** (V0.3.0 退役 `io/inputs.json` / `io/outputs.json` 物理文件路径, 见 [物理布局](./01-physical-layout.md))。

### io 字段结构

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

### 静态数据流校验 (A8 补全 — 编译期)

Loader 把根 `io.inputs` 作为漏斗 schema 源 (Input Funnel, 见 [State and IO Contract MVP0 Alignment](../state-and-io-contract/mvp0-alignment.md)), 按 DAG 拓扑遍历每个 phase 的 `io.inputs` 必填字段, 校验它来自:

- 根 `io.inputs.properties` (整 graph 入口字段), 或
- 任一上游 phase (`depends_on` 之一) 的 `io.outputs.properties`

来源缺失 → `[F-v3-graph-dataflow-source-missing]` (含 phase_id + field_name + 候选 source_phases 列表)。

[SUBGRAPH IO 严格映射](./04-subgraph-md-spec.md) 引用本节根 IO 契约 — 子图作为 phase 调用时, 子图根 io.inputs 跟父图 phase 声明的 io.inputs 必须 1:1 名字对齐。
