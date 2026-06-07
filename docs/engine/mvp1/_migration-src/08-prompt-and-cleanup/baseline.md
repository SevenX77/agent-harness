---
module: 08-prompt-and-cleanup
doc: baseline
status: drafted
last_verified: 2026-06-02
---
<!-- 核对进度:已迁 7 块 / 未迁 0 块 / 2026-06-04 -->

~~# 08-prompt-and-cleanup — Baseline(现状)~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/baseline.md#后端功能)

核心结论：V0.3.0 prompt spec 是 FROZEN，当前 prompt 仍多处强调 finish_task；但 live 工具集合没有默认绑定 `log_ambiguity` / `ask_clarification`。工具异常在 hand-written loop 中直接 `tool.invoke`，没有 try/except 桥接成 error ToolMessage。

~~## 覆盖范围~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/baseline.md#后端功能)

覆盖范围：本文覆盖决策记录 §10、§11。

| 覆盖目标 | 现状范围 | 覆盖说明 |
|---|---|---|
| frozen prompt spec | `docs/engine/mvp0/skill-spec/06-cognitive-template-spec.md:1-76` | spec 标 FROZEN，模板含 finish_task 提醒。 |
| runtime V030 prompt | `packages/graph-agent/src/graph_agent/cognitive/prompt.py:174-241` | live prompt 仍输出 critical_reminders 和 exit_contract。 |
| log_ambiguity | `packages/graph-agent/src/graph_agent/cognitive/ambiguity.py:17-72` | 函数存在，但需要 ctx 才能记录。 |
| ask_clarification | `packages/graph-agent/src/graph_agent/tools/builtin/clarification_tool.py:8-29` | tool wrapper 存在。 |
| tool binding | `packages/graph-agent/src/graph_agent/core/graph_assembler.py:650-672` | framework tools 只处理 critic 和 finish_task 跳过；未知 tool fatal。 |
| tool exception | `packages/graph-agent/src/graph_agent/core/graph_assembler.py:545-546` | 普通工具直接 invoke，无 try/except。 |

~~## 编号执行流程(现状)~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/baseline.md#后端功能)

1. `docs/engine/mvp0/skill-spec/06-cognitive-template-spec.md` 标注 `status: FROZEN`，并有 DO NOT EDIT 注释，见 `docs/engine/mvp0/skill-spec/06-cognitive-template-spec.md:1-4`。

2. frozen spec 的 `<critical_reminders>` 明确要求 finish_task、diagnostics_md、business_data_md 和 md_to_json 校验反馈，见 `docs/engine/mvp0/skill-spec/06-cognitive-template-spec.md:64-70`。

3. frozen spec 的 `<exit_contract>` 明确“回答必须调用 finish_task”，见 `docs/engine/mvp0/skill-spec/06-cognitive-template-spec.md:72-76`。

4. runtime `apply_v030_cognitive_template`(用途：组装 V0.3.0 agent prompt)也输出 `<critical_reminders>` 和 `<exit_contract>`，见 `packages/graph-agent/src/graph_agent/cognitive/prompt.py:227-240`。

5. runtime `resolve_role_prefix_from_llm_role` 已不再由 engine 读取 role files，provider role prefix 移到 gateway，见 `packages/graph-agent/src/graph_agent/cognitive/prompt.py:26-35`。

6. `log_ambiguity`(用途：记录非阻塞歧义反馈)函数存在；如果没有 ctx，会记录 ignored，见 `packages/graph-agent/src/graph_agent/cognitive/ambiguity.py:17-47`。

7. `ask_clarification_tool`(用途：向用户请求澄清)作为 LangChain tool 存在，见 `packages/graph-agent/src/graph_agent/tools/builtin/clarification_tool.py:8-29`。

8. `_build_framework_tools`(用途：为 agent phase 构造 framework tools)当前只识别 critic 命名和 `finish_task`，未知 tool 会 fatal，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:650-672`。

9. `_build_skill_node` 的 `all_tools` 是 `business_tools + framework_tools + finish_task`，没有默认追加 `log_ambiguity` 或 `ask_clarification`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:452-480`。

10. `_skill_node` 普通工具执行是 `result = tool.invoke(call_args)`，没有 try/except，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:545-546`。

11. `ToolErrorHandlingMiddleware` 目前是 no-op skeleton，见 `packages/graph-agent/src/graph_agent/middleware/tool_error.py:11-16`。

12. LangChain `wrap_tool_call` 文档说明异常默认传播，除非 ToolNode 配了 handle_tool_errors，见 `.venv/lib/python3.12/site-packages/langchain/agents/middleware/types.py:649-660`。

~~## Baseline / Alignment 差异~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/baseline.md#后端功能)

baseline prompt 仍靠反复提醒 finish_task；alignment 目标是在 exit gate 结构性保证之后给 prompt 减负，但不改 frozen V0.3.0 spec，只标注“需新 V4 spec”。baseline 工具异常和提示词工具绑定存在止血缺口；alignment 要并入 Plan A 实现。

~~## 决策原因~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/baseline.md#后端功能)

prompt 减负必须等待 exit gate 生效。否则删掉“必须 finish_task”提醒会放大现有 `if not tool_calls: break` 静默退出风险，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:526-528`。

`log_ambiguity` / `ask_clarification` 必须绑定，是因为 prompt 让模型调用它们；如果工具集合没有它们，模型照做会触发 unknown tool fatal，当前 fatal 点见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:531-533`。

~~## 代码索引(clues)~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/baseline.md#后端功能)

- `docs/engine/mvp0/skill-spec/06-cognitive-template-spec.md:1-4`: frozen 标记。
- `packages/graph-agent/src/graph_agent/cognitive/prompt.py:227-240`: runtime finish_task 提醒。
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:531-546`: unknown tool fatal 与工具异常无桥接。
- `packages/graph-agent/src/graph_agent/middleware/tool_error.py:11-16`: no-op ToolError slot。

~~## 待办/疑点~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/baseline.md#后端功能)

1. 待办：实现 ToolErrorHandlingMiddleware，把普通工具异常转成 error ToolMessage。
2. 待办：默认绑定 `log_ambiguity` 和 `ask_clarification`，或从 prompt 移除未绑定工具指令。MVP1 决策倾向绑定。
3. 待办：V4 spec 解冻后再做 prompt 减负；本轮不改 frozen spec。

