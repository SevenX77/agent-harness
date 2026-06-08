---
module: 02-mechanism/04-run-outer/01-graph-exec
doc: baseline
status: drafted（现状对齐 WS-E1 Step3 后代码；LOGIC runtime 已从可变 Context diff 收口为纯返回 dict,action/tool 两套注册表;2026-06-05 吸收 11-io 现状:子图 io 1:1 校验 + io.outputs file/artifact 落盘）
binds_alignment: ./mvp1-alignment.md
binds_code: core/graph_assembler.py（_build_logic_node:332, _build_subgraph_node:366）· runtime/state_mapper.py:37 · core/actions.py（18/49）· core/loader.py:528（_validate_subgraph_io_contracts）· io/manager.py:108（save_outputs）· io/storage.py:149（save_artifact）
---

# 01-graph-exec — Baseline(当下代码实现逻辑)

> **Scope**: 运行时按 DAG 执行 phase 的外层机制:`StateMapper`(io slice/merge)、LOGIC 执行(`_build_logic_node`,plain dict action input + 纯返回写回)、SUBGRAPH 调用、action/tool 两套注册表(`actions.py`)、io_manager。
> **现状一句话**:LOGIC 节点 `_build_logic_node`(`graph_assembler.py:332`)已不再创建可变 `Context` facade;每个 action 收到 `{**before, **updates}` plain dict,只有 action 显式返回的 dict 会通过 `_validate_logic_update_keys` 校验后写回。action 与 tool 是 `actions.py` 里**两套独立注册表**(`ActionDef`/`ActionRegistry` vs `ToolDef`/`ToolRegistry`)。StateMapper(`runtime/state_mapper.py:37`)做 io slice/merge,失败报 `[F-v3-runtime-state-mapping-failed]`。

## UI/UX
N/A。

## 前端逻辑
N/A。

## 后端功能

### 1. StateMapper:io 切片 / 回写(state_mapper.py)
`StateMapper`(`runtime/state_mapper.py:37`)按 phase 的 `io.inputs`/`io.outputs` 从黑板 slice 输入、merge 输出。
- **slice 输入**(`build_phase_input:44` → `filter_runtime_inputs:25`):只按 `io.inputs.properties` 过滤,**现状不校验 `required` 缺失**——缺的字段静默丢弃、不报错(`required` 在 schema 里根本没被读)。
- **merge 输出**(`wrap_phase_output:77`):output key 越界(不在 `io.outputs.properties`)才报 `[F-v3-runtime-state-mapping-failed]`(`:142`);`PhaseWrapper` 双包 / 节点异常也报同码(`:208/:225`)。
> ⚠️ **baseline 修正(2026-06-05 审计)**:旧文写"required 缺失报错"是把 alignment 目标当成了现状——代码实为只过滤、不校验 `required`。required 校验是 mvp1 目标(见差异表 + alignment §3/§6),归 refactor-target。

### 2. LOGIC 执行:plain dict inputs + 纯返回写回(WS-E1 Step3 已落)
`_build_logic_node`(`graph_assembler.py:332`):
1. `output_schema_keys = _schema_output_keys(phase_ast.io.outputs)`(`:338`)。
2. `before = phase_inputs_from_state(state)`(`:341`) 读取已由 `StateMapper` 按 `io.inputs` 切出的 phase-local 输入。
3. 每个 action 执行前构造 `action_ctx = {**before, **updates}`(`:348`)——这是普通 Python dict,不是 `Context` facade;前序 action 显式返回的 dict 会作为后序 action 的输入增量。
4. 调 `result = action(action_ctx)`(`:349`);返回非 dict 报 `[F-v3-logic-action-return-invalid]`。
5. 返回 dict 的 key 经 `_validate_logic_update_keys` 限制在 `io.outputs.properties` 子集后并入 `updates`;最终只把 `{"data": updates}` 交给外层 StateMapper。
> **WS-E1 Step3 收口点**:LOGIC runtime 已不再通过 Context mutation / `_dict_delta` 捕捉隐式写回。`context.set` / `context.update` / item assignment / `setdefault` 这类对 action 入参的本地修改不会隐式写入 blackboard。

### 3. action vs tool:两套独立注册表(actions.py)
- `ActionDef`(`actions.py:18`)/ `ActionRegistry`(`:25`,`for_phase` `:44`)——LOGIC 的 action(引擎调,确定性)。
- `ToolDef`(`:49`)/ `ToolRegistry`(`:60`,`_structured_tool` `:76`)——AGENT 的 tool(LLM 调,`StructuredTool`)。
- **两套独立、不互通、无桥**(mvp1 决定**不统一** capability,见 `04-tools` TL2)。

### 4. SUBGRAPH:io 严格 1:1 校验(loader)
SUBGRAPH 节点 `_build_subgraph_node`(`:363`,装配归 `03-assemble`)递归调 child graph,父 data 启动子图、回 delta。
- **子图 io 严格 1:1 校验**(编译期):`loader.py:_validate_subgraph_io_contracts`(:528,`:211` 调用)对 **inputs + outputs 都**强制父 `SUBGRAPH.md` io == 子 `GRAPH.md` io,任一不等 → `[F-v3-subgraph-io-mismatch]`(:553)fatal。mvp1 要**放宽 inputs**(子图像普通节点从黑板切片)、保留 outputs(见 alignment E1)。

### 5. io.outputs 落盘:file / artifact(io/manager + io/storage)
`IOManager.save_outputs`(`io/manager.py:108`,storage-agnostic)按 `output_spec.target`(默认 `"file"`,:143)分发:
- **artifact**(:163):有注入 `artifact_saver` 用它(:176);否则回退框架 `StorageManager.save_artifact`(:168 → `io/storage.py:149`,写 `<run_dir>/phases/<phase>/<name>`、str/bytes 原样 else JSON、发 `ArtifactSavedEvent`)。
- **file**(:184):`path` 来自 `output_spec.get("path")`(:185);**path-less 默认 `output_dir/{name}.json`**(:186-187,⚠️ 非旧文所写 `runner.py:603`);`{context.key}` 占位由 `_resolve_path_template`(:193 → :210)解析。
- ⚠️ **缺口:文件导入→黑板**——运行中"跑到节点才把外部文件字段注入黑板"**无机制**(mvp1 新增,alignment E2)。

## API
- `StateMapper`(`state_mapper.py:37`)——slice/merge。
- `_build_logic_node(...)`(`graph_assembler.py:325`)——LOGIC 节点闭包(装配归 `03-assemble`,执行范式归本域)。
- `ActionRegistry.for_phase(phase_id)`(`actions.py:44`)/ `ToolRegistry.for_phase`(`:71`)。

## Data Model / State
blackboard = `WorkflowState.data`(`data-contracts`);io 经 StateMapper slice/merge。LOGIC 现只把 action 返回 dict 写回 data,不再经可变 Context mutation diff 写回。

## 当前边界(这个模块现在不是什么)
- **LOGIC runtime 已纯返回**:action 收到 plain dict,只显式返回 dict 写回;loader 对 action 第一参数名仍要求 `context/ctx`,这是语法层 drift,见 `01-contract/02-skill-syntax/baseline.md`。
- **action/tool 不统一**:两套注册表(spec 已固定 Action≠Tool)。
- **代码里术语混叫**:历史处把 action 叫 "tool"(死簇,待清)。
- **子图 io 现严格 1:1**:inputs+outputs 都强制相等(`loader.py:528`),mvp1 放宽 inputs(E1)。
- **文件导入→黑板无机制**:运行中无"跑到节点才注入外部文件字段"(mvp1 新增 E2)。

## 🚨 已知代码债(2026-06-05 审计;如实记录,不在文档审计里改代码)
按"审计 ≠ 改代码"原则,以下代码现状如实登记 + 警告,归 refactor-target(kiro):
- **`ensure_no_input_write` 空壳**:`state_mapper.py:187` 函数体只有 `pass`,却列进 `__all__`(`:264`)对外导出——本应阻止往只读输入写值,现状什么都不做。🚨 要么实现、要么删。
- **类型逃逸(minor)**:`wrap_phase_output` 用 `cast(WorkflowState, updates)`(`:115`)、`PhaseWrapper.wrap` 用 `cast(Any, _wrapped)`(`:228`)绕过静态类型(`mypy` 过,但靠 cast 兜)。
- **`graph_assembler.py` 体积**:1403 行,且包内 ruff 对它豁免 C901(圈复杂度检查),极简度偏弱(装配细节归 `03-assemble`)。
- (黑板塞非序列化对象、死簇仍是 refactor-target；可变 Context mutation 写回已由 WS-E1 Step3 runtime 收口；skill-local action 源码里的 `run_skill`/直接 FS/`sys.path`/动态 import 已由 `01-compile` purity 门编译期拦截。)

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标(LE1-3) |
|---|---|---|
| action 写黑板 | 仅 action 返回 dict 写回;Context mutation diff 通道已关闭 | 纯返回 dict、只读 inputs(砍 set/update/delete) |
| action 编排/副作用 | skill-local action 源码里的 `run_skill`/直接 FS/`sys.path`/动态 import 已编译期 purity FATAL；运行时是 plain dict + 纯返回范式 | 保持 compile-time hard-ban,并继续收口非序列化返回等纯 action 数据契约 |
| 黑板对象 | 塞 `BatchAccumulator` 等非序列化对象 | `iterate.accumulate` + 序列化数据 |
| 死簇 | `code_phase_node`/`phase_executor` | 删(live 用 `_build_logic_node`) |
| StateMapper required 校验 | slice **不校验** required(只过滤 properties、缺失静默丢)(`filter_runtime_inputs:25`) | required 缺失报 `[F-v3-runtime-state-mapping-failed]`(alignment §3/§6) |
| 子图 io 校验 | inputs+outputs **都**严格 1:1(`loader.py:528/553`) | **放宽 inputs**(从黑板切片)、outputs 保留(E1) |
| 文件导入→黑板 | 无机制 | 跑到节点才 lazy 注入(E2) |
| io.outputs md artifact | str 原样写(`io/storage.py:167`);finish_task 工具走 markdown→parsed `data`,**未接 business_data_md**(中间件侧) | md 取 `business_data_md`、不 json→md 回转(E3) |

> **验"是否按 mvp1 改了"**:① LOGIC runtime 是否只把 action 返回 dict 写回、Context mutation 不再隐式改黑板;② action 里 `run_skill`/FS/`sys.path`/动态 import 是否触发编译期 purity FATAL;③ 黑板是否只剩可序列化数据;④ StateMapper required 缺失/越界 key 是否报 `[F-v3-runtime-state-mapping-failed]`。

## 读代码主路径提示
StateMapper `state_mapper.py:37` → LOGIC `_build_logic_node`(`graph_assembler.py:332`,plain dict action_ctx `:348`)→ action/tool 注册表 `actions.py:18/49` → SUBGRAPH `:366`。

## 交叉引用(链接, 不复制)
mvp1-alignment（目标 + LE1-3,双向）· `04-tools`(action/tool,双向)· `02-iterate` · `03-checkpoint` · `05-run-inner`(AGENT 委派)· `data-contracts`(blackboard)
