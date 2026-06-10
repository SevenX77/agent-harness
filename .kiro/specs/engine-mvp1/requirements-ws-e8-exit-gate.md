---
ws_id: WS-E8-exit-gate
modules: [05-run-inner/05-exit-control, 05-run-inner/01-agent-loop]
depends_on: [WS-E1-create-agent-core]
blocks: []
owns_files:
  - .kiro/specs/engine-mvp1/requirements-ws-e8-exit-gate.md
  - packages/graph-agent/src/graph_agent/middleware/exit_control.py
  - packages/graph-agent/src/graph_agent/middleware/nudge_injector.py
  - packages/graph-agent/src/graph_agent/core/nudge_injector.py
  - packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py
  - packages/graph-agent/src/graph_agent/middleware/factory.py
  - packages/graph-agent/src/graph_agent/middleware/__init__.py
  - packages/graph-agent/src/graph_agent/core/error_registry.py
  - packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py
  - docs/engine/mvp1/02-mechanism/05-run-inner/05-exit-control/baseline.md
spec_ssot:
  - docs/engine/mvp1/_impl/IMPL_PLAN.md
  - docs/engine/mvp1/_impl-backlog.md
  - docs/engine/mvp1/02-mechanism/05-run-inner/05-exit-control/mvp1-alignment.md
  - docs/engine/mvp1/02-mechanism/05-run-inner/01-agent-loop/mvp1-alignment.md
  - docs/development/task-spec-standard.md
baseline_ref: PR #118 head 047d46f676ca2440ce4973ecb817c2dad7a83fa4
status: drafted
---

# WS-E8 exit gate - 需求书

## 1. 目标(intent + why)

给 AGENT phase 补上退出闸，收口“没有合格 finish_task 但看起来成功”的假成功路径。phase 只有在合格 finish_task 已写入明确 marker 后才能作为成功结束；否则必须被 nudge 推回模型继续完成，或在预算耗尽时返回明确失败/诊断。机制细节以 `spec_ssot` 为唯一真理。

## 2. SSOT 指针(grounding,IR2/IR5)

- 目标机制: `docs/engine/mvp1/02-mechanism/05-run-inner/05-exit-control/mvp1-alignment.md` §1-§6。
- 依赖机制: `docs/engine/mvp1/02-mechanism/05-run-inner/01-agent-loop/mvp1-alignment.md` §1-§6。
- 实施排期/文件锁: `docs/engine/mvp1/_impl/IMPL_PLAN.md` §二-§三, `docs/engine/mvp1/_impl-backlog.md` Tier 2 I4。
- 写作/流程标准: `docs/development/task-spec-standard.md` §一-§四。
- 现状 baseline: PR #118 head `047d46f676ca2440ce4973ecb817c2dad7a83fa4`。
- 必读源码(实现前先读并回述关键现状):
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py` 的 AGENT create_agent 装配和 recursion/max_iterations 边界。只读 grounding；本 WS 默认不 owns 此文件。
  - `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py` 的 finish_task 接受/拒绝路径。
  - `packages/graph-agent/src/graph_agent/middleware/factory.py` 和 `packages/graph-agent/src/graph_agent/middleware/__init__.py` 的 middleware 链构造与顺序契约。
  - `packages/graph-agent/src/graph_agent/core/nudge_injector.py` 的既有 nudge 策略。注意: 当前仓库没有 `middleware/nudge_injector.py`; 若实现选择新增 middleware 侧适配器，必须保持现有 nudge 语义可解释。
  - `packages/graph-agent/src/graph_agent/core/result.py`, `packages/graph-agent/src/graph_agent/core/exceptions.py`, `packages/graph-agent/src/graph_agent/core/error_registry.py` 的失败/诊断表达。

## 3. 文件归属(并发锁,IR1)

- 本 WS owns: 见 frontmatter `owns_files`。
- 禁止触碰:
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py`: 归 WS-E1 串行热点。若 RED 证明必须改这里才能避免假成功，先停下请示。
  - `packages/graph-agent/src/graph_agent/middleware/tracing.py`, `tool_error.py`, `loop_detection.py`: 后三槽真实实现归 WS-E2。
  - checkpoint/state resume 相关文件: 归 WS-E5。
  - callbacks/events/emit: 不在 WS-E8。
  - file lazy/artifact/io storage/read_file: 不在 WS-E8/归 WS-E1-io。
  - Studio/gateway 文件: 不在 WS-E8。
- 共享文件协调: `cognitive_flow.py` 只允许 finish marker/退出权边界的小范围调整；`factory.py`/`__init__.py` 只允许接入 exit-control middleware 所需的最小变更。

## 4. 现状锚点(baseline)

PR #118 已把 AGENT phase 迁到 `create_agent` 链路，并传入 6 槽 middleware。当前仍需要 WS-E8 验证并收口: 合格 finish_task 的 marker 是否由退出闸统一放行、无 tool_calls/无 finish_task 是否会被 nudge 或显式失败、recursion/max_iterations 耗尽是否不会被包装成成功。

## 5. 目标行为(可测的契约)

- AGENT phase 不得因为模型自然停顿、无 tool_calls、空输出、或达到循环/递归上限而静默成功。
- 合格 finish_task 必须写入 `FrameworkState.finish_task_result` 等明确 marker；after_agent 退出闸只在该 marker 合格时放行成功结束。
- finish_task 的成功信号不得绕过退出闸直接宣告 phase 成功；唯一成功出口是退出闸观察到合格 marker 后放行。
- 当模型没有完成信号但仍可继续时，退出治理必须向模型提供可见 nudge，并让 agent loop 继续尝试完成。
- 当 nudge/iteration/recursion 预算耗尽时，结果必须是明确失败或明确诊断，不得返回 `RunResult.success=True` 且业务输出为空/残缺。
- 失败结果必须可由调用方机器判定: 至少有失败状态、错误码或诊断文本之一，且能定位到 phase/exit-control 语义。
- finish_task schema 不得退化: `business_data_md`, `reasoning`, `diagnostics_md` 的入参/marker 语义保持可用；schema gate/business validator 既有拒绝路径仍返回模型可修正的反馈。

## 6. 测试要求(Codex 必须覆盖,IR3/IR4)

Codex 先写 RED 测试，运行到干净失败后停在契约门。建议落点: `packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py`。

必须覆盖:

- AGENT 未调用 finish_task 时不得静默成功。至少一条测试走真实 `compile_skill` + `assemble_graph` 或 `run_skill` 路径，不接受只测孤立 mock 函数。
- finish_task 写入明确 marker 后，after_agent gate 放行；断言成功结果中保留业务输出，并能观察到 `finish_task_result` 语义。
- 模型无 tool_calls / 无完成信号时，退出闸能 nudge 并回到模型，或在预算耗尽后返回结构化失败；不得裸退为成功。
- max_iterations/recursion 上限触发时，结果必须是明确失败/诊断，不得从 checkpoint/partial state 中取空结果当成功。
- CognitiveFlow finish_task schema 对齐不破坏: `business_data_md`、`reasoning`、`diagnostics_md`、schema validation/parsed data 的基本契约仍可断言。
- 回归命令必须覆盖 WS-E1 create_agent、subagent、logic、iterate、subgraph IO 关键回归；这些可以通过既有测试文件运行，不要求在 RED 文件里复制全部场景。

## 7. 硬依赖约束

- WS-E8 以 PR #118 head 为候选基线；若 #118 后续 CI 失败或 head 改变，需要重新核实后再继续。
- RED 测试先于任何生产代码变更。
- 若 RED 指向 `graph_assembler.py` 的 E1 接线缺口，先停下复审，不在 WS-E8 中擅自改热点文件。

## 8. 验收标准(硬退出,IR4)

- [ ] WS-E8 RED 已先失败，且失败原因对应退出闸缺口，不是测试拼写/fixture 错误。
- [ ] WS-E8 实现后新增测试全绿。
- [ ] 既有 WS-E1 create_agent 核心回归全绿。
- [ ] subagent、logic、iterate、subgraph IO 相关回归无退化。
- [ ] 至少一条真实 assemble/run 路径证明无 finish_task 不会成功。
- [ ] finish_task 成功路径证明 marker 写入和退出闸放行均成立。
- [ ] max_iterations/recursion 耗尽路径返回明确失败/诊断。
- [ ] scope 审计确认只动 `owns_files`; 若有例外，已先停下复审并记录。

## 9. 不做(范围锁定,IR7)

- 不做 middleware 后三槽实现；归 WS-E2。
- 不做 checkpoint/state/resume；归 WS-E5。
- 不做 callbacks/events/emit。
- 不做 WS-E1-io 的文件 lazy/artifact/read_file/storage。
- 不做 Studio/gateway。
- 不改 `graph_assembler.py`，除非 RED 证明 E1 接线缺口且先停下请示。
- 不重写 finish_task schema/业务校验体系；只允许为退出闸调整 marker 和退出权边界。

## 10. baseline 回写指令(IR6)

实现落地并通过审查后，按真实代码更新 `docs/engine/mvp1/02-mechanism/05-run-inner/05-exit-control/baseline.md`。只记录已实现事实: exit-control middleware 接线、finish_task marker 放行、nudge/耗尽失败行为、仍未实现的边界。不得把未落地目标写成现状。

## 11. 评审检查点

- 契约门(Claude/PM 审测试): RED 是否忠实编码 “无 finish_task 不成功、合格 finish_task 才放行、耗尽显式失败”；是否没有用过度 mock 掩盖 create_agent live path。
- Codex 审查退出: §8 全满足；验证命令真实跑过；scope 审计无越界。
- Claude/PM 终审: 行为是否符合 alignment；baseline 是否诚实；测试是否可能假绿。

## 12. 给 Codex 的交接:按写作规范写 kiro task.md

契约门通过后，Codex 据已批准测试写 `.kiro/specs/engine-mvp1/task-ws-e8-exit-gate.md`，遵守:

- 来源 = 已批准测试；不凭空添加实现步骤。
- 格式 = Phase 分段 + `- [ ]` 勾选项 + 每条挂 `_Requirements: WS-E8.*` + 验证命令。
- frontmatter 指回本需求书和 `spec_ssot`；不重写设计。
- 嵌入编排注解: `owns_files`、实现者 = Gemini、§8 硬退出。
- 行号 Codex 落地时自己重新核；不照抄旧行号。
- 不跑 `/kiro:spec-tasks`，避免 clobber。
- 同步输出可复制 Gemini prompt，包含工作区路径、必读文件、RED 失败结果、owns_files/禁止触碰、目标行为、验证命令、回报格式。
