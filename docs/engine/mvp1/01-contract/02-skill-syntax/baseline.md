---
module: 01-contract/02-skill-syntax
doc: baseline
status: drafted（现状对齐 pinned 代码 2f77c76；GRAPH/LOGIC/SUBGRAPH 解析已核实；LOGIC V4 与 SUBGRAPH path/io 仍有 refactor-target drift）
binds_alignment: ./mvp1-alignment.md
binds_code: packages/graph-agent/src/graph_agent/core/loader.py:SkillLoader.compile_skill; packages/graph-agent/src/graph_agent/core/manifest.py:GraphManifest; packages/graph-agent/src/graph_agent/core/manifest.py:LogicNodeAST; packages/graph-agent/src/graph_agent/core/manifest.py:SubgraphNodeAST
---

# 02-skill-syntax — Baseline(当下代码实现逻辑)

> **Scope**: skill 文件语法的**当前代码现状**:GRAPH/LOGIC/SUBGRAPH 的 frontmatter 解析、body 解析、AST 与运行装配入口。本文只对照代码,不拿旧 spec 当现状。
> **现状一句话**:当前代码已能解析 V0.3.0 `GRAPH.md`、`LOGIC.md`、`SUBGRAPH.md`,但仍有几处与 mvp1 目标反转不一致:LOGIC action 仍走可变 `Context`；SUBGRAPH / agent `subgraphs[]` 仍是 `target_skill` 逻辑 id；SUBGRAPH 编译期仍做父子 IO 完整相等校验；validator 主要是 bool/占位契约,缺完整加载生命周期。

## UI/UX
N/A。

## 前端逻辑
N/A —— skill 源码语法被 Studio 编辑器/copilot 消费；本 baseline 只核代码解析层。

## 后端功能

### 1. 通用 Markdown/YAML 解析与路由
- Markdown frontmatter/body 拆分:`packages/graph-agent/src/graph_agent/core/parser.py:parse_markdown_parts` 读取 YAML frontmatter 与 raw body。
- 根编译主路径:`packages/graph-agent/src/graph_agent/core/loader.py:SkillLoader.compile_skill` 读取 `GRAPH.md`,再扫描 `phases/<id>/` 下的 phase 节点文件。
- phase 文件名到 mode 的映射:`packages/graph-agent/src/graph_agent/core/loader.py:_PHASE_FILE_TO_MODE` 固定 `LOGIC.md`→`logic`、`SUBGRAPH.md`→`subgraph`、`SKILL.md`→`agent`。
- phase AST 构建:`packages/graph-agent/src/graph_agent/core/loader.py:_build_phase_document` 注入内部 `mode`,再用 `LogicNodeAST` / `SubgraphNodeAST` / `AgentNodeAST` 做 Pydantic 校验。

### 2. GRAPH.md 现状
- 根 AST:`packages/graph-agent/src/graph_agent/core/manifest.py:GraphManifest` 当前字段为 `schema_version`、`name`、`description`、`io`、`phases`、`metadata`。
- inline IO 结构:`packages/graph-agent/src/graph_agent/core/manifest.py:PhaseIOSchema` 要求 `inputs` / `outputs` 两个 dict；`packages/graph-agent/src/graph_agent/core/loader.py:_reject_deprecated_physical_io` 禁 `io/inputs.json`、`io/outputs.json`；`packages/graph-agent/src/graph_agent/core/loader.py:_build_graph_manifest` 禁 `io_inputs_ref` / `io_outputs_ref`。
- 根版本/manifest 校验:`packages/graph-agent/src/graph_agent/core/loader.py:_build_graph_manifest` 要求 `schema_version == "v0.3.0"`、`phases` 是 list,再交给 `GraphManifest.model_validate`。
- body DAG 解析:`packages/graph-agent/src/graph_agent/core/loader.py:_extract_body_phase_refs` 解析 `<phase depends_on="...">name</phase>` 与 `output` flag。
- 拓扑校验:`packages/graph-agent/src/graph_agent/core/loader.py:_validate_graph_topology` 串起 `_validate_graph_phase_declarations`、`_validate_phase_name_sets`、`_validate_acyclic_graph`、`_validate_no_islands`、`_validate_unknown_dependencies`、`_validate_output_phases`、`_validate_phase_dir`。
- phase 节点唯一性:`packages/graph-agent/src/graph_agent/core/loader.py:_discover_phase_files` 要求每个 phase 目录恰好有 `LOGIC.md` / `SUBGRAPH.md` / `SKILL.md` 之一。

**GRAPH drift / refactor-target**:
- `packages/graph-agent/src/graph_agent/core/manifest.py:GraphManifest` 当前没有 `llm_role` 字段；目标语法有 graph 默认 `llm_role`。
- `packages/graph-agent/src/graph_agent/core/manifest.py:GraphManifest` 对 `name` 只做长度约束,未实现目标正则 `^[a-z][a-z0-9_-]*$`；`phases` item 也未逐项做正则。
- `packages/graph-agent/src/graph_agent/core/loader.py:_validate_output_phases` 当前要求至少一个 body `<phase output>`；目标语法允许未标记时由无下游节点推导输出候选。
- `packages/graph-agent/src/graph_agent/core/loader.py:_validate_inline_io_schema` 只调用 Draft 2020-12 `check_schema`,未强制顶层 `type: object` 或必须含 `properties`。
- 当前未见完整静态数据流“phase required 输入必须来自根输入或上游输出”的来源校验；`packages/graph-agent/src/graph_agent/core/loader.py:_validate_sequential_overwrites` 只处理上游输出字段覆盖授权。

### 3. LOGIC.md 现状
- AST:`packages/graph-agent/src/graph_agent/core/manifest.py:LogicNodeAST` 当前字段为 `mode`、`io`、`actions`、`validator`,并继承 `name`、`raw_blocks`、`metadata`、`allow_sequential_overwrite`、`batch`。
- body `<action>`:`packages/graph-agent/src/graph_agent/core/loader.py:_extract_logic_actions` 从 body 抽取 `<action>...</action>`；`packages/graph-agent/src/graph_agent/core/loader.py:_validate_logic_actions_declared` 要求 frontmatter `actions` 与 body 顺序完全一致。
- action 目录发现:`packages/graph-agent/src/graph_agent/core/loader.py:_discover_actions_and_tools` 只允许 LOGIC phase 有 `actions/`,并调用 `packages/graph-agent/src/graph_agent/core/loader.py:_load_action_dir` 加载 phase-local `actions/*.py`。
- action registry:`packages/graph-agent/src/graph_agent/core/actions.py:ActionDef` / `packages/graph-agent/src/graph_agent/core/actions.py:ActionRegistry` 保存并按 `phase_id + action_name` resolve。
- action 签名现状:`packages/graph-agent/src/graph_agent/core/loader.py:_validate_action_signature` 要求第一个参数名是 `context` 或 `ctx`,且注解兼容 `graph_agent.cognitive.context_facade.Context`。
- LOGIC 运行装配:`packages/graph-agent/src/graph_agent/core/graph_assembler.py:_build_logic_node` 当前创建 `Context(data, phase_id=..., run_id=...)`,然后执行 `action(ctx)`；返回必须是 dict,返回 key 和 Context mutation delta 都通过 `_validate_logic_update_keys` 限制在 `io.outputs`。
- 运行外层 StateMapper:`packages/graph-agent/src/graph_agent/core/graph_assembler.py:_wrap_phase_runtime_node` 用 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:StateMapper` 包裹 LOGIC 节点,按 `io.inputs` 过滤输入、按 `io.outputs` 限制写回。
- purity 扫描:`packages/graph-agent/src/graph_agent/core/purity.py:scan_python_purity` 当前拦截本地写类 API,包括写模式 `open()`、Path mutation、`os`/`shutil` 文件系统变更、`tempfile`。

**LOGIC drift / refactor-target**:
- mvp1 目标是 `def <action_name>(inputs) -> dict`、只读 inputs、纯返回；当前 `packages/graph-agent/src/graph_agent/core/loader.py:_validate_action_signature` 与 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:_build_logic_node` 仍要求/传入可变 `Context`。
- 当前 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:_build_logic_node` 允许 action 通过 Context mutation 产生 delta；目标要求 action 不写黑板,只返回 dict。
- 当前 `packages/graph-agent/src/graph_agent/core/loader.py:_load_action_dir` 发现本地 `actions/*.py` 中的任意本模块函数,未强制函数名必须等于文件名。
- 当前未见 Engine/Studio 通用 action registry 装配入口；`packages/graph-agent/src/graph_agent/core/actions.py:ActionRegistry` 只承载 loader 发现的 phase-local actions。
- 当前 `packages/graph-agent/src/graph_agent/core/purity.py:scan_python_purity` 未覆盖 mvp1 目标硬禁的 `run_skill`、`sys.path` hack、import 越界、非序列化对象返回。
- validator 现状只在 AST 中有 `validator: StrictBool`;`packages/graph-agent/src/graph_agent/core/validator_contract.py:VALIDATOR_SIGNATURE` 只是占位契约,注释明确运行期 validator loading 在后续 PR；当前未见 LOGIC `validator.py` 缺失/entrypoint 的编译期加载校验,也未见 `_build_logic_node` 后置调用 validator。

### 4. SUBGRAPH.md 现状
- AST:`packages/graph-agent/src/graph_agent/core/manifest.py:SubgraphNodeAST` 当前字段为 `mode`、`target_skill`、`io`、`validator`,并继承 `name`、`raw_blocks`、`metadata`、`allow_sequential_overwrite`、`batch`。
- `target_skill` schema:`packages/graph-agent/src/graph_agent/core/manifest.py:SubgraphNodeAST` 使用 `packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py:SKILL_ID_PATTERN`;agent `SKILL.md` 的 `subgraphs[]` 仍复用 `packages/graph-agent/src/graph_agent/core/manifest.py:AgentRegistryItem`,字段也是 `target_skill`。
- 编译期子图 IO 校验:`packages/graph-agent/src/graph_agent/core/loader.py:_validate_subgraph_io_contracts` 对每个 `SubgraphNodeAST` 调 `resolve_skill_root(resolver, doc.ast.target_skill)`,递归编译子图,再要求父 `SUBGRAPH.md io.inputs/outputs` 与子 `GRAPH.md io.inputs/outputs` 整个 schema 相等。
- 运行期子图装配:`packages/graph-agent/src/graph_agent/core/graph_assembler.py:_build_subgraph_node` 同样用 `resolve_skill_root(skill_resolver, phase_ast.target_skill)` 找子图 root,递归 assemble 后 invoke 子 graph。
- SUBGRAPH runtime 已被 StateMapper 包裹:`packages/graph-agent/src/graph_agent/core/graph_assembler.py:_wrap_phase_runtime_node` + `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:StateMapper` 会按父 `SUBGRAPH.md io.inputs` 切片,并按 `io.outputs` 限制合并。

**SUBGRAPH drift / refactor-target**:
- mvp1 目标字段是绝对 `path`;当前 `packages/graph-agent/src/graph_agent/core/manifest.py:SubgraphNodeAST` 和 `packages/graph-agent/src/graph_agent/core/manifest.py:AgentRegistryItem` 仍是 `target_skill` 逻辑 id。
- mvp1 目标无 registry 寻址;当前 `packages/graph-agent/src/graph_agent/core/loader.py:_validate_subgraph_io_contracts` 与 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:_build_subgraph_node` 仍调用 `resolve_skill_root(... target_skill)`。
- mvp1 目标放宽父子 IO,只按普通节点做 blackboard slice/merge；当前 `packages/graph-agent/src/graph_agent/core/loader.py:_validate_subgraph_io_contracts` 仍要求父子 `io.inputs/outputs` schema 完全相等。
- SUBGRAPH validator 当前只是 `SubgraphNodeAST.validator` bool 与 `validator_contract.py:VALIDATOR_SIGNATURE` 占位,未见 subgraph phase-local `validator.py` 加载/调用生命周期。

## API
- 根 AST:`packages/graph-agent/src/graph_agent/core/manifest.py:GraphManifest`
- phase AST union:`packages/graph-agent/src/graph_agent/core/manifest.py:PhaseAST`
- LOGIC AST:`packages/graph-agent/src/graph_agent/core/manifest.py:LogicNodeAST`
- SUBGRAPH AST:`packages/graph-agent/src/graph_agent/core/manifest.py:SubgraphNodeAST`
- 编译产物:`packages/graph-agent/src/graph_agent/core/loader.py:CompiledSkill`
- phase 文档:`packages/graph-agent/src/graph_agent/core/loader.py:PhaseDocument`
- action registry:`packages/graph-agent/src/graph_agent/core/actions.py:ActionRegistry`

## Data Model / State
skill 源码(语法)→ `CompiledSkill` → LangGraph node:
- `GRAPH.md` frontmatter/body 产出 `GraphManifest` + `raw["graph_topology"]`。
- `LOGIC.md` 产出 `LogicNodeAST`,再由 `graph_assembler.py:_build_logic_node` 转成运行节点。
- `SUBGRAPH.md` 产出 `SubgraphNodeAST`,再由 `graph_assembler.py:_build_subgraph_node` 转成子图 invoke 节点。
- `StateMapper` 现已承担 phase 输入切片和输出字段限制,但若编译期旧校验拦住,子图 path/io 放宽目标仍无法成立。

## 当前边界(这个模块现在不是什么)
- 不是运行机制最终真相:LOGIC 运行外层决策归 `02-mechanism/04-run-outer/01-graph-exec`,本文只记录 skill 语法现状。
- 不是 resolver 真相:子图 `target_skill`→path 的旧解析现状归 `02-mechanism/02-resolver` 也有 baseline；本文只写语法字段现状。
- SKILL.md / cognitive / mention / resource / iterate / io 切片语法还未在本批展开。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标 |
|---|---|---|
| GRAPH `name`/phase id 命名 | `GraphManifest.name` 只长度约束；phase item 未逐项正则 | `^[a-z][a-z0-9_-]*$` |
| GRAPH `llm_role` | `GraphManifest` 无字段 | 可选,默认 `"analyst"`,必须已注册 |
| GRAPH output phase | `_validate_output_phases` 要求显式 `<phase output>` | 可显式多个；未标记时由无下游节点推导 |
| GRAPH inline IO object | `_validate_inline_io_schema` 只 `check_schema` | 顶层 `type: object` 且含 `properties` |
| GRAPH 静态数据流 | 未见 required 来源完整校验 | required 必须来自根输入或上游输出 |
| LOGIC action 签名 | `_validate_action_signature` 要求 `context/ctx` + `Context` | `def <action_name>(inputs) -> dict` |
| LOGIC action 写状态 | `_build_logic_node` 允许 Context mutation delta | 只读 inputs,纯返回 dict,不写黑板 |
| LOGIC purity | 只挡部分本地写/FS 变更 | 硬禁 `run_skill`/FS/sys.path/import 越界/非序列化返回 |
| LOGIC validator | bool + `VALIDATOR_SIGNATURE` 占位,未见加载/调用 | `validator: true` 必须加载同级 `validator.py` 并后置阻断 |
| SUBGRAPH 寻址字段 | `target_skill` 逻辑 id | `path` 绝对路径 |
| SUBGRAPH resolver | `resolve_skill_root(... target_skill)` | 直接按绝对 path 解析,无 registry |
| SUBGRAPH IO | 编译期父子 schema 完整相等 | 普通节点黑板切片/合并,不强制父子 1:1 |

> **验"是否按 mvp1 改了"**:① GRAPH name/phase/io/output/dataflow 按目标收紧或推导；② LOGIC action 不再接受 `Context`,改为 action 同名函数 `inputs -> dict`,mutation/run_skill/FS/sys.path/import 越界被挡；③ LOGIC/SUBGRAPH validator 生命周期真正加载同级 `validator.py`;④ SUBGRAPH / agent `subgraphs[]` 解析 `path` 绝对路径,旧 `target_skill` 报未知字段；⑤ 移除/反转 `_validate_subgraph_io_contracts` 的父子 1:1 schema 相等门。

## 读代码主路径提示
GRAPH: `loader.py:SkillLoader.compile_skill` → `parser.py:parse_markdown_parts` → `loader.py:_build_graph_manifest` → `loader.py:_extract_body_phase_refs` → `loader.py:_validate_graph_topology` → `loader.py:_discover_phase_files`。

LOGIC: `loader.py:_build_phase_document` → `manifest.py:LogicNodeAST` → `loader.py:_extract_logic_actions` / `_validate_logic_actions_declared` → `loader.py:_discover_actions_and_tools` / `_load_action_dir` → `graph_assembler.py:_build_logic_node` → `runtime/state_mapper.py:StateMapper`。

SUBGRAPH: `loader.py:_build_phase_document` → `manifest.py:SubgraphNodeAST` → `loader.py:_validate_subgraph_io_contracts` → `graph_assembler.py:_build_subgraph_node` → `runtime/state_mapper.py:StateMapper`。

## 交叉引用(链接, 不复制)
`mvp1-alignment`(目标) · `01-physical-layout`(文件位置/节点唯一) · `03-compile-rules`(错误码全表) · `02-mechanism/02-resolver`(path 解析目标) · `02-mechanism/04-run-outer/01-graph-exec`(LOGIC V4 / StateMapper)
