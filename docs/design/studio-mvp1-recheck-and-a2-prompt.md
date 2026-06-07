# Codex 任务:复核 Claude 第二轮修复 + A2 分歧的客观裁定

承接你上轮 `studio-mvp1-claude-work-audit-report.md`。Claude 已据此修了一轮(见 git 最新提交 / 当前工作树)。本任务两部分。**对抗式、不迎合任何一方。**

## Part 1:复核第二轮修复是否到位、有无新错
逐项独立确认:

- **C/S-03**:HitL "顶部问题框"是否全清?`01_workflows/05_debugging.md:17` 与 `:34` 应都是"节点 debug bar 上方悬浮框 / 非固定顶栏";`02_capabilities/debug-resume/mvp1-alignment.md:40,73` 一致。**注意**:`01_workflows/00_settings-ux-spec.md:508` 的"顶栏"是**设置页保存徽章**、与 HitL 无关,不算残留。
- **D/inline 忠实度**:对 `_reorg/alignment-notes.md` 原文逐字核——
  - `02_authoring.md:38` D7 是否补回"唯一要注意的是 copilot 的工作目录范围要把 subgraph 的子图 path 加进去"这个约束?(原文 `alignment-notes.md:58`)
  - `02_authoring.md:39` G2 / `:40` G3 / `04_platform/native-fs/mvp1-alignment.md:72` D10 是否已还原 PM 原文、去掉过度压缩的"…"?(原文 `:250-256`、`:71-77`)
  - D12(native-fs:73)原话部分是否逐字、后半"含义"是否在引号外?
- **A1/消费标记**:`file-editing`/`editor`/`skill-workspace`/`studio-settings`/`settings`(region)/`timeline`/`properties` 的相关 §5 行是否已标 `(消费)/(落点)+owner`?`state-engine-1` 是否拆清 stage→compile-stage-gate / provider→六态 / sidecar→shell-runtime-gate 分属?
- **新错误**:相对链接是否仍 0 断?63 档 frontmatter schema 是否完整(`units:`、`binds_*`、无 `lock:`)?`predict` gold 是否仍零改动?

有未修净 / 修出新问题的,逐条标 `文件:行` 证据。

## Part 2:A2 分歧的客观裁定(**不要迎合任一方**)
你上轮判:frontmatter `units:` 混入"消费/引用单元" = R8 归属污染。Claude **不认同**,论据如下:

1. `docs/development/design-doc-standards/01-writing-standard.md` §4 原文:`units: [<unit-a>]   # 本文**承载**的设计单元切面(在 INDEX 登记)`。
2. 同文件 §1.6:"能力模块文件 frontmatter 标 `units:`(它**承载**哪些单元切面),锁态以 INDEX 为准。"
3. 消费方"承载"的是该单元的**消费切面**,故 frontmatter 列它符合"承载切面"的字面定义。
4. owner 唯一性(R8 去重铁律)的权威在 **`DESIGN_UNITS_INDEX` 的 spans 列**(每切面一个 owner);frontmatter 列消费单元**不改变** INDEX 的 owner 裁定。
5. §5/正文已用 `(消费)/(引)/(落点)` 标明 facet 类型,owner 不被混淆。
6. 反过来:若只许 frontmatter 列 owned 单元,"某文件承载某单元的消费切面"这一事实将**无处声明**。

请**客观**裁:
- 按标准**现有原文**,frontmatter 列消费单元到底算不算违规?Claude 论据 1–6 逐条成立 / 不成立?
- 若你仍主张收紧(只许 owned):依据是标准哪一句?还是属于"标准没写清、需补一条约定"(而非现状违规)?
- 给结论 + 引标准/INDEX 原文为据。**不要为维持上轮判断而硬撑,也不要因为是 Claude 反驳就让步**;就事论事。

## 交付
新建 `docs/design/studio-mvp1-recheck-report.md`:Part 1 复核结果(逐项 PASS/FAIL + 证据)+ Part 2 A2 裁定(认同 Claude / 维持原判 / 第三种,附依据)。**不改任何被审文件。**
