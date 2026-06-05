# Codex 任务：Studio MVP1 —— 内容审计（R0–R3 专审，禁样板）

你是设计文档审计员。这是对 `docs/studio/mvp1/` 的**第二轮、只审内容**。第一轮（`docs/design/studio-mvp1-audit-report.md`）把结构合规（R4–R8 的 frontmatter/units/INDEX）审了，但**把内容轨 R0–R3 全标“局部可读”糊弄过去了**。这一轮**只审内容、必须出具体 finding**。

## 只审这些（其余别碰）
- **R0 内容正确**：文档内自相矛盾 / 逻辑漏洞 / not-make-sense；跨文档对同一事实冲突。
- **R1 唯一真理**：有没有把弃用 / 过去文档当 SSOT 引用。
- **R2 baseline 对代码**：baseline 写的“现状”与**真实代码**是否一致（读 `文件:符号名` 核）。
- **R3 alignment 无 stale**：alignment 的目标 / 决策是否被更新决策推翻。
- **Q2 决策留底**：关键决策有没有 PM 原话 + 动机。
- **Q3 跨模块一致**：同一设计单元在它 spans 的各模块说法是否一致（对照 `docs/studio/mvp1/DESIGN_UNITS_INDEX.md`）。
- **跳过 R4–R8 / Q1 / Q4 / Q5**（结构合规第一轮已审，这轮不重复，不要再报 frontmatter/units/INDEX 缺失）。

## 硬要求（违反 = 任务失败）
1. **禁样板**：不许出现“R0/R2/R3 局部可读”这种无 finding 的糊弄句。每档要么给**具体** finding（指出哪句话错 / stale / 与代码不符 + `文件:符号名` + 正确值应是什么），要么明写“**无内容 finding**”。
2. **必须真比对**：R2 真去读对应代码符号比对；R3 对照**最新权威**比对（下面权威序）；不许空泛“需核实”。
3. **每条 finding 挂证据**：`文件:符号名` 或 `文档:行`，标严重度（critical/major/minor）。

## 最新权威（判 R1/R3 stale 用）
- 最新 = `01_workflows/` + `_reorg/workflow-action-catalog.md` + `_reorg/alignment-notes.md` + `00_settings-ux-spec.md`；`.kiro/specs` = 过去参考（当 SSOT = R1 违规）；`_mvp1-snapshot-*` = stale。
- 引擎拥有的契约（子图 path / golden 落点 / skill 语法 / 错误码 / resolver / checkpoint）以 `docs/engine/mvp1/` 为准；studio 复制一份 = drift。

## 已知内容 drift（这是地板，不是天花板 —— 要找出更多同类）
- **5 态 vs 6 态**：`01_workflows/00_settings.md:4` 仍写 5 态（含已删 `needs_setup`），`00_settings-ux-spec.md:255` 锁 6 态 → 凡描述 provider 态的文档都查 stale。
- **R1/R6 权威泄漏**：`README:4` / `02_authoring.md:3` 引 `.kiro/specs`、旧 engine FROZEN；`03/04/05_*.md` 引 `_reorg/*prompt*`。
- **子图代码 drift**：代码 `canvas-authoring.ts:defaultPhaseMarkdown` 写 `mode: subgraph` 旧格式，与 alignment 的 D7 path 模型矛盾 → 凡写子图的 alignment 查是否与代码现状（baseline）矛盾。

## 输出 → `docs/design/studio-mvp1-content-audit-report.md`
逐档（只列有 finding 的 + 明确“无内容 finding”的；不要复制第一轮的结构样板）：
```
### <文档相对路径>
- R0: <具体矛盾 + 证据> | 无
- R1: <把谁当 SSOT 错 + 证据> | 无
- R2: <baseline 哪句与代码不符 + 文件:符号名 + 实际> | 无
- R3: <哪个目标/决策 stale + 被谁推翻 + 证据> | 无
- Q2/Q3: <缺原话 / 跨模块不一致 + 证据> | 无
```
全局：① 内容矛盾清单（按严重度）② stale 决策清单（被哪条新决策推翻）③ 跨模块 drift（同单元说法不一，对照 INDEX）④ 权威泄漏（R1/R6）清单。

宁误报不漏报；每条挂证据；只产 Markdown，不返回评分 JSON。
