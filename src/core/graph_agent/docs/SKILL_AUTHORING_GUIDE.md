# SKILL_AUTHORING_GUIDE

本指南说明如何为 `graph_agent` 编写可编译、可迁移、可审计的 `SKILL.md`。

## 1. 先选模式

### `type: simple`

适合单个 agent loop 即可完成的任务。

特点：

- 最多一个 Phase
- 可以完全不写 `## Phase N:` 标题
- 如果缺少 `<phase_config>`，loader 会补一个最小默认 Phase

### `type: graph`

适合显式拆成多个节点的任务。

特点：

- 使用 `<node>` 描述拓扑节点
- 每个节点内部仍然是一个 Phase
- 节点之间通过共享 `context` 传递数据

## 2. SKILL.md 结构

一个完整 skill 由两部分组成：

1. YAML frontmatter
2. XML 风格标签正文

### frontmatter 常用字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | 是 | skill 名称 |
| `description` | 是 | 用途描述，建议写清“当什么情况时使用” |
| `type` | 否 | `simple` 或 `graph`，默认 `simple` |
| `io` | 否 | 声明式输入输出 |
| `context_mapping` | 否 | 把 runtime/input 组装成 `initial_context` |

### 正文标签

| 标签 | 用途 |
|------|------|
| `<phase_config>` | Phase 参数 |
| `<system_prompt>` | 当前 Phase 的系统提示 |
| `<user_prompt>` / `<user_prompt_builder>` | 当前 Phase 的用户提示模板 |
| `<data_architecture>` | 数据结构约束说明 |
| `<node>` | graph 模式节点 |
| `<ref>` | 引用外部片段 |

## 3. `phase_config` 支持字段

`phase_config` 最终会映射为 `Phase` 对象。常用字段如下：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | `str` | 从标题推导 | Phase 名称 |
| `tier` | `str` | `balanced` | 对应 `llm_roles.yaml` 的角色名 |
| `tools` | `list[str]` | `[]` | 工具引用，格式 `tools.module.function` |
| `validator` | `str` | `None` | 校验器引用，返回 `(passed, errors)` |
| `retry_target` | `str` | `None` | 校验失败时回退到哪个 Phase |
| `max_retries` | `int` | `3` | 校验失败最大重试次数 |
| `max_iterations` | `int` | `20` | DeerFlow agent loop 的最大迭代次数 |
| `max_tool_calls` | `int` | `0` | 0 表示不额外限制 |
| `max_nudges` | `int` | `3` | 文本偏航提醒上限 |
| `dead_end_threshold` | `int` | `3` | 连续失败多少次后注入 dead-end warning |
| `subagent_enabled` | `bool` | `false` | 是否允许在该 Phase 使用 subagent |
| `subgraph` | `str` | `None` | 子 skill 的 `SKILL.md` 路径 |
| `context_bridge` | `dict` | `None` | 父子 skill 输入输出映射 |

以下字段不是直接写在 `phase_config` 里，而是来自其他标签或运行时推导：

- `system_prompt`：来自 `<system_prompt>`
- `user_prompt_template`：来自 `<user_prompt>` 或 `<user_prompt_builder>`
- `data_architecture`：来自 `<data_architecture>`
- `requires_llm`：由是否存在 `system_prompt` / `subgraph` 自动推导

## 4. `context_mapping` 语法

支持三种表达式：

| 写法 | 含义 |
|------|------|
| `{input.scene.scene_id}` | 按点路径深取值 |
| `"literal"` / `'literal'` | 字符串字面量 |
| `plain_text` | 原样字符串 |

不再支持：

- `$func(...)`

如果你需要复杂组装逻辑，请显式写一个 `requires_llm: false` 的 setup/code phase 或 skill 本地工具。

## 5. 工具与校验器引用

### 工具引用

使用点路径：

```text
tools.collect.render_html
```

解析规则：

1. 最后一个 `.` 右侧是函数名
2. 左侧是相对 skill 目录的模块路径
3. loader 会优先找 `.py` 文件，再找包的 `__init__.py`

### 校验器约定

校验器函数签名建议为：

```text
validator(ctx) -> (passed: bool, errors: list[str])
```

要求：

- `passed=True` 表示进入下一阶段
- `passed=False` 表示写入 `_retry_feedback` 并触发重试
- `errors` 中每一条都应可直接写进用户反馈

## 6. 编写建议

1. 把业务规则写进 skill，不要写进 framework
2. 把“输入 shape”和“输出 key”写清楚，避免 Phase 间格式漂移
3. 让 `validator` 只做确定性检查，不要把模糊判断留给代码
4. `data_architecture` 用来声明关键字段、数据边界和下游依赖
5. 如遇规则不清晰，优先让 agent 调用 `log_ambiguity`，而不是静默跳过

## 7. 最小 simple 示例

```md
---
name: scene-analysis
description: 当需要对单个 scene 做结构化分析时使用。
type: simple
context_mapping:
  scene: "{input.scene}"
---

<phase_config>
name: analyze
tier: balanced
tools:
  - tools.analysis.collect_scene_context
</phase_config>

<system_prompt>
完成分析后调用 finish_task。
</system_prompt>

<user_prompt>
请分析当前 scene：{scene}
</user_prompt>
```

## 8. graph + subgraph 示例

```md
---
name: visual-pipeline
description: 当需要把文本分析与视觉生成拆成多阶段时使用。
type: graph
---

<node id="plan">
<phase_config>
name: plan
tier: analyst
</phase_config>
<system_prompt>
先拆解任务，再 finish_task。
</system_prompt>
</node>

<node id="render">
<phase_config>
name: render
subgraph: subskills/render/SKILL.md
context_bridge:
  inputs:
    plan_result: render_input
  outputs:
    render_output: final_render
</phase_config>
</node>
```

## 9. 提交前检查

- `compile_skill()` 无 FATAL
- `tier` 在 `llm_roles.yaml` 中存在
- 每个 `tools`/`validator` 引用都能解析
- `retry_target` 指向真实 Phase
- 所有关键输出在下游阶段中都有消费者或最终 `io.outputs`
