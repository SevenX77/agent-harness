# Physical Layout Spec

本文规定 graph_skill 的物理目录结构、文件命名和 mode/path 双向校验边界, 是 Loader 开始解析前的第一层约束。错误处理需和 [错误码契约](./11-error-code-spec.md#错误码速查全表) 对齐, 后续编译顺序见 [Compile Runtime Flow](./12-compile-runtime-flow-spec.md#编译期校验流-compile-time-workflow)。

## 物理结构拓扑 (Directory Tree)

V0.3.0 graph_skill 根目录必须以 `GRAPH.md` 为入口, phase 节点统一放在 `phases/<id>/` 下。配套资产目录放在 skill root, 供全 skill 共享。

```text
<skill_root>/
  GRAPH.md
  phases/
    <phase_id>/
      LOGIC.md | SUBGRAPH.md | SKILL.md
      validator.py              # only for LOGIC.md with validator: true
  actions/                      # optional, skill-global Logic actions
    <action_name>.py
  references/                   # optional, documents registered by SKILL.md references
    *.md
  examples/                     # optional, document examples registered by SKILL.md examples
    *.md
  subskills/                    # optional local authoring scratch, not resolver source of truth
```

物理目录字段级规则:

| 路径 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `<skill_root>/GRAPH.md` | file | 是 | 无 | 必须存在且文件名大小写精确匹配 | `[F-v3-graph-root-missing]` | graph_skill 唯一入口, 声明根 metadata / DAG / IO |
| `<skill_root>/phases/` | directory | 是 | 无 | 必须存在且为目录 | `[F-v3-graph-phases-dir-missing]` | 承载所有 phase 节点 |
| `<skill_root>/phases/<id>/` | directory | 是 | 无 | `<id>` 必须出现在 `GRAPH.md phases[].id`; 命名匹配 `^[a-z][a-z0-9_-]*$` | `[F-v3-graph-phase-dir-missing]` / `[F-v3-graph-phase-id-invalid]` | phase 的物理边界 |
| `LOGIC.md` / `SUBGRAPH.md` / `SKILL.md` | file | 每个 phase 必须三选一 | 无 | 每个 phase 目录内恰好一个节点文件; 多个或缺失 FATAL | `[F-v3-graph-phase-mode-ambiguous]` / `[F-v3-graph-phase-node-missing]` | 决定 phase 节点类型 |
| `<skill_root>/actions/` | directory | 当任一 LOGIC 声明 `actions` 时必填 | 无 | action 文件只能一级放置 | `[F-v3-logic-action-dir-missing]` | 存放 Logic 节点静默执行的 Python action |
| `<skill_root>/references/` | directory | 否 | 无 | 被 `references[].path` 引用时路径必须存在且不逃逸 root | `[F-v3-resource-reference-path-invalid]` | 存放领域资料 |
| `<skill_root>/examples/` | directory | 否 | 无 | 被 document example 引用时路径必须存在且不逃逸 root | `[F-v3-resource-example-path-invalid]` | 存放长示例文档 |
| `<skill_root>/subskills/` | directory | 否 | 无 | 不参与 `target_skill` 解析 | — | 可作为作者本地素材区, 不是 V0.3.0 resolver 真相源 |

Loader 必须从根向下校验, 先确认物理结构, 再解析 frontmatter。这样可以把“文件放错位置”和“字段写错”分开报错。

[编译期校验流](./12-compile-runtime-flow-spec.md#编译期校验流-compile-time-workflow) 引用本节目录拓扑。

## 文件命名规约 (Naming Conventions)

V0.3.0 节点文件名强制全大写 + `.md` 后缀:

| 文件 | 允许位置 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `GRAPH.md` | `<skill_root>/` | 是 | 无 | 大小写精确; 不接受 `graph.md` / `Graph.md` | `[F-v3-graph-root-missing]` | 根入口 |
| `LOGIC.md` | `phases/<id>/` | 三选一 | 无 | 大小写精确; frontmatter `mode: logic` | `[F-v3-graph-mode-path-mismatch]` | 确定性 action 节点 |
| `SUBGRAPH.md` | `phases/<id>/` | 三选一 | 无 | 大小写精确; frontmatter `mode: subgraph` | `[F-v3-graph-mode-path-mismatch]` | 子 graph 调用节点 |
| `SKILL.md` | `phases/<id>/` | 三选一 | 无 | 大小写精确; frontmatter `mode: agent` | `[F-v3-graph-mode-path-mismatch]` | LLM Agent 节点 |

phase 目录名规范:

| 项 | 规则 | 错误码 |
|---|---|---|
| 正则 | `^[a-z][a-z0-9_-]*$` | `[F-v3-graph-phase-id-invalid]` |
| 与 GRAPH 对齐 | 目录名必须等于 `GRAPH.md phases[].id` | `[F-v3-graph-phase-dir-missing]` |
| 大小写 | 只允许小写; 不做大小写自动归一 | `[F-v3-graph-phase-id-invalid]` |
| 空目录 | 不允许 phase 目录没有节点文件 | `[F-v3-graph-phase-node-missing]` |

[GRAPH.md 字段契约](./02-graph-md-spec.md#phases-列表与拓扑校验-phase-dag)、[LOGIC.md 字段契约](./03-logic-md-spec.md#frontmatter-字段解析表-schema--validation)、[SUBGRAPH.md 字段契约](./04-subgraph-md-spec.md#mode-声明与类型断言)、[SKILL.md 字段契约](./05-agent-md-spec.md#frontmatter-字段解析表) 引用本节命名规则。

## mode↔路径双向校验 (Mode-Path Cross Validation)

文件名和 frontmatter `mode` 是双向断言。Loader 不能只信路径, 也不能只信 frontmatter。

| 物理文件 | 期望 frontmatter | 路径 → mode 校验 | mode → 路径校验 | 失败错误码 |
|---|---|---|---|---|
| `<root>/GRAPH.md` | 无 phase `mode`; 必含 `schema_version` | 根文件只能作为 graph root | `GRAPH.md` 不允许放在 phase 目录 | `[F-v3-graph-mode-path-mismatch]` |
| `phases/<id>/LOGIC.md` | `mode: logic` | 文件名锁定 Logic AST | `mode: logic` 必须来自 `LOGIC.md` | `[F-v3-graph-mode-path-mismatch]` |
| `phases/<id>/SUBGRAPH.md` | `mode: subgraph` | 文件名锁定 Subgraph AST | `mode: subgraph` 必须来自 `SUBGRAPH.md` | `[F-v3-graph-mode-path-mismatch]` |
| `phases/<id>/SKILL.md` | `mode: agent` | 文件名锁定 Agent AST | `mode: agent` 必须来自 `SKILL.md` | `[F-v3-graph-mode-path-mismatch]` |

四类 phase 节点的校验方向:

| 节点类型 | 方向 A: 路径决定候选类型 | 方向 B: frontmatter 反证路径 | 业务意义 |
|---|---|---|---|
| GRAPH | root `GRAPH.md` 才能解析根 metadata | phase 目录不得声明 graph root | 防止嵌套根被误读 |
| LOGIC | `LOGIC.md` 才会加载 actions/validator | `mode` 必须是 `logic` | 防止 action 节点进入 Agent runtime |
| SUBGRAPH | `SUBGRAPH.md` 才会读取 `target_skill` | `mode` 必须是 `subgraph` | 防止 registry 寻址被跳过 |
| Agent | `SKILL.md` 才会解析 body XML/template | `mode` 必须是 `agent` | 防止 prompt 节点被静默执行 |

双向校验失败均 FATAL, 不做自动修正。文件名是给 Loader 的硬边界, `mode` 是给 AST 的硬边界; 两者不一致说明作者意图不可信。

[F-v3-graph-mode-path-mismatch 错误契约](./11-error-code-spec.md#graph-domain) 覆盖本节 FATAL 行为。

## IO 物理文件退役声明 (Inline IO Deprecation)

V2.1 允许或曾经使用的物理 IO 文件和引用字段在 V0.3.0 全部退役:

| 旧入口 | 状态 | 替代写法 | 校验失败错误码 | 业务原因 |
|---|---|---|---|---|
| `<root>/io/inputs.json` | 禁止 | `GRAPH.md frontmatter io.inputs` | `[F-v3-graph-io-physical-file-deprecated]` | 根 IO 必须随 graph metadata 一起版本化和审阅 |
| `<root>/io/outputs.json` | 禁止 | `GRAPH.md frontmatter io.outputs` | `[F-v3-graph-io-physical-file-deprecated]` | 避免 schema 与 DAG 分离后漂移 |
| `io_inputs_ref` | 禁止 | inline `io.inputs` dict | `[F-v3-graph-io-physical-file-deprecated]` | 禁止间接引用 |
| `io_outputs_ref` | 禁止 | inline `io.outputs` dict | `[F-v3-graph-io-physical-file-deprecated]` | 禁止间接引用 |

Loader 处理规则:

1. 若发现 `<root>/io/inputs.json` 或 `<root>/io/outputs.json`, 编译期 FATAL。
2. 若任意 frontmatter 出现 `io_inputs_ref` / `io_outputs_ref`, 编译期 FATAL。
3. `GRAPH.md`, `LOGIC.md`, `SUBGRAPH.md`, `SKILL.md` 的 `io` 均使用 inline YAML dict, 并按 JSON Schema object 校验。

[Root IO Schema](./02-graph-md-spec.md#根-io-契约-root-io-schema) 与 [State and IO Contract MVP0 Alignment](../state-and-io-contract/mvp0-alignment.md) 说明 inline `io:` dict 的收敛边界。
