# execution-runtime (engine) — MVP0 Alignment (下一步对齐逻辑)

> **Status**: Filled by a2 (Gemini), 2026-05-20
> **Scope**: Graph 执行装配调度、主入口生命周期 run_skill、节点重试、subagent / call_subgraph 动态工具注入 (audit A4/A5)
> **配套**: 见 [INDEX.md](../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

N/A — 此模块为纯 backend Python library, 无 UI / 无前端调用面。

这里的 "backend Python library" 指 `packages/graph-agent` 里的 Python 引擎代码。尽管 Studio 画布的右侧有一个 "Playground" 测试面板或者 History 的 Run 面板用于触发和展示这段 graph 跑的结果，但引擎的这套运行时逻辑是不包含任何 React 前端组件或是 API HTTP Server 代码的。所有用户看到的界面元素，都是外部包装层（比如 FastAPI WebSocket 流）通过捕获此执行态数据并自行渲染绘制的。这层机制就像发动机，决定了能否发动，但不负责仪表盘的展现。在 MVP0 阶段，它的目标就是稳健地将推演逻辑跑通，不抛出内部底层错误，所有的提示都应当被妥善包装为前端可展示的结构。

## 前端逻辑

N/A — 此模块为纯 backend Python library, 无 UI / 无前端调用面。

前端逻辑仅仅是通过网络接口获得一个 `run_id` 然后通过 WebSocket 或者长轮询来订阅这里的执行状态变迁而已。本库只负责接收核心装配后的参数，把它们丢入 LangGraph 并使用真实的 AI 模型推演到最终退出或报错，前端不对如何发往 LLM、如何清理消息栈等核心行为进行介入。前端对 `ModelResolver` 或 `ExitContractRegistry` 没有任何感知，这些黑盒逻辑全部封装在引擎后端内。因此，这里没有任何前端架构的改动。所有的业务模型全部被收拢在了后端的 Python 实现里。

## 后端功能

### 1. V2.1 真实 LLM 路径模型装载接通 (P0-1 修复)

当前 `run_skill` 在无 mock 模型时会抛出臭名昭著的错误：`[F-v21-graph] SKILL phase requires chat_model`。这是由于引擎缺乏主动寻找并注入模型的机制。实测位置在 `packages/graph-agent/src/graph_agent/core/runner.py:467` 附近的 `chat_model` 装载判定，详见 [baseline.md#后端功能](./baseline.md#后端功能)。这种缺失使得公用的核心入口彻底失效。

MVP0 改造必须建立模型自发现闭环：
我们需要提供完整的 `ModelResolver` 以完成从 `llm-provider-config`（负责具体的 provider API key 存放以及多角色调度设定）到底层真实可推理 LangChain `BaseChatModel` 的无缝切换。这意味着 `run_skill` 在启动期间将借助该 Resolver 自动拿到当前所选的 LLM（区分 `default` 和 `critic` 等不同角色），再把其送入 `assemble_graph` 构造出的图中，确保 `SKILL` node 具备实际对外发起大模型调用的核心推演能力。
这种组装将在每一次图启动时动态进行，以适应随时被改变的用户配置。

### 2. Child flow subagent_depth 状态透传与下发 (P1-2 修复)

目前嵌套层级的探测在实际子图中名存实亡。在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:482` 附近，`_subagent_runnable_config` 仅仅是把 `subagent_depth: depth + 1` 敷衍地写进了 LangGraph 自身控制体系的 `RunnableConfig.metadata`。但真正的运行节点逻辑使用 `parent_state.get("flow", {})` 直接拿到了未增加层级的原始 flow 字典，这就是失效并导致死循环风险激增的根因。由于没有传到底层运行栈，深层网络就会无限制蔓延。

MVP0 的下传透传机制改造：
在执行阶段切入子运行的 `_invoke_subagent_once_t23()` 方法内（大约 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:400` 处），我们必须对 `flow` 进行显式的深拷贝复制并覆写层级属性，接着送入隔离的黑板。只有这样做才能保证父图和子图之间深度状态的安全。

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

### 3. Exit_contract 历史堆积净化去重 (P1-3 修复)

在循环多次的 LLM 对话中，每次注入引导后如果不做清理，它将导致提示消息无底洞般膨胀。在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:244` 处，`inject_exit_contract(messages, phase_ast.exit_contract)` 产生的带有契约提示的消息数组被整体保存入了长期流。ReAct 转的圈数越多，`messages` 中的系统契约指令越多，不仅耗费巨量 Token 甚至会带偏模型注意力，从而引发退化。

MVP0 净化逻辑：
为了根治这一缺陷，我们将设计一层透明拦截净化。引入 `ExitContractRegistry` 数据结构。它能在发往 `model.invoke()` 之前，动态拼接入包含 exit contract 的特殊 `SystemMessage` 结构并记录其内存 ID；但是在接收模型答复之后，更新到 `BlackboardState` 准备回传时，执行净化操作，筛除掉标记有 exit contract 特征的元素。保证依靠 LangGraph 的 `add_messages` 默认行为只会追加纯粹的推断交互历史，保证对话上下文绝不污染。通过这种去重机制，模型的记忆流永远保持精简。

### 4. Subagent 抽象层级轻量单节点化 (A4 改造)

当前的 subagent 机制极其厚重，竟然要求子代理具备完整的 `GRAPH.md`、`io/*.json` 以及复杂的 `phases/` 目录结构。这对于仅仅想跑一个代理完成微型分析任务的场景来讲，带来了巨大阻力。这部分痛点导致复杂的装载代码大量散落在 loader 的拼接处理中，这也被 baseline.md 多次提及。当前逻辑集中在 `packages/graph-agent/src/graph_agent/core/subagents.py`。

MVP0 改造：
我们将支持定义一种纯粹的**轻量单节点**作为 subagent。即它的目录下就只包含一个 Markdown（甚至可能只需要提供 Prompt）和一个工具目录。在引擎遇到这类特殊轻量子图，进入装载时，引擎将为其动态包裹一层虚构的 Graph 执行外壳，或者干脆退化为一个原生的 LangChain 工具节点。这就彻底摆脱了多文件编排的桎梏，实现了随处可调用的灵活性。这也是让 PM 不写复杂 YAML 而完成微操的核心改进。

### 5. Call_subgraph 大流程动态工具暴露 (A5 改造)

LLM 目前只能用上述被拍平的微型 `subagent` 去执行单步闭环任务。对于需要委派一整套带有明确拓扑 `GRAPH.md` 和多节点串联子流程的情况，我们目前没有任何有效入口。这是极其受限的，它阻止了嵌套业务的开发。

MVP0 改造：
我们将向大模型开放名为 `call_subgraph` 的注册工具。它是专门用于让模型基于意图去拉起另外一个独立的复杂 V2.1 skill 流的桥梁封装。模型能够通过传递结构化的参数集来触发一条包含研究、总结、审计等多步骤连环的复杂编排，而对父节点自身依然只是一次 Tool Call 的等待。它在功能上极大地扩充了引擎作为底座的想象空间，也是未来编排庞大系统架构的关键能力。

### 6. 执行器的异常捕获与容错包裹

在运行中，LangGraph 节点由于其不确定性，抛出的各种异常常常使得调用者一头雾水。为此我们将在 `packages/graph-agent/src/graph_agent/core/runner.py:460` 主体注入强大的重试与保护：
任何异常如果不是由我们定义的控制流异常（如隔离违规抛错），都应当被统一降级为 `GraphAgentFatalError`，并附带着精确的错误栈抛给 Studio，使得容错机制标准化。这种包裹层将让那些未被处理的 KeyError 或者 IndexError 变成可被监控和捕捉的形式。

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

本运行时不直接持有持久化的外围 Schema，其关注的 Data Model 主要围绕传递流中对象的控制：

- **子节点上下文控制块**: `child_flow` 字典将作为隔离状态的一部分，在深拷贝后独立发展其 `subagent_depth`、`subagent_validation_retries`，保证内部的递归错误不会影响上游流状态的完整性。这也是为什么 P1-2 必须通过状态下放实现，而不是继续依赖外挂的 metadata，这种分而治之的结构使得整个架构免受内部错误波及。同时，这种传递方式也使得状态的回溯与 debug 成为可能。

## Cross-feature Interaction

本特性的运行阶段极大地牵涉着上下游状态的传递以及前端表现。如果引擎运行时罢工，其它模块全部停摆。

### 1. State 黑板数据的严格沙盒隔离
在执行子图时（无论是通过底层的 `_invoke_subagent_once_t23()` 还是暴露的 `call_subgraph` 大招），最核心的要求是断绝隐式变量继承的灾难。此过程强依赖状态与合约中的全新沙盒规范，黑板必须经历一次彻底的划分阻断。其双向协作及内存分配策略的细节详见：[state-and-io-contract 层的黑板彻底隔离设计](../state-and-io-contract/mvp0-alignment.md#cross-state-blackboard-isolation)。这是保证引擎健壮不崩溃的核心防线。它也从根本上确保了子任务的边界清晰。

### 2. 运行时全维度事件发射
当引擎处于上述调度流中，包括发起单节点的 Tool Call 或是进出复杂的 Subgraph，它都必须在关键切面主动激活 [tracing-and-observability 的 callback event bus](../tracing-and-observability/mvp0-alignment.md#后端功能) 的相关记录。这实现了 PM 最重要的 “看到运行过程输入输出” 的愿景，也是把抽象的 Python 执行轨迹变成 Studio 界面中人类可阅读日志流的唯一核心路径。正是这层打通，才让死板的代码运行具备了可视化的生命力。通过对状态流转的精确控制与事件的分发，这两大模块完成了闭环。

### 7. 详细的状态下发测试策略
为了保证上述的 `subagent_depth` 和 `BlackboardState` 的完全隔离能够在长期的迭代中不被破坏，我们必须在 `packages/graph-agent/tests/core/` 下引入深度的集成测试：
- **测试用例 1: Depth 穿透拦截**。使用 pytest 构建一个具备 `subgraph` 调用的 skill，在其子图中继续进行 `subagent` 调用。我们断言执行流能在第三层准确抛出 `GraphAgentFatalError`，并且错误栈能精准指出触发超限的阶段名。实测发生路径在 `packages/graph-agent/tests/core/test_v21_subagent_executor.py:124`。
- **测试用例 2: 独立流隔离**。我们将在父图的 `flow` 注入特殊的 `test_marker=1`。断言当进入 `_invoke_subagent_once_t23()` 后，子图如果在其 `LOGIC` 阶段修改了 `flow["test_marker"] = 2`，在退出子图后，父图的 `flow["test_marker"]` 必须依旧等于 `1`。这种完全隔离是 A6 设计成功的基础。

### 8. LangChain RunnableConfig 的彻底改造
在 LangGraph 中，除了 State 之外，`RunnableConfig` 的 `metadata` 和 `callbacks` 也是信息传递的重要途径。
MVP0 将重新梳理这一块的装载。目前在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:482` 中的 `_subagent_runnable_config`：
- 我们不仅要传递 `thread_id`，还需要将 `run_id` 与当前的 `phase_id` 拼装成 `parent_id`。
- 将清理不必要的自定义 metadata，统一将其归还给 `flow` 控制，让 config 只负责最原生的并发控制与异步调度，保证职责单一。

### 9. 异常分发与状态码体系
为了配合前端界面的多状态展示，我们在抛出异常时需要完善内部的 Error Code 体系：
```python
class ErrorCode:
    MODEL_NOT_FOUND = "F-v21-model-not-found"
    DEPTH_LIMIT_REACHED = "F-v21-depth-limit"
    INVALID_TOOL_ARGS = "F-v21-tool-args-invalid"
```
这将在 `packages/graph-agent/src/graph_agent/core/runner.py:460` 附近被强绑定，最终交付给 Tracer。
