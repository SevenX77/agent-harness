# graph_agent + Skill Studio 计划框架

> 还原自 2026-04-21 对话截图（IMG_0074–IMG_0102）
> 本文件包含两部分：**一、完整对话原文**（按截图顺序逐条还原）；**二、提炼后的计划框架**（结构化整理）

---

## 一、当前框架评估与优化空间

### 1.1 技术栈盘点

| 层 | 选型 | 点评 |
|----|------|------|
| 编排引擎 | LangGraph StateGraph | 成熟 |
| Agent 内核 | DeerFlow（vendored，11k 行）| 原则上不动 |
| DSL | SKILL.md（YAML frontmatter + body 标签）| 核心 |
| 校验 | Pydantic v2 + compiler/rules.yaml | 静态 |
| I/O | IOManager + ContextResolver（{input.x.y}）| 设计好 |
| 模型路由 | ModelResolver（role→model→provider）| 熔断 |
| 可观测 | 14 个 Callback 事件钩子 + TracingCallback | 已具备 |
| MD→对象 | tools/md_to_json.py + md-patch skill | 亮点 |

### 1.2 模块实现质量

| 模块 | 实现度 | 主要问题 |
|------|--------|---------|
| core/harness.py（952 行）| 功能完整 | 太臃肿，待拆分 |
| core/loader.py + core/parser.py | 好 | parser 规则需增强 |
| core/compiler.py + skills/compiler/ | 中等 | 规则覆盖不全 |
| cognitive/（prompt/finish/memory/middlewares）| 好 | 但需 CallbackEvent 类型化 |
| callbacks/ | 中等 | 事件钩子未类型化 |
| io/manager.py + io/context_resolver.py | 优 | 最佳实现 |
| models/resolver.py | 中等 | 熔断逻辑可再完善 |
| tools/md_to_json.py | 中等 | 66% 完成 |
| skills/builtin/ | 差 | md-patch 是唯一完整 skill |
| 文档 | 差 | docs/ 大量缺失 |
| 多模态工具 | 差 | generate_video 等无单测 |

### 1.3 可以更优雅的 7 个点（按 ROI 排序）

1. **把 harness.py 拆成 4 个合作者**：GraphBuilder / PhaseExecutor / RetryRouter / NudgeInjector。现在 952 行里改任何一处都要通读全文。

2. **CallbackEvent 类型化**（Pydantic v2 模型 + schema 版本号），这是前端稳定消费事件流的基础——不做这个，Studio 永远在追 bug。

3. **Prompt Capture 埋点**：在 DeerFlow 系统的最后一刻，把「模板 + 变量 + 注入后最终文本」三元组发到 callback，PM 调试的头号痛点。

4. **SKILL.md 契约单一事实源**：frontmatter schema 落在一个 Pydantic 模型里，parser.py / loader.py / compiler.py / deerflow/skills/parser.py 共享它。CHANGELOG 里说"by design 分居校验"——一但规则不同就是债，不是设计。

5. **合并两个 docs/**：一份在 package 内（随包发布），一份是仓库顶层（工程师看），只留一份，另一份做 symlink 或构建时复制。

6. **删掉 skills/builtin/script/patch_tools.py 的副本**，只保留 md-patch/script/ 下那份；把 .pyc 加入 .gitignore。

7. **熔断策略参数化**：30min、30 误差阈值这些从 llm_roles.yaml 读，不要写死。

---

## 二、核心定位："这是给 PM 的 Agent 最后一公里"

> LangGraph 给了你 StateGraph，DeerFlow 给了你 Agent Loop——但 PM 不会写 Python。
> graph_agent 把两者封进 SKILL.md：写 markdown 就能跑多阶段 Agent。

这意味着框架的两条设计律是：

- **任何需要 PM 动手的地方，都应该是 markdown 或可视化**（不是 Python）
- **任何运行时信息，PM 应该能在界面上看到**（不是 log）

以此为"尺子"回头看当前代码，引擎层已经 80% 就位，缺的是"给 PM 的那一面镜子"，这就是前端 Studio 的价值。

---

## 三、Skill Studio 前端方案

### 3.1 整体架构

```
Browser（Next.js + React）
├── React Flow               # 阶段图（点击阶段展开）
├── Monaco: SKILL.md 编辑器  # 带 lint
├── Prompt Inspector         # 模板 / 注入 / 最终
├── Trace Timeline           # WebSocket（Callbacks）
│
│   Copilot 对话框
│   "加一个事件提取阶段" → diff → 应用 → 即实时更新
│
└── REST + WebSocket（CallbackEvent schema）
        ↓
    Skill Studio Server（FastAPI）
    ├── Skill CRUD（读写 SKILL.md + lint）
    ├── Run Service（run_skill + tracing）
    ├── Trace Store（每次 run 一个目录）
    └── Copilot（子进程调用 Claude / Gemini CLI）
            ↓
        Python import → graph_agent（+ 新增 CallbackEvent schema + TracingCallback）
```

### 3.2 关键可视化模块（与现有代码的对应关系）

| 界面元素 | 数据来源 |
|---------|---------|
| 阶段图（React Flow）| load_workflow_from_md() 返回的 Phase 列表 |
| SKILL.md 编辑器侧边 lint | compile_skill() + rules.yaml |
| 当前 Phase 的 system/user prompt | cognitive/prompt.py 组装后 |
| DeerFlow 模板注入对比 | DeerFlow 内部 prompt 拼装 |
| LangGraph 执行时间轴 | Callback.on_phase_*/on_llm_* |
| 模型 fallback 链路 | ModelResolver 内部状态 |
| 输入输出路径管理 | IOManager |
| Working Memory 差异视图 | cognitive/memory.py |

### 3.3 Copilot（Claude Code / Gemini CLI）集成

**关键决策**：不要让前端直接调用 LLM API，让 Copilot 继续使用它们原生的 CLI（它们已经有工具权限、diff 预览、沙箱）——Studio 只做会话桥和产出落地。

```
PM 在对话框输入 → Studio Server
→ 以 subprocess 方式 spawn 'claude' / 'gemini' CLI（headless 模式）
→ 传入系统提示："你在编辑 skill-studio 项目的 SKILL.md，当前文件路径..."
→ CLI 返回的 tool_use（write/edit）被 Studio 拦截 → 展示 diff → 应用
→ 文件变更触发 filewatcher → 前端实时重绘
```

**好处**：
- 继承 Claude Code 的 agent skills 生态（/review、/init 等）
- Copilot 能力随 CLI 升级免费升级
- 切换 Claude ↔ Gemini 零成本（同一个桥接协议）

### 3.4 典型用户旅程（闭环）

1. PM 打开 Studio，选 story-deconstruction skill
2. React Flow 画出 4 个 phase：segmentation → extraction → batch → synthesis
3. PM 点 batch 节点 → 右侧弹出 SKILL.md 片段 + 当前 system prompt + tools 列表
4. PM 在对话框："batch 阶段输出太长了，加一个每批最多 10 章的限制"
5. Copilot 回：`<diff>` 在 `<phase_config>` 里加上 max_batch_size: 10
6. PM 点"应用" → 文件写回 → 图面板自动重绘，lint 面板绿灯
7. PM 点"Run with sample"，选一个预存的 golden input
8. Trace Timeline 流式展开：
   - phase_start: segmentation ✓（3.2s，1.1k tokens，provider=OC_CL）
   - llm_fallback: OC_CL timeout → 切 OC_CL_ANT ✓
   - tool_call: inspect_entity ✓
   - validator: batch ✗ continuity_check failed
9. PM 点失败节点 → 看到 full system prompt + LLM raw output + validation error
10. Copilot 自动给出诊断："validator 要求 entity_ids 必须出现在前序 phase 的 context 中，但当前 prompt 没有提醒模型保留 id，建议在 user_prompt 里加上..."

这就是"显确定性"的含义：每一步都有 ground truth 可点开。

---

## 四、细粒度可视化功能清单

### A. Skill 模块化与规范化
- Frontmatter 必填项实时校验：name/description/type/io.inputs/io.outputs
- 输出 schema 可视化：把 output_schema Pydantic 模型渲染成表单 / JSON Schema
- 输入标准：source: runtime | file + 类型声明 + 样例值
- Skill 依赖图：sub_skills 声明的父子调用关系
- 模板库：新建 skill 向导（选 template → 填关键字段 → 生成目录）

### B. LLM 调用链可视化
- 角色 → 模型 → provider 三级展视图
- Fallback 尝试链（[OC_CL timeout] → [OC_CL_ANT ok] 时间轴）
- 熔断状态面板：哪些 provider 被熔断，剩余时间，手动 reset
- 本次 run 成本汇总：按 role / phase / provider 聚合 tokens 和估算费用

### C. Trace 与行为分析
- 事件时间轴（WebSocket 流式）：phase/llm/tool/validator/retry/nudge/finish
- 每步快照：context diff、messages diff、working_memory diff
- Prompt 三标签页：原始模板 / 变量字典 / 最终注入文本（🔍 核心痛点）
- Agent loop 步骤可视化：LLM 思考 → tool_call → tool_result → 下一轮
- 回放模式：从 trace 文件重放历史 run

### D. 自动报告与意图一致性
- Run 结果自动生成报告（HTML + JSON）：耗时/tokens/成本分布、Validator 通过率、重试次数、nudge 次数、Fallback 发生次数与原因
- 意图偏离检测：对比 SKILL.md 中 `<description>` 声明的意图 + plan_checklist（来自 finish_task）vs 实际 trace，高亮跑题的步骤、额外的工具调用
- Working Memory 一致性：PM 在 skill 设计目标 vs agent 实际写入的 working_memory，维度评分
- Golden set 回归：保存输入 + 期望输出，每次改动自动回归，diff 高亮

---

## 五、落地路线图

| 阶段 | 目标 | 关键交付 |
|------|------|---------|
| P0 地基 | 让前端能稳定订阅运行时 | CallbackEvent Pydantic 化 |
| P1 最小 Studio | PM 能看图、编辑、跑一次 | React Flow + Monaco + Trace Timeline |
| P2 Copilot | 对话式修改 skill | Claude Code / Gemini CLI 桥接 |
| P3 运维面板 | Fallback / 熔断 / 成本可见 | ModelResolver 状态 API |
| P4 报告与回归 | 意图一致性分析 | 自动报告生成器 + golden set 机制 |

**前置清理**（与 P0 并行）：拆 harness.py，合并 docs/，删 patch_tools.py 副本，清 .pyc，补多模态单测。

---

## 六、5 个悬而未决的问题（立场）

| # | 问题 | 建议 |
|---|------|------|
| 1 | Nudge 还要不要？ | 保留但降权：默认 max_nudges=1 |
| 2 | LLM 三档 role + 细粒度指定 | 核心改进：premium/balanced/fast 三档，plus role 列表细粒度 |
| 3 | 并发作为内置工具 | parallel_map 内置工具：接受 item_list + skill_path，内部 SubagentExecutor |
| 4 | 步骤工程化（脱离散文 prompt）| 最重要的 DSL 改进：引入 `<step>` 标签，每步有 name/goal/tools/validator |
| 5 | token / 耗时重点记录 | 强制 MetricsCallback 默认开启 |

---

## 七、必做 3 件 & 待讨论 3 件

### 必做（不做就没法稳定做 Studio）

1. **CallbackEvent 类型化** + schema 版本号
2. **Prompt Capture 埋点**（模板版 / 变量字典 / 最终三份）
3. **SKILL.md 契约统一到单一 Pydantic 模型**

### 待讨论

1. **Copilot 用 Claude Code 子进程还是直接 SDK？**
   - 子进程：继承其生态但部署复杂，SDK 更容易自己做预览
   - SDK：不等于"完整的 Claude Code"，不带交互式 UI、不带 slash commands、不带 IDE 集成，但核心 agent loop + 工具 + sub-agent + MCP + hooks 都有

2. **Studio 是 web 应用还是 VS Code 扩展？**
   - Web 对 PM 友好；VS Code 对 开发者友好，还要自己做 Monaco / git 集成

3. **意图偏离检测是否用 LLM 做 judge？**
   - LLM judge 更智能但引入随机性；基于 plan_checklist 的结构化对比确定性有限

---

## 八、Superpowers / Kiro 项目确认

**Superpowers**（obra/superpowers plugin）：docs/superpowers/plans/2026-04-08-story-deconstruction.md（1734 行）—— 是 superpowers 的 plan 格式（带 `- [ ]` checkbox + REQUIRED SUB-SKILL 引用），用于执行阶段，agent 可以顺着 checkbox 一项项实施。

**Kiro**（AWS Kiro IDE spec 规范）：.kiro/settings/ 完整的规则和模板，包括：
- rules/design-principles.md（设计原则，Type Safety / SRP / Contract First 等）
- rules/design-review.md、rules/ears-format.md、rules/gap-analysis.md
- templates/specs/（requirements/design/tasks/research 四件套）
- templates/steering/（product/structure/tech）+ steering-custom/

Kiro 用于设计阶段（spec-driven development）。

**落盘策略**：用 superpowers plan 格式落扎实化方案（单文件，带 checkbox，可直接被 agent 实施），和现有 2026-04-08-story-deconstruction.md 风格保持一致。如果后续 track 需要深设计，再用 Kiro spec 三件套展开。

---

## 九、CCB（Claude Code Bridge）补充

- 多 agent tmux 编排：Claude / Codex / Gemini / OpenCode 各跑一个 pane（pane_title_marker: CCB-Claude-xxx）
- 项目隔离：ccb_project_id（项目路径哈希）让同一项目的多 agent 共享上下文
- IPC 通道：至少 codex 用了 input_fifo/output_fifo 命名管道
- 环境变量契约：被启动的 agent 从 CCB_MANAGED=1 / CCB_PARENT_PID / CCB_RUN_DIR / CCB_CALLER 感知自己在 CCB 体系里
- 会话状态文件：仓库里的 .ccb/（.claude, codex, gemini, opencode）- session 是 CCB 写入的指针

**结论**：Studio Copilot 直接复用 CCB 作为 Gemini 侧的桥，不需要造轮子。但 .ccb/ 目前被签进了 git（.gitignore 漏了），这是本地 runtime 元数据，应在 hardening 任务里加到 .gitignore。


---

# 完整对话原文还原

> 来源：IMG_0074–IMG_0102（2026-04-21 11:50–11:52 截图）
> 以下按截图顺序逐条还原，[用户] 表示用户消息，[Claude] 表示 Claude 回复

---

## 第一轮（IMG_0074–IMG_0076）

**[用户]** 扫描整个仓库，告诉我这个库现在是什么情况

**[Claude]** （运行了 8 个命令，读了 2 个文件）

### Agent Harness 仓库状态报告

**总体状况**
- 当前分支：claude/analyze-repo-status-PsYNu（与 main 完全一致，领先 0 个提交）
- 工作区：干净，无未提交改动
- 历史：仓库只有 1 个提交（c7405b7），是一次巨型初始化提交，新增 53,813 行 / 313 个文件
- 提交信息：feat: merge Story Forge features into Agent Harness（2026-04-21，由 SevenX77 + Claude Sonnet 4.6 共同创作）

**项目本质**

这是一个基于 DeerFlow 的多阶段 Agent 编排引擎（graph_agent），用 SKILL.md 描述工作流，刚刚把 AI-Story-Forge 的三大能力合并进来：

1. Sub-skill Calling——跨 skill 零 Python 调用
2. V2 Schema Tag——在 SKILL.md phase_config 声明 schema 输出
3. MD Parser——LLM 输出 → Pydantic（带自动修复）

**目录结构**

| 路径 | 作用 |
|------|------|
| src/core/graph_agent/ | 核心引擎（内含 DeerFlow） |
| src/core/graph_agent/skills/builtin/md-patch/ | 新加的 MD 手术修复 skill |
| src/visual_learning/ | 多模态学习模块 |
| skills/ | 业务 skills（5 个） |
| config/ | llm_roles.yaml |
| docs/graph_agent_docs/ | 9 篇架构/实现文档 |
| docs/superpowers/plans/ | 2026-04-08-… |
| scripts/ | run_e2e_test.sh |
| .kiro/settings/ | 设计/规则/模板… |
| .claude/sessions/ | 3 份历史 sessions |
| .ccb/ | 4 个 coding agent 的状态文件 |

**技术栈与依赖**
- Python > 3.12（DeerFlow 依赖 typing.Self/override）
- LangChain > 1.2（patched），graph_agent 作为独立可安装包
- 支持 Claude / OpenAI Codex / Minimax / DeepSeek 多 provider

**已知技术债（来自 CHANGELOG）**
- harness.py 952 行，超过 300 行规则，待拆分
- deerflow/ 与 core/parser.py 有两套并行 SKILL.md 校验（设计使然）
- 多模态工具（generate_video/synthesize_speech/understand_video）无单测
- src/visual_learning/phase1_gt_extraction_v1.py.bak 还留着旧备份

**可疑/可清理项**
- 根目录 2026-04-08-...ai-narrated-recap.txt（1230 行会话录，是否该进仓库？）
- src/core/graph_agent/docs/ 与 docs/graph_agent_docs/ 有 9 份完全重复的文档
- skills/builtin/md-patch/script/__pycache__/*.pyc 被签入仓库
- skills/builtin/script/patch_tools.py 与 skills/builtin/md-patch/script/patch_tools.py 内容疑似重复

**一句话总结**

一个刚落地、骨架完整但尚无二次迭代的 graph-agent 编排框架——初始合并把交给 DeerFlow 内核、Story-Forge 特性、业务 skills 完整矩阵一次性导入，目前处于"已到达远站、等待下一轮清理与拆分"的状态。

> 对这个 graph agent 的功能、工程架构、输入输出接口做一个全面分析

（运行了 3 个文件，1 个工具）

核心事实已核验（Init 公开 API、Phase / WorkflowState 字段完全一致）。下面是整理后的全面分析报告。

---

## graph_agent 全面分析报告（IMG_0076–IMG_0085）

**位置**：src/core/graph_agent/（内嵌 DeerFlow），~142 个 Python 文件，~4000 行核心代码。  
**定位**：以 SKILL.md 为单一事实源的声明式多阶段 Agent 编排引擎。

### 一、功能能力

#### 1.1 核心抽象（public API）

graph_agent/__init__.py 导出的对外原语：

| 原语 | 类型 | 职责 |
|------|------|------|
| run_skill | function | 一键执行 SKILL.md，无需手写 harness |
| GraphAgentHarness | class | 外层编排器（LangGraph 驱动）|
| Phase | dataclass | 单阶段配置（prompt/tools/validator/…）|
| ContextBridge | dataclass | 父子 skill 输入输出映射 |
| WorkflowState | TypedDict | 节点点流转状态（context/messages/…）|
| load_workflow_from_md | function | SKILL.md → GraphAgentHarness |
| compile_skill | function | 静态规则校验（rules.yaml）|
| IOManager/ContextResolver | classes | 声明式 I/O + {input.x.y} 模板解析 |
| ModelResolver | class | role → model → provider 解析 |
| Callback 系 | classes | 14+ 事件钩子（logging/metrics/tracing）|

#### 1.2 五类核心能力

1. **声明式多阶段工作流**：SKILL.md 里的 `<node>/<phase_config>` 编译成 list[Phase]，按照顺序在 StateGraph 中流转。

2. **认知循环约束（cognitive/）**：强制 LLM 写 working_memory（本阶段目标/步骤/数据来源），用 finish_task() 结构化自检（reasoning/evidence/plan_checklist），并通过 DeadEndPruningMiddleware 识别死循环。

3. **子技能调用（Sub-skill）**：core/skill_tool_factory.py，SubSkillSpec 把任意 SKILL.md 包成 StructuredTool，零 Python 跨 skill 互调。

4. **MD→Pydantic 自动解析修复**：tools/md_to_json.py + skills/builtin/md-patch/——LLM 输出被解析成 Pydantic；失败时用 "md-patch" 小模型做 surgical 修复，避免整轮重跑。

5. **角色化模型路由**：models/resolver.py——tier → role → model_codes[] → provider_codes[]，任一层失败自动降级；30 min 熔断窗口。

### 二、工程架构

#### 2.1 双层控制架构（核心设计点）

```
外层 GraphAgentHarness（LangGraph）
  • 阶段顺序与条件路由（phase→validator→retry→next）
  • planning/selfcheck nudge 注入
  • checkpoint compaction（长任务消息压缩）
  • validator 重试路由到 retry_target

          per-phase .invoke(state)
                    ↓
  内层 DeerFlow create_agent() loop
  • LLM 调用 + tool 执行 + 流式响应
  • 中间件：WorkingMemory / DeadEndPruning / ToolError
  • Sandbox 工具（list_dir/read_file/execute_command）
  • SubagentExecutor(max_workers=3) 用于并行子任务
```

**设计原则**（docs/graph_agent_docs/ARCHITECTURE.md）：
- 不改 DeerFlow 源码——通过外层 harness、callbacks、middleware、config 解决问题
- 框架层零业务逻辑——业务只写在 skill 目录里
- Kitchen-Pass（厨房传递）：一阶产物结果先进 context，真正持久化由 IOManager + 调用方注入的 artifact_saver 完成

#### 2.2 模块分层

| 目录 | 行数 | 作用 |
|------|------|------|
| core/ | ~3500 | Harness/Runner/Loader/Compiler/Parser/State |
| cognitive/ | ~560 | prompt/finish/memory/ambiguity/middlewares |
| callbacks/ | ~770 | 14 个事件钩子 + logging/metrics/tracing + DeerFlow |
| config/ | ~880 | llm_roles.yaml / multimodal_roles.yaml 等 |
| io/ | ~440 | IOManager（inputs/outputs 声明）+ ContextResolver |
| models/ | ~525 | ModelResolver（role→provider 解析，provider failover）|
| tools/ | ~1940 | 多模态工具（image/video/speech）+ md_to_json |
| deerflow/ | ~11k | 内嵌的 DeerFlow（agents/middlewares/sandbox/…）|
| skills/ | — | 内建 skill：compiler/（自检）+ md-patch/（修复）|

#### 2.3 关键类关系

```
run_skill(skill_path, **kwargs)
  └── load_workflow_from_md() ──→ GraphAgentHarness
                                    ├── phases: list[Phase]
                                    ├── _graph: StateGraph[WorkflowState]
                                    ├── _resolver: ModelResolver
                                    ├── _io: IOManager
                                    └── callbacks: [Logging|Metrics|Tracing|…]

harness.run(initial_context)
  ├── IOManager.load_inputs() + ContextResolver 展开 context
  └── for each Phase:
        ├── phase_node → DeerFlow create_agent().invoke() → (ok, error)
        ├── validation_node → validator(context) → (ok, error) → retry_target
        └── router → 下一阶段 | 重试路由 | END

IOManager.save_outputs(context)
```

#### 2.4 扩展点

| 扩展点 | 机制 |
|--------|------|
| 工具 | SKILL.md tools: 列表 / `<ref>` 引用，或向 Phase 注入 C |
| 子技能 | SubSkillSpec → skill_tool_factory.build_skill_tool() |
| 回调 | 继承 Callback，14 个事件钩子（phase_start/end、llm_…）|
| 中间件 | 继承 DeerFlow AgentMiddleware，内置 agent loop 可插 |
| 验证器 | Phase.validator：(context) → (ok, list[str]) |
| Sandbox | deerflow/sandbox/ 抽象类，可换 local/docker/remote |
| 模型 provider | llm_roles.yaml 增加 models/providers/roles 三段配置 |

#### 2.5 并发/缓存/容错

- **并发**：阶段间顺序；阶段内部 SubagentExecutor(max_workers=3) 并行子任务
- **缓存**：runner._harness_cache 按 SKILL.md + llm_roles.yaml 的 mtime 快照缓存已编译 harness
- **容错**：provider failover + 30 分钟熔断；validator 重试最多 max_retries 次；max_nudges 限制认知 nudge 次数；dead_end_threshold 阈断重复工具调用

### 三、输入输出接口

#### 3.1 Python API

```python
from graph_agent import run_skill, load_workflow_from_md, GraphAgentHarness

# 方式一：一键执行
result = run_skill(
    "path/to/SKILL.md",
    scene_data,
    artifact_saver=my_saver_fn,   # 通过 **kwargs 传入 run
    output_dir="/tmp/output",      # 可选：调用方持久化函数
)
# result: WorkflowState = {context, messages, current_phase, …}

# 方式二：显式编排并行（放测试/调试）
harness = load_workflow_from_md(Path("skill/SKILL.md"), callbacks)
result = harness.run(initial_context={"input": data})
```

#### 3.2 CLI

```bash
python -m graph_agent --skill path/to/SKILL.md --inputs '{"k": "v"}'
```

#### 3.3 配置输入

config/llm_roles.yaml（三段式）：

```yaml
models:    # 模型代号 → 与 provider 绑定
  CL46T: { providers: { OC_CL: claude-sonnet-4-6-thinking, … } }
providers: # provider 代号 → openai_compatible，api_key 从环境变量
  OC_CL:  { type: openai_compatible, api_key: ONECHATS_API_… }
roles:     # tier 名（balanced/fast/creative）+ 模型优先级列表
  balanced: { model_codes: [{ model_code: CL46T, provider_codes: [O…
```

查找顺序：GRAPH_AGENT_ROLES_PATH 环境变量 → 向上搜索 config/llm_roles.yaml → 内置兜底。

.env: OPENAI_API_KEY/ANTHROPIC_API_KEY/ONECHATS_API_KEY...（由 provider 声明 api_key_env）

#### 3.4 SKILL.md 契约

```yaml
---
name: story-deconstruction          # hyphen-case
description: "..."                  # ≤ 1024 字
type: graph | code                  # graph=LLM 编排；code=纯代码节点
io:
  inputs:
    - { name: scene, source: runtime }   # 或 source: file, …
  outputs:
    - { name: result, target: file, path: out.json }
    - { name: gt,     target: artifact_manager }
context_mapping:
  scene_id: "<input.scene_id>"           # 点路径语法
sub_skills:                              # 可选：声明可调用的子 skill
  - { name: md_patch, skill_path: .../builtin/md-patch/SKILL.md }
---

<node id="phase_1">
  <phase_config tier="balanced" tools="[...]" output_schema="S">
    <system_prompt>... </system_prompt>
    <user_prompt>{{ scene_id }}</user_prompt>
  </phase_config>
</node>
```

Phase dataclass 字段（core/types.py:27）覆盖：prompt、tools、tier、validator、retry_target、max_retries、max_nudges、dead_end_threshold、subgraph、context_bridge、output_schema、md_type_dict 等。

#### 3.5 State 流转与 Kitchen-Pass

WorkflowState（core/state.py:15）：

```python
context        # 业务黑板，跨阶段读写
messages       # 当前阶段 LLM 会话记录（切阶段时重置）
current_phase  # 正在执行的阶段名
retry_counts   # 按 phase / retry_target 分辨的重试计数
metrics        # 累计 token 用量 & 耗时
```

Kitchen-Pass 模式：阶段产物先写 context，再由 IOManager.save_outputs() 决定落盘；target=artifact_manager 时回调 artifact_saver(name, value, metadata)——框架不依赖宿主项目的存储实现。

#### 3.6 持久化产物布局

```
output_dir/
├── _trace.json       # TracingCallback 写入的完整执行轨迹
├── _metrics.json     # token / 耗时
├── result.json       # context 按 io.outputs 声明输出
└── <artifact>.bin    # artifact_manager 回调存储
```

#### 3.7 宿主项目集成（示例）

src/visual_learning 要接入时：在自身目录下写 vision_skill.SKILL.md，声明 io.outputs: [{ target: artifact_manager }]，然后：

```python
def save_to_db(name, value, meta=None):
    db.insert_artifact(name, value, meta)

run_skill("src/visual_learning/vision_skill/SKILL.md",
          image_path="...", artifact_saver=save_to_db)
```

---

## 第二轮（IMG_0085–IMG_0086）：用户追问

**[用户]** （发来一段长消息，内容如下）

> 1. 全面分析一下现在这个框架，技术栈，各个功能实现得怎么样？有没有优化空间？2. 这个 harness 可以考虑更加维护：最大的优势和设计目的就是方便产品经理快速创建他们想要的 skill，复杂的 lang.graph 框架和 agent loop 不用关心，以及更灵活：可以让 pm 制定某一个步骤，调用工具的主要 agent 的模型，主要 agent 的 subagent 以及 tool 的 buildin 模型：需要和 md2json 一并考虑；不做 buildin 模型化工程，规范化只是很难随意适用于所有工程，需要集成 claude code，Gemini cli 这类 agent 来作为修改 skill 的大脑，产品经理通过对话创新探索修改 skill；需要能够直观地看到 langraph 图，能够看到每一个 agent/skill 的内容，可以设置系统的输入是什么，管理输入/输出的路径 test，可以看到每一个 agent/skill 的内容；可以看到每一个 agent / skill 的内容，可以设置系统的输入是什么，管理输入/输出的路径测试，每一个节点每一步操作有什么，输入和标准是什么？llm 调用 fallback 排序，熔断情况，每一个节点每一步操作有什么的 trace，自动分析运行报告，agent 行为是否和设计意图一致。4. 还有很多小的功能成功能也需要设计它的模块化规范化，比如 head 飞要必须，输出 schema 是什么，输入和标准是什么？llm 调用 fallback 排序，熔断情况，每一个节点每一步操作有什么的 trace，自动分析运行报告，agent 行为是否和设计意图一致。

> 下面是结构化的分析与建议，这是一个讨论框架，不是敲定计划——我会标出优先级和取舍，具体做到哪一步、哪些先做，你可以随时面向定。

**[Claude]** 分两部分回答（IMG_0086–IMG_0094）：

### 一、当前框架评估与优化空间

（见上方提炼后框架的"一、当前框架评估"章节——内容完全一致，不重复）

### 二、核心定位："这是给 PM 的 Agent 最后一公里"

（见上方"二、核心定位"章节）

### 三、Skill Studio 前端方案

（见上方"三、Skill Studio 前端方案"章节——完整架构、可视化模块、Copilot 集成、用户旅程）

### 四、细粒度可视化功能清单

（见上方"四、细粒度可视化功能清单"章节——A/B/C/D 四类）

### 五、落地路线图（建议）

（见上方"五、落地路线图"章节）

### 我建议的三件必做 & 三个值得再讨论的点

**必做（不做就没法稳定做 Studio）：**
1. CallbackEvent 类型化 + schema 版本号
2. Prompt Capture 埋点（模板版 / 变量字典 / 最终三份）
3. SKILL.md 契约统一到单一 Pydantic 模型

**待讨论：**
1. Copilot 用 Claude Code 子进程还是直接 SDK？子进程继承其生态但部署复杂；SDK 更容易自己做预览
2. Studio 是 web 应用还是 VS Code 扩展？Web 对 PM 友好；VS Code 对开发者友好，还要自己做 Monaco / git 集成
3. 意图偏离检测是否用 LLM 做 judge？LLM judge 更智能但引入随机性；基于 plan_checklist 的结构化对比确定性有限

---

## 第三轮（IMG_0095）：用户追问工具选型 + 项目工具确认

**[用户]**

> 1. nudge 还要不要？2. llm 调用用 ppm 快速选择 premium/balance/fast 三档 + 各种单模型（用 provider fallback）可以让 pm 制定某一个步骤，调用工具的主要 agent 的模型；不做 buildin 模型化工程规范化只是很难随意适用于所有工程，需要集成 claude code，Gemini cli 这类 agent 作为修改 skill 的大脑；产品经理通过对话创新探索修改 skill。3. 并发作为内置工具，4. 步骤工程化（脱离散文 prompt）最重要的 DSL 改进：引入 `<step>` 标签。5. token 和耗时重点记录，每次运行中也都需要关注这两个参数；
>
> 你的分析和建议都很好（很高我也看不懂），你想要讨论的我只能回答：一定是 web 应用，因为你子进程是什么原理？sdk 效果哪个好？sdk 是把 Claudecode 完整功能接进来？帮我科普一下。意图偏离检测是否要 llm 做 judge？是的，但是你刚刚说的 plan checklist 也应该作为 llm 分析的一部分
>
> 我希望你快速落盘文档，这个项目有没有 super power 和 kiro？

---

## 第四轮（IMG_0096–IMG_0100）：Claude 回答 SDK vs 子进程 + 确认 Superpowers/Kiro

**[Claude]**

> 最优先想要做的就是把核心的 graph agent 的迭代实优化一点，能够得到一个更成熟的标准化产品。
>
> 先确认项目里 superpowers / kiro 的使用情况，然后科普 + 落盘。

（运行了 4 个文件读取）

先回答你的问题，然后落盘主文档。

### 一、Claude Code SDK vs 子进程科普

两者都是"让自己的程序用上 Claude Code 的能力"，但路径不同。

#### 子进程方式（CLI subprocess）

原理：你的程序 spawn `claude` 命令作为子进程，通过 stdin/stdout 通信。

```python
your_server.py
  └── subprocess.Popen(["claude", "-p", task, "--output-format", ...])
      → 把 PM 对话写入 stdin
      → 解析子进程输出的 JSON 事件（tool_use / text / result）
```

✅ 继承用户本地所有配置：~/.claude/CLAUDE.md、MCP、自定义 skills、settings.json 全部生效  
✅ 实现超简单（几十行）  
❌ 部署困难：用户必须安装 Claude Code CLI 才能用 Studio  
❌ 程序化拦截 tool_use（做 diff 预览）需要解析文本流，容易漂移

#### SDK 方式（Claude Agent SDK）

原理：Python/TS 的 SDK 库，内部是一个完整的 agent loop 实现，把 Claude Code 的核心能力封装成函数/类。

```python
from claude_agent_sdk import query, ClaudeAgentOptions

async for msg in query(
    prompt="给 SKILL.md 加一个事件提取阶段",
    options=ClaudeAgentOptions(
        allowed_tools=["Read", "Edit", "Glob"],  # 代码精细控制
        cwd="/path/to/skill/dir",
        mcp_servers={...},
        system_prompt_suffix="...",    # 追加到系统提示
    )
):
    # msg 是结构化对象：ToolUseBlock、TextBlock、ResultBlock
    if isinstance(msg, ToolUseBlock) and msg.name == "Edit":
        # 拦截并展示 diff 预览
```

✅ 程序化控制强：tool_use 是类型对象，拦截/审批/改写都容易  
✅ 部署轻量：pip install claude-agent-sdk，用户不需要装 CLI  
✅ Studio 可以给每个 PM 会话独立的权限策略  
❌ 不自动继承用户本地的 CLAUDE.md / skills——要在代码里显式加载  
⚠️ SDK 不等于"完整的 Claude Code"：不带交互式 UI、不带 slash commands、不带 IDE 集成；但核心 agent loop + 工具 + sub-agent + MCP + hooks 都有

#### SDK 是把 Claude Code 完整接进来吗？

核心引擎接进来了，外壳没接进来。具体说：

| 能力 | CLI 有 | SDK 有 |
|------|--------|--------|
| Agent loop（思考→工具→响应）| ✓ | ✓ |
| 工具：Read/Edit/Write/Bash/Glob/Grep | ✓ | ✓ |
| Sub-agent（Task 工具）| ✓ | ✓ |
| MCP servers | ✓ | ✓ |
| Hooks | ✓ | ✓（更细粒度）|
| 权限模式 | ✓ | ✓（更细粒度）|
| 自定义 Skills（Agent Skills）| ✓ | ✓（需要 setting…）|
| 交互式 TUI | ✓ | ✗（SDK 是库，U…）|
| /init/clear/review 等 slash commands | ✓ | ✗（但可用 setti…）|

**对 Skill Studio 的选型结论**：Studio 用 SDK。理由：web 服务化部署 + 需要程序化拦截工具调用做 diff 预览 + 每个 PM 独立权限沙箱。子进程在作为开发者 fallback。

Gemini 同类比：Gemini CLI 有子进程模式；Google 也有 Gemini SDK（google-genai），但它只针对模型调用，没有 agent。要让 Gemini 作"skill 修改版脑"，得自己包 agent loop，工量量大得多。第一版 Studio Copilot 只做 Claude SDK，Gemini 留口子。

### 二、你 5 个问题的立场

（见上方"六、5 个悬而未决的问题"章节——完整表格）

### 三、Superpowers / Kiro 项目确认

（见上方"八、Superpowers / Kiro 项目确认"章节）

> 我将用 superpowers plan 格式落扎实化方案（单文件，带 checkbox，可直接被 agent 实施），和现有 2026-04-08-story-deconstruction.md 风格保持一致。如果后续 track 需要深设计，再用 Kiro spec 三件套展开。

---

## 第五轮（IMG_0101–IMG_0102）：落盘触发 + API 超时 + CCB 发现

**[Claude]** 现在落盘。

⚠️ API Error: Stream idle timeout - partial response received

**[用户]** 继续

（运行了 1 个命令）

> 1. Gemini cli 做辅助分析，用 claude+ccb 协议来调用（看一下库里面有没有 ccb 协议），Claude 做业务逻辑分析建议。claude code 与 Gemini battle 出最终结果（3 轮，battle 不出的问题交给用户）。2. 不单单是三档 role，还有独立模型指定，role 会有有不同模型优先级 fallback，而独立模型指定是确定性的测试某个模型

⚠️ Request timed out

先查库里的 CCB，然后更新方案。

（运行了 3 个模式搜索，读了 2 个文件）

CCB 查清楚了——关键信息：

**CCB（Claude Code Bridge）发现**

不在本仓库代码里，是你 mac 本地的外部协议工具，功能：
- 多 agent tmux 编排：Claude / Codex / Gemini / OpenCode 各跑一个 pane（pane_title_marker: CCB-Claude-xxx）
- 项目隔离：ccb_project_id（项目路径哈希）让同一项目的多 agent 共享上下文
- IPC 通道：至少 codex 用了 input_fifo/output_fifo 命名管道
- 环境变量契约：被启动的 agent 从 CCB_MANAGED=1 / CCB_PARENT_PID / CCB_RUN_DIR / CCB_CALLER 感知自己在 CCB 体系里
- 会话状态文件：仓库里的 .ccb/（.claude, codex, gemini, opencode）-session 是 CCB 写入的指针

结论：Studio Copilot 直接复用 CCB 作为 Gemini 侧的桥，不需要造轮子。但 .ccb/ 目前被签进了 git（.gitignore 漏了），这是本地 runtime 元数据，应在 hardening 任务里加到 .gitignore。

现在落盘主文档。

⚠️ API Error: Stream idle timeout - partial response received

**[用户]** 又报错了

直接落盘，不再查询。

⚠️ API Error: Stream idle timeout - partial response received

**[用户]** 又报错

拖数拖延了，直接写文件。

⚠️ API Error: Stream idle timeout - partial response received

（截图在此结束——对话被 API 超时打断，文件最终未在截图中看到写入成功）
