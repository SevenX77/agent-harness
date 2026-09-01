完成。

**PR**:https://github.com/SevenX77/agent-harness/pull/1074(已开,auto-merge/squash 已武装,CI 绿即自动合入 `main`)

**文档路径**:`docs/design/gskill-restructure-decision-2026-08-31.md`(单文件,新建)
**同 PR 台账**:`docs/development/DELIVERY_LEDGER.md` 顶部活动区新增任务块「gskill 重整(北极星 / 搬仓 / 模块化 / 执行模型)(2026-08-31)」,四行:状态=决议已落盘、范围、边界(§6 待用户裁决不得代裁)、下一步=全局模块盘点。

**门禁结果**:`uv run pytest apps/studio/backend/tests/docs/` → **181 passed**(含 design-doc 治理四道门、台账表格形状门、文档代码引用门)。文件为 UTF-8 + LF,符合 `.gitattributes` 基线。

**落盘要点**
- frontmatter 按 `01-writing-standard.md` 闭集取 `status: drafted`(带注解说明 §6 留裁)、`role: workflow-record`(§0 载体划分里轴①=决策留底,本文正是用户裁决的落盘正本)。
- 结构:§0 术语表与权威范围 → §1 北极星五条(含"明确排除项降级为 §8 第⑪条")→ §2 四层权威链 + 三道检验 + claim-non-seed → §3 行为原则八条 → §4 引擎归属与搬仓(背景事实 + a–e)→ §5 双场景执行模型(a–f)→ §6 格式载体**待用户裁决** → §7 盘点方法 → §8 十一条验收清单(表格,每条注明强制方式)→ §9 六步流水线 + 五把锁 → §10 资源与并发 → §11 修订记录(注明"内容为 2026-08-31 会话中用户逐项批准的决定,落盘即存证")。
- 写作纪律:全中文;gskill / AST / 膜 / Port-Adapter / executor / durable handoff / monorepo 等术语首现即给平白话解释;不引会话、不写"如前所述";§6 通篇标注待裁,未代下结论;未添加 brief 之外的新决定。

**一处证据核验(影响 §6 措辞的可信度)**:brief 把三处冗余的机器强制归到 `02-skill-syntax/mvp1-alignment.md` §3.2。实测该文 §3.2(第 66–68 行)只写了「Studio 做 rename 时必须同步目录名、`GRAPH.md phases` 注册表和 body `&lt;phase&gt;` 引用」,**三个原因码在另一份文档**:`docs/engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md` 的 `:250`(`[F-v3-graph-phase-name-mismatch]`,原文明写"body `&lt;phase&gt;` name / frontmatter `phases` 注册名 / 物理目录名三者不一致")、`:247`、`:257`。文档里按实际坐标分别引用,未沿用 brief 的单一出处写法——事实不变,出处更准。
