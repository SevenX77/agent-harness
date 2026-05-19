---
status: Living
target_goal: "定义前端如何解析并渲染来自引擎的执行 Trace，消除调试黑盒"
linked_code_paths:
  - apps/studio/frontend/src/components/history/HistoryPanel.tsx
linked_specs:
  - .kiro/specs/_archive/predict-v2/
last_updated: 2026-05-19
---

# 运行 Trace 与可视化 (Trace & Visualization)

## 1. WebSocket 推流事件分类
当执行 `Run` 时，引擎会实时向前端 WebSocket 发送事件流，前端必须能够解析以下核心事件簇：
- `PHASE_START` / `PHASE_END`
- `AGENT_STEP_START`: (Agent 思考中)
- `LLM_CALL`: (带 Token 消耗统计)
- `TOOL_CALL` / `TOOL_RESULT`: (工具执行记录)
- `VALIDATOR_FAILED` / `NUDGE`: (关键：质检不通过并触发重试的强制纠偏事件)

## 2. 时间轴视图 (Timeline) 的竖向渲染规范
由于 Trace 具有强烈的时间流与层级嵌套属性，前端必须采用**竖向瀑布流**来展示。
- 当大模型陷入多轮 Tool 循环或连续触发 Nudge 时，相关记录会被缩进，包裹在同一个 `Phase` 卡片下。
- `Nudge` 与报错信息必须以显眼的红/黄警示色高亮，让 PM 一眼看出模型在哪里“翻车”。

## 3. Prompt 透视仪 (Prompt Inspector)
在时间轴上点击任意一次 `LLM_CALL` 记录，弹出一个具有 3 个 Tab 的独立面板：
1. **模板 (Template)**: 原始的 `{{ var }}`。
2. **变量 (Variables)**: 注入时的 JSON 字典。
3. **渲染文本 (Rendered)**: 实际发给 OpenAI/Anthropic 的最终纯文本。
这是排查“为什么大模型答非所问”的终极利器。

## 4. 连线黑板快照 (Edge Inspection)
在 React Flow 的画布上，每条代表 Context 传递的连线上，都放置一个小圆点。
在一次运行跑完或挂起时，点击圆点，右侧滑出抽屉，纯净展示上一轮跑完时，上游往下游传递的具体 `Context Dictionary` (JSON 格式)，供排查断流问题。

## 相关 Spec
*(此模块当前作为基础设施存在，历史记录见 [predict-v2](../../.kiro/specs/_archive/predict-v2/design.md))*
