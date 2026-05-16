# graph_agent V2.1 升级 — Requirements

**Spec**: graph-agent-v2.1
**Status**: Requirements (Kiro Step 2)
**Date**: 2026-05-15
**Author**: a2 (Gemini, 委托 PM Claude)
**Related**: research.md (Step 1)

## R0. 不可妥协的前置决策 (User 2026-05-15 verbatim)

> 1.暂定;
> 2.先keep pending, 等改完engine再说;
> 3.直接一刀硬切, 不要向后兼容;

- **解读 1**: `studio-frontend-v2` 研发挂起，本 spec 的输出必须彻底冻结 V2.1 Schema 前端交互协议格式，作为恢复开发的前置契约。
- **解读 2**: `skills/_v2_pending/` 目录从本次升级的技能重构范围中剥离，专注现役 10 个业务强相关技能的迁移。
- **解读 3**: 解析层与图加载层不保留向下兼容分支（如 `schema_version: "2.0"` 单文件模式），现役 in-scope 11 份文件全数阻断 (filesystem 实证 20 份 SKILL.md = in-scope 11 + 历史归档 4 + _v2_pending 5; 详 research.md §2.2)，一次性切至 V2.1 格式。

> **PM Amendment #11 (2026-05-16)** — 旧 "17 份" 数字已 superseded by filesystem 实证 "20 份 = in-scope 11 + 历史 4 + pending 5" (research.md §2.2)。requirements R0/R3/R4/R5 全部统一引用 "in-scope 11 份" 表述; research §5.2 (改造清单) + §6 R-6 风险范围已同步修正。

## R1. 功能需求 (Functional Requirements)

**R1.1: 三层范式 (YAML/XML/JSON Schema) 强制分离**
- 系统**必须**按解耦规则解析文档：YAML frontmatter 仅含引擎配置；`phases/*/` 下 XML body 仅含 phase 内部业务意图 (prompts), **整图宏观拓扑 (`depends_on`) 独立转移到根 `GRAPH.md`**；IO 契约独立为 `io/inputs.json` 和 `outputs.json`。
- 验收: 将带 Prompt 的全 YAML Schema 交给编译器，须报 FATAL 拒绝；`hello-world` V2.1 技能能够顺利通过解析和 IO 校验。
- 依赖: 无。

**R1.2: 根 `GRAPH.md` + 同构 `phases/*/` 目录设计 (四种物理文件 = 四种角色)**
- 技能结构**必须**按以下物理布局组织, 四类文件 = 四类角色, 完全同构无歧义:
  - `<skill_root>/GRAPH.md` — graph manifest (depends_on 拓扑 / IO 契约 reference / 全局 metadata), **不是** phase 节点
  - `<skill_root>/io/inputs.json` + `outputs.json` — IO Schema 独立契约 (R1.1)
  - `<skill_root>/phases/<phase_name>/LOGIC.md` — Python 确定性单 phase 节点
  - `<skill_root>/phases/<phase_name>/SUBGRAPH.md` — 子图委派单 phase 节点
  - `<skill_root>/phases/<phase_name>/SKILL.md` — LLM ReAct skill 单 phase 节点
- 验收:
  1. 提供无 `GRAPH.md` 或无 `phases/` 目录结构的单体老技能, 须在加载阶段直接抛错拦截
  2. 根目录出现 `SKILL.md` (历史 schema 2.0 单文件残留) → 编译期 FATAL, **不保留兼容路径** (user 决策 3 一刀硬切)
  3. `phases/*/` 下出现 `GRAPH.md` → 编译期 FATAL (manifest 不允许嵌套在 phase 内)
- 依赖: R1.1。

**R1.3: LOGIC/SUBGRAPH/SKILL 三类节点声明分离 + GRAPH.md 不参与 AST 构建**
- 框架**必须**根据 phase 节点声明（`LOGIC.md` / `SUBGRAPH.md` / `SKILL.md`）采用不同的 AST 节点构建策略，严格执行单一节点纯度；**`GRAPH.md` 仅承载拓扑 (`depends_on`) + 全局元数据 + IO 契约 reference, 不参与 AST 节点构建**。
- 验收 (节点纯度三类全测 FATAL):
  1. `LOGIC.md` 中添加 `<system_prompt>` → 编译期 FATAL (LOGIC 不许 LLM Prompt)
  2. `SKILL.md` 中注入 `<python_callable>` 或 Python 副作用块 → 编译期 FATAL (SKILL 不许确定性 Python)
  3. `SUBGRAPH.md` 中添加 `<role>` 或 `<system_prompt>` → 编译期 FATAL (SUBGRAPH 仅委派, 不许内联 Prompt)
- 依赖: R1.2。

**R1.4: `<exit_contract>` 强制退出防死循环**
- 解析器**必须**提取 `<exit_contract>` 标签内容; 认知中间件每轮 ReAct 时**在 `messages` 列表末尾追加一条独立 User Message**, 内容含 `<exit_contract>` 全文, 跟 System Prompt 物理隔离 — 利用 LLM recency bias 把退出条件钉在 attention 最高位置, 实现 per-turn 提醒。
- 验收 (机器化可测):
  1. 断言每轮 ReAct 发往 LLM 的 `messages` 列表中**最后一条**为 `role=user` 且其文本末端**确切包含** `<exit_contract>` 标签内全文
  2. 长 Prompt 场景 (System Prompt > 4000 tokens) 跑 e2e, 不应再触发 `W-FINISH-TASK-VISIBILITY` 告警
- 依赖: R1.1。

**R1.5: Tools vs Logic Actions 权限物理隔离**
- 框架**必须**引入 Logic Action 概念和对应的 `phases/*/actions/*.py` 加载机制, 后者享有**全局黑板 (context) 读写权限**; Tool 机制保留, 通过 LangChain `StructuredTool` 的 type-hint binding **天然 tunnel vision** (函数签名只暴露 LLM 传参字段, 不接 context 参数)。
- 验收 (静态 + 运行双轨, 注: 现役 Tools 已天然合规, V2.1 enforce 为永久规则):
  1. `actions/*.py` 内代码能成功 import 全局 context 门面并读写黑板状态 (e2e 测试覆盖)
  2. 编译期对 `tools/*.py` 做静态扫描, 任何 Tool 函数签名出现 `context` / `ctx` / `state` / `blackboard` 等参数 → 编译期 FATAL (LangChain StructuredTool type-hint binding 天然隔离的 enforce 化)
- 依赖: R1.3。

**R1.6: Actor-Critic 机制 Tool 化**
- Review / Auditing 等子代理交互**必须**作为 ReAct 循环内的 Tool 被调用，而非增加状态机级别的复杂环回边。
- 验收: 子代理 Critic 不应出现在图的宏观拓扑 `depends_on` 中；应通过 Tool 观测指标证明其在一个 phase 内完成调用。
- 依赖: R1.5。

**R1.7: md2json 中间件格式兜底**
- 认知层**必须**引入中间件，自动将 LLM 返回的 Markdown 解析转换为内部所需的 Python Dict / JSON，并在异常时静默唤醒 `md-patch` 代理进行修复。
- 验收: 强制返回残缺或多余标记的 Markdown 格式，系统应不报错，自动拉起 md-patch Agent 后修复成功。
- 依赖: 无。

## R2. 非功能需求 (NFR)

- **R2.1**: 性能 —— 编译器解析多目录 V2.1 技能并装配为 LangGraph AST 的耗时相比 Schema 2.0 单文件应增加不超过 200ms。
- **R2.2**: 可测试性 —— `core/loader.py` 及 `core/parser.py` 的改造必须配有多目录扫描与文件挂载的端到端集成测试基线。
- **R2.3**: 可观测性 —— 新的 XML+YAML 双体解析错误或 IO Schema 验证失败，必须抛出含有具体文档名、行号（`file:line`）定位锚点的高清晰错误日志。
- **R2.4**: 文档完整 —— `SKILL_AUTHORING_GUIDE` (必须新增 "如何编写 GRAPH.md" 专章, 严格界定全局拓扑编排与 phase 内业务 Prompt 的物理鸿沟) / `TOOL_DEVELOPMENT_GUIDE` (Tools vs Actions 边界) / `ARCHITECTURE` (V2.1 四角色 + 6 红线映射) 必须在设计交付前完成全面重写。
- **R2.5**: 互操作性 —— V2.1 三类 AST Pydantic model (LOGIC/SUBGRAPH/SKILL) 必须暴露并稳定支持 `.model_json_schema()` export, 输出符合 `studio-frontend-v2` 配置表单消费的 JSON Schema (Q-4 决议落地)。Schema 字段、required、discriminator 在 V2.1 内**不再变动**, 前端 contract 锁死。

## R3. 范围声明 (In-Scope vs Out-of-Scope)

| 内容 | 范围 | 备注 |
|---|---|---|
| graph_agent 内核 V2.1 改造 | In | 编译器 / runtime / Schema 校验 / 认知中间件 / Action 加载 |
| 现役 in-scope 11 份 SKILL 重构 (实证 20 份 SKILL.md: in-scope 11 + 历史 4 + pending 5; 老 schema 2.0 单 SKILL.md **拆解**为 `GRAPH.md` + `phases/*/(LOGIC\|SUBGRAPH\|SKILL).md` + `io/*.json`) | In (按 R-6 优先级排) | 高频先迁, 不是单文件翻新 |
| `skills/_v2_pending/` 迁移 | **Out** (user 决策 2: 维持 pending, engine 完工后再决定) | 跟 graph-agent-v2.1 不同期 |
| studio-frontend-v2 适配 | **Out** (user 决策 1: 暂停, V2.1 定后再启) | 单独 spec |
| graph-agent-studio 对接调整 | In (轻量, 只调接口签名) | 跟 V2.1 同步 |
| **studio-canvas-v1 deferred schema 演进** (`depends_on` Optional→Required 结构性突变) | **In** (V2.1 承接) | canvas-v1 design.md:36 推迟到独立 spec, R0 决策 3 一刀硬切 = 承接 spec, 由 V2.1 GRAPH.md 落地 Required |
| V1 兼容路径 / 双轨制 | **Out** (user 决策 3: 一刀硬切) | 不维护 |

## R4. Open Questions → Resolved (User 2026-05-15 已拍板, design.md 无阻塞)

- **Q-1: XML Body 解析器选型**
  - 状态: **Resolved (User 2026-05-15 override Gemini 推荐)**
  - 决议: **正则 / 轻量级状态机的 "块级劫持 (Block-level Hijacking)"**, **不是 lxml 标准 XML 解析器**。
  - 用户原话 (verbatim 2026-05-15):
    > "我们的需求不是『建立一棵支持 XPath 深度查询的严格 DOM 树』, 我们的需求仅仅是『把一对标签 (如 `<role>...</role>`) 中间夹着的所有字符, 不论里面有多少个未转义的尖括号或乱七八糟的符号, 当做一整块 Raw String 提取出来』。"
  - 拒绝 lxml 的关键原因:
    1. lxml 见到 PM Prompt 里的自然语言尖括号 (e.g., "请判断 A < B 是否成立" / "输出 `<div>` 的 HTML") 会因找不到闭合标签**当场 XMLSyntaxError 崩溃**
    2. 强制 lxml 路径会逼出 **"转义地狱 (Escaping Hell)"** — PM 必须 `&lt;` 或 `<![CDATA[...]]>` 包字符串, 比 Schema 2.0 全 YAML 更反人类
    3. V2.1 的 XML 用途 = **物理边界 (Boundary Markers)**, 不是 DOM 树 — 不需要 XPath / XSchema / XSLT 这些 lxml 提供的能力
  - 对 design.md 的输入: 内核解析器走 "找 `<tag>...</tag>` 配对的非贪婪正则 + 跨段块抓取" 轻量级实现, **不引入 lxml 依赖**, **不做内部内容合法性校验**, 标签仅作 boundary。
- **Q-2: exit_contract 注入点及权重定义**
  - 状态: **Resolved (User 2026-05-15 confirmed Gemini 推荐)**
  - 决议: **独立 + 每轮 ReAct 复现 的最后一条 User Message**, 防遗忘权重最高。
  - 用户评价 (verbatim 2026-05-15): "这个战术极其高明! 比起把它拼在 System Prompt 开头, 把它作为每轮对话的最后一条强制插入给大模型, 防遗忘的权重最高。这完美落地了我们定义的 `<exit_contract>` 的架构思想。"
  - 对 design.md 的输入: 认知中间件每轮 ReAct 后**注入一条独立 User Message** 含 `<exit_contract>` 内容, 跟 System Prompt 物理隔离。
- **Q-3: 老技能强制改造期的人力投入**
  - 状态: **Resolved (User 2026-05-15 默认接受 Gemini 推荐, 未提出异议)**
  - 决议: **Codemod 脚本自动迁移基础 YAML + 人工审查复杂 Prompt**。
  - 对 design.md 的输入: design 阶段需输出 codemod 工具规格 (输入 schema 2.0 SKILL.md → 输出 V2.1 `phases/*/SKILL.md` 雏形 + `io/*.json` 雏形); 复杂 Prompt 拆分到 `<role>` `<system_prompt>` `<exit_contract>` 等 XML 段的工作交人工。
- **Q-4: 前端配置 JSON Schema 定义职责**
  - 状态: **Resolved (User 2026-05-15 confirmed Gemini 推荐)**
  - 决议: **graph-agent 框架基于 Pydantic 自动 export JSON Schema**, 前端只消费不维护。
  - 用户评价 (verbatim 2026-05-15): "这和我们今天确立的 `io/inputs.json` 契约体系是吻合的 (单点真实源)。"
  - 对 design.md 的输入: V2.1 三种节点 Pydantic models (LOGIC/SUBGRAPH/SKILL) 必须支持 `.model_json_schema()` export; export 出的 JSON Schema 作为 `studio-frontend-v2` 配置表单的唯一数据源。
- **Q-5: 现役 in-scope 11 份 SKILL 改造的优先级与停摆窗口**
  - 状态: **Resolved (User 2026-05-15 默认接受 Gemini 推荐, 未提出异议)**
  - 决议: **容忍 3-5 天停摆 + 高频先迁 (`text-segmentation` / `story-deconstruction`) → 冷门后排 (`product-manual`)**。
  - 对 design.md 的输入: 排期表必须列出 in-scope 11 份 skill 的优先级 (Tier 1 / Tier 2 / Tier 3), Tier 1 在 V2.1 内核冒烟通过的第 1 个工作日完成迁移。
- **Q-6: 新引擎开发模式**
  - 状态: **Resolved (User 2026-05-15 默认接受 Gemini 推荐, 未提出异议)**
  - 决议: **in-place 改造 `packages/graph-agent` + long-running feature branch `feat/graph-agent-v2.1` 并发推进**。
  - 对 design.md 的输入: 不新建 `graph-agent-v2.1` 独立包; 不改 `from graph_agent import ...` 导入路径; CI 在 feature branch 上跑 V2.1 e2e baseline, main 分支保持 schema 2.0 直到 cutover。
- **Q-7: 四种角色物理文件命名同构区分 (graph manifest + 三种 phase 节点)**
  - 状态: **Resolved (User 2026-05-15 enhanced Gemini 推荐 + 补 GRAPH.md 概念)**
  - 决议: **四种物理文件命名 + YAML `mode` 字段双重校验**, 四角色完全同构无歧义:
    - `<root>/GRAPH.md` — graph manifest (整图元数据 / 拓扑 / IO 契约 reference)
    - `<root>/phases/*/LOGIC.md` — Python 确定性 phase 节点
    - `<root>/phases/*/SUBGRAPH.md` — 子图委派 phase 节点
    - `<root>/phases/*/SKILL.md` — LLM ReAct skill phase 节点
  - 用户原话 (verbatim 2026-05-15): "但在我们最终的蓝图里, 我们做得更绝: 我们不仅用了 mode, 我们在物理文件命名上直接做到了 `LOGIC.md`、`SUBGRAPH.md`、`SKILL.md` 的同构区分, 彻底杜绝了解析路由的歧义。"
  - 用户补充 (2026-05-15): 根目录不能叫 `SKILL.md` (会跟 `phases/*/SKILL.md` 重名); 应该叫 `GRAPH.md`, 因为根表达的是"整图 manifest"不是一个 phase 节点。否则解析器要靠 path depth 才能 route, Q-7 同构区分**只贯彻一半**。
  - 对 design.md 的输入:
    1. 编译器**第一步按物理路径 + 文件名联合路由**:
       - 根 `GRAPH.md` → manifest parser (解析 depends_on / IO ref / metadata)
       - `phases/*/LOGIC.md` → LOGIC parser
       - `phases/*/SUBGRAPH.md` → SUBGRAPH parser
       - `phases/*/SKILL.md` → SKILL (LLM ReAct) parser
    2. YAML frontmatter 内 `mode` 字段作为**双重校验** — 文件名跟 mode 不一致 → 编译期 FATAL
    3. 杜绝歧义场景 (全数 FATAL):
       - 根 `SKILL.md` (历史 schema 2.0 残留)
       - `phases/*/GRAPH.md` (manifest 不允许嵌套)
       - `phases/*/SKILL.md` 但 frontmatter `mode: logic` (文件名跟 mode 矛盾)

## R5. 实施纪律 (Process Requirements)

- 一刀硬切**意味着** master 分支会有一个"V2.1 大爆破" PR 不会拆细 (不可能小步迭代, 因为内核 + in-scope 11 份 skill 必须同步切)。
- 但**可以**先开一条 long-running feature branch (e.g., `feat/graph-agent-v2.1`) 让内核改造 + skill 迁移并发推进, 全部跑通 e2e 再回 main。
- 一切 in-scope 改动**必须**走 Kiro spec → tasks.md → 一对应 PR 的链路, 不允许 ad-hoc 修 (避免补丁思维)。