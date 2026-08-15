---
module: 02-mechanism/05-run-inner/05-exit-control
doc: mvp1-alignment
status: audited-ready（**U8 单元锁定 2026-06-05**:after_agent 退出闸目标成段、live 无闸已标 impl gap;文件未 FROZEN）
aligns_with: ../../../00-architecture-overview.md（§3 机制层 B·运行内层）
---

# 05-exit-control — 机制 B · 退出闸(运行内层)

> **Tier**: 机制层 B · 运行·内层 | **Owns**: `after_agent` 退出闸 + NudgeInjector + 耗尽显式失败(**phase 不静默成功**) | **现状**: ⏳ | **Related**: `02-middleware`(本域是 after_agent middleware)· `03-cognitive`(finish_task marker)· `07-subagent`(对称:都是 middleware 但独立职责)

## 1. 定义
exit-control = 内层 agent loop 的**退出治理**:用一个 `after_agent` 闸保证 phase **不静默成功**——要么产出校验通过的 finish_task,要么显式失败。它**实现为 after_agent 中间件**(like `07-subagent` 是 wrap_tool_call 中间件),但**职责独立**(无其他归属)→ 独立模块。

## 2. 数据流 / 机制
`after_agent` 读 `finish_task_result` marker(`03-cognitive` 写):合格 → 放行 END;agent 自然停止但无合格 finish_task → NudgeInjector 构 nudge + `jump_to:"model"` 回灌;多次 nudge 仍无 → 写明确错误状态/抛 fatal(不静默 END)。借鉴 deepagents `RubricMiddleware` 的 after_agent 范式。

## 3. 接口契约
after_agent hook(返回 state update + can_jump_to);读 `FrameworkState.finish_task_result`(`data-contracts`/`03-cognitive`);耗尽显式失败的 V4 错误码(归 `compile-rules`/`data-contracts` ERROR_REGISTRY)。

## 4. 设计决策基础(用户原话)
> exit-control 独立(2026-06-03 PM):它和 subagent 一样是 middleware 但独立职责("phase 不静默成功"无其他归属)→ 独立模块。
> 诚实边界(04):"系统不能保证 LLM 一定把任务做好;能保证的是 phase 不会静默成功"。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| EX1 | phase 不静默成功:after_agent 闸,合格 finish_task / 显式失败 | 静默 END 让下游看见空 BusinessData 却不知原因 |
| EX2 | 成功 finish_task 不 `goto=END`,交本闸放行 | 唯一退出权落在 after_agent 闸 |
| EX3 | 独立模块(虽是 middleware)——和 subagent 对称 | 机制相同≠同模块,职责独立成模块 |

## 6. 测试关键点
1. D-test-2:无 tool_calls 不得 END;合格 finish_task 才 END;预算耗尽显式失败。
2. after_agent `jump_to:"model"` 重入端到端(nudge 回模型后合格提交或显式失败)。

## 7. 涉及 region / platform
engine 全权。

## 8. gaps / 待设计
1. "耗尽未提交 finish_task" 的 V4 错误码定义。
2. ~~NudgeInjector 策略收口(从 04 迁)。~~ **已关闭**(2026-08-15 决议 §3.5,PR C):策略语义迁入
   `middleware/nudge_policy.py` 成为唯一策略源,`ExitControlMiddleware` 是它的唯一适配器;
   死侧 `core/nudge_injector.py` 已随 §5 整族删除移除。

## 交叉引用(链接, 不复制)
00-architecture-overview §3 · `02-middleware`(本域=after_agent 中间件)· `03-cognitive`(finish_task marker,双向)· `07-subagent`(对称)
