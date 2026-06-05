---
status: FROZEN
---
<!-- DO NOT EDIT: Golden principle contract baseline. Any divergence is strictly prohibited unless explicitly approved. -->

# Resource Mechanisms Spec

> 🔖 **本文 = mvp0 留底,非 SSOT(mvp0 弃用中)。** 内容已分布到 mvp1(零 deferral):references/examples **声明语法** → `01-contract/02-skill-syntax` §2.5.1;**reference-reader 装配期机制** → `02-mechanism/03-assemble`;**`read_reference`/`read_example` 运行期工具** → `02-mechanism/05-run-inner/04-tools`。**机制细节深度**(三机制契约表 / 降级 / tool schema)待那两模块成段时纳入,当前留底参考。

本文定义 Reference 三机制、Example 双模式和 Frontmatter 挂载格式。它连接 [Agent SKILL.md](./05-agent-md-spec.md#frontmatter-字段解析表)、[Builtin Modules](./09-builtin-modules-spec.md#builtin-reference-reader-subagent-签名) 与 [Cognitive Template](./06-cognitive-template-spec.md#动态装配插槽解析)。

## Reference 三机制生命周期

Reference 是“领域知识资料”, V0.3.0 同时保留三条进入 Agent 的路径:

```text
frontmatter references
  ├─ 装配期 builtin reference reader subagent 必读
  │    └─ 输出 markdown → cognitive template <knowledge_base>
  ├─ runtime read_reference tool 按需读取
  │    └─ Agent 在 ReAct 中传 R-id 获取原文/摘要
  └─ body @reference:R1 显式引用
       └─ Loader 静态校验 + 给 LLM 标出步骤依赖
```

三机制字段级契约:

| 机制 | 输入 | 必填 | 默认值 | 校验规则 | 失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| 装配期 reader 必读 | `references[]` 全量 | 否 | 空列表 | 每个 reference path 可读; reader 失败可降级 | `[F-v3-resource-reference-invalid]` / `[F-v3-reference-reader-failed]` | 先把资料提炼进 `<knowledge_base>` |
| runtime `read_reference` | `reference_id` | 否 | 无 | id 必须存在于 `references[].id` | `[F-v3-resource-reference-not-found]` | Agent 遇到边界问题时读取完整资料 |
| body `@reference:R1` | XML body mention | 否 | 无 | R1 必须存在于 references registry | `[F-v3-mention-target-not-found]` | 在具体 step 中标明依赖哪份资料 |

三条路径并存的原因: 预读解决“模型不知道该看资料”的问题, tool 解决“预读摘要不够细”的问题, mention 解决“业务步骤到底依赖哪份资料”的可审计问题。

装配期预读位置见 [Template 装配流](./12-compile-runtime-flow-spec.md#template-装配流-assembly-time-workflow), 按需读取接口见 [Builtin Tools](./09-builtin-modules-spec.md#按需调取-tools-read_reference--read_example)。

## Example 处理逻辑

Example 是“案例”, 不等同于 Reference。V0.3.0 区分两类来源:

| 来源 | 写法 | 装配期行为 | runtime 行为 | 适用场景 |
|---|---|---|---|---|
| inline | SKILL.md body `<example id="E1">...</example>` | 直接 splat 到 `<examples>` 的 `【内联示范】` | 不需要 tool | 短小、稳定、强相关的判断边界 |
| document | frontmatter `examples: [{id, path, summary}]` | 只把 id + summary 列入 `【扩展案例库】`, 不预读原文 | Agent 可调用 `read_example(example_id)` | 长案例、低频边界、会挤占 prompt 的材料 |

字段级规则:

| 字段 | inline body example | document frontmatter example | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|
| `id` | 必填 | 必填 | `[F-v3-resource-example-invalid]` | `@example:E1` 和 `read_example` 的 key |
| 正文内容 | 必填 | 禁止 | `[F-v3-agent-example-invalid]` | 直接注入 prompt 的短示例 |
| `path` | 禁止 | 必填 | `[F-v3-resource-example-path-missing]` | runtime 按需读取的文档路径 |
| `summary` | 禁止 | 必填 | `[F-v3-resource-example-summary-missing]` | 给 LLM 决定是否读取的目录说明 |

Document example 不预读是刻意设计: Reference 是规则和知识, 需要先修正模型理解; Example 是案例库, 全量塞进 prompt 容易让模型照搬格式或污染输出。长案例只在 Agent 判断需要时通过 tool 拉取。

Example 引用校验需对齐 [@-Mention 语法规范](./07-mention-syntax-spec.md#--mention-语法规范)。

## Frontmatter 挂载格式

`references` 挂载格式:

```yaml
references:
  - id: R1
    path: ./references/architecture_guide.md
    summary: 影视改编剧本结构与特殊术语说明
```

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `id` | string | 是 | 无 | 正则 `^[A-Z][A-Za-z0-9_-]*$`; list 内唯一 | `[F-v3-resource-reference-id-invalid]` | mention/tool 的稳定 id |
| `path` | string | 是 | 无 | 必须是相对当前 skill root 的安全路径; 文件存在且可读; 不允许 `..` 逃逸 skill root | `[F-v3-resource-reference-path-invalid]` | 指向原始资料 |
| `summary` | string | 是 | 无 | trim 后非空, 建议一句话 | `[F-v3-resource-reference-summary-missing]` | 模板 registry listing 和 Studio tooltip |

`examples` frontmatter 只注册 document 扩展案例库。inline 案例必须写在 SKILL.md body `<example id>` 中。

```yaml
examples:
  - id: E2
    path: ./examples/long_crossover_example.md
    summary: 长篇交叉时间线与闪回混合场景的分析示范
```

```xml
<example id="E1">梦境中存在现实时间线流逝时, 判定为 B 类而不是 C 类.</example>
```

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `id` | string | 是 | 无 | 正则 `^[A-Z][A-Za-z0-9_-]*$`; list 内唯一 | `[F-v3-resource-example-id-invalid]` | mention/tool 的稳定 id |
| `path` | string | 是 | 无 | 文件存在且不逃逸 skill root | `[F-v3-resource-example-path-missing]` / `[F-v3-resource-example-path-invalid]` | runtime `read_example` 读取目标 |
| `summary` | string | 是 | 无 | trim 后非空 | `[F-v3-resource-example-summary-missing]` | 扩展案例库目录说明 |

挂载字段属于 [Agent Frontmatter 字段解析表](./05-agent-md-spec.md#frontmatter-字段解析表) 的一部分。
