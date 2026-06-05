# Studio MVP1 设计文档审计报告

> 审计日期：2026-06-05。范围锁定：`docs/studio/mvp1/` 的 31 个模块文档（62 份 baseline/alignment）+ `04_platform/i18n.md` 单文件，共 63 份。
> 判据已读：`docs/development/design-doc-standards/00-three-axes.md`、`01-writing-standard.md`、`02-audit-standard.md`、`example/baseline-example.md`、`example/alignment-example.md`。项目材料已读：`docs/studio/mvp1/README.md`、三分区 README、`01_workflows/*.md`、`docs/studio/_reorg/workflow-action-catalog.md`、`alignment-notes.md`、`settings-action-catalog.md`、`copilot-action-catalog.md`。

审计结论先行：**63/63 不能进入 FROZEN**。主要不是“没有内容”，而是新规范要求的 `frontmatter + binds_* + binds_code + units + 设计单元 INDEX + baseline 测试锚点` 没落地；当前 `01_workflows/INDEX.md` 是 workflow 走查索引，不是 R8 要求的设计单元 INDEX。

## 逐份文档审计

### docs/studio/mvp1/02_capabilities/compile-lint/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 major — `apps/studio/frontend/src/components/studio/Workspace.tsx:CompileErrorPanel` 仍是底部浮层/全局 toast 路径，和 `01_workflows/03_compile.md:18` drawer 决策不齐。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/02_capabilities/compile-lint/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：stage gate 与 `center-action-bar`/`predict`/`run-execution` 重叠，需要 INDEX 明确 owner。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/02_capabilities/conflict-overwrite/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 minor — `apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.ts:handleSaveConflict` 与顺序覆盖 overlay 是两条 UX，尚未统一成一个冲突呈现单元。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/02_capabilities/conflict-overwrite/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：冲突呈现切面横跨 canvas/editor/file-editing，未登记设计单元。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/02_capabilities/copilot-assist/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 缺 `binds_code`, 缺 `binds_alignment`, 缺 `binds_baseline`, 缺 `units`；R1/R6 本档未见 `.kiro/` 直接 SSOT，但仍缺拓扑证明；R7 FAIL — 有 `status` 但非完整四态锁/无哈希锁表；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 major — `apps/studio/backend/app/services/copilot.py:_translate_sdk_message` 未翻 ThinkingBlock；`apps/studio/frontend/src/store/copilotStore.ts:reset` 仍是内存态，未满足 D8 session 持久化。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/02_capabilities/copilot-assist/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 缺 `binds_code`, 缺 `binds_alignment`, 缺 `binds_baseline`, 缺 `units`；R1/R6 本档未见 `.kiro/` 直接 SSOT，但仍缺拓扑证明；R7 FAIL — 有 `status` 但非完整四态锁/无哈希锁表；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：PM 原话充足，但 frontmatter 缺 `binds_baseline/units`，且 F7 数据流跨 golden/publish 未由 INDEX 约束。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/02_capabilities/debug-resume/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 critical — `apps/studio/backend/app/routers/runs.py:resume_run` 直接 `raise_not_implemented`，节点级 resume 主路径不可用。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/02_capabilities/debug-resume/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：依赖 engine checkpoint/resume，但未绑定 `docs/engine/mvp1/` 具体契约符号。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/02_capabilities/file-editing/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 major — `apps/studio/frontend/src/api/client.ts:writeSkillFile` 与 `apps/studio/frontend/src/components/studio/Workspace.tsx:handlePhaseFileSave` 仍走 FastAPI 写 skill 文件，和 D12 Rust 唯一写者冲突。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/02_capabilities/file-editing/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：D12 Rust 写路径、trace 只读、debug tamper 三个切面跨 native-fs/timeline/debug，缺设计单元 owner。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/02_capabilities/golden-eval/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 major — `apps/studio/backend/app/services/golden_diff.py:set_golden_baseline_for_run` 仍复制整次 run 的 final_state，和逐 agent-node golden 目标冲突。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/02_capabilities/golden-eval/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：per-node golden 与 engine eval/native-fs storage/copilot bar 跨模块，未登记 spans。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/02_capabilities/graph-authoring/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 critical — `apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.ts:defaultPhaseMarkdown` 生成 `mode/system_prompt/exit_contract/python_callable` 旧格式；`apps/studio/frontend/src/components/studio/SubgraphInline.tsx:SubgraphInline` 仍是假数据。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/02_capabilities/graph-authoring/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：子图 path/inline/drilldown、布局、L3 步骤横跨 graph-authoring/canvas/assets/native-fs，缺 INDEX。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/02_capabilities/phase-editing/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 critical — `apps/studio/frontend/src/components/studio/panels/phase-frontmatter.ts:parsePhaseForm` 继续读写 V2.x `mode/system_prompt/exit_contract/python_callable`。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/02_capabilities/phase-editing/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：字段白名单应绑定 engine skill-spec 符号；当前只引用 workflow 行。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/02_capabilities/predict/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 critical — `apps/studio/frontend/src/components/studio/Workspace.tsx:onPredict` 仅 `console.info("predict clicked")`，前端主入口未接 `postPredictRun`。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/02_capabilities/predict/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：predict-pass/stage gate 和 compile-lint/run-execution 重叠，需要单 owner。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/02_capabilities/publish/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 major — `apps/studio/backend/app/services/artifact_registry.py:build_publish_package` 在 Python 打 zip，需按 D12 迁 native-fs/Rust 编排；现状低优先但不能 FROZEN。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/02_capabilities/publish/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：Artifact Registry 与 autocommit 区分较清楚，但 D12 打包落盘 owner 未由 INDEX 锁。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/02_capabilities/run-execution/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 critical — `apps/studio/frontend/src/components/studio/Workspace.tsx:onRun` 仅 `console.info("run clicked")`，且 `GraphCanvas:statusByNodeId` 未传真实 run 状态。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/02_capabilities/run-execution/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：batch/loop 依赖引擎设计，当前只登记 workflow，未绑定 engine mvp1 契约。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/02_capabilities/skill-workspace/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 major — `apps/studio/backend/app/services/skills.py:list_skill_summaries` 仍是注册表聚合；`services/skills.py:import_existing` 仍有 GRAPH/SKILL 门禁，违 D11/D2。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/02_capabilities/skill-workspace/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：D11/D2 已对齐，但 “Remove from Studio”/MRU/native-fs spans 未登记。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/02_capabilities/studio-settings/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 major — `apps/studio/frontend/src/components/studio/settings/LlmRolesTab.tsx:roleTestStates` 与 `CopilotTab.tsx:routeStatusOverrides` 仍是前端易失真相；`llm_import_drafts.py:sync_remote_evidence_library` 直接 `os.getenv("STUDIO_CATALOG_URL")`。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/02_capabilities/studio-settings/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：6态/role materializer/draft/copilot SDK test 与 gateway/HTTP/settings region 重叠，缺设计单元。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/02_capabilities/trace-observability/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 major — `apps/studio/frontend/src/components/edges/ContextEdge.tsx:getMockEdgeContext` 仍生成假黑板；`TracePanel`/`useRunStream` 已建未挂载。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/02_capabilities/trace-observability/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：dot 黑板、prompt inspector、trace 文档、node-state deriver 横跨 trace/timeline/canvas/editor/state-engine/engine，缺 INDEX。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/03_regions/assets/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 major — `apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:subgraph detection` 仍读 `mode/sub_skill_ref` 等旧形态，和 D7 path 模型冲突。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/03_regions/assets/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：subgraph path 与 workspace membership 应链接 `skill-workspace`/`native-fs` owner。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/03_regions/canvas/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 major — `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:buildNodes` 默认首节点 success，`ContextEdge:getMockEdgeContext` 假黑板，运行/trace/debug 不是实时源。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/03_regions/canvas/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：运行态节点灯、trace dot、debug resume 与 trace/state-engine/debug 重叠。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/03_regions/center-action-bar/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 critical — `apps/studio/frontend/src/components/studio/Workspace.tsx:onPredict/onRun` 是桩，stage gate 的成功路径不可达。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/03_regions/center-action-bar/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：stage gate owner 与 compile-lint/predict/run-execution 重复。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/03_regions/copilot/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 major — `apps/studio/frontend/src/components/studio/Workspace.tsx:CopilotPanel` 有 `skillId/currentSkillId` 传参风险；Settings Copilot 仍依赖 `mock-copilot-data`。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/03_regions/copilot/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：region 只应写 UI，本档仍承载模型/SDK 行为，需要回链 copilot-assist/studio-settings。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/03_regions/editor/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 major — `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:writeSkillFile` 仍走 FastAPI 写，D12 Rust 写路径未落；trace/debug 只读/可写复用未接。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/03_regions/editor/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：写路径归 native-fs、trace/read-only/debug tamper 跨能力，缺 unit。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/03_regions/input/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 critical — `apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:inputFiles` 投影假 `input/schema.json`；`apps/studio/backend/app/routers/test_inputs.py:create_test_input/delete_test_input` 仍 501。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/03_regions/input/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：i/o panel 同时承载 phase-editing 与 predict/run input，需 INDEX 分切面。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/03_regions/local-history/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 minor — `apps/studio/frontend/src/components/history/HistoryPanel.tsx:HistoryPanel` 只显示 git snapshot，run detail/batch summary ownership 未接。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/03_regions/local-history/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：snapshot 语义和 publish autocommit/native-fs/history UI 边界需锁。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/03_regions/properties/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 major — `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:PropertiesPanel` 仍含 stale phase form 与 selected-edge JSON dump。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/03_regions/properties/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：field diagnostics、golden diff、trace dot 三类跨能力混在 region 文档里，需 units 切开。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/03_regions/settings/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 major — 同 `studio-settings`: `LlmRolesTab.tsx:roleTestStates`、`CopilotTab.tsx:routeStatusOverrides`、`mock-copilot-data.ts` 仍在设置 UI 路径。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/03_regions/settings/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：和 `studio-settings` 内容高度平行，INDEX 应声明 region UI 切面 vs capability 机制切面。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/03_regions/shell-layout/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 major — `apps/studio/frontend/src/App.tsx:RuntimeGate` 仍全屏 gate，和 D10 eager sidecar + shell immediate render 冲突。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/03_regions/shell-layout/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：RuntimeGate 退役、settings overlay、copilot slot、publish header 横跨平台/能力，缺 owner。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/03_regions/timeline/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 major — `apps/studio/frontend/src/components/TracePanel.tsx:TracePanel` 与 `hooks/useRunStream.ts:useRunStream` 未挂到 `TimelinePanel` 成功路径。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/03_regions/timeline/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：trace live/history、prompt inspector、run list 与 trace-observability/run-execution 重叠。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/03_regions/welcome/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 major — `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:WelcomePage` 仍读 `/skills` 注册表列表并保留 import/delete 旧语义。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/03_regions/welcome/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：Home region 的 Open Folder/Remove from Studio 与 skill-workspace/native-fs 双写，需要 INDEX。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/04_platform/engine/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 major — Studio 侧 `apps/studio/backend/app/routers/runs.py:resume_run` 501；engine 细节应引用 `docs/engine/mvp1/` SSOT，不在 Studio 重写。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。 engine 细节只引用 `docs/engine/mvp1/` 的 contract/mechanism 符号，不在 Studio 复制。

### docs/studio/mvp1/04_platform/engine/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：已经声明 engine 内部细节归 `docs/engine/mvp1/`，这是正确方向；仍缺 frontmatter 绑定和具体 engine contract 符号。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。 engine 细节只引用 `docs/engine/mvp1/` 的 contract/mechanism 符号，不在 Studio 复制。

### docs/studio/mvp1/04_platform/gateway/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 major — `apps/studio/backend/app/routers/llm.py:router` 巨型路由承载 HTTP glue + probe/materialize/draft/6态内核；`_role_test_jobs` 为内存 job store。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。 gateway 公共能力内核只绑定 graph-agent-gateway SSOT，Studio 文档只保留 ③a 适配壳/消费面。

### docs/studio/mvp1/04_platform/gateway/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：把 provider registry/materializer/6态/draft 写在 Studio platform 内，存在复制 gateway SSOT 风险。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。 gateway 公共能力内核只绑定 graph-agent-gateway SSOT，Studio 文档只保留 ③a 适配壳/消费面。

### docs/studio/mvp1/04_platform/llm-copilot-http-api/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 缺 `binds_code`, 缺 `binds_alignment`, 缺 `binds_baseline`, 缺 `units`；R1/R6 FAIL — 正文含旧/临时源引用，需要区分 SSOT 与留底；R7 FAIL — 有 `status` 但非完整四态锁/无哈希锁表；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 major — `apps/studio/backend/app/routers/llm.py:_probe_copilot_sdk_tool_call` 走 `AsyncAnthropic`，而真实 chat 走 `ClaudeSDKClient`，测试路径不等价。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。 gateway 公共能力内核只绑定 graph-agent-gateway SSOT，Studio 文档只保留 ③a 适配壳/消费面。

### docs/studio/mvp1/04_platform/llm-copilot-http-api/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 缺 `binds_code`, 缺 `binds_alignment`, 缺 `binds_baseline`, 缺 `units`；R1/R6 本档未见 `.kiro/` 直接 SSOT，但仍缺拓扑证明；R7 FAIL — 有 `status` 但非完整四态锁/无哈希锁表；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：比多数文档颗粒度好，但缺 `binds_baseline/units`；model profile snapshot 是 authoring abstraction 术语，需避免与 stale snapshot 混淆。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。 gateway 公共能力内核只绑定 graph-agent-gateway SSOT，Studio 文档只保留 ③a 适配壳/消费面。

### docs/studio/mvp1/04_platform/native-fs/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 major — `apps/studio/frontend/src/api/client.ts:writeSkillFile`、`services/artifact_registry.py:build_publish_package` 等本地写仍非 Rust 唯一写者；`tauri.ts:open_in_cursor/open_in_terminal/open_in_codex` 是 D3 死代码。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/04_platform/native-fs/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：D12 唯一写者正确，但 spans 覆盖几乎所有本地写，必须有设计单元索引。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/04_platform/state-engine/baseline.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — baseline 无规范「baseline / alignment 差异(测试锚点)」表；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q4 ⚠️ — baseline 多为 Current Code Index + Known Drift，缺范例级差异表；代码证据多为 `文件:行号`，不是 `文件:符号名` 主证据。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 major — `RuntimeGate`、`roleTestStates`、`routeStatusOverrides` 分散持状态，尚无单一 state-engine/WS bridge。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/04_platform/state-engine/mvp1-alignment.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 部分 PASS — alignment 以 F1/F2 功能段写目标和测试点；但缺 `binds_baseline` 与 units，职责锁不成立；R5 FAIL — 无 frontmatter；R5 FAIL — 能力/区域文档直接引用 workflow 行号，未走设计单元 INDEX 枢纽；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 有目标功能段，但多数只引 workflow 行号，PM 原话/决策动机未就近完整落；跨模块一致性无法经 INDEX 校验。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 内容轨：state-engine 与各 feature 状态源边界未锁，尤其 settings/test/run/trace。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

### docs/studio/mvp1/04_platform/i18n.md
- R0–R8: FAIL — R0/R2/R3 局部可读；R4 FAIL — 单文件未按 baseline/alignment 配对职责建模，缺测试锚点与配对绑定；R5 FAIL — 无 frontmatter；R1/R6 本档未见 `.kiro/` 直接 SSOT，但仍缺拓扑证明；R7 FAIL — 无规范 `status`；R8 FAIL — 本档无 `units` 且项目缺设计单元 INDEX。
- Q1–Q5: ⚠️ — Q1/Q2/Q3 ⚠️ — 设计叙述较细，但单文件横切无 `units`/INDEX，不能锁 spans。 Q5 需回扣 `docs/studio/mvp1/README.md` 的 deferred/non-goals；当前 scope 多靠 workflow 行号而非模块 frontmatter 锁定。
- 🚨 本档真空 / 债: 代码轨 major — `apps/studio/frontend/src/lib/llm-error-messages.ts:composeTestErrorMessage` 仅英文 catalog；react-i18next 骨架未落。 迁移债：补规范 frontmatter、双向引用、units，并把正文 line-only 证据迁成 `文件:符号名`。
- 修复建议: 按 `01-writing-standard.md` 模板重写：baseline 增 `binds_alignment/binds_code/units` 与差异测试锚点；alignment 增 `binds_baseline/units`、PM 原话与接口契约；把本模块涉及的横切 unit 登进设计单元 INDEX。

## 全局汇总

### ① FAIL 总清单（按优先级）
- **P0 / R8：设计单元 INDEX 缺失。** 证据：`docs/studio/mvp1/01_workflows/INDEX.md:1` 标题为 “Skill Studio UI/UX 工作流总览”，仅列 workflow nodes；规范 `02-audit-standard.md:R8` 要求 INDEX 行含「单元｜源 workflow/atom action｜spans 模块×切面｜binds_code｜锁状态」。现有 63 份对象文档全部缺 `units`。
- **P0 / R5：双向引用拓扑缺失。** 证据：63 份对象文档均无 `binds_code`；除 `copilot-assist` 与 `llm-copilot-http-api` 少数文档外，绝大多数无任何 frontmatter；代码中也没有 baseline 注释绑定，`rg "binds_code|mvp1-alignment|design unit" apps/studio/*` 只命中业务词 “golden baseline”，不是设计绑定。
- **P0 / R7：锁状态不合规。** 证据：59/63 无 frontmatter `status`；4/63 有 `status` 但仍缺 `binds_*`/`units`，未审计通过且无哈希锁表。所有文档均不得进 `FROZEN`。
- **P1 / R4/Q1：baseline 普遍缺差异测试锚点。** 证据：`docs/development/design-doc-standards/example/baseline-example.md` 有 “baseline / alignment 差异(测试锚点)”表；对象 baseline 多为 `Current Code Index / Current Coverage / Known Drift`，扫描仅 `llm-copilot-http-api/mvp1-alignment.md` 命中类似差异字样。
- **P1 / R2/代码轨：line-only 证据抗漂移不足。** baseline 正文大量写 `apps/studio/...:行号`；规范 `01-writing-standard.md:2` 要求 baseline 用 `文件:符号名` 为主、行号为辅。
- **P1 / R1/R6：旧源与临时源仍混在权威链。** `docs/studio/mvp1/README.md:4` 把 `.kiro/specs/studio-feature-*` 写为设计来源；`01_workflows/00_settings.md:3` 与 `02_authoring.md:3` 仍写 `.kiro/specs...`/旧 engine FROZEN 源；`03_compile.md:44`、`04_run-and-verify.md:144`、`05_debugging.md:38` 引 `_reorg/*prompt*.md`，按本次任务说明这类 prompt 属临时源。

### ② 🚨 去-旧版债总账
- `.kiro/specs/studio-feature-*`：当前只能作历史参考，不得作 SSOT。需从 `docs/studio/mvp1/README.md:4`、`01_workflows/00_settings.md:3`、`01_workflows/02_authoring.md:3` 的权威表述中降级或删除。
- `_reorg/*-prompt*.md` / `gemini-prompt-batch-loop.md`：`01_workflows/03_compile.md:44`、`04_run-and-verify.md:144`、`05_debugging.md:38` 仍把 prompt 当引擎需求引用；需要迁成 engine mvp1 SSOT 符号，prompt 只留审计附件。
- `docs/engine/mvp0/skill-spec` / 旧 FROZEN：`01_workflows/02_authoring.md:3` 仍写旧 engine FROZEN；studio 对 engine 拥有的契约应引用 `docs/engine/mvp1/`，尤其子图落点、golden 路径、skill 语法、错误码、resolver 协议。
- 旧 publish 散文：当前 workflow 已修正为 Artifact Registry，但对象文档仍需在 `publish`/`shell-layout`/`local-history` 的 unit 里锁“发布 != git push；autocommit 属本地存档”。证据：`docs/studio/mvp1/01_workflows/06_eval.md:13`、`apps/studio/backend/app/routers/skills.py:publish_skill`、`artifact_registry.py:build_publish_package`。

### ③ 双向引用缺口（代码 / baseline / alignment）
- **代码 ↔ baseline：缺。** 所有 baseline 没有 `binds_code` frontmatter；代码里也无反向设计注释。能从正文顺藤定位的代码债见逐档“代码轨”。
- **baseline ↔ alignment：缺。** 大多数配对只靠同目录文件名；无 `binds_alignment` / `binds_baseline`。`copilot-assist` 与 `llm-copilot-http-api` 虽有 frontmatter，也缺这些绑定字段。
- **能力模块 ↔ 设计单元 INDEX：缺。** `units` 全缺；现有 `01_workflows/INDEX.md` 不含 spans/binds_code/锁状态，不能承担 R8 枢纽。
- **能力/区域/平台互链：弱。** 正文多写 `Region links` / `Platform link`，但没有双向校验；例如 `compile-lint`、`center-action-bar`、`predict`、`run-execution` 都写 stage gate，owner 未锁。

### ④ 跨模块 drift
- **stage gate drift：** `compile-lint`、`center-action-bar`、`predict`、`run-execution`、`state-engine` 都描述 Compile→Predict→Run gate；`workflow-action-catalog.md:20` 已指出应归 `compile-lint` 单一 owner。
- **settings 5态 vs 6态：** `00_settings.md:4` 仍描述 `ready/untested/cooling_down/needs_setup/off` 五态；`00_settings-ux-spec.md:255` 锁 6 态（含 `historical_ready` 与 `failed(reason)`）。对象 docs 多写 6 态，但 workflow 高层仍有旧态，需回写。
- **subgraph path/inline/drilldown：** `skill-workspace`、`assets`、`canvas`、`graph-authoring`、`phase-editing`、`native-fs` 都涉及 path/展开/导入，但没有一个 unit 指定 owner；代码仍有 `AssetsPanel.tsx:sub_skill_ref` 与 `SubgraphInline` 假数据。
- **gateway ③a/③b 边界：** `gateway` platform 与 `llm-copilot-http-api` 都写 materialize/6态/draft/probe；后者标“内核待下沉”，但没有 binds 到 graph-agent-gateway SSOT，容易复制两份真理。
- **trace/dot/debug：** `trace-observability`、`timeline`、`canvas`、`properties`、`debug-resume`、`state-engine` 都写 dot 黑板/节点灯/事件派生；代码仍 `ContextEdge:getMockEdgeContext`。
- **golden：** baseline 记录 whole-run snapshot，alignment 目标 per-node；涉及 `golden-eval`、`predict`、`run-execution`、`copilot-assist`、`native-fs`、`engine`，无 unit 锁。

### ⑤ 锁状态清单（status + 可否进 FROZEN）
- **无 frontmatter status：59 份。** 所有普通 capability/region/platform baseline/alignment（除 `copilot-assist/*`、`llm-copilot-http-api/*`）以及 `04_platform/i18n.md` 都不能进入 FROZEN。
- **有 status 但不能 FROZEN：4 份。** `02_capabilities/copilot-assist/baseline.md`、`02_capabilities/copilot-assist/mvp1-alignment.md`、`04_platform/llm-copilot-http-api/baseline.md`、`04_platform/llm-copilot-http-api/mvp1-alignment.md` 有 frontmatter `status`，但缺 `binds_*`、`binds_code`、`units` 和哈希锁，仍 FAIL。
- **单元级锁：0。** 因为 INDEX 不存在，`unit-lock` 无从登记；任何横切单元都不能单独 locked。

### ⑥ 设计单元索引覆盖
- **必须新增 INDEX 文件或改造现有 INDEX：** 建议不要复用 `01_workflows/INDEX.md` 的 workflow 索引语义，另建 `docs/studio/mvp1/DESIGN_UNITS_INDEX.md` 或将 R8 表单独成节。
- **首批横切单元清单：** `native-rust-writer`、`workspace-open-folder-mru`、`subgraph-path-inline-drilldown`、`phase-field-whitelist`、`io-panel-artifacts-test-inputs`、`compile-stage-gate`、`predict-pass-run-gate`、`run-batch-loop-range`、`trace-dot-blackboard`、`event-to-node-state`、`golden-per-agent-node`、`debug-resume-checkpoint`、`settings-six-state-provider-health`、`model-group-role-bundle-materialization`、`copilot-sdk-test-parity`、`copilot-session-persistence`、`copilot-mention-safe-write`、`publish-artifact-autocommit`、`local-history-snapshot`、`i18n-error-code-ui-copy`、`conflict-overwrite-resolution`。
- **重复 owner 风险：** stage gate、6态投影、materializer、trace dot、golden diff、D12 本地写者目前均被多个模块同时描述；INDEX 需要精确到「模块 × 切面」，否则无法审 Q3。
- **真空：** 所有 unit 当前都没有 `binds_code`，也没有 `unit-lock`；不能对外宣称任何横切设计已锁。

## 附：代码轨重点缺陷（按严重度）
- **critical** — `apps/studio/frontend/src/components/studio/Workspace.tsx:onPredict/onRun` 仍是 `console.info` 桩：predict/run 成功路径不可达。
- **critical** — `apps/studio/backend/app/routers/runs.py:resume_run`、`routers/test_inputs.py:create_test_input/delete_test_input`、`routers/copilot.py:dispatch_copilot` 仍 501：debug resume、测试输入 CRUD、旧 copilot dispatch 不可用。
- **critical** — `apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.ts:defaultPhaseMarkdown` 与 `components/studio/panels/phase-frontmatter.ts:parsePhaseForm` 使用旧 phase 格式，违 engine skill-spec。
- **major** — `apps/studio/frontend/src/components/studio/settings/LlmRolesTab.tsx:roleTestStates`、`CopilotTab.tsx:routeStatusOverrides`、`apps/studio/backend/app/routers/llm.py:_role_test_jobs` 是易失测试状态，和 Settings 后端投影 SSOT 冲突。
- **major** — `apps/studio/frontend/src/components/studio/settings/copilot/mock-copilot-data.ts` 仍被 Settings Copilot 真实 UI 路径引用；copilot 配置还没完全去 mock。
- **major** — `apps/studio/frontend/src/components/edges/ContextEdge.tsx:getMockEdgeContext` 仍用假黑板；trace dot 设计未接真实事件。
- **major** — `apps/studio/backend/app/routers/llm.py:router` 集中 HTTP glue、probe、materialize、draft、projection，接口与依赖边界不清；`llm_import_drafts.py:sync_remote_evidence_library` 直接 `os.getenv("STUDIO_CATALOG_URL")`。
- **minor** — `apps/studio/backend/tests/test_security.py:test_symlink...` 仅有平台能力型 `pytest.skip`，不是脆弱跳过；未发现 `.skip`/`.only` 式测试活性违规。
