---
module: 01-contract/03-compile-rules
doc: baseline
status: drafted（现状对齐 WS-E1 Step4 后代码 error_registry.py / loader.py / purity.py / exceptions.py / result.py；已移除 mvp0 SSOT 依赖；WS-E3 P0-1 已落 details+diagnostics 最小闭环；iterate 两个错误码已注册）
binds_alignment: ./mvp1-alignment.md
binds_code:
  - packages/graph-agent/src/graph_agent/core/error_registry.py:ERROR_REGISTRY
  - packages/graph-agent/src/graph_agent/core/loader.py:SkillLoader.compile_skill
  - packages/graph-agent/src/graph_agent/core/purity.py:scan_python_purity
units: [U4, U11, U12]
---

# 03-compile-rules — Baseline(当下代码实现逻辑)

> **Scope**: 编译规则与错误码现状。代码 SSOT 是 `error_registry.py:ERROR_REGISTRY`(95 个码及 level/stage/doc_link)、`loader.py:SkillLoader.compile_skill`(DAG/IO/mention/purity/iterate 等校验聚合)、`purity.py:scan_python_purity`(action/tool Python 扫描器)。
> **现状一句话**: registry 已有 95 个 `[F-v3-*]` 码；WS-E1 Step4 新增 `[F-v3-iterate-accumulate-fields-missing]` 与 `[F-v3-iterate-over-not-list]`。loader 会在编译期聚合物理结构、frontmatter、DAG、IO、mention、subgraph/subagent resolver、iterate loop 输入字段、action purity 等校验；WS-E3 P0-1 已落 `ErrorPayload.details` + `GraphAgentError.context` 序列化 + `RunResult.diagnostics` 有界快照;purity 扫描器已从本地写 API 扩到 LE2 的 `run_skill` / 直接 FS / `sys.path` / 动态 import 高风险路径。

## UI/UX
N/A。本模块是 engine 契约/编译规则，不直接承载 Studio UI。

## 前端逻辑
N/A。Studio 前端只消费编译结果和错误 payload；错误 payload 形状归 `03-api-contract` / `data-contracts`。

## 后端功能

### 1. 错误码注册表(error_registry.py)
`ERROR_REGISTRY`(`packages/graph-agent/src/graph_agent/core/error_registry.py:ERROR_REGISTRY`)注册 95 个 `ErrorCodeMetadata`，每个条目包含:

| 字段 | 代码现状 |
|---|---|
| `code` | 与字典 key 相同的 `[F-v3-*]` 字符串 |
| `level` | `FATAL` 或 `WARN` |
| `stage` | `("编译期",)` / `("装配期",)` / `("运行期",)` 或多阶段 tuple |
| `doc_link` | 指向 mvp1 契约/机制文档的链接 |

WS-E1 Step4 前的 93 个既有码保持不变；Step4 只新增两个 iterate 码。`[F-v3-mention-unused-registry-entry]` 与 `[F-v3-reference-reader-failed]` 是 `WARN`，其余现有码为 `FATAL`。

iterate 新增码:
- `[F-v3-iterate-accumulate-fields-missing]`:编译期 fatal；loop phase `io.inputs` 缺 `item_var` 或 `accumulate.var`。
- `[F-v3-iterate-over-not-list]`:编译期/运行期 fatal metadata；当前 runtime 在 `iterate.over` 解析结果不是 list 时抛出。

### 2. 编译期校验聚合(loader.py)
`SkillLoader.compile_skill`(`packages/graph-agent/src/graph_agent/core/loader.py:SkillLoader.compile_skill`)负责把 skill root 编译成 `CompiledSkill`，主要现状:

- 递归编译防护:加载栈循环报 `[F-v3-compile-recursion-cycle]`，深度超限报 `[F-v3-compile-depth-exceeded]`。
- 根结构校验:`_guard_v030_root` / `_reject_deprecated_physical_io` / `_build_graph_manifest` 校验 `GRAPH.md`、inline IO、schema version、deprecated IO 文件。
- 拓扑校验:`_extract_body_phase_refs` + `_validate_graph_topology` 校验 phase 注册、依赖、输出 phase、DAG cycle/island、phase 目录/节点文件。
- phase AST 校验:`_build_phase_document` 按 `LOGIC.md` / `SUBGRAPH.md` / `SKILL.md` 构建 typed AST。
- subgraph/subagent 可达性:`_validate_subgraph_io_contracts` / `_compile_subagent_metadata` 经 `SkillResolverProtocol` 解析 target skill。
- dataflow / output 校验:`_validate_logic_action_return_keys` 和 `_validate_sequential_overwrites` 处理 action 输出字段与串联覆盖。
- iterate 校验:`_validate_iterate_compile_contracts` 处理 loop phase `io.inputs` 必含 `item_var` 与 `accumulate.var`;runtime 对 `iterate.over` 非 list 报 `[F-v3-iterate-over-not-list]`。
- purity:`_discover_actions_and_tools` 加载 action/tool 前调用 `_raise_on_purity_violations`，命中后报 `[F-v3-logic-action-purity-violation]`。

编译期不执行 action、不调用业务 Agent；resolver 可用于 skill root 可达性检查。

### 3. purity 扫描器(purity.py)
`scan_python_purity`(`packages/graph-agent/src/graph_agent/core/purity.py:scan_python_purity`)对 action/tool Python 文件做 AST walk，当前会报:

- Python 语法错误(`api="python"`)。
- `run_skill` 编排调用。
- `open()` / `io.open` 文件访问。
- `pathlib.Path` 读、探测、枚举、stat、mutation API。
- `os` / `os.path` 文件系统访问或变更 API。
- `shutil` 文件系统变更 API。
- `tempfile` 临时文件创建 API。
- `glob` 文件枚举 API。
- `sys.path` mutation 调用及赋值/删除目标。
- `importlib` / `__import__` 动态导入高风险路径。

`scan_tool_imports_context` 额外禁止 tool 导入 `graph_agent.cognitive.context_facade`。现状仍是静态 AST 启发式,只扫描 loader 识别出的 skill-local action/tool 文件；不做全仓扫描,也不覆盖 LOGIC 纯签名、Context mutation 退场或非序列化返回。

### 4. StateMapper required 校验 drift(跨模块代码债)
运行时 StateMapper 不归本模块实现，但三段生命周期契约会引用它。代码现状见 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:StateMapper.build_phase_input`:它调用 `filter_runtime_inputs` 只按 `io.inputs.properties` 过滤字段，**不读取也不强制 `required`**。因此 “slice 时 required 缺失报 `[F-v3-runtime-state-mapping-failed]`” 是 mvp1 目标契约，不是当前代码现状；同一 drift 已在 `docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/baseline.md` 记录。

### 5. 错误契约 V2 P0-1 最小闭环(exceptions.py + result.py)
WS-E3 P0-1 已落地通用消费者所需的最小诊断容器，但未推进 registry 化和事件流:

- `ErrorPayload.details`(`packages/graph-agent/src/graph_agent/core/exceptions.py:62`) 默认 `{}`，由 `_normalize_details_val` 归一化为 JSON-safe 传输形状。`GraphAgentError.__init__` 会把异常 `context` 合入 `payload.details["context"]`;显式 dict 型 `details["context"]` 与异常 context 冲突时，显式值优先。
- `RunResult.diagnostics`(`packages/graph-agent/src/graph_agent/core/result.py:86`) 是最终诊断快照；`error` 仍保留为主 fatal。失败只传 `error` 时 diagnostics 自动包含主 fatal；显式 diagnostics 会与主 error 去重合并、按 `diagnostics_limit` 截断，并产出 `diagnostic_counts={total,by_level,by_code}`。
- 真实 run failure 边界不用改 `runner.py`:现有 `_write_workflow_result_artifacts` 通过 `result.model_dump(mode="json")` 写 `result.json`，因此新增 diagnostics 字段会自然落盘。
- P0-1 **未改** `ERROR_REGISTRY` key set、`ErrorCodeMetadata` 形状、`doc_link` 语义，也未新增 `remediation` / `doc_ref` / `doc_url` / `details_schema` / `schema_version`。
- P0-1 **未实现** `DiagnosticEmittedEvent` / `CallbackEvent` union 变更 / `GET /errors` / golden 新码 / 运行期细分码；这些仍归后续 WS-E4、P0-2、P0-3。iterate 两个基础码已由 WS-E1 Step4 注册。

## API
本模块不定义 public API。它约束的运行入口由 `03-api-contract` 定义，编译机制入口由 `02-mechanism/01-compile` 实现。

## Data Model / State
错误 payload 数据形状由 `ErrorCodeMetadata` 和 `ErrorPayload` 承接:至少有 `code`、`level`、`stage`、`message`、`doc_link`，可带 `skill_id`、`phase_id`、`field_path`、`source_path`、`details`。运行结果可通过 `RunResult.diagnostics` 获取有界诊断快照。

## 当前边界(这个模块现在不是什么)
- 不是 scanner 实现细节文档；loader/purity/module_sandbox 的实现归 `02-mechanism/01-compile`。
- 不是运行外层实现文档；StateMapper、LOGIC action 执行、SUBGRAPH 调用归 `02-mechanism/04-run-outer/01-graph-exec`。
- 不是错误 payload API 文档；API/JSON 边界归 `03-api-contract` / `data-contracts`。

## baseline / alignment 差异(测试锚点)

| 维度 | 现状 | 目标 |
|---|---|---|
| 错误码总量 | `ERROR_REGISTRY` 95 个码；WS-E3 P0-1 未改 key set，WS-E1 Step4 新增 2 个 iterate 码 | mvp1 alignment 自承载；新增码按 WS 落地后回写 baseline |
| doc_link | 现状应指向 mvp1 文档 | 验证所有 `metadata.doc_link.startswith("docs/engine/mvp1/")` |
| 错误契约 V2 P0-1 | `ErrorPayload.details`、异常 context 序列化、`RunResult.diagnostics` 有界快照已 live | 后续 registry 化、诊断事件、码表端点、运行期细分码分 WS 落地 |
| golden stale | registry 现无 `[F-v3-golden-stale-fields]` | mvp1 目标:golden 缺必填字段是 eval 期 staleness，不是编译期 |
| iterate 码族 | registry 已有 `[F-v3-iterate-accumulate-fields-missing]` / `[F-v3-iterate-over-not-list]`;loader/runtime 已使用 | 基础 iterate 错误码已落地；更细运行期码如需增加归后续契约 |
| purity 范围 | 已挡本地写/API、直接 FS、`run_skill`、`sys.path`、动态 import 高风险路径；tool context import 禁令仍有效 | 剩余 LOGIC 纯签名、Context mutation 退场、非序列化返回等由后续 WS 收口 |
| StateMapper required | `build_phase_input` 只过滤 properties，required 缺失静默丢 | required 缺失报 `[F-v3-runtime-state-mapping-failed]` |

> **验“是否按 mvp1 改了”**:① registry 是 95 个现有码且 doc_link 全部指向 mvp1；② compile-rules alignment 自承载错误码与三段生命周期；③ mvp0 11/12 不再被本域当 SSOT 引用；④ iterate 两个基础码已注册且被 loader/runtime 使用；⑤ StateMapper required drift 明确留在 graph-exec refactor-target；⑥ WS-E3 P0-1 的 details/diagnostics 回归测试绿。

## 读代码主路径提示
`error_registry.py:ERROR_REGISTRY` → `exceptions.py:ErrorPayload` 自动补 metadata + details/context 归一化 → `loader.py:SkillLoader.compile_skill` 编译校验聚合 → `loader.py:_validate_iterate_compile_contracts` iterate 编译校验 → `result.py:RunResult` diagnostics 快照 → `purity.py:scan_python_purity` / `loader.py:_raise_on_purity_violations` purity 错误上报。

## 交叉引用(链接, 不复制)
mvp1-alignment(目标) · `02-mechanism/01-compile`(loader/purity 实现,双向) · `02-mechanism/04-run-outer/01-graph-exec`(StateMapper + LOGIC action 目标,双向) · `01-contract/02-skill-syntax`(被校验语法) · `01-contract/05-invalidation` / `05-run-inner/06-golden-eval`(golden eval 期) · `02-mechanism/04-run-outer/02-iterate`(iterate 码族目标) · `03-api-contract` / `01-contract/04-data-contracts`(payload/API 形状)
