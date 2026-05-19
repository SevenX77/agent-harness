---
status: Living
target_goal: "定义 PM 在 Studio 桌面端开发与调试 Skill 的端到端标准用户旅程"
linked_code_paths:
  - apps/studio/frontend/src/components/studio/Workspace.tsx
linked_specs:
  - .kiro/specs/studio-frontend-v21-multifile-editor/
last_updated: 2026-05-19
---

# Studio 用户工作流蓝图 (UX Workflow Blueprint)

## 1. 发现与初始化 (Discovery & Initialization)

### 1.1 主页与专注区隔离
- **极简入口**: Studio 启动后的首页是一个类似于集成开发环境 (IDE) 的极简启动界面，核心提供三个入口：
  - **Recent Skills**: 列出最近打开过的技能项目列表，支持单次点击恢复完整的项目状态。
  - **Open Skill Folder**: 调起原生系统文件选择器，选定本地已有的 Skill 文件夹。
  - **New Skill**: 提供新建向导，在本地磁盘选定位置创建并自动初始化 `.workspace` 环境。
- **操作心智**: 这里的核心心智是将操作系统的文件管理和 Studio 的加载能力紧密结合。支持**直接从操作系统的文件管理器中将一个文件夹拖拽进入 Studio 界面**来打开项目。
- **专注工作区 (Skill Workspace)**:
  - 一旦通过以上任意方式选中并打开了一个 Skill，Studio 立即进入**专注工作区模式**。
  - 左侧边栏（Assets Panel）完全切换为仅展示当前选中 Skill 目录下的文件结构（隐藏其他任何系统级导航），让 PM 的精力完全聚焦在当前正在开发的技能任务上。

### 1.2 拖拽交互规约
- 当用户拖入一个包含 `.workspace` 的合法 Skill 文件夹时，系统验证文件结构并在画布中渲染拓扑。
- 当用户拖入一个未经格式化的普通文件夹时，触发“隐式初始化”流程（参见 [WORKSPACE_AND_FILE_SPEC.md](../engine/WORKSPACE_AND_FILE_SPEC.md)）。

## 2. 节点宏观/中观/微观编辑 (Editing & Topology)

### 2.1 画布优先的分屏体验
进入 Workspace 后，主要界面区域采用左右（或上下）的响应式分屏系统：
- **核心画板 (React Flow Canvas)**: PM 可以在画布上直观地进行节点的拖拽、连线、和布局排列，配置输入与输出。
- **代码映射区 (SplitEditor/Monaco)**: 右侧的 Monaco 编辑器自动跟随高亮当前选中节点相关的 Markdown (`SKILL.md`) 代码。或者用户在 Monaco 中修改代码，画布会实时重绘。

### 2.2 宏观层：契约与 I/O 黑板
- **全局 Input/Output 节点**: 画布的最左侧和最右侧固定为系统级的 Input 和 Output 节点。
- PM 点击 Input 节点，可以在右侧属性栏或代码区中声明该技能运行所需的初始数据。
- 点击连线可定义“Context 数据桥接”的流向和映射关系。

### 2.3 微观拓扑展开 (Micro-Topology Unboxing)
为了彻底**消除业务黑盒**，复杂的 Agent 节点内部的运作被设计为可逐级下钻的结构。
- **交互动作**: 画布中的复杂节点（如包含多次 Tool 调用和思考的 Agent-Loop 节点，或者嵌套 Subgraph 节点）下方提供了一个明显的 `[ + ]` 展开按钮。
- **UI 状态机切换**:
  - 点击 `[ + ]`，该节点在画布中原地膨胀，展开为一个“内嵌的微型画布”或者“详细步骤时间轴”。
  - **微观 JSON 渲染**: 展开后的内部结构会展示每一次子调用的详细 Request/Response，采用纯净的 JSON Viewer 进行渲染，提供格式化和折叠功能。
  - **逻辑节点下钻**: 对于纯粹执行 Python 函数的 Code-only (Logic) 节点，双击节点直接在右侧唤起 Monaco 编辑器，定位并打开对应的 `.py` 源文件。
  - **Nudge 计数标示**: 在微观展开中，如果发生了 Validator 失败导致的纠偏 (Nudge)，会在步骤旁边用显眼的红/黄警示色圆点显示**重试计数**（例如：`Nudge: 2/3`），清晰标明大模型纠错的激烈程度。

### 2.4 背景 Compile (编译检查)
- “交通警察”机制：PM 的任何按键输入或连线修改，都会触发后台的静默 Compile。
- 当且仅当右下角状态指示灯全绿（无语法错误、无 I/O 断流）时，底部的 `[ Predict ]` 与 `[ Run ]` 按钮才会解锁。

## 3. 预测与 Golden 基线打磨 (Predict & Baseline)

### 3.1 空转预测 (Predict 机制)
- 在烧毁真实的 LLM Token 之前，PM 需要验证整个计算图的数据流是否通畅。
- 点击 `[ Predict ]` 按钮，引擎采用 `Mock LLM` 模式执行整个拓扑，跳过所有真实的大模型 API 请求，获取纯粹数据组装层的假数据。
- 这一步确保所有的 Python 工具能够正常接收和返回预期类型的数据。

### 3.2 Golden 打磨与锁定
- 当 Predict (或真实 Run) 成功跑出结果后，界面进入**双屏对比打磨视图**。
- 左侧展示本次执行产生的“拟真或实际输出”，右侧为供 PM 编辑的 `Golden Baseline` 面板。
- PM 可以结合右侧滑出的 Copilot 对话框，针对当前结果的不足提出修改指令，不断将其润色为一份“完美的期望数据”。
- 润色满意后，点击 `[ Save as Golden ]`，该数据将被锁定并隔离存储至当前 Skill 目录的 `golden/` 子文件夹中，作为未来回归测试和性能评估的绝对锚点。

## 4. 真实运行观测 (Run & Trace)

### 4.1 Trace 瀑布流交互
- PM 确信图逻辑没问题后，点击底部的 `[ Run ]` 开始真实调用大模型。
- **瀑布流展示**: 界面上方（或右侧切 Tab）展开为极其详尽的**竖式 Trace 时间轴**。
- 详细呈现每阶段 LLM 的 System Prompt (经过注入后的完全体)、User 提问、它选择了调用什么工具、传入了什么参数，以及工具返回的原始响应。

### 4.2 连线数据包点击 (Edge Inspection)
- 在 React Flow 画布中，表示 Context 数据流转的连线（Edges）上，会有流动的小圆点或包裹图标。
- **触发抽屉 UI**: 在运行时或暂停状态下，PM 点击连线上的数据包图标，界面右侧或底部会滑出一个纯净的 **Context Inspector 抽屉**。
- 抽屉内以高亮 JSON 形式展示上一轮执行完毕时，通过该连线从上游传递往下游的完整 Context Dictionary 数据。这能立刻帮助排查“是不是上一步少吐了一个关键字段”。

## 5. 断点干预与重试 (Debug, HitL & Resume)

### 5.1 人工介入点 (Human-in-the-Loop)
- 当底层 Python 工具明确请求人工介入（如询问二选一），或者 Validator 重试次数超限导致异常中断时，时间轴亮起红灯并挂起。
- 画布在该出错节点旁弹出显眼的交互气泡。

### 5.2 状态修改与就地 Resume
- **修改 Context**: PM 打开错误处（比如上一条连线）的 Context 抽屉，直接手动修改有瑕疵的输出 JSON。
- **修改逻辑**: 或者，PM 打开右侧 Monaco 修改 Prompt，或是修改了报错的 `.py` 代码。
- **断点续跑**: 修改完成后，PM 在画布上的报错节点旁直接点击专属的 `[ Resume ]` 按钮。
- **底层支持**: 引擎利用 Checkpoint 恢复机制，携带刚刚 PM 修改过的合法数据“原地复活”，继续执行下游节点逻辑。这极大节省了重新运行全量图的 Token 消耗和时间成本。

## 相关 Spec
- [studio-frontend-v21-multifile-editor](../../.kiro/specs/studio-frontend-v21-multifile-editor/design.md)
