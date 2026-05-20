# graph-agent 引擎合并审计报告

署名：Codex
日期：2026-05-20
范围：`/home/sevenx/coding/agent-harness/packages/graph-agent`
状态：合并版 / 权威恢复版

> 恢复说明：原文件被删除后，本文件按本轮对话中的最终审计结论、补丁记录和复核意见重建。内容覆盖最终版的技术结论、已验证 bug、A1-A8 架构缺口、PR 拆分和优先级；不保证与被删文件逐字节完全一致。

## 合并来源

本报告合并了三部分信息：

1. Codex 审计报告：`graph-agent-audit-by-codex-2026-05-20.md`
2. Claude Opus 4.7 审计报告：`graph-agent-engine-audit__by-claude-opus-4.7.md`
3. Claude 对 Codex 关键发现的二次实测反馈，以及后续用户提出的 IO contract / graph isolation 架构问题

整体判断：

- Claude 的原报告更擅长说明编译流程、装配机制、错误码、纯净性扫描、critic/md_patch 链路。
- Codex 的原报告更擅长抓运行时主路径 bug，并跑了实测。
- 二次实测确认 Codex 抓到多个 Claude 初版漏掉的真 bug，其中 `run_skill()`、`shallow_dict_merge`、cache、subagent depth、exit_contract 都属于 V2.1 主路径问题。
- 用户后续指出的 runtime input funnel、phase-level IO、subagent/subgraph 隔离，是 V2.1 下一轮架构收口的核心。

## 一句话结论

`graph-agent` 当前已经从旧的单文件 `SKILL.md` / `GraphAgentHarness` 时代切到 V2.1 目录型 skill + LangGraph runtime，但迁移边界没有收口。

真实运行链路是：

```text
run_skill(skill_root)
  -> compile_skill(root)
  -> SkillLoader.compile_skill(root)
  -> assemble_graph(compiled, chat_model=...)
  -> LangGraph graph.invoke({data, flow, messages, run_id})
```

V2.1 loader 和 graph assembler 的主体已经成型，但 public runner、状态合并、cache、subagent runtime、callback/trace、文档、测试隔离、IO contract、graph isolation 都没有完全收口。

现在最危险的不是某段旧代码存在，而是用户以为自己在使用完整 SDK，实际跑到的是一个功能尚未完全接线、数据模型尚未稳定的新 runtime。

## 当前真实运行逻辑

### V2.1 skill 目录结构

当前真实支持的 skill 形态是目录，不是单个 `SKILL.md` 文件：

```text
skill_root/
├── GRAPH.md
├── io/
│   ├── inputs.json
│   └── outputs.json
└── phases/
    └── <phase_id>/
        ├── LOGIC.md
        ├── SUBGRAPH.md
        └── SKILL.md
```

每个 phase 目录只能有 `LOGIC.md`、`SUBGRAPH.md`、`SKILL.md` 三者之一。

- `GRAPH.md`：声明整体拓扑、输入输出 schema、phase 顺序和依赖。
- `LOGIC.md`：纯 Python action，不调用 LLM。
- `SKILL.md`：LLM ReAct phase，模型调用 tools，最后调用 `finish_task`。
- `SUBGRAPH.md`：递归调用另一个 skill 子图。
- `io/inputs.json`：输入 JSON Schema。V2.1 当前主要做编译期 schema 合法性校验；其 properties 会参与 `ctx.update(...)` / `context.update(...)` 的上下文字段允许集，但不参与 `finish_task` 校验。
- `io/outputs.json`：输出 JSON Schema。用于 `finish_task` Markdown -> JSON 的结果校验、LOGIC action `return {...}` 写键校验，以及运行时 `_validate_logic_update_keys` 校验。

### 编译流程

`compile_skill(root)` 主要做这些事：

1. 守卫 skill root：必须是目录，必须有 `GRAPH.md` 和 `phases/`，根目录不能再是旧 `SKILL.md`。
2. 解析 `GRAPH.md`：读取 frontmatter、`<input />`、`<output />`、`<phase />`。
3. 校验拓扑：phase id 去重、自环、环、孤岛、`depends_on`、src 越界。
4. 校验 `io/*.json`：要求合法 JSON Schema Draft 2020-12。
5. 解析每个 phase AST：`LogicNodeAST` / `SubgraphNodeAST` / `SkillNodeAST`。
6. 发现 actions/tools：按 LOGIC/SKILL 的目录规则加载 Python 函数。
7. 纯净性扫描：禁止 tools/actions 做直接文件写入、危险 os/shutil/tempfile 操作等。
8. action 写键校验：静态扫描 `return {...}` 和 `ctx.update(k=v)`。`return {...}` 只能写 output schema key；`ctx.update(k=v)` / `context.update(k=v)` 的允许集来自 input + output schema properties。
9. 编译 subagent metadata，并为父级 SKILL 注入 `call_subagent_<name>` 工具。
10. 可选写编译 cache。

### 装配和执行流程

`assemble_graph(compiled, chat_model=...)` 把 `CompiledSkill` 翻译成 LangGraph：

```text
CompiledSkill
  -> StateGraph(BlackboardState)
  -> 每个 phase 一个 node
  -> depends_on 转成 LangGraph edge
  -> terminal phase 连到 END
```

三类 node 行为：

- LOGIC node：复制 `state.data`，构造 `Context`，运行 action，返回 data delta。
- SUBGRAPH node：递归 compile + assemble 子 skill，调用子图，再把子图 data delta 合回父图。
- SKILL node：构造 system prompt + messages，每轮注入 exit_contract，调用模型，执行 tools/subagents/finish_task。

`BlackboardState` 当前字段：

```python
class BlackboardState(TypedDict, total=False):
    data: Annotated[dict[str, Any], shallow_dict_merge]
    flow: dict[str, Any]
    messages: Annotated[list[AnyMessage], add_messages]
    run_id: str | None
```

人话解释：

- `data` 是业务数据黑板。
- `flow` 是框架控制数据。
- `messages` 是 LLM 对话历史。
- `run_id` 是一次执行的标识。

## 已验证关键 bug 表

### P0-1. `run_skill()` V2.1 真实 LLM 路径跑不起来

位置：

- `packages/graph-agent/src/graph_agent/core/runner.py:451`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:233`

现象：

```python
run_skill("tests/fixtures/subagent_minimal")
```

不传 `mock_llm` / `chat_model` 时，遇到 SKILL phase 会直接抛：

```text
RuntimeError: [F-v21-graph] SKILL phase requires chat_model
```

严重性：

- 这不是普通文档瑕疵，而是 public `run_skill()` 入口无法跑真实 V2.1 LLM skill。
- 该异常不是 `GraphAgentError`，不会被当前 `run_skill()` 的错误包装稳定处理。
- Claude 初版只说“没有自动接 ModelResolver”，严重性低估。

修复方向：

- V2.1 `run_skill()` 要么接入 `ModelResolver`，无 mock 时能解析真实模型。
- 要么明确公开 API 要求调用者传 `chat_model`，并把错误变成清晰的 `WorkflowResult(success=False)` 或 `GraphAgentError`。
- 同时需要明确 callbacks、trace、artifact、unattended 等参数在 V2.1 是否支持。

### P0-2. README Quick Start 示例不可用

位置：

- `packages/graph-agent/README.md:68`
- `packages/graph-agent/src/graph_agent/core/loader.py:224`

现象：

README 仍教用户运行单文件：

```python
run_skill("packages/graph-agent/src/graph_agent/examples/hello_world/SKILL.md")
```

但 loader 当前只接受 V2.1 skill root 目录。单文件 `SKILL.md` 会被拒绝。

修复方向：

- README 改成 V2.1 目录型示例。
- `examples/hello_world` 迁移到 `GRAPH.md + io + phases`。
- 如果保留旧示例，必须标注为 legacy，不再放 Quick Start。

### P0-3. `shallow_dict_merge` 把顺序覆盖也当成冲突

位置：

- `packages/graph-agent/src/graph_agent/runtime/state.py:13`
- `packages/graph-agent/src/graph_agent/runtime/state.py:26`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:155`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:166`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:508`

现象：

```python
shallow_dict_merge({"foo": 1}, {"foo": 2})
```

会抛：

```text
[F-v21-state-conflict] key='foo'
```

这本来是为了阻止并行分支写同一个 key，但 LangGraph reducer 在顺序 phase 更新已有 key 时也会触发。LOGIC node 通过 `_dict_delta(before, after)` 返回 delta，只要 action 正常更新已有 key，就可能被 reducer 当成冲突。

SUBGRAPH node 也会撞同一个问题：`_build_subgraph_node()` 会用 `_dict_delta(before_data, result_data)` 算子图输出 delta，然后把 `{"data": data_updates}` 交给父图 reducer。子图只要写了任何与父图 `data` 重名的 key，也会在出子图时触发同样冲突。

严重性：

- 任何 phase 出口都难以正常修正或覆盖已有字段，不只 LOGIC，SUBGRAPH 回写父图也会受影响。
- 业务里常见的“清洗输入”“补全字段”“更新状态”会失败。
- Claude 初版只覆盖了“并行分支冲突”设计，没有意识到顺序覆盖也会触发。

修复方向：

LangGraph reducer 在顺序图和并行图里都会被调用，不能指望 `shallow_dict_merge()` 自己识别“这是顺序更新还是并行 fan-in”。修复前需要先选定 state 策略。

可选方案：

- 方案 A，最小改动：`data` reducer 改成 right 覆盖 left；同时在编译/装配期基于静态拓扑识别“可能并行写同一 key”的 fanout 汇合点，对这些汇合点挂并行专用冲突检测 wrapper。
- 方案 B，state shape 拆分：把 `data` 拆成只读 `inputs` + `phase_outputs[phase_id]`，每个 phase 写自己的桶，reducer 只按 phase_id 合并。业务字段跨 phase 读取时走显式解析逻辑。这会强制隔离并行写冲突，但改动更大。
- 方案 C，LangGraph 原生 channel：研究是否能使用 LangGraph channel / reducer / super-step 信息区分同一 super-step 内的并行写和跨 super-step 的顺序写。需要先确认当前 LangGraph 版本是否暴露足够的 super-step 或 channel 元数据。

建议 PR 前先用一个小 spike 比较 A/B/C。若目标是尽快恢复现有 API，优先评估方案 A。

### P1-1. 编译 cache 丢 `subagents_by_phase` 和 `phase_tokens`

位置：

- `packages/graph-agent/src/graph_agent/core/cache.py:84`
- `packages/graph-agent/src/graph_agent/core/cache.py:102`
- `packages/graph-agent/src/graph_agent/core/cache.py:120`

现象：

`_dehydrate_compiled_skill()` 只保存：

```text
raw
manifest
nodes
```

`_rehydrate_compiled_skill()` 只恢复：

```text
actions
tools
```

没有恢复：

```text
subagents_by_phase
phase_tokens
```

实测结果：

```text
fresh compile:
  subagents_by_phase = ['main']
  tools = {'main': ['call_subagent_echo_expert']}

cache hit:
  subagents_by_phase = []
  tools = []
```

严重性：

- cache hit 会改变运行行为。
- subagent 技能第一次能跑，第二次可能找不到动态注入工具。
- 这是正确性问题，不是性能问题。

修复方向：

- cache snapshot 保存并恢复 `subagents_by_phase` 和 `phase_tokens`。
- 或 cache hit 后重新执行 subagent metadata 编译和工具注入。
- 为 `tests/fixtures/subagent_minimal` 增加 cache hit 回归测试。

### P1-2. subagent depth 只写进 config metadata，没有写回 child flow

位置：

- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:321`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:400`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:482`

现象：

深度检查读的是：

```python
current_subagent_depth(flow)
```

但子图调用时传入：

```python
"flow": parent_state.get("flow", {})
```

新增深度只写在 `RunnableConfig.metadata["subagent_depth"]`，没有写进 child graph 的 `flow["subagent_depth"]`。

严重性：

- `MAX_SUBAGENT_DEPTH=1` 可能没有真正限制住嵌套子 agent。
- 子 agent 内部再次调用子 agent 时，可能仍看到旧 flow。
- 成本、死循环、递归膨胀风险增加。

修复方向：

- `_invoke_subagent_once_t23()` 构造 child state 时写入：

```python
import copy

child_flow = copy.deepcopy(parent_flow)
child_flow["subagent_depth"] = depth + 1
```

- 实施时要让 `_invoke_subagent_once_t23()` 能拿到明确的 `depth`，例如显式传参；不要只把深度放在 `RunnableConfig.metadata` 里。
- 注意 `flow` 里可能有嵌套 dict，例如 `subagent_validation_retries`。只做浅拷贝会让子图修改反向污染父图状态，因此更稳妥的是 `deepcopy` 或按字段显式复制。
- 增加真实嵌套 subagent 集成测试。

### P1-3. V2.1 SKILL node 每轮 ReAct 都把 exit_contract 写进历史

位置：

- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:243`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:246`

现象：

当前循环：

```python
prompt_messages = inject_exit_contract(messages, phase_ast.exit_contract)
response = model.invoke(prompt_messages)
messages = [*prompt_messages, response]
```

因为 `prompt_messages` 被保存回 `messages`，下一轮会在已有 exit_contract 后再追加一份。

实测：

```text
turn 0: exit_contract copies = 1
turn 1: exit_contract copies = 2
turn 2: exit_contract copies = 3
```

严重性：

- prompt 随轮次膨胀。
- 重复 instruction 增加噪声。
- 长任务里可能影响模型行为和 token 成本。

修复方向：

- exit_contract 只在 `model.invoke()` 前临时注入，不写入 `messages`。
- 或给 exit_contract message 标记，下一轮替换，不追加。

### P1-4. V2.1 主线没有接 callbacks / trace / heartbeat 等旧 harness 能力

位置：

- `packages/graph-agent/src/graph_agent/core/harness.py`
- `packages/graph-agent/src/graph_agent/core/runner.py:451`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py`

现象：

旧 `GraphAgentHarness` 支持：

- callbacks
- heartbeat
- checkpoint / resume
- tracing
- IOManager
- working memory
- nudge loop
- validation retry
- artifact saver

但 V2.1 `run_skill()` 直接：

```text
compile_skill -> assemble_graph -> graph.invoke
```

不走旧 harness。

严重性：

- 文档和 API 参数承诺与真实行为不一致。
- Studio 或上层调用方拿不到 V2.1 phase 级事件。
- 老代码还在，容易误导维护者。

修复方向：

- 明确 V2.1 runtime owner。
- 把需要保留的能力迁移到 V2.1 graph runtime。
- 旧 harness 如果保留，标为 legacy/internal。

### P2-1. legacy `CognitiveFlowMiddleware` 可能没有真正拦截 `finish_task`

位置：

- `packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py:311`
- `packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py:428`
- `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:134`
- `packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py:217`

现象：

legacy `LLMPhaseNode` 注释说 `finish_task` 由 `CognitiveFlowMiddleware` 拦截校验。但实际调用 agent 时只传：

```python
{"messages": current_messages}
```

没有传完整 `WorkflowState`。middleware 拿不到 state 后会 pass-through。

严重性：

- legacy 路径里 schema/business validator 可能没有按注释执行。
- 如果 legacy harness 要继续维护，这属于真实逻辑缺口。
- 如果 legacy 要清理，则此项可降优先级。

修复方向：

- 保留 legacy 时，agent state 必须包含 `data/flow/messages`。
- 注意：LangChain `create_agent` 默认 state schema 通常只含 `messages` channel。实际修复不是简单把 `agent.invoke({"data": ..., "flow": ..., "messages": ...})` 传进去，因为额外 key 可能被 schema 丢弃。要么通过 `create_agent(state_schema=...)` 扩展 state schema，要么使用当前 LangChain 版本支持的 ChannelOverride / 等价 channel 注入机制把 `data`、`flow` 注册成合法 channel。
- 加测试证明非法 `finish_task` 会被 middleware 拒绝。
- 若不保留 legacy，文档里不能再把它描述为 canonical runtime。

### P2-2. cache 默认写 `~/.cache/graph-agent-v21`，写失败没有降级

位置：

- `packages/graph-agent/src/graph_agent/core/cache.py:18`
- `packages/graph-agent/src/graph_agent/core/cache.py:45`

现象：

`save_to_cache()` 直接：

```python
cache_dir.mkdir(parents=True, exist_ok=True)
cache_file.write_text(...)
```

没有 try/except。只读 HOME、容器、沙箱环境里可能让 compile/run 失败。

修复方向：

- cache 写失败降级为 no-cache，最多 warning。
- 支持环境变量指定 cache dir。
- `compile_skill(cache=True)` 不应因为缓存不可写失败。

### P2-3. 测试 xpass 数量暴露迁移隔离状态

实测全量：

```text
930 passed, 3 skipped, 50 xfailed, 53 xpassed
```

位置：

- `packages/graph-agent/tests/conftest.py:72`

问题：

- `53 xpassed` 表示很多“预计失败”的测试实际已经通过。
- 因为 `strict=False`，CI 不会把这些 xpass 当问题。
- 这会掩盖迁移状态，降低测试信号。

修复方向：

- 清理已经 xpass 的测试。
- 对继续隔离的测试注明 owner 和退出条件。
- 核心 V2.1 测试使用 `strict=True`。

### P2-4. public API 数量和文档不一致

位置：

- `packages/graph-agent/README.md`
- `packages/graph-agent/src/graph_agent/__init__.py:3`
- `packages/graph-agent/src/graph_agent/__init__.py:48`

事实纠正：

- README 写 public API 是 12 个。
- `__init__.py` docstring 写 13 个。
- 实际 `__all__` 是 17 个。
- Claude 初版写 16 个是错的。
- Codex 初版文档曾写 18 个，也已修正为 17 个。

修复方向：

- README 和 `__init__.py` docstring 同步到实际 `__all__`。
- 明确哪些是稳定 API，哪些是 V2.1 暂时暴露的编译/装配接口。

## 新增架构缺口：IO contract / graph isolation redesign

以下是二次讨论后补充的架构级问题。它们不是单个函数 bug，而是 V2.1 下一轮收口必须解决的设计缺口。

### A1. 缺少 runtime input funnel

当前覆盖情况：

- engine-flow 文档已经说明：`run_skill(**inputs)` 不会按 `io/inputs.json` 校验，也不会过滤 runtime 参数。
- 原 audit 没把它列成独立问题。

问题：

当前入口基本是：

```text
run_skill(**inputs)
  -> data = dict(inputs)
```

这意味着：

- 未声明字段也会进入 `data`。
- 类型错误不会在入口被拦住。
- 默认值、规范化、未知字段策略都没有统一入口。
- 后续 phase 看到的是未经漏斗处理的原始数据。

建议方向：

增加 runtime input funnel：

```text
raw kwargs
  -> io/inputs.json validate
  -> filter / reject / normalize
  -> canonical initial data
```

需要明确策略：

- 未声明字段是 reject、drop 还是 warning。
- 是否按 schema 做默认值填充和类型 coercion。
- funnel 后的 data 是顶层字段，还是进入 `inputs` 分区。

### A2. 所有节点读全量 data，缺少 phase-level IO contract

当前覆盖情况：

- engine-flow 文档说明了当前共享黑板模型。
- audit P0-3 的方案 B 提到 state shape 拆分，但没有把“全节点读全量 data”作为独立架构问题。

问题：

当前所有 phase 默认能看到完整 `state.data`。这会带来：

- 每个节点输入不清晰。
- 下游节点可以隐式依赖任何上游字段。
- phase 之间的真实数据依赖无法从 `GRAPH.md` 静态看出来。
- 大型流程里 `data` 会越来越膨胀，节点读到大量冗余字段。
- 并行冲突、顺序覆盖、字段命名污染会越来越难排查。

建议方向：

引入 phase-level IO contract：

```text
phase.input
  <- 从上游 phase output / initial inputs 显式映射

phase.output
  -> 只允许写该 phase 声明的 output dict
```

更理想的 state 形态：

```text
inputs: 入口输入，只读
phase_outputs[phase_id]: 每个 phase 自己的输出桶
phase_input: 当前 node 执行时临时组装出的输入 dict
```

人话：

> 每个节点不应该默认拿整张黑板，而应该拿“这个节点被声明允许看到的那一份数据”。

### A3. SUBGRAPH 修改父图已有 key 的具体触发场景

当前覆盖情况：

- audit P0-3 已经标注：SUBGRAPH 通过 `_dict_delta(before_data, result_data)` 回写父图时，修改父图已有 key 会触发 `shallow_dict_merge` 冲突。

需要补清楚的场景：

SUBGRAPH 修改父图已有 key 主要发生在：

1. 子图 LOGIC action 里 `ctx.set("existing_key", new_value)` 或 `ctx.update(existing_key=...)`。
2. 子图 LOGIC action `return {"existing_key": new_value}`。
3. 子图 SKILL phase 的 `phase_id` 与父图已有顶层 key 重名，`finish_task` 成功后写 `data[phase_id]`。
4. 子图内再调用 SUBGRAPH，孙图最终改了父图已有 key。
5. 父图把全量 data 传给子图后，子图把某个输入字段当成本地工作字段覆盖。

根因：

当前 SUBGRAPH 初始 state 是父图完整 `data`，子图运行后再和父图运行前做 diff。它没有独立输入输出边界。

建议方向：

如果保留 SUBGRAPH phase 作为流程级编排，应给 SUBGRAPH 明确：

```text
subgraph_input_mapping
subgraph_output_mapping
```

或者要求子图输出只能写入：

```text
phase_outputs[parent_subgraph_phase_id]
```

避免子图直接污染父图顶层 key。

### A4. subagent 抽象层级需要重设

当前覆盖情况：

- audit 已标注当前 subagent 的 cache、depth、tool 注入问题。
- engine-flow 已说明当前 subagent 必须是完整 V2.1 skill root。
- 但之前没有覆盖“subagent 应该如何重新设计”的架构方向。

当前问题：

现在 subagent 需要用户提供完整 skill root：

```text
subskills/name/
  GRAPH.md
  io/inputs.json
  io/outputs.json
  phases/.../SKILL.md
```

这对“agent phase 内的子 agent”来说太重。用户本质上只想声明一个单节点 agent phase，却被迫手写外围 graph 包装。

建议方向：

subagent 应定义为“单节点 agent phase 规格”：

```text
subagents/name/
  SKILL.md
  tools/
  assets / prompts / examples 等业务相关文件
```

外围包装由 engine 自动生成：

```text
auto GRAPH.md
auto io/inputs.json
auto io/outputs.json
auto phases/<name>/SKILL.md
```

同时，调用 subagent 的能力应模块化进 engine 自带 tools 系统，而不是散落在 loader/assembler 中为每个 subagent 拼临时工具逻辑。

目标：

- subagent 对用户是轻量 agent phase。
- 对 engine 内部仍可包装成完整 graph 运行。
- `call_subagent_<name>` 是 engine-provided tool 类型的实例化结果，而不是业务作者手写 tool。

### A5. agent phase 需要 call_subgraph 工具

当前覆盖情况：

- 之前 audit 只覆盖了 SUBGRAPH phase 和 subagent tool。
- 没有覆盖“agent phase 内调用完整 graph skill”的需求。

当前能力缺口：

现在有两种 graph 调用：

- `SUBGRAPH phase`：流程走到该节点自动调用子图。
- `subagent tool`：agent phase 里调用子 agent，但当前语义偏单 agent 子任务。

缺少第三种：

```text
agent phase 里由 LLM 主动调用完整 graph skill
```

建议方向：

在 agent phase 目录下，与 subagent 同级增加 subgraph 声明目录，例如：

```text
phases/main/
  SKILL.md
  subagents/
  subgraphs/
    research_flow/
      SUBGRAPH.md
      graph_skill/
        GRAPH.md
        io/
        phases/
```

父 `SKILL.md` 可声明：

```yaml
phase_config:
  subgraphs:
    - name: research_flow
      path: subgraphs/research_flow
      description: Run the research workflow.
```

engine 注入：

```text
call_subgraph_research_flow
```

语义：

- subagent：轻量单 agent 子任务。
- call_subgraph：完整 graph skill 子流程，LLM 主动决定何时调用。
- SUBGRAPH phase：流程固定节点，执行到这里必跑。

### A6. agent-called graph 必须和父 graph 黑板隔离

当前覆盖情况：

- engine-flow 说明了当前 subagent 子图初始 data 是 `parent_data + input_item`。
- audit 没把它定性为架构缺陷。

问题：

当前 subagent 调用时：

```text
child_data = parent_data + explicit_input
```

这会导致：

- 子 graph 可以隐式读取父 graph 全量黑板。
- 子 graph 依赖不透明，无法从子 graph 输入 schema 看出来。
- 子 graph 字段和父 graph 字段可能重名。
- 子 graph 内部状态可能被父图污染。
- 后续要做权限、最小上下文、可复用 graph 时会变困难。

建议方向：

凡是在 agent phase 里调用的 graph，包括 subagent 和 call_subgraph，都应该默认隔离黑板：

```text
child_data = explicit_tool_input_only
```

父 graph 数据只能通过显式 tool args / input mapping 进入子 graph。

返回也不应自动合回父 graph，只作为 tool result 交给父 LLM，由父 LLM 决定是否通过 `finish_task` 汇总。

### A7. agent phase / subagent SKILL.md 头部必须声明 io dict

当前覆盖情况：

- 之前文档只覆盖了根级 `io/inputs.json` / `io/outputs.json`。
- 没有要求 agent phase 或 subagent `SKILL.md` 自己声明 IO。

问题：

如果 agent phase 没有 phase-level IO：

- LLM phase 需要哪些输入不清楚。
- `finish_task` 输出结构不清楚，尤其是非终点 SKILL phase。
- subagent 的 tool args schema 只能依赖子 skill root 的 `io/inputs.json`，无法从单节点 agent phase 自洽生成。

建议方向：

要求 agent phase、subagent 的 `SKILL.md` frontmatter 必须声明 `io` dict：

```yaml
---
mode: skill
name: analyze
io:
  inputs:
    clean_text:
      type: string
      required: true
  outputs:
    summary:
      type: string
      required: true
---
```

engine 可据此生成：

- phase input schema。
- phase output schema。
- subagent tool args schema。
- `finish_task` 校验 schema。
- graph-level IO 对齐校验。

### A8. 需要图级 IO 数据流校验，保证无冲突

当前覆盖情况：

- audit 已覆盖 action 写键校验、`finish_task` 校验、reducer 冲突。
- 但这些都是局部校验，不是整张图的数据流校验。

需要补的能力：

编译期应检查整张图的 IO contract：

```text
initial inputs
  -> phase input requirements
  -> phase outputs
  -> downstream phase inputs
  -> terminal outputs
```

至少校验：

- 每个 phase required input 都能从 initial inputs 或 upstream outputs 找到。
- 下游读取字段必须由上游声明产出。
- 并行分支不能写同一 output key，除非显式允许 merge。
- phase output 不能写未声明字段。
- SUBGRAPH / call_subgraph 的输入输出映射必须和被调 graph schema 对齐。
- subagent / call_subgraph tool args 必须和被调对象 input schema 对齐。
- terminal outputs 必须能由终点 phase 或映射规则产生。

目标：

> 冲突和缺字段尽量在 compile 阶段报出来，而不是等运行到 reducer、finish_task 或 LLM tool call 才暴露。

建议把 A1-A8 作为一个独立设计主题：

```text
V2.1 IO Contract & Graph Isolation Redesign
```

它应优先于大规模 legacy 清理，并且应在修完 P0-1 / P0-3 后尽早定设计，否则后续 subagent、SUBGRAPH、callback、trace 都会继续围绕不稳定的数据模型打补丁。

## 需要保留的 Claude 机制细节

Claude 原报告里以下内容应保留进后续工程文档：

1. `GRAPH.md` 拓扑校验规则：重复 id、自环、环、孤岛、src 越界。
2. `LOGIC.md` / `SUBGRAPH.md` / `SKILL.md` 三选一和 mode 匹配规则。
3. actions/tools 目录约束：LOGIC 只能 actions，SKILL 只能 tools/subskills，SUBGRAPH 禁止。
4. 纯净性扫描清单：文件写入、Path 写操作、危险 os/shutil/tempfile 等。
5. action 写键编译期校验：`return {...}`、`ctx.update(k=v)` 和 output schema 对齐。
6. 错误码前缀：`F-v21-route`、`graph`、`io`、`actions`、`actions-keys`、`purity`、`state-conflict`、`md2json`。
7. critic/reviewer/auditor 工具按名字关键词自动包装。
8. `finish_task` 的 Markdown -> JSON -> JSON Schema -> md_patch 重试链路。
9. subagent 工具名规则：`call_subagent_<name>`。
10. `messages` 用 LangGraph `add_messages` reducer 累积。
11. LOGIC / SUBGRAPH node 通过 `_dict_delta(before, after)` 在出口产生 data delta，只回传变化的 key。这与 `shallow_dict_merge` reducer 联用，是 P0-3 顺序覆盖冲突的根因。
12. 关键运行常量：`MAX_REACT_TURNS = 8`、`MAX_SUBAGENT_DEPTH = 1`、`MAX_SUBAGENT_SCHEMA_RETRIES = 10`、subagent 批量调度 `asyncio.Semaphore(3)`、`finish_task` 默认 `max_patch_attempts = 3`。

这些是“代码怎么设计”的重要知识，但不抵消上面的运行时 bug。

## 对 Claude 初版结论的纠正

### 1. “V2.1 不自动接 ModelResolver 是故意的”不能作为 public API 解释

底层 `assemble_graph(chat_model=...)` 要求显式模型，可以是合理设计。

但 public `run_skill()` 当前看起来是顶层执行入口。如果它不解析真实模型，又不要求调用方传 `chat_model`，那么对用户就是入口不可用。这个问题应按 P0 处理。

### 2. cache key 不包含 actions/tools Python 文件

实际 `_collect_skill_files()` 只收集：

```text
GRAPH.md
io/*.json
phases/**/*.md
```

不收集 actions/tools `.py` 文件。

不过 cache hit 会重新 `_discover_actions_and_tools()`，所以 Python 函数本体会重新加载。真正严重的问题不是这个，而是 cache rehydrate 没恢复 subagent metadata 和 phase token。

### 3. “旧 runner 分支一定 AttributeError”说法过于绝对

方向是对的：旧 `GraphAgentHarness` 分支和 V2.1 hard cut 后的 loader 已经错位。

但具体触发可能更早被 loader 以 `[F-v21-route]` 拒绝，不一定总是走到 AttributeError。建议描述为“public API 下旧 harness 路径已经不可依赖 / 不应作为真实主线”，而不是只绑定某个异常形式。

## 建议修复拆分

### PR 0 / Design Spike：IO contract 与 graph isolation 定案

目标：

- 明确 runtime input funnel：`run_skill(**inputs)` 如何按 `io/inputs.json` 校验、过滤、规范化。
- 明确 state shape：继续共享 `data`，还是拆成 `inputs + phase_outputs + phase_input`。
- 明确 phase-level IO contract：哪些 phase 必须声明 `io`，声明格式是什么。
- 明确 agent-called graph 隔离规则：subagent / call_subgraph 是否只能读取显式 tool input。
- 明确 subagent 抽象：用户写单节点 agent phase，engine 自动包装 graph。
- 明确 call_subgraph 工具：agent phase 如何主动调用完整 graph skill。
- 明确图级 IO 校验：required input、output 冲突、edge mapping、terminal output 如何在 compile 阶段检查。

验收产物：

- 一份设计文档或 ADR。
- 2-3 个最小 fixture：
  - phase-level IO mapping。
  - isolated subagent。
  - agent phase call_subgraph。
- 明确哪些旧 V2.1 skill 需要迁移。

### PR 1a：public runner 接线

目标：

- 修 `run_skill()` V2.1 不带模型直接崩溃的问题。
- 修 `RuntimeError` 没有稳定错误包装的问题。
- 明确 V2.1 public runner 是否负责接 `ModelResolver`、callbacks、trace、artifact、unattended 等运行时能力。

验收测试：

- `run_skill(v21_skill_with_skill_phase, mock_llm=...)` 正常成功。
- `run_skill(v21_skill_with_skill_phase)` 在无模型配置时返回清晰失败，不裸抛 `RuntimeError`。

### PR 1b：state merge 策略改造

目标：

- 先在方案 A/B/C 中选定 `data` merge 策略。
- 修 `shallow_dict_merge` 顺序覆盖误判冲突的问题。
- 覆盖 LOGIC 和 SUBGRAPH 两类 phase 出口。

验收测试：

- 顺序 LOGIC phase 可以更新已有 input key。
- 顺序 SUBGRAPH phase 可以回写父图已有 key，或在新 state shape 下以明确方式覆盖/归档该 key。
- 并行 fan-in 写同一 key 仍能被检测为冲突。

### PR 2：subagent runtime 和 cache

目标：

- cache hit 后保留 `subagents_by_phase` 和 `phase_tokens`。
- subagent depth 写进 child flow。
- cache 写失败降级为 no-cache。

验收测试：

- `tests/fixtures/subagent_minimal` fresh compile 和 cache hit 结果一致。
- 嵌套 subagent 超过限制会被真实子图触发拒绝。
- HOME 不可写时 compile 不失败。

### PR 3：SKILL node prompt 历史和 callbacks

目标：

- exit_contract 临时注入，不写入长期 messages。
- V2.1 SKILL/LOGIC/SUBGRAPH node 发出 phase/tool/LLM callback 或 LangChain callback。

验收测试：

- N 轮 ReAct 后 exit_contract 只出现 1 份或仅存在于临时 prompt。
- V2.1 run 能产出 phase start/end、tool call、LLM call trace。

### PR 4：文档和测试卫生

目标：

- README Quick Start 迁移到 V2.1。
- public API 数量同步到 17 或重新收口。
- 清理 `xpassed=53`。
- 明确 legacy harness 的生命周期。

验收测试：

- README 示例可直接运行。
- `uv run pytest -q` 不再有未解释的大量 xpass。

## 已验证清单和回归测试入口

以下清单用于把审计发现转成后续 regression tests。

本节优先列出已经实测复现的 bug。未单独展开的 P0-2、P1-2、P1-4 和 P2 系列不是没有回归路径，而是需要在 PR 实施阶段补成可执行测试，具体方向见各自章节。

待补 regression 重点：

- P0-2：把 README Quick Start 做成文档冒烟测试，确保示例路径和调用方式真实可运行。
- P1-2：构造父 SKILL -> 子 SKILL -> 孙 SKILL 的 fixture，断言第二层 subagent 会被 `assert_subagent_depth_allowed` 拒绝。
- P1-4：用 fake callback / tracing callback 捕获 V2.1 phase、LLM、tool 事件，证明新 runtime 真的发事件。
- P2-1：如果保留 legacy harness，增加 `CognitiveFlowMiddleware` 拿到完整 state 并拒绝非法 `finish_task` 的测试。
- P2-2：monkeypatch cache dir 为不可写路径，断言 `compile_skill(cache=True)` 降级而不是失败。
- P2-3 / P2-4：把 xfail/xpass 清理和 public API 数量同步变成 CI 可检查项。
- A1-A8：用 PR 0 的最小 fixture 覆盖 input funnel、phase IO、isolated subagent、agent call_subgraph、图级 IO 校验。

### P0-1：`run_skill()` 无模型直接崩溃

复现：

```python
run_skill("tests/fixtures/subagent_minimal")
```

当前结果：

```text
RuntimeError: [F-v21-graph] SKILL phase requires chat_model
```

建议测试位置：

- 新增或扩展 `tests/core/test_runner_v21.py`
- 使用 `tests/fixtures/subagent_minimal`

### P0-3：顺序覆盖被 reducer 当成冲突

复现：

```python
shallow_dict_merge({"foo": 1}, {"foo": 2})
```

当前结果：

```text
GraphAgentFatalError: [F-v21-state-conflict] key='foo'
```

建议测试位置：

- 扩展 `tests/core/test_v21_graph_assembly.py`
- 增加一个 LOGIC 顺序更新已有 input key 的 fixture
- 增加一个 SUBGRAPH 回写父图已有 key 的 fixture
- 保留并行 fan-in 冲突测试

### P1-1：cache hit 丢 subagent

复现要点：

```text
fresh compile:
  subagents_by_phase = ['main']
  tools = {'main': ['call_subagent_echo_expert']}

dehydrated snapshot:
  keys = ['manifest', 'nodes', 'raw']

cache hit:
  subagents_by_phase = []
  tools = []
```

建议测试位置：

- 新增 `tests/core/test_v21_cache.py`
- 使用 `tests/fixtures/subagent_minimal`
- 强制 fresh compile 和 cache hit 后对比 `subagents_by_phase`、phase tools、`phase_tokens`

### P1-3：exit_contract 累积

复现要点：

```text
turn 0: exit_contract copies = 1
turn 1: exit_contract copies = 2
turn 2: exit_contract copies = 3
```

建议测试位置：

- 扩展 `tests/core/test_v21_graph_assembly.py`
- 用假 chat model 连续返回多轮 tool call，统计传给 model 的 prompt 中 exit contract 份数

### 测试套件现状

当前全量结果：

```bash
uv run pytest -q
```

```text
930 passed, 3 skipped, 50 xfailed, 53 xpassed
```

建议测试卫生：

- 清理已经 xpass 的迁移测试。
- 对仍 xfail 的测试写明 owner 和退出条件。
- 核心 V2.1 路径避免 `strict=False` 长期掩盖状态。

## 当前推荐优先级

按风险排序：

1. P0：`run_skill()` 真实 LLM 路径不可用。
2. P0，文档入口：README Quick Start 不可用。工程上放到 PR 4 处理，不阻塞 P0-1 / P0-3 的代码修复。
3. P0：`shallow_dict_merge` 阻止顺序更新。
4. P0/P1，架构定案：IO contract 与 graph isolation。包括 input funnel、phase-level IO、subagent 抽象、call_subgraph、黑板隔离、图级 IO 校验。
5. P1：cache hit 改变 subagent 行为。
6. P1：subagent depth 限制没有进入 child flow。
7. P1：exit_contract 在 ReAct 历史里重复累积。
8. P1：V2.1 callback/trace 未接线。
9. P2：public API 数量 / 其它示例漂移。
10. P2：legacy middleware 和旧 harness 去留。
11. P2：测试 xfail/xpass 清理。
12. P2：cache 写 HOME 没降级。

## 最终结论

V2.1 的方向是清晰的：把 skill 作为文档驱动的图声明，编译成 LangGraph，再用 `BlackboardState` 统一调度 LOGIC、SKILL、SUBGRAPH。

但当前代码还不是一个完整收口的 SDK：

- 文档仍教旧入口。
- public `run_skill()` 和真实 V2.1 LLM 执行没有完整接线。
- state reducer 把正常顺序更新挡掉。
- runtime input、phase input/output、subagent/subgraph 调用还没有形成统一 IO contract。
- agent phase 内调用的 graph 当前缺少隔离设计，仍容易被父图全量黑板污染。
- cache 会改变 subagent 行为。
- subagent depth、exit_contract、callbacks 都有主路径问题。
- 旧 harness 还在，但不是 V2.1 主线。

因此后续不应先做大规模死代码清理。应先修 public runner、state merge 这几处会直接改变运行行为的 bug，同时尽快定下 IO contract / graph isolation 设计；否则 cache/subagent/SUBGRAPH/callback/trace 的后续修复都会继续围绕不稳定的数据模型打补丁。之后再整理文档和 legacy 边界。

署名：Codex
