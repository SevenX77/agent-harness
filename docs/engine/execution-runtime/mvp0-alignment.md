# execution-runtime (engine) — MVP0 Alignment (下一步对齐逻辑)

> **Status**: Filled by a1 (Codex) based on a2 framework, 2026-05-20
> **Scope**: Graph 执行装配调度、主入口生命周期 run_skill、节点重试、subagent / call_subgraph 动态工具注入 (audit A4/A5)
> **配套**: 见 [INDEX.md](../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

N/A — 此模块为纯 backend Python library, 无 UI / 无前端调用面。

Execution runtime 是“真正把编译好的 skill 跑起来”的引擎层。PM 在 Studio 里看到的 Run 按钮、Trace 流和 History 结果，都不是这里直接渲染的 UI；它们只是消费 runtime 产生的结果、错误和事件。当前 V2.1 主线在 `_run_v21_skill_dict()` 里执行 `compile_skill -> assemble_graph -> graph.invoke`，见 `packages/graph-agent/src/graph_agent/core/runner.py:451` 到 `packages/graph-agent/src/graph_agent/core/runner.py:486`。

MVP0 runtime 的用户价值是：点击运行后，真实 LLM 能被自动解析并注入，子图不会偷读父图黑板，ReAct 消息不会无限堆积，错误能以可展示的 code 返回，而不是裸 Python RuntimeError。

## 前端逻辑

N/A — 此模块为纯 backend Python library, 无 UI / 无前端调用面。

React 不调用 `assemble_graph()`，也不理解 LangGraph reducer。前端最多通过 Studio 后端启动 run，再订阅事件。Runtime 与前端的边界应该是结构化结果和 trace event，而不是共享内部 Python state。V2.1 当前还会丢弃 callbacks，代码在 `packages/graph-agent/src/graph_agent/core/runner.py:462`，所以 MVP0 需要把 observability 接线放回 runtime，但不是让前端介入执行。

## 后端功能

### 1. V2.1 真实 LLM 路径模型装载接通 (P0-1 修复)

MVP0 SHOULD 让 `run_skill()` 在没有 mock 的情况下也能跑真实 SKILL phase。当前 `_run_v21_skill_dict()` 只在传入 `mock_llm` 时给 `chat_model` 赋值，否则就是 None，见 `packages/graph-agent/src/graph_agent/core/runner.py:467` 到 `packages/graph-agent/src/graph_agent/core/runner.py:469`。SKILL node 一旦发现 `chat_model is None`，直接抛 `RuntimeError("[F-v21-graph] SKILL phase requires chat_model")`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:229` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:234`。

这里的 ModelResolver 是“把角色名解析成真实 LangChain 模型”的工厂。例子：phase frontmatter 写 `llm_role: analyst`，resolver 查 Studio 的 roles/provider 配置，得到 Anthropic/OpenAI/Gemini 等具体模型实例，然后交给 `assemble_graph()`。当前 `assemble_graph(compiled, chat_model=...)` 已经有注入参数，签名在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:55` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:60`，MVP0 不需要改 LangGraph 装配入口，只需要在 runner 主线补上解析路径。

MVP0 WILL 把“缺模型”从裸 RuntimeError 升级成结构化错误，例如 `F-v21-model-not-found`。这样 Studio 可以告诉用户“没有配置 copilot/default 模型”而不是“SKILL phase requires chat_model”。

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

### 5. Call_subgraph 大流程动态工具暴露 (A5 改造)

MVP0 SHOULD 新增 `call_subgraph` 工具，让 LLM 在 SKILL phase 中主动调用一个完整 graph skill。它和当前 `SUBGRAPH` phase 不同：`SUBGRAPH` 是固定拓扑节点，执行到那里自动跑；`call_subgraph` 是 LLM 决策时的工具调用，模型可以按任务需要选择是否调用。

当前 `_build_skill_node()` 收集业务 tools、subagent tools、framework tools 和 `finish_task`，代码在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:184` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:227`。subagent tool map 只来自 `compiled.subagents_by_phase`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:301` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:308`。没有 subgraph registry，也没有 `call_subgraph` 工具族。

MVP0 WILL 把 call_subgraph 设计成显式输入沙盒：LLM 必须传 `child_graph_path` 和 `explicit_inputs`，父图 `data` 不会隐式继承。这个约束与 [state-and-io-contract 的 A6 黑板隔离](../state-and-io-contract/mvp0-alignment.md#cross-state-blackboard-isolation) 是同一个安全边界。

### 6. 执行器的异常捕获与容错包裹

MVP0 SHOULD 把运行期异常归一化。当前 `run_skill()` 成功时会包装 `WorkflowResult`，异常分支只捕获 `GraphAgentError`，见 `packages/graph-agent/src/graph_agent/core/runner.py:195` 到 `packages/graph-agent/src/graph_agent/core/runner.py:224`。但 P0-1 的无模型错误是裸 `RuntimeError`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:233` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:234`。

MVP0 WILL 让 runtime node 抛出的可预期错误使用统一 code，例如 `MODEL_NOT_FOUND`、`DEPTH_LIMIT_REACHED`、`INVALID_TOOL_ARGS`。未知异常也应被包进 `GraphAgentFatalError`，并交给 tracing 发出 `EXCEPTION` 事件。这样 Studio 不需要按 Python 异常类猜测用户提示。

## API

以下是配合上述 MVP0 功能变更需要全新定义或者调整的重要接口签名与结构体。它们是联结不同层次能力的骨干，不仅是供内部调用，也是未来接入 CLI 等外界形态的保障。

### 1. ModelResolver 接口声明
用于接管 `run_skill` 中空缺的大模型注入能力（解决 P0-1），它在 `packages/graph-agent/src/graph_agent/core/models.py` 的预计详细形态如下：

```python
from typing import Any
from pydantic import BaseModel
from langchain_core.language_models.chat_models import BaseChatModel

class ModelInfo(BaseModel):
    provider: str
    model_name: str
    roles: list[str]

class ModelResolver:
    def __init__(self, llm_routing: dict[str, Any]) -> None:
        """Initialize resolver with Studio's LLM roles configuration.
        
        Args:
            llm_routing: System-level configuration binding roles to models,
                         typically sourced from `llm_roles.yaml` configuration.
        """
        self.routing = llm_routing

    def resolve(self, role_or_provider: str) -> BaseChatModel:
        """Resolve a specific role (e.g. 'default', 'critic') to a LangChain model.
        
        This factory instantiates the precise vendor implementation (OpenAI, 
        Anthropic, Gemini, etc.) based on the mapped configuration.
        
        Args:
            role_or_provider: String identifier usually from node frontmatter.
            
        Returns:
            A bound BaseChatModel ready to be injected into SKILL nodes.
            
        Raises:
            ModelResolutionError: If the specified role is unmapped.
        """
        pass
        
    def list_available(self) -> list[ModelInfo]:
        """Return list of models available in the configured routing."""
        pass
```

MVP0 SHOULD 在 `_run_v21_skill_dict()` 中使用 resolver，而不是要求调用方手动传 `mock_llm`。`mock_llm` 仍可保留为测试覆盖入口。

### 2. call_subgraph 工具封装完整签名
对应 A5 阶段中 LLM 对外界发起复杂编排的请求入口。它的 Python 端调用承载将是这个函数：

```python
from pathlib import Path
from typing import Any
from langchain_core.language_models.chat_models import BaseChatModel

def call_subgraph(
    child_graph_path: Path,
    explicit_inputs: dict[str, Any],
    chat_model: BaseChatModel | None = None,
) -> dict[str, Any]:
    """Execute child graph in a strictly isolated blackboard sandbox.

    This executor bridges the gap between an LLM's tool call desire and
    the complex multi-step execution engine. It compiles and invokes the
    target graph dynamically without leaking state.

    Args:
        child_graph_path: Absolute V2.1 skill root directory of child graph.
        explicit_inputs: The exact dictionary mapping to `io/inputs.json`.
            Parent blackboard is NOT implicitly inherited under any condition.
        chat_model: Optional override for child's LLM routing. Defaults to 
            inheriting the parent's default model resolver setup.

    Returns:
        Final child blackboard ``data`` dict, namespaced by phase outputs,
        ready to be digested back as a tool execution result.

    Raises:
        SubgraphIsolationError: If child tries to read parent-only keys or write out of bounds.
        CompileIssue: If the requested child graph is structurally invalid.
    """
    pass
```

### 3. ExitContractRegistry 去重服务
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
