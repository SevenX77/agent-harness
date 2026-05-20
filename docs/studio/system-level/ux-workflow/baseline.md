# ux-workflow (studio system-level) — Baseline (当下代码实现逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-20
> **Scope**: 贯穿多个 feature (canvas → editor → trace) 的用户核心操作流蓝图
> **配套**: 见 [INDEX.md](../../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

这份 baseline 只描述当前代码里真实能走通的 Studio 用户旅程。

它不是旧 `UX_WORKFLOW_BLUEPRINT.md` 的复述。

旧文档把很多 MVP0/未来态交互写成了现状, 例如:

- 拖入文件夹即打开 skill。
- 点击连线数据包打开 Context Inspector。
- Predict / Run 完整执行后进入 trace 调试。
- Golden baseline 双屏打磨。

当前代码的主入口是 `App`。

`App` 只保存一个 `currentSkillId` 状态, 然后把它传给 `Workspace`:
`apps/studio/frontend/src/App.tsx:7`
`apps/studio/frontend/src/App.tsx:13`
`apps/studio/frontend/src/App.tsx:16`

用户打开 Studio 后, 如果没有选中 skill, `Workspace` 渲染 `WelcomePage`:
`apps/studio/frontend/src/components/studio/Workspace.tsx:397`
`apps/studio/frontend/src/components/studio/Workspace.tsx:398`

Welcome 页面当前提供三个主要视觉区:

- 顶部品牌与说明。
- New skill / Import skill 两个入口。
- Recent skills 卡片列表。

这些 UI 在代码中的位置是:
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:161`
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:174`
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:203`
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:220`

New skill 是一个弹窗流程。

弹窗文案明确说会在 `AgentStudio/Skills` 下创建文件夹和 starter `SKILL.md`:
`apps/studio/frontend/src/components/welcome/NewSkillDialog.tsx:28`
`apps/studio/frontend/src/components/welcome/NewSkillDialog.tsx:32`
`apps/studio/frontend/src/components/welcome/NewSkillDialog.tsx:34`

Import skill 不是拖拽。

当前 UI 按钮调用目录选择器, 让用户选择一个本地文件夹:
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:189`
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:193`
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:197`
`apps/studio/frontend/src/lib/tauri.ts:64`

Recent skills 不是后端唯一真相。

它的排序偏好保存在浏览器 `localStorage` 里:
`apps/studio/frontend/src/hooks/useRecentSkills.ts:9`
`apps/studio/frontend/src/hooks/useRecentSkills.ts:26`
`apps/studio/frontend/src/hooks/useRecentSkills.ts:29`

用户点开一个 skill 后, `Workspace` 会进入 loaded 状态。

当前 loaded 状态默认打开左侧 Assets panel, 并打开右侧 Copilot panel:
`apps/studio/frontend/src/components/studio/Workspace.tsx:47`
`apps/studio/frontend/src/components/studio/Workspace.tsx:48`
`apps/studio/frontend/src/components/studio/Workspace.tsx:49`

主工作区如果没有打开文件, 显示 `GraphCanvas`。

如果已经打开文件, 显示 `SplitEditor`。

这个互斥关系在 `Workspace` 中直接写死:
`apps/studio/frontend/src/components/studio/Workspace.tsx:385`
`apps/studio/frontend/src/components/studio/Workspace.tsx:387`
`apps/studio/frontend/src/components/studio/Workspace.tsx:400`

画布交互当前以节点为主。

单击或拖拽 skill 节点只选中节点, 并把选中节点状态送回 Workspace:
`apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:185`
`apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:188`
`apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:191`
`apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:194`

双击全局 input / output 节点会打开 `io/inputs.json` 或 `io/outputs.json`, 并切到 Input panel:
`apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:198`
`apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:200`
`apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:201`
`apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:202`
`apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:203`

双击普通 skill 节点会打开该 phase 的文件, 并切到 Properties panel:
`apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:206`
`apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:208`
`apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:209`

这和旧 UX 文档里的“画布和 Monaco 自动双向重绘”不完全相同。

当前代码可以从画布打开文件到编辑器。

但画布连线修改仅更新 React Flow 本地 `edges` 和目标节点 `dependsOn` 的前端内存, 没有在此处立即序列化写回磁盘:
`apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:135`
`apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:136`
`apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:146`

编辑器打开后, 顶部是 Monaco 编辑器, 底部是 compact 画布。

这个用户体验由 `SplitEditor` 的上下 `ResizablePanelGroup` 组成:
`apps/studio/frontend/src/components/studio/SplitEditor.tsx:68`
`apps/studio/frontend/src/components/studio/SplitEditor.tsx:73`
`apps/studio/frontend/src/components/studio/SplitEditor.tsx:89`
`apps/studio/frontend/src/components/studio/SplitEditor.tsx:92`

单文件编辑态可以点击 split 按钮进入左右双编辑器。

对应 UI 在 `LazyMonacoPanel`:
`apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:187`
`apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:190`
`apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:194`

保存体验是自动保存。

用户改 Monaco 内容后, 当前代码 1.5 秒后调用后端写文件。

没有一个显式 Save 按钮作为主旅程必经步骤:
`apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:163`
`apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:171`
`apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:172`
`apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:174`

Compile 是当前能从中心操作栏触发的主要执行前动作。

中心操作栏永远在 loaded 且非 settings 的工作区底部显示:
`apps/studio/frontend/src/components/studio/Workspace.tsx:410`
`apps/studio/frontend/src/components/studio/Workspace.tsx:415`
`apps/studio/frontend/src/components/studio/Workspace.tsx:417`

Compile 失败时, 中心下方会出现 `CompileErrorPanel`。

这个面板显示第一条错误摘要和错误列表:
`apps/studio/frontend/src/components/studio/Workspace.tsx:412`
`apps/studio/frontend/src/components/studio/Workspace.tsx:452`
`apps/studio/frontend/src/components/studio/Workspace.tsx:457`
`apps/studio/frontend/src/components/studio/Workspace.tsx:460`

Predict / Run 按钮现在只是 console 输出。

它们不是完整用户旅程的可运行终点:
`apps/studio/frontend/src/components/studio/Workspace.tsx:418`
`apps/studio/frontend/src/components/studio/Workspace.tsx:419`

Trace Timeline panel 现在是静态样例列表。

它没有接入真实 run stream:
`apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:5`
`apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:6`
`apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:17`

Audit High-003 的真实状态如下。

旧 UX 文档说点击连线数据包后左侧 Properties 会切换为 Context Inspector。

当前代码没有这个旅程。

`GraphCanvas` 没有 `onEdgeClick`。

`PropertiesPanel` 只显示选中节点的 Phase ID、Mode、Depends On、Role、Tools、Subagents、File:
`apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:83`
`apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:97`
`apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:103`
`apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:109`

所以 baseline 结论是:

当前 UX 主线是 Welcome 选择/创建/导入 skill → 画布查看拓扑 → 节点/文件打开编辑器 → 自动保存 → Compile → 静态 Timeline/未实现 Predict Run。

它还不是旧文档描述的 canvas → editor → trace 闭环。

单 feature 细节请分别看:

- Canvas 细节: [canvas-topology baseline](../../feature-folders/canvas-topology/baseline.md)
- 多文件编辑细节: [multi-file-editor baseline](../../feature-folders/multi-file-editor/baseline.md)
- Trace 细节: [trace-visualization baseline](../../feature-folders/trace-visualization/baseline.md)
- Copilot 细节: [copilot-assistance baseline](../../feature-folders/copilot-assistance/baseline.md)

## 前端逻辑

`Workspace` 是当前 UX workflow 的总状态机。

它管理:

- 导航栈 `navStack`。
- 左侧 active panel。
- Copilot 是否打开。
- 当前打开文件。
- split editor 是否打开。
- settings 是否打开。
- 选中节点。
- 保存冲突弹窗。
- compile 阶段和 compile 错误。

这些状态集中在:
`apps/studio/frontend/src/components/studio/Workspace.tsx:36`
`apps/studio/frontend/src/components/studio/Workspace.tsx:37`
`apps/studio/frontend/src/components/studio/Workspace.tsx:38`
`apps/studio/frontend/src/components/studio/Workspace.tsx:52`
`apps/studio/frontend/src/components/studio/Workspace.tsx:53`
`apps/studio/frontend/src/components/studio/Workspace.tsx:54`
`apps/studio/frontend/src/components/studio/Workspace.tsx:55`
`apps/studio/frontend/src/components/studio/Workspace.tsx:59`
`apps/studio/frontend/src/components/studio/Workspace.tsx:62`
`apps/studio/frontend/src/components/studio/Workspace.tsx:63`

skill 详情数据通过 `useSkills(currentSkillId)` 拉取。

`useSkills` 用 SWR 访问 `/skills` 和 `/skills/{id}`:
`apps/studio/frontend/src/hooks/useSkills.ts:6`
`apps/studio/frontend/src/hooks/useSkills.ts:7`
`apps/studio/frontend/src/hooks/useSkills.ts:15`

文件打开不是直接读 Tauri 文件系统。

`Workspace.toOpenFile` 从 `skillDetail.files` 里取内容, 计算 hash, 再构造 `OpenFile`:
`apps/studio/frontend/src/components/studio/Workspace.tsx:91`
`apps/studio/frontend/src/components/studio/Workspace.tsx:97`
`apps/studio/frontend/src/components/studio/Workspace.tsx:103`
`apps/studio/frontend/src/components/studio/Workspace.tsx:104`

`WorkspaceContext` 把文件打开、关闭、更新、保存回调发给子组件。

这是 editor、panel、canvas 之间的主要派发通道:
`apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:22`
`apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:28`
`apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:31`
`apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:32`
`apps/studio/frontend/src/components/studio/Workspace.tsx:258`
`apps/studio/frontend/src/components/studio/Workspace.tsx:267`

Compile 的前端状态流如下:

1. 点击中心操作栏。
2. `handleCompile` 把 stage 改成 `compiling`。
3. 调 `compileSkill(currentSkillId)`。
4. 后端返回 failure 时记录 errors 并 toast。
5. 后端返回 ok 时 stage 改成 `compile-pass` 并刷新 skill detail。

代码位置:
`apps/studio/frontend/src/components/studio/Workspace.tsx:292`
`apps/studio/frontend/src/components/studio/Workspace.tsx:295`
`apps/studio/frontend/src/components/studio/Workspace.tsx:297`
`apps/studio/frontend/src/components/studio/Workspace.tsx:300`
`apps/studio/frontend/src/components/studio/Workspace.tsx:301`
`apps/studio/frontend/src/components/studio/Workspace.tsx:306`
`apps/studio/frontend/src/components/studio/Workspace.tsx:310`

后台 lint 状态也会影响中心操作栏 stage。

`readLintStatus` 从 `sessionStorage` 读取状态。

`deriveBuildStage` 用 lint 状态补足 compile stage:
`apps/studio/frontend/src/hooks/useDebouncedLint.ts:21`
`apps/studio/frontend/src/hooks/useDebouncedLint.ts:26`
`apps/studio/frontend/src/components/studio/Workspace.tsx:324`
`apps/studio/frontend/src/components/studio/Workspace.tsx:327`
`apps/studio/frontend/src/components/studio/Workspace.tsx:330`

但是 `useDebouncedLint` 的触发点不在 `Workspace` 主链路里。

它是一个可用 hook, 会在 markdown 变化 800ms 后 POST lint:
`apps/studio/frontend/src/hooks/useDebouncedLint.ts:30`
`apps/studio/frontend/src/hooks/useDebouncedLint.ts:48`
`apps/studio/frontend/src/hooks/useDebouncedLint.ts:49`

文件外部变化通过 WebSocket 接入。

`Workspace` 连接 `/ws/events`, 只处理当前 skill 的 `skill_changed`:
`apps/studio/frontend/src/components/studio/Workspace.tsx:218`
`apps/studio/frontend/src/components/studio/Workspace.tsx:220`
`apps/studio/frontend/src/components/studio/Workspace.tsx:223`
`apps/studio/frontend/src/components/studio/Workspace.tsx:224`

如果变化命中当前打开文件且没有 in-flight 保存, 前端热更新编辑器内容。

如果有 in-flight 保存, 前端弹 `ConflictDialog`:
`apps/studio/frontend/src/components/studio/Workspace.tsx:225`
`apps/studio/frontend/src/components/studio/Workspace.tsx:233`
`apps/studio/frontend/src/components/studio/Workspace.tsx:234`
`apps/studio/frontend/src/components/studio/Workspace.tsx:243`

这也是旧 Layout 文档中提到的产品反模式:

当前代码确实存在 conflict 机制, baseline 只记录现状, 不在这里做产品判断。

Copilot context 当前随 selected node 和 lint status 更新。

`Workspace` 通过 `useCopilotContext` 把选中节点摘要放入上下文:
`apps/studio/frontend/src/components/studio/Workspace.tsx:65`
`apps/studio/frontend/src/components/studio/Workspace.tsx:69`
`apps/studio/frontend/src/components/studio/Workspace.tsx:72`
`apps/studio/frontend/src/components/studio/Workspace.tsx:78`

## 后端功能

当前后端是 Studio workflow 的真实 skill 文件与编译入口。

FastAPI app 启动时会:

- 清理 backend cache。
- 确保 workspace layout 根目录存在。
- 启动 terminal reaper。
- 启动 file watcher。

代码位置:
`apps/studio/backend/app/main.py:49`
`apps/studio/backend/app/main.py:53`
`apps/studio/backend/app/main.py:54`
`apps/studio/backend/app/main.py:56`

后端注册了 skills、lint、runs、golden、copilot、websockets 等 router。

这说明 UX workflow 的“编辑 / compile / run / trace”不是一个单一 endpoint, 而是多个 router 组合:
`apps/studio/backend/app/main.py:124`
`apps/studio/backend/app/main.py:126`
`apps/studio/backend/app/main.py:127`
`apps/studio/backend/app/main.py:132`
`apps/studio/backend/app/main.py:134`
`apps/studio/backend/app/main.py:138`

创建 skill 走 `POST /api/skills`。

router 调用 `create_new_skill`:
`apps/studio/backend/app/routers/skills.py:81`
`apps/studio/backend/app/routers/skills.py:88`
`apps/studio/backend/app/routers/skills.py:94`

当传入 `directory_path` 且目录非空时, 后端会把它作为已有 skill 导入。

它会保存 index entry 和 summary, 不会强制重写目录:
`apps/studio/backend/app/services/skills.py:443`
`apps/studio/backend/app/services/skills.py:448`
`apps/studio/backend/app/services/skills.py:460`
`apps/studio/backend/app/services/skills.py:464`

当目录为空或没有传入目录时, 后端写 scaffold 文件, 创建 `.workspace`, 初始化本地 git repo:
`apps/studio/backend/app/services/skills.py:467`
`apps/studio/backend/app/services/skills.py:476`
`apps/studio/backend/app/services/skills.py:477`
`apps/studio/backend/app/services/skills.py:478`

Compile 走 `POST /api/skills/{skill_id}/compile`。

router 调用 `compile_skill_for_studio`。

失败时返回 422 JSON, 成功时返回 `CompileSuccess`:
`apps/studio/backend/app/routers/skills.py:108`
`apps/studio/backend/app/routers/skills.py:116`
`apps/studio/backend/app/routers/skills.py:118`
`apps/studio/backend/app/services/skills.py:294`
`apps/studio/backend/app/services/skills.py:303`
`apps/studio/backend/app/services/skills.py:309`

真实 run/predict 的后端 endpoint 已存在, 但当前 `Workspace` 的 Predict/Run 按钮没有调用它们。

前端 API client 定义了 `postPredictRun` 和 `startRun`:
`apps/studio/frontend/src/api/client.ts:120`
`apps/studio/frontend/src/api/client.ts:140`

后端 runs router 也定义了 predict 和 runs:
`apps/studio/backend/app/routers/runs.py:27`
`apps/studio/backend/app/routers/runs.py:32`

所以系统能力有后端底座, 但主 UX workflow 还没有接起来。

## API

当前用户旅程涉及这些 API 边界:

`GET /api/skills`

用于 Welcome 页面列出 Recent skills 的候选 skill。

前端 SWR 调用:
`apps/studio/frontend/src/hooks/useSkills.ts:7`

后端 router:
`apps/studio/backend/app/routers/skills.py:72`

`POST /api/skills`

用于 New skill 和 Import skill。

New skill 传 `skill_id` 和 generated content:
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:101`
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:103`

Import skill 额外传 `directory_path`:
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:135`
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:137`

后端请求模型允许 `skill_id`、`files`、`directory_path`:
`apps/studio/backend/app/models/skills.py:118`
`apps/studio/backend/app/models/skills.py:121`
`apps/studio/backend/app/models/skills.py:123`

`GET /api/skills/{skill_id}`

用于加载画布、文件树、编辑器内容。

前端:
`apps/studio/frontend/src/api/client.ts:157`
`apps/studio/frontend/src/api/client.ts:158`

后端:
`apps/studio/backend/app/routers/skills.py:98`
`apps/studio/backend/app/routers/skills.py:105`

`POST /api/skills/{skill_id}/files/{file_path}`

用于 Monaco 自动保存单个文件。

前端 API:
`apps/studio/frontend/src/api/client.ts:162`
`apps/studio/frontend/src/api/client.ts:169`

后端 API:
`apps/studio/backend/app/routers/skills.py:365`
`apps/studio/backend/app/routers/skills.py:375`
`apps/studio/backend/app/routers/skills.py:393`

`POST /api/skills/{skill_id}/compile`

用于中心操作栏 Compile。

前端 API:
`apps/studio/frontend/src/api/client.ts:81`
`apps/studio/frontend/src/api/client.ts:83`

后端 API:
`apps/studio/backend/app/routers/skills.py:108`

`POST /api/skills/{skill_id}/lint`

用于 debounce lint hook。

前端:
`apps/studio/frontend/src/hooks/useDebouncedLint.ts:49`

后端:
`apps/studio/backend/app/routers/lint.py:13`

`/ws/events`

用于文件变化热更新和 conflict 判断。

前端连接:
`apps/studio/frontend/src/components/studio/Workspace.tsx:220`

后端连接:
`apps/studio/backend/app/routers/websockets.py:50`
`apps/studio/backend/app/routers/websockets.py:60`

Tauri IPC 当前只用于桌面能力:

- `selectSkillDirectory` 使用 `@tauri-apps/plugin-dialog`。
- `revealInFileManager` 调 `reveal_in_file_manager`。

代码位置:
`apps/studio/frontend/src/lib/tauri.ts:47`
`apps/studio/frontend/src/lib/tauri.ts:48`
`apps/studio/frontend/src/lib/tauri.ts:71`
`apps/studio/frontend/src/lib/tauri.ts:73`

没有 `read_skill_dir` / `write_skill_dir` 这样的 Tauri IPC 在当前 workflow 中读写 skill 内容。

## Data Model / State

前端的核心状态是 `currentSkillId`。

它决定 Welcome 还是 Workspace:
`apps/studio/frontend/src/App.tsx:8`
`apps/studio/frontend/src/components/studio/Workspace.tsx:39`

`SkillDetail` 是画布、文件树、编辑器、compile 反馈的共同数据源。

模型包含 manifest、graph_topology、io_schema、file_paths、files、has_golden、latest_run_metadata、lint_result:
`apps/studio/backend/app/models/skills.py:39`
`apps/studio/backend/app/models/skills.py:42`
`apps/studio/backend/app/models/skills.py:43`
`apps/studio/backend/app/models/skills.py:45`
`apps/studio/backend/app/models/skills.py:46`
`apps/studio/backend/app/models/skills.py:47`
`apps/studio/backend/app/models/skills.py:48`
`apps/studio/backend/app/models/skills.py:49`
`apps/studio/backend/app/models/skills.py:50`

`OpenFile` 是编辑器当前内存态。

它在前端包含 path、content、language、skillId、hash、title、saveEnabled:
`apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:6`
`apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:7`
`apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:8`
`apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:9`
`apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:10`

`SaveConflict` 是当前外部变化/并发保存的 UI 状态。

它包含 skillId、path、side、localContent、remoteContent、remoteHash:
`apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:13`
`apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:17`
`apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:19`

Compile 前端状态不是后端持久对象。

它是 `Workspace` 内部的 `compileStages` 和 `compileErrors`:
`apps/studio/frontend/src/components/studio/Workspace.tsx:62`
`apps/studio/frontend/src/components/studio/Workspace.tsx:63`

Compile 后端成功模型是 `CompileSuccess`。

失败模型是 `CompileFailure`。

它们定义了 status、phase_count、manifest_name、errors:
`apps/studio/backend/app/models/skills.py:101`
`apps/studio/backend/app/models/skills.py:105`
`apps/studio/backend/app/models/skills.py:106`
`apps/studio/backend/app/models/skills.py:107`
`apps/studio/backend/app/models/skills.py:110`
`apps/studio/backend/app/models/skills.py:115`

Recent skills 存在 `localStorage`。

Lint 状态存在 `sessionStorage`。

这两个状态都不是后端数据库:
`apps/studio/frontend/src/hooks/useRecentSkills.ts:9`
`apps/studio/frontend/src/hooks/useRecentSkills.ts:29`
`apps/studio/frontend/src/hooks/useDebouncedLint.ts:17`
`apps/studio/frontend/src/hooks/useDebouncedLint.ts:26`

文件真实内容最终落在后端解析出来的 skill 目录。

`.workspace` 是后端目录约定。

运行、golden、predict、test inputs 都以 `.workspace` 子目录为位置函数:
`apps/studio/backend/app/services/skills.py:672`
`apps/studio/backend/app/services/skills.py:676`
`apps/studio/backend/app/services/skills.py:680`
`apps/studio/backend/app/services/skills.py:684`
`apps/studio/backend/app/services/skills.py:692`

## Cross-feature interaction

本系统级 workflow 不复述各 feature 内部实现。

当前跨 feature 链路按 owner 分流:

- Welcome / lifecycle owner: [skill-lifecycle baseline](../../feature-folders/skill-lifecycle/baseline.md)
- Canvas owner: [canvas-topology baseline](../../feature-folders/canvas-topology/baseline.md)
- Editor owner: [multi-file-editor baseline](../../feature-folders/multi-file-editor/baseline.md)
- Trace owner: [trace-visualization baseline](../../feature-folders/trace-visualization/baseline.md)
- Copilot owner: [copilot-assistance baseline](../../feature-folders/copilot-assistance/baseline.md)

Audit High-003 在本文件的结论是:

当前没有 Edge Inspection → Context Inspector 的真实 UI workflow。

如果未来补齐, owner 更适合落在 trace/canvas feature, 本文件只描述它如何接入端到端旅程。
