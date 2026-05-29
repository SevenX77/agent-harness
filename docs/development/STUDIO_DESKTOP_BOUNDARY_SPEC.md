---
status: Living
target_goal: "定义 Studio 桌面版中 Frontend、Tauri command 与 Python sidecar 的职责边界"
linked_code_paths:
  - apps/studio/frontend/src/lib/tauri.ts
  - apps/studio/tauri/src/lib.rs
  - apps/studio/tauri/src/sidecar.rs
  - apps/studio/backend/app/
linked_specs:
  - docs/development/FRONTEND_UI_SPEC.md
last_updated: 2026-05-29
---

# Studio 桌面能力边界规范

## 1. 目标与非目标

Studio 使用 Tauri 技术栈后，Rust/Tauri 不应只是一个窗口壳；它应成为桌面 OS 能力的唯一收口点。
同时，Tauri 化不等于把所有 Python 领域逻辑重写成 Rust。Python sidecar 仍然是 graph-agent、
skill schema、LLM registry、run artifact 等领域能力的执行环境。

本规范的目标是：

- 把文件选择、外部应用、终端、sidecar 生命周期等 OS 能力收口到 Tauri command。
- 让 Python sidecar 保持领域语义 API，不暴露裸文件系统权限。
- 避免前端通过 HTTP 传 absolute path 触发真实删除、移动、复制或任意进程启动。
- 为新增 endpoint、Tauri command 和删除逻辑提供统一 review checklist。

本规范的非目标是：

- 不要求短期内把现有 Python backend 全部迁移到 Rust。
- 不要求把纯领域配置写入全部搬到 Tauri，例如 LLM roles、API keys registry、run metadata。
- 不禁止 Python 在受控 root 内进行领域数据读写。

## 2. 三层职责

| 层 | 负责 | 不负责 |
| --- | --- | --- |
| Frontend | UI 状态、用户意图、调用 `apps/studio/frontend/src/lib/tauri.ts` 和 HTTP API | 直接访问 `window.__TAURI__`、自行拼 absolute path、直接表达 destructive 文件操作 |
| Tauri command | native dialog、reveal/open、外部应用、终端/PTY、sidecar 生命周期、runtime token、用户选择路径的来源证明 | graph-agent 编译执行、LLM provider 业务规则、skill AST/GRAPH 解析 |
| Python sidecar | skill/run/LLM/git 等领域语义、受控 root 内的原子写入、schema 校验、agent runtime | 裸 OS capability、任意 path delete/move/copy、任意 shell/terminal launch |

### 2.1 Frontend 规则

- 业务组件不得直接解构或调用 `window.__TAURI__`；必须通过 `apps/studio/frontend/src/lib/tauri.ts`。
- HTTP 请求只表达产品意图，例如 `unregisterSkill(skillId)`、`deleteRun(skillId, runId)`。
- 前端不得把用户可编辑的 absolute path 作为 destructive 操作参数发给 Python sidecar。
- 用户可见删除确认遵循 `docs/development/FRONTEND_UI_SPEC.md`：统一使用 shadcn Sonner action/cancel toast。

### 2.2 Tauri command 规则

- Tauri command 是 native capability 的边界，不是业务 API 的镜像。
- 打开 Finder、终端、Cursor、Codex、系统文件夹选择器等能力必须留在 Tauri。
- 未来若产品确实需要真实删除、移动、复制用户磁盘上的文件或目录，应新增窄口径 Tauri command，
  并优先使用系统 Trash/Recycle Bin 语义；不得让 Python HTTP endpoint 接收裸 path 后直接执行。
- Tauri command 接收路径时必须校验空字符串、存在性、目录/文件类型和预期用途。

### 2.3 Python sidecar 规则

- Python API 必须优先使用语义 ID，而不是文件路径：`skill_id`、`run_id`、`endpoint_id`、`role_name`。
- 任何 ID 都必须拒绝空值、`.`、`..`、slash、backslash、URL encoded traversal 和不符合本领域格式的字符。
- Python 可以读写 Studio 管理 root 内的数据，包括 workspace、resource skills、app config、run artifacts。
- Python 只能在明确 root-bound resolver 下访问文件；如果需要处理用户选择目录，路径必须来自 Tauri picker，
  且进入 Python 后仍要做 root/provenance/类型校验。

## 3. 操作分类

| 操作 | 归属 | 规则 |
| --- | --- | --- |
| 选择 skill/import 目录 | Tauri | 使用 native picker；Python 只接收选择结果并做领域校验 |
| Reveal in file manager | Tauri | 只用于展示定位，不改变磁盘 |
| Open in terminal/Cursor/Codex | Tauri | 外部 app/process launch 不走 Python HTTP |
| Sidecar port/token/lifecycle | Tauri | Rust 分配端口、生成 token、启动和关闭 sidecar |
| Delete skill | Python 领域 API | 只注销 Studio 注册和索引；不得删除真实 skill 目录 |
| Delete run | Python 领域 API | 可删除 Studio run artifact，但必须由 `skill_id + run_id` 定位到受控 runs root |
| Delete LLM endpoint/route/role/profile | Python 领域 API | 操作 registry/config 语义对象；必须检查引用关系和 cascade 规则 |
| 真实删除用户选择的目录 | Tauri-only | 必须是显式产品命令，优先 Trash/Recycle Bin，并有 UI 二次确认 |
| Skill create/import/fork | Shared | Tauri 负责目录选择；Python 负责 scaffold、graph/schema、copy into managed location |
| Skill 文件编辑 | Python | 只允许 `skill_id + relative_path`，不得从前端传 absolute path 修改任意文件 |
| Terminal/PTY | Tauri target | 长期收口到 Tauri；过渡期 Python 实现必须命令白名单、cwd root 限定、TTL/reaper |
| Git workflow | Python 领域 API | 允许受控 repo root 内的 git 子命令；外部 app/open 操作归 Tauri |
| LLM provider test/network probe | Python | 领域能力，不属于桌面 OS capability |

## 4. HTTP API 设计红线

新增或修改 HTTP API 时，必须满足以下约束：

- API 名称表达产品语义，不表达底层文件动作。使用 `unregisterSkill`，不要使用 `deletePath`。
- destructive API 不接收 absolute path。
- destructive API 不接收 frontend 自由拼接的 relative path；必须通过领域 ID 和服务端 resolver 定位。
- 如果 API 需要访问 skill 内文件，参数应是 `skill_id + relative_path`，且 relative path 必须被 resolver 限制在 skill root 内。
- 如果 API 需要处理用户选择目录，目录来源必须是 Tauri picker；request DTO 中应能区分 `user_selected_path`
  和普通业务字段，服务端仍需校验路径存在性、类型和允许用途。
- cascade delete 必须写清楚 ownership：只能删除该对象拥有的子对象，不能删除外部引用对象。
- delete/unregister 的文案、endpoint 名称和测试必须区分“从 Studio 移除注册”和“删除磁盘文件”。

## 5. 文件系统与路径规则

### 5.1 Managed roots

Python sidecar 可以操作这些受控 root：

- Studio workspace root，例如默认 workspace skills 与 `.workspace/runs`。
- Studio resource skills root。
- Studio app config root，例如 LLM registry、credentials、roles、skill index。
- 明确由服务端创建并拥有的临时目录。

### 5.2 Absolute path 规则

- Tauri 可以接收 absolute path 用于 reveal/open/select 这类 native UI 能力。
- Python 不得把 absolute path destructive 操作暴露给 HTTP。
- Python 内部 adapter 如果支持 absolute path，只能作为内部实现细节使用；不得直接接到 router DTO。
- 对通用 storage adapter，要优先拆成 root-bound storage 和 user-selected path handler，避免一个方法同时服务安全和危险场景。

### 5.3 Traversal 与 symlink

- 所有 path resolver 必须在 `resolve()` 后检查 `is_relative_to(allowed_root)`。
- 测试必须覆盖 `..`、`%2E%2E`、slash、backslash、空字符串、`.`、symlink escape。
- 不能只在字符串层面检查前缀；必须基于 resolved path。

## 6. 删除语义

删除类功能必须先回答两个问题：

1. 删除的是 Studio registry/config 中的记录，还是用户磁盘上的真实文件？
2. 删除对象是否被其他对象引用，是否有 owned child 需要 cascade？

默认规则：

- `Delete skill` = 从 Studio 注销 skill，不删除真实 skill folder。
- `Delete run` = 删除 Studio 受控 run artifact，可以真实删除 run 目录。
- `Delete LLM role/endpoint/route/profile` = 删除 registry/config 对象，必须做引用检查。
- 真实删除用户文件夹 = Tauri-only，且必须使用明确文案和二次确认。

## 7. 进程与终端规则

- 打开外部应用、系统终端、Finder/Explorer 属于 Tauri command。
- 任意 shell command 不得从 frontend/HTTP 直通。
- Python 允许执行领域需要的受控子进程，例如 git、agent runner、LLM probe 辅助逻辑，但必须满足：
  - command 和 args 由服务端构造或白名单生成；
  - cwd 被限制在受控 root；
  - timeout、错误映射和日志脱敏明确；
  - 不把用户输入拼接成 shell string。
- 长期目标：交互式 Terminal/PTY 收口到 Tauri，Python 只保留领域 runner。

## 8. 测试与验收

### 8.1 Backend tests

涉及 path、delete、move、copy、terminal、git 的变更，至少覆盖：

- 正常语义路径，例如有效 `skill_id` / `run_id`。
- traversal 拒绝：`..`、`%2E%2E`、`a/../b`、backslash。
- absolute path 拒绝或仅在内部受控场景允许。
- symlink escape 拒绝。
- delete 后不误删不属于该产品语义的真实文件。
- 引用关系冲突和 owned child cascade。

### 8.2 Tauri tests

涉及 Tauri command 的变更，至少覆盖：

- 空 path、缺失 path、错误文件类型。
- command 参数构造不使用 shell string。
- 不存在的外部 app 或 terminal fallback 有明确错误。
- sidecar token、port 和 shutdown 行为不退化。

### 8.3 Manual desktop verification

涉及用户可见 native 能力时，必须在 Tauri dev 环境或等价 Tauri bridge 路径下手动验证：

- folder picker / reveal / open terminal / open external editor 的主路径。
- cancel/error 状态。
- 前端非 Tauri fallback 不得被当成 native 能力的唯一验收。

## 9. 当前审计快照

已符合边界或方向正确：

- `apps/studio/frontend/src/lib/tauri.ts` 已集中封装 Tauri bridge。
- `apps/studio/tauri/src/lib.rs` 已承载 `select_directory`、`reveal_in_file_manager`、`open_in_terminal`、
  `open_in_cursor`、`open_in_codex`。
- `apps/studio/tauri/src/sidecar.rs` 已承载动态端口、sidecar token、生命周期。
- `Delete skill` 应保持 unregister 语义，不删除真实 skill folder。
- `Delete run` 可以留在 Python，但必须始终通过 validated `skill_id + run_id` 定位。

需要后续收口或重点 review：

- `LocalFilesystemBackend.delete/move/copy_tree` 支持 absolute path；不得直接暴露给 router DTO，
  后续应拆分 root-bound storage 和用户选择路径 handler。
- `TerminalManager` 当前在 Python 中创建 PTY；这是可接受的过渡态，但长期应迁移到 Tauri command。
- `GitLocalService` 使用 subprocess；保留在 Python 领域层可以接受，但需持续保持 repo root、参数白名单和 timeout。
- Skill import/fork/create 这类涉及用户目录的流程，需要确保目录来源来自 Tauri picker，Python 不执行裸 path destructive op。
- 所有新增 delete endpoint 都要用本规范第 10 节 checklist review。

## 10. 新增能力 Checklist

新增 endpoint、Tauri command 或删除逻辑前，reviewer 必须逐项确认：

- [ ] 这个能力是 OS capability 还是领域逻辑？
- [ ] 如果是 OS capability，是否通过 Tauri command 暴露？
- [ ] 如果是领域逻辑，API 是否只接收语义 ID 或受控 relative path？
- [ ] 是否存在真实文件删除、移动、复制？如果有，是否避免了 Python HTTP 裸 path？
- [ ] 是否区分 unregister/remove-from-Studio 与 delete-from-disk？
- [ ] 是否校验 traversal、encoded traversal、backslash、空值和 symlink escape？
- [ ] 是否明确 cascade ownership 与外部引用冲突？
- [ ] 是否有对应 backend/Tauri tests？
- [ ] 如果影响用户可见 native flow，是否完成 Tauri 环境手动验证？

## 相关 Spec

- [Frontend UI Spec](./FRONTEND_UI_SPEC.md)
- [Skill Studio Tauri README](../../apps/studio/tauri/README.md)
