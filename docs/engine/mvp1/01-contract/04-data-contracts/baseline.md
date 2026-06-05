---
module: 01-contract/04-data-contracts
doc: baseline
status: drafted（B 成段:对当前 packages/graph-agent 逐符号 grep 核 2026-06-05;形状散在 core/+runtime/;⚠️ BlackboardState 在 runtime/state.py、ErrorPayload 无 line 轴）
binds_alignment: ./mvp1-alignment.md
binds_code: packages/graph-agent/src/graph_agent/core/state.py:BusinessData · core/state.py:FrameworkState · core/state.py:WorkflowState · runtime/state.py:BlackboardState · core/result.py:RunResult · core/exceptions.py:ErrorPayload · core/error_registry.py:ERROR_REGISTRY · core/validator_contract.py:VALIDATOR_SIGNATURE · core/types.py:Phase
---

# 04-data-contracts — Baseline(当下代码实现逻辑)

> **Scope**: "我们设计的数据形状"在当前代码里的**现状落点**:state schema / result 类 / 异常树 + ErrorPayload / 错误码注册 / validator 契约 / Phase AST / 公开 `__all__` surface。langgraph 原语(StateGraph state、DeltaChannel reducer、checkpointer)是底座、引用不复述(归 `03-checkpoint`/`08-messages-state`)。
> **现状一句话**:这些形状**物理散在 `core/`(+ `runtime/`)**、非独立 L0 叶——`BusinessData`/`FrameworkState`/`WorkflowState` 在 `core/state.py`,result 类在 `core/result.py`,异常树 + `ErrorPayload` 在 `core/exceptions.py`,错误码注册在 `core/error_registry.py`,而**公开的 `BlackboardState` + blackboard 数据模型在 `runtime/state.py`**(⚠️ 与迁移源"core/state.py 别名"说法漂移)。alignment 目标是抽成零内部依赖的 L0 叶 + 给 `ErrorPayload` 加 `line` 轴 + `data` 通道补 delta reducer。

## UI/UX
N/A。

## 前端逻辑
N/A —— 本模块是 engine 数据契约。

## 后端功能

### 1. state schema(core/state.py + runtime/state.py)
- `packages/graph-agent/src/graph_agent/core/state.py:BusinessData`(:79,Pydantic `BaseModel`):用户业务字段容器;`__setitem__` 拒 `_` 前缀字段(检查 :135,报错信息 :137:"BusinessData 不允许 _ 前缀字段...必须用 update_framework")。
- `core/state.py:FrameworkState`(:156,`BaseModel`):框架元数据,与用户业务字段物理隔离(A1 拆分)。
- `core/state.py:WorkflowState`(:203,`TypedDict`):顶层 graph state;`messages` 通道用 langgraph `DeltaChannel`(:214,reducer `_messages_delta_reducer`、`snapshot_frequency=50`;`DeltaChannel` 导入 :21)。`data` 通道**无 delta reducer**(现状,见差异表)。
- `core/state.py:StateManager`(:217):state 读写/校验 helper(含 `_` 前缀守卫 :227/:265-267)。
- `packages/graph-agent/src/graph_agent/runtime/state.py:BlackboardState`(:88,`TypedDict`):公开的 blackboard state 形状(`__init__.py:49` re-export 进 `__all__`)。同文件 `BlackboardData`(:14,`TypedDict`:`inputs`/`phase_outputs`/`scratch` 三区)+ `normalize_blackboard_data` / `blackboard_data_merge`(归一化 / 合并 helper)。
  > ⚠️ **drift vs 迁移源**:源 12-contracts 称 `BlackboardState` 是 `core/state.py` 的公开别名;实测它是 `runtime/state.py:88` 的独立 `TypedDict`,且源未记 `BlackboardData` 模型 + normalize/merge。blackboard 数据流机制归 `01-graph-exec`,本域只登记形状落点。

### 2. result 类(core/result.py)
- `core/result.py:WorkflowMetrics`(:14)· `PathDiff`(:48)· `PhaseRecord`(:58)· `RunResult`(:68)· `WorkflowResult`(:92,继承 `RunResult`)。`RunResult` 是 run/predict 统一返回模型(字段对照见 `01-physical-layout` baseline §5;被 studio 消费,接口契约归 `03-api-contract`)。

### 3. 异常树 + ErrorPayload(core/exceptions.py)
- 异常树(基类 `core/exceptions.py:GraphAgentError`:82):
  - `GraphCompileError`(:103)→ `LoaderError`(:126)→ `SkillParseError`(:135)
  - `GraphExecutionError`(:107)→ `GraphAgentFatalError`(:119)
  - `ModelProviderError`(:111)· `ResourceNotFoundError`(:115)
- `core/exceptions.py:ErrorPayload`(:21,`BaseModel`):9 字段 `code` / `level` / `stage` / `message` / `doc_link` / `skill_id` / `phase_id` / `field_path` / `source_path`。**无 `line` 轴**(现状;alignment Task3 要加)。helper `make_error_payload`(被 `runtime/state.py` 等 import)。

### 4. 错误码注册(core/error_registry.py)
- `core/error_registry.py:ErrorCodeMetadata`(:8,`NamedTuple`,含 `level`)· `ERROR_REGISTRY`(:15,`dict[str, ErrorCodeMetadata]`;93 码全表见 `03-compile-rules §4`)。`ErrorPayload.code` 必须 ∈ `ERROR_REGISTRY`。

### 5. validator 契约(core/validator_contract.py)
- `core/validator_contract.py:VALIDATOR_SIGNATURE`(:9,`"def validate(output: dict, state_slice: dict, **kwargs) -> None | dict"`)· `VALIDATOR_ERROR_CODES`(:11,`tuple[str, ...]`;agent/subgraph/logic γ0 占位)。运行时 validator 加载属 execution 域(`graph-exec`)。

### 6. Phase AST(core/types.py)
- `core/types.py:Phase`(:19;`__all__=["Phase"]`:80):编译产物 phase 节点 AST 形状。

### 7. 公开 `__all__` surface(__init__.py)
- `__init__.py:__all__`(:51)现含 19 个符号:`run_skill` / `predict_skill` / `RunResult` / `PathDiff` / `PhaseRecord` / `compile_skill` / `CompileResult` / `assemble_graph` / `CompiledSkill` / `CompiledStateGraph` / `BlackboardState` / `LocalWorkspaceResolver` / `SkillManifest` / `serialize_skill` / `GraphAgentError` / `GraphCompileError` / `GraphExecutionError` / `ModelProviderError` / `ResourceNotFoundError`。
  > ⚠️ **drift vs 迁移源**:源只列了 6 + 5 个;实测 surface 已增 8 个(compile/assemble/serialize/resolver/manifest 等)。surface 稳定性契约归 `07-runtime`(`tests/test_public_api_contract.py`)。

## API
- 公开数据形状 surface:`__init__.py:__all__`(:51)。
- result 消费契约:`03-api-contract`(studio 读 `RunResult`)。

## Data Model / State
- 我们的形状:`BusinessData`/`FrameworkState`/`WorkflowState`(core/state.py)+ `BlackboardState`/`BlackboardData`(runtime/state.py)+ result 类(core/result.py)+ `ErrorPayload`(core/exceptions.py)。
- langgraph 底座(机制,不复述):`StateGraph` state、`DeltaChannel` reducer、checkpointer —— 归 `03-checkpoint`/`08-messages-state`。

## 当前边界(这个模块现在不是什么)
- **现状非 L0 叶**:形状散在 `core/`(+ `runtime/state.py`),与上层(cognitive/middleware/tools/runtime)循环纠缠;alignment 目标才是抽成零内部依赖的 leaf。
- blackboard 数据流(normalize/merge/slice)机制归 `01-graph-exec`,本域只登记形状落点。
- langgraph 原语是底座,不是我们的契约(引用不复述)。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标(alignment) |
|---|---|---|
| 物理布局 | 形状散在 `core/` + `runtime/state.py`,循环纠缠 | 抽成 L0 叶 `data-contracts`,**零内部依赖**(去环;kiro 重排) |
| `ErrorPayload` 定位轴 | 9 字段,**无 `line`** | 加 `line` 轴(Task3)+ emit 处填全 phase/field/source/level |
| `data` 通道 reducer | `WorkflowState.data` **无 delta reducer**(仅 messages 有 DeltaChannel) | `data` 通道补 delta reducer(归 `03-checkpoint`) |
| 错误码 domain | 缺 `golden`/`iterate` domain | 加 `golden`/`iterate` 码(Task1) |
| `BlackboardState` 落点 | `runtime/state.py:88`(独立 TypedDict) | 形状沿用;物理随 L0 抽出收口 |

> **验"是否按 mvp1 改了"**:① `data-contracts` 成独立 leaf、import 图零内部模块(acyclicity guard);② `ErrorPayload` 有 `line` 字段且 emit 填全;③ `WorkflowState.data` 有 delta reducer;④ `ERROR_REGISTRY` 含 golden/iterate 码。

## 读代码主路径提示
state: `core/state.py`(BusinessData/FrameworkState/WorkflowState/StateManager)+ `runtime/state.py`(BlackboardState/BlackboardData)。result: `core/result.py`。错误: `core/exceptions.py`(ErrorPayload + 树)→ `core/error_registry.py`(ERROR_REGISTRY)。validator: `core/validator_contract.py`。Phase AST: `core/types.py`。surface: `__init__.py:__all__`。

## 交叉引用(链接, 不复制)
[mvp1-alignment](./mvp1-alignment.md)(目标)· `02-mechanism/04-run-outer/03-checkpoint`(state 存储 / data delta reducer)· `05-run-inner/08-messages-state`(messages 通道 DeltaChannel)· `04-run-outer/01-graph-exec`(blackboard 数据流)· `03-api-contract`(RunResult 消费契约)· `03-compile-rules`(ERROR_REGISTRY 93 码)· `07-runtime`(public `__all__` surface 契约)
