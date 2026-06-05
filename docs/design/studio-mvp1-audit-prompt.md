# Codex 审计任务:Studio MVP1 设计文档审计

你是**设计文档审计员**。严格按 `docs/development/design-doc-standards/` 这套规范,审计 **studio mvp1** 全部 31 个模块的设计文档。**先读规范、再开审**;每条结论必须挂 `文件:符号名` 或引用证据,不凭印象、不脑补(读不到的文件就说读不到,不要根据文件名推断内容)。

---

## 第 1 步:读规范(全读,这是你的判据)
1. `docs/development/design-doc-standards/00-three-axes.md` — 三轴心智(轴① workflow 决策脊柱 / 轴② 能力模块 baseline+alignment / 轴③ 设计单元 INDEX)。
2. `docs/development/design-doc-standards/01-writing-standard.md` — 文档怎么写(四态状态机、baseline/alignment 模板、引用拓扑、单元锁)。
3. `docs/development/design-doc-standards/02-audit-standard.md` — **审计怎么审:硬规范 R0–R8(违反即 FAIL)、质量 Q1–Q5(弱项标 ⚠️)、双轨(文档轨+代码轨)、输出格式(第四节)、判定铁律(第五节)。主依据。**
4. `docs/development/design-doc-standards/example/baseline-example.md` + `alignment-example.md` — 颗粒度范例(判 Q1 深度对照它)。

## 第 2 步:读项目实例化材料(规范是通用自包含的,scope/现状由项目材料给)
- **项目 README(判 Q5 scope/non-goals)**:`docs/studio/mvp1/README.md` + 三分区 README:`02_capabilities/README.md`、`03_regions/README.md`、`04_platform/README.md`。
- **轴③ INDEX**:`docs/studio/mvp1/01_workflows/INDEX.md`。⚠️ 现有这份是 **workflow 走查索引**,**不是** R8 要求的"设计单元 INDEX(spans / 模块×切面 / binds_code / 锁状态)"——这点本身按 R8 报缺。
- **轴① workflow 留底(决策脊柱,做覆盖检验)**:`docs/studio/mvp1/01_workflows/*.md`(含 `00_settings-ux-spec.md` = settings SSOT)。

---

## 审计对象:31 模块(各一对 `baseline.md` + `mvp1-alignment.md`)
- **02_capabilities(14)**:compile-lint, conflict-overwrite, copilot-assist, debug-resume, file-editing, golden-eval, graph-authoring, phase-editing, predict, publish, run-execution, skill-workspace, studio-settings, trace-observability
- **03_regions(12)**:assets, canvas, center-action-bar, copilot, editor, input, local-history, properties, settings, shell-layout, timeline, welcome
- **04_platform(5+1)**:engine, gateway, llm-copilot-http-api, native-fs, state-engine,+ 单文件 `04_platform/i18n.md`

---

## 关键项目背景(判 R1/R3/R6/Q3 必须知道,否则会误判"stale / 谁是权威")

### Studio mvp1 权威序(2026-06-03 PM 锁定 —— 你判"是否 stale、是否拿弃用文档当 SSOT"用这个)
- **最新权威** = `01_workflows/`(workflow 走查)+ `_reorg/workflow-action-catalog.md`(atom actions)+ `_reorg/alignment-notes.md`(PM 逐项确认的决策日志)+ `00_settings-ux-spec.md`(settings SSOT)。**全是 PM 一项项确认的最新文档。**
- `.kiro/specs/studio-feature-*` = **过去的设计、只作参考**,曾在 06-01 被当权威、但被 06-02/03 走查 override/refine。文档若把 `.kiro/` 当 SSOT 引用 = **R1/R6 违规**。
- `docs/engine/_mvp1-snapshot-*` 快照 = **stale**,不得当真理。
- **引擎拥有的契约 / 物理布局,studio 必须引用 engine mvp1 SSOT(`docs/engine/mvp1/`)、不得复制。** studio 自己抄一份 = drift(典型 engine 拥有项:子图落点、golden 路径、skill 语法、错误码、resolver 协议)。**`04_platform/engine`、`04_platform/gateway` 这两个边界模块尤其要查"是引用 engine mvp1、还是复制了一份"。**
- ⚠️ `_reorg/` 性质要分清:`workflow-action-catalog.md` / `alignment-notes.md` / `settings-action-catalog.md` / `copilot-action-catalog.md` 是 **PM 确认的决策留底**(轴① 留底性质),引用它们判 R6 时按"决策留底"对待,**不**一刀切当 temp 违规;但 `_reorg/` 里的 `*-prompt-*.md`(发给 AI 的 prompt)、`*-handoff-*.md`、snapshot 性质文件属临时,引用它们 = **R6 违规**。

### 文档现状(你会撞到,提前知道,别困惑也别漏报)
- 现有 baseline/alignment **早于这套新规范的 frontmatter 约定**:多数**没有** `module/doc/status/binds_alignment/binds_code/units` frontmatter;baseline 用"`文件:行号`"挂代码证据(规范要"`文件:符号名`为主、行号辅,抗漂移")。→ 这些按 **R4(frontmatter/职责)、R5(binds_* 双向拓扑)、R7(status 状态机)、R8(units/INDEX)、Q1(颗粒度)系统性报"未按规范"**,但**逐档给证据**,别只写一句笼统结论。
- `units:` frontmatter + 设计单元 INDEX(R8)两边都没落 → R8 系统性报缺;并在全局汇总里给出"**哪些横切单元该登记 INDEX**"的清单(明显横跨多模块的:子图、golden、predict、trace、i18n、copilot、debug-resume 等)。

---

## 双轨审计(规范第三节,缺一不可)
- **文档轨**:每份 baseline / alignment 逐条过 R0–R8 + Q1–Q5。
- **代码轨**:顺 baseline 挂的代码符号跑 5 维工程体检——**极简度**(无为兼容堆的临时适配器/冗余包装)、**类型安全度**(无 `any`/`as any`/`@ts-ignore`/`cast(Any)`/`type: ignore`)、**死代码干净度**(无物理残留废弃方法/不可达逻辑)、**测试活性度**(非假 Mock、有真实端到端、无脆弱 skip)、**接口与依赖清晰度**(不越权引私有 `_` 模块、不绕统一 `Settings` 随处 `os.getenv`、无循环导入)。每条缺陷标**严重度(critical/major/minor)+ `文件:符号名`**。
  - Studio 代码 = `apps/studio/frontend/`(React/TypeScript)+ `apps/studio/backend/`(FastAPI/Python)。
  - baseline 没挂 `binds_code` 的:先按 **R5 报"代码↔baseline 双向绑定缺失"**;能从正文证据(文件:行号)定位到代码的,就顺藤把那段代码跑代码轨。

---

## 输出格式(严格按规范第四节)
逐份文档:
```
### <文档相对路径>
- R0–R8: PASS | FAIL — 证据(文件:符号名 / 引用)
- Q1–Q5: PASS | ⚠️ | N/A — 证据
- 🚨 本档真空 / 债:缺什么、待迁什么
- 修复建议:具体
```
**全局汇总**(六项,一项不能少):① FAIL 总清单(按优先级)② 🚨 去-旧版债总账(哪些文档还把真理压在 .kiro/snapshot/弃用源)③ 双向引用缺口(代码 / baseline / alignment 哪层没绑)④ 跨模块 drift(同一设计单元在它 spans 的各模块说法不一致)⑤ 锁状态清单(各文档 `status` + 可否进 FROZEN)⑥ 设计单元索引覆盖(哪些横切单元未登记 INDEX / 重复 owner / 真空)。

## 判定铁律(规范第五节)
- **宁可误报、不可漏报**(漏报 = 假装合格)。
- 每条结论必有 `文件:符号名` / 引用证据。
- 拿不准"现状是否被新决策推翻"→ 先核实最新决策(按上面权威序;**`FROZEN` 也可能已废**)。
- **范围锁定**:只审 `docs/studio/mvp1/`;engine 文档只在核对"studio 是否正确引用 engine SSOT"时读,**不审 engine 本身**。

## 交付
报告直接产出 **Markdown**(不要返回评分 JSON,本任务用上面第四节的格式),写到 `docs/design/studio-mvp1-audit-report.md`。
