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
- **代码映射区 (SplitEditor/Monaco)**: 中间主工作区的 SplitEditor / Monaco 编辑器自动跟随高亮当前选中节点相关的 Markdown (`SKILL.md`) 代码。或者用户在 Monaco 中修改代码，画布会实时重绘。 <!-- LAYOUT-VERIFIED 2026-05-19 vs STUDIO_LAYOUT_SPEC §2.4 -->

### 2.2 宏观层：契约与 I/O 黑板
- **全局 Input/Output 节点**: 画布的最左侧和最右侧固定为系统级的 Input 和 Output 节点。
- PM 点击 Input 节点，可以在左侧属性栏 (Properties Panel) 或主工作区的代码区中声明该技能运行所需的初始数据。 <!-- LAYOUT-VERIFIED 2026-05-19 vs STUDIO_LAYOUT_SPEC §2.3 -->
- 点击连线可定义“Context 数据桥接”的流向和映射关系。

### 2.3 微观拓扑展开 (Micro-Topology Unboxing)

为了彻底**消除业务黑盒**，节点的内部运作被设计为可逐级下钻或内联展开的结构。

#### 2.3.1 节点类型与展开行为清单

| 节点类型 | 微观展开支持 | 展开后视觉 | 触发交互 |
|---|---|---|---|
| **Agent** (LLM + Tool loop) | ✅ 支持 | 节点原地膨胀，内部呈现竖向的时间轴列表，展示 Plan, Tool Call, Prompt 等微观执行序列。 | 点击节点下方 `[ + ]` 按钮 |
| **Subgraph** (嵌套技能) | ✅ 支持 | 当前主画布下钻切换为被嵌子技能的完整拓扑图，顶部出现面包屑导航。 | 双击节点 或 点击 `[ + ]` |
| **Logic** (纯 Python 函数) | ❌ 不支持内联 | 不在画布上视觉膨胀。直接在中间主工作区的 Monaco 编辑器中打开对应的 `.py` 源文件。 <!-- LAYOUT-VERIFIED 2026-05-19 vs STUDIO_LAYOUT_SPEC §2.4 --> | 双击节点 |
| **Input / Output** (系统) | ❌ 不支持 | 无变化。属性参数展示在左侧 Properties Panel 中。 | 点击选中节点 |
| **Validator** (校验节点) | ✅ 支持 | 作为 Agent 的附属子节点展开，展示校验规则、报错信息及 Nudge 重试进度。 | 随 Agent 节点一并展开 |

#### 2.3.2 微观 JSON 渲染与视觉 Mockup

当点击 `[ + ]` 展开 Agent-Loop 节点时，节点会在 Canvas 画布中原地膨胀，展示微观执行细节和 JSON 渲染：

```text
┌─ Agent-Loop 节点 [ ContentSummarizer ] ──────────────────────────────────────────────┐
│                                                                                    │
│  ▼ Step 1 (LLM Reasoning) — 2.3s, 1.2k tokens                          [ ✓ pass ]  │
│    {                                                                               │
│      "input": { "raw_article": "React Flow is a library..." },                     │
│      "output": { "intent": "extract_keywords", "next_tool": "web_search" }         │
│    }                                                                               │
│                                                                                    │
│  ▼ Step 2 (Tool: web_search) — 1.1s                                    [ ✓ pass ]  │
│    { "query": "React Flow custom nodes" }                                          │
│    ↳ [ Result: 200 OK (2 KB) ]                                                     │
│                                                                                    │
│  ▼ Step 3 (Validator: Output Schema Check) — Nudge 2/3                 [ 🟡 retry ]│
│    ❌ Error: missing required field 'summary_result'                                │
│    {                                                                               │
│       "message": "Validation failed, initiating nudge...",                         │
│       "retries_left": 1                                                            │
│    }                                                                               │
│                                                                                    │
│  └ [ ▶ Play from here ] [ ⇕ Collapse All ] [ ⎘ Copy JSON ] [ ↗ Open in Monaco ]    │
└────────────────────────────────────────────────────────────────────────────────────┘
```

**视觉与交互规约**:
- **区域**: 在 React Flow Canvas 画布中原地膨胀（Width 从标准的 ~200px 撑开至 ~600px），周围的节点利用 D3/Dagre 布局算法自动推开避让。
- **JSON Viewer 控制**: 
  - 支持层级折叠 (`▼` / `▶`)。
  - 底部动作栏提供全选复制 (`Copy JSON`)、全部收起 (`Collapse All`)。
  - 对于过长（> 1000 lines）的 JSON，自动裁剪，并提供 `Open in Monaco` 按钮在中间主编辑器深度查看。
- **Nudge 计数与报错**: Validator 失败时右侧状态打上醒目的黄底徽章 `🟡 retry` 及重试次数。详细报错红字显示。
- **关闭机制**: 再次点击节点外部的 `[ - ]` 收起按钮，或者按下 `Esc`，节点恢复初始态。展开状态在本地 React Context 保持。

## 2.4 背景 Compile (编译检查)
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
- **瀑布流展示**: 左侧面板切换至 Timeline 面板展开为极其详尽的**竖式 Trace 时间轴**。 <!-- LAYOUT-VERIFIED 2026-05-19 vs STUDIO_LAYOUT_SPEC §2.3 -->
- 详细呈现每阶段 LLM 的 System Prompt (经过注入后的完全体)、User 提问、它选择了调用什么工具、传入了什么参数，以及工具返回的原始响应。

### 4.2 连线数据包点击 (Edge Inspection)
- 在 React Flow 画布中，表示 Context 数据流转的连线（Edges）上，会有流动的小圆点或包裹图标。
- **触发视图 UI**: 在运行时或暂停状态下，PM 点击连线上的数据包图标，界面左侧的属性面板 (Properties) 会切换显示为纯净的 **Context Inspector** 视图。 <!-- LAYOUT-VERIFIED 2026-05-19 vs STUDIO_LAYOUT_SPEC §2.3 -->
- 抽屉内以高亮 JSON 形式展示上一轮执行完毕时，通过该连线从上游传递往下游的完整 Context Dictionary 数据。这能立刻帮助排查“是不是上一步少吐了一个关键字段”。

## 5. 断点干预与重试 (Debug, HitL & Resume)

### 5.1 人工介入点 (Human-in-the-Loop)
- 当底层 Python 工具明确请求人工介入（如询问二选一），或者 Validator 重试次数超限导致异常中断时，时间轴亮起红灯并挂起。
- 画布在该出错节点旁弹出显眼的交互气泡。

### 5.2 状态修改与就地 Resume
- **修改 Context**: PM 打开错误处（比如上一条连线）的 Context 抽屉，直接手动修改有瑕疵的输出 JSON。
- **修改逻辑**: 或者，PM 在中间主工作区打开 Monaco 修改 Prompt，或是修改了报错的 `.py` 代码。 <!-- LAYOUT-VERIFIED 2026-05-19 vs STUDIO_LAYOUT_SPEC §2.4 -->
- **断点续跑**: 修改完成后，PM 在画布上的报错节点旁直接点击专属的 `[ Resume ]` 按钮。
- **底层支持**: 引擎利用 Checkpoint 恢复机制，携带刚刚 PM 修改过的合法数据“原地复活”，继续执行下游节点逻辑。这极大节省了重新运行全量图的 Token 消耗和时间成本。


## 6. 全局设置与模型接入 (Settings & API Keys)

### 6.1 Settings Page 布局叠加
当 PM 在 Toolbar 点击齿轮图标进入 Settings 时，整个主工作区 (`Main Panel`) 将被全屏 Overlay 覆盖。
其中最核心的面板为 **API Keys 管理页**。

### 6.2 Provider 接入与管理
- **卡片式总览**: 界面展示一组 ProviderCards (包含 3 个 Official Vendors 与多个第三方接入商)。
- **添加流程**: PM 点击未配置的卡片，弹出 `AddProviderForm` 侧拉/弹窗界面。
- **探测与测试**: PM 填入 API Key 及可选的自定义 Base URL 后，系统执行 `probe_compatible_sdks` 和模型列表探测，实时通过徽章反馈连通性（成功显示绿灯，并回显获取到的第一个模型名称或可用 SDK 列表）。

## 相关 Spec
- [studio-frontend-v21-multifile-editor](../../.kiro/specs/studio-frontend-v21-multifile-editor/design.md)
