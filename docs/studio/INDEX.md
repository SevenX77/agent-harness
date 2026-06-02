# Skill Studio 文档体系 — 治理总纲 (INDEX)

> **用途**: 本文件是 `docs/studio/` 的**唯一治理总纲**。任何人(含 AI)在写 Studio 文档、设计任务、圈定改动范围前, 必须先读本文件, 按这里的三维模型 + 所有权不变量 + 路由决策树办事。
> **状态**: v1 治理总纲已落 (2026-06-01)。`02_capabilities/` 与 `03_regions/` 为新骨架; `02_features/` 与 `03_platform/` 为 **legacy 迁移源**(迁移后删除)。迁移逐条去向见 [_reorg/workflow-derivation.md](_reorg/workflow-derivation.md)。
> **为什么需要它**: 旧体系所有 baseline 都引用一个"INDEX.md 5 维模板"但它从不存在; 5 个 feature 用两条互不兼容的轴混切, 导致同一组件被多份文档争抢、大量动作无人认领。本文件就是补上那个缺失的根, 并换成经 workflow 全量推导验证的三维模型。

---

## 1. 三维模型 (核心心智)

Studio 的每个功能都是同一系统在**三条正交轴**上的投影。三轴两两多对多, **因此是三棵互相链接的独立树, 不能互相嵌套**。

| 维度 | 树 | 回答的问题 | 拥有什么 |
|---|---|---|---|
| ① **Workflow(旅程)** | `01_workflows/` | "PM 这一步在做什么, 我有没有漏" | 用户旅程; 每个动作链接到 capability + region + status |
| ② **Capability(能力)** | `02_capabilities/` | "这个跨组件的流程/行为怎么跑通" | 端到端**数据流/行为**; 只链接 region, 不重述组件 |
| ③ **Region(UI 区域)** | `03_regions/` | "这块界面是什么、状态在哪" | UI **组件**结构/状态/props/API |
| (基础设施) | `04_platform/` | "后端服务/底层架构怎么提供能力" | 非 UI、非用户能力的真 infra |

**正交性证明**(两两多对多, 所以不能嵌套):
- 一个 workflow 节点 → 多个能力(debug 节点 = trace-observability + debug-resume + copilot-assist)
- 一个能力 → 多个 workflow 节点(trace-observability 出现在 run / debug / eval)
- 一个能力 → 多个 region(trace-observability 渲染在 timeline + properties + canvas)
- 一个 region → 多个能力(properties = phase-editing + trace-observability + golden-eval)

**用法**: 设计阶段从 ① 走(旅程脊柱保证不漏); 执行/圈 scope 时落在 ②×③ 的某个格子(能力 C 在区域 R 的那一份)。

---

## 2. 所有权不变量 (铁律, 灭重叠的关键)

> **一个事实只在一个 tier 写"实现", 其余 tier 只能链接。**

- **region 文档**拥有组件本身: 结构、state、props、API、file:line。
- **capability 文档**拥有跨组件的数据流/行为: **只链接 region, 绝不重述组件内部**。
- **workflow 节点**拥有旅程: 只链接 capability + region + status。
- **platform 文档**拥有后端服务/架构: 被哪些 capability 依赖用**反向链接**。

违反示例(旧体系实况): `canvas-topology` 和 `trace-inspector` 都去描述 `ContextEdge → Properties 面板` 的实现 → 两份矛盾。正确做法: `regions/canvas` 写 ContextEdge 组件、`regions/properties` 写 Connection Trace 视图组件; `capabilities/trace-observability` 只写"点击 edge 数据包点 → 在 properties 渲染上游 Context"这条流并链接两个 region。

**强制一致**: 文档标题 == 文件夹名(旧体系 5 处不一致引发改名漂移, 杜绝)。

---

## 3. 路由决策树 (一个任务/需求该落哪个文档)

```
这个改动主要是……
├─ 改某个 UI 组件的结构/状态/渲染/props      → 03_regions/<region>
├─ 改一条跨组件的流程/行为/数据流            → 02_capabilities/<cap>  (它链接相关 region)
├─ 新增/调整用户旅程里的一步, 或做覆盖查漏    → 01_workflows/<node>   (链接 cap + region + status)
└─ 改后端服务/事件桥接/文件系统/provider     → 04_platform/<x>
```

**worked example — V0.3.0 需求 1 (assets 面板加 subgraph 类目 + 导入流程)**, 旧体系 PM 列了 3 个候选家, 现在确定:
- subgraph 类目**渲染在 assets 面板** → 组件归 `03_regions/assets` 写 `<SubgraphCategory>`;
- "registry resolve → 标红 → OS 选目录 → POST import"**这条流** → `02_capabilities/skill-registry`(链接 input region, 不重写组件);
- 它服务于装配期 → `01_workflows/02_authoring` 加一行链接;
- 后端 `SkillResolverProtocol` DI → `04_platform/workspace-fs`(或 llm-gateway 同款 resolver 段)。
→ 一个需求拆成**职责不同**的归属, 互不重叠、一个不漏。

---

## 4. 实现状态标注规范 (status, per-action 标签)

旧 baseline 把"目标设计 / 占位 / 孤儿 / 活代码"混写不标注, 是设计任务时分不清的根源。**每个动作/组件必须带 status**:

| status | 含义 | 例 |
|---|---|---|
| `live` | 已接线、真实数据驱动、可用 | compile 门控、run 历史列表 |
| `placeholder` | 入口/按钮存在但回调是桩 | `onPredict`/`onRun` = `console.info` |
| `orphan-unmounted` | 组件已构建但无 importer, 不可达 | `TracePanel` `PromptInspector` `DiffView` `useRunStream` |
| `backend-only` | 后端就绪, 前端无 UI | `resume_run`、predict→golden 409 守卫、batch-run |
| `target-design` | 仅文档目标, 代码无任何对应 | HitL 问题框、Copilot Judge、node-micro-topology |
| `stale-doc` | 文档与实现相反/过时, 需修文档 | publish 走 registry 非 git; canvas "未持久化" 实则已持久化 |
| `stale-code` | 代码在跑但实现**过时格式**, 冲突 FROZEN skill-spec, 需重建 | phase 表单写 `mode`/`<system_prompt>`/`<exit_contract>`/`<python_callable>`、删 `validator`/`llm_role`(全违背 `docs/engine/skill-spec`) |

---

## 5. 目录结构

```
docs/studio/
  INDEX.md            # 本文件 — 治理总纲(根, 管 mvp0+mvp1)
  _reorg/             # 重组工作区: catalog / 对齐笔记 / 推导 / handoff / 暂存需求
  mvp0/               # 旧设计·当前实现 baseline: 02_features/ 03_platform/ (⚠ 迁移后按需删; 不要据此实现)
  mvp1/               # ★新设计·重设计目标: 01_workflows/ 02_capabilities/ 03_regions/ 04_platform/
```

---

## 6. 权威注册表 (Registry — 唯一词表)

设计任务时**只能用下面的 capability / region / platform 名**, 不要另造。新增需先在此登记。

### 02_capabilities (13)
| 能力 | 一句话 | 迁移来源 |
|---|---|---|
| `skill-workspace` | 打开文件夹/Recent(MRU)/新建/移除最近/reveal; **无注册表**; 子图按 path 解析(copilot cwd 含子图 path) | 旧 workspace-fs(前端) + system-layout(路由) |
| `graph-authoring` | 画布拓扑编辑: IO 节点、连线/断连、校验、新建 phase、子图展开/下钻、数据断层 | 旧 canvas-topology(流程) |
| `phase-editing` | 节点属性表单全字段编辑 + 保存 | 旧 asset-explorer(表单); 进阶字段大量待补 |
| `file-editing` | Monaco 全文编辑/分屏/schema 推断/保存冲突/file-watch | 旧 asset-explorer(编辑器) |
| `compile-lint` | 实时 lint + 手动 compile + 错误面板 + stage 门控 | 旧 skill-lifecycle(compile) |
| `predict` | 试飞: 测试输入/远程校验/mock-llm/拟真输出/predict→golden 守卫 | 旧 skill-lifecycle(predict); 多处未挂载 |
| `run-execution` | 真实 Run/状态/WS 流/autocommit/batch/run 历史 | 旧 skill-lifecycle(run) + state-engine(流) |
| `trace-observability` | trace 读取/metrics/filter/Prompt Inspector/edge-pin/edge-context/节点灯/微观拓扑 | 旧 trace-inspector |
| `golden-eval` | golden 固化/Diff/字段得分/Copilot Judge/导出/打磨编排 | 旧 ux-workflow; judge 无主待建 |
| `debug-resume` | HitL 问题框/节点级 Resume/checkpoint 续跑/脏状态失效/context 篡改 | **全孤儿, 待新建** |
| `conflict-overwrite` | 顺序覆盖 overlay/白名单/cancel 标红 | 旧 skill-lifecycle + canvas-topology(并) |
| `copilot-assist` | 对话/上下文注入/@mention/建技能向导/打磨/judge/commit-msg | 旧 copilot-chat(流程) |
| `publish` | 上线/commit-msg/confetti/artifact-registry | **无主待建**(注意文档与实现矛盾) |

### 03_regions (12)
| 区域 | 一句话 | 关键组件 | 迁移来源 |
|---|---|---|---|
| `welcome` | 主页/Home 入口屏 | WelcomePage, NewSkillDialog | 旧 system-layout + workspace-fs(前端) |
| `shell-layout` | 全局壳: Header/Toolbar/三栏/Resizable/Context/主题/面包屑/路由 | Workspace, Header, Toolbar | 旧 system-layout(主体) |
| `center-action-bar` | 中心动作条 + 编译错误面板 (Compile/Predict/Run) | center-action-bar, CompileErrorPanel | 旧 system-layout + skill-lifecycle(状态语义) |
| `canvas` | GraphCanvas 节点/边/overlay 渲染(中心视图之一) | GraphCanvas, ContextEdge, SkillNode | 旧 canvas-topology(组件) |
| `editor` | Monaco 全文/分屏编辑器(中心视图之一, 下嵌随动图) | SplitEditor, LazyMonacoPanel | 旧 asset-explorer(编辑器/split) |
| `assets` | 左侧文件树面板(Toolbar `assets`) | AssetsPanel | 旧 asset-explorer(文件树) + system-layout(panels) |
| `input` | 左侧 Input/schema 面板 + JSON schema infer + 测试输入 | InputPanel, PredictInputDialog | 旧 asset-explorer(笼统), 实为无主 |
| `properties` | PropertiesPanel: 节点表单 + edge-context 只读 + (未来)Diff | PropertiesPanel, phase-frontmatter | 旧 asset-explorer + trace-inspector(分) |
| `timeline` | Timeline/Trace 面板: run 历史 + 流式 trace | TimelinePanel(历史), TracePanel(流式·未挂载) | 旧 trace-inspector(组件) |
| `local-history` | 本地历史/版本/batch summary/run drawer/replay | BatchSummary, RunDetailDrawer | 旧 workspace-fs(前端), 薄 |
| `copilot` | CopilotPanel: 对话/消息/工具气泡/模型选择器 | CopilotPanel, ModelPicker | 旧 copilot-chat(组件) |
| `settings` | SettingsPage: API keys/roles/copilot 配置/产物路径 | SettingsPage, ProviderCard, LlmRolesTab | **无 region 文档**, 旧 llm-gateway 只覆盖后端配置 |

### 04_platform (4) — 后端三分(锁定 2026-06-01, 详见 [_reorg/alignment-notes.md D10](_reorg/alignment-notes.md))
| 块 | 形态 | 职责 | 迁移来源 |
|---|---|---|---|
| `gateway` | Python sidecar | provider/role/credential/model 解析 + copilot chat facade | 旧 llm-gateway + studio backend 的 gateway 代码并入 |
| `engine` | Python sidecar | graph-agent: compile/lint/predict/run/eval/trace | packages/graph-agent |
| `native-fs` | Rust(Tauri) | FS 读写/打开文件夹/watch/MRU/reveal + runs 目录 + golden CRUD + **闭环编排** + copilot session 落盘 + sidecar 生命周期 | 旧 workspace-fs(后端→Rust) |
| `state-engine` | 前端 | 前端状态 + WS/Rust-event ipc 桥 | 旧 state-engine |

> 块1/2 = **无状态纯服务**(引擎真跑时调); 状态/FS/编排归 Rust。两 sidecar **启动期即由 Rust 拉起**(settings 的 API/role 配置 + 未来 login 需 gateway), 但**非全屏 bootstrap gate**: 壳+FS 立即可用, 调 sidecar 处 skeleton + 全局后端就绪指示。RuntimeGate 退役。

---

## 7. 文档模板 (取代缺失的"5 维模板", 按 tier 分)

每个文档顶部统一 frontmatter:
```
> Tier: capability | region | workflow | platform
> Owns: <一句话边界>
> Status-summary: live X / placeholder Y / orphan Z / target W
> Related: [links]
```

### region 文档模板
1. **区域职责** — 一句话边界(本区域管什么、不管什么)
2. **组件清单** — file:line 列表
3. **状态 & props** — 本区域持有的 state(不含跨区域流程状态)
4. **容器/布局归属** — 链接 `shell-layout`
5. **承载的能力** — 表格: 能力(链接 capability) | 在本区域渲染成什么 | status
6. **本区域直接调用的 API**
7. **实现状态总览** — 每个组件 status

### capability 文档模板
1. **能力定义** — 一句话
2. **端到端数据流** — 上游 → 处理 → 下游(谁触发、数据怎么流)
3. **涉及 region** — 表格: region(链接) | 在该 region 渲染什么 | status
4. **依赖的 platform 服务** — 链接 `04_platform/*`
5. **契约 & 关键字段** — 请求/响应/事件 schema
6. **per-step 实现状态**
7. **关联 workflow 节点** — 反向链接
8. **已知缺口 / 重叠 / 矛盾**

### workflow 节点模板
1. **用户旅程目标**
2. **动作清单表** — 动作 | capability(链接) | region(链接) | status | 证据(file:line)
3. **失败退路**
4. **节点间流转** — 上游/下游链接

### platform 文档模板
1. **服务职责**
2. **接口契约** — API / Protocol / 事件
3. **数据模型**
4. **被哪些 capability 依赖** — 反向链接

---

## 8. cross-link 规范

- 一律相对路径 + 锚点, 文档内引用代码用 file:line(终端可点)。
- region→capability: "本区域承载 [<cap>](../02_capabilities/<cap>.md)"。
- capability→region: "在 [<region>](../03_regions/<region>.md) 渲染为……"。
- capability→platform: "由 [<svc>](../04_platform/<svc>.md) 提供"。
- workflow→cap/region: 动作清单表里每行链接。
- **禁止跨 tier 重述实现**, 只能链接(见 §2 不变量)。
- 链接到 legacy 文档时标注 `(legacy, 迁移源)`, 不在新文档里依赖它存活。

---

## 9. 已知组织债 (迁移时统一修)

- **死链**: 所有 baseline 的 `../../../INDEX.md`(原指向不存在的 5 维模板)、`../multi-file-editor/`、`../llm-provider-config/` 等全部失效 → 迁移时按本注册表重连。
- **改名漂移**: 旧 5 文件夹名 ≠ 文档标题(asset-explorer/"multi-file-editor" 等)→ 迁移后强制标题==文件夹名。
- **命名混淆**: `TimelinePanel`(run 历史) 被 Toolbar 标成 "Trace Timeline", 真正的流式 `TracePanel` 未挂载 → 在 `regions/timeline` 文档里澄清两者。
- **自相矛盾**: `trace-inspector` baseline(复用 Properties)vs mvp0(独立 Debugger Panel)→ 迁移到 `capabilities/trace-observability` 时定夺其一并记 decision。
- **文档与实现相反**(标 `stale-doc`): publish 走 Artifact Registry 非 git; Release 用 usePublishSkill 非 useSkillSync; canvas "连线不持久化" 实则已持久化; 分屏 "不可拖拽" 实则可。
- **V0.3.0 暂存需求**: `V0.3.0-NEW-REQUIREMENTS--DO-NOT-DELETE-DURING-CLEANUP.md` 内 5 条按本注册表路由分发后, 方可删该文件。

---

## 10. 迁移分期

1. **P0 治理(本文件)** — ✅ 已落。
2. **P1 灭热点 + 补最大孤儿** — 先做 4 个冲突热点 region(`properties`/`canvas`/`timeline`/`center-action-bar`)+ 新建 `debug-resume` 能力文档。
3. **P2 补全** — 其余 region/capability/platform 文档 + 死链/改名/V0.3.0 分发 + 删 legacy。

> 迁移逐条去向(旧 5 features + 4 platform → 新三维)见 [_reorg/workflow-derivation.md §6](_reorg/workflow-derivation.md)。

---

## 11. 跨切约定 (NFR, 锁定 2026-06-01)

- **后端就绪**: gateway/engine 两 Python sidecar 在 app 启动期由 Rust 拉起。**不全屏 gate** —— 壳+文件树+编辑器(Rust)立即渲染; 依赖 sidecar 的功能(settings/copilot/compile/predict/run)用 skeleton + 全局"后端就绪"指示; sidecar 失败在该功能内报错。(未来 login 可能另加 auth gate, 独立于 sidecar 就绪。)
- **skeleton + lazy load**: 所有后端数据驱动的组件必须骨架屏 + 懒加载 —— `available models` 巨长列表为首要。
- **copilot session 持久化**: 对话 + session 记录落盘(Rust 写 skill 目录), 退出再进**恢复一模一样**(Cursor 同款), 跨窗口可用。
- **多窗口**: Rust 壳 + 共享无状态 sidecar 支持多窗口(一窗口 = 一 skill workspace)。
- **子图按 path**: `SUBGRAPH.md` 与 agent phase 内子图都写死 path, 直接解析(无注册表); copilot cwd scope 必须纳入被引用子图 path。

> 后端单体 → 3 块拆分是独立工程 track(P-arch), 平台层文档依赖它; 详细拆分计划须过 Codex review 再实施。
