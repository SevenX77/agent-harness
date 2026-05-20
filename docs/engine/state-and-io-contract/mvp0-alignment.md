# state-and-io-contract (engine) — MVP0 Alignment (下一步对齐逻辑)

> **Status**: Filled by a2 (Gemini), 2026-05-20
> **Scope**: BlackboardState 规约 (data/flow/messages)、Reducer 并发冲突控制、阶段级 IO 隔离、Runtime Input 漏斗 (audit A1/A2/A3/A6)
> **配套**: 见 [INDEX.md](../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

N/A — 此模块为纯 backend Python library, 无 UI / 无前端调用面。

这里的 "backend Python library" 指 `packages/graph-agent` 里的 Python 引擎代码，而不是 Studio 的 FastAPI 后端接口层，也绝对不涉及 React 前端展现。即使 PM 或者开发者能在画布的 Playground 面板看到最终过滤出的输入框表单或是执行结束输出的阶段结果列表，那些也都只是前端主动利用 HTTP 查询拿到的数据片段而已。在这个引擎合约模块里，只涉及最为严厉的 Python 内存模型拆解和运行时的无情阻断逻辑，没有任何视觉界面产物直接在其中构成。这套底层架构的存在，恰恰是为了让前端展示的数据更加准确，并避免不必要的噪声干扰。隔离做不好，前端必然呈现一片混沌。

## 前端逻辑

N/A — 此模块为纯 backend Python library, 无 UI / 无前端调用面。

状态字典（Dict）在节点间的智能合并、顶层调用时的入口数据大过滤拦截、Phase 执行时对非授权属性的屏蔽，这一切行为均发生在 LangGraph 控制链及引擎核心装饰器层。前端除了被动接受过滤完成的状态体或者接收 `InputFunnelValidationError` 等明确错误反馈用于告警弹窗，完全无需了解底层的隔离方式和 Reducer 并发控制机制。引擎在内部就默默把所有的状态隔离干净了，前端业务只管放心使用经过洗礼的纯净数据。

## 后端功能

### 1. 升级 Reducer 智能合并语义 (P0-3 修复)

当前负责图上黑板数据整合的 `shallow_dict_merge` 函数存在一刀切的严重缺陷，它位于 `packages/graph-agent/src/graph_agent/runtime/state.py:13`，现状探讨参见 [baseline.md#Data Model / State](./baseline.md#Data-Model-/-State)。只要下游发生任何已存在键的同名覆写，它都会暴力地以 `[F-v21-state-conflict]` 进行封杀。这不仅仅阻挡了并行的竞争，它错误地也拒绝了合理且必须的串行单线程状态更新。这就导致简单的覆盖行为被视为非法。这严重违背了常见的顺序推演直觉。

MVP0 改造中，我们要实现一个基于 `LangGraph` channel 及 super-step 特征感知的 `SmartReducer`。它能够动态辨别当前发生的数据回写究竟是跨 Super-step 的顺序演进，还是位于同一并发 Super-step 之中的并行数据风暴。若是前者，则优雅放行实现类似 `dict.update` (right overwrites left) 的功能，达成状态迭代；若是后者，则维持原有的致命阻塞防爆行为，实现完美兼顾顺序覆盖和并行防范的运行逻辑。这一机制的革新彻底解锁了 LangGraph 中节点自如覆盖前置临时结果的可能。

### 2. 引入 Runtime Input Funnel (A1 补全)

目前 `run_skill(**inputs)` 在启动之际仅仅是无脑做了一次 `dict(inputs)` 后强塞入核心黑板，见 `packages/graph-agent/src/graph_agent/core/runner.py:473` 附近。这将外部无效、杂乱或非法的参数直接暴露给了所有的下层逻辑，导致严重的脏数据污染和未定义行为，完全破坏了隔离层的安全性。

MVP0 将收口此处。在 `run_skill` 的执行入口，引擎必须首先调用一个前置清洗管道（Input Funnel）。该组件会加载由 `io/inputs.json` 解析衍生出的强类型校验 Schema，对 `inputs` 参数群展开审查。它会：
- 丢弃未声明的未知属性，严格遵守白名单机制。
- 自动进行类型转换（如将字符串数字安全强转为 int）。
- 在关键数据缺失或格式完全背离时，在执行的最前端直接报出格式化异常，提前终止以绝后患。只有经过它净化的 `canonical initial data`，才会被用于构造 `BlackboardState.data`。这保障了整个流转大盘是无毒的。

### 3. 细粒度 Phase-Level IO 契约与防覆盖机制 (A2/A3 补全)

目前由于设计缺陷，所有子环节都拥有对 `state.data` 全局的读取和写入权利，这是隐患深重的设计灾难。
- **A2 节点级沙箱构建**: 我们将在 `packages/graph-agent/src/graph_agent/core/phase_node.py` 的执行 Wrapper 内做严格隔离。节点在准备执行并构建提示词/上下文之前，引擎将依据其自身的声明 Schema，组装出一份仅涵盖所需键的纯净 `phase_input` 字典。节点在此轮推断中犹如戴上眼罩，只能看到这些它理应看到的数据。这种 “最小权限原则” 极大地抑制了意外依赖。
- **A3 SUBGRAPH 防越权写入防御**: 为了阻止被委托的独立子图或有越权倾向的 LOGIC 阶段覆盖了父级的同名关键 `flow` 或核心 `data`，我们将在引擎上对节点回写行为进行限制。引擎将实施前缀命名空间封装：强制挂载到类似 `phase_outputs[phase_id].*` 之下，除非明确得到授权。通过这种手段，保证各节点只在自己的结果空间折腾，互不干扰。

### 4. 彻底隔离 Child Graph 黑板状态 (A6 补全) {#cross-state-blackboard-isolation}

这是一个重大的架构修复跨特性机制。目前，当我们触发一个 `subagent`（或者是即将新增的 `call_subgraph`）时，它们竟然是通过直接拉取并连带继承全套 `parent_state.get("data", {})` 作为启动黑板基础。这把全量秘密喂给了不需要它的下级环境，破坏了沙箱的隔离边界，让权限控制形同虚设，很容易造成下游恶意串改上游关键状态。实现路径在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py` 内部。

MVP0 必须断决这种隐式继承关系。无论何时，当从当前主图衍生并进入一个新图实例之际，这颗全新的 LangGraph 种子在执行初始化时，其所得到的 `BlackboardState.data` **被强制且完全等于**来自 `explicit_tool_input_only` 的参数传值（即经过显式工具映射的部分）。决不留存一丝一毫多余的父级隐患数据，这是确保模型推断安全与组件化图级复用的死规定。这使得图的嵌套组合变得稳定可期。

### 5. 防污染的垃圾回收策略
配合上述沙箱设计，任何离开 `subagent` 或是 `phase_input` 临时内存区的处理，在退出 LangGraph 对应节点后，都必须在 Python 层级触发对象回收与引用断开。这能彻底防范引用类型的属性（例如 list 或嵌套 dict）被下游恶意篡改后反射回父级结构。这一行为要求 `copy.deepcopy` 的大面积安全铺设。

## API

以下为这些重要修改需要引入引擎侧的 API 签名展示，展示了更健壮的新设计。所有的实现都需要严防黑板溢出和不符合预期的参数传递。

### 1. SmartReducer 接口实现定义
对应 P0-3 缺陷的彻底解决：

```python
from typing import Any

def smart_dict_reducer(
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge data with intelligent conflict detection for graph paths.
    
    This replaces the overly aggressive `shallow_dict_merge`. It evaluates
    the metadata context (e.g., from LangGraph's super-step or active 
    channel context injection) to allow sequential overrides 
    while strictly blocking concurrent writes to the exact same key 
    during parallel fan-in branches.

    Args:
        left: The existing blackboard dictionary state.
        right: The new dictionary update arriving from a phase node exit.

    Returns:
        The smartly merged blackboard data, preferring `right` where legal.

    Raises:
        GraphAgentFatalError: If an undeniable concurrent collision is detected.
    """
    pass
```

### 2. Input Funnel 过滤签名定义
对应 A1 的强依赖启动拦截函数，通过 jsonschema 进行防御：

```python
from typing import Any

def filter_runtime_inputs(
    raw_kwargs: dict[str, Any], 
    schema: dict[str, Any]
) -> dict[str, Any]:
    """Validate and funnel incoming start state data strictly against schema.
    
    This function utilizes `jsonschema` strict validation to enforce
    properties. Unmapped or undeclared fields in `raw_kwargs` are explicitly
    dropped to ensure absolute purity before placement into the global state.

    Args:
        raw_kwargs: The incoming raw data dict from `run_skill(**inputs)`.
        schema: Evaluated draft JSONSchema definition from `io/inputs.json`.
        
    Returns:
        Canonical initial data matching schema properties safely.
        
    Raises:
        InputFunnelValidationError: Structured error if types mismatch or 
            required inputs are fundamentally omitted.
    """
    pass
```

## Data Model / State

### 1. BlackBoard 状态结构的隔离深化
随着黑板完全向 A2 描述的那样进行分阶段治理，原有的单一 `data` 聚合形式在设计思维中演变为多个分段概念区。尽管出于对旧模块兼容性考量我们依然把它们承载在原 `BlackboardState` 之中（代码位于 `packages/graph-agent/src/graph_agent/runtime/state.py:35` 附近）：

- **`inputs` 专有区**：容纳从 `Input Funnel` 处理后形成的数据集，它被设定为全生命周期只读，作为大局依赖源，绝对禁止任何修改。
- **`phase_outputs` 字典树**：形如 `phase_outputs = {"analyze": {...}, "search": {...}}`，成为节点专属的、被隔离保护的存储地带。
- 只有通过专门包装的节点装载器函数，它们才会被按需挑选组合，形成一个局部的、轻量的 `phase_input` 发送至目标工作空间，并在完工后反向提取写回树中。这就完成了从逻辑到物理层面的彻底切割。

### 2. 状态映射器模型 (StateMapper)
由于状态不再是扁平的铺开，可能需要一个新的 `StateMapper` 工具类协助负责。它依据静态期间生成的 `io.inputs` 要求，从 `inputs` 或 `phase_outputs` 的分段中提取需要的数据：
```python
class StateMapper:
    def build_phase_input(self, data: dict, required_schema: dict) -> dict: ...
    def wrap_phase_output(self, phase_id: str, output: dict) -> dict: ...
```

## Cross-feature Interaction

本机制的完善是跨越整个生命周期的枢纽，涉及多个其他模块的密切配合：

- **与 Compilation 特性的深度耦合**:
  不论是 `Input Funnel` 还是 `Phase-Level IO` 拦截，这里用于驱动过滤和裁切漏斗逻辑的所有 JSONSchema 数据来源依据，全部是 [skill-compilation AST 解析时注入并在图检验中查阅完毕的 io_schema 产物](../skill-compilation/mvp0-alignment.md#后端功能)。静态编译阶段提供法则，此模块提供基于法则的无情动态执法。这形成了完整的信任链条。
  
- **向 Execution-Runtime 执行装载提供支撑**:
  子图与子代理的启动，必然将遭受这层 A6 级黑板屏蔽切断继承的洗礼。这在 [execution-runtime 的运行分发与隔离调用机制](../execution-runtime/mvp0-alignment.md#cross-feature-interaction) 中会直接体现。它迫使调用流分发器在切分支时进行无情的状态抛弃，而不是再将上层黑板的冗余大字段漫无目的地向深处传递扩散。正是因为这种相互作用，才保证了大型架构在伸缩时的一致性。

### 6. Phase Wrapper 的上下文准备过程
在落实 A2 时，我们在 `packages/graph-agent/src/graph_agent/core/phase_node.py` 中引入了 `phase_input` 的装载机制。它的执行细则如下：
1. **阶段提取**: 从 `BlackboardState.inputs` 中提取当前节点在 `io.inputs` 中声明关联的全局字段。
2. **前置合并**: 从 `BlackboardState.phase_outputs` 遍历当前节点的 `depends_on` 列表，将合法的输出组装进来。如果出现命名冲突（比如上游的两个节点都输出了 `text` 且当前节点需要 `text`），触发 `[F-v21-io-conflict]` 阻断。
3. **严格过滤**: 确保任何未声明在这个阶段的输入列表里的属性，都绝对不会被传入给大模型。这种控制大幅度降低了大模型在收到过多信息时产生幻觉（Hallucination）的几率。

### 7. 对遗留字典 `shallow_dict_merge` 的退役计划
由于 P0-3 所指出的 `packages/graph-agent/src/graph_agent/runtime/state.py:13` 中的函数严重阻碍了单线状态推进，在替换为 `SmartReducer` 之后，我们需要全量清理旧有函数的引用。
- 在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py` 里面的 `Annotated[dict, shallow_dict_merge]` 会被完全替换为 `Annotated[dict, smart_dict_reducer]`。
- 为了兼顾可能依赖旧版行为的少部分 V2.0 遗留测例，我们在一段时间内可能保留原函数名但挂上 `@deprecated` 标志。

### 8. 输入过滤机制的数据纠错与补全 (Coercion)
关于 A1 中描述的 `Input Funnel`，它不仅承担丢弃无效数据的责任，更在某些安全范围内负责补全：
- **默认值**: 如果 `io/inputs.json` 中某属性标明了 `default` 且外部未传，Funnel 会补上它。
- **强制转换**: 对于 Pydantic 支持的安全类型转换（例如 `str` 转 `bool`），引擎会做最佳努力处理，使得 CLI 命令行或者外部 HTTP 触发时，容错率得到提升。
这种鲁棒性的提升，是使得整个执行体系摆脱脆弱标签的关键，这也是我们在 `packages/graph-agent/src/graph_agent/core/runner.py` 主线逻辑中需要着重把控的防御屏障。

### 6. Phase Wrapper 的上下文准备过程
在落实 A2 时，我们在 `packages/graph-agent/src/graph_agent/core/phase_node.py` 中引入了 `phase_input` 的装载机制。它的执行细则如下：
1. **阶段提取**: 从 `BlackboardState.inputs` 中提取当前节点在 `io.inputs` 中声明关联的全局字段。
2. **前置合并**: 从 `BlackboardState.phase_outputs` 遍历当前节点的 `depends_on` 列表，将合法的输出组装进来。如果出现命名冲突（比如上游的两个节点都输出了 `text` 且当前节点需要 `text`），触发 `[F-v21-io-conflict]` 阻断。
3. **严格过滤**: 确保任何未声明在这个阶段的输入列表里的属性，都绝对不会被传入给大模型。这种控制大幅度降低了大模型在收到过多信息时产生幻觉（Hallucination）的几率。

### 7. 对遗留字典 `shallow_dict_merge` 的退役计划
由于 P0-3 所指出的 `packages/graph-agent/src/graph_agent/runtime/state.py:13` 中的函数严重阻碍了单线状态推进，在替换为 `SmartReducer` 之后，我们需要全量清理旧有函数的引用。
- 在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py` 里面的 `Annotated[dict, shallow_dict_merge]` 会被完全替换为 `Annotated[dict, smart_dict_reducer]`。
- 为了兼顾可能依赖旧版行为的少部分 V2.0 遗留测例，我们在一段时间内可能保留原函数名但挂上 `@deprecated` 标志。

### 8. 输入过滤机制的数据纠错与补全 (Coercion)
关于 A1 中描述的 `Input Funnel`，它不仅承担丢弃无效数据的责任，更在某些安全范围内负责补全：
- **默认值**: 如果 `io/inputs.json` 中某属性标明了 `default` 且外部未传，Funnel 会补上它。
- **强制转换**: 对于 Pydantic 支持的安全类型转换（例如 `str` 转 `bool`），引擎会做最佳努力处理，使得 CLI 命令行或者外部 HTTP 触发时，容错率得到提升。
这种鲁棒性的提升，是使得整个执行体系摆脱脆弱标签的关键，这也是我们在 `packages/graph-agent/src/graph_agent/core/runner.py` 主线逻辑中需要着重把控的防御屏障。

### 6. Phase Wrapper 的上下文准备过程
在落实 A2 时，我们在 `packages/graph-agent/src/graph_agent/core/phase_node.py` 中引入了 `phase_input` 的装载机制。它的执行细则如下：
1. **阶段提取**: 从 `BlackboardState.inputs` 中提取当前节点在 `io.inputs` 中声明关联的全局字段。
2. **前置合并**: 从 `BlackboardState.phase_outputs` 遍历当前节点的 `depends_on` 列表，将合法的输出组装进来。如果出现命名冲突（比如上游的两个节点都输出了 `text` 且当前节点需要 `text`），触发 `[F-v21-io-conflict]` 阻断。
3. **严格过滤**: 确保任何未声明在这个阶段的输入列表里的属性，都绝对不会被传入给大模型。这种控制大幅度降低了大模型在收到过多信息时产生幻觉（Hallucination）的几率。

### 7. 对遗留字典 `shallow_dict_merge` 的退役计划
由于 P0-3 所指出的 `packages/graph-agent/src/graph_agent/runtime/state.py:13` 中的函数严重阻碍了单线状态推进，在替换为 `SmartReducer` 之后，我们需要全量清理旧有函数的引用。
- 在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py` 里面的 `Annotated[dict, shallow_dict_merge]` 会被完全替换为 `Annotated[dict, smart_dict_reducer]`。
- 为了兼顾可能依赖旧版行为的少部分 V2.0 遗留测例，我们在一段时间内可能保留原函数名但挂上 `@deprecated` 标志。

### 8. 输入过滤机制的数据纠错与补全 (Coercion)
关于 A1 中描述的 `Input Funnel`，它不仅承担丢弃无效数据的责任，更在某些安全范围内负责补全：
- **默认值**: 如果 `io/inputs.json` 中某属性标明了 `default` 且外部未传，Funnel 会补上它。
- **强制转换**: 对于 Pydantic 支持的安全类型转换（例如 `str` 转 `bool`），引擎会做最佳努力处理，使得 CLI 命令行或者外部 HTTP 触发时，容错率得到提升。
这种鲁棒性的提升，是使得整个执行体系摆脱脆弱标签的关键，这也是我们在 `packages/graph-agent/src/graph_agent/core/runner.py` 主线逻辑中需要着重把控的防御屏障。



### 9. 状态重置与清理策略
在很多情况下，`run_skill` 可能需要被反复触发（比如在 Playground 里的批量测试）。如果核心 `data` 没有被完全重置，很容易出现数据串联导致的脏读脏写。
在 MVP0 中：
- 我们规定每次启动时，不仅仅是清空 `BlackboardState`，更是要在内部主动调用垃圾回收机制（Garbage Collection），释放掉所有大体积的对象引用（例如上一次运行加载的巨型 DataFrame 或是图像 Buffer）。
- 在 `packages/graph-agent/src/graph_agent/runtime/state.py` 内部会增加 `clear_state()` 的支持。

### 10. 长时运行图的状态保存机制 (Checkpointing)
尽管目前的重点是把流程隔离并推断跑通，但是考虑到后续的扩展，这套 Reducer 和黑板机制不能对外部是绝对封闭的：
- 在 `packages/graph-agent/src/graph_agent/core/checkpointer.py` (如果存在) 或 LangGraph 原生的 Checkpointer 的协作下，我们隔离好的 `phase_outputs` 及其字典树，能完美适配 JSON 的序列化。
- 这意味着我们以后在实现断点续传（Pause and Resume）时，由于状态完全按 Phase 隔离，我们可以精准地知道哪些步骤不需要重跑。

### 9. 状态重置与清理策略
在很多情况下，`run_skill` 可能需要被反复触发（比如在 Playground 里的批量测试）。如果核心 `data` 没有被完全重置，很容易出现数据串联导致的脏读脏写。
在 MVP0 中：
- 我们规定每次启动时，不仅仅是清空 `BlackboardState`，更是要在内部主动调用垃圾回收机制（Garbage Collection），释放掉所有大体积的对象引用（例如上一次运行加载的巨型 DataFrame 或是图像 Buffer）。
- 在 `packages/graph-agent/src/graph_agent/runtime/state.py` 内部会增加 `clear_state()` 的支持。

### 10. 长时运行图的状态保存机制 (Checkpointing)
尽管目前的重点是把流程隔离并推断跑通，但是考虑到后续的扩展，这套 Reducer 和黑板机制不能对外部是绝对封闭的：
- 在 `packages/graph-agent/src/graph_agent/core/checkpointer.py` (如果存在) 或 LangGraph 原生的 Checkpointer 的协作下，我们隔离好的 `phase_outputs` 及其字典树，能完美适配 JSON 的序列化。
- 这意味着我们以后在实现断点续传（Pause and Resume）时，由于状态完全按 Phase 隔离，我们可以精准地知道哪些步骤不需要重跑。

### 9. 状态重置与清理策略
在很多情况下，`run_skill` 可能需要被反复触发（比如在 Playground 里的批量测试）。如果核心 `data` 没有被完全重置，很容易出现数据串联导致的脏读脏写。
在 MVP0 中：
- 我们规定每次启动时，不仅仅是清空 `BlackboardState`，更是要在内部主动调用垃圾回收机制（Garbage Collection），释放掉所有大体积的对象引用（例如上一次运行加载的巨型 DataFrame 或是图像 Buffer）。
- 在 `packages/graph-agent/src/graph_agent/runtime/state.py` 内部会增加 `clear_state()` 的支持。

### 10. 长时运行图的状态保存机制 (Checkpointing)
尽管目前的重点是把流程隔离并推断跑通，但是考虑到后续的扩展，这套 Reducer 和黑板机制不能对外部是绝对封闭的：
- 在 `packages/graph-agent/src/graph_agent/core/checkpointer.py` (如果存在) 或 LangGraph 原生的 Checkpointer 的协作下，我们隔离好的 `phase_outputs` 及其字典树，能完美适配 JSON 的序列化。
- 这意味着我们以后在实现断点续传（Pause and Resume）时，由于状态完全按 Phase 隔离，我们可以精准地知道哪些步骤不需要重跑。

### 9. 状态重置与清理策略
在很多情况下，`run_skill` 可能需要被反复触发（比如在 Playground 里的批量测试）。如果核心 `data` 没有被完全重置，很容易出现数据串联导致的脏读脏写。
在 MVP0 中：
- 我们规定每次启动时，不仅仅是清空 `BlackboardState`，更是要在内部主动调用垃圾回收机制（Garbage Collection），释放掉所有大体积的对象引用（例如上一次运行加载的巨型 DataFrame 或是图像 Buffer）。
- 在 `packages/graph-agent/src/graph_agent/runtime/state.py` 内部会增加 `clear_state()` 的支持。

### 10. 长时运行图的状态保存机制 (Checkpointing)
尽管目前的重点是把流程隔离并推断跑通，但是考虑到后续的扩展，这套 Reducer 和黑板机制不能对外部是绝对封闭的：
- 在 `packages/graph-agent/src/graph_agent/core/checkpointer.py` (如果存在) 或 LangGraph 原生的 Checkpointer 的协作下，我们隔离好的 `phase_outputs` 及其字典树，能完美适配 JSON 的序列化。
- 这意味着我们以后在实现断点续传（Pause and Resume）时，由于状态完全按 Phase 隔离，我们可以精准地知道哪些步骤不需要重跑。



### 11. 与日志及 Trace 观测体系的数据同步
这里的数据沙箱隔离机制并非仅仅服务于业务的健康运转。在 `tracing-and-observability` 特性的实现中，我们需要向 Studio 返回阶段级别的完整输入输出镜像。
- 这些日志所依赖的核心数据抓取点，就是建立在经过 `Input Funnel` 过滤以及 `Phase Wrapper` 切分的纯粹结构体之上的。
- 如果没有这一套无冗余的数据合约作保障，Trace 记录中会充斥着全集数据，造成网络和存储的双重灾难。

### 11. 与日志及 Trace 观测体系的数据同步
这里的数据沙箱隔离机制并非仅仅服务于业务的健康运转。在 `tracing-and-observability` 特性的实现中，我们需要向 Studio 返回阶段级别的完整输入输出镜像。
- 这些日志所依赖的核心数据抓取点，就是建立在经过 `Input Funnel` 过滤以及 `Phase Wrapper` 切分的纯粹结构体之上的。
- 如果没有这一套无冗余的数据合约作保障，Trace 记录中会充斥着全集数据，造成网络和存储的双重灾难。

