---
title: Pending Questions (PM 待拍板清单)
status: Active
created: 2026-05-20
purpose: 归档 PM 多轮 chat 累积的 pending 决策项 + 主控/agent 实证发现, PM 一次性拍板, 不让对话散乱
---

# Pending Questions (2026-05-20)

> 主控按宪法 7 不下设计结论, 只列 (1) PM 原话引用 / (2) 主控/agent 实证发现 / (3) 候选方向。PM 拍板后, 各条迁到对应 spec 的 design 阶段或 round 反馈。
>
> 所有 `file:line` 引用均已 grep verify (2026-05-19/2026-05-20).

---

## §1. Engine v2.1 真相 vs Baseline 文档脱节 — 重大背景

**实证 (2026-05-19)**: `docs/engine/` 三份 baseline 文档跟 engine v2.1 代码完全脱节, 用 schema 2.0 旧概念 (SKILL.md 根入口) 描述, 实际 v2.1 用 GRAPH.md 根 + phases/<id>/{LOGIC,SUBGRAPH,SKILL}.md (`packages/graph-agent/src/graph_agent/core/loader.py:1` + `loader.py:264` reject schema 2.0 root SKILL.md).

**PM 2026-05-20 明示**: 忽略 `workspaces/default/skills/` 下所有 skill (story-deconstruction / text-segmentation / batch-analysis 等), 这些是**待标准化**的 schema 2.0 残留, **不是** v2.1 真相参考。**v2.1 真相 source 只有**: fixture (`packages/graph-agent/tests/fixtures/{subagent_minimal,fake_canvas_fanout,canvas_serializer,v21_assembly}/`) + 源码 (`loader.py` / `manifest.py` / `parser.py`).

**a2/a3 前期任务多次违反这条**:
- a2 round 1 §0 引用 `story-deconstruction/SKILL.md:11` + `text-segmentation 老版本` + `adaptation_v1_sandbox/...` 作 "v2.1 真相 verify" — 全是 schema 2.0
- a3 inventory §0/§1/§2 引用 `workspaces/default/skills/text-segmentation/phases/*/{LOGIC,SKILL}.md` 作 "真生产 v2.1 skill" — 是待标准化 corpus, 不算

---

## §2. Engine v2.1 标签命名 cutover (a3 inventory 推荐)

### Q2.1 `<python_callable>` → `<action>` ?

**a3 实证**: `loader.py:1024` allowed 列表里是 `python_callable`, 但 engine 内部已用 `ActionDef` / `ActionRegistry` / `_load_action_dir` (`loader.py:24,302,492,501-504`) 全是 `action` 术语。phase 目录也叫 `actions/`. **标签名跟内部对齐有割裂**.

**PM 上轮明示**: "这个标签命名非常奇怪, 改成 action; 需要更新 engine 文档."

**主控 verify**: 改名影响 = parser.py regex / loader.py:1024 allowed / manifest.py:73 字段 / 全部 fixture LOGIC.md / SKILL_AUTHORING_GUIDE.md 文档 / 任何 production v2.1 skill (目前**零个 production 真用 LOGIC.md mode, 只有 fixture 用**, 影响面有限).

**PM 拍板 (待)**: 改名 scope?
- A. 只改 `<python_callable>` → `<action>`
- B. + `<sub_skill_ref>` → `<subgraph_ref>` (a3 推荐)
- C. + 修 `<role>` dead tag (从 allowed 删 OR 在 SkillNodeAST 加字段消费)
- D. + 让 GRAPH.md `depends_on=""` 真 optional (a3 §6 提)
- E. 全改

### Q2.2 `<sub_skill_ref>` 在 SUBGRAPH.md 真有产代码用过吗?

**a3 实证**: 4 套 v2.1 fixture (`subagent_minimal` / `fake_canvas_fanout` / `canvas_serializer/with_comments_v21` / `v21_assembly`) **没一个用 `mode: subgraph`**. `SUBGRAPH.md` 路径在 `loader.py:48` 注册了, `SubgraphNodeAST` 在 manifest 定义了, body 标签在 allowed 列表了, 但**仓内零真实例子**.

**PM 拍板 (待)**: 派 a1 全仓库再 grep `mode: subgraph` 看是否漏判, 还是直接接受"mode:subgraph 是 schema 写好但还没用"?

### Q2.3 `<role>` body tag 是否 99% dead?

**a3 实证**: `loader.py:1024` 把 `role` 纳入 allowed, 但 `manifest.py:83-90` `SkillNodeAST` 没有 `role` 字段消费它, 写了进 `raw_blocks` 没人读. 引擎自己在 `cognitive/prompt.py:77` 注入硬编码 `<role>` wrapper, **跟用户的 body `<role>` 不是同一个**.

**PM 拍板 (待)**: 派 a1 全仓 grep `raw_blocks["role"]` / `.role\b` verify 是否真 dead?

---

## §3. Context Mapping 双模设计 — 重大事实暴露

### Q3.1 PM 跟 Gemini 历史对齐"自动推断", v2.1 实现是手动声明式

**PM 原话 (2026-05-19)**:
> "Q3. 需要 Gemini 好好设计一下这里的机制, 手动和自动推断都要, 文档都落在下游主文档里的 context mapping 标签吗? 还是说自动推断成立的话就不用落文档了?"

**a2 round 1 verify (有部分错)**: `ContextResolver` (`packages/graph-agent/src/graph_agent/io/context_resolver.py:1-10`) 现仅支持 3 种表达式: `{dot.path}` / quoted literal / plain string — **纯手动声明式, 没自动推断**.

### Q3.2 **更大的实证发现 (2026-05-20)**: v2.1 production 路径完全不走 `GraphAgentHarness`

**主控 grep 实证**:
- `harness.py:357-365` `__init__` 参数 `context_mapping: dict[str, str] | None = None`
- `harness.py:850` `_ensure_io_manager()` instantiate `ContextResolver(mapping=self._context_mapping, ...)`
- **但是**: 全 production 路径 grep `GraphAgentHarness(` **只 2 处**, 都在 docstring 例子 (`harness.py:352` + `callbacks/tracing.py:9`), **没有 production code instantiate**
- `_run_skill_dict` (`runner.py:227, 460-468`) 走 `compile_skill + assemble_graph`, **不 instantiate harness**
- `load_workflow_from_md` (`loader.py:211, 228`) 同样走 compile + assemble, 不走 harness
- `compile_skill` 和 `assemble_graph` 内部 grep `context_mapping` **全空**

**结论**: `context_mapping` 参数 + `ContextResolver` 类 + `harness.py:850` instantiate = **v2.1 dead code, 没人填没人读**.

- `manifest.py` GraphManifest / LogicNodeAST / SubgraphNodeAST / SkillNodeAST **都没有 `context_mapping` 字段** (a3 inventory §4)
- 唯一可能激活路径: schema 2.0 root SKILL.md 走 GraphAgentHarness fallback, 但 `loader.py:264` 已显式 reject schema 2.0 root → 完全堵死
- schema 2.0 builtin `md-patch/SKILL.md` 不走 GraphAgentHarness, 走独立 `cognitive/md_patch.py` `LLMMdPatchClient`

**a2 round 1 §0 "ContextResolver 还在跑" 是误判** — a2 看到 instantiate code 在, 没 trace 到 v2.1 production 不走这条路径.

### Q3.3 PM 拍板 (待) — 设计的起点是哪?

**a2 round 1 是基于错的前提设计的, 不能直接用. 重新 design 起点 3 选 1**:

- **A. 从零设计 context_mapping 双模 (engine 没现成可用)**
  - harness.py 那段 + context_resolver.py 当 dead code 留/删
  - 在 v2.1 真路径 (`compile_skill + assemble_graph`) 新建 context_mapping 机制
  - PM 历史跟 Gemini 对齐的"自动推断" + 你 2026-05-19 加的"手动也要"都从零落地

- **B. 把 `GraphAgentHarness` + `ContextResolver` 重新拉回 v2.1 主路径** 
  - 相当于 revive 老 code, 但跟 "v2.1 cutover 已完成" 矛盾
  - 不推荐 (但你定)

- **C. 把 `ContextResolver` 概念**直接搬到 `compile_skill + assemble_graph` v2.1 真路径里, harness.py 那段废弃
  - 复用现有 expression engine 实现 (`{dot.path}` / literal / plain), 加自动推断
  - 是 A + B 的折中

### Q3.4 a2 round 1 的 Q3.1-3.4 推荐 (部分仍有效, 部分基于幻觉)

**有效部分**:
- **Q3.2 推断条件**: 同名 wire + depends_on 唯一时上游全部 → 下游全部 ✅ 合理
- **Q3.3 折中**: 推断成立不强制写 + 显式声明优先 + GUI 干预 (rename / JSON path) 才回写显式 XML ✅ 合理
- **Q3.4 spec 归宿**: 扩 `canvas-micro-topology-v1/requirement.md` 新增 `Edge Data Flow & Context Resolution` 章节 ✅ 合理

**有 hallucination 部分**:
- **Q3.1 语法归宿**: a2 推 "B `<context_mapping>` 标签 OR 收敛到 `<inputs><input source target/></inputs>`" — **后者 v2.1 完全没有, grep engine core + fixture 全空, 是 a2 凭印象自由发挥**. 你 2026-05-19 之前提的"`<context_mapping/>` 标签放下游 input"是合理候选, 但语法的最终形态需要 PM 拍 (新建标签 / 加 frontmatter 字段 / 加 `<phase>` 属性).

### Q3.5 a2 自己提的术语疑问

> "context_mapping 是 yaml 时代术语, 跟如今 XML 化的 phase body 风格不太搭. 是否正式 deprecate 重命名为 I/O Mapper?"

**PM 拍板 (待)**: 维持 `context_mapping` / 改名 `<io_mapping>` 或 `<edge_mapping>` 之类?

---

## §4. Copilot Context Design — 待决策点

### Q4.1 Studio 用 Claude Code preset 还是自写 system prompt?

**a3 调研结果 (2026-05-19)** (报告 `/tmp/a3-claude-code-system-prompt-leak-research.md`):
- 找到 7 个 leak source (L1 `asgeirtj/system_prompts_leaks` + L2 `Piebald-AI/claude-code-system-prompts` 是 GitHub raw repo, High 可信)
- preset = Anthropic 维护的 Claude Code 默认 prompt (bundled CLI `_bundled/claude` 版本 2.1.138)
- 整理出 17 段模板 (11 段 A 高可信 + 6 段 B/C 中低)
- 隐藏模块 C 低可信: KAIROS (持久后台 daemon + autoDream) / Undercover Mode (non-allowlist repo 注入 "never mention you are AI" + strip Co-Authored-By) / BUDDY / Anti-distillation mechanisms

**3 个候选方向**:

| 方向 | 好处 | 风险 |
|---|---|---|
| **A. 用 preset (`{type:"preset", preset:"claude_code"}`)** | Anthropic 维护 / 14+ 版本微调自动跟 / 内置 best practice / safety 边界完整 / memory system 已对接 | preset CLI 假设嵌入太深 (8 条冲突跟 Studio GUI 工作流, "users can't see tool calls" / git CLI / gh CLI / memory 路径硬编码 / 隐藏模块 KAIROS/Undercover 不可控) |
| **B. 完全自写 (裸 str 或文件)** | Studio GUI 上下文显式声明 / Studio-specific 行为可定制 / 完全可审计无隐藏模块 / 叠加 KV 14 条规律 | 没 Anthropic alignment 红利 (refuse 自己写自己测) / 跨版本维护成本 / 模型 prior 漂移风险 |
| **C. 混合 (preset + append)** | 技术 OK, 大部分 CLI 行为复用 + append 写 Studio overlay (例 "你在 GUI, 用户能看到工具调用") | 不能删 preset 旧指令, LLM 在两条冲突间犹豫; 不能 override 隐藏模块 |

**PM 拍板 (待)**: A / B / C / 派 a2 部分 2 出完整方案?

### Q4.2 Claude SDK 文档落盘 PR

`docs/claude-agent-sdk-reference` branch 已 push commit `b97f142` (a1 写, 654 行, 10 章节), 待 PM 拍 `gh pr create` 时机.

### Q4.3 Copilot mention 方案 — 已拍板 tiptap (2026-05-20)

a2 报告推荐 tiptap + cmdk (shadcn 自带) + react-window 虚拟列表三件套. PM 决策 2 项 (a2 §6):

- 接受 tiptap ~100KB bundle (Tauri 桌面端可忽略)? **PM 已拍接受**
- 严格 schema 过滤所有富文本格式 (加粗/斜体/图片), 只留 Text + Mention Node? **PM 拍板 (待)** — a2 自己建议必须过滤

### Q4.4 SDK 粘贴图片接入

**主控 verify**: SDK 支持 `ImageContent(type="image", data=<base64>, mimeType=<image/png>)` (`__init__.py:473-479`). "从剪贴板抓图"是前端 Tauri 责任, SDK 只接 already-prepared bytes.

**PM 拍板 (待)**: 是否纳入 copilot-context-design spec 的 In Scope?

---

## §5. UX / Layout 决策 (上轮 audit 的 3 真 High, PM 已细化但未确认)

### Q5.1 High-004 新建 Skill 谁建骨架 — PM 已拍 B (后端 API)

**PM 已拍** (2026-05-19): **后端 API 写盘** (`POST /api/skills/init` 之类), 不是前端 Tauri fs.

**PM 细化** (2026-05-19 + 2026-05-20):
- "新建 skill 是创建一个**新目录**, 不是选空目录"
- "弹**OS fs 路径选择对话框** (选父目录 + 输入子目录名**合并一个 dialog**)"
- "需要一个**软件默认存数据路径**, 一个 skill 文件夹作为默认 (PM 修正 2026-05-20: **不用** `agent-harness-skill`, 用 `skill` 或 `graph-skill`)"
- 骨架 v2.1 真相: **`GRAPH.md` (大写)** 而**不是 SKILL.md** (因为 PM 上轮把这个 audit 描述基于错的 v2.0 SKILL.md 主入口讨论, 实际 v2.1 是 GRAPH.md)

**PM 拍板 (待)**: 骨架内容细化 — GRAPH.md + 哪些子目录 (按 v2.1: `phases/` + 可选 `actions/` + 可选 `io/inputs.json` + `io/outputs.json` + 可选 `.workspace/`)? 默认 root 路径具体名?

### Q5.2 High-003 点连线**圆点** (不是连线) 后展示什么

**PM 修正** (2026-05-19): 不是点连线本身, 是**点连线中间的圆点**.

**PM 已拍** (2026-05-19): **复用属性面板** (Studio Properties 切换显示, 不开新 Panel), 内容**全换掉**显示 context dict 切片.

**实证**: a2 round 1 提议看 mapped dict (DataMapper 进 phase 前抠出来的那份 dict). 但 §3 实证显示 v2.1 没有 DataMapper / ContextResolver 在 production 跑, 所以"点圆点看什么"得跟 §3 设计同步.

**PM 拍板 (待)**: 圆点 inspector 的 data 来源 = (取决于 §3 设计的 context_mapping 双模落地后产出什么).

### Q5.3 High-002 Copilot @ 引用接 backend 参数

**PM 细化** (2026-05-19):
> "首先交互不单单是主动写 @ 选择对象, 点击画布上可选择的组件 copilot 对话框自动出现 @ 对象 (被动模式). @ 对象用标签包裹插入对话框 (学 cursor 的 chip style). 至于 copilot 能否接到参数需要具体设计."

**a3 调研 + PM 拍板 mention = tiptap** (§4.3 已定).

**主控 verify**: copilot-context-design `requirements.md` User Story 1 + 2 + Acceptance Criteria 实际**已覆盖**主动 + 被动两种模式 + chip 风格 (research §1.1 已写 "UI Pill 胶囊" Cursor 风格). a2 上轮 audit High-002 报"缺口"是 a2 没读自己写的 spec, 是 **audit 质量问题, 非真缺口**.

**PM 拍板 (待)**: copilot-context-design 解锁 design.md 阶段? (按 INDEX.md, baseline 只允许 requirement + research, design.md 需 PM 解锁)

---

## §6. PR 待 PM 拍板

| PR / Branch | 内容 | 拍板项 |
|---|---|---|
| **PR #80** `refactor/split-frontend-large-files` | Task #25 拆 3 大前端文件 (Panels 530 / SettingsPage 1017 / GraphCanvas 632) commit `63570ae`, typecheck + 104 tests pass | merge 时机? |
| **PR #81** `docs/baseline-audit-2026-05-19` | Task #34 a2 audit 13 份 baseline (commit `801ec9e`) — **上轮你提示 audit 基础错要重做** | A. close 重做 / B. 保留只取 3 真 High 做 follow-up |
| `docs/claude-agent-sdk-reference` (待 create PR) | Task #35 a1 SDK 文档 (commit `b97f142`, 654 行) | 你说 create PR 我就 `gh pr create` |

---

## §7. 待派任务 (你拍板后我派)

| Task | 给谁 | 触发条件 |
|---|---|---|
| **#38 round 2** context_mapping 双模设计 | a2 (你跟 a2 直接对话, 我传话) | §3.3 你拍设计起点 (A/B/C) 后 |
| **#39** engine 标签命名 cutover 实施 | a1 (实施) + a2 (验收) | §2 你拍 cutover scope 后 |
| **#41** Studio Copilot system prompt 设计 (基于 a3 调研) | a2 | §4.1 你拍 A/B/C 后 (或先派 a2 出完整方案) |
| **engine baseline 文档 v2.1 cutover** (`docs/engine/*` 3 份过期 + `packages/graph-agent/README.md`) | a2 主笔 + 主控落盘 | §1 关联, 你说何时做 |
| **a3 inventory §7 5 条 follow-up** (sub_skill_ref 产代码 / role dead / `$func()` / md-patch 路径 / metadata.legacy_type 清理) | a1 verify | 你说要不要做 |

---

## 主控注: 关于"现在做到哪一个文档了"

这一轮主线**没有在迭代某份单一文档**, 而是在 **alignment phase** (按 SOP-02 §2): 把 5 月 19-20 累积的设计 / 实证 / 验证问题归 sort 出来, 等 PM 拍板后才能进 implementation phase (各 spec 解锁 design.md). 本文档 (`pending-questions-2026-05-20.md`) 就是这次 alignment 的归档.
