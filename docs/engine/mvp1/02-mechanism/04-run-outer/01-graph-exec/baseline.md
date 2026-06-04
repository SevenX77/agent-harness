---
module: 02-mechanism/04-run-outer/01-graph-exec
doc: baseline
status: drafted（现状对齐 pinned 代码 7cd4b9c；LOGIC 用可变 Context facade,action/tool 两套注册表）
---

# 01-graph-exec — Baseline(当下代码实现逻辑)

> **Scope**: 运行时按 DAG 执行 phase 的外层机制:`StateMapper`(io slice/merge)、LOGIC 执行(`_build_logic_node`,action + 可变 `Context` facade)、SUBGRAPH 调用、action/tool 两套注册表(`actions.py`)、io_manager。
> **现状一句话**:LOGIC 节点 `_build_logic_node`(`graph_assembler.py:325`)用**可变 `Context` facade**(`:336`)让 action 读写黑板(`ctx.get`/`ctx.update`),再用 `_dict_delta`(`:1280`)只交回变化——这正是 mvp1 LE1 要砍掉的"action 写黑板"。action 与 tool 是 `actions.py` 里**两套独立注册表**(`ActionDef`/`ActionRegistry` vs `ToolDef`/`ToolRegistry`)。StateMapper(`runtime/state_mapper.py:37`)做 io slice/merge,失败报 `[F-v3-runtime-state-mapping-failed]`。

## UI/UX
N/A。

## 前端逻辑
N/A。

## 后端功能

### 1. StateMapper:io 切片 / 回写(state_mapper.py)
`StateMapper`(`runtime/state_mapper.py:37`)按 phase 的 `io.inputs`/`io.outputs` 从黑板 slice 输入、merge 输出;违规(required 缺失、越界 key)报 `[F-v3-runtime-state-mapping-failed]`(`:142/:208/:225`)。

### 2. LOGIC 执行:可变 Context facade(现状,mvp1 要砍)
`_build_logic_node`(`graph_assembler.py:325`):
1. `output_schema_keys = _schema_output_keys(phase_ast.io.outputs)`(`:331`)。
2. `ctx = Context(data, phase_id=..., run_id=...)`(`:336`)——**可变 facade**,action 可 `ctx.get("x")` / `ctx.update(y=...)` 改黑板。
3. 调 action;`_dict_delta(before, after)`(`:1280`)算出 action 经 Context 改的变化。
4. 若 action 还 `return dict`,校验 output key ⊂ io.outputs 后并入。
> **现状即 mvp1 反模式**:action 通过可变 Context **写黑板**(`ctx.update`);mvp1 LE1 要砍成**纯返回 dict、只读 inputs**(见 alignment §2/§5)。

### 3. action vs tool:两套独立注册表(actions.py)
- `ActionDef`(`actions.py:18`)/ `ActionRegistry`(`:25`,`for_phase` `:44`)——LOGIC 的 action(引擎调,确定性)。
- `ToolDef`(`:49`)/ `ToolRegistry`(`:60`,`_structured_tool` `:76`)——AGENT 的 tool(LLM 调,`StructuredTool`)。
- **两套独立、不互通、无桥**(mvp1 决定**不统一** capability,见 `04-tools` TL2)。

### 4. SUBGRAPH + io_manager
SUBGRAPH 节点 `_build_subgraph_node`(`:363`,装配归 `03-assemble`)递归调 child graph,父 data 启动子图、回 delta。io 落盘经 `io/manager.py`。

## API
- `StateMapper`(`state_mapper.py:37`)——slice/merge。
- `_build_logic_node(...)`(`graph_assembler.py:325`)——LOGIC 节点闭包(装配归 `03-assemble`,执行范式归本域)。
- `ActionRegistry.for_phase(phase_id)`(`actions.py:44`)/ `ToolRegistry.for_phase`(`:71`)。

## Data Model / State
blackboard = `WorkflowState.data`(`data-contracts`);io 经 StateMapper slice/merge。LOGIC 现经可变 Context 改 data(mvp1 改纯返回)。

## 当前边界(这个模块现在不是什么)
- **LOGIC 现在能写黑板**:可变 Context facade(`:336`),mvp1 要砍成纯返回。
- **action/tool 不统一**:两套注册表(spec 已固定 Action≠Tool)。
- **代码里术语混叫**:历史处把 action 叫 "tool"(死簇,待清)。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标(LE1-3) |
|---|---|---|
| action 写黑板 | 可变 `Context.update`(`:336`) | 纯返回 dict、只读 inputs(砍 set/update/delete) |
| action 编排 | 现有 action 跑 `run_skill`/碰 FS | 硬禁(扩 purity 扫描器,归 `01-compile`) |
| 黑板对象 | 塞 `BatchAccumulator` 等非序列化对象 | `iterate.accumulate` + 序列化数据 |
| 死簇 | `code_phase_node`/`phase_executor` | 删(live 用 `_build_logic_node`) |

> **验"是否按 mvp1 改了"**:① action 是否变成 `def <name>(inputs)->dict` 纯返回(无 Context mutation);② action 里 `run_skill`/FS 是否触发编译期 purity FATAL;③ 黑板是否只剩可序列化数据;④ StateMapper required 缺失/越界 key 是否报 `[F-v3-runtime-state-mapping-failed]`。

## 读代码主路径提示
StateMapper `state_mapper.py:37` → LOGIC `_build_logic_node`(`graph_assembler.py:325`,Context facade `:336`)→ action/tool 注册表 `actions.py:18/49` → SUBGRAPH `:363`。

## 交叉引用(链接, 不复制)
mvp1-alignment(目标 + LE1-3)· `04-tools`(action/tool,双向)· `02-iterate` · `03-checkpoint` · `05-run-inner`(AGENT 委派)· `data-contracts`(blackboard)· mvp0/`12-compile-runtime-flow`
