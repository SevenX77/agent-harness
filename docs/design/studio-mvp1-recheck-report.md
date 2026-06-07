# Studio MVP1 Recheck Report

日期: 2026-06-05

范围: 按 `docs/design/studio-mvp1-recheck-and-a2-prompt.md` 复核 Claude 第二轮修复, 并客观裁定 A2 `units:` 分歧。只审当前树, 不改被审文件。

## Part 1. 第二轮修复复核

### 1. C/S-03 HitL 顶栏残留

结论: **PASS**。

- workflow F4 已写“节点 debug bar 上方悬浮富文本输入框 / 非固定顶栏”: `docs/studio/mvp1/01_workflows/05_debugging.md:17`。
- workflow 测试关键点已从“顶部问题框”改为“节点 debug bar 上方悬浮框(非固定顶栏)”: `docs/studio/mvp1/01_workflows/05_debugging.md:34`。
- debug-resume F3 与 §4 一致: `docs/studio/mvp1/02_capabilities/debug-resume/mvp1-alignment.md:40`, `:73`。
- `docs/studio/mvp1/01_workflows/00_settings-ux-spec.md:508` 的“顶栏无全局保存态”是 Settings 保存徽章, 与 HitL 无关, 不算残留。

### 2. D/inline 忠实度

结论: **FAIL, 部分修净**。

- D7: **PASS**。已补回 copilot cwd scope 约束, 且引号内与 `_reorg/alignment-notes.md:58` 原文一致: `docs/studio/mvp1/01_workflows/02_authoring.md:38`。
- G2: **基本 PASS**。`02_authoring.md:39` 已还原 `_reorg/alignment-notes.md:252` 的主要原文, 并把“导入时机=a”放在引号外说明为后续锁定。
- G3: **FAIL**。`02_authoring.md:40` 仍在引号内用 `…` 压缩原文, 省掉“一 schema 落两个文件 / 不同 schema 落不同文件 / artifacts 默认组织待想清”等原句。原文见 `_reorg/alignment-notes.md:257-260`。
- D10: **FAIL**。`04_platform/native-fs/mvp1-alignment.md:72` 已去掉 `gateway...` 省略, 但仍缺原文末尾“判断这样是否可行?? 如果是这样的话, 应该不需要bootstrap. 调用后端的地方skeleton就行.”; 原文见 `_reorg/alignment-notes.md:73`。
- D12: **PASS**。`04_platform/native-fs/mvp1-alignment.md:73` 的引号内为 PM 原话短句, 后半“skill 源文件 / .workspace / copilot patch...”在引号外作为含义说明; 对照 `_reorg/alignment-notes.md:203-209` 可接受。

### 3. A1/消费标记

结论: **核心问题基本修净; 严格按“消费/落点 + owner”仍有轻微残留**。

已修净:

- `file-editing` 写路径/autosave 已标 `native-rust-writer`（消费; owner=native-fs）: `docs/studio/mvp1/02_capabilities/file-editing/mvp1-alignment.md:78-79`。
- `editor` 写路径已标消费 + owner: `docs/studio/mvp1/03_regions/editor/mvp1-alignment.md:77`。
- `skill-workspace` 子图 membership 已标消费/引 + owner 非 skill-workspace: `docs/studio/mvp1/02_capabilities/skill-workspace/mvp1-alignment.md:81`。
- `studio-settings` Copilot test 已标消费/配置面 + owner=copilot-assist: `docs/studio/mvp1/02_capabilities/studio-settings/mvp1-alignment.md:91`。
- `settings` region Copilot settings 已标消费/UI + owner=copilot-assist: `docs/studio/mvp1/03_regions/settings/mvp1-alignment.md:88`。
- `timeline` run detail 已标消费/落点 + owner=run-execution/state-engine: `docs/studio/mvp1/03_regions/timeline/mvp1-alignment.md:86`。
- `properties` 字段表单已标落点/消费 + owner=phase-editing: `docs/studio/mvp1/03_regions/properties/mvp1-alignment.md:67`。
- `state-engine-1` 已拆清 stage/provider/sidecar 分属: `docs/studio/mvp1/04_platform/state-engine/mvp1-alignment.md:76`。

严格口径残留:

- 仍有若干消费/引/落点行只写 `(消费)` 或 `(引)`, 没写 `owner=...`, 例如 `debug-resume:mvp1-alignment.md:80`, `file-editing:mvp1-alignment.md:80`, `editor:mvp1-alignment.md:78`, `properties:mvp1-alignment.md:68`, `timeline:mvp1-alignment.md:87`, `native-fs:mvp1-alignment.md:81`。这不是上轮 A1 核心项未修, 但若本轮要求字面执行“`(消费)/(落点)+owner`”, 仍未 100%。
- `studio-settings` / `settings` 的六态、materialize 行在“为什么”里说明 ③b/gateway 内核与 Studio 消费, 但未采用统一的括号格式: `studio-settings/mvp1-alignment.md:89-90`, `settings/mvp1-alignment.md:86-87`。

### 4. 新错误 / 机械检查

结论: **PASS, 未发现新机械错误**。

- 63 档 frontmatter schema 完整: baseline 均有 `units` / `binds_alignment` / `binds_code`; alignment 均有 `units` / `binds_baseline`。
- `rg "^lock:" docs/studio/mvp1` 无命中。
- 相对链接脚本解析: broken=0。
- predict gold: `git diff --name-only HEAD~1..HEAD -- docs/studio/mvp1/02_capabilities/predict...` 与当前工作树 diff 均无输出。

## Part 2. A2 分歧裁定

### 结论

**我修正上轮判断: 按现有标准原文, frontmatter `units:` 列消费/引用/落点切面本身不构成 R8 违规。** 上轮把“消费/引用单元进入 `units:`” blanket 判为“污染”, 依据不足。更准确的标准应是:

1. `units:` 表示本文承载的设计单元切面, 不限 owner 切面。
2. owner 唯一性由 `DESIGN_UNITS_INDEX.md` 的 spans/owner 裁定。
3. 若 `units:` 列了消费/引用/落点切面, 正文/§5 必须明确 `(消费)/(引)/(落点)` 与 owner, 防止读者误会为本模块 owns。
4. 若要收紧为“frontmatter 只列 owned 单元”, 现有标准原文没有这条; 只能说需要新增约定, 不能按现状判违规。

注意: `docs/design/studio-mvp1-retrofit-prompt.md:13` 曾写“own 哪些单元切面就列哪些（消费/依赖不进 units）”。这能解释我上轮判断来源, 但它是 retrofit 任务提示, 不是 `docs/development/design-doc-standards/` 的通用标准; 且与当前标准“承载切面”的字面口径不完全一致。

### 逐条裁定 Claude 6 条论据

| # | 裁定 | 依据 |
|---|---|---|
| 1 | **成立** | `docs/development/design-doc-standards/01-writing-standard.md:63` 写 `units` 是“本文承载的设计单元切面(在 INDEX 登记)”。 |
| 2 | **成立** | `01-writing-standard.md:33-34` 写文件级 FROZEN = 文件承载的所有单元切面都 locked; frontmatter 标它承载哪些单元切面。 |
| 3 | **基本成立** | R8 要求 INDEX spans 精确到“模块 × 切面”: `02-audit-standard.md:41-43`; INDEX 本身也登记消费/引/落点切面, 如 `DESIGN_UNITS_INDEX.md:22`, `:31-32`, `:37`, `:39`, `:42`。所以消费方确实可以承载该单元的消费切面。前提是该消费切面确实在 INDEX spans 或正文中成立。 |
| 4 | **成立** | R8 去重判据是“每个切面只一个 owner”: `02-audit-standard.md:43`; INDEX 也写“每个切面只有一个 owner”: `DESIGN_UNITS_INDEX.md:11`。frontmatter 列 unit 不会改 owner。 |
| 5 | **条件成立, 当前仍未全量做到统一格式** | 第二轮已给核心 A1 行补 `(消费)/(落点)+owner`, 但仍有若干消费/引行无 owner, 见 Part 1 A1 严格口径残留。 |
| 6 | **大体成立, 但“无处声明”说得过满** | 正文/§5 当然也能声明消费切面; 但若 frontmatter 不列, 文件级锁“该文件承载的所有单元切面都 locked”就无法完整表达, 见 `01-writing-standard.md:33-34`。 |

### 最终裁定

我**认同 Claude 对 A2 的主裁定**: frontmatter `units:` 可以列消费/引用/落点切面, 不应因“非 owner”直接判 R8 污染。

我保留两条约束:

- 列入 `units:` 的切面必须能在 `DESIGN_UNITS_INDEX.md` 的 spans 或当前正文中找到明确角色, 不能把“泛相关”当承载。
- 非 owner 切面必须在正文/§5 标清 `(消费)/(引)/(落点)` 与 owner; 否则不是 frontmatter 本身违规, 而是跨小节自洽 / owner 表达不清的 Q3 风险。
