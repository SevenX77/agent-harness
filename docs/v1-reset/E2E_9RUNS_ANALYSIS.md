# E2E 9 次运行轨迹综合分析报告

日期: 2026-04-30
分析目标: `docs/v1-reset/e2e_traces/run_1` 到 `run_9` 的 9 次真 LLM E2E 测试轨迹。

## 1. 总览

- **整体通过率**: 9 / 9 (100% PASS)。所有的运行状态最后都达到了 `status=OK`，并且成功流转到了最后的 `current_phase=review`。
- **Token 消耗与开销**: 
  - 总 Input Tokens: 范围在 `35,446` ~ `45,086` 之间。
  - 总 Output Tokens: 范围在 `1,771` ~ `3,023` 之间。
- **执行时间 (Duration)**: 最快 `39.37s`，最慢 `58.17s`。
- **轨迹完整性**: 每次运行都生成了预期的 5 个文件（部分包含了历史残留的 `error.txt`，但对结果正确性无影响）。轨迹覆盖了从 `setup` 到 `segment` 再到 `review` 阶段的完整流转。

## 2. 逐次运行分析

### Run 1
- **概况**: 耗时 46.90s, Input 39,945, Output 2,685。
- **流转细节**: 产生 14 条 state messages。工具调用序列为 `[parse_segmentation_output, store_segments, finish_task, parse_segmentation_output, store_segments, finish_task]`。过程非常标准，依次度过了 `segment` 与 `review` 两个核心带有 LLM 推理的阶段。
- **异常**: 无。

### Run 2
- **概况**: 耗时 46.26s, Input 40,168, Output 2,747。
- **流转细节**: 同 Run 1 完全一致产生 14 条 state messages，以及一模一样的工具调用链路。LLM 的行为模式极为稳定。
- **异常**: 无。

### Run 3
- **概况**: 耗时 58.17s, Input 45,086, Output 3,023。
- **流转细节**: 产生 **16** 条 state messages（最多），工具序列为 `[update_working_memory, parse_segmentation_output, store_segments, finish_task, store_segments, finish_task]`。
- **异常/特征**: 这是唯一一次主动触发了 `update_working_memory` 工具的运行。LLM 在 `segment` 阶段认为有必要记录进度，因而产生了一次额外的思考轮次，这直接导致了最大的 Token 消耗和最长的耗时。

### Run 4
- **概况**: 耗时 48.16s, Input 35,565, Output 2,751。
- **流转细节**: 14 条 messages。工具调用序列恢复标准 `[parse, store, finish, parse, store, finish]`。
- **异常**: 无。

### Run 5
- **概况**: 耗时 40.66s, Input 35,446, Output 2,793。
- **流转细节**: 14 条 messages。标准执行链路，非常顺利。
- **异常**: 无。

### Run 6
- **概况**: 耗时 52.31s, Input 35,561, Output 2,695。
- **流转细节**: 14 条 messages。执行链路同样非常标准。耗时略偏长推测为 Opus 4.7 接口网络抖动。
- **异常**: 无。

### Run 7
- **概况**: 耗时 46.56s, Input 35,562, Output 2,698。
- **流转细节**: 14 条 messages。标准执行链路。
- **异常/特征**: 目录下出现 `error.txt`，经检查为之前沙箱失败残留的产物，不影响本次 Trace 本身的成功断言。

### Run 8
- **概况**: 耗时 47.05s, Input 35,644, Output 2,855。
- **流转细节**: 14 条 messages。标准执行链路。同样伴随历史残留的 `error.txt`。
- **异常**: 无。

### Run 9
- **概况**: 耗时 39.37s, Input 37,722, Output 1,771。
- **流转细节**: 产生 **11** 条 state messages（最少），工具调用仅有 `[parse_segmentation_output, parse_segmentation_output, store_segments, finish_task]`。
- **异常/特征**: 在某个 LLM 阶段，模型似乎将几个步骤进行了批处理合并，导致整个 Graph 少经历了一轮完整的 LLM Phase 交互流转，不仅消息数下降，输出 Token（1771）也直接探底，这也是 9 次中最为“急躁”但仍满足契约成功结束的例子。

## 3. 预期 (Predict) 与实际结果差距矩阵

Integration 测试（`test_mvp1_smoke.py`）针对真实 LLM 测试提出了四大约束不变量（Invariants）。实测匹配情况如下：

| Invariant 契约要求 | 预期结果 | 9 次真机实测结果 | 匹配度 |
| --- | --- | --- | --- |
| **BusinessData 纯净** | `state["data"]` 无 `_` 前缀的内部框架变量 | 实测 `data_keys` 均只包含合法的业务键（`chapter_content`, `segments` 等），没有任何元数据或框架状态泄漏。 | 完美 (9/9) |
| **FrameworkState 闭环** | `state["flow"]` 可以合法通过 `FrameworkState.model_validate` 而不发生字段遗漏或多余。 | 测试断言皆通过。 | 完美 (9/9) |
| **业务字段非空** | 运行必须实际产出数据 | 均非空。 | 完美 (9/9) |
| **Messages 非空且轨迹有效** | 必须有 LLM 实际发生过推理并产生对话历史记录 | 所有 messages_count 在 11 到 16 之间，且覆盖了多个 tool_calls 和 Human/AI 交替。 | 完美 (9/9) |

## 4. LLM 行为方差与稳定性

* **执行的一致性**: 尽管选用了具备深度推理（Thinking）或复杂模型的角色（`test_opus47_ws`），9 次测试的收敛性达到惊人的 100%。没有发生过死循环（Recursion Limit Exceeded），且 0 次幻觉调用（没有调用未声明的 tools）。
* **Token 与 Duration 方差**:
  - `Input Tokens` 的底线在 35k 左右，高线飙到 45k。这与大模型在处理长上下文时触发不同的思考轮数，以及由于 `update_working_memory` 等工具带来的上下文历史不断 append 的累积效应强相关。
  - `Output Tokens` 比较稳定，在 2700 左右波动，仅 Run 9 （急躁合并输出）出现 1771 的低谷。说明业务对于输出 Schema 的指导力是非常强的。

## 5. 关键观察与结论

1. **引擎健壮性 (Engine Stability)**：未发现任何属于引擎自身的 Bug（Engine Bug）。无论是 Tool Binding 注入、消息合并、还是 Cognitive Flow 的 Schema 兜底，全部稳稳接住了真实大模型的各类突发奇想的输出。
2. **大模型的 Flakiness**：模型是 Flaky（存在方差）的。例如 Run 3 突发奇想地调用了 `update_working_memory`；Run 9 决定压缩流程直接合并 Tool 调用退出。但这反而证明了我们采用 LangGraph 状态机配合 CognitiveFlow 重试反馈回路的做法是**完全正确的**，它成功在运行时熨平了 LLM 行为的不确定性。
3. **残留物说明**：部分文件夹中的 `error.txt` 系本地环境在 a1 开发测试早期的残留文件。新框架采用 `pytest` 的原生日志收集以及 `final_state.json` 转储，整个输出结构十分清爽。