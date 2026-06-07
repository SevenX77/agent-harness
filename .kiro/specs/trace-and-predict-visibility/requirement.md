---
spec: trace-and-predict-visibility
status: Draft
last_updated: 2026-05-19
linked_level3_docs:
  - docs/studio/TRACE_AND_VISUALIZATION.md
  - docs/engine/GRAPH_EXECUTION_MODEL.md
---

# Requirement: Trace & Predict Visibility (Timeline & Edge Inspection)

> ⛔ **SUPERSEDED (2026-06-01)** — 本 spec 已**改名为 [`studio-feature-trace-inspector`](../studio-feature-trace-inspector/requirement.md)** 并合并内容。请勿在此继续编辑;以 trace-inspector 为准。本目录待物理归档到 `_archive/`。下方内容仅作合并来源留存(Timeline / Prompt 透视 / Edge Inspection / Compile 报错)。

## 1. 问题陈述 (Problem Statement)
### 1.1 现状痛点
在 MVP 早期，Engine 可以运行图，但前端仅仅能收到一些干瘪的成功/失败响应。PM 在点击 Predict 或 Run 后，面临完全的盲区：输入是怎么被拆分映射的？每一轮 LLM 到底说了什么乱七八糟的话才导致了 Validator 失败？
去后端的 Console 里捞海量的杂乱日志来 debug 是不可接受的噩梦。

### 1.2 为什么需要这个 spec
- **PM 原话引用**: "Compile 报语法/规则违规；Predict 做打磨；Run 实测。必须能看到每一步的输入输出、数据如何映射合并、Agent loop 每轮循环/subagent 的输入输出。这部分需要具体设计。"
- **Phase 3 Gap Matrix 描述**: 文档里已经给出了机制和数据约束，但具体前端 React Flow 组件如何与这些 Trace 状态绑定（呼吸灯、边框变色机制），以及竖向时间轴、Prompt 透视仪的组件级数据交互协议缺失。本 Spec 旨在填补这一“最后一公里”的设计空白。

## 2. 用户故事 (User Stories)
1. **As a PM**, I want 在点击 Run 后，右侧滑出一个竖排的时间轴，so that 我能清晰地按执行顺序看到每一个 LLM 请求的延迟、消耗 Token 以及最终抛出的结果。
2. **As a PM**, I want 在时间轴上点击一条特定的 LLM 回复记录，弹出“Prompt 透视仪”，so that 我能比对原始的 Markdown 模板和我实际喂进去的变量 JSON，找到幻觉的根源。
3. **As a PM**, I want 在画布中点击两个节点之间的那条“连线”，so that 我能在旁边展开一个抽屉，看到上一轮跑完时，这条线上正流淌着什么样的大黑板 JSON Context 数据包。
4. **As a 前端 Dev**, I want 后端的 Compile API 在出错时返回结构化的字段与行号，so that 我能够将错误高亮定位到 Monaco 编辑器的特定行，或者为用户提供一个 `[ 复制一键问 Copilot ]` 的快捷按钮。

## 3. Acceptance Criteria
### User Story 1 & 2 (Timeline 与 透视仪)
- **Given** Engine 正在执行并推流，**When** 一个 LLM Call 结束，**Then** 右侧 Timeline 必须立刻插入一张记录卡片，右上角标明执行耗时（如 `2.3s`）和 Token 消耗。
- **Given** 用户点击了一张 Timeline 卡片，**When** 弹出透视仪面板，**Then** 面板必须提供三个切换 Tab：`Template`, `Variables (JSON 格式化)`, `Rendered (纯文本)`，缺一不可。

### User Story 3 (连线数据包 Edge Inspection)
- **Given** Graph 成功 Predict 到第二步后被挂起或执行完毕，**When** 用户点击第一步和第二步之间的连线（Edge）中心的图标，**Then** 界面右侧或下方滑出一个只读的 Monaco Editor，展示一个由上游写入 Blackboard 的完整 JSON 对象。
- **Given** Context 数据嵌套非常深，**Then** JSON 面板必须支持按层级折叠展开。

### User Story 4 (结构化 Compile 报错)
- **Given** 用户在 Monaco 中写错了 `depends_on` 指向一个不存在的节点，**When** 系统触发 Compile，**Then** 界面下方不仅提示 "Compile Failed"，还必须有一条错误项标明 `Field: depends_on`, `Message: Phase XXX not found`，并且提供一个 `Ask Copilot` 图标。

## 4. 范围 (In Scope vs Out of Scope)
### In Scope
- Timeline (瀑布流时间轴) 组件的交互与数据绑定需求。
- Prompt Inspector (透视仪) 的三面板需求。
- Edge Inspection (连线上的 Context 数据抽屉) 的触发机制。
- Compile 结构化报错在 UI 层的呈现形式。

### Out of Scope
- Canvas 节点本身的放大内联展开（微观拓扑），属于 `canvas-micro-topology-v1` spec。
- 真实的 Golden Baseline 自动化打分算法（那是后续 Evaluate 阶段的任务，本阶段只负责展示数据流）。
- 离线/生产环境的 APM 日志收集（如对接 Datadog，本 spec 仅针对本地 Studio 的开发调试态展示）。

## 5. 依赖与前置条件
- 依赖 `docs/studio/TRACE_AND_VISUALIZATION.md` 确立的基础 UI/UX 精神。
- 依赖前端 `react-use-websocket` 或类似库来稳定处理推流，必须实现断线重连缓冲逻辑。
- 依赖 Engine 后端已经实现了结构化的 Event 发送器 (`apps/studio/backend/app/services/run_manager.py`)。

## 6. 关键约束
- **数据裁剪**: 一些特殊的工具可能返回极长的文本（如 10MB 的网页源码），前端在接收这类 Payload 并展示在 Trace 卡片或 JSON 面板时，必须有截断（Truncate）机制，防止浏览器标签页 OOM（内存溢出）崩溃。
- **响应速度**: Compile 的错误反馈必须在键盘停止敲击后的 500ms 内反映在 UI 上（Debounce 体验）。

## 相关文档
- [TRACE_AND_VISUALIZATION.md](../../../docs/studio/TRACE_AND_VISUALIZATION.md)
- [FRONTEND_UI_SPEC.md](../../../docs/development/FRONTEND_UI_SPEC.md)
- **Given** 用户在断点重试或干预状态下，**When** 引擎执行 resume() API，**Then** 时间轴必须以特殊图标标记这是恢复执行的起点，并在透视仪中展示由用户强行篡改的 payload。
