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

## 1. 发现与初始化 (主页与专注区隔离)
- **极简入口**: Studio 打开后首屏仅提供“最近项目”和“新建/打开文件夹”按钮。
- **专注工作区 (Skill Workspace)**: 一旦选定 Skill，整个界面进入强隔离模式，左侧边栏 (Assets Panel) 仅展示该 Skill 的内部文件结构，摒弃全局导航带来的干扰。

## 2. 节点宏观/中观/微观编辑 (I/O 与拓扑配置)
提供左右分屏体验：
- **画板 (React Flow)**: PM 在左侧拖拽连线，点击节点配置输入/输出。
- **代码映射 (SplitEditor)**: 右侧的 Monaco 编辑器自动跟随高亮。
- **微观展开**: 双击复杂 Agent 节点或点击 `+` 能够直接在界面上浮出底层 Python 脚本或 Agent 内循环的只读面板，消除黑盒。
- **交通警察 Compile**: 任何时刻编辑，背景都在执行 Compile，右下角的 `[ Predict ]` 按钮仅在 100% 校验通过后绿灯放行。

## 3. 预测与 Golden 基线打磨 (分支打磨流)
- **Predict 跑通**: 用 Mock LLM 执行整个拓扑，获取纯粹数据组装层的假数据。
- **Golden 打磨**: 将 Predict 或真实 Run 跑出的结果，与期望状态并排比对。PM 结合 Copilot，手工润色这份数据，保存为 `Golden Baseline`，供后续评测做锚点。

## 4. 真实运行观测 (Timeline 瀑布流)
- 点击 `[ Run ]` 后，界面上方或右侧展开**流式 Trace 时间轴**。
- 以极其细致的颗粒度，呈现每一阶段 LLM 的回复、它调用了什么工具、以及系统触发了多少次 Nudge 纠偏。

## 5. 断点干预与重试 (画布级别 Resume 逻辑)
- 当发生 Validator 抛错或 Python 代码崩溃时，运行暂停挂起。
- **就地修改**: PM 可以打开刚才错误处的数据，手工修改（如直接篡改有瑕疵的输出 JSON），或者改掉有 BUG 的 Python 代码。
- **断点续跑**: 在画布上的报错节点旁直接点击 `[ Resume ]`，引擎利用 Checkpoint 拿着修复后的数据原地复活，极大节省重跑成本。

## 相关 Spec
- [studio-frontend-v21-multifile-editor](../../.kiro/specs/studio-frontend-v21-multifile-editor/design.md)
