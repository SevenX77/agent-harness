# Node 5: 调试与干预 (Debug, HitL & Resume)

## 1. 业务目标
处理长流程 Skill 运行时的异常情况。Skill 可能因为 Validator 校验不通过、Python 代码抛错，或者由于配置了人工接入点（Human-in-the-loop）而暂停。PM 需要在这里进行干预并恢复执行，而不是每次都从头重跑（浪费 Token 和时间）。

## 2. 交互场景与 UX 设计

### 场景 A: 人工干预点 (Human-in-the-loop)
- **触发**: 底层 Python 工具执行了 `request_human_input()` 或 `ask_clarification()`。
- **UI 表现**:
  - Timeline 暂停，顶层弹出显眼的提问框（例如：“Agent 问：文案用词选方案 A 还是 B？”）。
  - 提供文本输入框或选项。
- **操作**: PM 输入答案后，点击 **[ Resume ]** 按钮，系统将答案作为 `ToolMessage` 注入，Graph 从断点继续向下流转。

### 场景 B: 断点修复与续跑 (Breakpoint & Resume)
- **触发**: 某个 Phase 运行失败（如 Validator 重试超限，或报错），Skill 停止。
- **UI 表现**:
  - Timeline 停在错误节点，亮红灯显示具体的 Error Message。
  - **核心设计: 节点级 Resume**: `[ Resume ]` 按钮**不是全局的**，而是直接显示在画布上的**具体节点**旁边。
- **操作逻辑**: 
  - PM 可以在代码区修改 Prompt 或外部修改 Python 代码。
  - 改完后，PM **点击图上某个节点的 `[ Resume ]`**。系统就会精准地从这个位置开始跑，并使用该节点之前的已有数据（Checkpoint）。
  - **脏状态失效 (Dirty State Invalidation)**: 系统会严格判断依赖关系。如果 PM 修改了图的拓扑（例如删除了某个前置节点），那么所有受影响的后续节点旁边的 `[ Resume ]` 按钮会自动消失/置灰。只有存在合法前置数据的节点，才允许弹出 Resume。

### 场景 C: Context "大黑板"的强制篡改 (Raw JSON Edit)
- **业务需求**: PM 发现某个阶段的输出有点瑕疵，导致下游报错。他不想改 Prompt 重跑该阶段，只想立刻“把这个瑕疵值改掉”试试下游逻辑。
- **操作逻辑**:
  - PM 点击画布上两个节点之间的**连线圆点 (Edge Dot)**，展开上一轮跑完的 Context 数据。
  - **直接篡改**: 界面提供一个纯净的 Monaco JSON Editor。PM 直接在里面手写修改这段 JSON（例如把 `{"result": "坏消息"}` 改成 `{"result": "好消息"}`）。
  - 修改保存后，点击下游节点的 `[ Resume ]` 按钮，系统就会拿着这段“伪造”的数据继续往下跑下游 Phase。

## 3. 下游流转
- 成功 Resume 并跑完全程后，进入 **[06_EVAL_AND_PUBLISH](./06_EVAL_AND_PUBLISH.md)** 进行最终评估。
