# graph_agent 设计意图理解报告

> 作者：Claude（重新学习后）
> 日期：2026-04-23
> 目的：在给任何方案之前，证明我真的读懂了 graph_agent 的设计意图；前一轮 Kiro spec 全部失效。

---

## 1. 我之前错在哪（自我诊断）

| 错误 | 事实 | 伤害 |
|------|------|------|
| **① 地基级幻觉**：`PhaseConfig.steps: list[Step]` | 代码里**没有任何 steps 概念**。Phase 是最小执行单元，内部是 DeerFlow agent loop | SkillManifest 第一次 `model_validate()` 在 5 个现有 skill 上全炸 |
| **② 机制混淆**：`<ref>` 和 `subgraph:` 当成同一回事 | `<ref>` 是 parser 阶段字符串替换（`parser.py` L160-186），`subgraph:` 是 loader 阶段递归加载（`loader.py` L535），两者作用完全不同 | 扁平化方案杀死递归 subgraph 机制 |
| **③ 设计意图背反**：扁平化合并 4 个独立 skill 到 story-deconstruction 里 | graph_agent 核心是"skill 独立可运行、互相即插拔"，扁平化等于**焊死**积木 | 彻底破坏模块化 |
| **④ Callback 事件幻觉**：14 个事件（含 llm_fallback/validator_start/end/prompt_captured/tool_result/subgraph_start/end/checkpoint_compacted/finish_task_called） | `callbacks/base.py` 实际只有 12 个事件，名字也不对 | 所有基于"14 事件"的前端/类型化设计空中楼阁 |
| **⑤ framework 越界**：`Step.when + simpleeval` 让 framework 执行条件表达式 | schema 2.0 已删除 `LLMPhase.steps` 字段（PR #5 方针 1.2），framework 不再有 `when` / `simpleeval` 的 hook 点；`Step` 类作为 dead public symbol 保留 | 违反 owner 的核心设计哲学 |

**根因**：我没读代码就开方案。Gemini 顺着我的叙述共谋，没交叉比对 loader.py。两个 LLM 基于幻觉对话了 3 轮。

---

## 2. graph_agent 是什么

**一句话**：基于 LangGraph + vendored DeerFlow 的**声明式多阶段 Agent 编排引擎**，以 SKILL.md 为单一事实源，支持递归 subgraph 和细粒度 skill-as-tool 两种组合方式。

**双层控制**（`docs/COGNITIVE_LOOP_GUIDE.md`）：
- 外层 `GraphAgentHarness`：phase 编排 / planning nudge / selfcheck nudge / checkpoint compaction / finish gate
- 中间层 middleware：WorkingMemory / DeadEndPruning / Clarification / DanglingToolCall
- 内层 DeerFlow agent loop：LLM 调用 / tool 执行 / 流式输出

---

## 3. SKILL.md 的 DSL 结构（真实，不是我幻想的）

### Frontmatter 字段（YAML）
- `name` / `description` / `type: simple | graph`
- `io: {inputs, outputs}` 声明式 I/O
- `context_mapping: {key: "{input.x.y}"}` 纯数据映射（**禁 $func()**，F006）

### 正文标签（XML 风格）

| 标签 | 作用 |
|------|------|
| `<node id="..." depends_on="...">` | graph 模式的拓扑节点 |
| `<phase_config>` | phase 参数（name/tier/tools/validator/retry_target/**subgraph**/context_bridge/**sub_skills**/...）|
| `<system_prompt>` | LLM 系统提示 |
| `<user_prompt>` / `<user_prompt_builder>` | LLM 用户提示模板 |
| `<data_architecture>` | 数据结构约束说明 |
| `<ref path="...">` | 文件级片段包含（parser 阶段字符串展开）|

**没有**：`<step>`、`steps: [...]`、`when:`、`skip_if:`、`model_override:`（都是我上轮幻觉）

---

## 4. 两种复用机制的本质区别

| 机制 | 展开阶段 | 作用 | 例子 |
|------|---------|------|------|
| **`<ref path="nodes/01.md" />`** | **Parser 阶段**（`parser.py` L160-186） | 文件级**字符串替换**，把外部 .md 内容拼进来，拼完后 loader 看到的是一个大字符串 | `compiler/SKILL.md` 用 `<ref path="nodes/01_compile_check.md" />` 把长 phase 配置外排 |
| **`subgraph: path/to/SKILL.md`** | **Loader 阶段**（`loader.py` L519-560） | 逻辑级**递归加载**另一个完整 skill 为子 `GraphAgentHarness` 实例，运行时 `child.run()` | SKILL_AUTHORING_GUIDE §8 示例：render phase 委派给 subskills/render/SKILL.md |

**关键**：`<ref>` 是物理文件工具（解决"主文件太长"），`subgraph:` 是逻辑组合工具（解决"skill 即插拔"）。**我之前把它们混为一谈是最致命的错误**。

---

## 5. Phase 的三种互斥模式（`loader.py` L565）

```python
requires_llm = (system_prompt is not None) and (subgraph_harness is None)
```

| 模式 | 触发条件 | 执行 |
|------|---------|------|
| **LLM phase** | 有 `<system_prompt>`，无 `subgraph:` | 跑 DeerFlow agent loop，LLM + tools |
| **Subgraph phase** | 有 `subgraph:`（**tools 被强制清空**，L578）| 递归执行子 skill 的 `child.run()` |
| **Code-only phase** | 两者都没有 | 纯代码执行，只跑 `tools` 列表里的函数 |

**互斥是硬约束**：定义 subgraph 时即使写了 system_prompt 也会被忽略；subgraph phase 不能有自定义 tools。

---

## 6. 两种 Skill→Skill 组合方式（我上轮完全漏掉）

| 方式 | 声明位置 | 粒度 | 编排者 | 场景 |
|------|---------|------|--------|------|
| **subgraph-as-phase** | `phase_config.subgraph: path/to/SKILL.md` + `context_bridge` | **粗**：整个 phase 委派给一个子 skill | **框架**（loader 递归，runner 执行子 harness） | 父 skill 知道确定的工作流顺序（pipeline） |
| **sub_skills-as-tool** | `phase_config.sub_skills: [{name, skill_path}]`（`loader.py` L586-596）| **细**：子 skill 被包成 LangChain Tool 挂到父 phase 的 tools 列表 | **LLM**（在 agent loop 里按需调用）| 父 skill 让 LLM 基于情境动态选择调哪个 sub-skill |

**两者都走框架原生机制**，不需要宿主项目写 Python 胶水。

---

## 7. 四大设计性质的代码支撑

| 性质 | 代码证据 |
|------|---------|
| **递归 subgraph** | `loader.py` L513 `_loading_stack` 防无限递归；`subgraph.py` L98 nested `thread_id="parent:phase"` |
| **模块化** | 每个 skill 一个目录 + 独立 SKILL.md + 独立 `script/` + 独立 `references/` |
| **独立验证** | `run_skill("skills/text-segmentation/SKILL.md", ...)` 不需要父 skill |
| **即插拔** | `subgraph:` 指哪个 skill 就嵌哪个；`context_bridge` (`subgraph.py` L72-84) 做声明式 I/O 映射，无对象引用依赖 |

---

## 8. 框架的红线（从代码和文档里读出来的）

1. **不改 DeerFlow 源码**（README 原则 1）— 所有增量靠外层 harness / callbacks / middleware / config
2. **框架零业务逻辑**（README 原则 2 + schema 2.0 manifest forbid 规则）— 业务只写在 skill 目录。**条件分支/数据组装必须走 setup phase + script/ tools，不能在 SKILL.md 里写表达式**
3. **Kitchen-Pass 出餐口模式**（README 原则 3 + INTEGRATION_GUIDE §3）— phase 写 context → IOManager 经 `artifact_saver` 回调落盘，框架不依赖 host project
4. **双层认知控制**（COGNITIVE_LOOP_GUIDE）— planning nudge / selfcheck / compaction / finish gate 是硬机制，不是可选
5. **SKILL.md 是跨工具的知识契约**（compiler/SKILL.md 本身）— 同一个 skill 可作为 graph_agent 引擎 skill，也可作为 Claude Code / Cursor IDE 的 skill。**skill 格式是 portable 的**
6. **认知循环的控制权必须唯一**（Phase 三模态互斥）

---

## 9. 现状 vs 设计意图的**根本缺口**

**故事线**：
- 框架实现了递归 subgraph、sub_skills、context_bridge、独立验证全套机制（parser + loader + subgraph.py 全部存在）
- 但**现有 5 个业务 skill 一个都没用**（`grep 'sub_skills\|subgraph:' skills/` 返回空）
- story-deconstruction 的 4 个 node 是 code-only（如 `01_segmentation.md` 只有 5 行：`tools: [script.orchestrator.segment_all_chapters]`）
- 编排逻辑藏在 Python 胶水（`script.orchestrator.*`）里，不在 SKILL.md 的 DSL 拓扑里

这就是 owner 愤怒的根源 — **框架给了 DSL 级积木组合的能力，但当前业务 skill 用 Python 代码绕过，退化成了"每个 node 调一个 Python 函数"**。

Studio 的使命之一：**让 PM 用好 DSL 级组合**（让 Copilot 生成正确的 `subgraph:` / `sub_skills:` 配置），而不是让 PM 也去写 Python 胶水。

---

## 10. 被我上轮 spec 破坏的能力（要收回的错误决策）

| 上轮错误决策 | 真正破坏的东西 |
|-------------|---------------|
| **SkillManifest 扁平化**（steps list） | 杀死 `<node>` 拓扑、杀死 subgraph 递归 |
| **14 事件类型化** | 基于幻觉事件清单，完全跑偏 |
| **Step.when + simpleeval** | 违反 F006（framework 不执行业务代码） |
| **破坏性迁移现有 skill 成 inline** | 杀死独立验证、杀死 text-segmentation 等 skill 的可复用性 |
| **Task 3.4 删除 deerflow/skills/parser.py** | 误判为重复（实际和 core/parser.py 互补）|
| **Prompt Capture 要改 DeerFlow 源码** | 违反"不改 DeerFlow"红线 |
| **R7 AC5 gemini CLI 备选** | 和 R11 自相矛盾 |

**全部作废**，不是"修订 Top 5"，是**整份 Kiro spec 推翻重做**。

---

## 11. 我现在对 Studio 设计空间的判断（边界，不是方案）

**Studio 绝对不能做**（会破坏框架）：
- 任何扁平化 DSL 的设计
- 任何引入 step 层级的变更
- 任何改 DeerFlow 源码的埋点
- 任何让 framework 层执行业务表达式的字段（when/skip_if 求值）
- 任何把"skill 独立性"削弱的机制（比如强制 sub-skill 必须和 parent 同目录）

**Studio 应该做**（和框架意图一致）：
- 让 PM 用好**两种 skill 组合方式**（subgraph-as-phase vs sub_skills-as-tool）
- 让 PM 独立验证任意 skill（任何 SKILL.md 都可一键 Run）
- 让 PM 观察递归 subgraph 的嵌套执行（调用层级可视化）
- 复用 compiler skill 做 Lint（框架自举），不自己写 Python lint 代码
- 借用 Claude Code CLI 做 Copilot（因为 skill 格式本来就是 portable 的 Claude Code Skill）

**我现在认为 P1 的方向框架**（不是具体方案，只是边界判断）：
- 纯观察界面：调用 `run_skill()` + `compile_skill()`，渲染 CallbackEvent 流
- Open CLI：让 PM 通过 Claude Code CLI 用自然语言改 skill（skill 本来就是 Claude Code Skill 格式）
- 可视化：React Flow 画递归 subgraph 嵌套（有 subgraph phase 时画成双击下钻）
- 绝不改 SKILL.md DSL，绝不在 Studio 里搞"自己的 AST"

---

## 12. 已通读的材料

**文档**（9/9）：
- ARCHITECTURE / COGNITIVE_LOOP_GUIDE / INTEGRATION_GUIDE / README / SKILL_AUTHORING_GUIDE / USER_GUIDE
- IMPLEMENTATION / CONFIG_REFERENCE / TOOL_DEVELOPMENT_GUIDE（扫读）

**源码**（核心）：
- `core/parser.py` L160-186（`<ref>`）
- `core/loader.py` L519-660（subgraph + sub_skills + Phase 装配）
- `core/subgraph.py` 全文（`build_subgraph_node`）
- `core/types.py`（Phase / ContextBridge dataclass）
- `callbacks/base.py`（12 事件）
- `io/manager.py`（target: file | artifact_manager + artifact_saver）

**skills**：
- `skills/*/SKILL.md` + 关键 node 文件
- `skills/compiler/SKILL.md` + `data/rules.yaml`（F006 / P007 规则）
- `examples/hello_world/SKILL.md`

**交叉验证**：和 Gemini 做了 1 轮基于源码行号的验证（Gemini 补充了 sub_skills 机制和 subgraph 互斥 tools 两处）

---

## 13. 还没做的（候选下一步）

我克制着**不给方案**。在 owner 判断这份理解报告对不对之前，我不会再起草任何 spec 修订。

可选的下一步（由 owner 决定）：
- (a) 这份理解哪里还是错的，我继续深读
- (b) 理解准确，下一步讨论 Studio 的原则性边界，再细化方案
- (c) 方案作废，项目方向由 owner 重新定位

**对 Kiro spec 和 Superpowers plan 的处置**：当前 `.kiro/specs/graph-agent-studio/` 和 `docs/superpowers/plans/2026-04-22-graph-agent-studio.md` 都应标记为 DEPRECATED（我上轮基于幻觉写的），等 owner 确认这份理解后再决定是彻底删除、重写、还是保留供审计。

---

**一句话总结**：我把 SKILL.md 当成一堆 XML 标签的配置文件，没看出它是一棵**可递归嵌套、可即插拔、可独立验证**的逻辑树；所以我的扁平化方案等于把有机体砸成骨头粉。这份报告不是道歉，是工程交代。
