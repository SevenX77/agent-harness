---
status: FROZEN
---
<!-- DO NOT EDIT: Golden principle contract baseline. Any divergence is strictly prohibited unless explicitly approved. -->

> 🔖 **本文 = mvp0 迁移源档案，非当前 SSOT。** SUBGRAPH.md 类型推导、name/validator/io 字段已迁入 [`mvp1 skill-syntax`](../../mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#24-subgraphmd-其余语法契约path-之外)。旧 `target_skill` registry 寻址已按 mvp1 反转为绝对 `path`(见 §2.1),旧父子 IO 1:1 强校验已按 mvp1 反转为普通节点 blackboard slice/merge。mvp1 删除 mvp0 引用时，不得再把本文当权威。
<!-- 核对进度:已迁 3 块 / 未迁 0 块 / 2026-06-05 -->

~~# SUBGRAPH.md Spec~~ → ✅[已迁入并按 path/io 放宽反转](../../mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#24-subgraphmd-其余语法契约path-之外)

本文定义 `SUBGRAPH.md` 的 `target_skill` 寻址与父子图 IO 强校验。它连接 [SkillResolverProtocol](./10-skill-resolver-protocol-spec.md#protocol-interface-定义)、[Root IO Schema](./02-graph-md-spec.md#根-io-契约-root-io-schema) 和运行期 subgraph 调度。

~~## 类型推导与节点契约~~ → ✅[已迁入](../../mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#242-loader-拦截规则)

`SUBGRAPH.md` 表示当前 phase 委托另一个 graph skill 执行。节点类型由物理文件名 `SUBGRAPH.md` 唯一决定, Loader 注入内部 `mode="subgraph"`; 作者不写 `mode:`。它不是内联复制子图, 也不是相对路径 include; V0.3.0 的跨 skill 寻址统一走 registry + DI。

```yaml
---
name: producer_review
target_skill: producer_reviewer
io:
  inputs:
    type: object
    required: [segments]
    properties:
      segments: {type: array, items: {type: object}}
  outputs:
    type: object
    required: [review_score]
    properties:
      review_score: {type: number}
---
```

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `name` | string | 是 | 无 | 正则 `^[a-z][a-z0-9_-]*$` | `[F-v3-subgraph-name-invalid]` | Trace 与 Studio 展示名 |
| `validator` | boolean | 否 | `False` | 必须是 YAML boolean, 不能用 `"true"` 字符串 | Pydantic validation fatal | 结合 validator.py 控制阻断 |
| `target_skill` | string | 是 | 无 | 正则 `^[a-z][a-z0-9_-]*$`; 必须可被 SkillResolverProtocol 解析 | `[F-v3-subgraph-target-skill-invalid]` / `[F-v3-skill-not-registered]` | 指向被调用的 graph skill |
| `io.inputs` | JSON Schema object | 是 | 无 | 顶层 `type: object`; 字段名必须与子图 `GRAPH.md io.inputs.properties` 1:1 相等 | `[F-v3-subgraph-io-schema-invalid]` / `[F-v3-subgraph-io-mismatch]` | 声明父图传给子图入口的字段 |
| `io.outputs` | JSON Schema object | 是 | 无 | 顶层 `type: object`; 字段名必须与子图 `GRAPH.md io.outputs.properties` 1:1 相等 | `[F-v3-subgraph-io-schema-invalid]` / `[F-v3-subgraph-io-mismatch]` | 声明子图返回父图黑板的字段 |

Loader 拦截规则:

1. 扫描 `phases/<id>/` 时发现 `SUBGRAPH.md`, 节点类型锁定为 `subgraph`。
2. Loader 将内部 AST discriminator 注入为 `mode="subgraph"`。
3. 若同目录还存在 `LOGIC.md` 或 `SKILL.md`, 先由物理布局报 `[F-v3-graph-phase-mode-ambiguous]`。

[物理布局校验](./01-physical-layout.md#文件名类型推导-filename-type-derivation) 与 [错误码速查表](./11-error-code-spec.md#subgraph-domain) 覆盖 loader 拦截规则。

~~## target_skill 寻址规则~~ → ✅[已按绝对 path 反转迁入](../../mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#21-子图-path-引用契约mvp1-权威)

`target_skill` 只描述逻辑 skill id, 不描述磁盘路径。Engine 编译或装配子图时必须调用 DI 注入的单方法接口:

```python
resolved_root: Path = skill_resolver.resolve_skill(target_skill)
```

寻址流程:

1. Loader 读到 `target_skill: producer_reviewer`。
2. Engine 调 `SkillResolverProtocol.resolve_skill("producer_reviewer")`。
3. resolver 返回子 skill 根目录 Path。
4. Engine 在该目录读取 `GRAPH.md`, 并按完整 graph_skill 编译流程递归编译。
5. resolver 抛 `SkillResolutionError` 或返回不存在路径时, 归一为 `[F-v3-skill-not-registered]`。

禁止行为:

| 禁止写法 | 原因 | 错误码 |
|---|---|---|
| `target_skill: ./subskills/foo` | 绕过 Studio registry, 破坏跨 skill 导入流程 | `[F-v3-subgraph-target-skill-invalid]` |
| `target_skill_path` | V0.3.0 不暴露路径字段 | `[F-v3-subgraph-schema-unknown-field]` |
| `resolve_resource()` | round 2 已决议 SkillResolverProtocol 只有 `resolve_skill()` | `[F-v3-resolver-interface-invalid]` |

`target_skill` 必须通过 [SkillResolverProtocol Interface](./10-skill-resolver-protocol-spec.md#protocol-interface-定义) 寻址。Studio 的 subgraph asset panel 可以在同一失败码上渲染红色未注册入口并触发导入流程。

~~## IO 严格 1:1 映射校验 (Strict Mapping)~~ → ✅[已按普通节点 io 放宽反转迁入](../../mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#243-io-切片与合并规则mvp1-放宽)

父图 `SUBGRAPH.md io` 与子图 `GRAPH.md io` 必须做字段名 1:1 相等校验。这里的“相等”指 properties key set 完全一致, 不只是 required 字段覆盖。

```text
parent phase SUBGRAPH.md io.inputs.properties == child GRAPH.md io.inputs.properties
parent phase SUBGRAPH.md io.outputs.properties == child GRAPH.md io.outputs.properties
```

| 校验项 | 规则 | 失败错误码 |
|---|---|---|
| 输入字段集合 | 父 `io.inputs.properties.keys()` 与子 `GRAPH.md io.inputs.properties.keys()` 完全相等 | `[F-v3-subgraph-io-mismatch]` |
| 输出字段集合 | 父 `io.outputs.properties.keys()` 与子 `GRAPH.md io.outputs.properties.keys()` 完全相等 | `[F-v3-subgraph-io-mismatch]` |
| required 集合 | 父子同名 schema 的 `required` 集合必须相等 | `[F-v3-subgraph-io-mismatch]` |
| 字段 schema | 同名字段 schema 必须结构等价; description 差异不影响运行但 WARN | `[F-v3-subgraph-io-schema-incompatible]` |

为什么是严格 1:1: subgraph 调用像函数调用。父图 phase 的 `io.inputs` 是实参形状, 子图根 `io.inputs` 是形参形状; 如果允许自动改名或部分映射, 错误会延迟到运行期黑板缺字段, Debug 成本高。V0.3.0 先用强约束换可定位性。

失败报告必须包含:

- `parent_phase_id`
- `target_skill`
- `direction`: `inputs` 或 `outputs`
- `parent_fields`
- `child_fields`
- `missing_in_parent`
- `missing_in_child`

本节与 [State and IO Contract MVP0 Alignment](../state-and-io-contract/mvp0-alignment.md) 和 [编译期校验流](./12-compile-runtime-flow-spec.md#编译期校验流-compile-time-workflow) 对齐。
