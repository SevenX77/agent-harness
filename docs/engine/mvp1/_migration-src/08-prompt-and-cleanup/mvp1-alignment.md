---
module: 08-prompt-and-cleanup
doc: mvp1-alignment
status: drafted
last_verified: 2026-06-02
---
<!-- 核对进度:已迁 7 块 / 未迁 0 块 / 2026-06-04 -->

~~# 08-prompt-and-cleanup — MVP1 Alignment(目标设计)~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/mvp1-alignment.md#2-数据流--机制)

MVP1/V4 决策：exit gate 生效后，prompt 不再反复唠叨“必须调用 finish_task”，只定义一次提交方式和输出格式；但 frozen V0.3.0 spec 本轮不改。同时并入两项止血：工具异常桥接成 error ToolMessage；绑定 prompt 已要求的 `log_ambiguity` 和 `ask_clarification`。

~~## 覆盖范围~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/mvp1-alignment.md#2-数据流--机制)

覆盖范围：本文覆盖 prompt 减负、spec frozen 边界、工具异常桥接、工具绑定。

| 范围 | MVP1 目标 |
|---|---|
| `docs/engine/mvp0/skill-spec/06-cognitive-template-spec.md` | 不修改，只标注需要新 V4 spec。 |
| `cognitive/prompt.py` | 后续 V4 spec 解冻后减负。 |
| `middleware/tool_error.py` | 实现异常桥接。 |
| `log_ambiguity` / `ask_clarification_tool` | 默认进入 framework tools 或 middleware tools。 |

~~## 目标设计与编号流程~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/mvp1-alignment.md#2-数据流--机制)

1. 本轮不改 frozen V0.3.0 skill-spec。冻结证据见 `docs/engine/mvp0/skill-spec/06-cognitive-template-spec.md:1-4`。

2. V4 prompt 新 spec 需要把 finish_task 定义保留一次：说明什么时候提交、字段格式、失败会收到反馈。当前 frozen `<exit_contract>` 已承担这件事，见 `docs/engine/mvp0/skill-spec/06-cognitive-template-spec.md:72-76`。

3. V4 prompt 新 spec 应删除重复恐吓式提醒，把“必须 finish_task”的结构性保证交给 after_agent exit gate。当前 runtime 重复提醒在 `packages/graph-agent/src/graph_agent/cognitive/prompt.py:227-240`。

4. 工具异常止血：`ToolErrorHandlingMiddleware.wrap_tool_call` 捕获普通 tool exception，返回 `ToolMessage(status="error")`，让 LLM 能换路径或修 args。deerflow 参考实现见 `temp/deerflow/backend/packages/harness/deerflow/agents/middlewares/tool_error_handling_middleware.py:21-67`。

5. 工具异常桥接不能吞掉 LangGraph 控制流异常，例如 interrupt/bubble-up。deerflow 参考保留 `GraphBubbleUp`，见 `temp/deerflow/backend/packages/harness/deerflow/agents/middlewares/tool_error_handling_middleware.py:45-52`。

6. 绑定 `log_ambiguity`。函数本身在 `packages/graph-agent/src/graph_agent/cognitive/ambiguity.py:17-72`，但需要 ctx；MVP1 应通过 tool wrapper 注入 runtime context 或在 middleware 中提供等价 tool。

7. 绑定 `ask_clarification`。工具定义在 `packages/graph-agent/src/graph_agent/tools/builtin/clarification_tool.py:8-29`，CognitiveFlow 已有 ask_clarification 截获逻辑，见 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:369-380`、`packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:730-766`。

8. `_build_framework_tools` 不应再让 prompt 声称可用的工具落入 unknown tool fatal。当前 fatal 点见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:667-672`。

9. 绑定策略优先使用 local `@/components` 类似的 engine 本地 wrapper 思路：已有 `ask_clarification_tool` 用 LangChain `@tool` 包装，见 `packages/graph-agent/src/graph_agent/tools/builtin/clarification_tool.py:8-9`；`log_ambiguity` 需要同类 wrapper 或 `_wrap_tool_for_langchain`。

~~## 已实现 / 与 baseline 差异~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/mvp1-alignment.md#2-数据流--机制)

已实现：prompt composer、frozen spec、log_ambiguity 函数、ask_clarification tool、CognitiveFlow clarification handling 都存在。

未实现：ToolErrorHandlingMiddleware no-op，见 `packages/graph-agent/src/graph_agent/middleware/tool_error.py:11-16`。

未实现：live `graph_assembler` 不默认把 `log_ambiguity` / `ask_clarification` 放进 `all_tools`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:452-480`。

~~## 决策原因~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/mvp1-alignment.md#2-数据流--机制)

prompt 减负依赖 exit gate。没有结构闸时减少提醒会降低 finish_task 调用概率；有结构闸后，重复提醒只会增加 token 噪音。

工具异常桥接是无人值守稳定性兜底。当前 `tool.invoke` 无 try/except，工具小错误会直接崩 phase，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:545-546`；error ToolMessage 则能让模型修正。

绑定 prompt 提到的工具，是为了消除 prompt/runtime 不一致。模型被要求调用 `log_ambiguity`，但工具集合没有它，就会触发 unknown tool fatal，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:531-533`。

~~## 代码索引(clues)~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/mvp1-alignment.md#2-数据流--机制)

- `packages/graph-agent/src/graph_agent/cognitive/ambiguity.py:17-72`: log_ambiguity 函数。
- `packages/graph-agent/src/graph_agent/tools/builtin/clarification_tool.py:8-29`: ask_clarification tool。
- `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:730-766`: clarification command 控制流。
- `.venv/lib/python3.12/site-packages/langchain/agents/middleware/types.py:649-660`: wrap_tool_call 异常默认传播。

~~## 待办/疑点~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/mvp1-alignment.md#2-数据流--机制)

1. 待办：ToolErrorHandlingMiddleware 实现前写 failing test，复现普通工具异常不会崩 phase，而是回到模型。
2. 待办：绑定 `log_ambiguity` 时确认 ctx 注入来源，避免记录 ignored。
3. 待办：新 V4 spec 解冻后再实际改 prompt 文案；本轮只在文档标注。

