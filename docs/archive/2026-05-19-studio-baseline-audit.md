# Studio Baseline 13 份文档交叉验证 audit (2026-05-19)

## 审计范围 (13 份)
1. `README.md`
2. `docs/architecture/PROD_DEV_SEPARATION.md`
3. `docs/architecture/AGENT_COGNITIVE_ARCHITECTURE.md`
4. `docs/engine/GRAPH_EXECUTION_MODEL.md`
5. `docs/engine/WORKSPACE_AND_FILE_SPEC.md`
6. `docs/engine/LLM_ROUTING_AND_FALLBACK.md`
7. `docs/studio/UX_WORKFLOW_BLUEPRINT.md`
8. `docs/studio/STUDIO_LAYOUT_SPEC.md`
9. `docs/studio/WORKSPACE_FILE_MANAGEMENT.md`
10. `docs/studio/TRACE_AND_VISUALIZATION.md`
11. `docs/development/FRONTEND_UI_SPEC.md`
12. `docs/development/CONTRIBUTING.md`
13. `docs/llm-providers/README.md`

## High 不一致清单 (PM 必看)

### High-001: React Flow 画布 Edges 和 Handles 的样式描述与代码不符
- **类别**: A 代码 vs 文档
- **位置**: `docs/development/FRONTEND_UI_SPEC.md` (第 3 节)
- **不一致内容**:
  - 文档说: `连接线 (Edges): 常态显示为浅灰色（如 zinc-500），在动画状态下（模拟数据流）渲染动态渐变色。` 以及 `连接点 (Handles): 调小尺寸并使其处于隐藏半透状态，只有节点被 Hover 时激活显示`
  - 实际是: 代码 `apps/studio/frontend/src/components/edges/ContextEdge.tsx:37` 和 `GraphCanvas.tsx:155` 中只实现了基础的连线和尺寸覆盖，并没有实现动画渐变色和 Hover 隐藏逻辑。
- **影响**: 开发人员按照 UI Spec 去核对验收时，会认为当前实现是 Bug，并且可能花费不必要的时间去寻找这些并不存在的复杂动画逻辑。
- **修复建议**: 在 `FRONTEND_UI_SPEC.md` 中将这两个特性显式标记为 `[TODO: 设计意图未实现]`。*(注意：我在前几轮的 local 修改中修过一次，但由于跨回合拉取文件，这里再次抛出确保 PM 知晓)*

### High-002: Copilot 渐进式披露的触发条件在架构文档中缺乏精确的前端对接描述
- **类别**: B 跨 spec
- **位置**: `docs/architecture/AGENT_COGNITIVE_ARCHITECTURE.md` (第 5 节) vs `.kiro/specs/copilot-context-design/requirements.md`
- **不一致内容**:
  - 文档说: `AGENT_COGNITIVE_ARCHITECTURE.md` 伪代码里定义了 `build_copilot_session(skill_id, error_log)` 直接加载基础知识。
  - 实际是: 在 `copilot-context-design` spec 中定义了包含 `mentions: [{type: 'file', id: '...'}]` 的复杂前端 Payload。架构文档的伪代码过于简陋，没有体现出前端对具体引用元素的装配。
- **影响**: 后端研发按架构文档写出的 API 无法支撑前端 Spec 中要求的 `@` 提及功能。
- **修复建议**: 修改 `AGENT_COGNITIVE_ARCHITECTURE.md`，使其伪代码接收 `mentions` 数组作为参数。

### High-003: 连线数据包 (Edge Inspection) 点击行为在 Layout 态中缺失具体 Panel 定义
- **类别**: B 跨 spec
- **位置**: `docs/studio/UX_WORKFLOW_BLUEPRINT.md` §4.2 vs `docs/studio/STUDIO_LAYOUT_SPEC.md` §2.3
- **不一致内容**:
  - 文档说: `UX_WORKFLOW_BLUEPRINT.md` 称点击连线数据包后 `界面左侧的属性面板 (Properties) 会切换显示为纯净的 Context Inspector 视图`。
  - 实际是: `STUDIO_LAYOUT_SPEC.md` §2.3 中，`PropertiesPanel` 的包含功能仅仅描述为“当前选中节点的属性”，并未提及它可以切换为 Context Inspector 或者展示连线数据。
- **影响**: 前端在实现 Layout 状态机时，无法确定 Context Inspector 是应该挂载在 PropertiesPanel 组件内部，还是作为一种完全独立的 Panel 态存在。
- **修复建议**: 在 `STUDIO_LAYOUT_SPEC.md` 的 Left Panel 包含功能中，显式加上 `Context Inspector` 的定义。

### High-004: WORKSPACE_FILE_MANAGEMENT 对 `.workspace` 初始化的描述与 Engine 定义有微小边界冲突
- **类别**: B 跨 spec
- **位置**: `docs/studio/WORKSPACE_FILE_MANAGEMENT.md` §2 vs `docs/engine/WORKSPACE_AND_FILE_SPEC.md` §1
- **不一致内容**:
  - 文档说: 前者说 “当 PM 选择一个空文件夹... 隐式创建骨架”。
  - 实际是: 后者说 “系统会初始化如下标准的模板结构... 包含 SKILL.md, .workspace/, script/, references/, golden/”。但目前的后端代码 `FileWatcher` 或相关逻辑并没有自动创建 `script/` 和 `golden/` 这些空目录的代码桩。
- **影响**: 如果只读 `WORKSPACE_FILE_MANAGEMENT.md`，前端以为这只关乎 UI 刷新；读引擎文档则暗示这是深度的文件树模板生成，这会导致功能职责无人认领。
- **修复建议**: 两边必须对齐：究竟是由前端 Tauri `fs` 直接写入脚手架文件，还是调后端一个 `POST /api/skills/init` 接口。建议在 `WORKSPACE_FILE_MANAGEMENT.md` 中明确调用后端 API。

## Medium 不一致清单 (PM 自行决定要不要修)

### Medium-001: "Code-only (Logic)" 节点的执行方式描述模糊
- **类别**: B 跨 spec
- **位置**: `docs/architecture/AGENT_COGNITIVE_ARCHITECTURE.md` §3 vs `docs/engine/WORKSPACE_AND_FILE_SPEC.md` §2
- **不一致内容**: 架构图称其为 "Code-only" 纯 Python 流水线，但在文件规范中只详细定义了挂载在 `<tools>` 下的函数，并未明确 Code-only 阶段主函数是如何指定的（例如是用 `<tool>` 还是 `<script>` 标签）。
- **影响**: 编写 SKILL.md 缺乏精确的语法指导。
- **修复建议**: 在 `WORKSPACE_AND_FILE_SPEC.md` 补齐 Logic 节点的 XML 示例。

### Medium-002: Split Editor Focus 状态未在 Layout Spec 中作为全局状态体现
- **类别**: B 跨 spec
- **位置**: `.kiro/specs/split-editor-focus-enhancement/requirements.md` vs `docs/studio/STUDIO_LAYOUT_SPEC.md`
- **不一致内容**: 虽然在新出的增强 Spec 中定义了 `activeFocusSide` 属于全局上下文，但 `STUDIO_LAYOUT_SPEC.md` 的状态机部分未能反射这一重要的 UI 指针。
- **修复建议**: 可修可不修。因为 Spec 已说明它只是一个组件变体，不升格为 Layout State，但写上去更严谨。

## Low 不一致清单 (FYI)

### Low-001: 拼写不一致
- **类别**: C 内部
- **位置**: `docs/development/FRONTEND_UI_SPEC.md`
- **不一致内容**: `shadcn` 有时写为 `shadcn/ui`，有时写为 `shadcn`。
- **修复建议**: 统一为 `shadcn/ui`。

## 统计

- 总 audit 行数: 1391 行
- High: 4
- Medium: 2
- Low: 1
- 类别分布: A=1 B=5 C=1

## 我没把握的地方 (PM 决策)

- **关于 High-004 的职责归属**：`.workspace` 及其配套的 `SKILL.md` 空模板在初始化时，是由前端 Tauri 直接写盘，还是通过请求后端 API 来生成？我倾向于后端 API（因为需要建 SQLite DB 等），需要 PM 拍板以修改文档。
