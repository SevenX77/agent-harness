# Graph Agent V2.1 架构设计文档

**Schema 版本**: V2.1 (one-shot cutover from schema 2.0)
**Spec**: `.kiro/specs/graph-agent-v2.1/` (requirements / design / tasks)
**Founding axioms**: `CORE_ARCH_PRINCIPLES.md` (6 红线)

## 0. V2.1 是什么 / 不是什么

V2.1 是 graph_agent 的 schema 大版本升级 — 把 V1 Reset (schema 2.0) 时塞进单文件 SKILL.md 的所有内容按 **四角色物理文件命名 + YAML/XML/JSON Schema 三层范式分离** 拆开, 让大模型 prompt、整图拓扑、IO 契约、确定性 Python 逻辑各归各位。

V2.1 **不是**:

- **不是** schema 2.0 的兼容延伸 — 一刀硬切 (R0 决策 3, user 2026-05-15 verbatim "直接一刀硬切, 不要向后兼容"), 主分支没有双引擎路径, 旧根 `SKILL.md` 出现 → 编译期 FATAL 拦截, 无 fallback
- **不是** 新建一个 `graph-agent-v2.1` 独立包 — Q-6 决议: in-place 改造 `packages/graph-agent`, 不改 `from graph_agent import ...` 调用面, 走 long-running feature branch `feat/graph-agent-v2.1` 并发推进, 全跑通 e2e 后单 PR 回 main
- **不是** 给已有 Tool 加 context 隔离墙 — research §2.5 实证 Tool 路径已通过 LangChain `StructuredTool` type-hint binding 天然 tunnel vision; V2.1 真正新增的是 **Logic Action 概念** 跟 `phases/*/actions/*.py` 加载机制 (R1.5)
- **不是** 处理 `skills/_v2_pending/` 积压 (R0 决策 2: keep pending, V2.1 内核完工后再决定迁移路径)

V2.1 **范围内**: graph_agent 内核 (parser / loader / graph_builder / cognitive 中间件) + **in-scope 11 份** 现役 SKILL.md 一刀切迁移 (8 顶层 + 1 producer subskill + 2 examples fixture; 不含 4 份 versions/ 历史归档 + 5 份 \_v2\_pending/)。

## 1. 物理文件布局: 4 角色 4 文件名

skill 不再是单文件, 而是一个目录树, **四类物理文件名 = 四类角色** (Q-7 决议, requirements R1.2):

```
<skill_root>/
├── GRAPH.md                          # 角色 A: graph manifest (整图元数据 / 拓扑 / IO 契约 reference)
├── io/
│   ├── inputs.json                   # JSON Schema (运行时 input 契约)
│   └── outputs.json                  # JSON Schema (artifact / context 输出契约)
└── phases/
    ├── <phase_a>/
    │   ├── LOGIC.md                  # 角色 B: Python 确定性 phase 节点 (或 SUBGRAPH.md / SKILL.md, 三选一)
    │   ├── actions/
    │   │   └── *.py                  # 黑板读写专属脚本 (R1.5)
    │   └── tools/                    # 可选, phase-local tools
    │       └── *.py                  # LangChain StructuredTool, 天然 tunnel vision
    ├── <phase_b>/
    │   └── SUBGRAPH.md               # 角色 C: 子图委派 phase 节点
    └── <phase_c>/
        ├── SKILL.md                  # 角色 D: LLM ReAct phase 节点
        └── tools/*.py
```

**四角色职责** (绝不混用):

| 角色 | 物理文件 | 解析路径 | 干什么 | 不允许 |
|---|---|---|---|---|
| A. Graph Manifest | `<root>/GRAPH.md` | manifest parser | 整图元数据 (`name` / `description` / `version`) + IO 契约 reference (指向 `io/inputs.json` / `outputs.json`) + 拓扑 (`<phase id="..." depends_on="...">`) | 不写 prompt; 不参与 AST 节点构建; 不允许嵌套在 `phases/*/` |
| B. Logic Phase | `<root>/phases/<name>/LOGIC.md` | LOGIC parser | YAML frontmatter `mode: logic` + XML body 描述确定性 Python 流程 + 配对的 `actions/*.py` | 不允许 `<system_prompt>` / `<role>` / `<exit_contract>` 等 LLM-only 标签 |
| C. Subgraph Phase | `<root>/phases/<name>/SUBGRAPH.md` | SUBGRAPH parser | YAML frontmatter `mode: subgraph` + `<subgraph_target>` 指向另一个 skill 的 `GRAPH.md` + `<context_bridge>` 父子黑板桥接 | 不允许内联 `<system_prompt>` / `<role>` / `<python_callable>` |
| D. LLM ReAct Phase | `<root>/phases/<name>/SKILL.md` | SKILL parser | YAML frontmatter `mode: agent` (或别名 `llm`) + XML body 含 `<role>` / `<system_prompt>` / `<user_prompt>` / `<exit_contract>` | 不允许 `<python_callable>` 或确定性 Python 副作用块 |

**关键命名澄清**: 根 `GRAPH.md` **不是** 一个 phase 节点 — 它只承载 manifest, 不进入 AST 构建; phase 节点全部下沉到 `phases/<name>/` 子目录, 由 `LOGIC.md` / `SUBGRAPH.md` / `SKILL.md` 三选一。

## 2. 联合路由 (文件名 × YAML `mode` 双校验)

编译器**第一步按物理路径 + 文件名联合路由**到对应 parser (Q-7 决议):

```
路径 = <root>/GRAPH.md                       → manifest parser
路径 = <root>/phases/*/LOGIC.md              → LOGIC parser
路径 = <root>/phases/*/SUBGRAPH.md           → SUBGRAPH parser
路径 = <root>/phases/*/SKILL.md              → SKILL (LLM ReAct) parser
路径 = <root>/io/inputs.json | outputs.json  → JSON Schema 校验器
```

YAML frontmatter 内 `mode` 字段做**双重校验** — 文件名跟 mode 不一致直接 FATAL, 杜绝路由歧义:

| 文件名 | 合法 `mode` 值 | 不一致后果 |
|---|---|---|
| `LOGIC.md` | `logic` | `[F-v21-purity]` 文件名 ≠ mode |
| `SUBGRAPH.md` | `subgraph` | `[F-v21-purity]` 文件名 ≠ mode |
| `SKILL.md` (in phases/) | `agent` 或 `llm` | `[F-v21-purity]` 文件名 ≠ mode |

**编译期 FATAL 矩阵** (R1.2 / R1.3 验收):

| 违规场景 | 错误码 | 原因 |
|---|---|---|
| 根目录出现 `SKILL.md` | `[F-v21-graph]` | schema 2.0 残留, 一刀硬切不保留兼容路径 |
| `phases/*/GRAPH.md` | `[F-v21-graph]` | manifest 不允许嵌套在 phase 内 |
| 缺 `GRAPH.md` 但有 `phases/` | `[F-v21-graph]` | 没 manifest 无法构图 |
| 有 `GRAPH.md` 但缺 `phases/` 目录 | `[F-v21-graph]` | manifest 引用了不存在的 phase src |
| `LOGIC.md` 出现 `<system_prompt>` | `[F-v21-purity]` | Logic 节点不许 LLM Prompt |
| `SKILL.md` 出现 `<python_callable>` | `[F-v21-purity]` | LLM 节点不许确定性 Python |
| `SUBGRAPH.md` 出现 `<role>` 或 `<system_prompt>` | `[F-v21-purity]` | SUBGRAPH 仅委派, 不许内联 Prompt |
| `phases/*/{LOGIC,SUBGRAPH,SKILL}.md` XML body 内出现 `<phase>` / `<depends_on>` / `<edge>` 等整图拓扑标签 | `[F-v21-graph]` | 拓扑只能在根 `GRAPH.md`, phase 内不允许重述 |
| 文件名 `LOGIC.md` 但 frontmatter `mode: agent` | `[F-v21-purity]` | 联合路由双校验失败 |
| `io/inputs.json` 缺失 / 非法 JSON Schema | `[F-v21-io]` | IO 契约不健全 |
| `GRAPH.md` 引用了 `phases/<name>` 但目录不存在 | `[F-v21-graph]` | manifest 跟 filesystem 不一致 |

所有 FATAL 必须带 `file:line` 锚点 (R2.3)。

## 3. 六条不可违反的红线 (Axioms) 跟 V2.1 实现映射

详 `CORE_ARCH_PRINCIPLES.md`。这里给 V2.1 改造的具体落点:

### Axiom 1: Kitchen-Pass (Strict Separation of Concerns)

> Framework is the Kitchen; skills are the Recipes.

**V2.1 落点**:
- `packages/graph-agent/src/graph_agent/core/` 不允许出现任何业务 prompt 字符串 / 业务 schema 字段名 / 业务文件路径
- 反向 `skills/*/` 不允许 import `graph_agent.core.*` 内部模块或 monkey-patch LangGraph state
- T1.2 静态扫描会 enforce: `tools/*.py` 不能调 `graph_agent._internal_*` 私有 API

### Axiom 2: Document-Driven Orchestration (Docs as Code)

> The graph is built in Markdown/YAML, not in Python.

**V2.1 落点**:
- `<root>/GRAPH.md` 是 AST **单源真相** (Single Source of Truth)
- 不接受 `script/orchestrator.py` 类手写编排 — 所有跨 phase 编排必须落到 `GRAPH.md` 的 `<phase depends_on="...">` 拓扑里
- Studio 后端 `compile_skill` 收 V2.1 skill root 后, **第一动作** 是读 `GRAPH.md`, 不允许从代码侧推断拓扑 (T3.1)

### Axiom 3: Node Purity (One Brain Per Phase)

> A single phase has exactly one cognition model. Hybrid forbidden.

**V2.1 落点**:
- 物理文件名直接对应认知模型 (Logic / Subgraph / LLM ReAct), 编译期联合路由 + mode 双校验, **物理上无法混用**
- `phases/<name>/` 下三类文件名互斥 (一个 phase 目录最多有其中一个), 同时出现两个或以上 → `[F-v21-purity]` FATAL
- 节点纯度三类 FATAL 矩阵见 §2

### Axiom 4: Global Blackboard (Implicit State Transfer)

> Nodes communicate via globally shared dictionary (LangGraph State/Context).

**V2.1 落点**:
- LangGraph state object 在 V2.1 内**继续作为黑板**, 不引入显式 point-to-point 消息传递
- 下游 phase 读 `{raw_text}` 默认从 state 取, 上游 phase 写 `state["raw_text"] = ...`
- **唯一例外**: SUBGRAPH 节点边界 — 通过 `<context_bridge>` 显式声明父子 skill blackboard 之间的 key 映射 (作为 API gateway, 防止子 skill 污染父 blackboard)
- 不允许在 skill 内造"翻译层"或"mapping 节点"只为重命名 key

### Axiom 5: Deterministic Macro-Routing vs Autonomous Micro-Routing

> Framework dictates *what* happens next; LLM dictates *how* to solve the current step.

**V2.1 落点**:
- 整图拓扑 100% 由 `GRAPH.md` 的 `<phase depends_on="...">` 决定, **LLM 永远不允许选下一个 phase**
- LLM 自主性严格限制在**单个 SKILL phase 内部** — ReAct 可循环 / 思考 / 调工具, 但 `finish_task` 一调用控制权立刻回到引擎, 引擎按 `depends_on` 路由到下一个 phase
- **R1.6 Actor-Critic Tool 化** 是 Axiom 5 的直接推论: reviewer / critic / auditor 必须作为 ReAct 内 Tool 调用 (在 phase 内), 不允许作为 macro 拓扑里的独立 phase (那会让 LLM 间接决定流程)

### Axiom 6: Stateless Skills (Framework-Managed Persistence)

> Skills are side-effect free regarding local file persistence unless explicitly configured.

**V2.1 落点**:
- `phases/<name>/actions/*.py` 跟 `tools/*.py` **禁止** `open(..., 'w' | 'a')` / `Path.write_text` / `Path.write_bytes` / `Path.touch` (T1.2 静态扫描 enforce, 命中 → `[F-v21-stateless]` FATAL)
- 所有产出必须通过 `io/outputs.json` 声明 + 走框架的 `IOManager`/`StorageManager` 落盘 (caller 可通过 `artifact_saver=` 完全接管, 不破坏 Kitchen-Pass)
- 详细 enforcement 规则见 `TOOL_DEVELOPMENT_GUIDE.md`

## 4. LangGraph 装配链路 (manifest 拓扑 + 三类 AST 独立 builder)

### 4.1 编译流程

```
                            ┌──────────────────────────────┐
                            │  compile_skill(skill_root)   │
                            └──────────────┬───────────────┘
                                           │
              ┌────────────────┬───────────┼────────────────┬───────────────────┐
              ▼                ▼           ▼                ▼                   ▼
       GRAPH.md            io/inputs    io/outputs    phases/*/LOGIC.md   phases/*/SKILL.md
       Manifest             schema       schema       LOGIC parser        SKILL parser
       parser                                                              ↑
                                                                           │ (phases/*/SUBGRAPH.md
                                                                              SUBGRAPH parser)
              │                │            │              │                   │
              ▼                ▼            ▼              ▼                   ▼
        GraphManifest       JSONSchema   JSONSchema    LogicNodeAST       SkillNodeAST
        Pydantic model      validator    validator     Pydantic           Pydantic
              │                                          │                   │
              │                                          ▼                   ▼
              │                                    builder_logic.py     builder_skill.py
              │                                    (LangGraph add_node) (LangGraph add_node)
              │                                          │                   │
              └──────────────────┬───────────────────────┴───────────────────┘
                                 │
                                 ▼
                       langgraph.StateGraph
                       with depends_on edges
```

**三类 AST 独立 builder** (T0.5 + T1.5):
- `builder_logic.py`: LOGIC node → LangGraph `add_node` 注册 Python 函数 (从 `actions/*.py` import)
- `builder_subgraph.py`: SUBGRAPH node → LangGraph `add_node` 注册子图入口 (递归 `compile_skill` 子 skill root)
- `builder_skill.py`: SKILL node → LangGraph `add_node` 注册 LLM ReAct loop (含 exit_contract 注入)

不同 builder **独立**, 内核里没有 `if mode == 'logic' else if mode == 'subgraph'` 的混合分支 — 联合路由阶段已经按文件名分流。

### 4.2 拓扑装配 (depends_on)

`GRAPH.md` 的 `<phase>` 标签列表决定拓扑:

```xml
<phase id="prep">
<ref path="phases/prep/LOGIC.md" />
</phase>

<phase id="draft" depends_on="prep">
<ref path="phases/draft/SKILL.md" />
</phase>

<phase id="review" depends_on="draft">
<ref path="phases/review/SKILL.md" />
</phase>
```

**depends_on DSL 规则** (T0.3 PM 决策):
- 首个 `<phase>` 标签**可省略** `depends_on` 属性 → 隐式 entry
- 额外 entry 必须**显式**写 `depends_on=""` (空字符串) — 不写非空 = 不是 entry
- 非首个 phase 缺 `depends_on` 属性 → `[F-v21-graph]` FATAL
- 非起点 phase: `depends_on="a b c"` 或 `depends_on="a,b,c"` (空白/逗号分隔)
- 拓扑校验失败 (self-loop / 循环 / 孤儿 phase / 重复 id / src 缺失) → `[F-v21-graph]` FATAL

详 `SKILL_AUTHORING_GUIDE.md` §2 跟 §3。

### 4.3 AST 缓存 (R2.1 性能要求 + T1.5 实现)

- 基于 file mtime / stat 的增量缓存, 首次编译耗时 ≤ 200ms (相比 schema 2.0 单文件)
- 缓存失效条件: `GRAPH.md` / `phases/**` 任一文件变更 (mtime 比缓存新)
- 缓存 key = `(skill_root_abspath, GRAPH.md mtime, phases/** mtime tree hash)`

## 5. 认知中间件

### 5.1 `<exit_contract>` 强制注入 (R1.4 / Q-2)

V2.1 在每轮 ReAct 后, **在 LLM messages 列表末尾追加一条独立 User Message**, 内容含当前 SKILL phase 的 `<exit_contract>` 全文。

**为什么是 User Message 不是 System Prompt 开头**:
- LLM recency bias — 最后一条 message 在 attention 权重最高
- System Prompt 长 (>4000 tokens) 时 exit_contract 在中段会被遗忘, 触发 `W-FINISH-TASK-VISIBILITY` 告警
- 物理隔离 (跟 System Prompt 分开) → exit_contract 内容变化时不污染 system prompt 缓存

**机器化验收** (T1.1 DoD):
- 每轮 ReAct 发往 LLM 的 `messages` 列表中**最后一条** = `role=user` 且文本末端含 `<exit_contract>` 全文
- 长 Prompt e2e 不再触发 `W-FINISH-TASK-VISIBILITY`

### 5.2 `finish_task(markdown)` + md2json 兜底 (R1.7 / T1.4)

LLM 调 `finish_task` 时传 Markdown 字符串, 框架内部用 `tools/md_to_json.py` (research §2.7 已有) 解析为 dict。

**异常路径**:
- Markdown 残缺 (缺标题 / 不闭合代码块 / 字段类型偏差) → 静默拉起 `skills/builtin/md-patch/` agent 修复
- md-patch 修复失败 → 返回结构化错误 (含 `file:line` 锚点)

### 5.3 Actor-Critic Tool 化 (R1.6)

reviewer / auditor / critic 等子代理交互 **必须** 作为 ReAct 循环内 Tool 调用 (在某个 SKILL phase 内), **不允许** 作为 macro 拓扑里的独立 phase。

**理由** (Axiom 5 推论): 如果 critic 是独立 phase, 它的"通过/拒绝"等于让 LLM 间接决定下一个 phase, 违反 deterministic macro-routing。

**验收**: `GRAPH.md` 的 `<phase depends_on="...">` 列表内不允许出现 critic / reviewer / auditor 类名字。

## 6. Tools vs Logic Actions (R1.5)

V2.1 引入 **Logic Action** 概念, 跟 Tools 物理隔离:

| 维度 | Tools | Logic Actions |
|---|---|---|
| 物理位置 | `phases/<name>/tools/*.py` 或 `skill_root/tools/*.py` | `phases/<name>/actions/*.py` |
| 调用方 | LLM (在 SKILL phase ReAct 内) | LOGIC phase 节点 Python 流程 |
| Context 访问 | **不接 context 参数** — LangChain `StructuredTool` 走 type-hint binding, LLM 只看到业务 args | **享有全局黑板 (context) 读写权限** |
| 静态扫描 | 函数签名出现 `context` / `ctx` / `state` / `blackboard` → `[F-v21-purity]` FATAL | 必须通过框架提供的 `context` 门面读写 |
| Stateless | 同样禁止本地写盘 (`open('w')` / `Path.write_*`) | 同样禁止 |

详 `TOOL_DEVELOPMENT_GUIDE.md`。

## 7. 一刀硬切边界声明 (R0 决策 3)

V2.1 实施期间 **不维护双引擎**:

- 主分支 `feat/graph-agent-v2.1` 跑通 e2e 后单 PR 回 main, 同 PR 内**必须**包含 in-scope 11 份 skill 全数迁移完成 (Tier 1: `text-segmentation` / `story-deconstruction` 先迁, Tier 2: 中频, Tier 3: `hello-world` + fixtures, 详 tasks.md §4)
- 旧根 `SKILL.md` (schema 2.0) 在 V2.1 内核里 by design crash, **没有 fallback path**, 没有 deprecation warning, 没有 schema 自动升级 — Q-3 决议: codemod 脚本只做 **dry-run** 雏形 (T0.4), 复杂 prompt 拆分留人工
- in-scope 11 份停摆窗口容忍 3-5 天 (Q-5 决议), 高频 (`text-segmentation` / `story-deconstruction`) 优先恢复, 冷门 (`product-manual`) 排后
- 不破坏导入路径: `from graph_agent import compile_skill, run_skill` 在 V2.1 后仍可用 (Q-6 决议)

**cutover PR (T3.3)** 必含:
- e2e 全过 + 11 skill 全迁
- 旧根 `SKILL.md` 全数 FATAL 拦截证据
- dual-run shadow 比对脚本 (Tier 1 强制跑, 验证迁移前后语义等价)
- single skill rollback CI SOP
- 停摆公告 + 验收 checklist + rollback 操作书

## 8. 模块架构 (V2.1 `packages/graph-agent/src/graph_agent/`)

```
graph_agent/
├── core/
│   ├── parser.py             # XML 块级劫持 (Q-1 决议, 不用 lxml)
│   ├── loader.py             # 目录树扫描 + 联合路由
│   ├── manifest.py           # GRAPH.md → GraphManifest Pydantic
│   ├── ast/
│   │   ├── logic.py          # LogicNodeAST Pydantic + .model_json_schema()
│   │   ├── subgraph.py       # SubgraphNodeAST Pydantic
│   │   └── skill.py          # SkillNodeAST Pydantic
│   ├── graph_builder.py      # 装配 LangGraph (调用三类 builder)
│   ├── builder_logic.py      # LOGIC node builder
│   ├── builder_subgraph.py   # SUBGRAPH node builder
│   ├── builder_skill.py      # SKILL (LLM ReAct) node builder
│   └── validators/
│       └── purity.py         # 节点纯度校验 (XML body 内不许 <phase>/<depends_on>/<edge> 等)
├── io/
│   ├── schema.py             # io/inputs.json + outputs.json JSON Schema 校验
│   └── manager.py            # IOManager / StorageManager (Axiom 6)
├── cognitive/
│   ├── exit_contract.py      # R1.4 末尾 User Message 注入
│   ├── md_to_json.py         # R1.7 finish_task(markdown) 兜底
│   ├── md_patch_bridge.py    # 拉起 skills/builtin/md-patch
│   ├── context_facade.py     # actions/*.py 用的全局黑板门面
│   └── tunnel_vision.py      # tools/*.py 静态扫描 (R1.5)
├── actions/                  # 框架自带 builtin actions (跨 skill 通用)
├── tools/                    # 框架自带 builtin tools (跨 skill 通用)
└── runtime/
    ├── runner.py             # run_skill 入口
    └── checkpoint.py         # LangGraph checkpoint (run-level state)
```

**相比 V1 (schema 2.0) 的关键变化**:

| V1 模块 | V2.1 状态 | 原因 |
|---|---|---|
| `core/compiler.py` `schema_version == "2.0"` 强校验 | **删除** | R0 决策 3 一刀硬切 |
| `core/parser.py` 单文件 SKILL.md 解析 | **重写** | 改为目录树扫描 + 联合路由 (T0.1) |
| `core/loader.py` 扁平 phase 加载 | **重写** | 支持 `phases/*/` 多目录 (T0.1) |
| `cognitive/finish.py` 静态告警 | **保留 + 扩展** | 增加 `<exit_contract>` 注入逻辑 (T1.1) |
| `core/validators/prompt_quality.py` `W-FINISH-TASK-VISIBILITY` 告警 | **删除** | R1.4 主动注入解决 |
| `tools/md_to_json.py` 已存在 | **保留 + 集成** | 接入 `finish_task` 兜底链 (T1.4) |
| `core/skill_tool_factory.py` LangChain StructuredTool 工厂 | **保留** | 已天然 tunnel vision, 加 R1.5 静态扫描 |
| 无 `actions/*.py` 概念 | **新增** | Logic Action 加载机制 + context 门面 (T1.2) |

## 9. Studio 对接

### 9.1 后端 `compile_skill` / `run_skill` 接 V2.1 root (T3.1)

`apps/studio/backend/app/services/skills.py` 内 `from graph_agent import compile_skill` 调用面**不变**, 入参语义改:
- V1: `compile_skill(skill_md_path)` — 单文件路径
- V2.1: `compile_skill(skill_root_path)` — 目录路径 (含 `GRAPH.md` 跟 `phases/`)

backend preview 接口返回:
- GRAPH 拓扑 (从 manifest 提取)
- 三类节点 schema (`.model_json_schema()` export, Q-4 决议)
- IO schema (`io/inputs.json` + `outputs.json`)

### 9.2 canvas-v1 deferred work 承接 (T3.2)

studio-canvas-v1 design.md 把 "`depends_on` Optional→Required 结构性突变" 推迟到独立 spec (canvas-v1/design.md:36), V2.1 R0 决策 3 一刀硬切就是承接 spec — `GRAPH.md` 编译期 enforce 非起点 phase `depends_on` 必填, 旧 Optional 输入 → FATAL。

后端 schema / 导出 JSON Schema / 样例**全部** required, 不留 Optional 通道。

### 9.3 studio-frontend-v2 暂停 (R0 决策 1)

前端节点编排界面迭代挂起, 等 V2.1 三种节点 (LOGIC/SUBGRAPH/SKILL) 的前端 JSON 表达定稿 (Q-4 自动 export from Pydantic) 后再启动。

## 10. 参考资料

- `CORE_ARCH_PRINCIPLES.md` — 6 红线源文档 (Axiom 1-6)
- `SKILL_AUTHORING_GUIDE.md` — V2.1 GRAPH.md / phases/ 作者指南
- `TOOL_DEVELOPMENT_GUIDE.md` — Tools vs Actions 边界
- `.kiro/specs/graph-agent-v2.1/research.md` — 现状画像 + 立项动机
- `.kiro/specs/graph-agent-v2.1/requirements.md` — R0/R1/R2 全文 + Q-1..Q-7 决议
- `.kiro/specs/graph-agent-v2.1/tasks.md` — 25 tasks 工时 + DoD
- `studio-canvas-v1/design.md` — depends_on 单源真相承接 spec
- [LangGraph 文档](https://langchain-ai.github.io/langgraph/)
