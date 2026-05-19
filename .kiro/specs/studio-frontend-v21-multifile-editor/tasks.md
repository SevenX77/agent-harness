# studio-frontend-v21-multifile-editor — Tasks

> **Status**: Tasks - Kiro Step 3  
> **Date**: 2026-05-16  
> **Author**: a1 Codex  
> **Spec link**: `requirements.md` + `design.md`  
> **Scope**: Frontend + Backend full stack, T-apps-1；解决 V2.1 多文件编辑、创建、读取、保存阻断。

## Critical Path 概览

21 个 task，约 **83h / 10.5 工作日**。关键 blocker = Backend `GET/POST/PUT files` 契约先落地，再接 Frontend data/UI/e2e。

```text
T-A1/T-A4 -> T-A2 -> T-A3/T-A7 -> T-A5 -> T-B1/T-B2/T-B3 -> T-C1..T-C7 -> T-D1..T-D4
```

---

## T-A1: Req Model 切 `files`
### 目标 (Goal)
`CreateSkillReq` / `UpdateSkillReq` 从 `content` 改为 `files: dict[str, str]`，保留 `extra="forbid"`。
### 修改文件 + 行号
- `apps/studio/backend/app/models/skills.py` line 38-54；R5/R6/R8 + design §4
### DoD (Definition of Done)
- `grep -n "files: dict\\[str, str\\]" apps/studio/backend/app/models/skills.py | wc -l` 输出 `2`。
- `grep -n "content: str" apps/studio/backend/app/models/skills.py | wc -l` 输出 `0`。
- `pytest apps/studio/backend/tests/test_models.py::test_skill_create_update_reject_content_payload` pass。
### 预估工时
2h
### 依赖
blocked_by: 无；⚠️ **必须与 T-A5 同 PR / 同 commit 提交**。
### 风险
若 router 仍消费 `request.content` 会直接 422；同一文件 (`models/skills.py`) 还由 T-A7 改，必须串行 commit 或同 PR squash。

---

## T-A2: 原子写盘 helper
### 目标 (Goal)
实现 `write_skill_files_atomic()`，按 tmpdir 写入、rename swap、失败 rollback 全量替换 skill 目录。
### 修改文件 + 行号
- `apps/studio/backend/app/services/skills.py` line 500-572 附近；R5 + design §4/§6
### DoD (Definition of Done)
- `grep -n "def write_skill_files_atomic" apps/studio/backend/app/services/skills.py | wc -l` 输出 `1`。
- `grep -n "os.rename" apps/studio/backend/app/services/skills.py | wc -l` 输出 `2` 或更多。
- `pytest apps/studio/backend/tests/services/test_skills_write.py::test_write_skill_files_atomic_rolls_back_on_failure` pass。
### 预估工时
6h
### 依赖
blocked_by: T-A1, T-A4；⚠️ **必须与 T-A5 同 PR / 同 commit 提交**。
### 风险
rollback corner case 容易残留 `_tmp` / `_bak`。

---

## T-A3: Service 多文件更新 + inline scaffold
### 目标 (Goal)
实现 `update_skill_files`，并在 `create_new_skill` 内 hardcode 最小 V2.1 scaffold。
### 修改文件 + 行号
- `apps/studio/backend/app/services/skills.py` create/update 区域；R6/R9 + design §3/§4 + Q-1 locked
### DoD (Definition of Done)
- `grep -n "def update_skill_files" apps/studio/backend/app/services/skills.py | wc -l` 输出 `1`。
- `grep -n "phases/init/LOGIC.md\\|io/inputs.json\\|io/outputs.json" apps/studio/backend/app/services/skills.py | wc -l` 输出 `3` 或更多。
- `pytest apps/studio/backend/tests/test_api.py::test_create_skill_uses_inline_v21_scaffold` pass。
### 预估工时
6h
### 依赖
blocked_by: T-A2, T-A4
### 风险
scaffold 必须是 `GRAPH.md` + `phases/init/LOGIC.md` + 空 `{}` IO，不能引回 V2.0 `SKILL.md`。

---

## T-A4: 路径白名单
### 目标 (Goal)
拒绝 `../`、绝对路径、非法后缀，并限制到 V2.1 合法物理结构。
### 修改文件 + 行号
- `apps/studio/backend/app/services/skills.py` 写盘 helper 附近；R7/R10 + design §5.5/§6
### DoD (Definition of Done)
- `grep -n "validate.*skill.*path\\|path.*validation" apps/studio/backend/app/services/skills.py | wc -l` 输出 `1` 或更多。
- `pytest apps/studio/backend/tests/test_security.py::test_skill_file_path_validation_rejects_traversal_absolute_and_bad_suffix` pass。
- `pytest apps/studio/backend/tests/test_security.py::test_skill_file_path_validation_allows_v21_actions_and_tools` pass。
### 预估工时
4h
### 依赖
blocked_by: 无
### 风险
不要误杀 `phases/<id>/actions/*.py` / `tools/*.py`。

---

## T-A5: Router 接新 service
### 目标 (Goal)
`POST /api/skills` 与 `PUT /api/skills/{id}` 传 `request.files`，URL 与 response model 不变。
### 修改文件 + 行号
- `apps/studio/backend/app/routers/skills.py` line 22-71；R5/R6 + design §3/§4
### DoD (Definition of Done)
- `grep -n "update_skill_content" apps/studio/backend/app/routers/skills.py | wc -l` 输出 `0`。
- `grep -n "request.files" apps/studio/backend/app/routers/skills.py | wc -l` 输出 `2` 或更多。
- `pytest apps/studio/backend/tests/test_api.py::test_update_skill_accepts_files_payload` pass。
### 预估工时
2h
### 依赖
blocked_by: T-A1, T-A2, T-A3；⚠️ **必须与 T-A1/T-A2 同 commit**。
### 风险
router 调用 `update_skill_files` 前 service 必须已实现，否则 NameError。

---

## T-A6: Backend 测试补齐
### 目标 (Goal)
补 **T-A1-A5/A7 各 task 单元测试未覆盖** 的边界：legacy `{content}` 422、concurrent atomic write 隔离、oversize files reject。
### 修改文件 + 行号
- `apps/studio/backend/tests/test_api.py`
- `apps/studio/backend/tests/test_security.py`
- `apps/studio/backend/tests/services/test_skills_write.py` 新建；R5-R8 + design §4/§6
### DoD (Definition of Done)
- `grep -R "atomic\\|path\\|scaffold\\|content" apps/studio/backend/tests -n | wc -l` 输出 `4` 或更多。
- `pytest apps/studio/backend/tests/test_api.py::test_update_skill_rejects_legacy_content_payload` pass。
- `pytest apps/studio/backend/tests/test_api.py apps/studio/backend/tests/test_security.py apps/studio/backend/tests/services/test_skills_write.py` pass。
### 预估工时
6h
### 依赖
blocked_by: T-A1, T-A2, T-A3, T-A4, T-A5
### 风险
测试 workspace 必须隔离；T-A6 不重复 T-A1-A5/A7 happy path test，只补边界与反例。

---

## T-A7: Backend GET multifile
### 目标 (Goal)
`GET /api/skills/{id}` 的 `SkillDetail` 返回 `files: dict[str, str]` 正文 map。
### 修改文件 + 行号
- `apps/studio/backend/app/models/skills.py` `SkillDetail`
- `apps/studio/backend/app/services/skills.py` `_detail_from_manifest*` / detail helpers line 519-545 附近；R4 + M-1
### DoD (Definition of Done)
- `grep -n "files: dict\\[str, str\\]" apps/studio/backend/app/models/skills.py | wc -l` 输出 `1` 或更多。
- `pytest apps/studio/backend/tests/services/test_skills_get.py::test_get_skill_returns_files_map` pass。
- `curl -s "$STUDIO_API/api/skills/batch-analysis" | grep -E '"files".*"GRAPH.md".*"io/inputs.json"'` exit 0。
### 预估工时
3h
### 依赖
blocked_by: T-A4；T-B2 blocked_by 本 task
### 风险
读取 files 复用同一白名单，避免泄露临时/隐藏文件；T-A1 + T-A7 改同一 `models/skills.py` 文件，必须 **串行 commit** 或同 PR squash。

---

## T-B1: Workspace store
### 目标 (Goal)
新建 Zustand store，持有 `files`、active file、per-file dirty 与 global `isDirty`。
### 修改文件 + 行号
- `apps/studio/frontend/src/stores/workspace.ts` 新建；R1-R3 + design §1/§3
### DoD (Definition of Done)
- `grep -n "Record<string, string>" apps/studio/frontend/src/stores/workspace.ts | wc -l` 输出 `1` 或更多。
- `grep -n "isDirty\\|dirty" apps/studio/frontend/src/stores/workspace.ts | wc -l` 输出 `2` 或更多。
- `cd apps/studio/frontend && npm run build` exit 0。
### 预估工时
4h
### 依赖
blocked_by: T-A1
### 风险
active file 与 dirty map 必须由 store action 单点更新。

---

## T-B2: API client 多文件读取/保存
### 目标 (Goal)
新增 `fetchSkillFiles`/`saveSkillFiles(skill_id, files)`，前端读取与保存都走 files map。
### 修改文件 + 行号
- `apps/studio/frontend/src/api/client.ts` line 27-30 附近；R3/R5 + design §3/§6 + T-A7
### DoD (Definition of Done)
- `grep -n "saveSkillFiles\\|fetchSkillFiles" apps/studio/frontend/src/api/client.ts | wc -l` 输出 `2` 或更多。
- `grep -n "{ files" apps/studio/frontend/src/api/client.ts | wc -l` 输出 `1` 或更多。
- `cd apps/studio/frontend && npm run build` exit 0。
### 预估工时
3h
### 依赖
blocked_by: T-A5, T-A7, T-B3
### 风险
不能再发送 `{ content }`。

---

## T-B3: API types
### 目标 (Goal)
补 `MultifileSkillPayload`、`SkillDetail.files`、lint error `file:line` 类型。
### 修改文件 + 行号
- `apps/studio/frontend/src/api/types.ts`；R3/R4 + design §3/§6 + T-A7
### DoD (Definition of Done)
- `grep -n "MultifileSkillPayload" apps/studio/frontend/src/api/types.ts | wc -l` 输出 `1` 或更多。
- `grep -n "files.*Record" apps/studio/frontend/src/api/types.ts | wc -l` 输出 `1` 或更多。
- `cd apps/studio/frontend && npm run build` exit 0。
### 预估工时
2h
### 依赖
blocked_by: T-A1, T-A7
### 风险
不要移除 `SkillDetail` 现有 graph/canvas fields。

---

## T-C1: FileTree + react-arborist
### 目标 (Goal)
新增目录树，展示根、`io/`、`phases/`、dirty 红点与 file error 红标。
### 修改文件 + 行号
- `apps/studio/frontend/package.json`
- `apps/studio/frontend/package-lock.json`
- `apps/studio/frontend/src/components/FileTree.tsx` 新建；R1/R10 + design §1/§5.5
### DoD (Definition of Done)
- `grep -n "react-arborist" apps/studio/frontend/package.json | wc -l` 输出 `1`。
- `grep -n "FileTree\\|dirty\\|error" apps/studio/frontend/src/components/FileTree.tsx | wc -l` 输出 `3` 或更多。
- `cd apps/studio/frontend && npm run build` exit 0。
### 预估工时
5h
### 依赖
blocked_by: T-B1
### 风险
只做 design-time 文件选择，不引入运行时 trace/DND 持久化。

---

## T-C2: EditorTabs + dirty close guard
### 目标 (Goal)
新增多 Tab，支持打开、切换、关闭，并在关闭 dirty tab 前确认。
### 修改文件 + 行号
- `apps/studio/frontend/src/components/EditorTabs.tsx` 新建；R2/R3 + design §3 + M-6
### DoD (Definition of Done)
- `grep -n "EditorTabs" apps/studio/frontend/src/components/EditorTabs.tsx | wc -l` 输出 `1` 或更多。
- `grep -n "dirty.*confirm\\|window.confirm" apps/studio/frontend/src/components/EditorTabs.tsx | wc -l` 输出 `1` 或更多。
- `cd apps/studio/frontend && npm run build` exit 0。
### 预估工时
4h
### 依赖
blocked_by: T-B1
### 风险
关闭 dirty tab 不能静默丢编辑。

---

## T-C3: Monaco active model
### 目标 (Goal)
`MonacoPanel` 接 active `ITextModel` 并 `setModel()` 热切，保留 undo 栈。
### 修改文件 + 行号
- `apps/studio/frontend/src/components/MonacoPanel.tsx` line 10-80；R2 + design §1/§3
### DoD (Definition of Done)
- `grep -n "setModel\\|ITextModel" apps/studio/frontend/src/components/MonacoPanel.tsx | wc -l` 输出 `1` 或更多。
- `grep -n "skillCode" apps/studio/frontend/src/components/MonacoPanel.tsx | wc -l` 输出 `0`。
- `cd apps/studio/frontend && npm run build` exit 0。
### 预估工时
6h
### 依赖
blocked_by: T-B1, T-C2
### 风险
model dispose 时机不当会泄漏或销毁已打开 tab。

---

## T-C4: App 接 workspace + 全树保存
### 目标 (Goal)
移除单字符串 `skillCode/setSkillCode`，`Ctrl+S` 调 `saveSkillFiles` 保存全量 files。
### 修改文件 + 行号
- `apps/studio/frontend/src/App.tsx` line 330-360；R3/R9 + design §3/§6
### DoD (Definition of Done)
- `grep -n "saveSkillFiles" apps/studio/frontend/src/App.tsx | wc -l` 输出 `1` 或更多。
- `grep -n "{ content: skillCode\\|setSkillCode" apps/studio/frontend/src/App.tsx | wc -l` 输出 `0`。
- `cd apps/studio/frontend && npm run build` exit 0。
### 预估工时
5h
### 依赖
blocked_by: T-B1, T-B2, T-B3, T-C1, T-C2, T-C3
### 风险
最大集成点；实施 4h 后 checkpoint 检查 model 切换与 Zustand 写入 race。

---

## T-C5: SkillSidebar load files + dirty switch guard
### 目标 (Goal)
选中 skill 后加载 files 到 workspace；dirty 状态下切换 skill 必弹确认。
### 修改文件 + 行号
- `apps/studio/frontend/src/components/SkillSidebar.tsx`
- `apps/studio/frontend/src/App.tsx` skill selection 区域；R1/R2/R3 + design §3 + M-6
### DoD (Definition of Done)
- `grep -n "load.*files\\|setFiles" apps/studio/frontend/src/App.tsx apps/studio/frontend/src/components/SkillSidebar.tsx | wc -l` 输出 `1` 或更多。
- `grep -n "dirty.*confirm\\|window.confirm" apps/studio/frontend/src/components/SkillSidebar.tsx apps/studio/frontend/src/App.tsx | wc -l` 输出 `1` 或更多。
- `cd apps/studio/tests-e2e && npx playwright test multifile-editor.spec.ts -g "unsaved skill switch"` exit 0。
### 预估工时
4h
### 依赖
blocked_by: T-B1, T-B2, T-C4
### 风险
未保存 dirty skill 的取消切换必须保留当前 active skill。

---

## T-C6: DirtyBar
### 目标 (Goal)
新增全局保存状态条，显示未保存文件数、保存中、失败、已保存。
### 修改文件 + 行号
- `apps/studio/frontend/src/components/DirtyBar.tsx` 新建
- `apps/studio/frontend/src/App.tsx` 布局集成；R3/R4 + design §3
### DoD (Definition of Done)
- `grep -n "DirtyBar" apps/studio/frontend/src/components/DirtyBar.tsx apps/studio/frontend/src/App.tsx | wc -l` 输出 `2` 或更多。
- `grep -n "isDirty\\|dirtyCount" apps/studio/frontend/src/components/DirtyBar.tsx | wc -l` 输出 `1` 或更多。
- `cd apps/studio/frontend && npm run build` exit 0。
### 预估工时
3h
### 依赖
blocked_by: T-B1, T-C4
### 风险
状态必须来自全局 dirty map，不是 active file。

---

## T-C7: Frontend 创建 Skill 流程
### 目标 (Goal)
把新建 skill 入口从 `{ content: preview }` 改为 `{ skill_id, files: {} }`，由 backend scaffold。
### 修改文件 + 行号
- `apps/studio/frontend/src/components/creator/SkillCreatorWizard.tsx` line 49-52
- `apps/studio/frontend/src/components/creator/steps/StepPreview.tsx` line 12-15；R6/R9 + Q-1 locked + M-2
### DoD (Definition of Done)
- `grep -rn "api.post.*skills.*content" apps/studio/frontend/src/ | wc -l` 输出 `0`。
- `grep -rn "api.post.*skills.*files\\|api.post<SkillSummary>('/skills'" apps/studio/frontend/src/ | wc -l` 输出 `1` 或更多。
- `cd apps/studio/frontend && npm run build` exit 0。
### 预估工时
2h
### 依赖
blocked_by: T-A3, T-B2
### 风险
Wizard preview 文案不能继续承诺生成 `SKILL.md`。

---

## T-D1: Monaco JSON Schema
### 目标 (Goal)
消费 `node_schema_v21` / `io_schema`，给 `io/*.json` 注入 JSON language service。
### 修改文件 + 行号
- `apps/studio/frontend/src/components/MonacoPanel.tsx`
- `apps/studio/frontend/src/App.tsx`；R4 + design §5/§6
### DoD (Definition of Done)
- `grep -n "node_schema_v21\\|jsonDefaults\\|setDiagnosticsOptions" apps/studio/frontend/src/components/MonacoPanel.tsx apps/studio/frontend/src/App.tsx | wc -l` 输出 `2` 或更多。
- `grep -n "io/inputs.json\\|io/outputs.json" apps/studio/frontend/src/components/MonacoPanel.tsx apps/studio/frontend/src/App.tsx | wc -l` 输出 `1` 或更多。
- `cd apps/studio/frontend && npm run build` exit 0。
### 预估工时
4h
### 依赖
blocked_by: T-C3, T-C4
### 风险
Schema URI 与 model URI 必须稳定。

---

## T-D2: 422 file:line 联动
### 目标 (Goal)
把 422 `lint_result.errors` 的 `file:line` 转 Monaco markers，并标红 FileTree 节点。
### 修改文件 + 行号
- `apps/studio/frontend/src/App.tsx`
- `apps/studio/frontend/src/components/FileTree.tsx`
- `apps/studio/frontend/src/components/MonacoPanel.tsx`；R4 + design §6
### DoD (Definition of Done)
- `grep -n "setModelMarkers\\|markers" apps/studio/frontend/src/App.tsx apps/studio/frontend/src/components/MonacoPanel.tsx | wc -l` 输出 `1` 或更多。
- `grep -n "error.*file\\|file.*error" apps/studio/frontend/src/components/FileTree.tsx | wc -l` 输出 `1` 或更多。
- `cd apps/studio/frontend && npm run build` exit 0。
### 预估工时
5h
### 依赖
blocked_by: T-C1, T-C3, T-C4
### 风险
需兼容无 `file` 的全局 lint error。

---

## T-D3: Reference skill 保存 e2e
### 目标 (Goal)
新增 Playwright e2e：load `batch-analysis` → 展示树 → edit phase file → Ctrl+S → reload 后内容保留。
### 修改文件 + 行号
- `apps/studio/tests-e2e/multifile-editor.spec.ts` 新建；R0/R3/R5 + design §7 + M-7
### DoD (Definition of Done)
- `grep -n "batch-analysis\\|GRAPH.md\\|io/inputs.json\\|reload" apps/studio/tests-e2e/multifile-editor.spec.ts | wc -l` 输出 `4` 或更多。
- `grep -n "atomic\\|Ctrl\\+S\\|Control\\+S" apps/studio/tests-e2e/multifile-editor.spec.ts | wc -l` 输出 `1` 或更多。
- `cd apps/studio/tests-e2e && npx playwright test multifile-editor.spec.ts` exit 0。
### 预估工时
5h
### 依赖
blocked_by: T-A6, T-C4, T-D2
### 风险
⚠️ batch-analysis 实际 phase type 未直接 verify；实施前必须先 `ls apps/studio/skills/batch-analysis/phases/*/` 确认 edit 目标是 `LOGIC.md` / `SUBGRAPH.md` / `SKILL.md`。

---

## T-D4: Scaffold e2e
### 目标 (Goal)
新增 Playwright e2e：点击 New Skill → backend scaffold → 树显示 starter → 可编辑可保存。
### 修改文件 + 行号
- `apps/studio/tests-e2e/multifile-scaffold.spec.ts` 新建；R6 + Q-1 locked + design §4/§7 + M-7
### DoD (Definition of Done)
- `grep -n "GRAPH.md\\|inputs.json\\|outputs.json\\|phases/init/LOGIC.md" apps/studio/tests-e2e/multifile-scaffold.spec.ts | wc -l` 输出 `4` 或更多。
- `grep -n "New Skill\\|POST\\|201" apps/studio/tests-e2e/multifile-scaffold.spec.ts | wc -l` 输出 `2` 或更多。
- `cd apps/studio/tests-e2e && npx playwright test multifile-scaffold.spec.ts` exit 0。
### 预估工时
2h
### 依赖
blocked_by: T-A3, T-C1, T-C7, T-D3
### 风险
e2e 需生成唯一 skill_id 并清理 workspace。

---

## Decisions Locked

- Scaffold 来源: `services/skills.py:create_new_skill` inline hardcode 最小 V2.1 starter (`GRAPH.md` + `phases/init/LOGIC.md` + `io/inputs.json` + `io/outputs.json`)。
- GET files map: `SkillDetail.files` 是 T-A7 的必交付，不再作为 Open Question。
- DirtyBar 已独立为 T-C6；T-C4 降为 5h，不再承载 DirtyBar UI。

## 总工时估算

- Phase A: 29h
- Phase B: 9h
- Phase C: 29h
- Phase D: 16h
- **合计: 83h，约 10.5 工作日。M(1-2 周) 上沿；若 Monaco/e2e 阻塞则按 L 处理。**

## 跟 V2.1 reference skill 对齐

- **设计/测试基准 reference**: `skills/batch-analysis/`。
- **broken skills (反例 corpus, 不在 must-pass)**: 其他 V2.1 skill 不强迫跑通，只用于错误提示与防御性边界。
