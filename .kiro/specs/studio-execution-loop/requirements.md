# Requirements: Studio Execution Loop

## 目标 (Target Goal)
> 让 PM 可用 — 不开终端、不写 YAML、不拼目录，在 Studio 里可视化地写、改、跑 V2.1 skill，跑完能清楚看到每个 phase 的输入输出。

## 用户场景与验收标准 (User Scenarios & Acceptance Criteria)

### 1. 运行时轨迹追踪 (Execute & Trace)
- **场景**: PM 在右侧面板填入测试参数并点击 "Run" 后，希望实时看到引擎正在做什么，而不需要盯着黑框终端。
- **验收标准**:
  - 右侧 Trace tab 不再显示 "Waiting for run events"，而是随执行进度实时填充事件流行。
  - 事件必须包含清晰的类型（如 Phase Start, LLM Call, Tool Call, Phase End）。
  - PM 能够展开每个 Phase 的事件，查看其上下文 (Context)、发给 LLM 的具体 prompt 以及大模型的原始返回内容。

### 2. 画布状态联动 (Visual Run Status on Canvas)
- **场景**: 看着一堆文本日志不够直观，PM 希望看图就知道哪个节点卡住了或正在运行。
- **验收标准**:
  - 当一个 Phase 正在执行时，Canvas 上对应的节点要有明显的视觉反馈（如边缘呼吸灯或高亮色）。
  - 当一个 Phase 成功结束，节点状态变绿；如果发生报错（Error / Validation Fail 阻断），节点标红并在 Hover 时能看到简要报错原因。
  - 当运行结束（或切换查看历史 Run），画布整体状态需与该次 Run 的最终状态一致。

### 3. 执行历史回溯 (Run History)
- **场景**: PM 昨天跑了一个效果很好的用例，今天想调出来对比一下。
- **验收标准**:
  - History tab 能准确列出当前 skill 过去的所有执行记录（时间、状态、成功/失败）。
  - 点击某一条历史记录，Trace tab 和 Canvas 会立刻恢复到那次执行的状态供回放查看。
  - 关闭重启 Studio 后，历史记录不丢失。

### 4. 核心体验打磨 (Polish & Fixes)
- **场景**: 现有的几个小 bug 让人觉得 Studio 是个毛坯房，容易干扰正常的测试心智。
- **验收标准**:
  - 启动 Studio 时，不再无故弹出版权/冲突的 Modal（消除状态泄漏）。
  - 切换 skill 时，Toast 提示需合并，不遮挡大面积屏幕。
  - 底部不再长时间卡着 "Studio event stream disconnected" 报错，断线能够自动静默重连。
