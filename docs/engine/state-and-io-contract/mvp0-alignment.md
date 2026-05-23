# state-and-io-contract (engine) — MVP0 Alignment (V0.3.0 graph_skill)

> **Status**: Rewritten by a1 (Codex) for V0.3.0 graph_skill, 2026-05-23
> **Scope**: BlackboardState 规约、Runtime Input Funnel、Phase-Level IO、StateMapper、child graph 黑板隔离、builtin reference reader 装配期沙盒。
> **配套**: 见 [skill-spec README](../skill-spec/README.md), [skill-compilation alignment](../skill-compilation/mvp0-alignment.md), [execution-runtime alignment](../execution-runtime/mvp0-alignment.md)。

## V0.3.0 改造摘要

本文件保留 A1 Input Funnel、A2/A3 phase-level IO、A6 child 黑板隔离、P0-3 smart reducer、StateMapper 的主方向, 只做 V0.3.0 graph_skill 对齐微调:

| 旧语义 | V0.3.0 新语义 | 决议来源 |
|---|---|---|
| Runtime Input Funnel 读取 `io/inputs.json` | 读取 `GRAPH.md` frontmatter inline `io.inputs` | [Root IO Schema](../skill-spec/02-graph-md-spec.md#根-io-契约-root-io-schema) |
| `io_inputs_ref` / `io_outputs_ref` 可作为 schema 来源 | 编译期 FATAL `[F-v3-graph-io-physical-file-deprecated]` | [Root IO Schema](../skill-spec/02-graph-md-spec.md#根-io-契约-root-io-schema) |
| Phase Wrapper 覆盖 skill / logic / subgraph 三类 | 覆盖 agent / logic / subgraph / builtin reference reader subagent 四类调用边界 | [Physical Layout](../skill-spec/01-physical-layout.md#物理结构拓扑-directory-tree), [Builtin Modules](../skill-spec/09-builtin-modules-spec.md#builtin-reference-reader-subagent-签名) |
| child graph 只做内存层隔离 | 通过 SkillResolverProtocol 解析 target skill 后, 再按目标 `GRAPH.md io.inputs` 做合约漏斗 | [SkillResolverProtocol](../skill-spec/10-skill-resolver-protocol-spec.md#protocol-interface-定义) |
| reference reader 未定义黑板归属 | 装配期临时 child blackboard, 独立沙盒, 失败 WARN fallback | [Reference 三机制](../skill-spec/08-resource-mechanisms-spec.md#reference-三机制生命周期) |

## UI/UX

N/A — 此模块为纯 backend Python library, 无 UI / 无前端调用面。

本模块定义 engine 内存里的黑板和 IO 边界。Studio 最终看到的输入输出、Trace 和错误是否干净, 取决于这里的漏斗、切片和沙盒是否稳定。

## 前端逻辑

N/A — 此模块为纯 backend Python library, 无 React 逻辑。

前端只消费运行结果和 trace event。StateMapper 需要产出足够精确的 `phase_input` / `phase_output` 镜像, 让 Studio Edge Inspection 展示“这条边实际传了哪些字段”, 而不是整张黑板。

## 后端功能

### 1. 升级 Reducer 智能合并语义 (P0-3)

MVP0 SHOULD 用 `smart_dict_reducer` 替换过度保守的 `shallow_dict_merge`。同一 super-step 内并行写同一 key 仍然 FATAL; 跨 step 顺序覆盖允许采用 `dict.update` 语义。

| 字段 / 输入 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `left` | dict | 否 | `{}` | 当前 blackboard data | `[F-v3-runtime-state-mapping-failed]` | reducer 旧状态 |
| `right` | dict | 否 | `{}` | phase 返回 state delta | `[F-v3-runtime-state-mapping-failed]` | reducer 新写入 |
| `super_step_id` | string/int | 并行冲突判断时必填 | runtime context | 同一 super-step 同 key 写入为冲突 | `[F-v3-runtime-state-mapping-failed]` | 区分并发冲突与顺序覆盖 |
| `source_phase_id` | string | 建议 | 无 | trace payload 中必须可定位 | `[F-v3-runtime-state-mapping-failed]` | Studio 标红来源节点 |

Reducer 只是最后一道防线。正常情况下, 编译期 A8 数据流校验和运行期 StateMapper 已经避免不明确的写入来源。

### 2. Runtime Input Funnel 迁移到 inline 根 IO (A1, C7)

MVP0 MUST 在 `run_skill(inputs)` 入口先按 `GRAPH.md` inline `io.inputs` 过滤和校验输入。V0.3.0 不再读取 `io/inputs.json`。

| 字段 / 来源 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `GRAPH.md io.inputs` | JSON Schema object | 是 | 无 | 顶层 `type: object`; Draft 2020-12 合法 | `[F-v3-graph-io-not-object]` / `[F-v3-graph-io-schema-invalid]` | Runtime Input Funnel 唯一 schema 来源 |
| raw runtime inputs | dict | 是 | 无 | 必须满足 `io.inputs.required` 与 properties 类型 | `[F-v3-runtime-state-mapping-failed]` | 外部输入原始值 |
| canonical inputs | dict | 是 | 无 | 只保留 schema 声明字段; 安全默认值 / coercion 可在白名单内执行 | `[F-v3-runtime-state-mapping-failed]` | 写入 blackboard inputs 专区 |
| `io_inputs_ref` / `io_outputs_ref` | deprecated field | 禁止 | — | 编译期发现即 FATAL | `[F-v3-graph-io-physical-file-deprecated]` | 防止旧物理 IO 引用继续影响运行 |
| `<root>/io/inputs.json` / `outputs.json` | deprecated file | 禁止 | — | 编译期发现即 FATAL | `[F-v3-graph-io-physical-file-deprecated]` | 防止 schema 漂移 |

Input Funnel 的依赖源从物理 JSON 文件迁移到编译产物中的 inline schema。Runtime 不重新猜 schema, 只消费 compilation 已校验过的 `GRAPH.md io.inputs`。规范终点见 [Root IO Schema](../skill-spec/02-graph-md-spec.md#根-io-契约-root-io-schema)。

### 3. 细粒度 Phase-Level IO 契约与防覆盖机制 (A2/A3)

MVP0 SHOULD 让每个 phase 只看到自己声明的输入, 只能写入自己声明的输出。`io.inputs` 是读取授权, `io.outputs` 是写入授权。

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `phase.io.inputs` | JSON Schema object | 是 | 无 | 顶层 object; required 只能引用 properties | `[F-v3-runtime-state-mapping-failed]` | 构造 `phase_input` |
| `phase.io.outputs` | JSON Schema object | 是 | 无 | 顶层 object; 返回字段必须是 properties 子集 | `[F-v3-runtime-state-mapping-failed]` | 包装 `phase_output` |
| `phase_input` | dict | 是 | 无 | 从 root inputs + 上游 phase outputs 切片, deep copy | `[F-v3-runtime-state-mapping-failed]` | 节点局部工作区 |
| `phase_output` | dict | 是 | 无 | 满足 `phase.io.outputs`; 不得含未声明 key | `[F-v3-runtime-state-mapping-failed]` | 节点回写边界 |
| `phase_outputs[phase_id]` | dict | 是 | `{}` | 按 phase_id 命名空间存储 | `[F-v3-runtime-state-mapping-failed]` | 防止顶层覆盖污染 |

LOGIC action、Agent finish_task、SUBGRAPH child output 都必须经 StateMapper 包装, 不能直接 diff 全局 `data` 后合并。

### 4. 彻底隔离 Child Graph 黑板状态 (A6, NEW-2) {#cross-state-blackboard-isolation}

MVP0 MUST 对 subagent / SUBGRAPH / future call_subgraph 做双向隔离: 内存层切断 + 合约层防穿透。

| 字段 / 步骤 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `target_skill` | string | 是 | 无 | 通过 `SkillResolverProtocol.resolve_skill(skill_id) -> Path` 解析 | `[F-v3-skill-not-registered]` | 找到目标 graph skill |
| child root `io.inputs` | JSON Schema object | 是 | 无 | 来自解析所得 target skill `GRAPH.md` | `[F-v3-graph-io-schema-invalid]` | child input funnel schema |
| explicit tool / phase input | dict | 是 | 无 | 必须先经 child root `io.inputs` 漏斗过滤 | `[F-v3-runtime-state-mapping-failed]` | 子图初始 data |
| `child.data` | dict | 是 | 无 | 只等于 canonical explicit input; 不继承 parent data | `[F-v3-runtime-state-mapping-failed]` | 黑板读隔离 |
| `child.flow` | dict | 是 | `{}` | deep copy parent flow, 写入 `subagent_depth + 1` | `[F-v3-runtime-state-mapping-failed]` | 控制态隔离 |
| child result | dict/tool result | 是 | 无 | 作为 tool result 或 SUBGRAPH phase output 返回, 不自动 patch 父 data | `[F-v3-runtime-state-mapping-failed]` | 黑板写隔离 |

这里的关键是“先 resolve, 再 funnel”。只有 SkillResolverProtocol 解析到目标 skill root 后, runtime 才知道 child `GRAPH.md io.inputs` 的真实 schema。规范终点见 [SkillResolverProtocol Interface](../skill-spec/10-skill-resolver-protocol-spec.md#protocol-interface-定义)。

### 5. 防污染的垃圾回收策略

MVP0 SHOULD 防止可变对象引用从临时 phase input 泄漏回父 state。构造 `phase_input`、`child.data`、`child.flow`、reference reader 临时 blackboard 时, 都应 deep copy JSON-like 对象。

| 对象 | 复制策略 | 非 JSON-like 对象处理 | 业务作用 |
|---|---|---|---|
| `phase_input` | deep copy | 拒绝或转引用句柄 | 防止 action 修改嵌套对象污染父 state |
| `phase_output` | schema validation 后 copy | 拒绝不可序列化对象 | 保证 trace / checkpoint 可 JSON 化 |
| `child.data` | funnel 后 deep copy | 拒绝隐式父对象引用 | 子图读隔离 |
| `child.flow` | deep copy | 只允许控制字段 | 子图控制态隔离 |
| reference reader blackboard | fresh object | 不继承父 graph data | 装配期沙盒 |

### 6. Phase Wrapper 四类调用拦截入口 (C8)

MVP0 SHOULD 抽出统一 Phase Wrapper, 覆盖 V0.3.0 四类调用边界: Agent、LOGIC、SUBGRAPH、builtin reference reader subagent。

| Wrapper 类型 | 输入来源 | 输出去向 | 必填 schema | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|
| Agent phase wrapper | `phase.io.inputs` 切片 | finish_task output -> `phase_outputs[phase_id]` | Agent `io.inputs` / `io.outputs` | `[F-v3-runtime-state-mapping-failed]` | LLM 节点沙盒 |
| LOGIC phase wrapper | `phase.io.inputs` 切片 | action dict -> `phase_outputs[phase_id]` | LOGIC `io.inputs` / `io.outputs` | `[F-v3-runtime-state-mapping-failed]` / `[F-v3-logic-output-field-undeclared]` | 确定性 action 沙盒 |
| SUBGRAPH phase wrapper | parent phase input -> child graph input funnel | child graph output -> parent phase output | SUBGRAPH IO + child GRAPH IO | `[F-v3-subgraph-io-mismatch]` / `[F-v3-runtime-state-mapping-failed]` | 子图调用沙盒 |
| Builtin reference reader wrapper | `references[]` registry | markdown report -> cognitive slot | reader input/output JSON contract | `[F-v3-reference-reader-failed]` WARN | 装配期资料预读沙盒 |

前三类来自 graph physical phases; reference reader 是装配期 builtin subagent, 不在 `phases/` 目录中, 但同样必须经过 wrapper 建立临时 blackboard 和错误归一。物理节点标准见 [Physical Layout](../skill-spec/01-physical-layout.md#物理结构拓扑-directory-tree), builtin 签名见 [Builtin Modules](../skill-spec/09-builtin-modules-spec.md#builtin-reference-reader-subagent-签名)。

### 7. Builtin Reference Reader Subagent 黑板隔离 (NEW-1)

MVP0 MUST 让 builtin reference reader subagent 运行在装配期独立沙盒中。它不读取父 graph runtime blackboard, 只接收 Agent phase 的 `references` registry 和必要 trace metadata。

| 字段 / 对象 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `reader.data.references` | list[ReferenceSpec] | 是 | `[]` | 每项 id/path/summary 已编译期校验 | `[F-v3-resource-reference-invalid]` | reader 唯一业务输入 |
| `reader.data.skill_id` | string | 是 | 无 | 当前 skill id | `[F-v3-reference-reader-input-invalid]` | trace 定位 |
| `reader.data.phase_id` | string | 是 | 无 | 当前 Agent phase id | `[F-v3-reference-reader-input-invalid]` | trace 定位 |
| `reader.flow` | dict | 否 | `{timeout_s: 60}` | 不继承父 runtime flow | `[F-v3-reference-reader-failed]` WARN | 装配期控制 |
| `reader.messages` | list | 是 | `[]` | 从空消息开始 | — | 防止 prompt history 污染 |
| reader output | markdown JSON payload | 是 | fallback excerpt | 输出非法则 WARN fallback | `[F-v3-reference-reader-failed]` | 注入 knowledge_base |

失败边界:

1. reference path 不合法是编译期 FATAL, 不进入 reader。
2. reader 远端调用失败、超时、输出非法是装配期 WARN `[F-v3-reference-reader-failed]`。
3. WARN 后 runtime 截取 reference 原文前 3000 token 作为 fallback, 填入 cognitive template。

Reference 三机制见 [Resource Mechanisms](../skill-spec/08-resource-mechanisms-spec.md#reference-三机制生命周期), reader 签名见 [Builtin Modules](../skill-spec/09-builtin-modules-spec.md#builtin-reference-reader-subagent-签名)。

## API

### 1. SmartReducer 接口

```python
def smart_dict_reducer(
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
    *,
    merge_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ...
```

| 参数 | 类型 | 必填 | 默认值 | 校验规则 | 错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `left` | dict | 否 | `{}` | 当前 state | `[F-v3-runtime-state-mapping-failed]` | 旧值 |
| `right` | dict | 否 | `{}` | phase delta | `[F-v3-runtime-state-mapping-failed]` | 新值 |
| `merge_context` | dict | 否 | `{}` | 建议含 super_step/source_phase | `[F-v3-runtime-state-mapping-failed]` | 冲突定位 |

### 2. Input Funnel 过滤签名

```python
def filter_runtime_inputs(
    raw_inputs: dict[str, Any],
    schema: dict[str, Any],
    *,
    strict_unknown: bool = True,
) -> dict[str, Any]:
    ...
```

| 参数 / 返回 | 类型 | 必填 | 默认值 | 校验规则 | 错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `raw_inputs` | dict | 是 | 无 | 外部 run inputs | `[F-v3-runtime-state-mapping-failed]` | 原始输入 |
| `schema` | JSON Schema object | 是 | 无 | 来自 `GRAPH.md io.inputs` | `[F-v3-graph-io-schema-invalid]` | 漏斗规则 |
| `strict_unknown` | boolean | 否 | `True` | unknown field FATAL 或 WARN drop | `[F-v3-runtime-state-mapping-failed]` | 严格模式 |
| return | dict | 是 | 无 | 满足 schema 的 canonical inputs | `[F-v3-runtime-state-mapping-failed]` | 初始 blackboard inputs |

### 3. StateMapper 模型

```python
class StateMapper:
    def build_phase_input(self, state: BlackboardState, phase_io: PhaseIOSchema) -> dict[str, Any]: ...
    def wrap_phase_output(self, phase_id: str, output: dict[str, Any], phase_io: PhaseIOSchema) -> dict[str, Any]: ...
    def build_child_input(self, target_skill_root: Path, explicit_input: dict[str, Any]) -> dict[str, Any]: ...
```

| 方法 | 输入 | 输出 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|
| `build_phase_input` | state + phase `io.inputs` | local dict | `[F-v3-runtime-state-mapping-failed]` | phase 读切片 |
| `wrap_phase_output` | phase_id + output + `io.outputs` | namespaced output | `[F-v3-runtime-state-mapping-failed]` | phase 写回 |
| `build_child_input` | resolved target skill root + explicit input | child canonical input | `[F-v3-runtime-state-mapping-failed]` / `[F-v3-skill-not-registered]` | 子图合约漏斗 |

## Data Model / State

### 1. BlackboardState 规范化区域

| 区域 | 类型 | 必填 | 默认值 | 校验规则 | 业务作用 |
|---|---|---|---|---|---|
| `data.inputs` | dict | 是 | `{}` | 只由 Runtime Input Funnel 写入; 全生命周期只读 | 根输入专区 |
| `data.phase_outputs` | dict[str, dict] | 是 | `{}` | 只由 StateMapper 写入 | phase 输出命名空间 |
| `data.scratch` | dict | 否 | `{}` | 单 phase 临时数据, 不进入最终 context | 临时计算 |
| `flow` | dict | 是 | `{}` | 控制字段; child 调用 deep copy | 深度 / retry / run 控制 |
| `messages` | list | Agent runtime 使用 | `[]` | 不跨 child graph 共享 | LLM 对话历史 |

MVP0 可以内部继续兼容旧扁平 `data`, 但语义上必须收敛到 inputs / phase_outputs / scratch 三个区域。

### 2. ReaderSandboxState

```python
class ReaderSandboxState(TypedDict):
    data: dict[str, Any]
    flow: dict[str, Any]
    messages: list[Any]
```

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 业务作用 |
|---|---|---|---|---|---|
| `data.references` | list | 是 | `[]` | 只含当前 Agent phase references | reader 业务输入 |
| `data.skill_id` | string | 是 | 无 | trace id | 定位 |
| `data.phase_id` | string | 是 | 无 | trace id | 定位 |
| `flow.timeout_s` | integer | 否 | `60` | 超时触发 WARN fallback | 控制 reader |
| `messages` | list | 是 | `[]` | 不继承父 Agent messages | 消息隔离 |

## Cross-feature Interaction

### 1. 与 skill-compilation 的耦合

本模块不解析 Markdown。`GRAPH.md io.inputs`、phase `io.inputs` / `io.outputs`、SUBGRAPH target skill 和 reference registry 都来自 [skill-compilation](../skill-compilation/mvp0-alignment.md#后端功能) 的编译产物。

### 2. 与 execution-runtime 的耦合

execution-runtime 调用 Agent、LOGIC、SUBGRAPH、reference reader 时必须经过本文件定义的 wrapper / StateMapper。runtime 负责执行, state-and-io-contract 负责运行前切片、运行后封装和 child graph 隔离。

### 3. 与 tracing-and-observability 的耦合

Trace 应记录 canonical root inputs、每个 phase_input、phase_output、child graph canonical input、reference reader fallback。记录的是沙盒后的结构, 不是全量父黑板。观测侧规划见 [tracing-and-observability mvp0 alignment](../tracing-and-observability/mvp0-alignment.md#后端功能)。
