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
- *(新)* 诸如 `RadioGroup` 等新增组件，必须优先从 `shadcn` 统一引入，并统一落户在 `src/components/ui/` 目录下；删除确认不再新增或使用 `AlertDialog`，统一走 Sonner。
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
- 需要遮蔽的密钥/密码输入（`.mask-input`）的遮蔽样式只能作用于真实输入值，不能波及 placeholder。当前实现叠加了 `-webkit-text-security: disc`（WebKit，只遮真实值）和 Firefox 回退字体 `font-family: 'text-security-disc'`（把每个字形都画成圆点，不区分 value 与 placeholder）；后者会把空状态提示文字也画成一排圆点，让空输入框看起来“已填入一串星号”而误导用户以为里面有内容。必须为 `.mask-input::placeholder` 显式恢复正常 UI 字体（`var(--font-sans)`）并 `-webkit-text-security: none`，保证空框显示可读提示文字、只有真实输入/已保存值才被遮蔽。
- Settings / 弹层内所有面向用户的文案（标题、描述、按钮、tooltip、空状态卡片）必须走 i18n（`t()` + `en` / `zh-CN` bundle 同步），不得写死中文或英文常量；否则切换语言时会漏翻，且英文模式下还会泄漏中文。新增带变量的文案用命名占位符（如 `{{n}}`）而非依赖 i18next 复数后缀，并在 `CopilotTab.test.tsx` 那种 bundle 契约测试里补一条“两个 bundle 都定义了该 key 且 zh 是真翻译”的断言。
- 页面内容区需要设置响应式最大宽度，避免表单、文本和卡片在超宽窗口里被横向拉得过长；数据密集型列表可按具体信息密度单独放宽。
- Settings 页面中用于归类列表的同级内容分区应统一使用本地 `CatalogAccordion`，例如 Endpoints 的 endpoint groups 和 LLM Roles 的 `Graph Agent Roles` / `Copilot Roles`；普通探测或表单内折叠继续使用基础 `Accordion`。空分区也要保留可见的 catalog header 和简短 empty state，避免用户误以为分类缺失。分区标题使用 Title Case，展开/收拢指示箭头放在标题前方，业务分类 icon 放在标题文本后方，并与首张内容卡保持清晰垂直间距。
- Copilot runtime 配置必须拥有独立 Settings 页，不要塞进 LLM Roles 页。Copilot 页整体布局对齐 API Keys / LLM Roles：外层使用同级 `CatalogAccordion` 分区和纵向 role card 列表，不再增加 Copilot 页内二级导航。Catalog 分区按 Copilot SDK 划分，例如 `Claude Agent SDK` / `Codex SDK`；分区内的 role 天然继承该 SDK，不再渲染 role 级 SDK selector。每个 role card 复用 LLM Roles 的 model group / provider route fallback 形态：内部 model group row、route grid、拖拽排序、删除和 Add route；不要另做解释型 dashboard。Copilot 可切换项等同于当前 Copilot roles；每个 Copilot role 只能包含一个 model group。按钮文案保留 `Add model`，但行为是先新增一张空 Copilot role card，用户在该 card 内用本地 `Select` 选择唯一 model group；候选 selector 只展示至少包含一条当前 SDK 兼容 route 的 group，并在进入 role card 前过滤掉不兼容 method 的 routes。Agent SDK readiness 只作为紧凑状态展示。
- 删除确认必须使用 shadcn Sonner action/cancel toast，并优先复用本地 `requestDeleteConfirmationToast` helper；不要使用 `window.confirm`、`AlertDialog`、`DeleteConfirmDialog` 或手写确认弹窗。确认 toast 必须包含明确的 destructive `Delete` action、`Cancel` action，并使用不可自动消失的确认时长。

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
- Provider、model、vendor 等实体标签使用本地 `Tag` wrapper；绿色可用态使用 `Tag variant="success"` 的圆角 outline 样式，不在业务组件里手写 `border-success` / `bg-success` 标签外观。`Tag` 的 `success` / `warning` / `destructive` / `multimodal` 只用边框表达语义差异，底色保持同一种轻量可用态底色；warning 使用 yellow 边框，destructive 使用专用 shadcn red tag token，multimodal 使用独立 blue 边框。`Badge` 继续用于状态徽章，例如 Connected、Test failed、Saving。
- 使用本地 Radix/shadcn `Tooltip` 的同一个 trigger 元素不得同时保留原生 `title` 属性，避免桌面 WebView 同时显示系统 tooltip 和 shadcn tooltip；需要可访问说明时用 `aria-label` / `aria-describedby`，视觉说明交给 `TooltipContent`。
- 卡片 `⋮` / 右键菜单里**移除/删除类**的菜单项必须用本地 `DropdownMenuItem` / `ContextMenuItem` 的 `variant="destructive"` 拿语义化销毁色（`data-[variant=destructive]:text-destructive`），**不要硬编码 red / 一次性 Tailwind 调色**；配一个 lucide 销毁图标（如 `Trash2`）。是否二次确认按**破坏性**分级：删除持久化配置/数据（如角色 DELETE，见 §2.9）必须走 Sonner action/cancel 二次确认 toast；只是清理一条列表项、底层数据/文件原样保留且可轻易恢复的低风险操作（如「从最近移除」——skill 文件不删、随时能再 Open folder 打开），用一个 `toast.success` 通知即可，不必拦一道确认弹窗。

### 2.8 输入框、搜索与行内动作
- 带图标、清空、复制、显示/隐藏等行内动作的输入框，优先使用本地 `InputGroup` / `InputGroupButton` / `InputGroupAddon`。不要用绝对定位按钮硬盖在 `Input` 上；这种做法容易被 input 拦截点击，也更难保证窄宽度布局。
- 搜索框应支持清空操作：有 query 时显示清空按钮，清空后恢复列表并把焦点放回搜索输入框。
- 搜索结果数量应在标题附近展示，让用户知道当前 filter 后剩余多少项。
- 搜索匹配在数据密集列表中应尽量宽容：支持名称、分组、provider/vendor 等关键字段，并避免 `-`、`.`、空格等符号成为强制精确匹配门槛。

### 2.9 数据密集列表与 Badge Overflow
- 数据密集列表中的标签必须尽量可读。不要把每个 Badge 单独截成 `Ope...` 这类不可识别文本。
- 多标签行的通用模式是：展示能稳定放下的完整标签，末尾用 `+N` overflow badge 表示剩余项；选中或展开后再展示完整标签集合。
- Badge 文本使用真实 label，不使用临时缩写。模型、provider、vendor 等实体名必须展示准确名称。
- Role / model / provider 这类层级编辑器不得把内部短码（如 `GM31P`、`CLO47T`）作为可见主标签或可访问标签；短码只用于持久化 key 或调试上下文。模型行展示模型真实名称，Provider 行只展示 provider 名称，不展示派生标题或 provider model id 副标题。
- Role fallback chain 只能保存后端返回的精确 `route_id`；UI 不得从 provider model id、display name 或 provider brand 推导执行目标。
- Role provider 的全局可用性和 API key 状态必须通过后端 DTO 暴露的 owning `endpoint_id`（或兼容旧数据时的 route id 前缀 fallback）映射到 credential endpoint；不得把 `route_id` 本身当作 API Keys credential id。Role card 顶部 `Test` 是 persisted Role Test：必须先 flush 当前 role autosave（包括 debounce timer 里尚未发出的 snapshot），再调用 `/api/llm/roles/{role_name}/test`。Role Test 的底层 route probe 必须复用 API Keys official Test 持久化的 verified profile / `method_id` / `request_mapper_id` 调用路径；前端不得为了进度并行调用 `/api/llm/endpoints/{endpoint_id}/models/test`，避免同一 route 出现两套 test 结果。Role Test 结果不要在 role card 内额外渲染报告面板；provider row 的边框/状态灯和整行 tooltip 承载 provider label、三态结果、role capability/降级/冷却等用户可行动诊断，不展示 raw route/endpoint/canonical id；后端需要实际 probe 多个 provider route 时应并发执行，而不是按 runtime fallback 串行短路。
- Role Test 的失败 toast 必须翻译请求层错误包装，并优先直接展示后端 `detail`；不要直接展示 `Request failed with status code ...`，也不要把 `Unknown LLM role` 等后端原因改写成前端推断。英文页面必须保持英文文案。
- Route-backed role provider（带 `endpoint_id` 或精确 `route_id`）的 ownership 已由后端 DTO 保证，前端不得再扫描 credential `available_models` 做旧版 provider ownership 推断；旧版推断只能用于非 route-backed provider code，避免长模型库首屏同步阻塞。
- 从 Available Routes 拖入 role 时，拖拽 payload 必须携带 exact `route_id`，并保持后端 DTO 中的 canonical/provider/status 字段只读展示；未知 route 由后端拒绝保存。拖入一个 Model Group 必须保留该组中所有后端返回的 provider routes，包括 `failed`、`cooling_down` 和 `off`，不要静默裁剪；用户可以在 role card 中显式删除不需要的 route。默认排序应 ready-first，然后再按 provider kind/name 稳定排序。
- 添加 role route 使用右侧 Available Routes 的拖拽源和本地 shadcn `Empty` drop target；不要提供与 route registry 割裂的 Add model select。
- 添加 Role 必须先通过本地 shadcn `Dialog` + `Field` 输入 role name，创建后的 role 是可保存的空草稿，不自动塞入默认 model/provider；保存前必须归一化掉空草稿或 orphan draft model 上的 stale `active_model`，并取消会读取 invalid ref 的既有 autosave；role name 必须可从 role 的三点 action menu 修改。
- Provider 添加入口使用与 provider row 等宽等高的 ghost `DropdownMenu` trigger；没有可添加 provider 时不显示占位按钮。
- Route fallback row 数量超过一个时使用响应式横向 grid，添加 route 的 ghost trigger 作为 grid 最后一项；route card 必须按最多 3 列排布，并随容器宽度自动降为 2 列、1 列。同一 role card 宽度下，不同 model group 的 provider row 必须使用一致列宽，少于当前列数时保留空轨道，不要用 `auto-fit`/内容宽度自适应把 2 个 route 拉成半宽；也不要保留文字状态 badge 时代的固定宽列或回退到纵向堆叠/单独 select。
- Role card 内的 Model Group row 只表达 fallback 顺序和 provider route 组成，不渲染 `Connected`/`Failed`/`Unavailable` 这类 aggregate 状态 badge，也不承载 settings gear；model fallback、thinking、output-token 等偏好设置必须放在 Role header 展开的内联配置 panel，Role header action 区只保留 Test 和 role action menu 等命令。
- Role 级配置不使用 modal；点击 role card header 的 role title 区域展开/收起内联配置 form。配置项应使用紧凑响应式 grid 编排，避免每个简单开关或选择器都独占整行。Model Fallback 和 Thinking 开关不使用额外边框容器，也不在开关旁重复解释文案。Provider order 不再作为配置项暴露，实际顺序由 provider row 拖拽决定并保存为 manual order。Model Fallback 用开关表达是否继续尝试下一个 model group。Thinking 用开关表达 Preferred/Off；Studio UI 开启时保存 `thinking: preferred`，不得保存 `required`。Output token 保留一个可空数字输入，输入右侧提供 `Use max` 开关；开启时输入框 disabled，并保存为 `maximum_available`，后端按每条 route 自身的 `max_output_tokens.max` 写入 runtime settings。输入附近必须展示当前 role 所有 provider routes 已知的 max output token 最小值和最大值；如果部分或全部 route 未暴露 cap，不要提示 Role Test 会补齐，只说明对应 route cap unavailable。Target 超过 route cap 时不再暴露 cap policy 选项，默认按 route max 降级执行。
- Role 删除必须使用 shadcn Sonner action/cancel toast 二次确认，并调用 persisted `DELETE /api/llm/roles/{role_name}`。不要只从本地 draft 删除后依赖 `PUT /api/llm/roles`，因为该 PUT 是合并语义，缺失 role 会被后端保留。
- Provider 名称在 row 内必须单行省略，避免窄卡片中把 provider label 拆成两行；不要给 provider 名称单独加 Tooltip。Provider row 的 Radix Tooltip 属于整条 row，第一行必须先显示真实 `provider_model_id`，后续展示模型能力、token limits 和 role 设置匹配/降级诊断；不要写 `This route can run in this role` 这类泛泛文案，也不要展示 raw route/endpoint/canonical id。
- Role card 内的 provider row 不渲染 `Connected`/`Failed` 等文字状态 badge；状态只用 row 边框/细 ring 和紧凑状态灯表达，不叠加状态背景色；testing 状态可用边框流动动画。Role Test 运行中不得把整个 role 的所有 provider row 预标成 testing；只能对当前进入测试 worker 或后端进度明确 active 的 route 设置 testing。文字型 aggregate 状态保留在 Model Group 层或 Role Test result surface。
- Role card 内的 provider row 不直接渲染后端内部 `Provider UI State` 或 `Role Fit` 文案；它必须把后端 provider projection、materialization Role Fit 和最新 provider-row test result 映射成用户可理解的三态：`Can Run`、`Limited`、`Blocked`。这三态只驱动 row 边框和紧凑状态灯，不渲染文字状态 badge；整条 row 的 tooltip/detail 必须包含具体受限 capability、fallback/test message、`Cooling Down` 等可行动诊断。全局 route 可用性仍由 API Keys 测试和右侧 Available Models provider tag 承载。
- Role list 和 Available Routes 这类可能很长的设置列表必须渐进渲染，保持搜索/计数完整，同时用 sentinel 自动加载后续批次。
- Role list 必须按用途分区展示，当前分为 `Graph Agent Roles` 与 `Copilot Roles`；每个分区底部都要提供对应的 `Add Graph Agent Role` / `Add Copilot Role` 入口，并与下一段分区保持明确垂直间距。Graph Agent 分类与 role icon 使用 engine/cog 语义图标，role 标题行需要使用默认字体，整行 controls 必须垂直居中对齐；窄宽度下 role header controls 应换到标题下一行，不能把 role name 挤压成逐字换行；编辑和删除等 role 级动作统一收进标题右侧的三点 `DropdownMenu`，删除必须使用统一 Sonner action/cancel toast 二次确认。
- Tauri/WebKit 下非编辑区双击可能触发原生文本选择命令，导致 macOS `Edit` 菜单闪烁或系统提示音；应用根部必须保留全局 double-click guard，在非输入、非 `contenteditable`、非 Monaco 区域阻止原生默认选择行为和 `selectstart`，并用 CSS 将普通 chrome 设为不可文本选择；但不能阻止事件冒泡，以免破坏业务组件自己的 `onDoubleClick`。确实需要保留原生双击选择的区域使用 `data-allow-native-double-click` 标记。Tauri macOS shell 使用自定义 app menu，`Edit` submenu 必须保留原生 `Undo`、`Redo`、`Cut`、`Copy`、`Paste`、`Select All`；不要为了规避非编辑区双击提示音而删除原生编辑命令，提示音问题应在前端双击 guard 或独立菜单实现里处理。非编辑区的原生 edit 快捷键和 `copy` / `cut` / `paste` 事件必须 `preventDefault()`，可编辑目标仍交给原生 WebKit；不要在前端用 `navigator.clipboard.readText()` 拦截 `Cmd+V` 做 paste fallback，否则 WebKit 会显示粘贴授权气泡而不是直接粘贴。
- Role 级三点菜单这类 hover-adjacent action 必须把鼠标双击视为 no-op，键盘打开菜单仍需保留。
- LLM Roles autosave 必须串行化并忽略被更新快照 supersede 的旧请求结果；当用户创建空 role 或拖入模型后，旧的 400 不应覆盖新的 pending/saved 状态或弹出陈旧 toast。任何依赖最新 role 草稿的动作（尤其 Role Test）必须 flush pending debounce timer 中的 snapshot 后再发起后续 API 请求。
- 层级编辑器必须用不同 shadcn surface/variant 区分层级，例如外层 role 用 `Card`，可排序 model/provider 行用 `Item` 的不同 variant，并且只使用语义化 token。
- 排序交互优先使用整行拖拽表面，不额外展示上下移动按钮或独立拖拽标签；设置、删除等行内动作必须阻止拖拽冒泡，保证点击目标可靠。
- 可拖拽的 route 和 route 库卡片必须使用 `select-none`，避免拖拽时选中文字；从 Available Routes 添加 route 时，drop handler 应覆盖整个 role card，Empty 只作为视觉 target，拖拽过程中 role header 的 Edit 等非 drop action 不应抢 hover/click。跨 role card 拖拽时必须用透明 drop shield 覆盖 header 操作，并在 pointerup 后吞掉该次合成 click，避免 Dialog trigger 在拖拽结束瞬间闪开。不要把跨区域添加依赖在 native HTML5 drag/drop 上；Tauri/WebKit 下 `dragstart`/`dataTransfer.types` 不稳定，应保留 pointer 坐标命中 drop zone 的 fallback，并同时渲染跟随指针的 drag preview，避免交互看起来像静态点击。长列表拖拽的 preview 坐标不得在父级 React state 中每帧更新，应使用 pointer-only source + ref/`requestAnimationFrame` 更新 transform，避免拖拽时重渲染整页和数百个模型卡。
- LLM Roles / Model Bundles 的跨区域拖拽失败不得 silent return；当找不到 drop target、源 model group 已失效、目标不允许嵌套或没有 provider routes 时，必须用 Sonner `toast.error` 显示具体失败原因。
- 长模型名、路径和 id 使用 `overflow-wrap:anywhere` / `break-words` 等方式在卡片内换行；不要让文本把卡片撑破。
- 如果列表来自外部探测或后端缓存，UI 不应写死样例数据。模型库类 UI 应展示已测试并持久化的数据源，按 vendor/provider 等真实字段归类。
- API Keys 的 third-party/custom 卡片的 `Available Models` 只能来自当前 draft 参数（API key、Base URL、Protocol）匹配的成功 test result；不得把 endpoint 下残留的 `provider_routes` 无条件投影到当前可见状态。参数变化后必须先清空可见测试状态，只有匹配历史 test result 或重新测试成功后才恢复模型列表。Official provider 的 `Available Routes` 例外：route tags 必须以后端 persisted registry / compact job response 为准，不能因为前端草稿 secret 与红acted/persisted secret 不一致而隐藏后端证据；草稿变更只能影响下一次 Test 写回，不能伪造或撤销 backend verified/failed/draft-inferred 状态。
- API Keys 的 official provider 卡片只暴露一个名为 `Test` 的动作，位置在 API key 行右侧；它调用后端 official endpoint test，由后端只验证 endpoint/base URL/API key 连通性并读取 provider model list，不得 generation-probe 全部模型。model-list/doc/draft inferred route 以未验证候选进入 `Available Routes` 和 registry；单模型 Test 或 Role Test 才执行 generation/profile probe 并把成功写成 verified。official provider 卡片不得再渲染手动 `Endpoint test` 输入行。
- API Keys 的 official provider 卡片标题必须使用规范品牌名（例如 `Anthropic Official`，不要直接显示 `anthropic-official` endpoint id），标题旁不渲染 `Connected` / `Not configured` 等连接状态 Badge；连接结果由 API key 行的可达性图标、route tags 和 toast 反馈承载，避免标题区重复信息。
- API Keys 的 official provider `Test` 必须走后端 job 化测试接口：启动请求只返回 job id/compact progress，前端轮询 compact job status，不得在每个轮询或最终测试响应中返回完整 registry。后端 compact `available_models` 必须包含本次 catalog/list 的全部候选及其后端状态（例如既有 `verified`、新观察到的 `unverified_manual`、历史 `failed`），前端每次 poll 都要合并到当前 provider test result；不得仅凭 provider 级 loading 把所有候选标成 testing。
- API Keys 不再渲染 `Available SDKs` chips；official method/profile 探测已经超出单一 SDK 概念，third-party/custom 的协议也由表单字段表达。保留模型/route 列表和空模型 warning 即可。
- API Keys 的 official provider 测试结果列表必须显示为 `Available Routes`，不是 `Available Models`。每个标签文本仍使用真实 `provider_model_id`，但标签状态来自后端 `ProviderRoute.ui_state` / verified profile / draft evidence：已验证并 active 的 route 使用 `Tag variant="success"` 绿色 outline；真正的 `probe-verified` 历史证据由后端投影为 `historical_ready` 后才使用蓝色 Previously Connected 标签；model-list/doc/draft inferred 且未 generation-probe verified 的候选保持 neutral/untested 标签；只有明确执行 probe 且失败的 route 使用 destructive/red 边框并展示 actionable reason。official route tags 排序必须 ready-first：绿色 verified routes 在最前，蓝色 historical-ready routes 其次，中性候选居中，failed/destructive routes 在最后。前端不得只凭 catalog list 或 model id 推断 route 已可用，也不得在最终结果里丢掉 catalog-only 候选；生成/embedding/audio/video/translation/3D/moderation/interactions-agent 必须按独立 typed group 展示，不能混成 text LLM fallback。
- Gemini catalog 中只支持 Interactions API 的 agent（如 `deep-research*`、`antigravity*`、`aqa`）不是普通 language/reasoning route；在 Studio 支持 Interactions route type 之前，应作为 catalog-only `interactions_agent` 展示，不得执行 `generateContent` probe 后标成 failed language route。
- API Keys 的 official provider `Available Routes` 标签必须表达 probe 进度和模型类型：测试过程中尚未拿到最终 probe message 的候选 route 使用与 LLM Roles provider row 一致的边框流动动画；后端标记为生成式多模态、audio/realtime、embedding、video、translation、3D 等 capability-library 类型的候选使用 `Tag variant="multimodal"` blue outline，并用本地 Radix `Tooltip` 展示模型类型。标签必须用 lucide 图标表达已知输入/输出能力，包括普通语言模型的 `text` 输入/输出：输入能力图标放在模型名前，输出能力图标放在模型名后；reasoning/thinking 通过模型名后的 brain 图标表达。输入/输出来源必须在 tooltip 中区分 provider model catalog、provider documentation、probe verified 或 stale inferred fallback；verified route 的 tooltip 必须展示已验证 profile capability 类型（例如 text chat、reasoning、image input）和 method，而不是 profile 数量；failed route 的 tooltip 必须优先展示后端持久化的具体 probe attempt / provider error，不得只展示 generic fallback。失败候选继续使用 destructive/red 边框。
- API Keys 的 official route tooltip 必须展示模型输入/输出 modality 和 `max_input_tokens` / `max_output_tokens`；provider 未在 catalog/probe 数据中列出 token limit 时显示 `not listed`，不要静默省略。
- API Keys 的 official provider verified route tooltip 不再追加泛泛的 model type label（如 `Language/reasoning model`），因为 verified profile capability 已经表达可用能力；failed / untested / capability-library 候选仍可展示 model type label 帮助解释状态。failed route tooltip 必须优先展示后端返回的 `last_probe_message`，不要只显示 generic `Route test failed`。
- API Keys 和 LLM Roles 的 route tooltip 中，任何 warning / failed 诊断行都必须带对应 lucide 警告或失败图标，并使用 `data-tooltip-diagnostic` / `data-tooltip-diagnostic-icon` 这类可测试标记；即使诊断句前面带 model id 前缀（例如 `gpt-x - Route test failed...`），也必须能识别为 failed/warning。
- API Keys official provider 的 route loading 动画必须来自后端 compact job 中每个 model 的显式 `testing` / active probe 状态；前端不得仅凭 provider 级 `isTesting` 把所有 `unverified_manual` route 推成 loading。生成式多模态等 capability-library 候选使用 `Tag variant="multimodal"` 的 blue outline；如果某候选明确 probe failed，失败状态优先，仍使用 destructive/red route tag。
- API Keys 的 official provider `Test` 进度和成功 toast 必须使用 catalog / route candidates 语义，不得显示 `Testing routes (x/y, n verified)` 这类全量 generation probe 文案；成功 toast 必须按已存在 live verified route 数量汇总，不得把返回的 route/model 总数写成 verified。如果返回列表中存在 failed、unverified 或未知状态，应明确显示 not generation-probe verified 数量。
- API Keys 的 third-party/custom provider 仍保持模型列表探测和端点连通探测拆开：`Get Models` 只调用 provider 的 models-list API，按钮不得使用 primary variant，成功后只刷新当前参数匹配的 `Available Models`，不得把状态 badge 置为绿色 `Connected`；`Endpoint test` 必须让用户输入一个来自 available models 的具体 model id，执行最小生成 probe，只有该 probe 成功才显示绿色 `Connected`。
- API Keys 的真实 API key secret hydration 只能在用户进入 API Keys 编辑上下文时触发；Settings 打开、General 页面、LLM Roles 页面只能读取 registry 摘要/红acted key 状态，不能批量请求 `/secret`，避免密钥请求阻塞其它设置页加载。
- third-party/custom provider 的 `Get Models` 只要 provider 返回 2xx，就只能证明 API Key / Base URL / Protocol 组合可访问模型列表接口，不等同于 endpoint generation 可用；这种情况应在对应字段右侧显示可达成功标记。若 2xx 响应没有返回模型（例如 `data: null` 或空数组），不得判定为失败或清空 API Key/Base URL 可达反馈，应在 `Available Models` 区域展示 warning empty state。
- API Keys 的 `Available Models` 标签必须展示真实 model id，并作为可点击复制目标；hover cursor 使用 pointer，点击后复制该 model id。third-party/custom provider 用户可将该 id 粘贴到 `Endpoint test`；official provider 则展示后端已 probe 并确认可作为语言/推理 route 的模型。
- API Keys 的同一卡片内表单控件必须按同一输入列左/右边界对齐，右侧 action 区域固定并右对齐；official `Test`、third-party/custom `Get Models` 和 `Endpoint test` 的 loading 状态必须按具体按钮区分，不得让同卡片其它测试按钮一起转圈。Endpoint test 失败不得清空当前参数匹配的 Available Models。
- LLM Provider Intelligence V2 之后，Available Routes 的 `canonical_id`、vendor/provider 分组、route availability 和 provider ownership 均来自后端 DTO；前端不再从 raw model string 做 canonicalization、provider ownership inference 或 stale provider pruning。
- LLM Roles 右侧 Available Models 仍以后端 Model Group 为可拖拽卡片，但列表 section 必须按模型族 / provider family 归类，不能退化成单一 `Model Groups` 大类；卡片标题使用普通 UI 字体，不使用 mono/code 风格；provider badge 直接用颜色表达 Ready / Historical Ready / Untested / Cooling Down / Failed / Off 等状态，不再额外渲染 `1 Untested` 这类第二层状态汇总标签。绿色只表示后端 ready/verified；蓝色只表示后端 `historical_ready`，也就是同一稳定 `route_id` 有真实 `probe-verified` 历史证据；untested/provider-list/doc/draft inferred language-capable route 必须保持中性候选态。后端 DTO 是唯一 eligibility 来源：只有 input 和 output modalities 都包含 `text` 的 route 才能进入 LLM Roles fallback chain；多模态、embedding、audio、video、translation、3D、moderation、interactions-agent 必须留在独立 capability group，不得混入 text LLM fallback。
- LLM Roles 右侧 Available Models 的模型 family / section 归属必须优先来自 route 自身的模型 ID / 后端投影结果，不能被代理 endpoint 名称或协议族带偏；例如 `Qiniu-Anthropic` 代理下的 `deepseek-*` 仍归入 `deepseek`。
- LLM Roles 右侧 Available Models 的 provider badges 必须按可用性排序，Ready / 已连通的 route 在前，其次 Untested、Cooling Down、Failed、Off；折叠态下也要优先露出可用 route，避免绿色可用项被 `+N` 隐藏。Ready provider badge 只用 `Tag variant="success"` 绿色 outline 表达可用状态，不额外渲染 `Ready` 文案；非 ready 状态仍可保留简短状态文本。
- LLM Roles 右侧 Available Models 的 Model Group 必须代表一个后端投影后的模型身份，而不是 raw `canonical_id`；不同 provider route 如果投影出相同 `display_name`，必须合并成一张模型卡，并在卡内以 provider badges 展示各 route。执行目标仍只保存精确 `route_id`，不得用展示名反推执行 ID。
- LLM Roles 的 Model Bundles 是与 Role 同构的编排对象：用户新建 bundle card，再把普通 Model Group 拖入 bundle，设置 model fallback / thinking / output token，并在 bundle 内排序 model group 和 provider route。后端保存时必须把 bundle 的 `model_groups` materialize 成 flat `fallback_chain`，右侧 Available Models 再把该 flat route list 作为 pinned Model Group 展示在普通模型之前。
- Model Bundle authoring surface 必须复用 Role 区域的 `Card` 层级、内联 settings grid、Model Group 行的 `Item` 层级和 provider row 交互；不得退化成“从某个 role 复制 fallback_chain”的快捷列表。普通 Model Group 仍可直接拖入 Role，不需要先创建 bundle；pinned bundle 可以作为普通 Model Group 拖入 Role，但不允许在 bundle 内递归嵌套另一个 bundle。
- Pinned bundle 被拖入 Role 后，API DTO 转换层必须把 `model_bundles` 同步投影为 `bundle:<id>` pseudo Model Group 并写入内存 `models/providers` map；否则 autosave 回填会把已保存的 bundle role entry 当作 orphan 删除，造成“拖进去后立刻消失”的无提示失败。
- LLM Roles 的模型显示名可以从后端 `display_name` / `canonical_id` / `provider_model_id` 派生 UI-only normalized label，但不得改写执行 ID。归一化顺序必须先识别日期和版本号，再做 title-case：`4-7`、`4.7`、`4 7`、`v3-1`、`V3 1` 分别显示为 `4.7`、`4.7`、`4.7`、`V3.1`、`V3.1`；`2025-4-28` 显示为 `2025-04-28`；`preview-05-2026` 和 `260425` 这类 snapshot/date-like token 不得误转成模型版本。

### 2.10 前端验证要求
- 纯前端 UI 调整不强制执行 TDD；可以直接实现，但完成前仍必须运行相关 typecheck/现有测试，并做实际界面检查。
- 修改 `apps/studio/frontend` 的用户可见 UI 后，完成前必须亲自启动或连接本地页面，实际打开、点击、输入相关流程，并检查桌面/窄面板等关键宽度下是否穿模、截断或布局错位。默认使用后台 Playwright 验证本地页面（包括 hover tooltip、点击、搜索、拖拽入口、窄宽度视口等），并用 locator / DOM 断言记录结果；不要用 macOS 桌面控制、系统截图或人工坐标点击替代普通网页 UI 验证。单测和 typecheck 不能替代这一步。
- 后台 Playwright smoke test 如果需要临时启动 Vite/backend，必须记录自己启动的 PID 并只清理这些 PID；不得用宽泛的 `pgrep`/`kill` 模式清理 `cargo tauri dev`、Studio Vite 或 Tauri dynamic sidecar，否则会把仍在使用的桌面窗口后端端口杀掉，造成 Settings 等页面持续请求 stale sidecar port。
- 必须覆盖被改动的主成功路径和明显的取消/清空/错误/空状态。对于搜索、选择、复制、显示/隐藏、展开/折叠等交互，要逐一点击验证。
- 手动验证应包含窄宽度视口。至少检查页面级、侧栏级、卡片级没有横向溢出；选中 ring、hover/active、badge overflow 和按钮点击目标不能被裁剪或被其它元素拦截。
- 全局 Sonner toast 不能占用固定底部主操作区；Studio 有底部居中的 action bar 时，通知默认放在顶部右侧，避免 success/error toast 拦截 Compile/Predict/Run 等连续点击路径。
- 如果变更涉及 Tauri 文件系统能力（目录选择、Reveal、终端、外部编辑器、原生菜单等），必须在 Tauri 环境或等价的 Tauri bridge 路径下验证，不能只用普通浏览器 fallback 得出结论；只有这类 Playwright 无法覆盖的原生 shell 行为才允许使用桌面控制工具，并且最终说明必须写清楚为什么不能用后台 Playwright 覆盖。

## 3. GraphCanvas 画布样式覆写
原生的 `@xyflow/react` 深色主题仍带有较重的网页感，在 `GraphCanvas` 组件和全局 `index.css` 中进行了覆写：
- **默认布局对齐**: 单链或可直线化的默认流程（例如 `Input -> init -> Output`）必须采用节点中心点坐标作为布局基准，并让左右 handle 在同一水平中心线上；同一水平线的连接边应渲染为直线路径，避免无意义的 Bezier 弯线或 IO 节点与 phase 节点上下错位。
- **节点选择反馈**: 单击 skill node 必须立即打开左侧 `Properties` panel 并同步选中态；双击继续用于打开对应 phase 文件。左侧工作区工具栏顺序固定为 `Assets`, `Properties`, `Input`, `Trace Timeline`, `Local History`，避免节点检查路径被埋在第三顺位之后。
- **节点双击语义统一走 ReactFlow `onNodeDoubleClick`，节点内部禁止 `stopPropagation` 截断双击**: 双击节点是「上层路由」——普通节点打开 phase 文件、子图（subgraph）节点下钻进子图，二者都由 `GraphCanvas` 的 `onNodeDoubleClick` 统一分发。因此 `SkillNode` 等节点组件**不得**在自己的 `onDoubleClick` 里 `event.stopPropagation()`：一旦截断，React Flow 收不到双击，子图下钻直接失效（双击只会打开 Properties，不下钻）。这是 2026-06-23 修过的真实回归（节点曾对有 `subgraphPath` 的双击 `stopPropagation`，导致下钻哑火，而手册一度仍标「符合」——状态滞后于代码）。节点内只有「需要保留原生双击选择」的局部区域才用 `data-allow-native-double-click` 放行（与 §2.9 全局 double-click guard 配套），其余一律让双击冒泡到画布。回归由 e2e `n2-canvas-shots.spec.ts #14` 守护（双击子图节点须出现面包屑 + 子图子节点）。
- **Canvas authoring 文件驱动**: 画布上的新建 phase、属性编辑、节点连线都必须先写入 phase 文件或 `GRAPH.md`，再通过刷新 `SkillDetail` 让 canvas 重绘；禁止渲染只存在于前端 state 的“假节点”。`GRAPH.md` 的 phase `src` 必须写 phase 目录（如 `phases/agent`），不要写具体文件路径（如 `phases/agent/SKILL.md`），否则 graph-agent loader 会把它当目录继续查找节点文件。`Properties` 只编辑当前 v3 AST 明确支持的字段：`LOGIC.md` 使用 `mode` + `<python_callable>`，`SKILL.md` 使用 `mode` + `tools` + `<system_prompt>` + `<exit_contract>`，`SUBGRAPH.md` 使用 `mode` + `target_skill`；不得写回旧版 `prompt`、`agent_tools`、`execute_steps`、`sub_skill_ref` 等会被后端 AST 拒绝的字段。保存时必须保留未知字段和正文。ReactFlow 连线必须持久化为 `GRAPH.md` 的 `depends_on`，不能只停留在本地 edge state。
- **节点主体 (`SkillNode`)**: 应用统一的背景令牌 (`bg-card`) (见 `GraphCanvas.tsx:143`)；处于执行态时，采用呼吸式的高亮效果，但仅应用在节点内部的 Status 徽章上 (通过 Tailwind `animate-pulse-primary` 实现，见 `GraphCanvas.tsx:186`)。
- **连接线 (Edges)**: `[TODO: 设计意图未实现]` 当前仅实现了基础连线和数据包中心点 (见 `ContextEdge.tsx:37`)，原设计的浅灰色常态及数据流动画渐变色均未实现。
- **连接点 (Handles)**: `[TODO: 设计意图未实现]` 目前已覆写基础样式 (如 `!size-2.5 !bg-primary`，见 `GraphCanvas.tsx:155`)，但未实现“仅 hover 时激活显示”的隐藏防噪逻辑。
- **叠加（overlay）节点必须自带显式 `width`/`height`**: 凡是不进 `useNodesState`、而是直接拼进 `displayNodes` 叠在受控节点之上的「临时/预览」节点（如子图 inline 展开的子节点 `subgraph-expansion.ts`），**必须在节点对象上写死 `width`/`height`**。原因：React Flow v12 对没量过尺寸的节点保持 `visibility: hidden`，要等它把测量结果通过 `onNodesChange` 回写进受控 state 才显形；但这些 overlay 节点根本不在 `useNodesState` 里，它们的测量 change 会被 `onNodesChange` 丢弃 → 永远量不到 → 永远 `visibility: hidden`（DOM 里在、但看不见）。带显式尺寸的容器节点（如 `SubgraphGroupNode` 自带 group bbox）能正常显示，正好掩盖这个坑，造成「虚线容器出来了、里面空的」。这是 2026-06-23 子图 inline 展开真机调出来的真实 bug，单测 `subgraph-expansion.test.ts` 用「每个子节点都带数值型 width/height」这条断言守护。
- **画布内"内联/预览"另一张图，必须复用主画布那套递归构建管线，不许临创局部 builder**: 子图 inline 展开这类"在画布里嵌一张真子图"的需求，子图节点/边一律走主画布同一条管线——`buildNodesFromTopology`（出子图自己的 `__global_input__`/`__global_output__` 全局节点 + 真 phase 节点）+ `buildEdges`（`contextEdge` 连接边，自带可点中点圆点）+ `getAutoLayoutedElements`（dagre TB），再整体偏移进容器、命名空间化 id、置只读。**不要**为了"省事"手搓一个只铺 phase、把父图直连子首/末、连接边用 `smoothstep`（没圆点）的局部版本——那样子图缺自己的 in/out、缺连线圆点，跟主画布与下钻（#14）长得不一样，是 2026-06-23 PM 打回的真实返工（"应该是一套递归算法，不是临创一套"）。桥接父子用单独的虚线 bridge 边接驳 `expand 节点 ↔ 子图自己的 INPUT/OUTPUT`，不接到具体 phase 上。
- **节点上的可视交互件（如子图展开 `+`）gate 在"回调是否接线"，不要 gate 在"某派生值解析成功"**: 展开 `+` 的出现条件是 `data.onToggleSubgraph` 这个回调存在（`build-nodes` 对每个 `mode==='subgraph'` 节点都接线、预览子节点剥离回调），**不是**"path 解析成绝对成功"。把可视件挂在派生值上，会让 path 没解析/未声明的节点直接不出 `+`——用户看到的就是"别的子图节点 + 号消失了"（2026-06-23 PM 第 3 问）。正确语义：能力恒在（所有子图节点都出 `+`），解析失败时点开走 recovery 提示态（F4「unresolved path shows recovery state」），而不是悄悄把入口藏掉。drill（双击下钻）这种"会真去读子图"的动作才另判 path 是否可解析。

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
