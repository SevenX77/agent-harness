# execution-runtime (engine) — MVP0 Alignment (V0.3.0 目标对齐逻辑)

> **Status**: Filled by a1 (Codex) based on a2 framework, 2026-05-20; Q9/Q13 + 死代码清退 + V0.3.0 版本号 升级 2026-05-21
> **Scope**: Graph 执行装配调度、主入口生命周期 run_skill、节点重试、subagent / call_<subgraph_name> per-tool 动态工具注入 (audit A4/A5, Q13 决策)
> **改造目标 engine 版本**: V0.3.0 (MVP0 落地后, 详见 [INDEX.md#engine-版本号约定-2026-05-21-pm-拍定](../../INDEX.md#engine-版本号约定-2026-05-21-pm-拍定))
> **配套**: 见 [INDEX.md](../../INDEX.md) 三时态模板 + cross-link 规则 + writing conventions。

## UI/UX

N/A — 此模块为纯 backend Python library, 无 UI / 无前端调用面。

Execution runtime 是“真正把编译好的 skill 跑起来”的引擎层。PM 在 Studio 里看到的 Run 按钮、Trace 流和 History 结果，都不是这里直接渲染的 UI；它们只是消费 runtime 产生的结果、错误和事件。当前 V2.1 主线在 `_run_v21_skill_dict()` 里执行 `compile_skill -> assemble_graph -> graph.invoke`，见 `packages/graph-agent/src/graph_agent/core/runner.py:451` 到 `packages/graph-agent/src/graph_agent/core/runner.py:486`。

MVP0 runtime 的用户价值是：点击运行后，真实 LLM 能被自动解析并注入，子图不会偷读父图黑板，ReAct 消息不会无限堆积，错误能以可展示的 code 返回，而不是裸 Python RuntimeError。

## 前端逻辑

N/A — 此模块为纯 backend Python library, 无 UI / 无前端调用面。

React 不调用 `assemble_graph()`，也不理解 LangGraph reducer。前端最多通过 Studio 后端启动 run，再订阅事件。Runtime 与前端的边界应该是结构化结果和 trace event，而不是共享内部 Python state。V2.1 当前还会丢弃 callbacks，代码在 `packages/graph-agent/src/graph_agent/core/runner.py:462`，所以 MVP0 需要把 observability 接线放回 runtime，但不是让前端介入执行。

## 后端功能

### 1. V2.1 真实 LLM 路径模型装载接通 (P0-1 修复, Q9 决策落地)

MVP0 SHOULD 让 `run_skill()` 在没有 mock 的情况下也能跑真实 SKILL phase。当前 `_run_v21_skill_dict()` 只在传入 `mock_llm` 时给 `chat_model` 赋值，否则就是 None，见 `packages/graph-agent/src/graph_agent/core/runner.py:467` 到 `packages/graph-agent/src/graph_agent/core/runner.py:469`。SKILL node 一旦发现 `chat_model is None`，直接抛 `RuntimeError(“[F-v21-graph] SKILL phase requires chat_model”)`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:229` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:234`。

**Q9 PM 拍定方案** (2026-05-21, 详见 `docs/engine/MVP0-DECISIONS-EXPLAINED-2026-05-21.md` Q9 + a2 round 5 reply): 采用 LangChain core/community 模式 — engine 只依赖 `ModelResolverProtocol` (typing.Protocol), 具体 `ModelResolver` 实现物理移出 `graph-agent` 包; Fallback 责任收敛到 `GatewayChatModel._generate` 内部 (LangChain 流派 1, with_fallbacks 思路)。

**物理切割 [BREAKING]**:

- **定义契约**: 在 `packages/graph-agent/src/graph_agent/core/` 新建 `model_resolver_protocol.py` 文件, 只放 `ModelResolverProtocol(Protocol)` 跟必要的协议层数据类 (例如 `ModelInfo` 如果需要)。engine 不再 import 具体 ModelResolver 实现。
- **物理移出**: `packages/graph-agent/src/graph_agent/models/resolver.py:43` 的 `ModelResolver` 具体类 (含 YAML 加载、role → provider 映射、`GatewayChatModel` 实例化) 从 `graph-agent` 包**整体移到** `apps/studio/backend/` (或新建 `packages/graph-agent-models/` 配套独立包, 跟 LangChain `langchain-anthropic` / SQLAlchemy dialect 模式同思路)。Studio 后端负责在请求 / 启动阶段实例化 `ModelResolver` 后注入引擎。
- **改写入口签名**: `_run_v21_skill_dict()` 的 `mock_llm: Any = _NO_MOCK_LLM` 参数 (`packages/graph-agent/src/graph_agent/core/runner.py:454`) 替换为 `resolver: ModelResolverProtocol` 强注入; `mock_llm` 作为测试 fallback 保留, 但生产路径必须传 `resolver`。
- **Fallback 不在 engine 层**: engine 的 SKILL node 仅调用一次 `chat_model.invoke(prompt)`; 模型轮询 / API timeout / provider 备用线路 (Anthropic → OpenAI → Gemini 顺序兜底) **完全在 `GatewayChatModel._generate` (`packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:151` 周边) 内部消化**。a1 2026-05-21 调查确认 `GatewayChatModel` 跟 `llm_client_manager.py` 现状不是死代码, 这跟 Q9 决策协同 — fallback 现状已经在这一层, MVP0 保持现状不动。

**用户价值升级**: MVP0 WILL 把”缺模型”从裸 RuntimeError 升级成结构化错误 `F-v21-model-not-found`。这样 Studio 可以告诉用户”没有配置 copilot/default 模型”而不是”SKILL phase requires chat_model”。这个错误由 engine 在 SKILL node 入口构造 (拿到注入的 resolver 后, 若 `resolver.resolve(“default”)` 抛 `ModelResolutionError`, 包装成 `F-v21-model-not-found` 沿 trace `EXCEPTION` 事件发出)。

### 2. Child flow subagent_depth 状态透传与下发 (P1-2 修复)

MVP0 SHOULD 把 subagent depth 写入 child state 的 `flow`，而不是只写进 RunnableConfig metadata。当前 `_subagent_runnable_config()` 把 `"subagent_depth": depth + 1` 放在 metadata，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:482` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:505`；但 `_invoke_subagent_once_t23()` 启动子图时，`"flow"` 仍然是 `parent_state.get("flow", {})`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:400` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:405`。

这会让深度限制变成“看起来写了，子图实际没读到”。MVP0 WILL 在进入 child graph 前深拷贝 parent flow，显式写入 `subagent_depth = current_depth + 1`，再传给子图。深拷贝很重要，因为 flow 是 dict；如果直接复用父对象，子图修改 `flow["subagent_validation_retries"]` 这类控制字段时会污染父图。

```python
import copy
from graph_agent.core.subagents import current_subagent_depth

# 深拷贝父级 flow 防止双向污染，确保完全隔离
child_flow = copy.deepcopy(parent_state.get("flow", {}))
# 读取旧深度并累加计算当前新层次
current_depth = current_subagent_depth(parent_state.get("flow", {}))
child_flow["subagent_depth"] = current_depth + 1

# 后续把带有正确累加层级的 child_flow 构建成初始态送入隔离的子图调用中
child_state = {
    "data": explicit_inputs,
    "flow": child_flow, 
    "messages": []
}
```

这段伪代码同时服务 A6：child data 不应该是 `{**before_data, **input_data}`。当前正是这样合并父图全量 data 与显式输入，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:398` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:403`。

### 3. Exit_contract 历史堆积净化去重 (P1-3 修复)

MVP0 SHOULD 让 exit contract 只在发给模型时临时出现，不进入长期 `messages` 历史。当前每轮 ReAct 都先 `inject_exit_contract(messages, phase_ast.exit_contract)`，再把 `prompt_messages` 和模型 response 一起保存为下一轮 messages，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:243` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:247`。如果模型跑多轮，exit contract 会重复堆积。

PM 版例子：exit contract 是“回答必须调用 finish_task 并输出 JSON”的规则。它应该像临时贴纸一样贴在本次请求上，而不是每轮都复印一份塞进聊天历史。MVP0 WILL 用 `ExitContractRegistry` 标记临时消息，并在写回 `BlackboardState.messages` 前 strip 掉。`messages` 当前使用 LangGraph `add_messages` reducer，定义在 `packages/graph-agent/src/graph_agent/runtime/state.py:40`；这意味着只要污染进入 state，后续就会一直追加扩散。

### 4. Subagent 抽象层级轻量单节点化 (A4 改造)

MVP0 SHOULD 允许轻量 subagent，不再强制每个 subagent 都是完整 V2.1 graph root。当前编译期 `_resolve_subagent_root()` 要求 subagent path 是目录且有 `GRAPH.md`，见 `packages/graph-agent/src/graph_agent/core/loader.py:447` 到 `packages/graph-agent/src/graph_agent/core/loader.py:483`。runtime 又会对每个 subagent 再 `compile_skill()` 和 `assemble_graph()`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:374` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:389`。

轻量单节点 subagent 的目标是：业务作者只写一个 prompt 或一个 `SKILL.md` 类文档，也能被父 SKILL phase 当工具调用。MVP0 WILL 在 compiler 侧识别轻量子代理，并在 runtime 侧包装成一个简单工具节点或虚拟单节点 graph。这样 A4 不会破坏现有完整 graph subagent，同时给“小任务委派”更低门槛。

### 5. Call_subgraph 大流程动态工具暴露 (A5 改造, Q13 决策落地)

MVP0 SHOULD 新增 `call_<subgraph_name>` 工具族，让 LLM 在 SKILL phase 中主动调用一个完整 graph skill。它和当前 `SUBGRAPH` phase 不同：`SUBGRAPH` 是固定拓扑节点，执行到那里自动跑；`call_<subgraph_name>` 是 LLM 决策时的工具调用，模型可以按任务需要选择是否调用。

**Q13 PM 拍定方案** (2026-05-21, a2 round 5 reply): 走 **per-tool 编译路径**, 不是统一 `call_subgraph(name=..., explicit_inputs=...)` 入口。理由是这是 Anthropic / OpenAI / Gemini Tool Calling API 最佳实践 — 每个 subgraph 在 graph 装配期编译为独立原生 tool, schema 直接挂到 LangChain `bind_tools`, 完全不占用 system prompt, 参数格式幻觉率最低。

当前 `_build_skill_node()` 收集业务 tools、subagent tools、framework tools 和 `finish_task`，代码在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:184` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:227`。subagent tool map (现状已是 per-tool `call_subagent_<name>`) 来自 `compiled.subagents_by_phase`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:301` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:308`。

**实施路径 (跟 subagent per-tool 编译同构)**:

- 装配期 (`packages/graph-agent/src/graph_agent/core/loader.py:387` `_inject_subagent_tools` 同位置 / 同思路) 新增 `_inject_subgraph_tools()`, 把 SKILL phase 声明的 subgraph references (类似 `subagents:` 字段, 待 a2 设计 frontmatter) 编译为独立 `call_<subgraph_name>` tool。
- 每个 subgraph tool 的 input JSON Schema 直接从 subgraph root `io/inputs.json` 转 (通过 `build_subagent_tool_args_model` 类似 helper, `packages/graph-agent/src/graph_agent/core/loader.py:419-422` 已是该路径), 挂到 LangChain `bind_tools`。
- 调用时 LLM tool_call 的 `arguments` 严格按 JSON Schema 校验, 通过后作为 `explicit_inputs` 注入 child graph 初始 `BlackboardState.data` (父图 data **不**隐式继承, 跟 [state-and-io-contract A6 黑板隔离](../state-and-io-contract/mvp0-alignment.md#cross-state-blackboard-isolation) 同一安全边界)。

**显式输入沙盒**: child graph 的初始 `data` **只**等于 LLM tool_call kwargs 经 schema funnel 后的结果, 不带父图任何字段。这跟现状 `_invoke_subagent_once_t23()` (`packages/graph-agent/src/graph_agent/core/graph_assembler.py:392-410`) 的 `{**before_data, **input_data}` 合并行为是 [BREAKING] 改变。

### 6. 执行器的异常捕获与容错包裹

MVP0 SHOULD 把运行期异常归一化。当前 `run_skill()` 成功时会包装 `WorkflowResult`，异常分支只捕获 `GraphAgentError`，见 `packages/graph-agent/src/graph_agent/core/runner.py:195` 到 `packages/graph-agent/src/graph_agent/core/runner.py:224`。但 P0-1 的无模型错误是裸 `RuntimeError`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:233` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:234`。

MVP0 WILL 让 runtime node 抛出的可预期错误使用统一 code，例如 `MODEL_NOT_FOUND`、`DEPTH_LIMIT_REACHED`、`INVALID_TOOL_ARGS`。未知异常也应被包进 `GraphAgentFatalError`，并交给 tracing 发出 `EXCEPTION` 事件。这样 Studio 不需要按 Python 异常类猜测用户提示。

## API

以下是配合上述 MVP0 功能变更需要全新定义或者调整的重要接口签名与结构体。它们是联结不同层次能力的骨干，不仅是供内部调用，也是未来接入 CLI 等外界形态的保障。

### 1. ModelResolverProtocol 契约层声明 (engine 内, Q9 决策)

按 Q9 PM 拍定: engine 只暴露 Protocol 层契约, 不放具体实现。新建 `packages/graph-agent/src/graph_agent/core/model_resolver_protocol.py` 文件:

```python
from typing import Protocol
from langchain_core.language_models.chat_models import BaseChatModel


class ModelResolverProtocol(Protocol):
    """Engine-side contract for role → BaseChatModel resolution.
    
    Concrete implementation lives outside `graph-agent` package (e.g.,
    `apps/studio/backend/` or `packages/graph-agent-models/`). Engine
    only depends on this Protocol; instantiation + injection is caller's
    responsibility (Studio backend / CLI / SDK consumer).
    """
    
    def resolve(self, role_or_provider: str) -> BaseChatModel:
        """Resolve a role (e.g. 'default', 'critic') to a bound BaseChatModel.
        
        Raises:
            ModelResolutionError: If role is unmapped or all providers fail
                after `GatewayChatModel._generate` internal fallback chain.
        """
        ...
```

**Engine 入口签名变更 [BREAKING]**: `_run_v21_skill_dict()` (`packages/graph-agent/src/graph_agent/core/runner.py:451`) 移除 `mock_llm` 参数, 改强注入 `resolver: ModelResolverProtocol`:

```python
def _run_v21_skill_dict(
    skill_root: Path,
    *,
    resolver: ModelResolverProtocol,  # [BREAKING] 替代 mock_llm
    trace_dir: str | Path | None = None,
    thread_id: str | None = None,
    callbacks: list[Any] | None = None,
    **inputs: Any,
) -> dict[str, Any]:
    ...
```

测试覆盖入口 (`mock_llm`) 通过实现 `MockModelResolver(ModelResolverProtocol)` 注入, 而不是在 engine 签名上保留两条路径。

### 2. 具体 ModelResolver 类 (配套包, 不在 engine 内)

按 Q9 物理切割决策, **具体 ModelResolver 实现移出 `graph-agent` 包**, 落在 `apps/studio/backend/` (或独立配套包 `packages/graph-agent-models/`)。这部分代码**不在 engine 域 spec 内**, 详细 API 由 Studio 后端域 spec 描述 (详见 `apps/studio/backend/` 相关 spec / 当前 `packages/graph-agent/src/graph_agent/models/resolver.py:43` 是迁出源)。

核心约束 (cutover discipline):

- 实现必须满足 `ModelResolverProtocol` (mypy 强校验)
- Fallback 责任仍由 `GatewayChatModel._generate` 消化 (`packages/graph-agent/src/graph_agent/models/gateway_chat_model.py`), **不**新建 engine 侧 retry node
- 移出后 engine 不再 import `graph_agent.models.resolver`; 该 import 在 `_run_v21_skill_dict` 调用方 (Studio backend) 完成实例化, 注入到 engine

MVP0 SHOULD 在 cutover PR 同步:
1. engine `model_resolver_protocol.py` 落地
2. `resolver.py` 物理 `git mv` 到 `apps/studio/backend/services/model_resolver.py` (或同等位置)
3. Studio backend `LLMRolesService` (现 `apps/studio/backend/app/services/llm_roles.py`) 跟 `ModelResolver` 关联调用 ([BREAKING], 需 a2 在 design 阶段细化)

### 3. call_<subgraph_name> per-tool 编译路径 (Q13 决策)

按 Q13 PM 拍定: 不是统一 `call_subgraph(name=..., explicit_inputs=...)` 入口, 而是**每个登记的 subgraph 编译为独立原生 tool**, 跟现状 `call_subagent_<name>` 编译思路 (`packages/graph-agent/src/graph_agent/core/loader.py:387-407`) 完全同构。

编译期工厂签名 (放在 `packages/graph-agent/src/graph_agent/core/loader.py` 内, 跟 `_inject_subagent_tools` 平级):

```python
def _inject_subgraph_tools(
    registry: ToolRegistry,
    subgraphs_by_phase: dict[str, list[CompiledSubgraph]],
) -> ToolRegistry:
    """Compile each registered subgraph into a native LangChain tool.
    
    Each subgraph becomes a separate tool named `call_<subgraph_name>`,
    not a unified entry point. The tool's input JSON Schema is derived
    from the subgraph's root `io/inputs.json` via `build_subgraph_tool_args_model`.
    
    Args:
        registry: Existing ToolRegistry from base SKILL phase tool collection.
        subgraphs_by_phase: parent_phase_id -> list[CompiledSubgraph], 
            built by compiler from frontmatter `subgraphs:` declarations
            (parallel to `subagents:` field).
    
    Returns:
        Augmented ToolRegistry with per-subgraph native tools attached.
    """
    ...
```

调用时 runtime 走 (`packages/graph-agent/src/graph_agent/core/graph_assembler.py:392-410` `_invoke_subagent_once_t23` 同思路扩展为 `_invoke_subgraph_once`):

```python
def _invoke_subgraph_once(
    runtime: _SubgraphRuntime,
    parent_state: BlackboardState,
    input_data: dict[str, Any],   # 来自 LLM tool_call kwargs 经 schema funnel 校验后
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Execute child graph with strict blackboard isolation.
    
    Child BlackboardState:
      - data: ONLY explicit `input_data` (parent data NOT inherited)
      - flow: deepcopy(parent_state.flow) + subagent_depth+1
      - messages: []
      - run_id: inherit parent for trace correlation
    
    Returns:
        {"status": "ok", "data": child_result_data_namespaced_by_phase, "flow": child_flow}
    """
    ...
```

注意 child `data` **不**继承父图 `before_data` — 这是跟现状 `_invoke_subagent_once_t23` (`graph_assembler.py:398-403` `{**before_data, **input_data}`) 的 [BREAKING] 差异, 跟 A6 黑板隔离同 cutover。

### 4. ExitContractRegistry 去重服务
用于解决 P1-3 的临时存储机制封装，用于拦截并剥离临时状态的公共注册机：

```python
from typing import Any

class ExitContractRegistry:
    """Manages injection and stripping of temporary system messages."""
    
    def inject(self, messages: list[Any], contract: str) -> list[Any]:
        """Inject the exit contract as a temporary message into the flow.
        
        Returns a new message list containing the temporary contract, ready
        to be sent to the LLM. The original list is unmodified.
        """
        pass
        
    def strip(self, messages: list[Any]) -> list[Any]:
        """Strip marked temporary messages from the history payload.
        
        Iterates over the current stack and removes any element identified
        as a volatile exit contract marker, preserving context size.
        This must be called before state is written back to the LangGraph reducer.
        """
        pass
```

## Data Model / State

Runtime state 仍以 `BlackboardState` 为主，当前字段是 `data`、`flow`、`messages`、`run_id`，定义在 `packages/graph-agent/src/graph_agent/runtime/state.py:35` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:41`。MVP0 不应把所有控制信息都塞进 RunnableConfig metadata；真正影响执行逻辑的内容必须进入 state，特别是 `subagent_depth`。

子图调用的 state WILL 变成隔离对象：`data` 只来自 explicit inputs，`flow` 是父 flow 的深拷贝加深度字段，`messages` 从空列表开始。当前 SUBGRAPH 固定节点也仍然用父图全量 data 启动子图，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:155` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:164`；MVP0 SHOULD 与 state-and-io-contract 一起收敛这个行为。

## Cross-feature Interaction

本特性的运行阶段极大地牵涉着上下游状态的传递以及前端表现。如果引擎运行时罢工，其它模块全部停摆。

### 1. State 黑板数据的严格沙盒隔离
在执行子图时（无论是通过底层的 `_invoke_subagent_once_t23()` 还是暴露的 `call_subgraph` 大招），最核心的要求是断绝隐式变量继承的灾难。此过程强依赖状态与合约中的全新沙盒规范，黑板必须经历一次彻底的划分阻断。其双向协作及内存分配策略的细节详见：[state-and-io-contract 层的黑板彻底隔离设计](../state-and-io-contract/mvp0-alignment.md#cross-state-blackboard-isolation)。

### 2. 运行时全维度事件发射
Runtime WILL 在 phase start/end、LLM call、tool call、subagent enter/exit 和 exception 位置调用 tracing callback。当前 V2.1 runner 删除 callbacks，见 `packages/graph-agent/src/graph_agent/core/runner.py:462`；MVP0 需要与 [tracing-and-observability 的 callback event bus](../tracing-and-observability/mvp0-alignment.md#后端功能) 对齐。

### 7. 详细的状态下发测试策略
为了保证上述的 `subagent_depth` 和 `BlackboardState` 的完全隔离能够在长期的迭代中不被破坏，我们必须在 `packages/graph-agent/tests/core/` 下引入深度的集成测试。重点断言包括：子图看到的 `flow["subagent_depth"]` 已递增；子图修改 `flow` 不会污染父图；child data 不含父图未显式传入的 key。当前问题触发点在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:398` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:405`。

### 8. LangChain RunnableConfig 的彻底改造
MVP0 SHOULD 让 `RunnableConfig` 只承载 tags、callbacks、run id 等调度/观测信息，而不是作为业务控制状态来源。当前 `_subagent_runnable_config()` 同时写 tags、run_id、metadata 和 callbacks，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:482` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:505`。深度、重试次数和隔离边界应该回到 `flow` 或显式 child state。

### 9. 异常分发与状态码体系
为了配合前端界面的多状态展示，我们在抛出异常时需要完善内部的 Error Code 体系：
```python
class ErrorCode:
    MODEL_NOT_FOUND = "F-v21-model-not-found"
    DEPTH_LIMIT_REACHED = "F-v21-depth-limit"
    INVALID_TOOL_ARGS = "F-v21-tool-args-invalid"
```
这些 code SHOULD 被 tracing 的 `EXCEPTION` 事件携带，并最终交给 Studio 展示。

## MVP0 死代码清退 {#mvp0-死代码清退}

按 a1 (Codex) 2026-05-21 死代码调查 (详见 [baseline.md#legacy--死代码残留清单-a1-调查-2026-05-21](./baseline.md#legacy--死代码残留清单-a1-调查-2026-05-21)) 跟 PM 拍定原则 "把事情做对, 不向后兼容", MVP0 cutover **同 PR** 一并清退以下 execution-runtime 域内的 legacy / 死代码。execution-runtime 是死代码集中域, 清退体量最大。

### V1/V2.0 GraphAgentHarness 栈整体退役 (~1553+ 行)

旧编排器栈不在 V2.1 主线 (`_run_v21_skill_dict`), 但被 `core/__init__.py:15` export 保活。MVP0 cutover 一次性删:

- `packages/graph-agent/src/graph_agent/core/harness.py` (1150 行) — `GraphAgentHarness` 主体
- `packages/graph-agent/src/graph_agent/core/graph_builder.py` (130)
- `packages/graph-agent/src/graph_agent/core/phase_executor.py` (154)
- `packages/graph-agent/src/graph_agent/core/retry_router.py` (56)
- `packages/graph-agent/src/graph_agent/core/run_context.py` (63)
- `packages/graph-agent/src/graph_agent/core/phase_nodes/` (整目录, `LLMPhaseNode` / `CodePhaseNode` / `ValidationPhaseNode`)
- `packages/graph-agent/src/graph_agent/core/nudge_injector.py`

### 同时改 `core/__init__.py` 移除 export

`packages/graph-agent/src/graph_agent/core/__init__.py:15-21` 删除以下 export:

- `GraphAgentHarness` (`:15`)
- `ContextBridge` (`:17`)
- `RunContext` (`:18`)
- `Phase` (`:21`)

`graph_agent.__init__.py:12` 顶层 public API 已经不含 `GraphAgentHarness`, `core/__init__.py` 同步即可。

### 旧 cognitive 模块退役

- `packages/graph-agent/src/graph_agent/cognitive/finish.py` (257 行) — V2.1 用 `cognitive/finish_task.py`, 不是这个文件。`finish.py` 只被 harness / phase_nodes / nudge_injector 引用, 跟 harness 栈一起删。
- `packages/graph-agent/src/graph_agent/cognitive/memory.py` (19 行, `update_working_memory`) — 同上, 旧栈专用。
- `packages/graph-agent/src/graph_agent/cognitive/middlewares.py` / `prompt.py` — 旧 LLMPhaseNode 用, 跟旧栈一起。

### 测试残留同 PR 删 (不改测 V2.1)

V1/V2.0 测试是 dead test, 不保护 V2.1 任何 regression。同 PR 删:

- `packages/graph-agent/tests/integration/test_mvp1_smoke.py`
- `packages/graph-agent/tests/core/test_harness_state_machine_resources.py` / `test_harness_save_outputs_failure.py` / `test_harness_awaiting_input_no_completion.py` / `test_harness_phase_b_invariants.py` / `test_compaction_sidecar.py`
- `packages/graph-agent/tests/core/test_heartbeat_pulser.py` / `test_thread_status.py`
- `packages/graph-agent/tests/core/test_graph_builder.py` / `test_phase_executor.py` / `test_phase_executor_validation.py` / `test_retry_router.py`

### legacy `run_skill` 旧分支同 PR 退役

`packages/graph-agent/src/graph_agent/core/runner.py:284` 到 `:360` 区间的旧 `_run_skill_dict()` 分支 (含 `load_workflow_from_md(...).run(...)` 调用) 整段退役。V2.1 主线 `_run_v21_skill_dict()` (`:451`) 成为 `run_skill()` 唯一执行路径; `run_skill()` 自身 (`:161`) 简化到只调用 V2.1 分支, 移除 V2.0 分支判断。同时删 `runner.py:284-286` 默认创建的 `LoggingCallback()` / `TracingCallback(trace_dir=...)` (跟 [tracing-and-observability/mvp0-alignment.md#MVP0-死代码清退](../tracing-and-observability/mvp0-alignment.md#mvp0-死代码清退) 协同)。

### 非死代码 — 保留 (跟 Q9 决策协同)

a1 确认以下文件**不是死代码**, 跟 Q9 ModelResolver 决策协同:

- `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py` — `ModelResolver` (现`resolver.py:27`) 使用; Predict 也继承; **保留**, 但按 Q9 决策, fallback 仍在 `GatewayChatModel._generate` 内部消化 (流派 1)。
- `packages/graph-agent/src/graph_agent/models/llm_client_manager.py` — `GatewayChatModel` 调用, 保留。

### Cutover discipline (按 SOP-05)

execution-runtime 域清退 PR 体量很大, 合计 ~2000+ 行 src + 12+ 个 test 文件。**禁止**分拆成"删 src 一 PR + 删 test 一 PR"。整体一次性 cutover, 同 PR `feat!:` 或 `refactor!:` 标 `!` breaking。

### V0.3.0 版本号 cutover (PM 2026-05-21)

MVP0 落地 = engine 版本号从 V2.1 升 V0.3.0 (详见 [INDEX.md#engine-版本号约定-2026-05-21-pm-拍定](../../INDEX.md#engine-版本号约定-2026-05-21-pm-拍定))。同 cutover PR 处理 execution-runtime 域内的版本号 step:

- **`__version__`**: `packages/graph-agent/src/graph_agent/__init__.py` 或 `packages/graph-agent/pyproject.toml` 内的版本号字段升 `0.3.0`。
- **错误码前缀** `[F-v21-graph]` → `[F-v3-graph]` (`packages/graph-agent/src/graph_agent/core/graph_assembler.py:234` 等 SKILL node 抛错位置)。同时 `RuntimeError("[F-v21-graph] SKILL phase requires chat_model")` 这条整体重构成结构化 `F-v3-model-not-found` (按本文件 §1)。
- **`_run_v21_skill_dict` rename**: `packages/graph-agent/src/graph_agent/core/runner.py:451` `_run_v21_skill_dict` 改名 `_run_v3_skill_dict` (或直接合并到 `_run_skill_dict` 主入口, V2.0 分支已经在死代码清退里删)。
- **`MAX_REACT_TURNS`** 常量 (`graph_assembler.py:37`) 保留, 不带版本号; 但 Q11 已经把保底分流 (turn 7 graceful warning + turn 8 strict error) 决策落地。
- **fixture 路径**: `packages/graph-agent/tests/fixtures/subagent_minimal/` 等 V2.1 fixture 检查是否需要重命名 (按 V0.3.0 新 frontmatter 重写, 见 MVP0 test 全清重写段)。

### MVP0 test 全清重写 (PM 2026-05-21)

PM 原则 (2026-05-21): **不只是 V1/V2.0 dead test, V2.1 现有 test 也全部清掉, MVP0 重新写 test 套**。

- **现状 V2.1 test**: `packages/graph-agent/tests/core/test_v21_graph_assembly.py` / `test_assemble_graph.py` / `test_runner_v21.py` / `test_subagent_*.py` 等 V2.1 runtime 相关 test 全部清退。
- **MVP0 重写覆盖** (execution-runtime 域):
  - P0-1: 真实 LLM 注入路径 (`ModelResolverProtocol` injection + `GatewayChatModel` fallback 走通)
  - P1-2: subagent child flow `subagent_depth` 透传 (深拷贝父 flow + 累加 depth + 子图实际读到)
  - P1-3: `ExitContractRegistry` strip 之后 messages 不留 contract 累积
  - A4: 轻量单节点 subagent (compiler 识别 + runtime 包装)
  - A5 + Q13: `call_<subgraph_name>` per-tool 编译 + child data 不带父图
  - 异常归一化: `F-v3-model-not-found` / `F-v3-depth-limit` / `F-v3-tool-args-invalid` 各自有 test 触发
- **重写策略**: a1 实施 PR 内, 跟 src 改造同 PR 写新 test。**禁止** "测试随后补"。
- **覆盖率**: unit (单 helper, 例如 `current_subagent_depth` / `assert_subagent_depth_allowed`) + integration (assemble_graph + invoke 端到端 mock LLM) + **e2e 真实 LLM** (跑 1-2 个 reference skill 走完整路径, 用 .env API key)。a3 (Claude) 负责 e2e 主力, a1 写 integration / unit。
