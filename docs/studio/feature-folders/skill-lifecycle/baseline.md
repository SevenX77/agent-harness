# skill-lifecycle (studio feature) — Baseline (当下代码实现逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-20
> **Scope**: skill 创建、模板、导入/发布、批量运行、golden diff、删除
> **配套**: 见 [INDEX.md](../../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

当前欢迎页主路径使用 `WelcomePage` 和 `NewSkillDialog`，不是 `SkillCreatorWizard`。`WelcomePage` 引入 `NewSkillDialog`，见 `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:43`，并在页面底部挂载，见 `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:350`。`SkillCreatorWizard` 文件存在，但搜索结果显示没有被 WelcomePage 或 Workspace 挂载；其实现入口在 `apps/studio/frontend/src/components/creator/SkillCreatorWizard.tsx:25`。

`SkillCreatorWizard` 本身提供模板选择、基础信息、输入、first phase、preview 五步，并有 Prev/Create/Next 导航，见 `apps/studio/frontend/src/components/creator/SkillCreatorWizard.tsx:121` 到 `apps/studio/frontend/src/components/creator/SkillCreatorWizard.tsx:189`。它支持选择目录和提交创建，见 `apps/studio/frontend/src/components/creator/SkillCreatorWizard.tsx:66` 到 `apps/studio/frontend/src/components/creator/SkillCreatorWizard.tsx:96`。

WelcomePage 支持从本地目录导入 skill：调用 `selectSkillDirectory`，再 POST `/skills`，见 `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:127` 到 `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:159`。欢迎页也提供创建入口和删除入口，打开新 skill dialog 的逻辑见 `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:67` 到 `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:75`，删除逻辑见 `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:77` 到 `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:88`。

批量运行 UI 是 `BatchRunner`，用户选择 test input checkbox 后点击 Run Batch，见 `apps/studio/frontend/src/components/playground/BatchRunner.tsx:22` 到 `apps/studio/frontend/src/components/playground/BatchRunner.tsx:112`。它显示输入名称、大小、内容预览、选择数量和 running 状态，见 `apps/studio/frontend/src/components/playground/BatchRunner.tsx:60` 到 `apps/studio/frontend/src/components/playground/BatchRunner.tsx:108`。

Golden diff 的用户入口分布在 TracePanel 和 run history。TracePanel 有 Compare 和 Golden 按钮，见 `apps/studio/frontend/src/components/TracePanel.tsx:56` 到 `apps/studio/frontend/src/components/TracePanel.tsx:75`；run detail drawer 中有 export button，见 `apps/studio/frontend/src/components/history/RunDetailDrawer.tsx:4` 到 `apps/studio/frontend/src/components/history/RunDetailDrawer.tsx:19`。

## 前端逻辑

创建向导状态由 `useSkillCreator` 管理，包含 step、data、submitting、error，见 `apps/studio/frontend/src/hooks/useSkillCreator.ts:9` 到 `apps/studio/frontend/src/hooks/useSkillCreator.ts:27`。每步校验在 `validateStep`，见 `apps/studio/frontend/src/hooks/useSkillCreator.ts:105` 到 `apps/studio/frontend/src/hooks/useSkillCreator.ts:143`。preview 通过 `generateSkillMd` 生成，见 `apps/studio/frontend/src/hooks/useSkillCreator.ts:145` 到 `apps/studio/frontend/src/hooks/useSkillCreator.ts:151`。

`generateSkillMd` 可根据 wizard data 生成 graph/agent/persona frontmatter。graph 会写 schema_version、io、context_mapping、phases 和 `llm_role`，见 `apps/studio/frontend/src/templates/skillMdGenerator.ts:68` 到 `apps/studio/frontend/src/templates/skillMdGenerator.ts:95`；agent 和 persona 生成逻辑见 `apps/studio/frontend/src/templates/skillMdGenerator.ts:98` 到 `apps/studio/frontend/src/templates/skillMdGenerator.ts:127`。模板内容会被解析、替换 frontmatter 并保留 body，见 `apps/studio/frontend/src/templates/skillMdGenerator.ts:133` 到 `apps/studio/frontend/src/templates/skillMdGenerator.ts:187`。

模板列表由 `useTemplates` 通过 SWR 拉取 `/templates`，见 `apps/studio/frontend/src/hooks/useTemplates.ts:5` 到 `apps/studio/frontend/src/hooks/useTemplates.ts:13`。后端 `list_templates` 扫描 `*.SKILL.md` 并读取 frontmatter，见 `apps/studio/backend/app/services/templates.py:15` 到 `apps/studio/backend/app/services/templates.py:30`。

批量运行 hook `useBatchRun` 拉取 test inputs、维护 selectedInputIds/batchId/batchStatus，并每秒轮询 batch status，见 `apps/studio/frontend/src/hooks/useBatchRun.ts:12` 到 `apps/studio/frontend/src/hooks/useBatchRun.ts:63`。启动 batch 时发送 `{ input_ids }` 到 `/skills/{skillId}/runs/batch-run`，见 `apps/studio/frontend/src/hooks/useBatchRun.ts:73` 到 `apps/studio/frontend/src/hooks/useBatchRun.ts:90`。

## 后端功能

创建 skill 的后端 endpoint 是 `POST /api/skills`，见 `apps/studio/backend/app/routers/skills.py:81` 到 `apps/studio/backend/app/routers/skills.py:95`。`create_new_skill` 如果传入非空目录且目录已有内容，会把该目录作为导入 skill 处理，保存 index 和 summary，见 `apps/studio/backend/app/services/skills.py:443` 到 `apps/studio/backend/app/services/skills.py:465`。否则会 scaffold 默认文件、创建 `.workspace`、初始化本地 repo 并保存 summary，见 `apps/studio/backend/app/services/skills.py:467` 到 `apps/studio/backend/app/services/skills.py:492`。

发布 skill 的 endpoint 是 `POST /api/skills/{skill_id}/publish`，见 `apps/studio/backend/app/routers/skills.py:245` 到 `apps/studio/backend/app/routers/skills.py:280`。发布包由 `build_publish_package` 生成 zip，跳过排除项、symlink 和非文件，见 `apps/studio/backend/app/services/artifact_registry.py:91` 到 `apps/studio/backend/app/services/artifact_registry.py:127`。

删除 skill endpoint 是 `DELETE /api/skills/{skill_id}`，见 `apps/studio/backend/app/routers/skills.py:474` 到 `apps/studio/backend/app/routers/skills.py:482`。fork_skill 服务存在于 `apps/studio/backend/app/services/skills.py:495` 之后，但本 baseline 未展开，因为当前任务关注 B3 Studio feature 的用户可见生命周期。

批量运行由 `RunManager.start_batch_run` 实现。它为每个 input_id 加载 test input，调用 `start_run`，记录 batch_id 到 run_id 的映射，见 `apps/studio/backend/app/services/run_manager.py:335` 到 `apps/studio/backend/app/services/run_manager.py:352`。`get_batch_status` 聚合每个 run 的 metadata，返回 running/success/failed，见 `apps/studio/backend/app/services/run_manager.py:354` 到 `apps/studio/backend/app/services/run_manager.py:385`。

Golden baseline 由 `golden_diff.py` 管理。保存 baseline 会读取 run final_state、写 baseline 文件和 metadata，见 `apps/studio/backend/app/services/golden_diff.py:34` 到 `apps/studio/backend/app/services/golden_diff.py:65`；compare 会加载 run 和 baseline 并递归 diff，见 `apps/studio/backend/app/services/golden_diff.py:68` 到 `apps/studio/backend/app/services/golden_diff.py:160`。

## API

生命周期 API：

- `GET /api/templates`：模板列表，router 见 `apps/studio/backend/app/routers/templates.py:10` 到 `apps/studio/backend/app/routers/templates.py:15`。
- `POST /api/skills`：创建或导入 skill，router 见 `apps/studio/backend/app/routers/skills.py:81` 到 `apps/studio/backend/app/routers/skills.py:95`。
- `DELETE /api/skills/{skill_id}`：删除 skill，router 见 `apps/studio/backend/app/routers/skills.py:474` 到 `apps/studio/backend/app/routers/skills.py:482`。
- `POST /api/skills/{skill_id}/publish`：发布 skill，router 见 `apps/studio/backend/app/routers/skills.py:245` 到 `apps/studio/backend/app/routers/skills.py:280`。

运行与 golden API：

- `POST /api/skills/{skill_id}/runs/batch-run`：启动 batch run，router 见 `apps/studio/backend/app/routers/runs.py:48` 到 `apps/studio/backend/app/routers/runs.py:50`。
- `GET /api/batch/{batch_id}`：前端通过 `api.get(/batch/${batchId})` 轮询，见 `apps/studio/frontend/src/hooks/useBatchRun.ts:39` 到 `apps/studio/frontend/src/hooks/useBatchRun.ts:58`。
- Golden list/set/delete 在 `apps/studio/backend/app/routers/golden.py:15` 到 `apps/studio/backend/app/routers/golden.py:39`。
- Compare 在 `apps/studio/backend/app/routers/compare.py:14` 到 `apps/studio/backend/app/routers/compare.py:29`。

## Data Model / State

创建 wizard 数据结构包含 templateId/templateContent/type/skillId/name/description/tags/inputs/phaseId/llmRole/prompt，见 `apps/studio/frontend/src/templates/skillMdGenerator.ts:13` 到 `apps/studio/frontend/src/templates/skillMdGenerator.ts:25`。输入项类型支持 str/int/float/bool/dict/list，见 `apps/studio/frontend/src/templates/skillMdGenerator.ts:3` 到 `apps/studio/frontend/src/templates/skillMdGenerator.ts:10`。

Skill summary/detail 类型承载生命周期列表和打开后的编辑上下文。`SkillSummary` 在 `apps/studio/frontend/src/api/types.ts:60` 到 `apps/studio/frontend/src/api/types.ts:69`，`SkillDetail` 在 `apps/studio/frontend/src/api/types.ts:383` 到 `apps/studio/frontend/src/api/types.ts:403`。

Batch run 类型包含 request、response、item 和 status，见 `apps/studio/frontend/src/api/types.ts:132` 到 `apps/studio/frontend/src/api/types.ts:149`。Golden 和 compare 类型包含 baseline、SetGoldenReq、FieldDifference、CompareResult，见 `apps/studio/frontend/src/api/types.ts:218` 到 `apps/studio/frontend/src/api/types.ts:248`。

## Cross-feature interaction

与多文件编辑器：创建或导入后的 skill 会进入 workspace，文件由 `SkillDetail.files` 驱动编辑器，详见 [multi-file-editor baseline](../multi-file-editor/baseline.md)。

与 LLM provider config：创建向导生成 graph phase 时写入 `llm_role`，但 roles/provider 的有效性由 Settings 管理，详见 [llm-provider-config baseline](../llm-provider-config/baseline.md)。

与 trace visualization：batch run 产生多个 run，每个 run 仍使用 trace/run detail；golden diff 和 promote baseline 是 TracePanel 的下游能力，详见 [trace-visualization baseline](../trace-visualization/baseline.md)。

与 workspace file system：目录导入、默认 skills root、index entry 和原子写文件属于系统层边界，详见 [workspace-file-system baseline](../../system-level/workspace-file-system/baseline.md)。
