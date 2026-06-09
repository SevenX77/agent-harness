---
status: FROZEN
---
<!-- DO NOT EDIT: Golden principle contract baseline. Any divergence is strictly prohibited unless explicitly approved. -->

# Builtin Modules Spec

> 🔖 **本文 = mvp0 留底,非 SSOT(mvp0 弃用中)。** 内容去向(mvp1 零 deferral):**reference-reader subagent 签名 + 优雅降级** → `02-mechanism/03-assemble`;**`read_reference`/`read_example` 工具** → `02-mechanism/05-run-inner/04-tools`。**I/O 签名表 / 降级矩阵 / tool param schema 的完整细节** 待那两模块成段时纳入,当前留底参考。

本文定义 builtin reference reader subagent、降级策略和 `read_reference` / `read_example` tools 的 I/O 签名骨架。它支撑 [Resource Mechanisms](./08-resource-mechanisms-spec.md#reference-三机制生命周期) 与 [Cognitive Template 动态装配](./06-cognitive-template-spec.md#动态装配插槽解析)。

## Builtin Reference Reader Subagent 签名

物理位置:

```text
packages/graph-agent/src/graph_agent/core/builtin_subagents/reference_reader.py
```

该模块是 Engine builtin, 不属于用户 skill 的 `actions/` 或 `tools/` 目录。它在 Template 装配期被 Engine 调用, 用于把 `references[]` 原始资料提炼成 `<knowledge_base>` 中的“垂直领域知识修正报告”。

输入 JSON 契约:

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `skill_id` | string | 是 | 无 | 当前 graph skill id | `[F-v3-reference-reader-input-invalid]` | trace 定位来源 skill |
| `phase_id` | string | 是 | 无 | 当前 Agent phase id | `[F-v3-reference-reader-input-invalid]` | trace 定位来源 phase |
| `references` | list[object] | 是 | `[]` | 每项含 `id`, `path`, `summary`, 且 path 可读 | `[F-v3-reference-reader-input-invalid]` | reader 需要处理的资料集合 |
| `max_output_tokens` | integer | 否 | `3000` | `500 <= n <= 12000` | `[F-v3-reference-reader-input-invalid]` | 控制 knowledge_base 注入体积 |
| `language` | string | 否 | `"zh"` | 仅影响报告语言, 不影响资料读取 | — | 让报告与 skill 文档语言一致 |

输出 JSON 契约:

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `markdown` | string | 是 | 无 | 非空 Markdown | `[F-v3-reference-reader-output-invalid]` | 注入 `{aligned_concepts_and_critical_corrections_markdown}` |
| `used_reference_ids` | list[string] | 是 | `[]` | 必须是输入 references id 子集 | `[F-v3-reference-reader-output-invalid]` | trace 记录哪些资料被摘要 |
| `warnings` | list[string] | 否 | `[]` | 字符串列表 | — | 记录截断、读取失败等非阻塞问题 |

专用 System Prompt 草案 `[a2-review-needed]`:

```text
你是 graph_skill 的内置资料阅读子代理。你的任务不是执行业务目标, 而是阅读已注册 Reference,
提炼会影响当前 Agent 判断的领域知识、术语定义、边界条件和容易误判的规则。

输出 Markdown, 必须包含:
1. 核心规则摘要
2. 与常识或模型默认理解可能冲突的修正点
3. 关键术语表
4. 需要 Agent 在判断时主动引用的 reference id

不要替 Agent 完成业务输出, 不要生成最终 JSON, 不要调用 finish_task。
```

本签名将在 [Template 装配流](./12-compile-runtime-flow-spec.md#template-装配流-assembly-time-workflow) 中作为装配期拦截点。

## 优雅降级策略 (Graceful Degradation)

Reference reader 是质量增强模块, 不是 Agent phase 的硬依赖。失败时必须保留可运行路径。

| 失败场景 | 阈值 / 条件 | 等级 | 错误码 | 降级输出 |
|---|---|---|---|---|
| reader 超时 | 默认 60s | WARN | `[F-v3-reference-reader-failed]` | 取每份 reference 原始内容前 3000 token, 加警告注入 `<knowledge_base>` |
| reader 抛异常 | 任意异常 | WARN | `[F-v3-reference-reader-failed]` | 同上 |
| 单个 reference 读取失败 | 文件不存在 / 无权限 | FATAL at compile | `[F-v3-resource-reference-path-invalid]` | 不进入 reader |
| reader 输出非法 | 非 JSON 或缺 `markdown` | WARN | `[F-v3-reference-reader-failed]` | 同上 |

降级 Markdown 格式:

```markdown
> WARN [F-v3-reference-reader-failed]: builtin reference reader failed; using raw excerpt fallback.

## R1: <summary>

<first 3000 tokens of raw content>
```

为什么不阻塞: reference reader 的价值是把资料变得更好读, 但 Agent 仍有 `read_reference` tool 可以按需读取原文。编译期只保证资料路径存在和 registry 正确; reader 推理失败不应让整个 graph 无法运行。

降级后的 knowledge_base 填充位置见 [Cognitive Template 内部插槽布局](./06-cognitive-template-spec.md#8-大插槽布局拓扑)。

## 按需调取 Tools (read_reference / read_example)

物理位置:

```text
packages/graph-agent/src/graph_agent/tools/builtin/read_reference.py
packages/graph-agent/src/graph_agent/tools/builtin/read_example.py
```

这两个是 Agent 可主动调用的 LangChain Tool, 只暴露给由 `SKILL.md` 文件名推导出的 Agent 节点。它们不是 Logic Action。

`read_reference` 参数 schema:

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `reference_id` | string | 是 | 无 | 必须存在于当前 Agent phase `references[].id` | `[F-v3-resource-reference-not-found]` | 选择要读取的资料 |
| `query` | string | 否 | `""` | 自由文本 | — | 说明要查的具体问题, 便于 reader 摘要 |
| `mode` | enum | 否 | `"excerpt"` | `excerpt` 或 `full` | `[F-v3-tool-argument-invalid]` | 控制返回摘要还是原文 |

`read_example` 参数 schema:

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `example_id` | string | 是 | 无 | 必须存在于当前 Agent phase frontmatter document `examples[].id` | `[F-v3-resource-example-not-found]` | 选择要读取的扩展案例 |
| `query` | string | 否 | `""` | 自由文本 | — | 说明想对照的边界问题 |

调用语义:

| Tool | 内部行为 | 返回 |
|---|---|---|
| `read_reference` | 读取真实 reference 文件; 可复用 reference reader 的摘要函数, 但必须能返回原文 excerpt | Markdown, 含 id、summary、命中片段或全文 |
| `read_example` | 读取 document example 文件; 不调用装配期全量预读 | Markdown, 含 id、summary、content/excerpt |

Tool 与 Action 边界见 [Actions 注册、寻址与执行契约](./03-logic-md-spec.md#actions-注册寻址与执行契约)。
