# Studio Skill Git 协作系统 — Tasks

> Source: design.md v3 Draft (2026-05-13)
> Status: Draft v1

## §1 P0 — 落盘基建 (无 L2/L3 依赖, 离线可跑通)

### T1.1 建立 OS 级全局配置目录与默认 Skill 根
- **目标**: 把默认 Skill 存储从 repo resource/workspaces 迁移到 OS-specific `AgentStudio` 全局目录, 同时保留测试可注入能力。
- **依据**: design.md 决策 3、4 + §3.2 OS 级目录树
- **file:line 改动清单**:
  - `apps/studio/backend/app/core/paths.py:9-23` — 增加 OS-specific app data 目录 helper, 明确 `app_settings.json` 与 `skill_index.json` 的父目录。
  - `apps/studio/backend/app/core/config.py:32-46` — 引入全局配置目录常量, 调整 `RESOURCE_DIR` fallback 只作为测试/开发覆盖。
  - `apps/studio/backend/tests/test_paths.py:8-17` — 扩展路径 helper 单测, 覆盖 env override 与 OS 默认路径。
- **验收**:
  - [ ] 单元测试覆盖: `test_paths.py` 能断言 Linux/macOS/Windows helper 输出目录形态。
  - [ ] manual smoke: 不设 `STUDIO_RESOURCE_DIR` 启动后, `~/.local/share/AgentStudio/` 或对应平台目录可被创建。
- **预估时长**: 2 小时
- **依赖**: 无

### T1.2 扩展 MetadataStore 为 `skill_index.json` 权威路由表
- **目标**: 用 `skill_index.json` 替代当前 per-workspace `skill_summary.json` 作为 Skill ID → 物理路径的唯一信源。
- **依据**: design.md 决策 4 + §3.2 OS 级目录树
- **file:line 改动清单**:
  - `apps/studio/backend/app/core/ports/metadata.py:11-37` — 增加 `list_skill_index/get_skill_index_entry/save_skill_index_entry/remove_skill_index_entry` 协议。
  - `apps/studio/backend/app/core/adapters/metadata_local.py:14-88` — 新增 `skill_index.json` read/write, 保留 run metadata 能力。
  - `apps/studio/backend/app/core/backends.py:51-57` — 改 `LocalJsonMetadataStore` 构造参数, 使其接收全局 config dir 与 workspace root。
  - `apps/studio/backend/tests/conftest.py:26-37` — fixture 注入临时 config dir, 避免污染真实 OS 目录。
- **验收**:
  - [ ] 单元测试覆盖: 新建 `apps/studio/backend/tests/test_skill_index.py`, 验证空索引、写入、覆盖、删除、坏 JSON 容错。
  - [ ] manual smoke: 创建 Skill 后 `skill_index.json` 出现 `{skill_id: {"absolute_path": "..."}}`。
- **预估时长**: 3 小时
- **依赖**: T1.1

### T1.3 新建 Skill 直写用户选择目录并登记索引
- **目标**: 新建 Skill 时直接写入用户选择的物理目录或 OS 默认 Skills 目录, 不再落到旧 `workspaces/default/skills`。
- **依据**: design.md 决策 1、3、4 + §4.1 新建 Skill 项目流程
- **file:line 改动清单**:
  - `apps/studio/backend/app/services/skills.py:164-216` — 改 `create_new_skill` 默认目录、写入 `skill_index.json`、返回 `directory_path`。
  - `apps/studio/backend/app/services/skills.py:450-477` — 更新 `_validated_directory_path` 与索引冲突检查。
  - `apps/studio/backend/app/models/skills.py:36-41` — 确认 `CreateSkillReq.directory_path` 保持兼容。
  - `apps/studio/backend/tests/test_api.py:120-171` — 更新新建 Skill 断言, 不再期待 `workspaces/default/skills`。
- **验收**:
  - [ ] 单元测试覆盖: 默认路径创建、自定义路径创建、路径冲突、已有 SKILL.md 冲突。
  - [ ] manual smoke: Welcome 创建 Skill 后真实目录含 `SKILL.md`, `skill_index.json` 记录该绝对路径。
- **预估时长**: 3 小时
- **依赖**: T1.2

### T1.4 砍掉隐式 writable fork, 所有写操作直达本体
- **目标**: 废除打开/编辑 public skill 时自动 copy 到 workspace 的行为。
- **依据**: design.md 决策 1 + §6.3 P0 “停用旧时伪副本”
- **file:line 改动清单**:
  - `apps/studio/backend/app/services/skills.py:257-282` — 删除 `storage.copy_tree` fork 逻辑, 找不到索引/本体时直接 404。
  - `apps/studio/backend/app/services/skills.py:285-306` — `resolve_skill_dir_async` 优先 `skill_index.json`, 仅内置示例走 `SKILLS_DIR` 只读路径。
  - `apps/studio/backend/app/services/skills.py:321-336` — 同步版 `ensure_workspace_skill_dir` 改为直达索引或明确只读失败。
  - `apps/studio/backend/tests/test_api.py:99-118` — 更新 PUT 编辑断言, 证明写入原始目录而非 workspace copy。
- **验收**:
  - [ ] 单元测试覆盖: PUT 后原始 `SKILL.md` 变化, 不生成 workspace 副本。
  - [ ] manual smoke: 编辑 Skill 后刷新列表, 同一物理文件内容已变更。
- **预估时长**: 2 小时
- **依赖**: T1.2, T1.3

### T1.5 统一 `.workspace/` 路由 helper
- **目标**: 所有 runs/golden/predict/local_settings 路径统一收口到 `<skill_root>/.workspace/`。
- **依据**: design.md 决策 2、8、16 + §3.1 L1 本地目录树
- **file:line 改动清单**:
  - `apps/studio/backend/app/services/skills.py:354-356` — `run_dir_for` 改为 `<skill_root>/.workspace/runs/<run_id>`。
  - `apps/studio/backend/app/services/skills.py:491-540` — `SkillDetail.file_paths` 改为 `.workspace/runs`, `.workspace/golden`, `.workspace/predict`, `.workspace/local_settings.json`。
  - `apps/studio/backend/app/services/skills.py:649-650` — `_workspace_skills_dir_for` 仅保留兼容或删除引用。
  - `apps/studio/backend/tests/test_api.py:230-252` — 更新 `file_paths["runs_dir"]` 等断言。
- **验收**:
  - [ ] 单元测试覆盖: detail API 返回 `.workspace/*` 路径。
  - [ ] manual smoke: 打开 Skill 后后端返回路径全部落在 `<skill_root>/.workspace/`。
- **预估时长**: 2 小时
- **依赖**: T1.4

### T1.6 搬迁 Run 存储并保留 latest 现场语义
- **目标**: Run 产物写入 `.workspace/runs/<run_id>` 并预留 `.workspace/runs/latest/` 供后续 Save to Team 强制同步。
- **依据**: design.md 决策 16、25 + §4.2 跨终端继续工作
- **file:line 改动清单**:
  - `apps/studio/backend/app/services/run_manager.py:280-326` — `start_run` 使用新 `run_dir_for` 并在成功结束后维护 latest 快照。
  - `apps/studio/backend/app/services/run_manager.py:385-421` — list/detail/delete 适配 `.workspace/runs`。
  - `apps/studio/backend/app/services/run_manager.py:493-520` — run 完成后复制 `final_state.json` 并同步 latest。
  - `apps/studio/backend/tests/test_api.py:313-358` — 更新 run 目录断言。
- **验收**:
  - [ ] 单元测试覆盖: run 完成后 `<skill_root>/.workspace/runs/<run_id>/final_state.json` 与 `latest/` 存在。
  - [ ] manual smoke: 触发一次 Run 后 `.workspace/runs/latest/run_metadata.json` 可读。
- **预估时长**: 3 小时
- **依赖**: T1.5

### T1.7 Golden/Predict 落盘到 `.workspace/golden` 与 `.workspace/predict`
- **目标**: Golden 和 Predict 作为协作质量资产进入 `.workspace`, 不再混在 Skill 根目录或普通 runs。
- **依据**: design.md 决策 8、16 + §3.1 L1 本地目录树
- **file:line 改动清单**:
  - `apps/studio/backend/app/services/golden_diff.py:19-65` — golden root 改为 `<skill_root>/.workspace/golden`。
  - `apps/studio/backend/app/services/golden_diff.py:113-118` — `_golden_root_for/_golden_dir_for` 改用统一 workspace helper。
  - `apps/studio/backend/app/services/predictor.py:54-83` — Predict 结果输出落入 `.workspace/predict` 或通过 run latest 标记可同步。
  - `apps/studio/backend/tests/test_api.py:440-493` — 更新 Golden/Diff 路径断言。
- **验收**:
  - [ ] 单元测试覆盖: promote golden 后 `.workspace/golden/<run_id>/golden_metadata.json` 存在。
  - [ ] manual smoke: Predict 批测后 `.workspace/predict/` 有输出, Skill 根目录无 golden/predict 噪声。
- **预估时长**: 3 小时
- **依赖**: T1.5, T1.6

### T1.8 初始化 L1 Git 仓与 `.gitignore` 模板
- **目标**: 新建 Skill 时自动 `git init`, 写入固定 `.gitignore`, 排除 `.workspace/*` 并放行 golden/predict。
- **依据**: design.md 决策 5、10、16、21 + §3.1 L1 本地目录树
- **file:line 改动清单**:
  - `apps/studio/backend/app/services/skills.py:164-216` — 新建完成后调用 Git 初始化 helper。
  - `apps/studio/backend/app/services/skills.py:205-215` — 写 `SKILL.md` 后创建 `.workspace/` 与 `.gitignore`。
  - 新建 `apps/studio/backend/app/services/git_local.py` — 封装 `git init`, `.gitignore`, `git config --local user.name/user.email`。
  - `apps/studio/backend/tests/test_api.py:120-171` — 新增断言 `.git/`, `.gitignore`, `.workspace/` 存在。
- **验收**:
  - [ ] 单元测试覆盖: `.gitignore` 包含 `/.workspace/*`, `!/.workspace/golden/`, `!/.workspace/predict/`, `/.workspace/local_settings.json`。
  - [ ] manual smoke: 新建 Skill 后 `git -C <skill_root> status` 可运行。
- **预估时长**: 3 小时
- **依赖**: T1.3, T1.5

### T1.9 移除 `.studio.json` 职责并迁移本地 UI 设置
- **目标**: 停用 `.studio.json`, 将项目级 UI 状态统一放入 `.workspace/local_settings.json`。
- **依据**: design.md 决策 6、16 + §3.1 L1 本地目录树
- **file:line 改动清单**:
  - `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:50-54` — 清理旧 `workspace-layout-*` localStorage 兼容策略。
  - `apps/studio/backend/app/services/skills.py:491-540` — `file_paths` 暴露 `local_settings` 路径给前端后续读写。
  - 新建 `apps/studio/backend/app/services/local_settings.py` — 读写 `.workspace/local_settings.json`。
  - `apps/studio/backend/tests/test_api.py:28-52` — 后续补充 settings endpoint 后更新 OpenAPI 断言。
- **验收**:
  - [ ] 单元测试覆盖: `local_settings.json` 创建在 `.workspace/` 且不会进入 `.gitignore` 放行范围。
  - [ ] manual smoke: 折叠面板偏好重启后恢复, Skill 根目录无 `.studio.json`。
- **预估时长**: 2 小时
- **依赖**: T1.5, T1.8

### T1.10 更新前端新建/导入路径提示与类型
- **目标**: 前端展示从旧 `workspaces/default/skills` 改为 OS 默认/用户选择目录, 并能显示 `directory_path`。
- **依据**: design.md 决策 3、13 + UC1
- **file:line 改动清单**:
  - `apps/studio/frontend/src/api/types.ts:30-37` — `SkillSummary` 增加 `directory_path`。
  - `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:93-158` — 新建/导入时展示默认路径与用户选择路径。
  - `apps/studio/frontend/src/components/creator/SkillCreatorWizard.tsx:64-75` — 创建向导支持传入目录选择。
  - `apps/studio/frontend/src/components/creator/steps/StepPreview.tsx:11-15` — 移除旧 `workspaces/default/skills/...` 文案。
- **验收**:
  - [ ] 单元/组件测试覆盖: SkillSummary 类型含 `directory_path`; Preview 不再出现旧 workspace 路径。
  - [ ] manual smoke: Welcome 新建弹窗显示默认 OS 目录, 导入目录后列表能显示绝对路径。
- **预估时长**: 2 小时
- **依赖**: T1.3

### T1.11 P0 后端集成回归
- **目标**: 验证“新建 skill → `.workspace/` 生成 → run/golden/predict 路由 → 索引恢复”离线闭环。
- **依据**: design.md §4.1、§4.5 + §6.3 P0
- **file:line 改动清单**:
  - `apps/studio/backend/tests/test_api.py:28-52` — 更新 OpenAPI surface, 纳入 P0 新 endpoint。
  - `apps/studio/backend/tests/conftest.py:26-37` — 临时根目录 fixture 覆盖 config dir + skill root。
  - 新建 `apps/studio/backend/tests/test_skill_git_p0.py` — 集成验证 P0 目录/索引/路径。
- **验收**:
  - [ ] 集成测试覆盖: 一次完整创建、重载 metadata store、GET detail、start run、promote golden。
  - [ ] manual smoke: 删除内存缓存重启 backend 后 Skill 仍能从 `skill_index.json` 找回。
- **预估时长**: 3 小时
- **依赖**: T1.1-T1.10

## §2 P1 — Auto-commit + Local History

### T2.1 GitLocalService 基础命令封装
- **目标**: 提供可测试的本地 Git 命令层, 统一 cwd、超时、stdout/stderr、错误码。
- **依据**: design.md 决策 5、21、26 + §6.3 P1
- **file:line 改动清单**:
  - 新建 `apps/studio/backend/app/services/git_local.py` — 封装 `git add`, `commit`, `log`, `reset`, `status`。
  - `apps/studio/backend/app/services/skills.py:164-216` — 新建 Skill 后调用 GitLocalService 初始化。
  - `apps/studio/backend/app/core/exceptions.py:1` — 复用标准错误结构包装 Git 失败。
  - 新建 `apps/studio/backend/tests/services/test_git_local.py` — subprocess fake 覆盖。
- **验收**:
  - [ ] 单元测试覆盖: 成功命令、非 0 退出、超时、cwd 不存在。
  - [ ] manual smoke: `git -C <skill_root> log --oneline` 在新建后至少有 initial commit。
- **预估时长**: 3 小时
- **依赖**: T1.8

### T2.2 Auto-commit 接入 run 生命周期
- **目标**: 每次成功 run 结束后自动提交当前有效工作区, commit message 为 `auto-run-<run_id>`。
- **依据**: design.md 决策 5、25 + UC6
- **file:line 改动清单**:
  - `apps/studio/backend/app/services/run_manager.py:462-507` — `_drain_process_queue` 成功结束后触发 auto commit。
  - `apps/studio/backend/app/services/run_manager.py:511-526` — 注入 GitLocalService helper, 便于测试替换。
  - `apps/studio/backend/tests/test_api.py:313-358` — 扩展 run endpoint 测试验证 auto commit 被调用。
- **验收**:
  - [ ] 单元测试覆盖: success 触发 commit, failed 不触发或按 PM 确认策略处理。
  - [ ] manual smoke: 连续跑两次 Run 后 `git log` 出现两个 `auto-run-*`。
- **预估时长**: 2 小时
- **依赖**: T2.1

### T2.3 Auto-commit 排除 latest 但保留 golden/predict
- **目标**: L1 自动提交时尊重 `.gitignore`, 不把 `.workspace/runs/latest/` 强行加入历史。
- **依据**: design.md 决策 16、25 + §4.2
- **file:line 改动清单**:
  - `apps/studio/backend/app/services/git_local.py` — `auto_commit_run` 使用普通 `git add -A`, 禁止 `git add -f .workspace/runs/latest/`。
  - `apps/studio/backend/app/services/run_manager.py:493-507` — latest 文件更新发生在 commit 前后顺序需固定并测试。
  - `apps/studio/backend/tests/test_api.py:313-358` — 增加 latest 未进入 auto commit 的断言。
- **验收**:
  - [ ] 单元测试覆盖: `git status --ignored` 能看到 latest 被忽略, golden/predict 变更可提交。
  - [ ] manual smoke: `git show --name-only HEAD` 不包含 `.workspace/runs/latest/`。
- **预估时长**: 2 小时
- **依赖**: T2.2

### T2.4 文件锁重试与阻断级错误
- **目标**: Git 提交遇到外部文件锁时重试 3 次, 失败后返回可被 UI 展示的阻断错误。
- **依据**: design.md 决策 26
- **file:line 改动清单**:
  - `apps/studio/backend/app/services/git_local.py` — 增加 3 次 retry、错误分类、`GIT_FILE_LOCKED`。
  - `apps/studio/backend/app/services/run_manager.py:462-507` — 捕获 Git 失败并保留 run 成功状态, 同时标记数据游离。
  - `apps/studio/backend/app/models/errors.py:1` — 如需扩展错误 details, 保持 ErrorResponse schema。
  - 新建 `apps/studio/backend/tests/services/test_git_local.py` — fake lock stderr 覆盖 3 次重试。
- **验收**:
  - [ ] 单元测试覆盖: 前 2 次失败第 3 次成功; 3 次失败返回 `GIT_FILE_LOCKED`。
  - [ ] manual smoke: 模拟 `.git/index.lock` 后 Run 完成但 UI 收到红色告警所需字段。
- **预估时长**: 3 小时
- **依赖**: T2.2

### T2.5 Local History API
- **目标**: 暴露单线历史列表, 给 “Local History” 面板读取 auto-run commit。
- **依据**: design.md 决策 23 + §5 Local History
- **file:line 改动清单**:
  - `apps/studio/backend/app/routers/runs.py:23-30` — 可新增 `/api/skills/{skill_id}/history` 或同 router 下 history endpoint。
  - `apps/studio/backend/app/routers/skills.py:31-40` — 如选择 skills router, 在现有 prefix 下注册历史入口。
  - 新建 `apps/studio/backend/app/models/git_history.py` — 定义 history item schema。
  - 新建 `apps/studio/backend/tests/test_skill_git_history.py` — API 集成测试。
- **验收**:
  - [ ] 单元/集成测试覆盖: 空仓、正常 log、损坏 git repo 返回空列表和标准提示码。
  - [ ] manual smoke: Local History API 返回按时间倒序的 `auto-run-*`。
- **预估时长**: 2 小时
- **依赖**: T2.1, T2.2

### T2.6 Revert API
- **目标**: 支持选择一个历史点并回滚活动工程到该 commit。
- **依据**: design.md 决策 23 + §4.5 Revert 流程
- **file:line 改动清单**:
  - `apps/studio/backend/app/routers/runs.py:64-70` — 参考 resume stub 增加 revert endpoint 或改造历史 router。
  - `apps/studio/backend/app/services/git_local.py` — 增加 `reset --hard <sha>` 包装与冲突保护。
  - `apps/studio/backend/app/services/skills.py:88-111` — revert 后重新读取 SkillDetail。
  - 新建 `apps/studio/backend/tests/test_skill_git_history.py` — 覆盖 revert 成功与不存在 sha。
- **验收**:
  - [ ] 集成测试覆盖: 修改 SKILL.md 两次, revert 到旧 sha 后内容恢复。
  - [ ] manual smoke: Local History 选择旧点后画布重新加载旧 manifest。
- **预估时长**: 3 小时
- **依赖**: T2.5

### T2.7 前端 Local History 接线
- **目标**: 将现有 Run History 心智拆出 Local History, 显示 Git 快照并触发 Revert。
- **依据**: design.md 决策 13、23 + UC6
- **file:line 改动清单**:
  - `apps/studio/frontend/src/hooks/useRunHistory.ts:6-52` — 新增或拆分 `useLocalHistory` hook。
  - `apps/studio/frontend/src/components/history/HistoryPanel.tsx:13-24` — 支持 history item 选择与 revert 操作。
  - `apps/studio/frontend/src/api/client.ts:28-31` — 复用 fetcher/API 封装调用 history/revert。
  - `apps/studio/frontend/src/components/studio/Toolbar.tsx:11-18` — 保持业务名词 “Local History”。
- **验收**:
  - [ ] 组件测试覆盖: 空历史、加载失败、点击 Revert。
  - [ ] manual smoke: UI 上能看到 Local History, 回滚后出现成功 Toast。
- **预估时长**: 3 小时
- **依赖**: T2.5, T2.6

## §3 P2 — L2 (Gitea) 协作

### T3.1 全局 App Settings 后端模型与存储
- **目标**: 保存 `Studio User ID` 与 `Gitea Host`, 作为 Git author、Gitea API、Publish author 的统一来源。
- **依据**: design.md 决策 9、10、18、21 + §3.2
- **file:line 改动清单**:
  - `apps/studio/backend/app/core/adapters/metadata_local.py:14-88` — 增加 `app_settings.json` read/write。
  - `apps/studio/backend/app/core/ports/metadata.py:11-37` — 增加 app settings 协议。
  - `apps/studio/backend/app/core/backends.py:51-57` — 确认 LocalJsonMetadataStore 注入 config dir。
  - 新建 `apps/studio/backend/app/models/settings.py` — 定义 user_id/gitea_host schema。
- **验收**:
  - [ ] 单元测试覆盖: 默认 user_id、保存、读取、坏 JSON 回退。
  - [ ] manual smoke: settings 保存后 `app_settings.json` 内容正确。
- **预估时长**: 2 小时
- **依赖**: T1.2

### T3.2 Settings API
- **目标**: 提供前端读取/保存全局 User ID 与 Gitea Host 的 REST 接口。
- **依据**: design.md 决策 18 + P2.3
- **file:line 改动清单**:
  - `apps/studio/backend/app/main.py:19-33` — 引入 settings router。
  - `apps/studio/backend/app/main.py:69-82` — include settings router。
  - 新建 `apps/studio/backend/app/routers/settings.py` — `GET/PUT /api/settings`。
  - `apps/studio/backend/tests/test_api.py:28-52` — 更新 OpenAPI expected paths。
- **验收**:
  - [ ] 集成测试覆盖: GET 默认值、PUT 后 GET 返回新值。
  - [ ] manual smoke: curl `/api/settings` 可读写。
- **预估时长**: 2 小时
- **依赖**: T3.1

### T3.3 Settings Page UI 接入 User ID + Gitea Host
- **目标**: 在 Settings 页面暴露业务化配置字段, 持久化到后端 settings。
- **依据**: design.md 决策 18 + P2.3
- **file:line 改动清单**:
  - `apps/studio/uikit/src/components/studio/settings-page.tsx:144-193` — AccountSection 增加 Studio User ID 字段。
  - `apps/studio/uikit/src/components/studio/settings-page.tsx:311-335` — IntegrationsSection 增加 Gitea Host 字段。
  - `apps/studio/frontend/src/components/studio/SettingsPage.tsx:145-193` — frontend 同步接线。
  - `apps/studio/frontend/src/api/types.ts:1-13` — 增加 settings DTO 类型。
- **验收**:
  - [ ] 组件测试覆盖: 输入 User ID/Gitea Host 后调用 PUT `/settings`。
  - [ ] manual smoke: Settings 修改后刷新页面值仍保留。
- **预估时长**: 3 小时
- **依赖**: T3.2

### T3.4 GitCollaborateService 骨架与 Gitea Client
- **目标**: 建立后端 L2 协作服务, 封装 Gitea repo/branch/PR API 与本地 git push/pull。
- **依据**: design.md 决策 11、18、20 + P2.1
- **file:line 改动清单**:
  - 新建 `apps/studio/backend/app/services/git_collab.py` — `save_to_team/sync_from_team/submit_for_review`。
  - `apps/studio/backend/app/services/skills.py:285-306` — 复用 skill dir resolve。
  - `apps/studio/backend/app/core/backends.py:23-34` — 增加 Gitea host/token 配置来源时保持 env 可测。
  - 新建 `apps/studio/backend/tests/services/test_git_collab.py` — fake Gitea API。
- **验收**:
  - [ ] 单元测试覆盖: 建仓、配置 remote、push main、push dev branch、创建 PR。
  - [ ] manual smoke: 指向本地 Gitea sandbox 可创建 repo。
- **预估时长**: 3 小时
- **依赖**: T2.1, T3.1

### T3.5 `/skills/{skill_id}/sync` API
- **目标**: 暴露 Save to Team / Sync from Team / Submit for Review 单入口。
- **依据**: design.md P2.1 + §5 操作手册
- **file:line 改动清单**:
  - `apps/studio/backend/app/routers/skills.py:5-13` — 增加必要 imports。
  - `apps/studio/backend/app/routers/skills.py:14-20` — 引入 request/response model。
  - `apps/studio/backend/app/routers/skills.py:22-29` — 引入 GitCollaborateService。
  - `apps/studio/backend/app/routers/skills.py:92-110` — 在 validate_input 附近增加 `POST /{skill_id}/sync`。
- **验收**:
  - [ ] 集成测试覆盖: action=`save_to_team|sync_from_team|submit_for_review` 路由到对应 service。
  - [ ] manual smoke: curl `/api/skills/<id>/sync` 返回业务化状态。
- **预估时长**: 2 小时
- **依赖**: T3.4

### T3.6 Save to Team: latest 强制入 L2
- **目标**: 手动保存到团队时执行 `git add -f .workspace/runs/latest/`, 上传最新断点。
- **依据**: design.md 决策 25 + §4.2
- **file:line 改动清单**:
  - `apps/studio/backend/app/services/git_collab.py` — Save to Team 流程强制 add latest。
  - `apps/studio/backend/app/services/run_manager.py:493-507` — 确保 latest 快照完整。
  - `apps/studio/backend/app/services/git_local.py` — 增加 force-add helper。
  - 新建 `apps/studio/backend/tests/services/test_git_collab.py` — 断言命令序列含 `git add -f .workspace/runs/latest/`。
- **验收**:
  - [ ] 单元测试覆盖: auto commit 不 force-add latest, save_to_team force-add latest。
  - [ ] manual smoke: 远端分支包含 `.workspace/runs/latest/`。
- **预估时长**: 2 小时
- **依赖**: T3.4, T2.3

### T3.7 403 切换 PR 模式
- **目标**: main push 遇 403 时自动转入 dev branch + PR 模式, 不让用户卡死。
- **依据**: design.md 决策 19、20 + §4.3
- **file:line 改动清单**:
  - `apps/studio/backend/app/services/git_collab.py` — 捕获 Gitea 403, 返回 `requires_review=true`。
  - `apps/studio/backend/app/routers/skills.py:92-110` — sync endpoint 原样传回状态。
  - `apps/studio/frontend/src/api/client.ts:21-31` — 增加 response interceptor 或错误归一。
  - `apps/studio/frontend/src/components/ui/use-toast.ts:141-190` — 如采用 shadcn toast, 接入 403 提示。
- **验收**:
  - [ ] 单元测试覆盖: fake 403 后 service 创建 dev branch + PR。
  - [ ] manual smoke: 受保护 main 保存时 Toast 提示并按钮变为 Submit for Review。
- **预估时长**: 3 小时
- **依赖**: T3.5, T3.6

### T3.8 前端协作按钮与状态机
- **目标**: 提供 4-5 个业务名词按钮: Save to Team / Sync from Team / Submit for Review / Release to Production。
- **依据**: design.md 决策 13 + UC2-UC5
- **file:line 改动清单**:
  - `apps/studio/frontend/src/components/studio/Header.tsx:7-21` — 增加协作入口按钮区域。
  - `apps/studio/frontend/src/components/studio/Toolbar.tsx:11-18` — 如放工具栏, 保持业务命名。
  - `apps/studio/frontend/src/api/client.ts:70-75` — 增加 sync helper。
  - 新建 `apps/studio/frontend/src/hooks/useSkillSync.ts` — 封装状态机与按钮状态。
- **验收**:
  - [ ] 组件测试覆盖: 403 后按钮从 Save to Team 切 Submit for Review。
  - [ ] manual smoke: 四个按钮可见, UI 不出现 Repository/Commit/Push/Pull。
- **预估时长**: 3 小时
- **依赖**: T3.5, T3.7

### T3.9 Sync from Team 拉取与冲突提示
- **目标**: 支持跨终端拉取 main/dev branch, 恢复 latest, 冲突时给覆盖/稍后再试选项。
- **依据**: design.md §4.2、§5 Sync from Team
- **file:line 改动清单**:
  - `apps/studio/backend/app/services/git_collab.py` — 实现 fetch/rebase/pull/latest restore。
  - `apps/studio/backend/app/services/skills.py:88-111` — sync 后重新编译 SkillDetail。
  - `apps/studio/frontend/src/hooks/useSkills.ts:11-24` — sync 成功后刷新 detail。
  - `apps/studio/frontend/src/components/studio/Workspace.tsx:95-125` — sync 后刷新 canvas/文件状态。
- **验收**:
  - [ ] 集成测试覆盖: 远端有 latest 后 sync 恢复 `.workspace/runs/latest/`。
  - [ ] manual smoke: 终端 B Sync from Team 后可从 latest 继续 Run。
- **预估时长**: 3 小时
- **依赖**: T3.5, T3.6

### T3.10 配置不一致仲裁提示
- **目标**: 当 `skill_index.json` 与 `.git/config` remote 不一致时, UI 提示并建议以 `.git/config` 为基准。
- **依据**: design.md 决策 22
- **file:line 改动清单**:
  - `apps/studio/backend/app/services/git_collab.py` — 加 remote/index mismatch 检测。
  - `apps/studio/backend/app/services/skills.py:43-85` — list summaries 时附带协作状态或告警。
  - `apps/studio/backend/app/models/skills.py:14-23` — `SkillSummary` 增加 warning/mismatch 字段。
  - `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:160-260` — 列表中展示非阻断仲裁提示。
- **验收**:
  - [ ] 单元测试覆盖: index remote 与 git remote 不一致返回 warning。
  - [ ] manual smoke: 手改 `.git/config` 后 Studio 展示仲裁提示, 不静默覆盖。
- **预估时长**: 3 小时
- **依赖**: T3.4

## §4 P2 — L3 (Artifact Registry) 发布

### T4.1 ArtifactRegistryClient 后端
- **目标**: 实现纯业务包上传 client, 不走 Git。
- **依据**: design.md 决策 12、24 + §8.7
- **file:line 改动清单**:
  - 新建 `apps/studio/backend/app/services/artifact_registry.py` — 打包并 POST Registry。
  - `apps/studio/backend/app/core/backends.py:23-34` — 增加 registry host/env 配置。
  - `apps/studio/backend/app/services/skills.py:285-306` — 复用 skill dir resolve。
  - 新建 `apps/studio/backend/tests/services/test_artifact_registry.py` — fake HTTP client。
- **验收**:
  - [ ] 单元测试覆盖: 成功上传、401、500、网络异常。
  - [ ] manual smoke: 指向本地 fake registry 可收到 multipart/zip。
- **预估时长**: 3 小时
- **依赖**: T3.1

### T4.2 发布包剥离 `.workspace/` 并附带 Metadata
- **目标**: L3 包只包含 `SKILL.md/script/example`, 完全没有 `.workspace`, metadata 含 author/time。
- **依据**: design.md 决策 9、12、24 + §8.7
- **file:line 改动清单**:
  - `apps/studio/backend/app/services/artifact_registry.py` — 实现 include/exclude 规则和 metadata 组装。
  - `apps/studio/backend/app/services/diagnostic_export.py:13-21` — 参考稳定 payload 思路, 保持 metadata schema 明确。
  - `apps/studio/backend/app/core/adapters/metadata_local.py:14-88` — 读取 `app_settings.json` author。
  - 新建 `apps/studio/backend/tests/services/test_artifact_registry.py` — 解 zip 断言无 `.workspace/`。
- **验收**:
  - [ ] 单元测试覆盖: zip 内无 `.workspace`, 无 golden/predict/runs/latest。
  - [ ] manual smoke: Release 包解压后只见生产需要文件与 metadata。
- **预估时长**: 2 小时
- **依赖**: T4.1

### T4.3 `/skills/{skill_id}/publish` API
- **目标**: 暴露 Release to Production 后端入口。
- **依据**: design.md §8.7 + §5 Release to Production
- **file:line 改动清单**:
  - `apps/studio/backend/app/routers/skills.py:5-13` — 引入 publish request/response。
  - `apps/studio/backend/app/routers/skills.py:22-29` — 引入 ArtifactRegistryClient/service。
  - `apps/studio/backend/app/routers/skills.py:113-119` — 在 delete stub 前后新增 `POST /{skill_id}/publish`。
  - `apps/studio/backend/tests/test_api.py:28-52` — OpenAPI 增加 publish path。
- **验收**:
  - [ ] 集成测试覆盖: publish 成功返回 artifact id; registry 401/500 返回业务化错误。
  - [ ] manual smoke: curl publish 后 fake registry 有包。
- **预估时长**: 2 小时
- **依赖**: T4.2

### T4.4 前端 Release to Production 接线
- **目标**: 前端提供业务按钮并展示发版失败/成功 Toast。
- **依据**: design.md 决策 13 + UC5
- **file:line 改动清单**:
  - `apps/studio/frontend/src/components/studio/Header.tsx:7-21` — 增加 Release to Production 按钮。
  - `apps/studio/frontend/src/api/client.ts:70-75` — 增加 publish helper。
  - `apps/studio/frontend/src/hooks/useSkills.ts:17-24` — publish 后刷新 Skill 状态或保留草稿状态。
  - `apps/studio/frontend/src/App.tsx:10-20` — 确认 Toaster 已挂载可展示失败提示。
- **验收**:
  - [ ] 组件测试覆盖: 401/500 提示 “发版校验失败或网络异常, 当前版本仍留存在草稿区”。
  - [ ] manual smoke: 点击 Release to Production 后按钮 loading, 成功显示 artifact id。
- **预估时长**: 2 小时
- **依赖**: T4.3

## §5 跨阶段依赖图

```text
T1.1 ──> T1.2 ──> T1.3 ──> T1.4 ──> T1.5 ──┬──> T1.6 ──> T1.7 ──> T1.11
                         │                   ├──> T1.8 ──> T1.9 ─────┘
                         │                   └──> T1.10
                         │
                         └──> T2.1 ──> T2.2 ──> T2.3 ──> T2.4
                                      └──> T2.5 ──> T2.6 ──> T2.7

T3.1 ──> T3.2 ──> T3.3
  │
  ├──> T3.4 ──> T3.5 ──> T3.6 ──> T3.7 ──> T3.8
  │                         └──────────────> T3.9
  └──> T4.1 ──> T4.2 ──> T4.3 ──> T4.4

T3.4 ──> T3.10
```

## §6 测试策略

- **单元测试** (a1 自己写, 跟 src/ 改动一起 commit): 覆盖 `LocalJsonMetadataStore`, `GitLocalService`, `GitCollaborateService`, `ArtifactRegistryClient`。
- **集成测试** (a1 写): backend 端到端走通 P0: 新建 skill → `.gitignore`/`.workspace` → auto-commit → history → revert。
- **E2E 测试** (a3 写, 用 Playwright): 4-5 个按钮的 UX 全流程跑通: Local History, Save to Team, Submit for Review, Sync from Team, Release to Production。
- **跨平台 smoke**: macOS/Linux/Windows 至少验证默认目录、路径空格、文件锁错误文案。

## §7 风险点 (a1 实施前要 PM 确认)

- 风险 1: P0 会改变当前测试和用户数据默认落盘根, 需要 PM 确认旧 `workspaces/default/skills` 是否做一次性迁移, 还是只支持新项目。
- 风险 2: public builtin skill 从可编辑变只读还是自动 import 到用户目录, 需要 PM 明确 UX。
- 风险 3: Auto-commit 对 failed run 是否提交当前状态, design 只写“能够得出输出结果”, 需要 PM 判定 failed/partial 是否入 L1。
- 风险 4: Gitea 鉴权来源未定, design §7 已标注 SSO 与本地伪邮箱映射需后续确认。
- 风险 5: `latest/` 在 Save to Team 强制入 L2 可能含敏感输入数据, 需要 PM 确认脱敏策略是否进入 v1。
- 风险 6: Settings 修改范围横跨 uikit 与 frontend, 需要 PM 确认 uikit 仍作为视觉真相时是否双改。
- 风险 7: L3 Artifact Registry 的上传协议已在 design.md §8 契约中固定，请参考相关 Request/Response 格式。
