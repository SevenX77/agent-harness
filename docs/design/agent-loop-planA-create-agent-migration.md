---
status: Designing (架构方向已与用户拍板; 输出格式与 structured-output 两项待实证)
created: 2026-06-01
updated: 2026-06-02
owner: Engine (graph-agent)
aligns_with: ../../.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md (gateway A')
ground_truth: packages/graph-agent 实际代码 + docs/engine/mvp0/skill-spec (FROZEN)
---

# Agent Loop 迁回 `create_agent` + middleware — 决策记录（Plan A = 未执行的 PR β）

> **一句话**：迁移脚手架早就搭好了——`graph_agent.middleware` 包已有完整 6 槽 `AgentMiddleware` 链 + 工厂，`middleware/__init__.py:16-17` 自述 *"PR γ0 锁顺序契约；**PR β wires the runtime classes**"*。Plan A 就是执行这个没做完的 PR β，不是"从 deepagents/deerflow 重抄一套 loop"。
>
> **体例**：每个主题自带「现状/设计 → 决策 → 证据(file:line 就地内联) → 用户原话」。证据是我亲自读代码核实的；temp 报告/子 agent 转述只作线索，引用前用代码复核（本轮已踩过行号漂移的坑）。
>
> **与 gateway 的关系**：本文管 agent loop 的**编排**(手写 ReAct → create_agent + middleware)；gateway 走 A'（`GatewayChatModel` 编排外壳内换原生 ChatX，管单次**调用**）。create_agent 的 `model=` 吃的就是 `GatewayChatModel`，两条迁移方向一致、互补。engine 与 gateway 已独立，文档也已分开（gateway 文档在 `docs/graph-agent-gateway/`，不在本范围）。

铁律：ground truth 只认 `packages/graph-agent` 实际代码 + `docs/engine/mvp0/skill-spec`（FROZEN）。

---

## 1. Plan A 本质：手写 loop → `create_agent` + middleware

**现状**：唯一 live = `_skill_node` 手写 ReAct loop。`for _ in range(max_turns)`（`graph_assembler.py:511`）→ `model.invoke`（`:513`）→ 无 tool_calls 直接 `break`（`:527-528`，**裸退无守卫**）→ `tool.invoke`（`:546`，**无 try/except**）→ 只调 `cognitive_flow.handle_finish_task_tool_result`（`:563`，legacy 桥接方法，**没走 create_agent**）。subagent 在 `:535-544` 特判。

**决策**：把 `_skill_node` loop 体换成
`create_agent(model, tools, system_prompt, middleware=build_middleware_chain(...), checkpointer)`；保留 phase 级编译缓存/模型解析/schema 解析不动。

**为什么可行（create_agent API 安装版核实，`.venv/.../langchain/agents`）**：
- 签名支持：`factory.py:658` `create_agent(model, tools, *, system_prompt, middleware, response_format, checkpointer, ...)`。
- `return_direct` 原生退出：`factory.py:1442-1446`、`:1750-1756`。
- `system_prompt`(str|SystemMessage) 置消息首，与现 `apply_v030_cognitive_template`(入口构建一次 SystemMessage) 语义一致。
- 中间件钩子齐全：`middleware/types.py:380` `AgentMiddleware` → `before_model:430` / `after_model:454` / `wrap_model_call:478` / `after_agent:625` / `wrap_tool_call:649`。
- 重入控制：`types.py:69` `JumpTo = Literal["tools","model","end"]`；`after_agent` 装饰器带 `can_jump_to`（`:1432`）。

**用户原话**：
> "继续 graph-agent 把 agent loop 迁回 create_agent + middleware（方案 A）"
> "我之前的手写ReAct也会出问题, 现在改成chatX和create agent就没问题了"（鲁棒性收益已被用户实证——但注意这收益来自 ChatX 正确的消息处理，**不等于** structured-output 可靠，见 §9）

---

## 2. 中间件链：6 槽已搭，3 实 3 桩

**现状**：`middleware/factory.py:29` `build_middleware_chain` 按 `MVP0_MIDDLEWARE_ORDER_CONTRACT`（`__init__.py:58`，6 槽 γ0 顺序）实例化一条 `tuple[AgentMiddleware, ...]`，**正是 `create_agent(middleware=...)` 能直接吃的格式**，但 live 从未调它（live 用 `factory.py:68` 的 `build_middleware_chain_cognitive_flow`，只产 CognitiveFlow）。

6 槽里：
- **真实实现 ×3**：`CognitiveFlowMiddleware`（`cognitive_flow.py:55`，984 行，finish_task 闸 + clarification，见 §5）、`ExecutionControlMiddleware`（`execution_control.py`，343 行，迭代计数 `:120` + dead-end 检测 `:243-277` + 轻量 loop 检测）、`ProtocolValidationMiddleware`（213 行，状态契约守卫 + after-model schema 校验）。
- **no-op 空桩 ×3**：`loop_detection.py` / `tool_error.py` / `tracing.py`（各 16 行 "slot reserved"）。

**决策**：迁移 = 接线 `build_middleware_chain` 进 create_agent + 实现 3 个空桩（即 `__init__.py:16-17` 写的 "PR β wires the runtime classes"）。实现 LoopDetection 前**先核实** ExecutionControl 已覆盖的轻量 loop/dead-end，避免重复。

---

## 3. 中间件借鉴清单（从 deepagents/deerflow，MIT）

迁回 create_agent 后逐个挂；优先级与去向：

| 项 | 来源 | 当前状态 | 去向 |
|---|---|---|---|
| RubricMiddleware（退出闸/质量评分范式） | deepagents `rubric.py:425` | 范式已用于 §6 退出闸骨架 | §6 抄骨架；§12 质量层后续叠加 |
| LoopDetection（warn→hard-stop + provider-safe nudge） | deerflow | 空桩待实现（§2） | §2/§6 |
| ToolError 桥接 + **SafetyFinishReason** | deerflow | 空桩待实现（§2） | §11 止血；SafetyFinishReason = 无人值守稳定性兜底 |
| live Summarization（compaction 触发） | deepagents | langchain **已内置** `middleware/summarization.py` | 优先用内置，验证语义后接 |
| **DeltaChannel checkpoint 压缩** | deepagents | **待复核**是否真 O(N²)（与"已有 reducer"冲突） | 先核实再决定抄不抄 |
| Anthropic prompt caching | gateway 层 | 标准 prompt 本静态 | gateway `client_manager` 注入，不改 SKILL schema |
| **SubagentLimit / 子任务 lifecycle 事件 / token 细粒度归因** | deerflow | 缺 | 服务 Studio 可观测性，接 §8 trace |

---

## 4. finish_task —— 定位：模型显式调用的"提交工具"

**设计**：finish_task 是模型在 loop 内**主动调用、把最终交付物作为入参传入**的提交工具。证据：`finish_task.py:95-100`（`StructuredTool`，name="finish_task"，描述 "Submit phase final output"）、`FinishTaskInput.markdown:24`。**结构化交付物 = finish_task 的入参，不是凭空的 loop 产物。**

**决策**：**保持** finish_task 为提交工具；**不**降级为"loop 结束后从末条消息抽取再校验"的被动校验器。

**为什么（两个方案对比，用户拍板保持提交工具）**：
- graph-agent 输出是给下游 phase 消费的强结构化 BusinessData（如 `skills/global-synthesis/GRAPH.md:18-23` outputs=嵌套 object）→ **显式提交**比"从自由文本猜哪段是交付物"稳得多，契合"确定性/控制端"定位。
- 被否决的方案（模型只写最终答案、系统抽取）会引入"哪段是交付物"歧义 + 丢失显式提交信号 + 改动大。

**用户原话**：用户在"保持提交工具 / 降级为后置校验器"间明确选了**保持提交工具**。

---

## 5. finish_task —— 校验流水线 + 语义/结构错分流（Q1 核心）

**用户的问题**：
> "之前的设计理念是, 先检查有没有业务相关的字段因为格式不符合导致业务质量不过关的, 比如'评分:int', 结果输出了一个'评分:好', 业务要求打精确的分数, 结果给了一个模糊的字符, 遇到这种问题, 格式修复是没法修的, 格式修复不知道好对应几分. 所以要输出一条报错, 打回去, 告诉llm 把这个字段重新输出成对的格式. 我想问这个机制还在不在."

**核实结论：机制没丢，是 V2.1 cutover 接错线了。** 当前 repo 并存两套：

- **丰富版**（`tools/md_to_json.py`，684 行，从 AI-story-forge V1 移植，完整保留）：
  - `diagnose`（逐 item Pydantic 校验）、`error_kind: Literal["structural","semantic"]`（`:108`）、`DiagnosticReport.semantic_only`（`:140`）、`SemanticValidationError`。
  - 决策逻辑 `md_to_json()`：全合格→返回（`:557`）；**`:560` `if report.semantic_only:` → `:566 raise SemanticValidationError`**（语义错如"评分:好"→int **不进 patch、打回主 agent 重生成**）；仅"结构错"才 `:571 _extract_md_excerpt` + `:578 run_skill(md-patch)` 做 **surgical 修复**（只补失败的 ## 块）。
  - 还有 `schema_to_type_dict`（教 LLM 字段类型约束，正是 `docs/engine/mvp0/skill-spec/00-FORMAT-GROUND-TRUTH.md:329` 抱怨"prompt 没教格式"的解药）。
- **简化版**（`cognitive/md2json.py`，185 行）：只有 `parse_finish_markdown:26` + `_coerce_value:88` + jsonschema 校验（`:36-38`），**无 structural/semantic 分类**。

**问题所在**：**live finish_task 接的是简化版**——`finish_task.py:13` + `graph_assembler.py:33` 用 `cognitive/md2json.py`；`graph_assembler.py:645` 把所有 validation_error 一律送 `LLMMdPatchClient` patcher → "评分:好" 也被送去格式修复，而 patcher prompt 只说"修格式和机械类型"、**无反捏造守卫**（`md_patch.py:74-82`）→ 可能瞎编个数字骗过 schema。丰富版 `md_to_json()` 的决策逻辑成了**孤儿**（只有底层 `parse_md` 被 `cognitive_flow.py:41` / `cognitive/finish.py` / md-patch skill 复用）。

**git 溯源**：V1 丰富版（AI-story-forge）→ `c7405b7e` 合并入 agent-harness → **`a53e72ca` V2.1 hard cutover 给 finish_task 新写了简化版，没接丰富版** → 后续 round 改错误码/复杂度，"越改越不对头"。

**决策**：把 finish_task 重新接回 `tools/md_to_json.py` 的 `md_to_json()`（代码现成），恢复三态分流：全合格→返回 / 结构错→surgical md-patch / **语义错→打回主 agent 重生成（不 patch、不捏造）**；退役或合并简化版 `cognitive/md2json.py`。

（补充：业务规则错——schema 通过后由 `cognitive_flow.py:253-262` `invoke_validator_with_contract` / `:637 _run_business_validator` / `:680 _reject_finish` 驳回打回——这条 live 已有，与上面的语义/结构分流是不同层。）

---

## 6. 退出控制：结构性保证"必出合格 finish_task"

**用户的洞察**：
> "我知道为什么会产生双路线并存在engine里面了, 就是因为langchain 的 create_agent 会一声不吭就退出, 而光用nudge不一定能阻止他. 我们需要想一个办法, 确保最终会使用finish_task."

**根因**：create_agent 默认"模型不发 tool_calls → 自然 END"，会**一声不吭退出**，绕过"必须提交合格 finish_task"的硬要求；软 nudge 拦不住。手写 loop 的价值就是**自己掌控退出**。

**设计：退出权集中到一个 `after_agent` 闸（唯一放行 END 处）**——
- 已记录合格 finish_task → 放行 END；
- 模型没发 tool_calls 想裸退 → 注入 nudge + `jump_to:"model"` 强制重入（create_agent 到不了 END）；
- `max_iterations`/recursion 耗尽 → **显式报错（绝不静默吐空/坏 BusinessData）**。
- finish_task 倾向**不**用 return_direct，退出权全交 after_agent（集中式，最易论证保证）。

**现成范式直接抄**：deepagents `RubricMiddleware`（`temp/deepagents/.../middleware/rubric.py:425` `@hook_config(can_jump_to=["model"]) def after_agent`，docstring "Agent state at natural stop (no further tool calls)"；`:660-669` `return {"messages":[HumanMessage(...)], "jump_to":"model"}`；`:353/:362-363` max_iterations 默认 3、硬上限 [1,20]）——**把它的 LLM grader 判定换成 finish_task 确定性校验**即可。

**nudge 逻辑也现成**：`core/nudge_injector.py` `NudgeInjector`（`:50` planning/selfcheck/standard；`:137 try_standard` = "别光说话，用工具或 finish" = 过早退出守卫；`:88 try_selfcheck` = payload 太薄回灌），但**仅接 legacy** `phase_nodes/llm_phase_node.py:293`，live 没用 → 移植成 after_agent 闸的一部分。注入模式 live 已有先例：`execution_control.py:277` after_model 返回 `{"messages":[HumanMessage(...)]}`。

**退出四层**：
1. 业务完成：finish_task 经闸校验通过（CognitiveFlow `cognitive_flow.py:241-269`）→ 闸放行 END。
2. 防失控：`recursion_limit`（映射 `max_iterations`）或内置 `model_call_limit`。
3. 防打转：实现 LoopDetection（ExecutionControl 已有轻量版 `execution_control.py:243`）。
4. 防裸退：本节 after_agent 闸 + NudgeInjector。

**诚实边界**：没有机制能"逼" LLM 把活干好并主动 finish；能 100% 保证的只是 **phase 要么产出校验通过的 finish_task，要么响亮失败，绝不静默退出**。重入语义已确认可跑（`types.py:69` JumpTo 含 "model" + `:1432` after_agent can_jump_to + Rubric 生产实践）。

---

## 7. subagent 调度 → `wrap_tool_call` 中间件

**现状**：手写 loop 在 `graph_assembler.py:535-544` 特判 subagent 工具，调 `_invoke_subagent_tool_t21`（`:1057`）——做：深度守卫 `assert_subagent_depth_allowed`、入参校验带重试 `validate_subagent_tool_args`、子图 `runtime.graph.invoke`、数据增量 `_dict_delta`、child_flow 传播。

**决策**：把这套逻辑移进一个 `wrap_tool_call` 中间件。state/flow 经 `request.state` 取（CognitiveFlow 已用 `_workflow_state_or_none(request.state)` 验证可行）。范式：deepagents `SubAgentMiddleware`（`temp/deepagents/.../graph.py:51,189`，subagent 经 `task` 工具、中间件托底）。

---

## 8. 可观测性 / trace 覆盖（流式 + 完整性 + 去黑盒）

**用户的要求**：
> "所有这些结束流程是否都有trace追踪每一步做了什么? 让我在前端面板能够看到. 这也是之前没有讨论到的一个重要话题(流式输出和trace的完整性、覆盖率, 去黑盒)"

**现状（核实）**：
- 事件类型丰富、前端就绪：`callbacks/events.py` 定义 32 类（`ValidationFailEvent:91` / `ValidationPassEvent:280` / `FinishTaskEvent:105` / `NudgeEvent:112` / `RetryEvent:98` / `DeadEndPrunedEvent:134` / `AgentLoopIterationEvent:359` …）；前端 trace-inspector 消费 `trace.jsonl`（`.kiro/specs/studio-feature-trace-inspector/requirement.md:36`）。
- **黑盒区**：`cognitive_flow.py` / `finish_task.py` / `cognitive/md2json.py` / `cognitive/md_patch.py` **全无 emit**（grep 实证为空）→ md→json、schema 闸、patcher 修复、business_validator 这些结束步骤在 trace 里**看不到**；`FinishTaskEvent`/`ValidationFail-Pass`/`NudgeEvent` 多类**定义了却没在 live 发**（NudgeEvent 只在 legacy 接线）。
- loop 级事件 live 有发：`graph_assembler.py:305 PhaseStart` / `:314 PhaseEnd` / `:515 LLMCall` / `:547 ToolCall` / `:852 Subagent`。

**决策（一等需求 + 迁移验收标准）**：
1. 实现 TracingMiddleware，把现在内联发的 loop 级事件（LLMCall/ToolCall/iteration）补进中间件——**否则迁到 create_agent 后这些事件会消失、覆盖率不升反降**。
2. 给 finish_task 校验流水线每步补发事件（FinishTaskEvent / ValidationFail-Pass / RetryEvent / NudgeEvent），消灭黑盒。
3. 流式：退出闸的重入/nudge/打回也发事件，前端实时可见。
4. 验收：迁移后 trace 覆盖**不回归**且校验子步骤可见。

---

## 9. 输出格式：保留 md2json+patcher；structured-output 仅作待测优化

**用户的质疑**：
> "你说的'靠 provider 的 tool-calling / structured-output 直接产出 schema 合法的 typed JSON', 真的靠谱吗? 之前为什么写着么一套东西, 就是因为 anthropic的模型没问题, 写json几乎不会错; deepseepv3.2、 seed2.0、Gemini 3.1 flash, 经常报错, 或者不报错但是在输出结果里面夹着各种奇怪的转译符. 我当然也想如果你说的成立那该多好, 但是需要测试."

**决策**（纠正我此前的过度承诺）：
1. **暂留 `md → md2json → schema → patcher` 这套**，不因"理论上 provider 能直接产 typed JSON"就删。
2. **structured-output（typed tool args）= 每模型需实测的优化项**，不是已拍板的替换。
3. **yaml 否决**：缩进敏感 + 标量歧义（`no`→False）+ 多行散文字段难写，对"嵌套+叙事"内容只是把脆弱点挪位、照样要兜底。

**理由**：
- 用户实证：Anthropic 写 JSON 几乎不错；DeepSeek v3.2 / Seed 2.0 / Gemini 3.1 flash 经常报错或夹转义符。md+patcher 正是为弱模型做的 provider-agnostic 兜底层。
- gateway 决策记录印证 provider 异质性：deepseek 要 `PatchedChatDeepSeek` 子类、thinking 归一化、`ProviderProfile` 表（`client-layer-decision-record.md` F4/F6）。
- **解耦**：迁移的鲁棒性收益来自 ChatX 正确的消息处理（修掉手写转换空-content bug，`gateway_chat_model.py:661-692`），**不等于** structured-output 可靠。两件事分开（见 §1 用户原话注）。

---

## 10. prompt 减负（spec 06 FROZEN）

**用户的洞察**：
> "既然rubric能够稳定拦截, 那么提示词就不用一直强调要调用finish task了吧?"

**决策**：§6 的 after_agent 闸结构性保证"不交不让退"后，prompt **不必反复唠叨**"记得调 finish_task"；只需**定义一次**（怎么提交 + 输出格式）。但"输出格式/schema"说明**不可全删**（校验需结构化输入）。**注意：动 prompt = 动 spec 06（FROZEN，`docs/engine/mvp0/skill-spec/06-cognitive-template-spec.md:53,67`），是单独的解冻决策项。**

---

## 11. 止血两项（并入 Plan A）

1. **工具异常崩 phase**（`graph_assembler.py:546` `tool.invoke` 无 try/except）→ 用 create_agent `ToolNode` 的 `handle_tool_errors` + 实现 `ToolErrorHandlingMiddleware` 桥接成 error ToolMessage（`types.py:660` wrap_tool_call docstring 确认 "Exceptions propagate unless handle_tool_errors configured"）。
2. **红旗：prompt 让调但 live 没绑**（`log_ambiguity`/`ask_clarification`）→ 模型照做会撞 `graph_assembler.py:533` `_graph_fatal("unknown tool")` 崩 phase → 把这俩绑进 create_agent 的 `tools`（ask_clarification 的副作用 CognitiveFlow 已托管）。

---

## 12. 质量层（RubricMiddleware）——后续增量

不入本轮。但记录：它与 §6 的 finish_task 闸**同构**（都是 `after_agent` + `jump_to:"model"` + max_iter 兜底），后续可串联为独立质量层——finish_task 闸管"交没交合格作业"（确定性），Rubric 闸管"作业够不够好"（LLM grader）。finish_task 闸的确定性校验比 Rubric 的"LLM 当裁判"更硬，所以先把确定性保证做扎实，质量层后置。

---

## 13. 待实证（实跑验证后再拍，不凭理论）

- **D-test-1 structured-output 跨模型可靠性**（决定 §9 走向）：**优先测最差的模型**（DeepSeek v3.2 / Seed 2.0 / Gemini 3.1 flash）——目标是"改了之后弱模型还能用"，不是"好模型更好"。经 gateway 实际 `RouteChatModelFactory` 路径测（非裸 SDK），看支持度/稳定性/转义污染率。弱模型过不了就**不能**全量切。
- **D-test-2 create_agent 重入（jump_to）端到端**：after_agent 返回 `{"jump_to":"model"}` 在我们装的版本 + GatewayChatModel 下确实重回 model 而非 END；finish_task 不用 return_direct 时与 after_agent 闸的协同。
- **D-test-3 与 gateway A' 的 model 协同**：`create_agent(model=GatewayChatModel(...))` 下编排(fallback/probe/熔断) + ChatX 调用 + middleware 三者协同；usage/metadata/thinking blocks 不丢。

---

## 14. 对齐 gateway A'

- gateway 走 **A'**：保留 `GatewayChatModel` 编排外壳，只把单次调用换原生 ChatX（`client-layer-decision-record.md` D1/D2）。
- 接口：create_agent 的 `model=` = `GatewayChatModel`；agent loop 不关心 provider 细节，provider 异质性由 gateway 的 `RouteChatModelFactory` + `ProviderProfile` 吸收（gateway M6/F6）。
- 正交：gateway 管"单次调用怎么打通各 provider"；本文管"loop 怎么编排 + 怎么保证 finish_task + 怎么 trace"。

---

## 15. Out-of-scope / 待用户

- prompt（spec 06 FROZEN）实际改写文本 —— 需解冻决策（§10）。
- §9 输出格式最终走向 —— 待 D-test-1 实测后拍。
- Rubric 质量层（§12）—— 后续增量。
- 前缀缓存 —— gateway 层，不在本迁移。
- **未覆盖、需逐一对照新设计确认有无冲突**：predict（mock 移出 gateway 后引擎侧 agent loop 怎么跑）、subagent lifecycle（SkillResolverProtocol DI）、checkpointer × middleware 交互。
