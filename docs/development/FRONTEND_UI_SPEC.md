---
status: Living
target_goal: "前端模块化组织原则 + UI 组件基准规范 + 画布/拖拽/Tauri 桥接最佳实践"
linked_code_paths:
  - apps/studio/frontend/src/components/studio/Panels.tsx
  - apps/studio/frontend/src/components/studio/SettingsPage.tsx
  - apps/studio/frontend/src/index.css
  - apps/studio/frontend/src/components/ui/
  - apps/studio/frontend/src/lib/tauri.ts
linked_specs:
  - .kiro/specs/_archive/studio-uikit-redesign/
last_updated: 2026-05-24
---

# 前端模块化与 UI 规范 (Frontend Modularity & UI Spec)

## 1. 前端模块化组织原则 (Module Hygiene)

在过往的快速迭代中，前端堆积了严重的“多组件挤一文件”反模式（如 `Panels.tsx` 超过 500 行，容纳了 5 个完全不相关的面板组件）。为了保障可维护性，从现在起确立以下重构与开发红线：

### 1.1 一文件一组件 (Single Component per File)
- **核心原则**: 每个 `.tsx` 文件应当只默认导出一个（或命名导出一个）核心的 React 组件。
- **例外豁免**: 仅供该核心组件局部使用的子渲染函数（如 `function FileRow()` 仅在 `AssetsPanel` 中被使用）或微型组件（总行数 < 50 行），允许生存在同一个文件中。但严禁在同一文件中导出（Export）多个平级的业务组件。

### 1.2 物理阈值拦截 (warning, 非阻塞)
- **200 行软提示**: 开发者应考虑是否混入了过多状态管理或子级渲染逻辑。
- **400 行 ESLint warning**: 文件突破 400 行时, ESLint 触发 warning (编辑器红线提示), 但**不 阻塞 PR / 不 build fail**。已存在的超阈值文件作为技术债清单 (见 §1.4) 排期重构, 不需立即修复 。
- **理由**: 强制 error 业界少数派 (一旦触发开发者倾向加 `/* eslint-disable max-lines */` 注释 escape, 反成反模式), warning + code review 把关是业界主流 (参考 Material UI / Airbnb / Google style guide)。
- **后续**: 实际 ESLint 配置 (`eslint.config.js` 加 `max-lines: ['warn', 400]`) 跟拆代码任务 一起实施。

### 1.3 拆分与目录策略 (Feature-Based Directory)
我们采用按 **Feature (功能域)** 划分的目录结构，拒绝扁平的 `components/` 堆砌：
- 当一个文件需要拆分时，应原地升级为以功能命名的目录，例如将 `Panels.tsx` 拆分为：
  ```
  components/studio/panels/
  ├── index.ts
  ├── AssetsPanel.tsx
  ├── InputPanel.tsx
  └── PropertiesPanel.tsx
  ```
- **文件命名**:
  - React 视图组件（包含 JSX）：必须使用大驼峰 `PascalCase.tsx`。
  - 纯逻辑 / 工具 / Hooks 文件：使用烤肉串格式 `kebab-case.ts`。

### 1.4 反模式示例 (需优先重构清单)
以下是全量扫描后列出的高优技术债（按优先级降序）：
1. **`components/studio/Panels.tsx`** (530行) 包含 `AssetsPanel`, `InputPanel`, `TimelinePanel`, `PropertiesPanel`, `Panels` 5个不相关的顶级业务面板。需拆分为 `panels/` 目录。
2. **`components/studio/SettingsPage.tsx`** (1017行) 混杂了设置大壳、`SettingsPageContent` 以及极其复杂的 `LlmRolesTab` 和 8 个处理数据流的纯逻辑 util 函数。不仅违反了组件单一原则，还混入了纯逻辑。需拆分为 `settings/` 目录，并将数据操作函数抽出为 hooks 或 API utils。
3. **`components/GraphCanvas.tsx`** (632行) 混杂了主画板 `GraphCanvas`、具体节点渲染器 `SkillNode` 以及边构建逻辑 `buildEdges`。应将具体节点抽出至 `components/nodes/` 目录下。

## 2. UI 组件与样式基准规范

Studio 定位为沉浸式的极客生产力工具。在构建桌面级复杂工具时，统一的设计系统是效率的保障。UI 视觉规范继承于我们早期的重构成果，并由本基准文件实施长期仲裁。

### 2.1 依赖体系与组件复用
- **基础库选型**: 抛弃内联 CSS 和手写类名，全面基于 `TailwindCSS v4` 配合无头组件库 [`shadcn/ui`](https://ui.shadcn.com/) (官方主页) / [组件文档](https://ui.shadcn.com/docs/components)。
- *(新)* 诸如 `AlertDialog`, `RadioGroup` 等新增组件，必须优先从 `shadcn` 统一引入，并统一落户在 `src/components/ui/` 目录下。
- **严禁重新发明轮子**：业务代码中如需模态框，必须复用 `ui/dialog.tsx`，除非有极为特殊的交互理由，才允许手写封装。

### 2.2 样式 Token 化 (Design Tokens)
**本项目样式真实来源**: shadcn `radix-mira` preset (preset id `b38miVIYq`, style `mira`, theme `indigo`), 可直接预览 demo: <https://ui.shadcn.com/create?preset=b38miVIYq&template=vite&pointer=true&rtl=true>。
- **核心风格**: deep indigo-violet primary on neutral grays, light + dark mode, 0.625rem radius, Inter Variable + JetBrains Mono Variable fonts, lucide icons。
- 设计 tokens 已 100% 推导自 demo computed CSS, 详细 token 矩阵见 [`.kiro/specs/_archive/studio-uikit-redesign/tokens.md`](../../.kiro/specs/_archive/studio-uikit-redesign/tokens.md), 当前已沉淀至本地主题 CSS (`apps/studio/frontend/src/index.css`)。
- **颜色原则**: 开发人员写新组件时, **严禁 Hardcode 任何十六进制颜色码或 Tailwind 具体色值** (如 `bg-gray-800`)。必须使用语义化的 CSS 变量类 (如 `bg-background`, `text-muted-foreground`, `border-border`)。

### 2.3 暗黑极客主题 (Dark Theme Only)
默认强制并专注于高对比度的暗色环境，营造专业生产力环境，不要求完美兼顾白昼模式的降级体验。
- 背景底色: `bg-background` 使用 `zinc-950`，制造沉浸深度感。
- 边框与分割线: `border-border` 使用 `zinc-800`。

### 2.4 圆角原则
为保持极客硬朗感，应用圆角不得超过 `rounded-md` (0.375rem)，杜绝大圆角的“消费端”圆滑感。视觉一致性约束包含全局组件（包括浮动弹窗和侧边栏），严禁引入过度活泼的大圆角元素。

### 2.5 表单与页面宽度
- Settings 类表单必须优先使用本地 shadcn `Field` 组件组织字段（`FieldSet` / `FieldGroup` / `Field` / `FieldLabel` / `FieldDescription`），不要在业务组件里手写 label-description-control 三段式布局。
- Settings 表单默认遵循 Endpoints 页的交互：字段变更实时保存并显示保存状态；除非是明确的事务型提交，不要放独立 `Save` 按钮。
- 后端探测/测试响应只能合并后端拥有的诊断字段，例如 `status`、`last_test_at`、`last_test_message`、probe capability 结果；不能用较旧响应覆盖用户仍在编辑、尚未 autosave 完成的本地表单字段。
- 输入框的 `value` 必须同步当前实际值；placeholder 只做空状态提示，不能承载当前路径、密钥、配置值等真实数据。不要在输入框下方重复显示同一个字段值。
- 页面内容区需要设置响应式最大宽度，避免表单、文本和卡片在超宽窗口里被横向拉得过长；数据密集型列表可按具体信息密度单独放宽。
- Settings 页面中用于归类列表的同级内容分区应统一使用本地 `CatalogAccordion`，例如 Endpoints 的 endpoint groups 和 LLM Roles 的 `Graph Agent Roles` / `Copilot Roles`；普通探测或表单内折叠继续使用基础 `Accordion`。空分区也要保留可见的 catalog header 和简短 empty state，避免用户误以为分类缺失。分区标题使用 Title Case，展开/收拢指示箭头放在标题前方，业务分类 icon 放在标题文本后方，并与首张内容卡保持清晰垂直间距。
- 删除确认必须复用本地 `DeleteConfirmDialog`，不要在各业务组件里分别使用 `window.confirm`、toast action 或手写 `AlertDialog` 文案；确认按钮统一使用 destructive variant。

### 2.6 桌面工具布局与滚动区域
- Settings 内部的标题、说明和主要内容必须作为一个整体进入对应内容区；不要把 header 和 main 做成割裂的同级结构，导致标题不随内容滚动或视觉归属不清。
- 主内容和侧栏内容应明确分工：主区域可以独立滚动，侧栏可以 sticky/fixed 并在自身内部滚动。不要让页面级滚动、主区滚动和侧栏滚动互相抢空间。
- 数据密集型侧栏（例如模型库、资源列表、引用列表）应避免外层再套装饰性 Card；侧栏本身是布局区域，只有单个 repeated item、弹窗或真正独立的工具面板才使用 Card。
- `ScrollArea` 不应让 scrollbar 占用内容宽度；需要隐藏 scrollbar 时使用本地 `ScrollArea` wrapper 的 slot selector，且必须验证内容宽度没有被挤压。
- 任何固定宽度或最小宽度都必须有响应式约束。窄面板下卡片、ring、badge、按钮和长文本不能横向溢出，也不能被父级裁掉关键反馈。

### 2.7 卡片、选中态与即时反馈
- 交互卡片统一使用语义 surface：`bg-card`、`rounded-md`、`ring-inset`、`ring-1 ring-foreground/10` 等既有 token/variant。不要为单个页面创造另一套 card 外观。
- Hover 反馈优先使用背景色变化（如 `hover:bg-muted/...`），不要用 hover 边框高亮制造跳动或与选中态冲突。
- 选中态必须保留明确高亮（例如 `data-[selected=true]` + selected ring/background），且反馈要在 pointer down/click 后即时发生。长列表中如果 React state 更新造成体感延迟，应采用局部 ref/DOM attribute 或等价轻量方案，但不能牺牲可访问状态。
- 选中后只展开用户需要的信息；不要在卡片里加入额外复杂详情区，除非产品需求明确要求。
- 图标、按钮和徽章要使用 lucide + 本地 `Button`/`Badge` wrapper；文本型按钮只用于清晰命令，不用于图标已有行业惯例的动作。

### 2.8 输入框、搜索与行内动作
- 带图标、清空、复制、显示/隐藏等行内动作的输入框，优先使用本地 `InputGroup` / `InputGroupButton` / `InputGroupAddon`。不要用绝对定位按钮硬盖在 `Input` 上；这种做法容易被 input 拦截点击，也更难保证窄宽度布局。
- 搜索框应支持清空操作：有 query 时显示清空按钮，清空后恢复列表并把焦点放回搜索输入框。
- 搜索结果数量应在标题附近展示，让用户知道当前 filter 后剩余多少项。
- 搜索匹配在数据密集列表中应尽量宽容：支持名称、分组、provider/vendor 等关键字段，并避免 `-`、`.`、空格等符号成为强制精确匹配门槛。

### 2.9 数据密集列表与 Badge Overflow
- 数据密集列表中的标签必须尽量可读。不要把每个 Badge 单独截成 `Ope...` 这类不可识别文本。
- 多标签行的通用模式是：展示能稳定放下的完整标签，末尾用 `+N` overflow badge 表示剩余项；选中或展开后再展示完整标签集合。
- Badge 文本使用真实 label，不使用临时缩写。模型、provider、vendor 等实体名必须展示准确名称。
- Role / model / provider 这类层级编辑器不得把内部短码（如 `GM31P`、`CLO47T`）作为可见主标签；短码只用于持久化 key 或调试上下文。模型行展示模型真实名称，Provider 行只展示 provider 名称，不展示派生标题或 provider model id 副标题。
- Role fallback chain 只能保存后端返回的精确 `route_id`；UI 不得从 provider model id、display name 或 provider brand 推导执行目标。
- 从 Available Routes 拖入 role 时，拖拽 payload 必须携带 exact `route_id`，并保持后端 DTO 中的 canonical/provider/status 字段只读展示；未知 route 由后端拒绝保存。
- 添加 role route 使用右侧 Available Routes 的拖拽源和本地 shadcn `Empty` drop target；不要提供与 route registry 割裂的 Add model select。
- 添加 Role 必须先通过本地 shadcn `Dialog` + `Field` 输入 role name，创建后的 role 是可保存的空草稿，不自动塞入默认 model/provider；保存前必须归一化掉空草稿或 orphan draft model 上的 stale `active_model`，并取消会读取 invalid ref 的既有 autosave；role name 必须可从 role 的三点 action menu 修改。
- Provider 添加入口使用与 provider row 等宽等高的 ghost `DropdownMenu` trigger；没有可添加 provider 时不显示占位按钮。
- Route fallback row 数量超过一个时使用响应式横向 grid，添加 route 的 ghost trigger 作为 grid 最后一项；route card 必须同时设置最小列宽和最大列宽，少量 route 不要横向撑满整行；不要回退到纵向堆叠或单独 select。
- Provider 名称在 row 内必须单行省略并配 Radix Tooltip 展示完整名称，避免窄卡片中把 provider label 拆成两行。
- Role list 和 Available Routes 这类可能很长的设置列表必须渐进渲染，保持搜索/计数完整，同时用 sentinel 自动加载后续批次。
- Role list 必须按用途分区展示，当前分为 `Graph Agent Roles` 与 `Copilot Roles`；每个分区底部都要提供对应的 `Add Graph Agent Role` / `Add Copilot Role` 入口，并与下一段分区保持明确垂直间距。Graph Agent 分类与 role icon 使用 engine/cog 语义图标，role 标题行需要使用默认字体，整行 controls 必须垂直居中对齐；编辑和删除等 role 级动作统一收进标题右侧的三点 `DropdownMenu`，删除必须使用统一 `DeleteConfirmDialog` 二次确认。
- Tauri/WebKit 下非编辑区双击可能触发原生文本选择命令，导致 macOS `Edit` 菜单闪烁或系统提示音；应用根部必须保留全局 double-click guard，在非输入、非 `contenteditable`、非 Monaco 区域阻止原生默认选择行为和 `selectstart`，并用 CSS 将普通 chrome 设为不可文本选择；但不能阻止事件冒泡，以免破坏业务组件自己的 `onDoubleClick`。确实需要保留原生双击选择的区域使用 `data-allow-native-double-click` 标记。Tauri macOS shell 不使用默认菜单，且自定义 app menu 不添加原生 `Edit` submenu；普通 input/textarea 的 `Cmd+V` / `Ctrl+V` 由前端 editable paste fallback 接管，避免为了粘贴恢复原生 Edit 菜单而重引入双击系统提示音。
- Role 级三点菜单这类 hover-adjacent action 必须把鼠标双击视为 no-op，键盘打开菜单仍需保留。
- LLM Roles autosave 必须串行化并忽略被更新快照 supersede 的旧请求结果；当用户创建空 role 或拖入模型后，旧的 400 不应覆盖新的 pending/saved 状态或弹出陈旧 toast。
- 层级编辑器必须用不同 shadcn surface/variant 区分层级，例如外层 role 用 `Card`，可排序 model/provider 行用 `Item` 的不同 variant，并且只使用语义化 token。
- 排序交互优先使用整行拖拽表面，不额外展示上下移动按钮或独立拖拽标签；设置、删除等行内动作必须阻止拖拽冒泡，保证点击目标可靠。
- 可拖拽的 route 和 route 库卡片必须使用 `select-none`，避免拖拽时选中文字；从 Available Routes 添加 route 时，drop handler 应覆盖整个 role card，Empty 只作为视觉 target，拖拽过程中 role header 的 Edit 等非 drop action 不应抢 hover/click。跨 role card 拖拽时必须用透明 drop shield 覆盖 header 操作，并在 pointerup 后吞掉该次合成 click，避免 Dialog trigger 在拖拽结束瞬间闪开。不要把跨区域添加依赖在 native HTML5 drag/drop 上；Tauri/WebKit 下 `dragstart`/`dataTransfer.types` 不稳定，应保留 pointer 坐标命中 drop zone 的 fallback，并同时渲染跟随指针的 drag preview，避免交互看起来像静态点击。
- 长模型名、路径和 id 使用 `overflow-wrap:anywhere` / `break-words` 等方式在卡片内换行；不要让文本把卡片撑破。
- 如果列表来自外部探测或后端缓存，UI 不应写死样例数据。模型库类 UI 应展示已测试并持久化的数据源，按 vendor/provider 等真实字段归类。
- LLM Provider Intelligence V2 之后，Available Routes 的 `canonical_id`、vendor/provider 分组、route availability 和 provider ownership 均来自后端 DTO；前端不再从 raw model string 做 canonicalization、provider ownership inference 或 stale provider pruning。

### 2.10 前端验证要求
- 修改 `apps/studio/frontend` 的用户可见 UI 后，完成前必须亲自启动或连接本地页面，实际打开、点击、输入相关流程，并检查桌面/窄面板等关键宽度下是否穿模、截断或布局错位。单测和 typecheck 不能替代这一步。
- 必须覆盖被改动的主成功路径和明显的取消/清空/错误/空状态。对于搜索、选择、复制、显示/隐藏、展开/折叠等交互，要逐一点击验证。
- 手动验证应包含窄宽度视口。至少检查页面级、侧栏级、卡片级没有横向溢出；选中 ring、hover/active、badge overflow 和按钮点击目标不能被裁剪或被其它元素拦截。
- 如果变更涉及 Tauri 文件系统能力（目录选择、Reveal、终端、外部编辑器等），必须在 Tauri 环境或等价的 Tauri bridge 路径下验证，不能只用普通浏览器 fallback 得出结论。

## 3. GraphCanvas 画布样式覆写
原生的 `@xyflow/react` 深色主题仍带有较重的网页感，在 `GraphCanvas` 组件和全局 `index.css` 中进行了覆写：
- **默认布局对齐**: 单链或可直线化的默认流程（例如 `Input -> init -> Output`）必须采用节点中心点坐标作为布局基准，并让左右 handle 在同一水平中心线上；同一水平线的连接边应渲染为直线路径，避免无意义的 Bezier 弯线或 IO 节点与 phase 节点上下错位。
- **节点选择反馈**: 单击 skill node 必须立即打开左侧 `Properties` panel 并同步选中态；双击继续用于打开对应 phase 文件。左侧工作区工具栏顺序固定为 `Assets`, `Properties`, `Input`, `Trace Timeline`, `Local History`，避免节点检查路径被埋在第三顺位之后。
- **Canvas authoring 文件驱动**: 画布上的新建 phase、属性编辑、节点连线都必须先写入 phase 文件或 `GRAPH.md`，再通过刷新 `SkillDetail` 让 canvas 重绘；禁止渲染只存在于前端 state 的“假节点”。`GRAPH.md` 的 phase `src` 必须写 phase 目录（如 `phases/agent`），不要写具体文件路径（如 `phases/agent/SKILL.md`），否则 graph-agent loader 会把它当目录继续查找节点文件。`Properties` 只编辑当前 v2.1 AST 明确支持的字段：`LOGIC.md` 使用 `mode` + `<python_callable>`，`SKILL.md` 使用 `mode` + `tools` + `<system_prompt>` + `<exit_contract>`，`SUBGRAPH.md` 使用 `mode` + `target_skill`；不得写回旧版 `prompt`、`agent_tools`、`execute_steps`、`sub_skill_ref` 等会被后端 AST 拒绝的字段。保存时必须保留未知字段和正文。ReactFlow 连线必须持久化为 `GRAPH.md` 的 `depends_on`，不能只停留在本地 edge state。
- **节点主体 (`SkillNode`)**: 应用统一的背景令牌 (`bg-card`) (见 `GraphCanvas.tsx:143`)；处于执行态时，采用呼吸式的高亮效果，但仅应用在节点内部的 Status 徽章上 (通过 Tailwind `animate-pulse-primary` 实现，见 `GraphCanvas.tsx:186`)。
- **连接线 (Edges)**: `[TODO: 设计意图未实现]` 当前仅实现了基础连线和数据包中心点 (见 `ContextEdge.tsx:37`)，原设计的浅灰色常态及数据流动画渐变色均未实现。
- **连接点 (Handles)**: `[TODO: 设计意图未实现]` 目前已覆写基础样式 (如 `!size-2.5 !bg-primary`，见 `GraphCanvas.tsx:155`)，但未实现“仅 hover 时激活显示”的隐藏防噪逻辑。

## 4. 面板拖拽系统与自适应重绘
Studio 必须表现得像一个原生桌面应用，核心支撑是灵活的分屏拖拽框架。
- **基建组件**: 采用 `react-resizable-panels`。
- **区域分割**:
  - `Sidebar (AssetsPanel)` 宽 15%-25%。
  - `Main Workspace (SplitEditor)` 包含上下或左右分割的 Canvas 画布和 Monaco 代码编辑器。
  - `Right Drawer (Copilot / Golden)` 按需滑出。
- **重要 caveat**: 拖拽调节窗体大小时，必须确保 `ReactFlow` 和 `Monaco Editor` 及时监听 Resize Observer，触发自我边界更新 (`fit-to-screen` 和 `layout()`)，否则可能产生渲染撕裂。

## 5. Tauri Native API 桥接层最佳实践
将网页代码安全接入 Tauri 本地能力的护城河机制：
- 严禁业务组件中直接解构 `window.__TAURI__` 对象。
- 所有本地 I/O 和 Shell 调用，必须收敛并封装在统一的文件下：`apps/studio/frontend/src/lib/tauri.ts`。
- **兼容策略**: 为了便于直接使用 Vite `npm run dev` 在浏览器中纯粹调试 UI，桥接层必须提供运行时检测：如果不在 Tauri 沙盒中，所有针对本地文件读写的接口必须返回模拟成功数据（Mock fallback ），而不是直接引发白屏崩溃。

## 相关 Spec
- [studio-uikit-redesign](../../.kiro/specs/_archive/studio-uikit-redesign/design.md)
