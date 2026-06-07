# Codex 任务:审计 Claude 本轮对 Studio MVP1 的修改(对抗式独立复核)

Claude 本轮(2026-06-05)对 `docs/studio/mvp1/` 做了四类修改。**请独立、对抗式地复核——假设 Claude 有错,主动找出来**(Claude 上一轮审计也漏报过,这轮换你查它)。**不要默认 Claude 对。**

## 权威源(裁决以这些为准,不是以 Claude 的改动为准)
- 设计单元 owner/spans/去重:`docs/studio/mvp1/DESIGN_UNITS_INDEX.md`(轴③ R8 枢纽,**单元归属的唯一权威**)。
- 审计判据:`docs/development/design-doc-standards/02-audit-standard.md`(R0–R8 / Q1–Q5)。
- 决策原话源(已 superseded,仅用于核 inline 是否忠实):`docs/studio/_reorg/alignment-notes.md`。
- Claude 自己的映射表(**审它对不对,别信它**):`docs/design/studio-mvp1-decision-table-fix.md`。

## 复核项

### A. §5 决策表「单元归位」是否正确(最重点,Claude 改了 31 档约 87 行)
每个 `mvp1-alignment.md` 的 `## 5. 决策 + 动机` 表,Claude 把每行的"动机"列从套话改成了「单元 `X`；**为什么**：…」。
**逐行独立判断**:
1. 该决策的切面,**按 `DESIGN_UNITS_INDEX` 的 spans(模块×切面→owner)**,正确的单元是哪个?和 Claude 写的一致吗?**不一致 = Claude 归错,标出来**。
2. 标了「(消费)/(引)/(负向边界)」的,是否确实是"本模块不拥有、只消费/引用/负向"的切面?有没有把**本该 own 的**切面错标成消费?
3. 多单元模块:frontmatter `units:` 里的每个单元,是否都在 §5 或正文有落点?有没有 unit **owned 但 §5 完全没体现**的漏项?

### B. §5「真实动机」是否站得住
- 是否还有套话残留(「对齐 X 设计单元，保证…可回扣」)?
- Claude 写的"为什么/约束"是否**真实、与该决策一致**?有没有为了填空**编造**动机、或写得和决策实质矛盾的?抽 ~10 档逐条对正文核。

### C. 6 个 P0 硬 FAIL 是否真修好、无残留
Claude 声称修了 6 个 R0/R3 矛盾(见 `docs/design/studio-mvp1-semantic-audit-report.md` §1.1 S-01~S-06)。逐个**重新验证矛盾是否真消除**:
- golden-eval/properties:golden 是否还在任何 positive link/接口出现(应只剩负向边界)?
- debug-resume F3 + `01_workflows/05_debugging.md` F4:HitL 是否两处都已统一成"节点 debug bar 上方悬浮框"、无"顶栏"残留?
- local-history frontmatter `aligns_with` 是否已对 06_eval/04_run、不再挂 05_debugging?
- predict §8:是否已去掉"实施归 kiro"的 SSOT 泄漏?
- shell-layout Header 测试:是否已不含 breadcrumb?
有未修净的标出来。

### D. _reorg→workflow 固化的「忠实度」
Claude 把 alignment-notes 的决策原话 inline 进了主场文档(native-fs §4 的 D10/D12、`01_init` §3 的 D3/D6/D9/D10、`02_authoring` §3 的 D7/G2/G3)。
- 抽这些 inline 原话,**逐字对 `_reorg/alignment-notes.md` 原文**:有没有**篡改/精简/曲解**(Gemini 警告的"有损压缩")?
- `docs/studio/mvp1/` 全树是否**真的零引用** `_reorg` / `alignment-notes`(路径 + 裸文本)?

### E. migration 对照结论是否成立
Claude 称 `_migrated-coverage-drift.md` 的 58 个 drift 符号无真漏迁(6 个挪位、2 个改名/次要)。抽查 5-8 个 drift 项,确认其**概念**确在对应 baseline 的「测试锚点」或正文被追踪。

### F. 有没有引入新错误
- frontmatter schema 是否仍完整(`units:` list、无 `lock:`、`binds_*` 在)?
- 相对链接是否仍 0 断?
- 有没有改坏 predict gold(应零改动)?

## 铁律
- **不改任何文件**,只产报告 + 证据(`文件:行/符号`)。
- 宁可误报、不可漏报;每条结论挂证据,不凭印象。
- 单元归属一律以 `DESIGN_UNITS_INDEX` 为准裁决,Claude 写的只是被审对象。

## 交付
`docs/design/studio-mvp1-claude-work-audit-report.md`:① §5 单元归错清单(模块/行/Claude写的/正确的/依据)② 动机存疑清单 ③ P0 未修净 ④ inline 失真 ⑤ migration 漏项 ⑥ 新错误。分批(A→F)报。
