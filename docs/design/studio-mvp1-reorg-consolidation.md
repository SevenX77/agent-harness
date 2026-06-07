# Studio MVP1 — _reorg → workflow 决策固化 + finality 裁决日志

> **目的**:把 `docs/studio/_reorg/alignment-notes.md`(原始设计工作笔记,712 行)里的 PM 决策固化进 workflow 节点文档,让 workflow 成为决策唯一权威(SSOT);workflow 与 alignment 的引用全部指向 workflow/主场文档,**零引用 `_reorg`**;最后给 alignment-notes 盖 `superseded → deprecated`。
> **触发**:R6(FROZEN 文档不得引用临时/将删目录);`_reorg/` 含 `…DO-NOT-DELETE-DURING-CLEANUP.md` = 正被清理。
> **方法经 Gemini + codex 双审**(2026-06-05)。

## finality 判定法(Gemini + codex 共识)
**不是单一线性优先序,是按决策逐条裁决,两轴:领域主场 + 签批级别。**

裁决强弱(冲突时左压右):
> 明确 supersede 话术("作废/以X为准/不作SSOT")> **PM 原话 + 🔒锁定**(在哪都算,含老 alignment-notes)> 领域 canonical(`ux-spec` 管状态机/分层、engine SSOT 管引擎契约、`DESIGN_UNITS_INDEX` 只管 owner/映射)> workflow 已回写的完整决策 > 原始 alignment 证据 > 派生/审计/索引摘要 > kiro

铁律:
- **workflow 不靠"比 alignment 新"自动赢**。迁移 = 逐条 diff/merge:用 alignment-notes 每条🔒原话当校验清单核 workflow;workflow 写丢/写歪 → 用🔒原话**修 workflow**。
- 原话就近 inline 在主场文档(workflow 留底允许冗余);跨切引主场,**不引 `_reorg`**。
- "待 PM / 原话待补"三类隔离:① 后续已答→收答案+标覆盖;② 仅 AI 建议→进 gap/待PM 区,不写成决定;③ 决策已锁但原话缺→收决策+标来源文档,**不伪造原话**。

## 决策 → 主场 映射
| 决策 | 主场文档 | 锁态 |
|---|---|---|
| D1 无注册表 · D2 不卡导入 · D11 IDE/workspace 模型 · R1 删 Delete · R2 欢迎屏 · D-1-1 · D-1-4 | `01_init` | 🔒 |
| D3 删外部 IDE 联动 | `01_init`(+ native-fs tauri 死代码) | ✓ |
| D5 copilot 建技能(graph skill) | `copilot-assist` | ✓ |
| D6 skeleton + lazy load(NFR) | INDEX §11(跨切) | ✓ |
| D7 子图按 path | `02_authoring`/`canvas` + engine resolver | ✓ |
| D8 copilot 会话持久化 | `copilot-assist` | 🔒 MUST |
| D9 多窗口 | `04_platform` | ✓ |
| D10 后端三分(gateway/engine sidecar + native-fs Rust) | `04_platform`(native-fs/gateway/engine) | 🔒 |
| D12 本地操作全量 Rust(唯一写者) | `04_platform`/native-fs | 🔒 |
| T5/T6 子图 inline/下钻 · G1–G9 · canvas FROZEN-1..4 | `02_authoring`/`canvas` | 🔒(G 锁 alignment-notes:274) |
| S1/S2 settings 结构/能力 | `00_settings`/`studio-settings` | ✓ |
| M1/L1 方法与教训 | 不进 workflow(随 _reorg 退役) | — |

## finality 热点(重点核)
alignment-notes:300 记:截至 **2026-06-02 只有 `01_init` / `02_authoring` 过 PM**;`03_prediction(=03_compile?)` / `04_execution(=04_run-and-verify)` / `05_debugging` / `06_eval` **未过 PM**(标"下个 session 逐节点走查")。这 4 节点的 workflow 文档可能是 AI 派生未签批 → 固化前须查后续(06-03+)有无补签;无签批的"决策"按②类(待 PM 区)处理,不当锁定决策。

## 逐节点裁决日志

### ✅ 01_init(批次1:D1–D12 / R1 R2 / D-1-1 D-1-4)— PM 已确认
**裁决:workflow 忠实,无冲突/无 supersede/无待 PM。** D10/D12 等🔒决策原话与关键细节(eager-spawn、非全屏 gate、仅 engine/gateway 走 sidecar)在 `01_init.md` 已无损承载,仅把部分原话甩给了 `_reorg`(第 5/6/41 行)。
**固化动作(已落)**:
- §3 line 41「D3/D6/D9/D10 详见 alignment-notes」→ **四条原话 inline**(D3 主场在此;D6 引 INDEX §11;D9/D10 标实现归 `04_platform` + 原话留底)。
- 删第 5 行「决策日志(原话依据): _reorg/alignment-notes 批次1」、第 6 行「原工作目录 _reorg/workflow-action-catalog 为迁移源」两处 `_reorg` 指针。
- 结果:`01_init.md` 零引用 `_reorg`,自包含。

### ✅ 02_authoring — §3 已 inline D7/G2/G3 原话(忠实,PM 已确认);删 line 5/6/14/35 的 _reorg 指针(M/T/V 详情改指 §2 + 能力文档)
### ✅ 00_settings / 00_settings-ux-spec — 删 settings-action-catalog 迁移源 + alignment-notes 走查流水指针(决策在 ux-spec PM 口述权威 + §0/§2.0 inline)
### ✅ 03_compile / 04_run-and-verify / 05_debugging / INDEX — 删 engine-prompt/gemini-prompt「仅历史草稿」面包屑(本就标非 SSOT,真 SSOT=engine mvp1 已在旁)
### ✅ alignment repoint — shell-layout / state-engine / native-fs 的 _reorg → 01_init / native-fs §4(D10/D12 原话现 inline 在 native-fs §4 主场)
### ✅ 裸引用清理 — native-fs 锁标记改 PM+日期 · DESIGN_UNITS_INDEX:22 · docs/studio/INDEX:130 改指 native-fs
### ✅ alignment-notes 退役 — 盖 `[SUPERSEDED 2026-06-05]` 横幅;mvp1 全树零引用(路径+裸文本);待 _reorg 内部依赖退役后 `deprecated` 删

## 结果
- **mvp1 全树零引用 `_reorg` / `alignment-notes`**(grep 验证);269 条相对链接 0 断链。
- 决策原话就近 inline 在主场;workflow / alignment 引主场不引 _reorg。
- **遗留(Phase B 语义读再核)**:`03_compile`/`04_run-and-verify`/`05_debugging`/`06_eval` 的 workflow **决策正文 finality** —— alignment-notes:300 记它们截至 06-02 未过 PM。本轮只清了它们的 _reorg 面包屑(非决策源),其决策正文是否 PM 签批,留待全量语义读核。
