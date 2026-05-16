# graph_agent V2.1 升级 — Research

**Spec**: graph-agent-v2.1
**Status**: Research (Kiro Step 1)
**Date**: 2026-05-15
**Author**: a2 (Gemini, 委托 PM Claude)

## 1. 背景与立项动机
graph_agent 演进经历了从早期的 V1 到 Schema 2.0 (即 V1 Reset) 的过程。Schema 2.0 试图修复早期的结构混乱，但矫枉过正地将所有业务 Prompt 塞入纯 YAML 文件中（如 `skills/_v2_pending/` 中的产物），彻底破坏了人类可读性与模块化，被新架构立宪 (`CORE_ARCH_PRINCIPLES.md`) 与 V2.1 提案定性为 **Anti-pattern**。
V2.1 旨在引入 YAML / XML / JSON Schema 三层解耦与多目录 (`phases/`) 的同构设计。

基于 User 指示，本次升级遵循以下 **3 个不妥协的决策**：
1. **studio-frontend-v2 暂停**: 前端节点编排界面迭代挂起，等待本 V2.1 中三种节点 (LOGIC/SUBGRAPH/SKILL) 的前端 JSON 表达完全定稿后再启动。
2. **`skills/_v2_pending/` 维持 pending**: V2.1 引擎改完前不动积压技能，改完后统一决策是废弃还是自动/手动迁移。
3. **一刀硬切，不向后兼容**: 实施期间不维护兼容旧 V1 范式的双引擎，所有老 Skill by design 触发 crash 阻断，等待同步重构。

## 2. 现状画像 (Deep Dive)

### 2.1 内核源码结构
- `packages/graph-agent/src/graph_agent/core/`: 核心解析与引擎 (如 `compiler.py`, `loader.py`, `parser.py`, `graph_builder.py`)。
- `packages/graph-agent/src/graph_agent/cognitive/`: 拦截器和认知逻辑 (如 `finish.py`, `clarification_middleware.py`)。
- `packages/graph-agent/src/graph_agent/tools/`: 基础工具链。
- `packages/graph-agent/src/graph_agent/io/`: 输入输出流和文件管理体系。

### 2.2 Schema 现状 (PM 2026-05-15 filesystem 实证修订)
- `find skills/ -name "SKILL.md"` 实证: **真实 20 份 SKILL.md 全是 `schema_version: "2.0"`** (V1 残留 = 0; V1 Reset / Schema 2.0 重构已全面落地)。round 1/2 引用的 "17 份" 是估算偏差, 真值见以下分类:
- **顶层现役独立 skill (8 个)**: `batch-analysis / event-extraction / global-synthesis / hello-world / producer / product-manual / story-deconstruction / text-segmentation` (注: `shared` 是 Python utility 模块 `skills/shared/{llm_utils.py, schemas.py}`, **不是 skill**; round 1 误列为 10 个内含 `shared`)。
- **producer 内嵌 subskill (1 个)**: `skills/producer/review/SKILL.md` (producer 工作流的 review 子阶段, V2.1 应内化为 phase)。
- **examples/ 测试 fixture (2 个)**: `skills/examples/broken-fixtures/story-deconstruction-inline-phase/SKILL.md` + `skills/examples/subgraph-sample/story-deconstruction/SKILL.md` (V2.1 编译器 e2e 测试 fixture, 一刀硬切必须同步迁移否则测试 break)。
- **text-segmentation/versions/ 历史归档 (4 个)**: `v0-main-baseline / v1-codex-attempt / v2-gemini-rewrite-r1 / v3-gemini-rewrite-r2` (V2 schema 迭代历史快照, 非现役 production skill, V2.1 迁移**不动**, 保持原状作历史 reference)。
- **_v2_pending 积压 (5 个)**: `adaptation_v1/SKILL.md` + 3 subskills (`beat_extractor / producer_strategy / writer_drafting`) + `story-deconstruction/SKILL.md` (user 决策 2: keep pending, V2.1 engine 完工后再决定迁移路径)。
- 编译器侧仍硬校验 `schema_version == "2.0"` (`core/compiler.py:178-188`), `callbacks/events.py:35` 提到 `1.0` 字符串是接口 enum 残留 mention, 不是 skill 文件。
- **V2.1 一刀切破坏面真相**: 20 份 = **In-scope 必迁 11 份** (8 顶层 + 1 producer subskill + 2 examples fixture) + **Historical 不动 4 份** (versions/) + **Out-of-scope 5 份** (_v2_pending/, keep pending)。R-6 风险范围 = 11 份 in-scope skill 即时停摆, 不是原估的 17 份。

### 2.3 编译器/解析器现状
- **解析入口**: `core/parser.py` 的 `parse_skill_file` 与 `core/loader.py:126` 高度耦合于单文件解析并显式检查 `schema_version == "2.0"` (校验在 `core/compiler.py:178-188`)。
- (注: round 1 引用的 `core/parser.py:187` 行号可能漂, 上面以函数名 / compiler.py 强校验位置为准, design.md 阶段需再精确定位。)
- 完全没有对 XML body 分开解析并分离业务逻辑的 `phases/` 多目录架构的代码支撑，依然沿用 V1 Reset 后的纯文件解析机制。

### 2.4 Runtime 现状 (LangGraph 集成)
- **节点注册**: `core/graph_builder.py:80` (`graph.add_node`) 表明底层已使用 LangGraph 构建 DAG，且内置了 `_make_llm_node`, `_make_validation_node` 等机制。
- 引擎基于内部编译时的 `phase list` 顺序装配图节点，不具备基于分离 `LOGIC`/`SUBGRAPH` 节点的动态目录加载能力。

### 2.5 Tools vs Logic Actions 权限边界现状 ⚠️ 重点
- **当前框架只有 Tools, 没有 Logic Action 概念** (这是结构性缺位, 不是 "混用违规")。
- **Tools 现状**: `core/skill_tool_factory.py:81-122` 通过 LangChain `StructuredTool.from_function` 工厂包装; `core/tool_wrapper.py:87-210` 提供 BaseTool/StructuredTool 包装链。LangChain StructuredTool 走 **type-hint binding** — 工具函数签名只暴露 LLM 传参字段, `grep "def.*context.*:" packages/graph-agent/src/graph_agent/tools/` 无结果 (天然 tunnel vision, 符合 V2.1 LLM Tool 隧道视野原则)。
- **Logic Action 现状**: `find skills/ -maxdepth 2 -type d -name "actions"` 0 命中 — `actions/*.py` 这套机制**从未诞生**, 当前所有逻辑都走 LLM Tool 路径。
- **V2.1 升级实际要做的**: 不是 "给已有 Tool 加隔离墙", 而是**新增 Logic Action 概念 + `actions/*.py` 加载机制 + 全局 context 读写门面** (Tools 路径基本不动)。

### 2.6 finish_task / exit_contract 现状
- **拦截器存在，但无契约注入**: `cognitive/finish.py:137` 显示确实有一套 `finish_task` 拦截工具，并且 `core/validators/prompt_quality.py:131` 会因为 `finish_task` 深埋于列表中而触发 `W-FINISH-TASK-VISIBILITY` 警告。
- 目前靠静态检测告警处理，缺乏 V2.1 规划的 `<exit_contract>` 强制顶/底注入最高权重提示词的主动防御机制。

### 2.7 md2json 中间件现状
- **存在且耦合深**: `tools/md_to_json.py:504` 显示 `md_to_json` 已具备解析与触发 `md_patch` (格式修复 Agent，见 `skills/builtin/md-patch/SKILL.md:2`) 的逻辑。
- LLM 目前已具备输出 Markdown 并让后端提拉成 JSON 的前置机制，但与图节点的交互不够解耦。

### 2.8 Studio 后端跟 graph_agent 耦合面
- `apps/studio/backend/app/services/skills.py:16` 调用 `from graph_agent import compile_skill` 进行文件转图编译。
- `apps/studio/backend/app/services/run_manager.py:223` 包含调用 `graph_agent.run_skill` 的子进程运行入口。
- HTTP 服务、静态解析与动态图执行都直接引用 `graph_agent.core.*` 进行通信。

## 3. V2.1 目标范式

1. **YAML/XML/JSON Schema 三层解耦**: 现状为未实现（纯单文件）。
2. **同构 phases/ 目录**: 现状为未实现（所有阶段扁平堆砌）。
3. **三种节点抽象 (LOGIC/SUBGRAPH/SKILL)**: 现状为未实现（全混杂在 Graph_Builder 中组装）。
4. **`<exit_contract>` XML**: 现状未实现，仅有告警（`prompt_quality.py:131`）。
5. **Tools vs Logic 权限隔离**: 现状未实现，边界模糊。
6. **Actor-Critic via tool**: 现状未实现，仍依赖拉新图节点退回。
7. **md2json**: 现状部分实现（已有 `tools/md_to_json.py` 及兜底代理）。

## 4. 现状 vs V2.1 差距

| V2.1 理念 | 现状描述 (file:line) | 差距程度 | 改造影响面 |
|---|---|---|---|
| 1. 三层范式 (YAML/XML/JSON) | 单文件, 依赖 schema 2.0 (core/compiler.py:178) | High | 内核解析器/校验器 |
| 2. 同构 phases/ 目录 | 扁平结构加载 (core/loader.py:126) | High | 编译器文件加载流 |
| 3. LOGIC/SUBGRAPH/SKILL 分离 | LangGraph 直接混合装配 (core/graph_builder.py:80) | High | 编译后抽象 AST 模型 |
| 4. `<exit_contract>` 标签 | 仅静态检测告警 (core/validators/prompt_quality.py:131) | Med | 认知中间件/Prompt注入 |
| 5. Tools/Actions 权限边界 | Tools 通过 LangChain StructuredTool 已天然 tunnel vision (`core/skill_tool_factory.py:81-122`); 但 **Logic Action 概念结构性缺位** (`skills/*/actions/` 0 命中) | Med | 新增 Action 加载机制 + 全局 context 门面 |
| 6. Actor-Critic tool 化 | Reviewer 目前依赖节点回退 | Med | Runtime / Tool 系统 |
| 7. md2json 中间件兜底 | 已有 md_to_json 拦截器 (tools/md_to_json.py:504) | Low | API 协议化迁移 |

## 5. 必做改动面

### 5.1 graph_agent 内核
- **编译器/解析器**: 重写 `core/parser.py` 和 `core/loader.py` 以支持目录树扫描与基于 Frontmatter / XML 体的分离提取。
- **Runtime/LangGraph**: 改造 `core/graph_builder.py` 支持三类阶段的区分路由；SUBGRAPH 的 DAG 发包，LOGIC 纯 Python 加载。
- **Schema 校验**: 重写 `core/manifest.py` 补充三层范式定义的 Pydantic 数据模型。
- **认知中间件**: 在 `cognitive/finish.py` 链条上游注入 `<exit_contract>` 高权重提示器。
- **Tools/Actions**: 重构工具加载框架，强行削减 Tools 获取全局 `context` 的接口，为 `actions/*.py` 单辟一套读写门面。

### 5.2 SKILL 库
- **现役 skills/ 全数改造清单**: 17 份 SKILL.md (全部 `schema_version: "2.0"`) 需重构为 V2.1 结构 (10 个现役 + 2 个 _v2_pending + 5 个 examples/* 待 verify), 工作量 L 级 (按 user 决策 3 硬切, 全数 break by design)。
- **_v2_pending/**: 遵照决策 2 维持不动，等待引擎完工。

### 5.3 测试 + CI
- **旧测试作废**: 凡是依赖于构建单文件 AST 的用例全废（如测试文件中对于单文件解析的断言）。
- **新增测试**: 对 `phases/` 目录挂载、子图调用及 XML/YAML 双体校验器补充单元测试。

### 5.4 docs
- **重写清单**: `SKILL_AUTHORING_GUIDE.md` (全改), `TOOL_DEVELOPMENT_GUIDE.md` (增加 Action 声明), `ARCHITECTURE.md` (同步节点分类)。

### 5.5 Studio 影响

| Spec | 关系 | 简述 + 证据 file:line |
|---|---|---|
| `studio-canvas-v1` | **V2.1 前置 + V2.1 承接 deferred** | (1) `studio-canvas-v1/design.md:29` P1-1: "manifest 的 depends_on 数组是画线的**唯一真相**, 不做任何隐式推导/fallback" → V2.1 GRAPH.md depends_on 同语义承接; (2) `design.md:30` P2-2: "I/O 节点是 depends_on **一等公民** (Output 反向声明 / Input 正向被引用, mirror 语义)" → V2.1 `io/inputs.json` + `outputs.json` 独立契约 + `io.depends_on` 反向声明同构; (3) `design.md:36`: canvas-v1 把 "`depends_on` Optional→Required 结构性突变" 推迟到独立 spec → **V2.1 R0 决策 3 一刀硬切 = 承接 spec**, GRAPH.md 编译期 enforce `depends_on` Required |
| `studio-frontend-v2` | **暂停** (user 决策 1) | 等 V2.1 三节点 (LOGIC/SUBGRAPH/SKILL) 的前端 JSON 表达定后再启 |
| `studio-llm-config-v2` | **无关** | Studio LLM API Key 管理 + `config/llm_roles.yaml` + Copilot 模型下拉的 spec, 不接触 graph_agent skill schema (verify: `.kiro/specs/studio-llm-config-v2/requirements.md:1-30`, 内容: SettingsPage 拆 API Keys/LLM Roles 两 Tab; 凭据存 `~/.studio/llm_credentials.json`) |
| `studio-skill-git-system` | **放大收益** | V2.1 `phases/` 多目录使 git diff 粒度更小, skill 历史回溯更清晰 |
| `studio-tunnel-safety` | **无关** | 底层通信安全, 不接触 skill schema |
| `studio-uikit-redesign` | **无关** | UIKit 视觉重设, 不接触 skill schema |
| `graph-agent-optimizations` | **可能被 V2.1 部分覆盖** | graph_agent 优化建议 spec — design.md 阶段需 read 该 spec verify 多少条已落进 V2.1 7 优化点 / 多少条是 V2.1 之外的优化点 |
| `graph-agent-studio` | **需对齐** | Studio 跟 graph_agent 对接层, V2.1 改 compile/runtime 接口后这 spec 跟着调 |
| `_deprecated_studio-copilot-providers-v3` | 已废弃 (参考) | 旧 LLM provider 设想 |
| `_deprecated_studio-api-keys-v1` / `_deprecated_studio-copilot-v1` | 已废弃 (参考) | 老 Copilot/API Key 设想 |
| `predict-v2 / harness-split / studio-mvp1 / studio-frontend-f4-api / tauri-t2 / tauri-t3 / v1-reset-mvp-0..5` | **无关** | 跟 V2.1 graph_agent schema 不耦合 (除 `v1-reset-mvp-5/tasks.md:422` 提及 "v2.0 roadmap" 作为历史规划证据) |

## 6. 风险

> **R-1: 解析重构一刀切导致服务大面积宕机**
> - 证据: High (core/compiler.py:178 强依赖 2.0 字符串, apps/studio/backend/app/services/skills.py:16 直接绑死 compiler)
> - 影响: High (硬切时整个 IDE & CLI 将立刻不能运转直至全部模块切齐)
> - 方案置信度: A (符合 user 不维护双轨向后兼容的决定)

> **R-2: 新增 Logic Action 机制改造范围低估**
> - 证据: Med (`skills/*/actions/` 0 命中, Logic Action 概念从未在框架/技能侧落地; LangChain Tool 路径已成熟但不能直接复用为 Action)
> - 影响: Med (新增的 actions 加载流 + context 门面是全新代码, 不是改造既有路径; 估算时易低估)
> - 方案置信度: B (设计阶段需明确 Action 的接口契约 + 跟 Tool 的物理目录分离规则)

> **R-3: 前端进度脱节**
> - 证据: High (User 决策要求 studio-frontend-v2 暂停等 JSON 协议定稿)
> - 影响: Med (Studio 升级的时间轴存在明显的阻塞等待区)
> - 方案置信度: A (符合 User "先保引擎"的战略思路)

> **R-4: 测试基线断层**
> - 证据: High (引擎解析逻辑重写)
> - 影响: High (覆盖率可能会断崖式下跌，且排错困难)
> - 方案置信度: B (需要强迫性新基线重铺，且需严格检查漏写)

> **R-5: 目录扫描替代单文件可能带来 IO 性能损耗**
> - 证据: Low (理论推断, 未进行基准测试)
> - 影响: Low (本地磁盘对小目录加载损耗极小)
> - 方案置信度: A (解耦获得的工程红利远大于解析耗时)

> **R-6: 现役 17 份 SKILL 全数 break by design, 用户业务即时停摆**
> - 证据: High (PM 跑 `grep -rh "^schema_version:" skills/` 显示 17 份 SKILL 全是 schema "2.0"; user 业务跑的 `story-deconstruction / text-segmentation / event-extraction / producer / batch-analysis` 全部 in scope)
> - 影响: High (一刀切后短剧分析等业务管线即刻全数停摆, 直到对应 skill 同步重构完成)
> - 方案置信度: B (符合 user 决策 3 "一刀硬切"; 但 design.md 阶段必须明确停摆窗口期 + skill  迁移优先级 — 高频用的 text-segmentation 先迁, 低频用的 product-manual 排后)

## 7. Open Questions

1. **XML Body 解析器选型** [影响范围: 内核 解析; 需要 User 决策]：在分离出 XML 后，是手写正则+轻量级解析、依赖 `lxml` 等标准库还是采用类似 `markdown-it+plugin` 的形式处理？
2. **exit_contract 注入点及权重定义** [影响范围: 内核 认知流; 需要 User 决策]：强切入的 `<exit_contract>` 到底是被编入顶级 System Prompt 的最开头，还是作为独立且不断复现的最后一条 User Message，以避免上下文窗口衰减？
3. **老技能强制改造期的人力投入** [影响范围: SKILL 库; 需要 User 决策]：因为实施一刀切阻断 (V1 break by design)，改造现役 `skills/`（大约几十个）的工程量谁来承担，还是通过大模型自动化 Codemod？
4. **前端配置 JSON Schema 定义职责** [影响范围: Studio; 需要 User 决策]：最终前端渲染用的 V2.1 Schema Definition 表单是从 graph-agent 框架自动生成 (Pydantic export JSON Schema) 还是前后端独立维护？
5. **现役 17 个 SKILL 改造的优先级与停摆窗口** [影响范围: 用户业务; 需要 User 决策]：是否允许“老 skill 全 break，新 skill 全重写”时的业务停摆？停摆窗口容忍多长？需排迁移优先级吗？
6. **新引擎开发模式** [影响范围: 工程规范; 需要 User 决策]：是 fork rewrite (新建包) 还是 in-place 直接在 `packages/graph-agent` 改造？
7. **三种节点识别字段** [影响范围: Schema 规范; 需要 User 决策]：LOGIC/SUBGRAPH/SKILL 的区分 Pydantic discriminator 字段命名用什么？(`mode` / `type` / `kind`?)

## 8. 后续 Spec 阶段流转

按 Kiro 流程:
- Step 2 → requirements.md (主笔: a2, 审阅: a3+a1, 收敛: 主控 + user)
- Step 3 → design.md (主笔: a2, 审阅: a3+a1, 收敛: 主控 + user)
- Step 4 → tasks.md (主笔: a1 Codex, 审阅: a2, 收敛: 主控 + a1 答疑 + user)