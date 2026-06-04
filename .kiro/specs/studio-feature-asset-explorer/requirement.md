# 需求规格 — Asset Explorer & Workspace 重新对准 (MVP0)

> **状态**: 重新对准 (2026-06-01)
> **重定向说明**: 本版相对旧版做了**重点对调**。旧需求把重心放在「整洁」与「复杂分屏」上，经与产品方对齐后确认真实意图是 **「透明 / 去黑盒」** 与 **「极简分屏」**。详见 §5 原话留底。

---

## 1. 背景与核心意图 (Background & Intent)

Studio 编辑器的文件浏览与分屏当前存在以下偏差，**且旧需求本身的重点也偏了**：

* **`.workspace` 黑盒**: 运行数据库 (`checkpoints.db`)、轨迹日志 (`trace.jsonl`)、产物 (`artifacts/`) 对开发者完全不可见。**真实诉求不是把树弄「干净」，恰恰相反——是要能清楚看到每一个文件，消除黑盒。**
* **子图呈现零散**: 子图文件 (`phases/<id>/SUBGRAPH.md`) 缺少像 VS Code 次级树那样的独立归类位置。
* **分屏诉求被过度设计**: 旧需求要「可拖拽阻尼器 + 双击折叠状态机 + 磨砂样式」。真实诉求只是 **diff/对照时能两屏并排看**，要极简。
* **缺少 Copilot 改动审阅**: Copilot 改完代码后，没有像 Cursor 那样的 inline diff 高亮 + accept/reject 交互。

**一句话定位**: 本特性的第一性原理是 **「透明可见」**（去黑盒）与 **「极简对照」**（够用即可），不是「整洁美观」。

---

## 2. 范围与 Scope 标注 (Scope Map)

| 需求 | 优先级 | Scope（归属域） | 说明 |
|------|--------|----------------|------|
| REQ-A `.workspace` 去黑盒 | **P0** | 后端文件服务 + 前端资源树 | 本特性核心 |
| REQ-B 子图面板 | P1 | 前端 Assets 面板 | 维持现状，抄 VS Code 次级树 |
| REQ-C 极简分屏 | P1 | 前端 Split/Editor | 复用现有 splitMode，小修 |
| REQ-D Copilot inline diff + accept | P1 | **Copilot 域**（CopilotPanel ↔ 编辑器集成） | 本 spec 包含，但需与 `studio-feature-copilot-chat` 协调接口边界 |

> **跨 spec 提示**: REQ-D 在功能域上属于 Copilot。本 spec 负责实现，但其「Copilot 如何产出 diff 建议」的上游契约由 `studio-feature-copilot-chat` 定义；本 spec 只负责「在编辑器内渲染 inline diff + accept/reject」的下游呈现与交互。

---

## 3. 功能需求 (Functional Requirements)

### REQ-A（P0）`.workspace` 全量透明暴露 — 去黑盒
> **Scope**: 后端文件服务 + 前端资源树
> **用户故事**: 作为 skill 开发者，我希望在文件树里看到工作区里的**每一个文件**（包括运行产物、日志、中间产物），以便不依赖终端就能直接审视运行结果、消除黑盒。

**验收标准 (EARS)**
* **A-1**: 系统应当在后端文件扫描中**放行** `.workspace` 目录及其全部子内容（runs / artifacts / 日志 / 数据库），不再以「隐藏目录」为由统一拦截。
* **A-2**: 当扫描到 `.workspace` 内的文件时，系统应当像对待普通文件一样将其纳入返回的文件清单。
* **A-3**: 前端文件树应当像 VS Code 一样，把 `.workspace` 当作普通文件夹**自然递归展开**，不创建合成节点、不做特殊隐藏（贯彻「去黑盒」）。
* **A-4**: 当文件为可解码文本时，系统应当允许在编辑器中正常打开查看。
* **A-5**: 若文件为二进制或超过体量阈值（如 `checkpoints.db`），则系统应当**仍在树中显示该文件**，并标注为「二进制 / 过大、不可文本打开」，而非将其从树中抹除。
* **A-6**: 当新建或导入 skill 时，系统应当自动补齐 `.workspace/runs` 与 `.workspace/artifacts` 标准目录布局（幂等、无损）。

**非功能约束**
* `.workspace` 全量入树的清单会随运行历史增长（接口 payload / 文件数）。**透明优先于整洁**；但 design 阶段须考虑大体量下的懒加载或上限策略，避免接口无界膨胀（设计期决策，非本需求阻塞项）。

---

### REQ-B（P1）子图面板 — 抄 VS Code 次级树
> **Scope**: 前端 Assets 面板
> **用户故事**: 作为开发者，我希望子图作为一类被独立归类呈现（像 VS Code 的次级树），以便在不打乱主文件树的前提下清晰管理子图。

**验收标准 (EARS)**
* **B-1**: 系统应当在左侧 Assets 侧栏**最底部**提供一个名为 "Subgraph Library" 的面板，支持**折叠/展开**且**独立滚动**。
* **B-2**: 系统应当通过 frontmatter（`mode: subgraph` 或存在 `target_skill` / `sub_skill_ref`）识别子图文件，并将其从主文件树挑出、归入该面板。
* **B-3**: 子图归类是**有意分类而非隐藏**——子图文件在该面板中仍**清晰可见**（不违背 REQ-A 的去黑盒原则）。
* **B-4**: 系统应当保留现有的子图注册/状态能力（Registered / Register 徽章、目录绑定）。
* **B-5**: 系统应当**移除**现有代码中的硬编码 demo 兜底数据（mock 子图列表、写死的绝对路径），改为真实数据驱动；当无真实子图时面板呈现空态而非假数据。

---

### REQ-C（P1）极简分屏 — 两屏对照
> **Scope**: 前端 Split / Editor
> **用户故事**: 作为开发者，我希望 diff/对照时能把两个文件并排放在两个屏里看，交互越简单越好。

**验收标准 (EARS)**
* **C-1**: 系统应当支持左右两个编辑器屏并排显示（复用现有 splitMode）。
* **C-2**: 系统应当允许用户通过**拖拽文件到某一屏**，将该文件加载到对应屏。
* **C-3**: 当某一屏为空白时，系统应当允许用户**点击文件直接填入该空白屏**。
* **C-4**: 系统**不应**引入双击折叠、折叠状态机、磨砂阻尼器样式等复杂交互（明确排除旧 REQ-5 的过度设计）。

---

### REQ-D（P1）Copilot inline diff + accept（Cursor 式）
> **Scope**: **Copilot 域**（CopilotPanel ↔ 编辑器集成）；本 spec 实现，上游契约见 `studio-feature-copilot-chat`
> **用户故事**: 作为开发者，当 Copilot 改动代码时，我希望像 Cursor 那样在编辑器里看到「改了哪里」的高亮 diff，并能 accept/reject。

**验收标准 (EARS)**
* **D-1**: 当 Copilot 产出对某文件的修改建议时，系统应当在该文件编辑器内以 **inline diff** 形式高亮展示新增 / 删除 / 修改的行（参照 Cursor 的 inline diff 体验）。
* **D-2**: 当存在待审阅的 inline diff 时，系统应当提供 **Accept / Reject** 控件（支持整体接受/拒绝；逐处接受为可选增强）。
* **D-3**: 当用户 Accept 时，系统应当将改动落盘并清除 diff 高亮，回到正常编辑态。
* **D-4**: 当用户 Reject 时，系统应当还原到改动前内容并清除 diff 高亮。
* **D-5**: 系统应当复用本特性既有的编辑器组件呈现 diff，不另起一套独立编辑器栈。

---

## 4. 非目标 (Non-Goals)
* **不做**任意「文件 A vs 文件 B」的通用 diff 视图（用户已明确：分屏只做并排对照，不做 diff 视图；diff 专指 Copilot 改动审阅，见 REQ-D）。
* **不做**「当前 vs 历史版本」「工作副本 vs 远端」的版本对比 diff（如未来需要，另起需求）。
* **不做**旧 REQ-5 的可拖拽阻尼器 / 双击折叠 / 磨砂样式。
* **不**为「整洁」而隐藏 `.workspace` 任何文件。

---

## 5. 原话留底 (User Intent — Verbatim)

> **关于重点对调**:
> 「我感觉重点不对了, 分屏不是什么重要功能, 我之前不想做那么复杂, diff 的时候能有两个屏对照着看就行。.workspace 绝对不是要干净, 而是能清楚看到每一个文件, 去黑盒」

> **关于子图面板**:
> 「维持现状, 但是我本来是说抄 vs code 的 asset tree, 放在底部, 可以收起来」

> **关于分屏与 diff 的边界**:
> 「我想了想不用 diff 视图, 分屏就简单, 分两个屏, 各自拖文件进入, 或者点击文件填入空白屏就行; diff 要的是像 cursor 那样的 copilot 改了哪里高亮 diff, accept 那种, 抄一下」

> **关于 REQ-D 归属**:
> 用户指示：把 Copilot inline diff + accept 这条**拉回本 spec**，并标明其 scope（Copilot 域）。

---

## 6. 关联文档与待同步项
* 技术设计（旧版已判定需重做）: `design.md` → 重新对准后须经 `/kiro:spec-design` 重写。
* **待修正失真**:
  * `docs/studio/02_features/asset-explorer/baseline.md`: 称分屏「rigid / 不可拖拽」，与实际不符（现有 `ResizableHandle` 默认即可拖拽）。
  * `docs/studio/02_features/asset-explorer/mvp0-alignment.md`: 「dedicated Workspace 节点」与本需求「自然入树、不造合成节点」冲突；磨砂样式诉求已废弃。
