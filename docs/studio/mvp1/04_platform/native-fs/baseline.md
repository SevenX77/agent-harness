---
module: 04_platform/native-fs
doc: baseline
status: drafted（现状对齐 pinned 代码 0d9fbaf；Tauri sidecar/picker/reveal live；实际 skill/graph/package 写入仍经 FastAPI/Python，多处未收敛到 Rust 唯一写者 ⚠️。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/tauri/src/lib.rs:select_directory · apps/studio/tauri/src/lib.rs:reveal_in_file_manager · apps/studio/tauri/src/lib.rs:open_in_cursor · apps/studio/tauri/src/sidecar.rs:SidecarManager · apps/studio/frontend/src/api/client.ts:writeSkillFile · apps/studio/backend/app/services/artifact_registry.py:build_publish_package
units: [native-rust-writer, workspace-open-folder-mru, subgraph-path-inline-drilldown, publish-artifact-autocommit, local-history-snapshot, copilot-session-persistence]
---

# native-fs — Baseline（当下代码实现逻辑）

> **Scope**: Tauri/Rust 本地能力：唯一写者、本地目录选择/打开、sidecar 生命周期、workspace runtime storage 与局部失败状态。
> **现状一句话**: Tauri sidecar/picker/reveal live；实际 skill/graph/package 写入仍经 FastAPI/Python，多处未收敛到 Rust 唯一写者 ⚠️。

## UI/UX
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Runtime config | Tauri exposes sidecar runtime config and stderr commands. | `apps/studio/tauri/src/lib.rs:lib（L19）`, `apps/studio/tauri/src/lib.rs:get_sidecar_config（L39）` |
| Directory picker | Tauri command selects a local directory with optional starting path. | `apps/studio/tauri/src/lib.rs:open_in_codex（L89）` |
| Reveal/open tools | Tauri exposes reveal and external tool helpers. | `apps/studio/tauri/src/lib.rs:spawn_tool（L70）`, `apps/studio/tauri/src/lib.rs:candidate（L129）` |
| Command handler | Tauri registers sidecar, picker, reveal, terminal, and external tool commands. | `apps/studio/tauri/src/lib.rs:app（L306）`, `apps/studio/tauri/src/lib.rs:app（L308）` |
| Sidecar startup | Tauri starts the Python sidecar unless disabled, stores manager or startup error. | `apps/studio/tauri/src/lib.rs:app（L325）`, `apps/studio/tauri/src/sidecar.rs:new（L140）` |
| Runtime URLs/token | Sidecar runtime config returns base URL, websocket URL, resource/config dirs, and API token. | `apps/studio/tauri/src/sidecar.rs:live_backend（L101）`, `apps/studio/tauri/src/sidecar.rs:live_backend（L115）` |
| Sidecar env/CORS | Sidecar process receives resource/config dirs, API token, CORS origins, and orphan-exit flag. | `apps/studio/tauri/src/sidecar.rs:spawn_sidecar_process（L317）`, `apps/studio/tauri/src/sidecar.rs:spawn_sidecar_process（L331）` |
| Current file writes | Frontend file writes call FastAPI `writeSkillFile`; backend writes and records API write. | `apps/studio/frontend/src/api/client.ts:writeSkillFile（L176）`, `apps/studio/backend/app/services/skills.py:update_skill_file（L410）` |
| Current graph writes | Graph serialization goes through FastAPI and Python service. | `apps/studio/frontend/src/api/client.ts:serializeSkillGraph（L95）`, `apps/studio/backend/app/routers/skills.py:compile_skill_endpoint_endpoint（L122）` |
| Run/golden dirs | Python service currently defines `.workspace` run/golden/local/test input directories. | `apps/studio/backend/app/services/skills.py:run_dir_for（L762）` |

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Runtime config | Tauri exposes sidecar runtime config and stderr commands. | `apps/studio/tauri/src/lib.rs:lib（L19）`, `apps/studio/tauri/src/lib.rs:get_sidecar_config（L39）` |
| Directory picker | Tauri command selects a local directory with optional starting path. | `apps/studio/tauri/src/lib.rs:open_in_codex（L89）` |
| Reveal/open tools | Tauri exposes reveal and external tool helpers. | `apps/studio/tauri/src/lib.rs:spawn_tool（L70）`, `apps/studio/tauri/src/lib.rs:candidate（L129）` |
| Command handler | Tauri registers sidecar, picker, reveal, terminal, and external tool commands. | `apps/studio/tauri/src/lib.rs:app（L306）`, `apps/studio/tauri/src/lib.rs:app（L308）` |
| Sidecar startup | Tauri starts the Python sidecar unless disabled, stores manager or startup error. | `apps/studio/tauri/src/lib.rs:app（L325）`, `apps/studio/tauri/src/sidecar.rs:new（L140）` |
| Runtime URLs/token | Sidecar runtime config returns base URL, websocket URL, resource/config dirs, and API token. | `apps/studio/tauri/src/sidecar.rs:live_backend（L101）`, `apps/studio/tauri/src/sidecar.rs:live_backend（L115）` |
| Sidecar env/CORS | Sidecar process receives resource/config dirs, API token, CORS origins, and orphan-exit flag. | `apps/studio/tauri/src/sidecar.rs:spawn_sidecar_process（L317）`, `apps/studio/tauri/src/sidecar.rs:spawn_sidecar_process（L331）` |
| Current file writes | Frontend file writes call FastAPI `writeSkillFile`; backend writes and records API write. | `apps/studio/frontend/src/api/client.ts:writeSkillFile（L176）`, `apps/studio/backend/app/services/skills.py:update_skill_file（L410）` |
| Current graph writes | Graph serialization goes through FastAPI and Python service. | `apps/studio/frontend/src/api/client.ts:serializeSkillGraph（L95）`, `apps/studio/backend/app/routers/skills.py:compile_skill_endpoint_endpoint（L122）` |

## 后端功能
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Runtime URLs/token | Sidecar runtime config returns base URL, websocket URL, resource/config dirs, and API token. | `apps/studio/tauri/src/sidecar.rs:live_backend（L101）`, `apps/studio/tauri/src/sidecar.rs:live_backend（L115）` |
| Current file writes | Frontend file writes call FastAPI `writeSkillFile`; backend writes and records API write. | `apps/studio/frontend/src/api/client.ts:writeSkillFile（L176）`, `apps/studio/backend/app/services/skills.py:update_skill_file（L410）` |
| Current graph writes | Graph serialization goes through FastAPI and Python service. | `apps/studio/frontend/src/api/client.ts:serializeSkillGraph（L95）`, `apps/studio/backend/app/routers/skills.py:compile_skill_endpoint_endpoint（L122）` |
| Run/golden dirs | Python service currently defines `.workspace` run/golden/local/test input directories. | `apps/studio/backend/app/services/skills.py:run_dir_for（L762）` |

## 当前边界（native-fs 现在不是什么）
- 不拥有业务校验；只拥有本地 IO 与生命周期。
- Settings 数据永不 Rust，按 README 四层边界排除。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| 唯一写者 | file/graph writes 仍走 FastAPI/Python ⚠️ | 所有本地写走 Rust/Tauri writer 或明确的 Rust-mediated path |
| 打包写者 | `build_publish_package` Python zip ⚠️ | publish package 写入/打包边界收口到 native-fs |
| sidecar gate | 旧 non-fullscreen gate 引用需对齐 D10 ⚠️ | shell 即时渲染，sidecar 错误局部显示 |
> **验"是否按目标改了"**：1. 唯一写者；2. 打包写者；3. sidecar gate。

## 读代码主路径提示
`apps/studio/tauri/src/lib.rs:select_directory` → `apps/studio/tauri/src/lib.rs:reveal_in_file_manager` → `apps/studio/tauri/src/lib.rs:open_in_cursor` → `apps/studio/tauri/src/sidecar.rs:SidecarManager` → `apps/studio/frontend/src/api/client.ts:writeSkillFile` → `apps/studio/backend/app/services/artifact_registry.py:build_publish_package`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#04-platform-native-fs)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `file-editing` · `editor` · `publish` · `skill-workspace` · `welcome` · `shell-layout`
