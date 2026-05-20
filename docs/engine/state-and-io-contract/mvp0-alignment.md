# state-and-io-contract (engine) — MVP0 Alignment (下一步对齐逻辑)

> **Status**: Filled by a1 (Codex) based on a2 framework, 2026-05-20
> **Scope**: BlackboardState 规约 (data/flow/messages)、Reducer 并发冲突控制、阶段级 IO 隔离、Runtime Input 漏斗 (audit A1/A2/A3/A6)
> **配套**: 见 [INDEX.md](../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

N/A — 此模块为纯 backend Python library, 无 UI / 无前端调用面。

本模块定义的是 engine 内存里的“黑板”和 IO 边界。黑板可以理解成每次运行时各节点共享的一张工作表：`data` 放业务数据，`flow` 放控制状态，`messages` 放 LLM 对话。当前 `BlackboardState` 定义在 `packages/graph-agent/src/graph_agent/runtime/state.py:35` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:41`。它不会直接渲染 UI，但它决定 Studio 最终看到的输入输出、trace 和错误是否干净。

## 前端逻辑

N/A — 此模块为纯 backend Python library, 无 UI / 无前端调用面。

前端不执行 reducer，也不持有 `BlackboardState`。Studio 只会看到 runtime 最终返回的 context，当前 V2.1 runner 用 `dict(result.get("data", {}))` 构造 context，见 `packages/graph-agent/src/graph_agent/core/runner.py:480` 到 `packages/graph-agent/src/graph_agent/core/runner.py:486`。MVP0 的目标是让这份 context 来自严格漏斗和 phase 输出，而不是来自一块所有节点都能读写的全局 dict。

## 后端功能

### 1. 升级 Reducer 智能合并语义 (P0-3 修复)

MVP0 SHOULD 替换当前过度保守的 `shallow_dict_merge`。Reducer 是 LangGraph 合并节点返回 state delta 的函数；当前 `data` 字段使用 `Annotated[dict[str, Any], shallow_dict_merge]`，见 `packages/graph-agent/src/graph_agent/runtime/state.py:38`。`shallow_dict_merge()` 定义在 `packages/graph-agent/src/graph_agent/runtime/state.py:13` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:32`。

当前行为是：如果 `left` 已经有某个 key，而 `right` 也写同一个 key，就抛 `[F-v21-state-conflict]`，见 `packages/graph-agent/src/graph_agent/runtime/state.py:24` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:30`。这能拦住并行 fan-in 分支同时写 `foo` 的危险场景，但也误伤顺序覆盖。例子：`{a: 1}` 后面一个 phase 合法地产出 `{a: 2}`，当前 reducer 也会抛错，而 PM 直觉上会认为“后一步更新前一步结果”是合理行为。

MVP0 WILL 引入 `smart_dict_reducer`：同一 super-step 内的并行冲突继续拦截；跨 step 的顺序覆盖允许采用 `dict.update` 语义，即 `{a:1} ∪ {a:2} -> {a:2}`。如果 LangGraph 不能直接给 reducer 足够上下文，MVP0 SHOULD 通过状态结构调整避免顶层同名写入，例如把 phase 输出放入 `phase_outputs[phase_id]`，减少 reducer 对并发来源的猜测。

落地时还要保留一类强阻断：两个并行分支同时写同一个 phase output slot，仍然是编排错误。MVP0 SHOULD 在错误里带上 key、左值来源、右值来源和 super-step 信息。现在的错误 message 只写 `key`、left、right，见 `packages/graph-agent/src/graph_agent/runtime/state.py:27` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:30`，足够给开发者看，但不足以让 Studio 把错误定位回两条 fan-in 边。

### 2. 引入 Runtime Input Funnel (A1 补全)

MVP0 SHOULD 在 `run_skill(**inputs)` 入口先过滤和校验输入。当前 `_run_v21_skill_dict()` 直接把外部 kwargs 做成 `dict(inputs)` 放入 `data`，见 `packages/graph-agent/src/graph_agent/core/runner.py:471` 到 `packages/graph-agent/src/graph_agent/core/runner.py:477`。这意味着未知字段、类型错误字段、缺失 required 字段都可能进入整张图。

Input Funnel 是“运行入口漏斗”：它根据 `io/inputs.json` 只放行声明过的字段。比如 schema 只允许 `scene_id` 和 `text`，调用方传了 `debug_token`，漏斗应该丢弃或拒绝它；如果 schema 要求 `count` 是 integer，而 CLI 传入 `"3"`，漏斗可以在安全范围内转成 `3`。旧 `IOManager.load_inputs()` 已经有 runtime/file 输入概念，见 `packages/graph-agent/src/graph_agent/io/manager.py:65` 到 `packages/graph-agent/src/graph_agent/io/manager.py:106`，但 V2.1 主线没有调用它。

MVP0 WILL 复用编译期验证过的根级 schema。`GraphManifest` 默认 input ref 是 `io/inputs.json`，见 `packages/graph-agent/src/graph_agent/core/manifest.py:53`；compiler 会在 `packages/graph-agent/src/graph_agent/core/loader.py:153` 和 `packages/graph-agent/src/graph_agent/core/loader.py:874` 到 `packages/graph-agent/src/graph_agent/core/loader.py:900` 校验 schema 文件合法。runtime 不应重新猜 schema，而应消费编译产物里的规范化 schema。

Funnel 的结果 SHOULD 成为只读 initial inputs。也就是说，后续 LOGIC 或 SKILL 如果想产生新字段，应写入自己的 phase output，而不是改写原始 input。这样批量测试和重跑才可解释：同一个 canonical input 进入图，无论跑多少次，输入区都不会被业务 action 意外修改。

### 3. 细粒度 Phase-Level IO 契约与防覆盖机制 (A2/A3 补全)

MVP0 SHOULD 让每个 phase 只看到自己声明需要的输入，只能写入自己的输出区域。当前 LOGIC node 复制全量 `state.data` 给 `Context`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:127` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:136`。SUBGRAPH node 也把父图全量 data 传入子图，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:155` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:164`。这就是 A2/A3 的核心问题。

Phase-Level IO Contract 是“每个节点自己的读写授权清单”。例子：`summarize` 只声明读取 `clean_text`，那它不应该能看到用户上传的全部原始 payload；它输出的 `summary` 应放进 `phase_outputs["summarize"]["summary"]`，而不是直接覆盖顶层 `data["summary"]` 或父图已有 key。

MVP0 WILL 在 phase wrapper 执行前构建 `phase_input`，执行后把结果封装到 phase 命名空间。对于 SUBGRAPH，子图返回值也不能直接 diff 父图全量 data 后合回顶层。当前 `_dict_delta(before_data, result_data)` 取子图变化，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:165` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:172`；MVP0 SHOULD 改成显式 output mapping。

这会改变 LOGIC action 作者的心智模型。当前 action 可以通过 `Context(data, ...)` 看到全局黑板，构造位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:130`；MVP0 SHOULD 让 Context 包装的是 `phase_input` 加受控 writer，而不是全量 `state.data`。如果 action 需要某字段，必须在 phase `io.inputs` 声明；如果没有声明却读取，应该得到清晰的 contract error。

### 4. 彻底隔离 Child Graph 黑板状态 (A6 补全) {#cross-state-blackboard-isolation}

MVP0 MUST 保证 agent-called graph 和父 graph 黑板隔离。当前 subagent child data 是 `{**before_data, **input_data}`，也就是父图全量 data 加上 LLM 显式传入的参数，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:392` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:410`。这会让子任务看到不该看到的父图字段。

隔离规则应该更严格：child graph 的初始 `data` **只等于** explicit tool input 经过 schema funnel 后的结果；父图 data 不隐式继承。child `flow` 可以继承必要控制字段，但必须 deep copy，并写入新的 `subagent_depth`。当前 child flow 直接用 `parent_state.get("flow", {})`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:400` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:405`，MVP0 WILL 修掉这类引用共享。

返回路径也要保持隔离。subagent 作为 tool 调用时，子图结果 SHOULD 作为 tool result 回到父 LLM，而不是自动合并进父 `data`。当前 `_invoke_subagent_once_t23()` 返回 `{"status": "ok", "data": data_delta, "flow": ...}`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:411` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:415`。MVP0 SHOULD 明确这个 `data` 是“给父 LLM 阅读的工具结果”，不是父图黑板 patch。

### 5. 防污染的垃圾回收策略

MVP0 SHOULD 防止可变对象引用从临时 phase input 泄漏回父 state。Python 的 dict/list 是引用类型；如果 phase_input 中包含嵌套 list，子图或 action 修改它，父图可能观察到副作用。MVP0 在构造 `phase_input`、child `data`、child `flow` 时 SHOULD 使用 `copy.deepcopy` 或等价结构化复制。

这不是性能洁癖，而是安全边界。当前 LOGIC node 会复制顶层 dict：`before = dict(state.get("data", {}))` 和 `data = dict(before)`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:127` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:130`；这只是浅拷贝，不能阻止嵌套对象污染。

MVP0 SHOULD 为大对象复制设置边界。对于普通 JSON-like dict/list，深拷贝可接受；对于文件句柄、模型客户端、DataFrame 这类非 JSON 对象，Input Funnel 和 Phase Wrapper 应直接拒绝或转成引用句柄。否则 Checkpointing 和 Trace JSON 化都会失控。

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

MVP0 SHOULD 在 `BlackboardState.data` 的 Annotated reducer 中替换旧函数。现有导出 `__all__ = ["BlackboardState", "shallow_dict_merge"]` 在 `packages/graph-agent/src/graph_agent/runtime/state.py:44`，迁移时可以短期保留旧名但标记 deprecated。

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

MVP0 SHOULD 在 `_run_v21_skill_dict()` 调用 `graph.invoke()` 前使用该函数，替换当前的 `"data": dict(inputs)`。接入点就是 `packages/graph-agent/src/graph_agent/core/runner.py:471` 到 `packages/graph-agent/src/graph_agent/core/runner.py:477`。

错误模型 SHOULD 与 compiler 的结构化 issue 对齐。缺少 required input 是用户输入错误，应该给 `F-v21-input-missing`；类型不可转换是输入格式错误，应该给 `F-v21-input-invalid`；未知字段如果被配置为 strict，则给 `F-v21-input-unknown`，如果配置为 permissive，则记录 warning 并丢弃。

## Data Model / State

### 1. BlackBoard 状态结构的隔离深化
随着黑板完全向 A2 描述的那样进行分阶段治理，原有的单一 `data` 聚合形式在设计思维中演变为多个分段概念区。尽管出于对旧模块兼容性考量我们依然把它们承载在原 `BlackboardState` 之中（代码位于 `packages/graph-agent/src/graph_agent/runtime/state.py:35` 附近）：

- **`inputs` 专有区**：容纳从 `Input Funnel` 处理后形成的数据集，它被设定为全生命周期只读，作为大局依赖源，绝对禁止任何修改。
- **`phase_outputs` 字典树**：形如 `phase_outputs = {"analyze": {...}, "search": {...}}`，成为节点专属的、被隔离保护的存储地带。
- 只有通过专门包装的节点装载器函数，它们才会被按需挑选组合，形成一个局部的、轻量的 `phase_input` 发送至目标工作空间，并在完工后反向提取写回树中。这就完成了从逻辑到物理层面的彻底切割。

MVP0 可以选择在内部继续把这些挂在 `data` 下，也可以扩展 `BlackboardState` 字段；关键是语义必须固定。当前 `data` 是一整块共享 dict，见 `packages/graph-agent/src/graph_agent/runtime/state.py:38`，这不是最终契约。

推荐的迁移路线是先兼容旧 `data`，同时新增规范化子结构：`data["inputs"]`、`data["phase_outputs"]` 和 `data["scratch"]`。其中 `scratch` 只能服务单个 phase 临时计算，不进入最终 context。等下游代码都切到 mapper，再考虑把它们提升为 `BlackboardState` 的顶层字段。

### 2. 状态映射器模型 (StateMapper)
由于状态不再是扁平的铺开，可能需要一个新的 `StateMapper` 工具类协助负责。它依据静态期间生成的 `io.inputs` 要求，从 `inputs` 或 `phase_outputs` 的分段中提取需要的数据：
```python
class StateMapper:
    def build_phase_input(self, data: dict, required_schema: dict) -> dict: ...
    def wrap_phase_output(self, phase_id: str, output: dict) -> dict: ...
```

`StateMapper` SHOULD 消费 skill-compilation 产出的 phase-level IO schema。编译侧将新增 `PhaseIOSchema`，见 [skill-compilation 的 Node AST 数据结构边界扩展](../skill-compilation/mvp0-alignment.md#2-node-ast-数据结构边界扩展)。

Mapper 还 SHOULD 负责冲突解释。比如两个上游都产出 `text`，而当前 phase 只声明输入 `text`，它应该提示用户在 `io.inputs` 里指定来源，或在上游输出改名。这个错误属于数据流 contract，不应该等 reducer 在运行时用 `[F-v21-state-conflict]` 才发现。

## Cross-feature Interaction

本机制的完善是跨越整个生命周期的枢纽，涉及多个其他模块的密切配合：

- **与 Compilation 特性的深度耦合**:
  不论是 `Input Funnel` 还是 `Phase-Level IO` 拦截，这里用于驱动过滤和裁切漏斗逻辑的所有 JSONSchema 数据来源依据，全部是 [skill-compilation AST 解析时注入并在图检验中查阅完毕的 io_schema 产物](../skill-compilation/mvp0-alignment.md#后端功能)。静态编译阶段提供法则，此模块提供基于法则的动态执法。
  
- **向 Execution-Runtime 执行装载提供支撑**:
  子图与子代理的启动，必然将遭受这层 A6 级黑板屏蔽切断继承的洗礼。这在 [execution-runtime 的运行分发与隔离调用机制](../execution-runtime/mvp0-alignment.md#cross-feature-interaction) 中会直接体现。

### 6. Phase Wrapper 的上下文准备过程
在落实 A2 时，我们在 `packages/graph-agent/src/graph_agent/core/phase_node.py` 中引入了 `phase_input` 的装载机制。它的执行细则如下：
1. **阶段提取**: 从 `BlackboardState.inputs` 中提取当前节点在 `io.inputs` 中声明关联的全局字段。
2. **前置合并**: 从 `BlackboardState.phase_outputs` 遍历当前节点的 `depends_on` 列表，将合法的输出组装进来。如果出现命名冲突（比如上游的两个节点都输出了 `text` 且当前节点需要 `text`），触发 `[F-v21-io-conflict]` 阻断。
3. **严格过滤**: 确保任何未声明在这个阶段的输入列表里的属性，都绝对不会被传入给大模型。

当前还没有 `phase_node.py` 这个 wrapper；现有逻辑分散在 `graph_assembler.py` 的 LOGIC/SUBGRAPH/SKILL builder，入口分别在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:116`、`packages/graph-agent/src/graph_agent/core/graph_assembler.py:141`、`packages/graph-agent/src/graph_agent/core/graph_assembler.py:177`。MVP0 SHOULD 抽出统一 wrapper，减少三类节点各自绕过 sandbox 的风险。

### 7. 对遗留字典 `shallow_dict_merge` 的退役计划
由于 P0-3 所指出的 `packages/graph-agent/src/graph_agent/runtime/state.py:13` 中的函数严重阻碍了单线状态推进，在替换为 `SmartReducer` 之后，我们需要全量清理旧有函数的引用。
- 在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py` 里面的 `Annotated[dict, shallow_dict_merge]` 会被完全替换为 `Annotated[dict, smart_dict_reducer]`。
- 为了兼顾可能依赖旧版行为的少部分 V2.0 遗留测例，我们在一段时间内可能保留原函数名但挂上 `@deprecated` 标志。

### 8. 输入过滤机制的数据纠错与补全 (Coercion)
关于 A1 中描述的 `Input Funnel`，它不仅承担丢弃无效数据的责任，更在某些安全范围内负责补全：
- **默认值**: 如果 `io/inputs.json` 中某属性标明了 `default` 且外部未传，Funnel 会补上它。
- **强制转换**: 对于 Pydantic 支持的安全类型转换（例如 `str` 转 `bool`），引擎会做最佳努力处理，使得 CLI 命令行或者外部 HTTP 触发时，容错率得到提升。

### 9. 状态重置与清理策略
在很多情况下，`run_skill` 可能需要被反复触发（比如在 Playground 里的批量测试）。如果核心 `data` 没有被完全重置，很容易出现数据串联导致的脏读脏写。
在 MVP0 中：
- 我们规定每次启动时，不仅仅是清空 `BlackboardState`，更是要在内部主动释放大体积对象引用。
- 在 `packages/graph-agent/src/graph_agent/runtime/state.py` 内部会增加 `clear_state()` 的支持。

### 10. 长时运行图的状态保存机制 (Checkpointing)
尽管目前的重点是把流程隔离并推断跑通，但是考虑到后续的扩展，这套 Reducer 和黑板机制不能对外部是绝对封闭的：
- 在 `packages/graph-agent/src/graph_agent/core/checkpointer.py` (如果存在) 或 LangGraph 原生的 Checkpointer 的协作下，我们隔离好的 `phase_outputs` 及其字典树，能完美适配 JSON 的序列化。
- 这意味着以后实现断点续传时，可以精准知道哪些 phase outputs 已存在，哪些需要重跑。

### 11. 与日志及 Trace 观测体系的数据同步
这里的数据沙箱隔离机制并非仅仅服务于业务的健康运转。在 `tracing-and-observability` 特性的实现中，我们需要向 Studio 返回阶段级别的完整输入输出镜像。
- 这些日志所依赖的核心数据抓取点，就是建立在经过 `Input Funnel` 过滤以及 `Phase Wrapper` 切分的纯粹结构体之上的。
- 如果没有这一套无冗余的数据合约作保障，Trace 记录中会充斥着全集数据。观测侧规划见 [tracing-and-observability mvp0 alignment](../tracing-and-observability/mvp0-alignment.md#后端功能)。

这个双向关系也会影响 Studio 的 Edge Inspection。Edge 面板需要展示“上游 phase 实际传给下游 phase 的字段”，而不是整张黑板。只有 StateMapper 能稳定产出 phase-to-phase slice，Trace 才能把它记录下来，Studio 才能在边上展示精确上下文。
