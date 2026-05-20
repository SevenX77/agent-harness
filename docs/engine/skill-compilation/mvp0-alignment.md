# skill-compilation (engine) — MVP0 Alignment (下一步对齐逻辑)

> **Status**: Filled by a2 (Gemini), 2026-05-20
> **Scope**: V2.1 技能目录解析、AST 构建、图拓扑校验、静态 IO 数据流校验 (audit A7/A8)、编译缓存策略
> **配套**: 见 [INDEX.md](../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

N/A — 此模块为纯 backend Python library, 无 UI / 无前端调用面。

这里的 "backend Python library" 指 `packages/graph-agent` 里的 Python 引擎代码，并不是指代 Studio 的 FastAPI 后端服务，也不是 React 前端应用。用户永远不会直接在操作界面上看到 "compile" 这一生命周期模块的状态流转。它只通过调用方拿到的异常（例如拓扑环报错）、返回的静态对象结构或后续 runtime 行为体现结果。

然而，编译器的校验结果是整个系统最前端的安全屏障，它负责为前端界面提供最核心的、结构化的校验错误信息。例如，当 PM 在画布（Canvas）界面连错了节点的数据依赖，这里发出的 `[F-v21-io-conflict]` 异常将被 Studio 后端捕捉，最后呈现在画布边缘的红色警告框中。如果没有这层完善的 backend 支持，前端将无法定位和标红具体的错误连线。因此，UI 界面的健壮性极度依赖此后端的严谨输出。如果编译过程只产生字符串报错，前端界面就无法做到精确的连线高亮，可视化编辑的 MVP0 目标便无从谈起。

## 前端逻辑

N/A — 此模块为纯 backend Python library, 无 UI / 无前端调用面。

React 前端（如多文件编辑器 `SplitEditor` 或 `GraphCanvas` 拓扑图）并不直接参与 `GRAPH.md`、`io/*.json` 或各个 Phase Markdown 文件的字符串解析与内存 AST 构建。前端只负责维护内存结构，并通过 Tauri IPC 或者 WebSocket 获取后端的解析结果。前端逻辑虽然需要深度消费后端的 `CompileResult` 实体，或者是针对 `GraphAgentError` 异常进行 UI 状态更新，但是它对这些数据的生产过程完全透明。因此，本编译模块内部没有任何涉及到 React component 的逻辑变迁。所有的工作均在 Python 的抽象语法树和校验器中完成。

## 后端功能

### 1. 缓存元数据补全与深层对象重建 (P1-1 修复)

当前 cache rehydrate 在恢复快照时丢失了至关重要的动态配置结构 `subagents_by_phase` 和 `phase_tokens`，详见 [baseline.md#后端功能](./baseline.md#后端功能)。这会导致缓存命中时，引擎丢掉了原本解析出的 Subagent 信息，产生致命的不一致行为。这是由于之前的序列化逻辑没有完全展开 Pydantic 的复杂类型，导致还原时只留下了壳子。

实测发生路径在 `packages/graph-agent/src/graph_agent/core/cache.py:84` 的 `_dehydrate_compiled_skill` 以及 `packages/graph-agent/src/graph_agent/core/cache.py:102` 的 `_rehydrate_compiled_skill`。

MVP0 改造必须确保 `cache_key` 的回放过程 100% 还原内存结构。
在序列化（dehydrate）侧，我们需要在返回的 JSON dict 中额外挂载提取自 `CompiledSkill` 实例的字典树。这里的复杂之处在于 `CompiledSubagent` 并不是一个普通的 Pydantic Model，它包含了动态构建的 `input_model` 类定义。因此我们需要提取元信息以备后续重建：

- 提取 `compiled.subagents_by_phase`，将其包含的 `root` 路径、`expected_schema` 结构化并存入 `snapshot["subagents_by_phase"]`。
- 提取 `compiled.phase_tokens` 放入 `snapshot["phase_tokens"]` 以保留所有的成本消耗标识。

在反序列化（rehydrate）侧，也就是 `packages/graph-agent/src/graph_agent/core/cache.py:102` 的恢复逻辑中，我们需要把 JSON 再次转化为 `CompiledSubagent` 实例。这不仅仅是单纯的字典赋值，更要借助动态类生成重新构造出 `input_model` (Pydantic 类)：

```python
# 拟定的重建逻辑示例，该部分将被插入 _rehydrate_compiled_skill 函数内
subagents_by_phase = {}
for phase, subs in snapshot.get("subagents_by_phase", {}).items():
    restored_subs = []
    for sub in subs:
        # 必须在这里调用 build_subagent_input_model 重新生成类型
        from graph_agent.core.subagents import build_subagent_input_model
        input_model = build_subagent_input_model(sub["name"], sub["expected_schema"])
        restored_subs.append(
            CompiledSubagent(
                parent_phase_id=sub["parent_phase_id"],
                name=sub["name"],
                path=sub["path"],
                description=sub["description"],
                root=Path(sub["root"]),
                input_schema=sub["input_schema"],
                input_model=input_model,
                expected_schema=sub["expected_schema"],
            )
        )
    subagents_by_phase[phase] = restored_subs
```
最后把这些组装回 `CompiledSkill` 对象，确保无论是否命中 Cache，产生的运行时环境以及可注入的 Tool 集合完全一致。

### 2. 缓存写失败平滑降级机制 (P2-2 修复)

目前，当编译器尝试在如 Docker 容器、无写入权限的只读沙箱等苛刻环境中写出编译快照时，它会因为遇到权限问题而抛出致命的 `OSError` 或 `PermissionError`。代码位于 `packages/graph-agent/src/graph_agent/core/cache.py:45` 的 `save_to_cache` 函数。这直接中断了用户的编译链路，甚至导致 Studio 侧看到未处理的 HTTP 500 错误，是典型的过激保护行为。这种因为缓存盘不可用而导致应用无法运行的情况是极不合理的。

MVP0 改造计划将这部分 IO 操作变为非阻塞性警告，引入平滑的降级（Graceful Degradation）机制：
- 我们将在 `cache_dir.mkdir(parents=True, exist_ok=True)` 以及接下来的 `cache_file.write_text(...)` 代码外部包裹一个细粒度的 `try ... except (OSError, IOError, PermissionError) as e` 异常捕获块。
- 一旦捕获到写入问题，将通过 Python 原生的 `logging` 设施进行输出，提示用户当前的系统状态：
  `logger.warning("Failed to write compile cache to %s: %s. Falling back to No-Cache in-memory compilation.", cache_dir, e)`
- 异常捕获后，函数直接 `return None` 进行退出。如此，只要内存编译环节本身成功，运行时就能拿到合法的 `CompiledSkill` 顺利向下推演，而绝对不会因为辅助性能提升的缓存模块的原因而罢工。

### 3. 编译期 Schema 解析强制增强 (A7 补全)

V2.1 引擎目前对 Node 内部自己的状态规约过于宽松。目前 `SkillNodeAST` 仅验证 `system_prompt` 和 `exit_contract` 等内容，见 `packages/graph-agent/src/graph_agent/core/manifest.py:83-90`。如果 Phase 不声明它的边界，后续的数据传递将如一盘散沙，导致运行时异常频发。这就好比在一台复杂的机器中各个零件互相传递着没有说明书的包裹。

MVP0 要求每个逻辑节点或模型节点，必须为系统提供其消费与产出的 JSONSchema 契约。这是 PM 看清楚每一步 “输入是什么、输出是什么” 的基石，更是可视化编排的生命线：
- 在 Markdown 解析组装阶段，也就是 `packages/graph-agent/src/graph_agent/core/loader.py:66` 附近的解析流水线中，遇到 `mode: skill` 和 `mode: logic` 时，我们将强制检查其 YAML Frontmatter 是否拥有合法的 `io` key。
- 如果引擎发现缺失，它将绝不放行。而是收集为一条编译期结构化错误并终止装配流程：
  `CompileIssue(severity="ERROR", code="F-v21-io-missing", message="Phase node 'analyze' is missing 'io' dict in its frontmatter.")`
- 如果存在，将其按照 Schema 规范进行装载，灌入新增的 `io` 字段内部（详见 Data Model 部分的扩展），供后续的静态数据流校验模块深度查询。这个要求将强制开发者在编写阶段明确声明所需的输入和将要输出的数据，从根本上提升了模块的可靠性和可测性。

### 4. 静态数据流拓扑连通性校验 (A8 补全)

除了现有的图循环检测（位于 `packages/graph-agent/src/graph_agent/core/compiler.py:40` 附近），我们需要一种强大的静态分析机制，能在图真正执行前（甚至都没发给 LangGraph 进行装配），就提前发现前后环节数据口径不匹配的问题。这能极大缩短调试周期，是“把事情做对”理念的直接体现。

MVP0 改造：
我们将实现图级数据流的连续性校验（Dataflow Continuity Validation）。这个新增验证将对 `GRAPH.md` 定义的图结构进行拓扑排序遍历。针对每一个 `PhaseAST` 节点在其 `io.inputs` 中声明的 `required` 属性：
- 它必须存在于全图启动的全局根节点 Schema (`io/inputs.json`) 的 properties 中。
- 或者，它必须被该节点的上游 `depends_on` 阶段声明的 `io.outputs` 覆盖输出。
如果找不到任何声明源，编译器将抛出带有精确路径和阶段名的 `[F-v21-io-conflict]` 错误。例如：“节点 `summarize` 需要 `clean_text`，但其上游依赖 `extract` 和全局输入中均未提供该字段。”通过静态分析将此类错误阻断在运行之前，极大地提高了整个系统流转的信心。

### 5. 编译期错误信息的规范化结构
在产生任何上述异常（A7 的解析错误，A8 的拓扑连续性错误）时，系统不能再单纯抛出普通的字符串 `ValueError`。它必须发出带有极其精确语义位点的异常实例，例如包含了 `line` 或 `phase_id`。这样不仅是供终端输出，更核心是为了跨端通信。

## API

以下为新增或变更的核心公共 API 及其签名定义。它们是整个 compilation feature 中承担核心防御和解析责任的暴露面，未来将被上游调用方紧密依赖。

### 1. 静态数据流校验入口

作为 `compile_skill` 主干流程中的新加入的验证关卡，我们需要提供一个结构化的分析函数。此签名预期为：

```python
from typing import Any

def _validate_phase_io_dataflow(
    manifest: GraphManifest, 
    nodes: list[PhaseAST],
    global_inputs_schema: dict[str, Any]
) -> list[CompileIssue]:
    """Validate dataflow continuity across all compiled phase nodes.

    This static analyzer traverses the declared graph topology in
    `manifest.phases`. It sequentially checks every node's required
    input fields against the output schemas declared by its ancestors
    or the global initialization inputs. This prevents missing keys
    during runtime execution.

    Args:
        manifest: The parsed GraphManifest describing phase sequence.
        nodes: Parsed PhaseAST items containing `io` schemas.
        global_inputs_schema: Evaluated root `io/inputs.json` schema.

    Returns:
        List of CompileIssue containing dataflow or type mismatch errors.
        For example: missing required upstream output mapping.
    """
    issues = []
    # 内部将执行拓扑排序并逐级累加可用字段的集合
    # 若发现 required field 缺失则 append issue 包含了详细的位置信息
    return issues
```

### 2. 扩充的 CompileResult 返回值契约

虽然 `CompileResult` 定义位于 `packages/graph-agent/src/graph_agent/core/compiler.py:22`，但它需要在返回集合中附加上述分析产生的 IO 层级问题。我们不需要改变其基础签名，但必须丰富其内含的 `issues` 列表承载的错误维度，确保抛给 Studio 对接时包含具体的定位锚点（比如引发冲突的字段名 `field_name` 和阶段源 `source_phase`）。这将协助前端实现更细腻的反馈。

## Data Model / State

### 1. CompiledSkill 缓存序列化 Schema 的深层升级

`packages/graph-agent/src/graph_agent/core/loader.py:66` 处的 `CompiledSkill` 及其附属组件需要配合 P1-1 进行 dehydrate 侧的字典结构变更，以确保反序列化的绝对无损。它的快照表示模型进化如下：

```python
from dataclasses import dataclass
from typing import Any

@dataclass
class DehydratedCompiledSkill:
    """The JSON-serializable representation of a CompiledSkill.
    
    This acts as the canonical data model for saving and loading the
    graph compilation state to and from disk.
    """
    raw: dict[str, Any]
    manifest: dict[str, Any]
    nodes: list[dict[str, Any]]
    
    # 新增字段：完整保留子代理的必要元数据，排除无法序列化的类定义
    # 用于确保运行时缓存命中后能动态重新挂载子执行图
    subagents_by_phase: dict[str, list[dict[str, Any]]] 
    
    # 新增字段：保留 Token 成本消耗等外围计量数据
    phase_tokens: dict[str, dict[str, Any]]             
```

### 2. Node AST 数据结构边界扩展

在 `packages/graph-agent/src/graph_agent/core/manifest.py:83` 中，必须为 `SkillNodeAST` 和 `LogicNodeAST` 引入 `io` 字段。这是所有动态 Schema 解析的基石结构定义，采用了强类型的 Pydantic 模型：

```python
from pydantic import BaseModel, Field
from typing import Any, Literal

class PhaseIOSchema(BaseModel):
    """Declarative JSONSchema wrapper for node boundary definitions.
    
    This enforces that every phase explicitly states what it consumes
    and what it yields, forming the basis of the IO contract.
    """
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)

class SkillNodeAST(_BaseNodeAST):
    """LLM ReAct phase node parsed from ``SKILL.md``."""
    mode: Literal["skill"]
    system_prompt: str = Field(min_length=1)
    exit_contract: str = Field(min_length=1)
    tools: list[str] = Field(default_factory=list)
    subagents: list[SubagentSpec] = Field(default_factory=list)
    
    # A7 要求的强制绑定结构，在 AST 解析阶段如果该字段无法被 
    # Frontmatter 提供，Pydantic 将直接引发 ValidationError
    io: PhaseIOSchema = Field(...) 
```

## Cross-feature Interaction

本特性的执行作为上游防线，直接影响下游的运行时和前端可视化的体验，属于跨模块的强关联枢纽：

### 1. 与 Studio trace-visualization 及 Canvas 的协同
当编译期在 `_validate_phase_io_dataflow` 检查发生失败并抛出结构化的 `CompileIssue` 列表时，Studio 后端会将这批包含着精确错误点位（如哪个 Phase，缺少哪个 Input key）的信息转化为 HTTP 响应发回前端。
前端画布将据此进行预判标红（即在运行期之前就可以在 Canvas 连线上打叉反馈节点结构连线断裂的提示）。具体反馈数据结构和链路的双向引用可见 [tracing-and-observability 后端功能](../tracing-and-observability/mvp0-alignment.md#后端功能)。这正是打通 PM 期待的 "可视化看到错误" 功能的最核心源头。

### 2. 对 State Contract 阶段过滤漏斗的直接支撑
此处静态发现并绑定的 `io` schema 将不会只是一个仅用于校验的占位符。在运行期（Execution-Runtime）中，这些被 AST 带过去的 `PhaseIOSchema` 对象将直接输送给各个阶段的 Phase Node Wrapper。
引擎将在那里将其作为 `phase_input` 的严格装载漏斗依据，详见 [state-and-io-contract 核心防覆盖机制](../state-and-io-contract/mvp0-alignment.md#后端功能)。通过这个深度的互操作，引擎完美闭环了从静态规约设定到动态执行期阻断的完整生命周期。由于它的把关，运行时的逻辑层变得异常纯粹。
