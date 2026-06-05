---
status: FROZEN
---
<!-- DO NOT EDIT: Golden principle contract baseline. Any divergence is strictly prohibited unless explicitly approved. -->

# Agent SKILL.md Spec

本文定义 Agent 节点 `SKILL.md` 的 Frontmatter、Body XML 扁平化规则和引用注入校验。它是 [Cognitive Template](./06-cognitive-template-spec.md#8-大插槽布局拓扑) 的主要静态输入, 也和 [Mention Syntax](./07-mention-syntax-spec.md#--mention-语法规范) 强关联。

> ~~已迁移: Frontmatter 字段解析表 → [mvp1 skill-syntax §2.5.1](../../mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#251-frontmatter-字段)。mvp1 delta:`subgraphs[]` 子项从 mvp0 `target_skill` 改为绝对 `path`;`subagents[]` 保持 `target_skill`。~~
> ~~已迁移: `subagents` / `subgraphs` 子项字段 → [mvp1 skill-syntax §2.5.2](../../mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#252-subagents--subgraphs-子项字段)。~~
> ~~已迁移: Body XML 5 标签、`<role>` / `<goal>` 必填、引用注入校验 → [mvp1 skill-syntax §2.5.3-§2.5.5](../../mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#253-body-xml-扁平化容器)。错误码全集不在 skill-syntax 重复,见 [mvp1 compile-rules §4](../../mvp1/01-contract/03-compile-rules/mvp1-alignment.md#agent-domain)。~~

## Frontmatter 字段解析表

Agent `SKILL.md` 是进入 LLM ReAct 循环的 phase 节点。节点类型由物理文件名 `SKILL.md` 唯一决定, Loader 注入内部 `mode="agent"`; 作者不写 `mode:`。frontmatter 只放框架装配配置, 业务 prompt 内容放在 body XML。未知字段编译期 FATAL `[F-v3-agent-schema-unknown-field]`。

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `name` | string | 是 | 无 | 正则 `^[a-z][a-z0-9_-]*$` | `[F-v3-agent-name-invalid]` | Trace、Studio 展示和 prompt 诊断名 |
| `llm_role` | string | 否 | 继承 `GRAPH.md llm_role`, 再无则 `"analyst"` | 必须存在于 `llm_roles.yaml` | `[F-v3-agent-llm-role-unknown]` | 路由 LLM tier / model policy, 不是 prompt 文案 |
| `validator` | boolean | 否 | `False` | 必须是 YAML boolean, 不能用 `"true"` 字符串 | Pydantic validation fatal | 结合 validator.py 控制 Agent 输出后置校验 |
| `io.inputs` | JSON Schema object | 是 | 无 | 顶层 `type: object`; `required` 只能引用 properties | `[F-v3-agent-io-schema-invalid]` | StateMapper 切给 Agent 的输入边界 |
| `io.outputs` | JSON Schema object | 是 | 无 | 顶层 `type: object` | `[F-v3-agent-io-schema-invalid]` | finish_task 输出强校验 schema |
| `tools` | list[string] | 否 | `[]` | 每项正则 `^[a-z][a-z0-9_]*$`; 必须是 builtin 或 tool registry 已注册名 | `[F-v3-agent-tool-unknown]` | 暴露给 Agent ReAct 循环主动调用 |
| `subagents` | list[object] | 否 | `[]` | 每项含 `name`, `target_skill`, `description`; `name` 供 `@subagent:NAME` 引用 | `[F-v3-agent-subagent-invalid]` | 注册可委托的 Agent 子技能 |
| `subgraphs` | list[object] | 否 | `[]` | 每项含 `name`, `target_skill`, `description`; target 走 SkillResolverProtocol | `[F-v3-agent-subgraph-invalid]` | 注册 Agent 可引用或说明的子图资产 |
| `references` | list[object] | 否 | `[]` | 每项含 `id`, `path`, `summary`; `id` 正则 `^[A-Z][A-Za-z0-9_-]*$` | `[F-v3-resource-reference-invalid]` | 装配期预读 + runtime `read_reference` 索引 |
| `examples` | list[object] | 否 | `[]` | 每项含 `id`, `path`, `summary`; 只注册 document 扩展案例库 | `[F-v3-resource-example-invalid]` | runtime `read_example` 索引 |
| `max_iterations` | integer | 否 | `10` | `1 <= max_iterations <= 50` | `[F-v3-agent-max-iterations-invalid]` | 限制 ReAct 循环最大轮数, 防止失控调用 |

`subagents` / `subgraphs` 子项字段:

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `name` | string | 是 | 无 | 正则 `^[a-z][a-z0-9_-]*$`; 同列表内唯一 | `[F-v3-agent-registry-name-invalid]` | Body 中 `@subagent:NAME` / `@subgraph:NAME` 的本地引用名 |
| `target_skill` | string | 是 | 无 | 正则 `^[a-z][a-z0-9_-]*$`; subgraph 必须可 resolve | `[F-v3-skill-not-registered]` | 指向 registry 中的 skill id |
| `description` | string | 是 | 无 | 非空 | `[F-v3-agent-registry-description-missing]` | 给 LLM 和 Studio 自动补全展示用途 |

[错误码速查表](./11-error-code-spec.md#agent-domain) 覆盖字段缺失、默认值和类型错误。

## Body XML 扁平化容器

`SKILL.md` frontmatter 后的 Markdown body 必须是 XML 片段集合, 顶层平铺, 不允许 `<steps>`、`<protocols>`、`<skill>` 这类壳节点。

允许的顶层标签只有 5 类:

| 标签 | 属性 | 数量 | 是否必填 | AST 去向 |
|---|---|---|---|---|
| `<role>` | 无 | 1 | 是 | `{skill_role}` |
| `<goal>` | 无 | 1 | 是 | `{skill_goal}` |
| `<step>` | `id`, `name` | 0..N | 否 | `{skill_steps_splat}` |
| `<protocol>` | `id` | 0..N | 否 | `{skill_protocols_splat}` 与 `@protocol` 可达域 |
| `<example>` | `id` | 0..N | 否 | `{skill_examples_inline}` |

解析行为:

1. Loader 把 body 当 XML fragment 解析, 可通过临时根节点包裹实现解析, 但临时根不进入 AST。
2. 顶层标签必须在允许列表内; 未知顶层标签 FATAL `[F-v3-agent-body-tag-unknown]`。遇到 `<exit_contract>` FATAL 报错, 因为 exit_contract 只在 cognitive template hardcode。
3. `<step>` 必须有 `id` 与 `name`; `<protocol>` / `<example>` 必须有 `id`; id 正则 `^[A-Z][A-Za-z0-9_-]*$`。
4. `<step>` / `<protocol>` / `<example>` 的 id 在各自命名空间内唯一。
5. 允许标签正文包含普通 Markdown 文本和 `@-mention`; 不允许嵌套另一个顶层业务标签。

禁止示例:

```xml
<steps>
  <step id="S1" name="parse">...</step>
</steps>
```

禁止 `<steps>` 壳的原因是 cognitive template 已经提供固定容器。SKILL.md body 只提供业务原子块, Loader 直接把 AST splat 到模板插槽, 不再猜测壳节点语义。

[Cognitive Template 内部插槽布局](./06-cognitive-template-spec.md#静态组装插槽解析) 引用 Body AST 到插槽的映射。

## 必须持有的业务核心标签

`<role>` 和 `<goal>` 是 Agent prompt 的业务身份与完成目标, 不是可选描述。缺任一项时 Loader 不能退化成通用 Agent, 必须 FATAL。

| 标签 | 必填 | 数量 | 内容规则 | 缺失错误码 | 业务作用 |
|---|---|---|---|---|---|
| `<role>` | 是 | 恰好 1 | 去空白后非空; 不允许只写占位文本 | `[F-v3-agent-role-missing]` | 决定 Agent 以什么专业身份判断 |
| `<goal>` | 是 | 恰好 1 | 去空白后非空; 必须描述可完成任务 | `[F-v3-agent-goal-missing]` | 决定 Agent 最终要产出什么 |

重复标签错误:

| 场景 | 错误码 |
|---|---|
| 多个 `<role>` | `[F-v3-agent-role-duplicate]` |
| 多个 `<goal>` | `[F-v3-agent-goal-duplicate]` |

缺失 `<role>` 或 `<goal>` 的 FATAL 行为见 [F-v3-agent 错误契约](./11-error-code-spec.md#agent-domain)。

## 引用注入校验 (Frontmatter ↔ Body)

Body 中出现的 `@type:NAME` 必须能在对应静态域内解析。Loader 不允许把无法解析的 mention 留给 LLM 自行理解。

| Mention | 可达域 | 校验规则 | 失败错误码 |
|---|---|---|---|
| `@reference:R1` | frontmatter `references[].id` | id 存在; path 在 skill 根内或合法相对路径 | `[F-v3-mention-target-not-found]` |
| `@example:E1` | body `<example id>` + frontmatter document `examples[].id` | id 存在; document example path/summary 合法 | `[F-v3-mention-target-not-found]` |
| `@subagent:producer_reviewer` | frontmatter `subagents[].name` | name 存在; target_skill 字段合法 | `[F-v3-mention-target-not-found]` |
| `@subgraph:review_graph` | frontmatter `subgraphs[].name` | name 存在; target_skill 可 resolve | `[F-v3-mention-target-not-found]` / `[F-v3-skill-not-registered]` |
| `@protocol:P1` | 本 body `<protocol id="P1">` | id 存在 | `[F-v3-mention-target-not-found]` |
| `@step:S1` | 本 body `<step id="S1">` | id 存在 | `[F-v3-mention-target-not-found]` |
| `@tool:store_segments` | frontmatter `tools[]` + framework builtin | tool 名存在 | `[F-v3-mention-target-not-found]` |

校验顺序建议:

1. 解析 body XML AST, 收集 step/protocol/inline example id。
2. 解析 frontmatter registry, 收集 tools/subagents/subgraphs/references/document examples。
3. 用 [Mention Syntax](./07-mention-syntax-spec.md#7-大分类静态可达性算法) 的统一 regex 扫描所有 body 文本节点。
4. 按类型查对应可达域, 聚合全部缺失项后一次报错。

Body 中的 `@reference` 与 `@example` 校验需对齐 [Mention Syntax](./07-mention-syntax-spec.md#--mention-语法规范) 和 [Resource Mechanisms](./08-resource-mechanisms-spec.md#frontmatter-挂载格式)。
