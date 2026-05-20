# workspace-file-system (studio system-level) — Baseline (当下代码实现逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-20
> **Scope**: Tauri/Rust IPC 桥接真实文件系统 (Watcher + Dir R/W) + 前端内存 Draft Persist
> **配套**: 见 [INDEX.md](../../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

当前 workspace file system 的用户体验和旧 `WORKSPACE_FILE_MANAGEMENT.md` 不一致。

旧文档说前端通过 Tauri `fs` 直接拉目录快照、渲染 OS 文件树、提供右键新建/重命名。

当前代码不是这样。

用户在 Welcome 页面有两个文件系统相关入口:

- New skill。
- Import skill。

入口位置:
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:174`
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:176`
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:189`
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:193`

New skill 打开 `NewSkillDialog`。

对用户可见的承诺是: 在默认目录下创建一个 starter skill:
`apps/studio/frontend/src/components/welcome/NewSkillDialog.tsx:28`
`apps/studio/frontend/src/components/welcome/NewSkillDialog.tsx:32`
`apps/studio/frontend/src/components/welcome/NewSkillDialog.tsx:34`

Import skill 调用系统目录选择器。

它不读取目录内容。

它只拿到目录路径, 然后把路径交给后端:
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:127`
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:130`
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:135`
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:137`

Recent skills 卡片可以 Reveal in file manager。

这个动作是桌面 shell 能力, 不是 Studio 自己的文件树:
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:73`
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:286`
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:320`

打开 skill 后, 左侧 Assets panel 展示文件树。

但这个树来自后端 `SkillDetail.files`, 不是 Tauri 前端直接扫描 OS 目录:
`apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:33`
`apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:35`
`apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:48`
`apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:82`

文件树只支持点击打开。

当前没有看到 Assets panel 内的新建、重命名、删除、右键文件操作实现。

它只构建树并渲染 `FileRow` / `FolderRow`:
`apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:65`
`apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:71`
`apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:76`
`apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:94`

编辑器保存体验是自动保存。

用户改 Monaco 内容后 1500ms 自动 POST 到后端:
`apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:163`
`apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:172`
`apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:174`

如果保存遇到 409, UI 会打开 conflict 弹窗。

这说明当前代码不是“本地文件唯一真相、永不弹冲突”的产品形态。

现状是存在 optimistic hash 和 conflict UI:
`apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:117`
`apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:122`
`apps/studio/frontend/src/components/studio/ConflictDialog.tsx:21`
`apps/studio/frontend/src/components/studio/ConflictDialog.tsx:24`

Audit High-004 的真实状态:

当前 `.workspace` 初始化职责在后端 `create_new_skill`。

Tauri/Rust 没有创建 `.workspace`、`script/`、`golden/` 的 command。

后端只在创建新 skill 时确保 `.workspace` 本身存在:
`apps/studio/backend/app/services/skills.py:476`
`apps/studio/backend/app/services/skills.py:477`

后端有 `golden_dir_for` 等路径函数, 但创建新 skill 的那段代码没有同时创建 `script/` / `golden/` 空目录。

代码位置:
`apps/studio/backend/app/services/skills.py:680`
`apps/studio/backend/app/services/skills.py:684`
`apps/studio/backend/app/services/skills.py:692`

所以旧文档里“空文件夹隐式创建完整骨架并由 FileWatcher 平滑重绘”的描述过宽。

当前更准确的用户体验是:

1. Welcome 选择创建或导入。
2. Tauri 只提供目录选择或 Reveal。
3. 后端 API 注册/创建 skill。
4. 前端从后端 SkillDetail 渲染文件树。
5. 编辑器自动保存到后端。
6. 后端 watcher 广播外部变化。

## 前端逻辑

`lib/tauri.ts` 是前端桌面桥接层。

当前声明的 shell command 只有:

- `open_in_cursor`
- `open_in_terminal`
- `open_in_codex`
- `reveal_in_file_manager`

代码位置:
`apps/studio/frontend/src/lib/tauri.ts:4`
`apps/studio/frontend/src/lib/tauri.ts:26`
`apps/studio/frontend/src/lib/tauri.ts:30`
`apps/studio/frontend/src/lib/tauri.ts:34`
`apps/studio/frontend/src/lib/tauri.ts:38`

`revealInFileManager` 在 Tauri runtime 下调用 Rust command。

非 Tauri runtime 下, 它尝试复制 path 到剪贴板:
`apps/studio/frontend/src/lib/tauri.ts:45`
`apps/studio/frontend/src/lib/tauri.ts:47`
`apps/studio/frontend/src/lib/tauri.ts:48`
`apps/studio/frontend/src/lib/tauri.ts:56`
`apps/studio/frontend/src/lib/tauri.ts:57`

`selectSkillDirectory` 使用 `@tauri-apps/plugin-dialog`。

它不是自定义 Rust command。

返回值只是一个目录字符串:
`apps/studio/frontend/src/lib/tauri.ts:64`
`apps/studio/frontend/src/lib/tauri.ts:71`
`apps/studio/frontend/src/lib/tauri.ts:72`
`apps/studio/frontend/src/lib/tauri.ts:73`
`apps/studio/frontend/src/lib/tauri.ts:74`

New skill 的前端创建逻辑:

1. normalize skill id。
2. 调 `POST /skills`。
3. body 里带 generated starter content。
4. 成功后刷新 skill list。
5. 打开新 skill。

代码位置:
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:90`
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:97`
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:101`
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:103`
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:117`
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:119`

Import skill 的前端创建逻辑:

1. 调目录选择器。
2. 从路径推导 skill id。
3. 调 `POST /skills`。
4. body 里带 `directory_path` 和 fallback generated content。
5. 成功后刷新并打开。

代码位置:
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:127`
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:130`
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:134`
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:135`
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:137`
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:152`
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:153`

文件打开逻辑:

`Workspace.toOpenFile` 从 `skillDetail.files` 找文件内容。

它会去掉 `${skillId}/` 前缀, 计算 hash, 记录 language:
`apps/studio/frontend/src/components/studio/Workspace.tsx:91`
`apps/studio/frontend/src/components/studio/Workspace.tsx:95`
`apps/studio/frontend/src/components/studio/Workspace.tsx:97`
`apps/studio/frontend/src/components/studio/Workspace.tsx:98`
`apps/studio/frontend/src/components/studio/Workspace.tsx:103`

文件保存逻辑:

`LazyMonacoPanel.saveNow` 调 `writeSkillFile(skillId, filePath, content, hashRef.current)`。

成功后更新 hash 和 saved content。

409 时触发 conflict:
`apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:97`
`apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:106`
`apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:107`
`apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:108`
`apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:117`
`apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:122`

`writeSkillFile` 的 HTTP body 包含 content 和 expected_hash:
`apps/studio/frontend/src/api/client.ts:162`
`apps/studio/frontend/src/api/client.ts:169`
`apps/studio/frontend/src/api/client.ts:170`
`apps/studio/frontend/src/api/client.ts:171`

外部文件变化逻辑:

`Workspace` 连接 `/ws/events`。

收到当前 skill 的 `skill_changed` 后, 如果变化命中打开文件, 拉最新 detail。

没有 in-flight 时直接替换编辑器内容。

有 in-flight 时打开 conflict:
`apps/studio/frontend/src/components/studio/Workspace.tsx:220`
`apps/studio/frontend/src/components/studio/Workspace.tsx:224`
`apps/studio/frontend/src/components/studio/Workspace.tsx:225`
`apps/studio/frontend/src/components/studio/Workspace.tsx:229`
`apps/studio/frontend/src/components/studio/Workspace.tsx:233`
`apps/studio/frontend/src/components/studio/Workspace.tsx:243`

前端 draft persistence 现状要分两类:

第一类是 `LazyMonacoPanel` 的内存 draft。

它只存在于 React state/ref, 用于 debounce 保存:
`apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:65`
`apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:66`
`apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:163`
`apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:165`

第二类是 `useDraftPersist` hook。

它使用 `localStorage`, 有 7 天 TTL, 支持 skill draft 和 edge draft。

但当前代码搜索结果显示它没有被 Studio 主编辑链路引用。

定义位置:
`apps/studio/frontend/src/hooks/useDraftPersist.ts:3`
`apps/studio/frontend/src/hooks/useDraftPersist.ts:5`
`apps/studio/frontend/src/hooks/useDraftPersist.ts:21`
`apps/studio/frontend/src/hooks/useDraftPersist.ts:29`
`apps/studio/frontend/src/hooks/useDraftPersist.ts:37`
`apps/studio/frontend/src/hooks/useDraftPersist.ts:61`
`apps/studio/frontend/src/hooks/useDraftPersist.ts:89`
`apps/studio/frontend/src/hooks/useDraftPersist.ts:107`

`DraftRestoreModal` 和 `DirtyIndicator` 也存在, 但没有被当前主 workflow 引用。

代码位置:
`apps/studio/frontend/src/components/draft/DraftRestoreModal.tsx:25`
`apps/studio/frontend/src/components/draft/DirtyIndicator.tsx:5`

所以 baseline 结论是:

当前主编辑器没有 IndexedDB draft persistence。

主链路是 React 内存 draft + debounce 后端保存。

localStorage draft hook 存在, 但不是主编辑器正在使用的机制。

## 后端功能

后端负责真实 skill 目录的读写、索引、创建、编译、watch。

app 启动时先确保 workspace skill 根目录存在:
`apps/studio/backend/app/main.py:54`
`apps/studio/backend/app/services/skills.py:161`
`apps/studio/backend/app/services/skills.py:163`

app 启动时还启动 `file_watcher`:
`apps/studio/backend/app/main.py:56`

file watcher 的 watch roots 是:

- bundled/public skills dir。
- default workspace skills dir。
- default skills root。

代码位置:
`apps/studio/backend/app/services/file_watcher.py:148`
`apps/studio/backend/app/services/file_watcher.py:149`

watcher 启动时会确保这些 root 存在。

它不会在这里创建每个 skill 的 `.workspace`、`script`、`golden`:
`apps/studio/backend/app/services/file_watcher.py:38`
`apps/studio/backend/app/services/file_watcher.py:40`

watcher 监听递归文件变化。

它跳过 dotfile 和目录。

然后把路径映射成 skill_id 和 relative path:
`apps/studio/backend/app/services/file_watcher.py:66`
`apps/studio/backend/app/services/file_watcher.py:69`
`apps/studio/backend/app/services/file_watcher.py:76`
`apps/studio/backend/app/services/file_watcher.py:77`
`apps/studio/backend/app/services/file_watcher.py:82`
`apps/studio/backend/app/services/file_watcher.py:120`
`apps/studio/backend/app/services/file_watcher.py:124`

watcher 生成的事件结构是:

- type = `skill_changed`
- skill_id
- path
- change
- hash
- mtime

代码位置:
`apps/studio/backend/app/services/file_watcher.py:125`
`apps/studio/backend/app/services/file_watcher.py:126`
`apps/studio/backend/app/services/file_watcher.py:127`
`apps/studio/backend/app/services/file_watcher.py:128`
`apps/studio/backend/app/services/file_watcher.py:129`
`apps/studio/backend/app/services/file_watcher.py:130`
`apps/studio/backend/app/services/file_watcher.py:131`

后端 API 写入会调用 `record_api_write`。

这用于 watcher echo filtering, 避免自己刚写的文件又触发一次外部变化提示:
`apps/studio/backend/app/services/skills.py:394`
`apps/studio/backend/app/services/skills.py:395`
`apps/studio/backend/app/services/skills.py:396`
`apps/studio/backend/app/services/file_watcher.py:56`
`apps/studio/backend/app/services/file_watcher.py:80`

创建 skill 的后端逻辑分两种:

如果 `directory_path` 指向非空目录, 它当作已有 skill 导入并保存 index/summary:
`apps/studio/backend/app/services/skills.py:443`
`apps/studio/backend/app/services/skills.py:448`
`apps/studio/backend/app/services/skills.py:460`
`apps/studio/backend/app/services/skills.py:464`

如果不是非空导入, 它写 scaffold, 创建 `.workspace`, 初始化 repo:
`apps/studio/backend/app/services/skills.py:467`
`apps/studio/backend/app/services/skills.py:476`
`apps/studio/backend/app/services/skills.py:477`
`apps/studio/backend/app/services/skills.py:478`

`ensure_workspace_skill_dir_async` 解析可写 skill dir。

它优先使用 global index, 再看 saved summary directory_path, 再看默认 workspace, 最后拒绝只读 public skill:
`apps/studio/backend/app/services/skills.py:533`
`apps/studio/backend/app/services/skills.py:540`
`apps/studio/backend/app/services/skills.py:546`
`apps/studio/backend/app/services/skills.py:552`
`apps/studio/backend/app/services/skills.py:556`

后端对 `.workspace` 的路径约定:

- `.workspace`
- `.workspace/runs`
- `.workspace/golden`
- `.workspace/predict`
- `.workspace/test_inputs`

代码位置:
`apps/studio/backend/app/services/skills.py:672`
`apps/studio/backend/app/services/skills.py:676`
`apps/studio/backend/app/services/skills.py:680`
`apps/studio/backend/app/services/skills.py:684`
`apps/studio/backend/app/services/skills.py:692`

但路径函数不等于创建目录。

创建新 skill 时仅看到 `.workspace` mkdir。

没有看到 `script/` 和 `golden/` 空目录一起创建。

这就是 High-004 当前真实边界。

## API

Tauri/Rust command 当前不是 skill 目录读写 API。

Rust 注册的命令是:

- `get_sidecar_config`
- `get_sidecar_stderr`
- `open_in_cursor`
- `open_in_codex`
- `open_in_terminal`
- `reveal_in_file_manager`

代码位置:
`apps/studio/tauri/src/lib.rs:15`
`apps/studio/tauri/src/lib.rs:35`
`apps/studio/tauri/src/lib.rs:62`
`apps/studio/tauri/src/lib.rs:67`
`apps/studio/tauri/src/lib.rs:72`
`apps/studio/tauri/src/lib.rs:101`
`apps/studio/tauri/src/lib.rs:150`
`apps/studio/tauri/src/lib.rs:156`

Rust 的 `reveal_in_file_manager` 是跨平台 shell command 包装。

macOS 用 `open -R`, Linux 用 `xdg-open`, Windows 用 `explorer /select`:
`apps/studio/tauri/src/lib.rs:73`
`apps/studio/tauri/src/lib.rs:74`
`apps/studio/tauri/src/lib.rs:75`
`apps/studio/tauri/src/lib.rs:82`
`apps/studio/tauri/src/lib.rs:83`
`apps/studio/tauri/src/lib.rs:90`
`apps/studio/tauri/src/lib.rs:91`

前端选择目录不是 Rust command。

它是 Tauri dialog plugin:
`apps/studio/frontend/src/lib/tauri.ts:71`
`apps/studio/frontend/src/lib/tauri.ts:73`

后端 skill 创建 API:

`POST /api/skills`

请求模型:
`apps/studio/backend/app/models/skills.py:118`
`apps/studio/backend/app/models/skills.py:121`
`apps/studio/backend/app/models/skills.py:122`
`apps/studio/backend/app/models/skills.py:123`

router:
`apps/studio/backend/app/routers/skills.py:81`
`apps/studio/backend/app/routers/skills.py:88`

后端 skill detail API:

`GET /api/skills/{skill_id}`

router:
`apps/studio/backend/app/routers/skills.py:98`
`apps/studio/backend/app/routers/skills.py:105`

后端单文件写 API:

`POST /api/skills/{skill_id}/files/{file_path}`

请求模型:
`apps/studio/backend/app/models/skills.py:139`
`apps/studio/backend/app/models/skills.py:142`
`apps/studio/backend/app/models/skills.py:143`

router:
`apps/studio/backend/app/routers/skills.py:365`
`apps/studio/backend/app/routers/skills.py:375`
`apps/studio/backend/app/routers/skills.py:382`
`apps/studio/backend/app/routers/skills.py:393`

WebSocket event API:

`/ws/events`

前端:
`apps/studio/frontend/src/components/studio/Workspace.tsx:220`

后端:
`apps/studio/backend/app/routers/websockets.py:50`
`apps/studio/backend/app/routers/websockets.py:60`

这条 WebSocket 是 file watcher → event bus → frontend hot reload/conflict 的 API 边界。

## Data Model / State

前端 `SkillSummary` 用于 Welcome 卡片。

它包含 id、name、description、phase_count、has_golden、last_run_at、directory_path、config_mismatch:
`apps/studio/backend/app/models/skills.py:26`
`apps/studio/backend/app/models/skills.py:29`
`apps/studio/backend/app/models/skills.py:35`
`apps/studio/backend/app/models/skills.py:36`

前端 `SkillDetail.files` 是文件树和编辑器内容的直接数据源:
`apps/studio/backend/app/models/skills.py:39`
`apps/studio/backend/app/models/skills.py:47`
`apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:35`
`apps/studio/frontend/src/components/studio/Workspace.tsx:93`

`OpenFile` 是前端打开文件状态。

它包含 `hash`, 用于 expected_hash 保存:
`apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:6`
`apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:8`
`apps/studio/frontend/src/components/studio/Workspace.tsx:103`

`UpdateSkillFileReq` 是后端保存契约。

它包含 content 和 expected_hash:
`apps/studio/backend/app/models/skills.py:139`
`apps/studio/backend/app/models/skills.py:142`
`apps/studio/backend/app/models/skills.py:143`

`UpdateSkillFileRes` 返回 path 和 hash:
`apps/studio/backend/app/models/skills.py:146`
`apps/studio/backend/app/models/skills.py:149`
`apps/studio/backend/app/models/skills.py:150`

`SaveConflict` 是前端冲突状态。

它不是后端持久化模型:
`apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:13`
`apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:17`
`apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:18`

file watcher event 是一个 dict。

字段由 `_skill_event_for_path` 生成:
`apps/studio/backend/app/services/file_watcher.py:120`
`apps/studio/backend/app/services/file_watcher.py:125`

`.workspace` 是后端文件布局状态, 不是前端 localStorage 状态。

路径函数显示当前约定:
`apps/studio/backend/app/services/skills.py:672`
`apps/studio/backend/app/services/skills.py:676`
`apps/studio/backend/app/services/skills.py:680`

前端 Recent skills 是 localStorage:
`apps/studio/frontend/src/hooks/useRecentSkills.ts:9`
`apps/studio/frontend/src/hooks/useRecentSkills.ts:29`

前端 draft hook 是 localStorage, 不是 IndexedDB:
`apps/studio/frontend/src/hooks/useDraftPersist.ts:3`
`apps/studio/frontend/src/hooks/useDraftPersist.ts:63`
`apps/studio/frontend/src/hooks/useDraftPersist.ts:156`

当前代码没有 IndexedDB 依赖或调用证据。

因此不要把 workspace-file-system 写成 “IndexedDB draft persistence 已接入主编辑器”。

当前真实状态是:

- 主编辑器 React 内存 draft。
- debounce 后端保存。
- localStorage draft hook 存在但未接主链路。
- 后端 watcher 负责外部变化。
- Tauri shell 不读写 skill 文件内容。

## Cross-feature interaction

本文件只定义 workspace/file-system 边界。

具体 editor 体验请看 [multi-file-editor baseline](../../feature-folders/multi-file-editor/baseline.md)。

具体 skill 创建和生命周期请看 [skill-lifecycle baseline](../../feature-folders/skill-lifecycle/baseline.md)。

具体 trace/golden 目录消费请看 [trace-visualization baseline](../../feature-folders/trace-visualization/baseline.md)。

Audit High-004 在本文件的结论是:

`.workspace` 创建当前由后端 API 负责。

FileWatcher 当前负责监听变化和广播事件。

它不负责初始化 `.workspace`、`script/`、`golden/`。

Tauri/Rust 当前也没有暴露目录读写或 scaffold 初始化 command。
