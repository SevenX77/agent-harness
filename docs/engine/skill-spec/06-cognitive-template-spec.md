# Cognitive Template Spec

本文定义 V0.3.0 Cognitive Template 的 7 大插槽、静态 AST 映射和动态装配输入。它消费 [Agent SKILL.md](./05-agent-md-spec.md#body-xml-扁平化容器) 与 [Resource Mechanisms](./08-resource-mechanisms-spec.md#reference-三机制生命周期), 并进入 [Template 装配流](./12-compile-runtime-flow-spec.md#template-装配流-assembly-time-workflow)。

## 7 大插槽布局拓扑

V0.3.0 Agent prompt 装配后的最终 XML 模板如下。`role` / `goal` 来自业务 body; 其余容器由 Engine 固定提供, 防止每个 skill 自己发明 prompt 结构。

```xml
<role>
{skill_role}
</role>

<goal>
{skill_goal}
</goal>

<thinking_style>
- 行动前先做简短策略思考: 目标是什么, 输入是否充分, 输出标准是什么
- 区分"事实"与"推断", 不要把推断当作事实写入结果
- 对关键判断给出依据, 不要无依据臆测
- 先规划后执行: 明确步骤, 再调用工具
- 思考用于规划; 对外输出必须给出可执行结果, 而不是只描述计划
- 建议步骤:
    {skill_steps_splat}
</thinking_style>

<knowledge_base>
【垂直领域知识修正报告】(系统已提前查阅相关资料并提取核心差异):
{reference_reader_subagent_output_markdown}

如果上述提炼不足以支撑判断, 或你需要阅读未被精炼的其他原始语料,
你可以自主调用 `read_reference` subagent 工具, 并传入需要的 R-id 从完整 Reference 库中获取.
当前可用的 Reference 注册清单:
{reference_registry_listing}
</knowledge_base>

<examples>
以下是供你理解业务思路和处理风格的参考案例. 请注意: 这些案例仅用于辅助理解业务逻辑,
你的最终输出格式必须严格遵守 <exit_contract> 中的 Schema, 不要照搬案例的结构.

【内联示范】:
{inline_examples_splat}

【扩展案例库】:
系统还注册了以下更多复杂案例. 遇到棘手边界问题时, 你可以调用 `read_example` subagent 工具, 传入对应的 E-id 查阅:
{document_examples_registry}
</examples>

<ambiguity_feedback>
当你发现规则不清晰, 输入不足或存在多种合理解释时, 不要静默跳过:
1. 优先调用 log_ambiguity 记录问题, 类型, 你的决策和理由
2. 然后继续按"最保守且可解释"的方案执行
</ambiguity_feedback>

<protocol_citation>
做判断时必须标注协议依据, 例如: [protocol:P1]. 若无明确协议, 需在自检说明中写明并调用 log_ambiguity.

必须遵守的协议:
{skill_protocols_splat}
</protocol_citation>

<critical_reminders>
- 调用 finish_task 前, 先检查关键工具返回值是否与预期一致
- 对每个关键结论都给出规则依据或数据依据
- 当你不确定规则边界时, 先 log_ambiguity, 再继续执行
- finish_task 必须提供 diagnostics_md (自检诊断 Markdown) + business_data_md (业务输出 Markdown)
- business_data_md 会经系统强校验. 如果校验失败, 你会收到错误反馈消息 — 按反馈修正后重新调用 finish_task
</critical_reminders>

{skill_exit_contract_inline}
```

字段级插槽定义:

| 插槽 | 类型 | 必填 | 默认值 | 来源 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `{skill_role}` | string | 是 | 无 | SKILL.md `<role>` | `[F-v3-agent-role-missing]` | 给 LLM 明确专业身份 |
| `{skill_goal}` | string | 是 | 无 | SKILL.md `<goal>` | `[F-v3-agent-goal-missing]` | 给 LLM 明确完成目标 |
| `{skill_steps_splat}` | string | 否 | `""` | 所有 `<step id name>` AST | `[F-v3-cognitive-slot-render-failed]` | 把业务步骤放入 thinking_style, 引导先规划后执行 |
| `{reference_reader_subagent_output_markdown}` | markdown string | 否 | 降级警告 + 原文摘录 | builtin reference reader 输出 | `[F-v3-reference-reader-failed]` (WARN) | 预先注入领域知识修正报告 |
| `{reference_registry_listing}` | markdown list | 否 | `"无注册 Reference"` | frontmatter references | `[F-v3-resource-reference-invalid]` | 告诉 Agent 可按需读取哪些资料 |
| `{inline_examples_splat}` | string | 否 | `"无内联示例"` | examples `type:inline` | `[F-v3-resource-example-invalid]` | 直接给短案例, 不消耗 tool 调用 |
| `{document_examples_registry}` | markdown list | 否 | `"无扩展案例"` | examples `type:document` | `[F-v3-resource-example-invalid]` | 只列 id/summary, 鼓励按需读取 |
| `{skill_protocols_splat}` | string | 否 | `"无显式协议"` | 所有 `<protocol id>` AST | `[F-v3-cognitive-slot-render-failed]` | 给判断提供可引用规则 |
| `{skill_exit_contract_inline}` | xml block | 是 | 无 | `<exit_contract>` + `io.outputs` schema | `[F-v3-agent-exit-contract-missing]` | 用 recency bias 把输出契约放在 prompt 末尾 |

这里叫“7 大插槽”是指 7 个固定容器: `role`, `goal`, `thinking_style`, `knowledge_base`, `examples`, `ambiguity_feedback`, `protocol_citation`, `critical_reminders` 中 `role/goal` 是业务直填, 后 6 个是框架容器; `exit_contract` 不再作为独立中部插槽, 而是完整 inline 到末尾。

[Cognitive Template 内部插槽布局](./06-cognitive-template-spec.md#7-大插槽布局拓扑) 是所有 Agent prompt 装配的最终结构入口。

## 静态组装插槽解析

静态组装发生在 Loader 已完成 Agent AST 构建后, 不调用 LLM, 只把 body XML AST 变成模板片段。

| 模板变量 | 输入 AST | 转换规则 | 空值行为 | 错误码 |
|---|---|---|---|---|
| `{skill_role}` | `<role>` text | 保留正文 Markdown, trim 外层空白 | 不允许为空 | `[F-v3-agent-role-missing]` |
| `{skill_goal}` | `<goal>` text | 保留正文 Markdown, trim 外层空白 | 不允许为空 | `[F-v3-agent-goal-missing]` |
| `{skill_steps_splat}` | `<step id name>` list | 按 body 顺序展开为 `- [S1] name: body`; 内容缩进 4 空格 | 允许为空字符串 | `[F-v3-agent-step-invalid]` |
| `{skill_protocols_splat}` | `<protocol id>` list | 按 body 顺序展开为 `[protocol:P1]\n...` | 输出 `"无显式协议"` | `[F-v3-agent-protocol-invalid]` |
| `{skill_exit_contract_inline}` | `<exit_contract>` | 原 block 末尾附加 `output_schema` fenced YAML/JSON | 不允许为空 | `[F-v3-agent-exit-contract-missing]` |

`{skill_exit_contract_inline}` 必须追加 `io.outputs` schema, 不能依赖单独 output_schema 插槽。这是 V0.3.0 对 V2.1 exit contract 方案的推翻: 输出契约越靠近 prompt 末尾, 模型越不容易在 finish_task 前忘记结构要求。

静态输入来自 [Body XML 扁平化容器](./05-agent-md-spec.md#body-xml-扁平化容器) 与 [@-Mention 语法规范](./07-mention-syntax-spec.md#--mention-语法规范)。

## 动态装配插槽解析

动态装配发生在编译后、LangGraph 节点完成前。它会读取资源、构造 registry listing, 但仍不执行业务 Agent。

| 模板变量 | 类型 | 必填 | 默认值 | 生成阶段 | 校验 / 失败行为 | 业务作用 |
|---|---|---|---|---|---|---|
| `{reference_reader_subagent_output_markdown}` | markdown | 否 | 降级警告 + 前 3000 token 原文摘录 | 装配期 | reader 失败 WARN `[F-v3-reference-reader-failed]`, 不阻塞 | 把 reference 先提炼成领域知识修正报告 |
| `{reference_registry_listing}` | markdown list | 否 | `"无注册 Reference"` | 装配期 | references schema 已在编译期校验 | 给 `read_reference` 提供 id/summary 目录 |
| `{inline_examples_splat}` | markdown | 否 | `"无内联示例"` | 装配期 | inline content 必须非空 | 注入短小、稳定、强相关案例 |
| `{document_examples_registry}` | markdown list | 否 | `"无扩展案例"` | 装配期 | document path/summary 必须存在 | 列出可按需读取的大案例, 不预读 |
| `{skill_exit_contract_inline}` | XML + schema | 是 | 无 | 装配期 | 输出 schema 序列化失败 FATAL `[F-v3-cognitive-output-schema-render-failed]` | 约束 finish_task 输出 |

动态装配的边界:

- Reference 会被 builtin reader 预读; document example 不预读。
- reader 失败只降级 knowledge_base, 不阻断 Agent run。
- registry listing 只暴露 id + summary, 不把 document example 原文塞进 prompt。
- 所有 slot render 都必须在 trace 中记录输入来源, 便于 Debug prompt 差异。

动态输入依赖 [Builtin Reference Reader Subagent 签名](./09-builtin-modules-spec.md#builtin-reference-reader-subagent-签名) 与 [Template 装配流](./12-compile-runtime-flow-spec.md#template-装配流-assembly-time-workflow)。
