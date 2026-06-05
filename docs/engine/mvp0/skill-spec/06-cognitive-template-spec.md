---
status: FROZEN
---
<!-- DO NOT EDIT: Golden principle contract baseline. Any divergence is strictly prohibited unless explicitly approved. -->

# Cognitive Template Spec

本文定义 V0.3.0 Cognitive Template 的 8 大插槽、静态 AST 映射和动态装配输入。它消费 [Agent SKILL.md](./05-agent-md-spec.md#body-xml-扁平化容器) 与 [Resource Mechanisms](./08-resource-mechanisms-spec.md#reference-三机制生命周期), 并进入 [Template 装配流](./12-compile-runtime-flow-spec.md#template-装配流-assembly-time-workflow)。

> ~~已迁移: cognitive 模板语法、8 大插槽布局、字段级 slot 定义 → [mvp1 skill-syntax §2.6.1-§2.6.2](../../mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#261-8-大插槽布局拓扑)。~~
> ~~已迁移: 静态组装 slot 输入映射(语法侧) → [mvp1 skill-syntax §2.6.3](../../mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#263-静态组装输入映射语法侧)。~~
> ~~机制归属: 动态渲染、reference-reader 预读、失败降级和 trace 记录不属于 skill-syntax,落点为 [mvp1 assemble](../../mvp1/02-mechanism/03-assemble/mvp1-alignment.md)。错误码全集见 [mvp1 compile-rules §4 cognitive/tool/runtime domain](../../mvp1/01-contract/03-compile-rules/mvp1-alignment.md#cognitive--tool--runtime-domain)。~~

## 8 大插槽布局拓扑

V0.3.0 Agent prompt 装配后的最终 XML 模板如下。`role` / `goal` / `step` / `protocol` / inline `example` 来自 SKILL.md body; 其余容器由 Engine 固定提供, 防止每个 skill 自己发明 prompt 结构。`exit_contract` 只在模板末尾 hardcode, 不从 SKILL.md 引用。

```xml
<role>
{skill_role}
</role>

{llm_role_prefix_section}

<goal>
{skill_goal}
</goal>

<thinking_style>
- 行动前先做简短策略思考：目标是什么、输入是否充分、输出标准是什么
- 区分"事实"与"推断"，不要把推断当作事实写入结果
- 对关键判断给出依据，不要无依据臆测
- 先规划后执行：明确步骤，再调用工具
- 思考用于规划；对外输出必须给出可执行结果，而不是只描述计划

建议步骤：
{skill_steps_splat}
</thinking_style>

<knowledge_base>
【垂直领域知识修正报告】(系统已为你提前查阅相关资料并提取核心差异)：
{aligned_concepts_and_critical_corrections_markdown}

如果上述提炼不足以支撑判断，或你需要阅读未被精炼的其他原始语料，
可自主调用 read_reference subagent 工具，传入 R-id 从完整 Reference 库获取。
当前可用 Reference 注册清单：{reference_registry_listing}
</knowledge_base>

<examples>
以下案例仅用于辅助理解业务逻辑，你的最终输出格式必须严格遵守 <exit_contract> 的 Schema，不要照搬案例结构。
【内联示范】：{skill_examples_inline}
【扩展案例库】(遇棘手边界可调用 read_example subagent)：{example_registry_listing}
</examples>

<ambiguity_feedback>
当你发现规则不清晰、输入不足或存在多种合理解释时，不要静默跳过：
1. 优先调用 log_ambiguity 记录问题、类型、你的决策和理由
2. 然后继续按"最保守且可解释"的方案执行
这不是阻塞流程的澄清请求，而是用于改进技能定义的反馈回路。
</ambiguity_feedback>

<protocol_citation>
做判断时必须标注协议依据，例如 [protocol:P1]。若无明确协议，需在自检说明写明并调用 log_ambiguity。
必须遵守的协议：
{skill_protocols_splat}
</protocol_citation>

<critical_reminders>
- 调用 finish_task 前，先检查关键工具返回值是否与预期一致；不一致先修复再 finish
- 对每个关键结论给出规则依据或数据依据
- 不确定规则边界时，先 log_ambiguity 再继续
- finish_task 必须提供 diagnostics_md（自检诊断）+ business_data_md（业务输出，遵循 output_schema）
- business_data_md 经 md_to_json 强校验，失败会收到错误反馈，按反馈修正后重新 finish_task
</critical_reminders>

<exit_contract>
回答必须调用 finish_task，输出符合下方 Schema 的结构化结果。business_data_md 遵循 output_schema 列业务字段；diagnostics_md 写自检诊断。
强制输出 Schema：
{output_schema}
</exit_contract>
```

字段级插槽定义:

| 插槽 | 类型 | 必填 | 默认值 | 来源 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `{skill_role}` | string | 是 | 无 | SKILL.md body `<role>` | `[F-v3-agent-role-missing]` | 给 LLM 明确专业身份 |
| `{llm_role_prefix_section}` | string | 否 | `""` | `llm_roles.yaml` 的 `system_prompt_prefix` | `[F-v3-agent-llm-role-unknown]` | 注入模型角色方法论 |
| `{skill_goal}` | string | 是 | 无 | SKILL.md body `<goal>` | `[F-v3-agent-goal-missing]` | 给 LLM 明确完成目标 |
| `{skill_steps_splat}` | string | 否 | `""` | SKILL.md body `<step id name>` | `[F-v3-cognitive-slot-render-failed]` | 把业务步骤放入 thinking_style |
| `{aligned_concepts_and_critical_corrections_markdown}` | markdown string | 否 | 降级警告 + 原文摘录 | knowledge_base 装载 subagent 输出 | `[F-v3-reference-reader-failed]` (WARN) | 预先注入领域知识修正报告 |
| `{reference_registry_listing}` | markdown list | 否 | `"无注册 Reference"` | frontmatter `references` | `[F-v3-resource-reference-invalid]` | 告诉 Agent 可按需读取哪些资料 |
| `{skill_examples_inline}` | string | 否 | `"无内联示例"` | SKILL.md body `<example id>` | `[F-v3-agent-example-invalid]` | 直接给短案例, 不消耗 tool 调用 |
| `{example_registry_listing}` | markdown list | 否 | `"无扩展案例"` | frontmatter document `examples` | `[F-v3-resource-example-invalid]` | 只列 id/summary, 鼓励按需读取 |
| `{skill_protocols_splat}` | string | 否 | `"无显式协议"` | SKILL.md body `<protocol id>` | `[F-v3-cognitive-slot-render-failed]` | 给判断提供可引用规则 |
| `{output_schema}` | JSON/YAML schema | 是 | 无 | 当前 Agent phase `io.outputs` | `[F-v3-cognitive-output-schema-render-failed]` | 约束 finish_task 输出 |

这里叫“8 大插槽”是指 8 个固定容器: `role`, `goal`, `thinking_style`, `knowledge_base`, `examples`, `ambiguity_feedback`, `protocol_citation`, `critical_reminders`; `exit_contract` 是末尾固定输出契约 block。

## 静态组装插槽解析

静态组装发生在 Loader 已完成 Agent AST 构建后, 不调用 LLM, 只把 body XML AST 变成模板片段。

| 模板变量 | 输入 AST | 转换规则 | 空值行为 | 错误码 |
|---|---|---|---|---|
| `{skill_role}` | `<role>` text | 保留正文 Markdown, trim 外层空白 | 不允许为空 | `[F-v3-agent-role-missing]` |
| `{skill_goal}` | `<goal>` text | 保留正文 Markdown, trim 外层空白 | 不允许为空 | `[F-v3-agent-goal-missing]` |
| `{skill_steps_splat}` | `<step id name>` list | 按 body 顺序直接拼入 thinking_style 建议步骤区域 | 允许为空字符串 | `[F-v3-agent-step-invalid]` |
| `{skill_protocols_splat}` | `<protocol id>` list | 按 body 顺序直接拼入 protocol_citation 区域 | 输出 `"无显式协议"` | `[F-v3-agent-protocol-invalid]` |
| `{skill_examples_inline}` | `<example id>` list | 按 body 顺序直接拼入 examples 内联示范区域 | 输出 `"无内联示例"` | `[F-v3-agent-example-invalid]` |

SKILL.md body 禁止 `<exit_contract>`。输出契约由模板末尾固定 `<exit_contract>` block 加 `{output_schema}` 生成。

## 动态装配插槽解析

动态装配发生在编译后、LangGraph 节点完成前。它会读取资源、构造 registry listing, 但仍不执行业务 Agent。

| 模板变量 | 类型 | 必填 | 默认值 | 生成阶段 | 校验 / 失败行为 | 业务作用 |
|---|---|---|---|---|---|---|
| `{aligned_concepts_and_critical_corrections_markdown}` | markdown | 否 | 降级警告 + 前 3000 token 原文摘录 | 装配期 | reader 失败 WARN `[F-v3-reference-reader-failed]`, 不阻塞 | 把 reference 先提炼成领域知识修正报告 |
| `{reference_registry_listing}` | markdown list | 否 | `"无注册 Reference"` | 装配期 | references schema 已在编译期校验 | 给 `read_reference` 提供 id/summary 目录 |
| `{example_registry_listing}` | markdown list | 否 | `"无扩展案例"` | 装配期 | document example path/summary 必须存在 | 列出可按需读取的大案例, 不预读 |
| `{output_schema}` | schema | 是 | 无 | 装配期 | 输出 schema 序列化失败 FATAL `[F-v3-cognitive-output-schema-render-failed]` | 约束 finish_task 输出 |

动态装配的边界:

- Reference 会被 builtin knowledge_base 装载 subagent 预读; document example 不预读。
- reader 失败只降级 knowledge_base, 不阻断 Agent run。
- registry listing 只暴露 id + summary, 不把 document example 原文塞进 prompt。
- 所有 slot render 都必须在 trace 中记录输入来源, 便于 Debug prompt 差异。

动态输入依赖 [Builtin Reference Reader Subagent 签名](./09-builtin-modules-spec.md#builtin-reference-reader-subagent-签名) 与 [Template 装配流](./12-compile-runtime-flow-spec.md#template-装配流-assembly-time-workflow)。
