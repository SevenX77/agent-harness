# Studio I/O Runtime Data Management - Tasks

状态: Draft for review
日期: 2026-07-06

> 本任务在用户确认设计后才进入实现。实现阶段必须 TDD: 先写失败测试，再写生产代码。

## Phase 0 - Design Confirmation

- [x] 调研现有 runtime_config、io_scan、InputPanel、Workspace 文件打开链路。
- [x] 明确 `.history/` 当前未过滤。
- [x] 明确文件编辑空白的根因。
- [x] 写 Kiro requirement/design/tasks。
- [ ] 用户确认设计。

## Phase 1 - Backend Red Tests

- [ ] 新建 skill / skill detail refresh 会创建 `.workspace/import_files/.phase/<phase_id>/`。
- [ ] runtime_config 扫描忽略 `history/` 和 `.history/`。
- [ ] init / graph 结构变化会清除非当前 phase 目录。
- [ ] 新增、删除、重命名 phase 会同步更新 `.workspace/import_files/.phase/` 下空目录。
- [ ] 同 scope 同字段多 candidate 产生 conflict，不生成 binding。
- [ ] lint/compile 对 required input conflict 报 `STUDIO_RUNTIME_INPUT_CONFLICT`。
- [ ] run 开始时写入 runtime_config 快照。

## Phase 2 - Backend Implementation

- [ ] 新增 `ensure_import_layout(skill_dir, phase_ids)`。
- [ ] runtime_config builder 调用 layout reconciler。
- [ ] io_scan/import copy ignore `history/` 和 `.history/`。
- [ ] bindings builder 改为 conflict-aware，不再 dict 覆盖。
- [ ] lint/compile 读取 conflicts 并输出明确错误。
- [ ] run snapshot 写入当前 runtime_config。

## Phase 3 - Tauri New Skill Tests

- [ ] native-fs 新建 skill 测试断言 `.workspace/import_files/.phase/init/` 存在。
- [ ] phase scaffold 不把 runtime 文件路径写入 md schema。

## Phase 4 - Tauri Implementation

- [ ] native-fs 新建 skill 创建标准 import layout。

## Phase 5 - Frontend Red Tests

- [ ] Input panel 不再显示 `Configure input` 按钮。
- [ ] input 配置内容默认展开。
- [ ] derive model 按 schema 顺序置顶 matched/missing/conflict。
- [ ] runtime_config 或 schema 变化后重新派生 checked 状态。
- [ ] 多 candidate conflict 时 checkbox 仍可操作，同时显示冲突错误。
- [ ] checkbox toggle 会调用 md schema 写入，不写 runtime_config。
- [ ] `.workspace/import_files/...` 文件编辑会真实读取磁盘内容。
- [ ] 文件路径截断有 tooltip。
- [ ] 打开文件夹按钮调用本地打开目录能力。
- [ ] import 按钮同时支持选择文件和文件夹。
- [ ] panel 修改显示 `saving` 小 tag。

## Phase 6 - Frontend Implementation

- [ ] 抽出 `deriveIoCandidateTree` 纯函数。
- [ ] 移除 InputPanel 的折叠按钮和手动保存按钮。
- [ ] 实现 checkbox autosave 队列，遵循统一并发语义。
- [ ] panel 内所有修改直接写真实数据源，和 Properties 面板一致实时保存。
- [ ] input schema 示例基于最新 md 内容实时渲染。
- [ ] 文件行增加 Tooltip。
- [ ] 文件行增加 Open folder 按钮。
- [ ] 修复 Workspace 文件打开链路，让 workspace 文件缺失于 `skillDetail.files` 时读取磁盘。
- [ ] 删除按钮改为删除 import truth 文件/目录，并刷新 runtime_config。
- [ ] import action 合并文件选择和文件夹选择能力。

## Phase 7 - Output / Artifacts Parity

- [ ] 复用 candidate tree / file row 行为到 output/artifacts。
- [ ] output/artifact 文件路径 tooltip、打开、打开文件夹一致。
- [ ] output/artifact 的冲突和排序语义与 input 对齐。

## Phase 8 - Docs / Handbook

- [ ] 更新 `docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md` 的 workspace 文件树标准。
- [ ] 更新 `docs/studio/mvp1/03_regions/input/mvp1-alignment.md`。
- [ ] 更新 frontend handbook 对应切片状态、测试、截图。
- [ ] 重新生成 frontend handbook `index.html`。

## Phase 9 - Gates / Manual Verification

- [ ] Backend: `uv run ruff check ...`
- [ ] Backend: `uv run mypy --strict packages/graph-agent/src`
- [ ] Backend: `uv run mypy --strict packages/graph-agent-gateway/src`
- [ ] Backend: `uv run mypy apps/studio/backend/app`
- [ ] Backend: pytest for changed backend/engine/gateway scopes.
- [ ] Frontend: `npm run lint`
- [ ] Frontend: `npm run typecheck`
- [ ] Frontend: `npm test`
- [ ] Frontend: `npm run build`
- [ ] App manual verification through `scripts/wt-dev.sh --backend` on worktree port.
- [ ] Ship PR via `scripts/wt-ship.sh` after all gates pass.
