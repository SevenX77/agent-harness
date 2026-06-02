# 交接 Prompt v2 — Studio 文档重组:过未确认节点(03-06)+ 00_settings,再写 capability/region 文档

> 用法: 新 session 清 context 后, `@docs/studio/_reorg/NEXT-SESSION-PROMPT-v2.md` 带进去。
> 取代 v1(`NEXT-SESSION-PROMPT.md`, 已被本轮 workflow 编目取代)。

## 你在做什么

继续 Skill Studio(`apps/studio`)**文档体系重组**。当前阶段:已用 workflow 把 6 个 user workflow 节点全量编目成 **119 个动作的 master 目录**(每动作 capability+region+status+动机+file:line+FROZEN 改动)。**这是文档/设计工作, 不写应用代码。**

本 session 的事:
1. **逐节点过 PM 未确认的部分**(03-06), 每节点把 catalog 的动作表呈现给 PM, 可疑项先核实代码再呈现, 记 PM **原话 + 动机**, 标确认。
2. **起草 `00_settings` 节点**(PM 已拍要立; 承载 API keys/LLM roles/copilot 配置/产物路径旅程)。
3. PM 全部确认后, 按 INDEX 模板正式撰写 `mvp1/02_capabilities/*` 与 `mvp1/03_regions/*`。

## 先读这些(按序, 别跳)

1. `docs/studio/INDEX.md` — **治理总纲**(三维模型 / 所有权不变量 / 路由树 / status 词表 / 注册表 13 能力·12 区域·平台三分 / 文档模板)。全部已锁。
2. `docs/studio/_reorg/alignment-notes.md` — **决策日志**(真相源, 含 PM 原话): D1–D12、G1–G9、批次1/2 + Half A、FROZEN 改动清单、🔒锁定、续做(2026-06-02)。
3. `docs/studio/_reorg/workflow-action-catalog.md` — **119 动作 master 目录**(本阶段核心)。顶部「怎么读 / 横切约束 / 审校修正 / FROZEN 改动集 / PM 决策 / 节点确认状态 / 可疑项核实」。
4. `docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md`(FROZEN)+ `02/03/04/05/11/12` — skill 格式唯一权威。
5. 设计权威 spec(5 份, PM 2026-06-01 review 定稿): `.kiro/specs/studio-feature-{canvas-topology,asset-explorer,skill-lifecycle,trace-inspector,copilot-chat}/`。注意各 spec 内**部分子文件已自我 stale**(asset-explorer/design、copilot-chat/requirement、skill-lifecycle/review)——权威文件见 alignment-notes「设计权威源更新」表。

## 铁律(全程贯彻)

- **核实优先于提问/下结论**: 任何现状判断先读代码给 `file:line`; 提问前先穷尽自查; 不信子 agent 转述。
- **文档默认可能过时, 采信前交叉验证**: 权威序 = 格式/字段 → FROZEN > 代码 > workflow-doc/derivation; 实现状态 → 当前代码 > 文档。**最新优先**(studio-feature-* spec > 旧 baseline)。
- **每条决策写清动机**(PM 硬要求): 决策 + 为什么。
- **PM 原话留底**: 每轮 PM 决策原文记进 alignment-notes(`>` 引用)。

## 已锁决策(别重开;原话见 alignment-notes)

- **D1–D11** IDE/workspace 模型(skill=文件夹; Home=打开文件夹+Recent MRU; 无注册表; 子图按 path D7; 不卡导入 D2; copilot 建技能 D5; copilot 持久化 D8; 多窗口 D9; 后端三分 D10; copilot 失败退路)。
- **D12 写入全量 Rust**: 本地写/落盘经 Rust(native-fs 唯一写者); 仅 graph-agent engine + llm-gateway 走 Python sidecar。
- **G1–G9 + canvas 设计细化**: 布局态非 FROZEN sidecar 落盘(G1); 子图 io 不绑 1:1, 从黑板过滤 + 任意 i/o 面板可导入文件注入黑板, 时机=a(G2); artifact 落盘写在 io.outputs schema 顶层路径, md 取最终 business_data_md 不回转(G3); 子图无限嵌套·扁平独立容器·LOD+culling(G4); dagre 只排新建+手动位实时存+右键 fit/100%/lock(G5); 共享子图 git 轻量安全网(G7); 运行时 focus 跟随节点(G9); 子图 inline 容器展开 + 就地下钻(T5/T6, copilot 不切换不缓存)。
- **FROZEN-1..4**(本 session 锁, 待统一改 spec 文件): 删 04-subgraph io 1:1 / io.outputs 加 artifact 路径 / 节点级文件导入→黑板 / REQ-2 字段勾选。
- **00_settings 节点立**; **copilot 失败退路补**。

## 进度

- ✅ **已 PM 确认**: `01_init`(批次1)、`02_authoring`(Half A + G1-G9 + canvas 细化)。
- ⏳ **未过 PM(本 session 接着过)**: `03_prediction`、`04_execution`、`05_debugging`、`06_eval`。
- 🆕 **待起草**: `00_settings` 节点。
- 📌 **可疑项已核实**: events.py 34 类 / business_data_md 保留(G3 可行)/ useGoldenDiff GET-POST mismatch(潜伏 bug)。

## 任务(从这里续)

**A. 逐节点过 03→04→05→06**(每节点一轮):
- 从 catalog 取该节点动作表, 先把表里标可疑/跨节点打架/critic 提示的项**核实代码**(给 file:line), 再呈现给 PM。
- 重点带 PM 确认: scope(owns/not-owns)、关键动作的 status 与目标、动机、FROZEN/D12 影响。
- 用 catalog「审校修正」校准(stage 机归 compile-lint; region≠platform; batch 失败 backend-only; i/o panel 两能力共用)。
- 记 PM 原话 + 动机进 alignment-notes; 在 catalog「节点确认状态」把该节点移到 ✅。

**B. 起草 `00_settings` 节点**: settings 旅程(API keys / LLM roles / copilot 配置 / 产物路径)+ 它被 publish/predict 硬依赖的关系。参考 `.kiro/specs/studio-{llm-gateway-redesign,llm-roles-*,api-keys-*}` + settings region 现码(`apps/studio/frontend/src/components/studio/settings/`)。

**C. 全部确认后**: 按 INDEX §7 模板写 `mvp1/02_capabilities/*`(13)与 `mvp1/03_regions/*`(12)。一个事实只在一个 tier 写实现, 其余链接(§2 不变量)。

**D.(独立 track, 可后置)** FROZEN 新版本: 据 FROZEN-1..4 实际编辑 `docs/engine/skill-spec/00/02/03/04/05/11/12`, 出新版本契约。须 PM 确认改动集后动手。

## 目录结构(本轮重组后)

```
docs/studio/
  INDEX.md      # 治理总纲(根)
  _reorg/       # 工作区: workflow-action-catalog.md(核心) / alignment-notes.md(决策) / workflow-derivation.md(旧骨架) / 本 prompt / V0.3.0 暂存需求
  mvp0/         # 旧设计 baseline(02_features/ 03_platform/), 迁移后按需删; 不要据此实现
  mvp1/         # ★新设计·重设计目标: 01_workflows/ 02_capabilities/ 03_regions/ 04_platform/
```

## 别做

- 别改应用代码(文档/设计工作)。
- 别重开已锁决策(D1-D12 / G1-G9 / FROZEN-1..4 / 00_settings / copilot 失败退路)。
- 别信 derivation/mvp0(旧 baseline)的字段; 别把 spec 子文件 stale 版当权威。
- 别没核实就向 PM 抛问题/结论。
