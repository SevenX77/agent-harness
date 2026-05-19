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

## 1. WebSocket 事件分类完整枚举
当 Engine 通过 `run()` 或 `predict()` 执行图时，内部的 callback 系统会向上游派发结构化的 WebSocket Event，以供前端渲染 Timeline。
核心事件 Payload Schema（TypeScript）：

```typescript
type TraceEventType = 
  | "PHASE_START" | "PHASE_END"
  | "AGENT_STEP_START"
  | "LLM_CALL" | "LLM_RESPONSE"
  | "TOOL_CALL" | "TOOL_RESULT"
  | "VALIDATOR_FAILED" | "NUDGE"
  | "GRAPH_ERROR";

interface TraceEventPayload {
  eventId: string;
  timestamp: string;      // ISO 时间戳
  type: TraceEventType;
  phaseId: string;        // 归属的节点 ID
  costMetrics?: {         // (可选) Token 消耗
    promptTokens: number;
    completionTokens: number;
  };
  content: any;           // 载荷数据 (例如原始 JSON / 错误栈)
}
```

## 2. Timeline 竖向渲染规范
前端界面接收到事件后，渲染为一条带缩进和嵌套层的竖向时间轴。
- **层级包裹**: `PHASE_START` 是大卡片，其内部所有的 `LLM_CALL`, `TOOL_CALL` 等子事件以树状形式缩进。
- **高亮处理**:
  - `LLM_RESPONSE` 正常返回为绿色边框。
  - `VALIDATOR_FAILED` 和随后触发的 `NUDGE` (纠偏) 为醒目的黄色/红色高亮（如附带徽章标示 `Nudge: 1/3`）。

## 3. Prompt 透视仪结构
在 Timeline 中点击带有 LLM 交互的条目，系统弹出透视仪面板，分为 3 个核心 Tab：
1. **模板 (Template)**: 呈现原始开发者编写的字符串（包含未被替换的 `{{ var }}`）。
2. **变量字典 (Variables)**: 展示运行时实际获取到的 JSON Dictionary (`{ "var": "The actual value" }`)。
3. **最终发往模型的文本 (Rendered)**: 完全替换完成，并且经过内部系统级封装后的最终请求字符串，主要排查模型无法识别上下文边界的问题。

## 4. Edge Inspection 协议
针对复杂拓扑，排查两个节点之间的连线数据流。
- **协议流程**:
  - 前端点击画布中的连接线圆点，发起请求：`GET /api/skills/{id}/runs/{run_id}/edges?source={from_node}&target={to_node}`。
  - 后端拉取指定运行的持久化 Checkpoint 库，抽出这部分上下文传递时刻的 JSON 快照，返回给前端展示为只读面板，实现断流核查。

## 相关 Spec
*(此模块当前作为基础设施存在，历史记录见 [predict-v2](../../.kiro/specs/_archive/predict-v2/design.md))*
