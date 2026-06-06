---
module: 02-mechanism/05-run-inner/05-exit-control
doc: baseline
status: audited-ready（现状对齐 pinned 代码 7cd4b9c；NudgeInjector 已存在,但 live 无 after_agent 退出闸）
---

# 05-exit-control — Baseline(当下代码实现逻辑)

> **Scope**: phase 退出治理现状:`NudgeInjector`(nudge 状态机)、live 的退出现状(无 after_agent 闸)。
> **现状一句话**:`NudgeInjector`(`core/nudge_injector.py`)的 nudge 状态机(standard/selfcheck/planning)已实现,但 **live 路径没有 after_agent 退出闸**——成功 finish_task 现走 `cognitive_flow` 的 `goto=END`(`:511`)直接结束,手写 loop 无 tool_calls 时裸退 `break`(`graph_assembler.py:527-528`)。"phase 不静默成功"目前**没有统一的闸**保证。

## UI/UX
N/A。

## 前端逻辑
N/A。

## 后端功能

### 1. NudgeInjector(已实现)
`core/nudge_injector.py`:`NudgeOutcome`(`:54`)、`NudgeKind = standard/selfcheck/planning`(`:50`)、`build_standard_nudge_text`(`:44`)——per-phase nudge 状态机,判断要不要注入 nudge + payload 是否已满足 selfcheck。`finish_task_result` marker 写在 flow(`cognitive_flow.py:214/490`)。

### 2. live 退出现状(无 after_agent 闸)
- CognitiveFlow 成功 finish_task → `goto=END`(`cognitive_flow.py:511`)**直接结束 phase**。
- 手写 loop 无 tool_calls → 直接 `break`(`graph_assembler.py:527-528`)裸退。
- **没有 after_agent hook 统一判断"能不能 END"**——这是 mvp1 要建的退出闸。
> **after_agent 第一次出现需定义**:agent loop 整体结束后触发的 middleware hook,用来统一裁决 phase 能否退出(合格 finish_task 才放行,否则 nudge 回灌或显式失败)。

## API
- `NudgeInjector` / `NudgeOutcome`(`nudge_injector.py:54`)/ `build_standard_nudge_text`(`:44`)。
- (目标)after_agent hook(返回 state update + can_jump_to)。

## Data Model / State
读/写 `FrameworkState.finish_task_result`(marker,`cognitive_flow.py:214`);nudge 计数在 flow。

## 当前边界(这个模块现在不是什么)
- **live 没有 after_agent 退出闸**:现靠 `goto=END` / 裸 break 结束,没有"phase 不静默成功"的统一保证。
- **NudgeInjector 已存在但未作为闸接入**:它是 nudge 策略,不是退出裁决器。
- **是 middleware 但独立模块**:like `07-subagent`,机制相同≠同模块。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标 |
|---|---|---|
| 退出裁决 | `goto=END`(`:511`)/ 裸 break(`graph_assembler.py:527`) | after_agent 闸:合格 finish_task 才 END |
| 耗尽 | 无统一处理 | NudgeInjector 回灌 + 多次仍无 → 显式失败码 |
| 闸位置 | 分散(cognitive goto / loop break) | 唯一退出权落 after_agent |

> **验"是否按 mvp1 改了"**:① 无 tool_calls 是否不再裸退、改走 after_agent 闸;② 合格 finish_task 才 END、否则 nudge 回模型;③ 预算耗尽是否显式失败(非静默 END)。

## 读代码主路径提示
NudgeInjector `nudge_injector.py:44/54` → 现 live 退出点 `cognitive_flow.py:511`(goto=END)+ `graph_assembler.py:527`(裸 break)。目标 after_agent 闸借鉴 deepagents RubricMiddleware。

## 交叉引用(链接, 不复制)
mvp1-alignment(目标)· `02-middleware`(本域=after_agent 中间件)· `03-cognitive`(finish_task marker,双向)· `07-subagent`(对称)· `data-contracts`(finish_task_result)
