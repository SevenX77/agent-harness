# PM Pending Questions — Studio Copilot Chat Redesign

> **用途**: 解锁 `design.md` 之前必须收敛的问题清单（baseline → implementation 阶段闸门）。
> **来源**: 对 `requirement.md` + `research.md` 的架构评审，对照 `docs/studio/02_features/copilot-chat/{baseline,mvp0-alignment}.md`、前身 spec `copilot-context-design/`、活线代码。
> **方法**: 第一性原理 + 全局统筹；每条结论附 `file:line` 证据。
> **日期**: 2026-06-01

---

## 结论

需求收敛与行业调研质量高，阶段纪律正确（baseline 阶段只有 requirement+research，符合 `.kiro/specs/INDEX.md:44-48`）。
但有 **3 个架构地基问题（P0）必须先拍板**，否则 design 建在错误前提上；另有一批被前身 spec/docs 写过、却在本次重写中丢失的需求与约束（P1）需要补回；还有若干文档卫生问题（P2）。

**P0-A 已由 PM 拍板**：文件写入唯一权威 = 编辑器 save-compile 契约（抄 Cursor / VS Code + Copilot 模式）。下文给出落地方案。

---

## P0 — 架构地基（design.md 之前必须解决）

### P0-A. 文件写入唯一权威 ✅ 已决策：抄 Cursor / VS Code + Copilot

**问题**：原 REQ-8 让 Copilot 自带 `POST /api/skills/{skill_id}/copilot/apply-patch`，自己做 hash 校验 + 安全写 + 增量编译。这与 `docs .../mvp0-alignment.md:248-252` 的 ownership 边界（"Multi-file editor owns conflict-aware application；Copilot 只 own patch proposal UI"）直接冲突，且与 SDK 直写（`copilot.py:127-130`）构成三条互相不认账的写盘路径。

**Cursor / VS Code + Copilot 的真实模式（第一性原理）**：
编辑器的**内存文档模型是唯一写入权威**。AI 永不直接写磁盘——它产出 edits，apply 到文档模型，以可审阅 diff 呈现，用户 accept/reject，最后走正常 save 路径落盘。"Apply" 按钮只是驱动编辑器已有的保存能力，不是另造一条写链路。

**关键发现：本仓库已经有这套权威，REQ-8 是在重复造轮子。**

| REQ-8 想造的能力 | 已存在的端点 | 证据 |
|---|---|---|
| 批量写多文件 | `PUT /skills/{skill_id}` → `UpdateSkillReq(files, expected_hash)` → `SkillDetail` \| 409 `snapshot_conflict` | `apps/studio/backend/app/routers/skills.py:338-363` |
| 写单文件（hash 守卫） | `POST /skills/{skill_id}/files/{path}` → `UpdateSkillFileReq(content, expected_hash)` → `UpdateSkillFileRes(path, hash)` \| 409 | `skills.py:366-394` |
| 冲突检测（`conflicts[]`） | 已返回 `{code:"snapshot_conflict", current_hash, current_markdown_content}` | `skills.py:359-362, 389-392` |
| 增量编译（`compile{}`） | `POST /skills/{skill_id}/compile` → `CompileSuccess` \| 422 `compile_failed{errors[]}` | `skills.py:109-119`；前端 `apps/studio/frontend/src/api/client.ts:83-85` |
| 编辑器侧冲突 UI | `SaveConflict` + `onSaveConflict` 已接 | `apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:26,47` |

> 已确认 `apply-patch` / `patch_proposed` 在前后端**均不存在**（grep 全仓库为空）——REQ-8 是 greenfield，没有迁移负担，现在定对形状即可。

**REQ-8 重设计（落地方案）**：
1. **删除** 独立的 `copilot/apply-patch` 端点，以及 `ApplyCopilotPatchRequest/Response` 自定义契约。
2. **"Apply" 数据流**（抄 VS Code）：
   - 若目标文件在编辑器中已打开 → 把 `afterText` 写入编辑器**内存 buffer**（变 dirty），让用户走正常保存；
   - 否则 → 直接调 `POST /skills/{skill_id}/files/{path}`（多文件用 `PUT /skills/{skill_id}`），`expected_hash` = 提案携带的 `beforeHash`。
3. **冲突**：命中 409 `snapshot_conflict` → 复用现有 `SaveConflict` / `onSaveConflict` UI，不另写一套。
4. **编译**：Apply 成功后调 `POST /skills/{skill_id}/compile`，把结构化 `compile_failed{errors[]}` 回灌 diff bubble。
5. Copilot 只负责：产出 `patch_proposed` 提案 + 提案 UI（Apply/Reject/Open Compare）。**写、冲突、编译三件事全部委托给上面已有端点。**

**对契约的连带要求**：提案必须携带 `beforeHash`（= agent 读文件时的 hash），否则 Apply 无法填 `expected_hash`、无法触发冲突检测。这把 P0-C 的"schema 必须保留 hash 字段"绑死了。

---

### P0-B. REQ-6"安全写"：机制未定义 + Bash 旁路（安全保证是漏的）

**问题 1（机制）**：REQ-6 要"禁止 Write/Edit 直接落盘，改成 `patch_proposed` 事件"。但活线 `copilot.py:129` 是 `permission_mode="acceptEdits"`（自动接受并落盘），spec/research **完全没写**如何把 SDK 工具调用变成提案。这是整个 feature 技术风险最高的部分，docs `mvp0-alignment.md:123` 还用了 "**when possible**" 对冲，而 REQ-6 把它硬化成绝对禁止、风险却没降。

可行机制（design 阶段需 PoC 验证 SDK 能力）：
- SDK 权限回调 `can_use_tool`（或 PreToolUse hook）拦截 Write/Edit → **deny 实际执行** → 捕获工具入参（path + new content）→ 转译为 `patch_proposed` 事件。
- 不要假设 SDK 一定支持——**design 阶段先写一个 30 行 PoC 确认拦截 + 拿到入参**，再继续。

**问题 2（Bash 旁路，更严重）**：`_ALLOWED_TOOLS = ["Read","Write","Edit","Bash"]`（`copilot.py:59`）。就算拦住 Write/Edit，Bash 仍在。LLM 被堵 Write 后可 `cat > file <<EOF` / `sed -i` / `python -c` 把文件写了，**绕过整个 patch-proposal 安全闭环**，"用户完全掌控 workspace 完整性"直接失效。

处置选项（需 PM/设计拍板）：

| 选项 | 做法 | 取舍 |
|---|---|---|
| **B1（推荐 MVP0）** | 从 Copilot 编辑会话**移除 Bash**，所有写操作只能走 Write/Edit→提案 | 整改最小、安全保证最强；代价是 Copilot 不能跑任意 shell（对"skill 编辑助手"定位通常够用） |
| **B2** | SDK `cwd` 指向 workspace 的**沙箱副本/overlay**，diff 副本 vs 真 workspace 生成提案 | agent 可自由用任何工具；代价是副本同步 + diff 计算复杂度，dirty buffer 协调更绕 |
| **B3（不推荐）** | PreToolUse hook 解析 Bash 命令检测写操作 | 脆弱，无法可靠覆盖所有写法（重定向/脚本/解释器内写） |

> 与 P0-A 一致：B1 让**所有写都变成经编辑器权威落盘的提案**，最符合"单一写入权威"。

---

### P0-C. Spec 碎片化：同一 mention 契约有三套不一致的真相源

`@mention` 契约散在三处，schema 互不一致，且新 spec 反而**比要取代的 docs 还少字段**：

| 来源 | mention 字段 | implicit context | 备注 |
|---|---|---|---|
| 旧 spec `copilot-context-design/research.md:41-54` | `type: file\|phase\|edge_context\|system_error`, `id` | `{activeSkillId, selectedNodeId, hasCompileErrors}` | 类型名是 `system_error` |
| docs `mvp0-alignment.md:59-80` | 含 `edge:{sourcePhaseId,targetPhaseId}`、`runId` | `dirtyFiles:[{path,content,hash?}]` | **最完整** |
| 新 spec `research.md:51-66` | **无** edge/runId | `dirtyFiles:[{path,content}]`（**无 hash**） | 最简，退化 |

**自相矛盾**：
- 丢了 `edge.sourcePhaseId/targetPhaseId` → 但 REQ-5 要"展开 edge_context 到 trace JSON"，只靠 `id` 无法定位一条边。
- 丢了 `hash` → 但 REQ-8（P0-A 方案）要 `expected_hash` 才能写 + 冲突检测，基线哈希无来源。

且本次重写与 `copilot-context-design/` 的关系**未声明**，docs `mvp0-alignment.md:26` 还在把旧 spec 当 edge 自动 mention 的权威引用——两份 Draft 同时宣称拥有 mention 契约。

**收敛动作**：
1. 明确 `studio-feature-copilot-chat` **supersede** `copilot-context-design`，把后者移入 `.kiro/specs/_archive/`。
2. 以 docs mvp0 完整版为基准统一 schema：补回 `edge{sourcePhaseId,targetPhaseId}`、`runId`、`dirtyFiles[].hash`、提案 `beforeHash`。
3. spec `research.md §3` 成为**唯一契约真相源**，docs 引用它而非各写一份。

---

## P1 — design 阶段必须补回的需求与约束

多为前身 spec/docs 写过、本次重写丢失，非凭空新增。

| # | 问题 | 证据 | 处置 |
|---|---|---|---|
| **D** | **Token 预算/截断策略整体缺失** | 旧 spec `copilot-context-design/requirements.md:62` 明确"150K 上限 + 截断或过载提示"；新 spec REQ-4/5 全量注入 file+AST+trace **无上限** | 补回 token 预算 + 显式截断/过载策略（呼应 error-handling 铁律"降级必须显式可观测"） |
| **E** | **REQ-3（带关闭按钮的交互式 pill）与 §4.1（react-mentions）技术互斥** | REQ-3 要"非可编辑 Pill + inline 关闭按钮"；`research.md:99-103` 选 react-mentions（textarea 高亮 overlay，无法在原生 textarea 内渲染真 DOM pill） | **推荐解法（抄 VS Code Copilot）**：mention chips 放在 composer **相邻的 chips 条**（真 DOM、可关闭、可着色），textarea 保持纯文本；`@` 仅作触发，选中后从文本移除、加入 chips。这样无需 Tiptap，也绕开 react-mentions 限制——甚至可不依赖 react-mentions |
| **F** | **mention 候选数据来源未定义** | REQ-1 要列 Files/Phases/Edge/Errors，未说从哪枚举 | 明确 picker 数据契约：phases←canvas graph model、errors←compile diagnostics、edge←trace DB |
| **G** | **跨 spec 硬依赖未声明** | REQ-5 依赖 phase AST / trace DB / incremental compile | 分属 `engine-mvp0-rebuild-v030` / `studio-feature-trace-inspector` / `studio-feature-skill-lifecycle`。在 spec 内列为前置，契约稳定前 resolver 无法完整实现 |
| **H** | **会话连续性 / episodic memory / new-chat reset 被丢** | docs `mvp0-alignment.md:125-128` 有，新 spec 无 | 补回多轮编辑的会话语义 |
| **I** | **`context_resolved` 透明回显事件被丢** | docs `mvp0-alignment.md:153` 用它兑现"拒绝 hidden prompt magic"（`mvp0-alignment.md:20`）；新 spec 无 | 补回：让 PM 可见"模型到底拿到了哪些上下文" |
| **J** | **面板 unmount 状态丢失风险** | mvp0 `CopilotPanelState` 含 `pendingPatchById`/`mentions`，未说面板卸载怎么办 | 与"切 Tab 丢测试状态"（state elevation 修复）同类，复用状态提升结论 |

**另**：REQ-9/10（模型路由状态 + 错误卡片）与在飞的 `studio-llm-gateway-redesign`、`studio-llm-copilot-reconciliation` 重叠；docs `mvp0-alignment.md:254-258` 已 cross-link，spec 未做——避免 Copilot 自造一套 model-resolution UI。

---

## P2 — 文档卫生（机械修复，本轮按 PM 指示未动）

- **K. docs 三处 cross-link 全断**：`baseline.md` / `mvp0-alignment.md` 指向 `../trace-visualization/`、`../multi-file-editor/`、`../llm-provider-config/`，三目录在 `docs/studio` 下全不存在（`find` 确认）。现行 taxonomy 是 `02_features/trace-inspector`、`03_platform/llm-gateway`，`multi-file-editor` 疑似并入 `03_platform/workspace-fs`。
- **L. `.kiro/specs/INDEX.md` 未登记**：copilot-chat、asset-explorer、canvas-topology 都不在 Active 表（grep 确认），但目录是 2026-06-01 新建。
- **M. 命名不统一**：新 spec 用 `requirement.md`（单数，符合 INDEX:42），旧 spec 用 `requirements.md`（复数）。新 spec 无错，但仓库两种约定并存。

---

## 收敛顺序

1. **先拍 P0**：A（已决策，落地 REQ-8 重设计）→ B（Bash 处置 + 拦截 PoC）→ C（supersede + 单一 schema）。三者未定，`design.md` 不解锁。
2. P1：D/E/H/I 补回需求；F/G 显式列出数据来源与前置依赖。
3. P2：5 分钟机械修复。

## 留给 PM 的开放决策

1. **P0-B Bash 处置**：B1 移除 Bash（最安全，Copilot 失去任意 shell）vs B2 沙箱 cwd（更强自治，更复杂）。
2. **P1-E composer 形态**：chips 条（推荐，抄 VS Code）已能满足 REQ-3 意图，确认是否接受"不做 textarea 内联 pill"。
3. **MVP0 范围切分**：REQ-1..12 跨多个可独立交付的能力（mention 选择器 / 结构化 context resolver / 安全 patch / 模型状态），风险各异。建议把最高风险的 REQ-6（写拦截）单独 de-risk 或后置，先交付 context resolver + mention。
