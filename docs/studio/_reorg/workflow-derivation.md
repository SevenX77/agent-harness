# Studio 文档重组 — Workflow 推导记录 (两维导出 + 目标结构)

> **方法**: 自底向上走 6 个 workflow 节点, 穷举每个用户动作 → 它需要的 capability → 渲染所在 UI region, 带 file:line 证据 + 当前文档归属 + 覆盖缺口 + 重叠标注。
> **来源**: workflow run `wf_ee8dbbb3-bd2`, 6 agent 并行, ~120 个动作。原始逐条数据在该 run 的 subagents journal (`.../subagents/workflows/wf_ee8dbbb3-bd2/`)。
> **日期**: 2026-06-01
> **状态**: 推导完成, 目标结构待 PM 确认后落 INDEX 治理总纲 + 迁移 spec。

---

## 1. 两维(从 workflow 动作中浮现, 非顶层拍脑袋)

### 维度 ② Capability(能力, 拥有跨区域数据流)
~13 个产品能力簇 + 3 个平台能力:

| 能力簇 | 涵盖动作(节选) | 主要 workflow 节点 |
|---|---|---|
| `skill-registry` | 建/导入/删除/打开/最近列表/归一化/drift/reveal/目录选择 | 01 |
| `workspace-shell` | home 路由/进入锁定/面板切换/缩放/主题/copilot 开合/面包屑/布局流派/runtime 启动/外部 IDE | 01·02·04 |
| `graph-authoring` | IO 节点/连线/断连/连线校验/新建 phase/子图就地展开/下钻/数据断层红叉 | 02 |
| `phase-editing` | 节点属性表单全字段: kind/role/prompt/exit_contract/tools/sub_skills/references/validator/retry/control/mapping/bridge/save | 02 |
| `file-editing` | Monaco 全文编辑/分屏/schema 推断/保存冲突/file-watch 热更新 | 02 |
| `compile-lint` | 实时 lint/手动 compile/错误面板/stage 门控(解锁 Predict/Run) | 02·03 |
| `predict` | 试飞/测试输入加载/远程 schema 校验/mock-llm/拟真输出/predict→golden 守卫 | 03 |
| `run-execution` | 真实 Run/状态指示/WS 事件流/autocommit/batch run/run 历史 | 03·04 |
| `trace-observability` | trace 读取/metrics/filter/Prompt Inspector/edge 数据包点/edge-context 查看/节点呼吸灯/微观拓扑/Tab 切换 | 04·05 |
| `golden-eval` | golden 固化/并排 Diff/字段得分/Copilot Judge 打分/导出报告/打磨编排 | 03·06 |
| `debug-resume` | HitL 问题框/节点级 Resume/checkpoint 续跑/脏状态失效/context 强制篡改 | 05 |
| `conflict-overwrite` | 顺序覆盖 overlay/Allow 白名单/Cancel 标红 | 02 |
| `copilot-assist` | 对话/上下文注入/@mention/建技能向导/打磨/judge/commit-msg | 全节点 |
| `llm-gateway` *(平台)* | provider/role/credential 解析/模型选择器 | 02·设置 |
| `state-engine` *(平台)* | WS 桥接/event-bus/ipc/前端状态广播 | 02·04 |
| `workspace-fs` *(平台)* | runs 目录/golden 落盘/git/artifact registry | 03·04·06 |

### 维度 ③ UI Region(区域, 拥有组件结构/状态)
代码里真实存在的 12 个区域(Toolbar 面板枚举 + 中心视图 + 壳):

`welcome` · `shell-layout` · `center-action-bar` · `canvas` · `editor` · `assets` · `input` · `properties` · `timeline` · `local-history` · `copilot` · `settings`

> 注: 初版推导把 `editor`(SplitEditor/Monaco) 折进 canvas、`assets`(AssetsPanel 文件树) 未单列; 已按 Toolbar 面板枚举 + 中心视图 修正为 12 个独立区域。

> 维度 ① 是 `01_workflows`(旅程脊柱), 已存在。三维互为多对多, 不能嵌套, 只能互相链接。

---

## 2. Region 视角的 Scope 冲突图(这就是"分不清该落哪")

每个 region 落进了哪些能力 + 当前被哪些文档同时声称。**重叠热点 = 你设计任务时的痛点位置。**

| Region | 落进的能力 | 当前声称的文档 | 问题 |
|---|---|---|---|
| `welcome` | skill-registry, workspace-shell(home) | workspace-fs + system-layout | WelcomePage 被两文档同时当 owner |
| `shell-layout` | workspace-shell, publish(Release 菜单) | system-layout | 相对干净; 但 Release 底层 hook 文档写错(说 useSkillSync, 实为 usePublishSkill) |
| `canvas` | graph-authoring, trace-observability(节点灯/edge-pin/微观拓扑), conflict-overwrite, debug-resume(节点 Resume) | canvas-topology + trace-inspector + skill-lifecycle | **热点**: 三方声称同一画布 |
| `input` | file-editing(schema-infer), predict(测试输入/远程校验), manifest-edit | asset-explorer(笼统) | **孤儿倾向**: 无文档明确认领 Input 面板 |
| `properties` | phase-editing(节点表单), trace-observability(edge-context 只读), golden-eval(Diff 视图), debug-resume(context 篡改) | asset-explorer + trace-inspector + ux-workflow | **最严重热点 + 自相矛盾**(见下) |
| `timeline` | run-execution(run 历史), trace-observability(trace/inspector/filter), golden-eval(Compare/Promote 按钮) | trace-inspector + skill-lifecycle + workspace-fs | **热点 + 命名混淆**(见下) |
| `center-action-bar` | compile-lint(stage 门控), predict(按钮), run-execution(Run 按钮) | skill-lifecycle + system-layout | **热点**: 状态语义 vs 布局归属不分 |
| `local-history` | run-execution(batch), debug(Replay 误入) | workspace-fs + skill-lifecycle | 薄/孤儿 |
| `copilot` | copilot-assist(对话/注入/向导/打磨/judge), llm-gateway(模型选择器) | copilot-chat + llm-gateway | 边界尚清 |
| `settings` | llm-gateway(provider/role/key), 产物输出路径 | llm-gateway + trace-inspector(mvp0) + system-layout | **孤儿**: 无 settings region 文档 |

### 三个标志性冲突
1. **ContextEdge 数据包点 → Properties 面板 trace**: `canvas-topology/baseline:48` 与 `trace-inspector/baseline:19` 各写一遍; 且 `trace-inspector` 自身 baseline(复用 Properties 面板) 与 mvp0(改成独立 Debugger Panel, 不碰 Properties)**自相矛盾**; 数据还是 `getMockEdgeContext()` 假数据。
2. **Timeline 命名混淆**: Toolbar 把 `TimelinePanel` 标成 "Trace Timeline"(`Toolbar.tsx:19`), 但它其实是 **run 历史列表**; 文档描述的"流式阶段时间轴"是另一个**未挂载**的 `TracePanel.tsx`。同一标签指向两个不同物。
3. **顺序覆盖 overlay**: `canvas-topology`(overlay 渲染) 与 `skill-lifecycle`(白名单逻辑/Allow Overwrite 403) 双重声称同一 `SkillNode.tsx` Popover。

---

## 3. 覆盖缺口(coverage_gap, 无任何文档归属)

按严重度:

- **整个 05_debugging 节点几乎全孤儿** — `debug-resume` 簇(HitL 问题框 / 节点级 Resume / checkpoint 续跑 / dirty-state-invalidation / context 强制篡改编辑)**无任一 feature 文档负责**。后端仅有 `ResumeReq` 契约 + `resume_run` raise_not_implemented; 前端全缺。**最大的洞**。
- **phase-editing 进阶字段无主** — validator / retry_target / max_retries / max_nudges / references / sub_skills / context_mapping / context_bridge — 节点表单这一半在 UI 无入口、无文档认领(且部分逻辑藏在**未挂载**的 `PhaseDrawer` 链路)。
- **golden-eval 语义层无主** — Copilot Judge 诊断打分(文档列为"必须展示"的强制项)、Publish 时 Copilot 自动生成 Commit Message — 前后端均无, 无文档认领。
- **predict 打磨编排无主** — "Predict 完成→自动展开左右双屏对比打磨"这一跨区编排、事后把真实 Run 输出导入打磨面板 — 无组件、无文档。
- **node-micro-topology** — LLM 节点内部 Agent-Loop 微观循环展开(deerflow update_working_memory/md2json/finish_task...) — 现有 expandedSubgraphs 是"子图下钻", 与之是两回事, 后者无实现无文档。
- **publish 机制无主 + 文档与实现矛盾** — `06_eval.md` 说底层 `git add && commit && push`, 实际后端是打包上传 **Artifact Registry**(与 git 无关); 无文档覆盖 registry 发布。
- 杂项 welcome 退路 — recent-skills / skill-delete / config-drift / 错误格式化 — 部分无主。

---

## 4. 第三维(意外发现, 对"设计任务"影响最大): 实现状态

baseline 文档把 **target 设计 / placeholder / 孤儿组件 / 活代码** 混在一起且不标注 — 这才是设计任务时真正分不清的根源(你不知道一个动作是"从零做"、"接线孤儿"还是"改活代码")。证据:

- **核心按钮是桩**: `onPredict` / `onRun` = `console.info(...)` 占位(两个最关键动作没接后端)。
- **大量孤儿组件(已构建, 无 importer)**: `TracePanel` · `PromptInspector` · `useRunStream` · `PredictInputDialog` · `DiffView`+`useGoldenDiff`+`DiffScore` · `celebrateSuccess`(confetti) · `PhaseDrawer`(另一套表单) · 整个 `components/diff/*`。
- **死脚手架**: `statusByNodeId` 从不被真实 run 填充 → 节点呼吸灯/红绿/paused/breakpoint 永远不会亮。
- **假数据冒充**: edge-context 用 `getMockEdgeContext()` 生成假 JSON, 不是真实上游 Context。
- **后端就绪/前端缺**: `resume_run`=not_implemented、predict→golden 409 守卫、batch-run、run-autocommit 均后端有、UI 无。
- **文档与实现相反/过时**: publish 走 registry 非 git; Release 用 usePublishSkill 非 useSkillSync; canvas baseline 说"连线不持久化"但其实已持久化; asset-explorer 说"分屏不可拖拽"但其实有 ResizableHandle。

**建议**: 新文档每个动作带一个 `status` 标注(`live` / `placeholder` / `orphan-unmounted` / `backend-only` / `target-design`)。这是 per-action 标签, 不是第四棵树。

---

## 5. 目标结构(三维 + 平台, 已被上面数据验证)

```
docs/studio/
  INDEX.md            # 治理总纲(当前缺失!): 三维模型 + 所有权不变量 + 实现状态标注规范 + 路由决策树 + cross-link 规范
  01_workflows/       # 维度① 旅程脊柱(保留). 6 节点 = 动作清单; 每动作链接 capability + region + status。这就是"查漏表"
  02_capabilities/    # 维度② 能力(拥有跨区域 flow, 只链接 region 不重述组件):
                      #   skill-registry · graph-authoring · phase-editing · file-editing · compile-lint
                      #   predict · run-execution · trace-observability · golden-eval · debug-resume
                      #   conflict-overwrite · copilot-assist · publish
  03_regions/         # 维度③ UI 区域(拥有组件结构/状态/API, MECE):
                      #   welcome · shell-layout · center-action-bar · canvas · editor · assets
                      #   input · properties · timeline · local-history · copilot · settings
  04_platform/        # 真·基础设施(非 UI 非用户能力): llm-gateway · state-engine · workspace-fs
```

### 所有权不变量(消灭重叠的关键, 不只是切轴)
> **一个事实只在一个 tier 写"实现", 其余只能链接。**
> - region 文档拥有组件本身(结构/状态/props/API/文件位置)。
> - capability 文档拥有跨组件的数据流/行为, **只链接 region, 绝不重述组件内部**。
> - workflow 节点拥有旅程, 只链接 capability + region + status。

### 路由决策树(任务该落哪)
- 改某组件的结构/状态/渲染 → 它的 `03_regions/<region>`。
- 改跨组件的流程/行为/数据流 → `02_capabilities/<cap>`(它链接相关 region)。
- 新增用户旅程步骤 / 查漏 → `01_workflows/<node>`(链接 cap + region)。
- 后端服务/基础设施 → `04_platform/<x>`。

---

## 6. 旧文档 → 新结构 迁移映射

| 旧(文件夹 / 文档标题) | 拆向 |
|---|---|
| `02_features/asset-explorer` (multi-file-editor) | `regions/assets`(文件树) + `regions/editor`(Monaco/split) + `regions/input`(schema) + `regions/properties`(表单半) + `capabilities/file-editing` + `capabilities/phase-editing` |
| `02_features/canvas-topology` | `regions/canvas`(组件) + `capabilities/graph-authoring`(流程) |
| `02_features/copilot-chat` (copilot-assistance) | `regions/copilot`(组件) + `capabilities/copilot-assist`(流程) |
| `02_features/skill-lifecycle` | 纯能力, 无 region: `capabilities/{compile-lint, run-execution, predict, conflict-overwrite, publish}` |
| `02_features/trace-inspector` (trace-visualization) | `capabilities/trace-observability`(流程) → 链接 `regions/{timeline, properties, canvas}`; 主题归 `regions/shell-layout` |
| `03_platform/llm-gateway` (llm-provider-config) | 保留 `platform/llm-gateway` + 模型选择器 UI 链到 `regions/{copilot, settings}` |
| `03_platform/state-engine` | 保留 `platform/state-engine`(真 infra) |
| `03_platform/system-layout` (studio-layout) | **降级拆分**: 它是前端壳不是平台 → `regions/{shell-layout, welcome, center-action-bar}` |
| `03_platform/workspace-fs` | 保留 `platform/workspace-fs`(runs/git/registry) |

### 顺带必修的组织债
- 补回缺失的 `docs/studio/INDEX.md`(所有 baseline 都引用它的"5 维模板"但它不存在)。
- 死链修复: `../multi-file-editor/` `../llm-provider-config/` `../../../INDEX.md` 等全部指向旧路径。
- 改名对齐: 5 个文件夹名 ≠ 文档标题。
- `V0.3.0-NEW-REQUIREMENTS...md` 里 5 条暂存需求按新结构分发归位。

---

## 7. 迁移成本与分期建议

5 features → ~13 capabilities + ~10 regions ≈ 23 个产品文档 + 3 平台。建议分期:
1. **P0 治理**: 写 `INDEX.md`(三维 + 不变量 + status 规范 + 路由树) — 没有它任何重切都会再次漂移。
2. **P1 灭热点**: 先处理 4 个冲突热点 region(`properties` / `canvas` / `timeline` / `center-action-bar`)+ 补 `debug-resume` 最大孤儿。
3. **P2 补全**: 其余 region/capability 文档 + 死链/改名/V0.3.0 分发。
