---
module: 01-contract/03-compile-rules
doc: baseline
status: drafted（现状对齐代码 error_registry.py / loader.py / purity.py；已移除 mvp0 SSOT 依赖）
binds_alignment: ./mvp1-alignment.md
binds_code:
  - packages/graph-agent/src/graph_agent/core/error_registry.py:ERROR_REGISTRY
  - packages/graph-agent/src/graph_agent/core/loader.py:SkillLoader.compile_skill
  - packages/graph-agent/src/graph_agent/core/purity.py:scan_python_purity
units: [U4, U11, U12]
---

# 03-compile-rules — Baseline(当下代码实现逻辑)

> **Scope**: 编译规则与错误码现状。代码 SSOT 是 `error_registry.py:ERROR_REGISTRY`(93 个码及 level/stage/doc_link)、`loader.py:SkillLoader.compile_skill`(DAG/IO/mention/purity 等校验聚合)、`purity.py:scan_python_purity`(action/tool Python 扫描器)。
> **现状一句话**: registry 已有 93 个 `[F-v3-*]` 码；loader 会在编译期聚合物理结构、frontmatter、DAG、IO、mention、subgraph/subagent resolver、action purity 等校验；purity 扫描器现只挡本地写 API/语法错误，尚未覆盖 mvp1 目标里的 `run_skill` / `sys.path` 硬禁。

## UI/UX
N/A。本模块是 engine 契约/编译规则，不直接承载 Studio UI。

## 前端逻辑
N/A。Studio 前端只消费编译结果和错误 payload；错误 payload 形状归 `03-api-contract` / `data-contracts`。

## 后端功能

### 1. 错误码注册表(error_registry.py)
`ERROR_REGISTRY`(`packages/graph-agent/src/graph_agent/core/error_registry.py:ERROR_REGISTRY`)注册 93 个 `ErrorCodeMetadata`，每个条目包含:

| 字段 | 代码现状 |
|---|---|
| `code` | 与字典 key 相同的 `[F-v3-*]` 字符串 |
| `level` | `FATAL` 或 `WARN` |
| `stage` | `("编译期",)` / `("装配期",)` / `("运行期",)` 或多阶段 tuple |
| `doc_link` | 指向 mvp1 契约/机制文档的链接 |

代码与迁移源逐码核对结果:表内 93 个码与 `ERROR_REGISTRY` 93 个码集合完全一致，无 table-only / registry-only 项，阶段 tuple 也一致。`[F-v3-mention-unused-registry-entry]` 与 `[F-v3-reference-reader-failed]` 是 `WARN`，其余现有码为 `FATAL`。

### 2. 编译期校验聚合(loader.py)
`SkillLoader.compile_skill`(`packages/graph-agent/src/graph_agent/core/loader.py:SkillLoader.compile_skill`)负责把 skill root 编译成 `CompiledSkill`，主要现状:

- 递归编译防护:加载栈循环报 `[F-v3-compile-recursion-cycle]`，深度超限报 `[F-v3-compile-depth-exceeded]`。
- 根结构校验:`_guard_v030_root` / `_reject_deprecated_physical_io` / `_build_graph_manifest` 校验 `GRAPH.md`、inline IO、schema version、deprecated IO 文件。
- 拓扑校验:`_extract_body_phase_refs` + `_validate_graph_topology` 校验 phase 注册、依赖、输出 phase、DAG cycle/island、phase 目录/节点文件。
- phase AST 校验:`_build_phase_document` 按 `LOGIC.md` / `SUBGRAPH.md` / `SKILL.md` 构建 typed AST。
- subgraph/subagent 可达性:`_validate_subgraph_io_contracts` / `_compile_subagent_metadata` 经 `SkillResolverProtocol` 解析 target skill。
- dataflow / output 校验:`_validate_logic_action_return_keys` 和 `_validate_sequential_overwrites` 处理 action 输出字段与串联覆盖。
- purity:`_discover_actions_and_tools` 加载 action/tool 前调用 `_raise_on_purity_violations`，命中后报 `[F-v3-logic-action-purity-violation]`。

编译期不执行 action、不调用业务 Agent；resolver 可用于 skill root 可达性检查。

### 3. purity 扫描器(purity.py)
`scan_python_purity`(`packages/graph-agent/src/graph_agent/core/purity.py:scan_python_purity`)对 action/tool Python 文件做 AST walk，当前会报:

- Python 语法错误(`api="python"`)。
- 写模式 `open()`、`Path.write_text` / `Path.unlink` 等 path mutation API。
- `os` / `shutil` 文件系统 mutation API。
- `tempfile` 临时文件创建 API。

`scan_tool_imports_context` 额外禁止 tool 导入 `graph_agent.cognitive.context_facade`。当前代码债:扫描器尚未硬禁 action 里调用 `run_skill`、修改 `sys.path`、import 越界；这是 mvp1 LE2 目标，见 `02-mechanism/04-run-outer/01-graph-exec`。

### 4. StateMapper required 校验 drift(跨模块代码债)
运行时 StateMapper 不归本模块实现，但三段生命周期契约会引用它。代码现状见 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:StateMapper.build_phase_input`:它调用 `filter_runtime_inputs` 只按 `io.inputs.properties` 过滤字段，**不读取也不强制 `required`**。因此 “slice 时 required 缺失报 `[F-v3-runtime-state-mapping-failed]`” 是 mvp1 目标契约，不是当前代码现状；同一 drift 已在 `docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/baseline.md` 记录。

## API
本模块不定义 public API。它约束的运行入口由 `03-api-contract` 定义，编译机制入口由 `02-mechanism/01-compile` 实现。

## Data Model / State
错误 payload 数据形状由 `ErrorCodeMetadata` 和 `ErrorPayload` 承接:至少有 `code`、`level`、`stage`、`message`、`doc_link`，可带 `skill_id`、`phase_id`、`field_path`、`source_path`。

## 当前边界(这个模块现在不是什么)
- 不是 scanner 实现细节文档；loader/purity/module_sandbox 的实现归 `02-mechanism/01-compile`。
- 不是运行外层实现文档；StateMapper、LOGIC action 执行、SUBGRAPH 调用归 `02-mechanism/04-run-outer/01-graph-exec`。
- 不是错误 payload API 文档；API/JSON 边界归 `03-api-contract` / `data-contracts`。

## baseline / alignment 差异(测试锚点)

| 维度 | 现状 | 目标 |
|---|---|---|
| 错误码总量 | `ERROR_REGISTRY` 93 个码，集合与迁移源 93 行一致 | mvp1 alignment 自承载 93 行，不再链接旧 spec 当 SSOT |
| doc_link | 现状应指向 mvp1 文档 | 验证所有 `metadata.doc_link.startswith("docs/engine/mvp1/")` |
| golden stale | registry 现无 `[F-v3-golden-stale-fields]` | mvp1 目标:golden 缺必填字段是 eval 期 staleness，不是编译期 |
| iterate 码族 | registry 现无 `[F-v3-iterate-*]` | mvp1 目标:iterate 编译校验码族待加入 registry |
| purity 范围 | 只挡本地写 API / tempfile / 部分 tool context import | 扩展硬禁 action 里 `run_skill`、文件系统、`sys.path`、import 越界 |
| StateMapper required | `build_phase_input` 只过滤 properties，required 缺失静默丢 | required 缺失报 `[F-v3-runtime-state-mapping-failed]` |

> **验“是否按 mvp1 改了”**:① registry 仍是 93 个现有码且 doc_link 全部指向 mvp1；② compile-rules alignment 有 93 行全表与三段生命周期；③ mvp0 11/12 不再被本域当 SSOT 引用；④ StateMapper required drift 明确留在 graph-exec refactor-target。

## 读代码主路径提示
`error_registry.py:ERROR_REGISTRY` → `exceptions.py:ErrorPayload` 自动补 metadata → `loader.py:SkillLoader.compile_skill` 编译校验聚合 → `purity.py:scan_python_purity` / `loader.py:_raise_on_purity_violations` purity 错误上报。

## 交叉引用(链接, 不复制)
mvp1-alignment(目标) · `02-mechanism/01-compile`(loader/purity 实现,双向) · `02-mechanism/04-run-outer/01-graph-exec`(StateMapper + LOGIC action 目标,双向) · `01-contract/02-skill-syntax`(被校验语法) · `01-contract/05-invalidation` / `05-run-inner/06-golden-eval`(golden eval 期) · `02-mechanism/04-run-outer/02-iterate`(iterate 码族目标) · `03-api-contract` / `01-contract/04-data-contracts`(payload/API 形状)
