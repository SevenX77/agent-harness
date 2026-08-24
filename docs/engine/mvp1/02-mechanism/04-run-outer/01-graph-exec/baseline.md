---
module: 02-mechanism/04-run-outer/01-graph-exec
doc: baseline
status: drafted（现状对齐 WS-E1 Step5 + WS-E1-io + WS-E4 runtime 后代码；LOGIC runtime 已纯返回 dict;声明式 iterate 已接入 phase/graph 外层 runtime;phase input dispatch、loop reduce、file input injection 已发 runtime edge events;action/tool 两套注册表;子图父子 io 编译期已不再比较,边界归运行期 StateMapper;声明式 file input lazy 注入与 file/artifact 输出落盘已接入）
binds_alignment: ./mvp1-alignment.md
binds_code: core/graph_assembler.py（_build_logic_node, _wrap_phase_runtime_node, _wrap_declared_input_files, _GraphIterateRuntime, _build_subgraph_node）· runtime/state_mapper.py:37 · core/actions.py（18/49）· core/loader.py（_validate_subgraph_io_contracts, _validate_iterate_compile_contracts）· core/runner.py（_save_v030_declared_file_outputs, _context_with_framework_output_sources）· tools/builtin/read_file.py（read_workspace_text_file）· io/manager.py:108（save_outputs）· io/storage.py:149（save_artifact）
---

# 01-graph-exec — Baseline(当下代码实现逻辑)

> **现状一句话**:LOGIC 节点 `_build_logic_node` 已不再创建可变 `Context` facade;每个 action 收到 `{**before, **updates}` plain dict,只有 action 显式返回的 dict 会通过 `_validate_logic_update_keys` 校验后写回。WS-E1 Step4 已把声明式 iterate 接到 graph/phase 外层:phase-level iterate 包在 `PhaseWrapper(StateMapper)` 外侧聚合/累积结果,graph-level iterate 包在 compiled graph 外侧执行整图 batch/loop。WS-E4 runtime 后,phase input slice/dispatch 进入节点前会发 `InputDispatchEvent`,声明式 loop accumulate merge 写回后会发 `BlackboardReduceEvent`。SUBGRAPH 父子 io 的编译期比较已全部取消:WS-E1 Step5 先放宽 inputs 镜像校验,2026-06-20 commit `cad7dbc0` 再移除 outputs 的 1:1 闸(`[F-v3-subgraph-io-mismatch]` 保留 registry 条目但**无发出点**);父 `SUBGRAPH.md` 声明的 outputs 边界改由运行期 `StateMapper` 按声明 schema 守。2026-07-05 runtime_config 收敛后,phase import binding 接成目标 phase 执行前 lazy 注入普通 blackboard,成功注入时发 `InputFileInjectedEvent`,runtime_config artifacts 与 `business_data_md` 原文保存接到 runner/io。action 与 tool 仍是 `actions.py` 里**两套独立注册表**。StateMapper(`runtime/state_mapper.py:37`)做 io slice/merge,失败报 `[F-v3-runtime-state-mapping-failed]`。

## UI/UX
N/A。

## 前端逻辑
N/A。

## 后端功能

### 1. StateMapper:io 切片 / 回写(state_mapper.py)
`StateMapper`(`runtime/state_mapper.py:37`)按 phase 的 `io.inputs`/`io.outputs` 从黑板 slice 输入、merge 输出。
- **slice 输入**(`build_phase_input:44` → `filter_runtime_inputs:25`):只按 `io.inputs.properties` 过滤,**现状不校验 `required` 缺失**——缺的字段静默丢弃、不报错(`required` 在 schema 里根本没被读)。
- **input dispatch 可观测性**(WS-E4 runtime):`graph_assembler.py:_wrap_phase_runtime_node` 在调用 `PhaseWrapper(StateMapper)` 前发 `InputDispatchEvent`,按 phase `io.inputs.properties` 从 business blackboard 计算 `dispatched_keys`/`changed_keys`,携带 dispatch 时的 `blackboard_snapshot`。普通 phase `branch_index=None`;iterate/graph iterate 分支由 runtime contextvar 提供 1-based `branch_index`。
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

### 3. 声明式 iterate 对 graph-exec 的接线影响(WS-E1 Step4 已落)
Step4 没把循环塞回 action,而是在 graph execution 外层接声明式 runtime:
- phase-level iterate:`_wrap_phase_runtime_node` 先构造 `PhaseWrapper(StateMapper, lifecycle=...).wrap(node)`(阶段的 `phase_start`/`phase_end` 由注入的 `_PhaseEventLifecycle` 从 wrapper **内部**发,见 observability OB13),再接 runtime_config import binding 注入,最后由 `_build_iterate_wrapped_phase` 包成 batch/loop。这样每轮 phase body 仍走正常 io slice/merge;若 runtime_config 声明该 phase 的 import binding,文件内容会在目标 phase 执行前注入普通 blackboard,再被 `PhaseWrapper` 按 `io.inputs` 切片给 action。
- node batch/range:`_build_batch_iterate_phase` 按 `iterate.over` 解析 list、按 `item_var` 注入每项、按 phase outputs 聚合。
- node loop:`_build_loop_iterate_phase` 串行执行,每轮把 `accumulate.var` 作为普通 business input 喂给 action,最终只写回 accumulator。
- graph-level iterate:`assemble_graph` 在 `compiled.manifest.iterate` 存在时,把 compiled LangGraph 包成 `_GraphIterateRuntime`;其 `invoke` 内部执行整图 batch 或整图 loop。
- legacy `batch:` 仍兼容,但通过 `_build_legacy_batch_wrapped_phase` 接到新的 batch runtime。
- WS-E4 runtime 后,phase/graph iterate 每轮设置 1-based branch contextvar,让各轮 `InputDispatchEvent` 可区分分支;node-level loop 与 graph-level loop 在声明式 accumulator merge 后发 `BlackboardReduceEvent`,携带 reducer 名、changed keys 与 merge 后 blackboard snapshot。

### 4. action vs tool:两套独立注册表(actions.py)
- `ActionDef`(`actions.py:18`)/ `ActionRegistry`(`:25`,`for_phase` `:44`)——LOGIC 的 action(引擎调,确定性)。
- `ToolDef`(`:49`)/ `ToolRegistry`(`:60`,`_structured_tool` `:76`)——AGENT 的 tool(LLM 调,`StructuredTool`)。
- **两套独立、不互通、无桥**(mvp1 决定**不统一** capability,见 `04-tools` TL2)。

### 5. SUBGRAPH:父子 io 编译期不再比较,边界改由运行期 StateMapper 守(loader)
SUBGRAPH 节点 `_build_subgraph_node`(`graph_assembler.py:1589`,装配归 `03-assemble`)递归调 child graph,父 data 启动子图、回 delta。
- **父子 io 编译期完全不比较**:`loader.py:_validate_subgraph_io_contracts`(`:996`,`:397` 调用)只做一件事——递归编译 child graph,使"子图指向一个编译不过的 child"仍在父图编译期失败(路径解析 + child 有效性)。它既不比较父 `SUBGRAPH.md io.inputs` 与子 `GRAPH.md io.inputs`,也不比较双方的 `io.outputs`;父子字段集合、`required` 或同名字段 schema 不一致都不会在 loader 层 fatal。
- **outputs 1:1 编译闸已于 2026-06-20 移除**(commit `cad7dbc0`,PM 授权):理由是子图与普通节点同构——按自己声明的 `io.inputs` 从父黑板切片、把声明的 `io.outputs` 合并回父黑板,这条边界由运行期 `StateMapper` 守,不需要编译期再要求父子 schema 相等;旧闸与该设计矛盾,并且卡死了 Studio 里逐节点编辑子图 io。权威设计见 `01-contract/02-skill-syntax/mvp1-alignment.md` §3.4(“父图和子图 IO 不需要字段全集一一相等”)与 §4 把“父子图 IO 1:1 强绑定”列为 drift。
- **运行期边界**:`runtime/state_mapper.py:_validate_phase_updates_against_schema`(`:318`)按该 phase 声明的 outputs schema 过滤写回;子图写了未声明字段时以受控的 `[F-v3-runtime-state-mapping-failed]` 失败(`:328` "phase wrote undeclared keys"),不是崩溃。
- **`[F-v3-subgraph-io-mismatch]` 保留在 registry,引擎源码无发出点**:保留是为了维持 round28 registry↔owner 双射与码表计数(`core/error_registry.py:95`,该行上方注释记录了这条保留理由)。同域的 `[F-v3-subgraph-io-schema-incompatible]`(`:96`)自 round-17 建表起就只有 registry 条目、从未有过发出点。

### 6. io.outputs 落盘:file / artifact(io/manager + io/storage + runner)
`IOManager.save_outputs`(`io/manager.py:108`,storage-agnostic)按 `output_spec.target`(默认 `"file"`)分发:
- **artifact / artifact_manager**:有注入 `artifact_saver` 时交给调用方;否则若有 `storage_manager`,回退 `StorageManager.save_artifact`(`io/storage.py:149`,写 `<run_dir>/phases/<phase>/<name>` 或 `<run_dir>/<name>`,str/bytes 原样,其他 JSON,并发出 `ArtifactSavedEvent`);若只有 `output_dir`,按声明 `path`/`filename` 写到 `output_dir` 下。
- **file**:`path`/`filename` 优先,否则 path-less 默认 `output_dir/{name}.json`;`{context.key}` 占位由 `_resolve_path_template` 解析。带 `output_dir` 时会校验最终路径不能逃逸 `output_dir`。
- **artifact 路径边界**:`StorageManager._artifact_path_under` 拒绝空名、绝对路径和 `..` 逃逸 run/phase 目录。
- **root output 保存**:`runner._save_v030_declared_file_outputs` 会扫描根 `GRAPH.md io.outputs.properties`,把 `target in {"file","artifact"}` 的声明交给 `IOManager`,默认写到 `<workspace_dir>/runs/<run_id>/artifacts`。
- **markdown 原文**:`IOManager._resolve_output_data` 支持 `source: business_data_md`;若未显式 source 但 `content_type: text/markdown` 且 context 中有 `business_data_md`,也保存 markdown 原文。`runner._context_with_framework_output_sources` 从 `flow.finish_task_result.business_data_md` 把该值带入输出上下文。

### 7. 声明式 file input lazy 注入(graph_assembler + read_file)
`_wrap_declared_input_files` 在 phase runtime wrapper 中识别 `io.inputs.properties.<field>.source == "file"`:
- `path` 缺失会在装配时抛 `[F-v3-runtime-state-mapping-failed]`。
- 运行到目标 phase 时,从 `flow.persistent_storage_config["workspace_dir"]` 解析相对路径,通过 `read_workspace_text_file` 读 UTF-8 文本;注入位置是普通 `WorkflowState.data`,因此仍由后续 `PhaseWrapper(StateMapper)` 按该 phase 的 `io.inputs` 切片消费。
- 成功注入后发 `InputFileInjectedEvent`,包含 `from_phase`、`to_phase`、`changed_keys`、`blackboard_snapshot`、`file_ref`、`target_field`。
- 绝对路径、`..` 逃逸、缺失文件、目录、非普通文件、超 200KB、二进制/非 UTF-8 文本都会稳定转成 `[F-v3-runtime-state-mapping-failed]`。

## API
- `StateMapper`(`state_mapper.py:37`)——slice/merge。
- `_build_logic_node(...)`(`graph_assembler.py:325`)——LOGIC 节点闭包(装配归 `03-assemble`,执行范式归本域)。
- `_runtime_input_file_specs(...)` / `read_workspace_text_file(...)`——runtime_config import binding 输入在目标 phase 前 lazy 注入普通 blackboard。
- `ActionRegistry.for_phase(phase_id)`(`actions.py:44`)/ `ToolRegistry.for_phase`(`:71`)。
- `IOManager.save_outputs(...)` / `StorageManager.save_artifact(...)` / `runner._save_v030_declared_file_outputs(...)`——声明式 `target=file/artifact` 输出保存。

## Data Model / State
blackboard = `WorkflowState.data`(`data-contracts`);io 经 StateMapper slice/merge。LOGIC 现只把 action 返回 dict 写回 data,不再经可变 Context mutation diff 写回。声明式 file input 的内容同样写入普通 `WorkflowState.data` 字段,再被目标 phase 的 `io.inputs` 切片消费。运行期工作区根来自 `FrameworkState.persistent_storage_config["workspace_dir"]`。

## 当前边界(这个模块现在不是什么)
- **LOGIC runtime 已纯返回**:action 收到 plain dict,只显式返回 dict 写回;loader 对 action 第一参数名仍要求 `context/ctx`,这是语法层 drift,见 `01-contract/02-skill-syntax/baseline.md`。
- **iterate runtime 已接入 graph-exec**:节点级/图级声明式循环 live;WS-E4 runtime edge trace 已覆盖 input dispatch 与 loop reduce;checkpoint delta/compaction、LangGraph `Send` 专门接线仍不在本 baseline 当前实现内。
- **action/tool 不统一**:两套注册表(spec 已固定 Action≠Tool)。
- **代码里术语混叫**:历史处把 action 叫 "tool"(死簇,待清)。
- **子图 io 现状**:编译期不做任何父子 io 比较(`loader.py:996` 只递归编译 child graph);父 `SUBGRAPH.md` 声明的 outputs 由运行期 `StateMapper` 按声明 schema 守边界,越界写回记 `[F-v3-runtime-state-mapping-failed]`。`[F-v3-subgraph-io-mismatch]` 仅保留 registry 条目(维持 round28 双射与计数),引擎源码无发出点。
- **声明式 file input 依赖 runner 注入 workspace_dir**:经 `run_skill` / v0.3 runner 路径会写入 `persistent_storage_config.workspace_dir`;若直接拼状态调用 graph 且缺该配置,文件注入会以 `[F-v3-runtime-state-mapping-failed]` 失败。

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
| 声明式 iterate | phase-level batch/range/loop 与 graph-level batch/loop 已 live;input dispatch branch trace 与 loop reduce trace 已落;checkpoint 深集成未落 | iterate.accumulate + 序列化数据;checkpoint 深接线分后续 WS |
| 边操作 observability | `InputDispatchEvent` 在 phase 执行前发出;`BlackboardReduceEvent` 在声明式 loop accumulate merge 后发出;`InputFileInjectedEvent` 仍无 runtime path | 文件 lazy 注入等 WS-E1-io 落地后补齐 |
| 死簇 | `code_phase_node`/`phase_executor` | 删(live 用 `_build_logic_node`) |
| StateMapper required 校验 | slice **不校验** required(只过滤 properties、缺失静默丢)(`filter_runtime_inputs:25`) | required 缺失报 `[F-v3-runtime-state-mapping-failed]`(alignment §3/§6) |
| 子图 io 校验 | inputs 已放宽(不再镜像比较);outputs 仍严格 1:1(`loader.py:528/553`) | 已对齐 E1:inputs 从黑板切片、outputs 保留严校 |
| 文件导入→黑板 | runtime_config phase import binding 已在目标 phase 前 lazy 注入普通 blackboard;路径受 `workspace_dir` 约束,成功发 `InputFileInjectedEvent`,失败报 `[F-v3-runtime-state-mapping-failed]` | 已对齐 E2:跑到目标节点才 lazy 注入 |
| io.outputs md artifact | `target=file/artifact` 根输出由 runner 交给 `IOManager`;markdown artifact 可取 `business_data_md` 原文;file/artifact 路径均有逃逸防护 | 已对齐 E3:md 取 `business_data_md`、不 json→md 回转 |

> **验"是否按 mvp1 改了"**:① LOGIC runtime 是否只把 action 返回 dict 写回、Context mutation 不再隐式改黑板;② action 里 `run_skill`/FS/`sys.path`/动态 import 是否触发编译期 purity FATAL;③ 循环/累积是否由声明式 iterate runtime 执行,而不是 action 手写循环;④ StateMapper required 缺失/越界 key 是否报 `[F-v3-runtime-state-mapping-failed]`。

## 读代码主路径提示
StateMapper `state_mapper.py:37` → runtime edge dispatch `_wrap_phase_runtime_node` → LOGIC `_build_logic_node`(plain dict action_ctx)→ phase-level iterate `_build_iterate_wrapped_phase` / `_build_loop_iterate_phase`(reduce emit) → graph-level iterate `_GraphIterateRuntime` → action/tool 注册表 `actions.py:18/49` → SUBGRAPH `_build_subgraph_node`。

## 交叉引用(链接, 不复制)
mvp1-alignment（目标 + LE1-3,双向）· `04-tools`(action/tool,双向)· `02-iterate` · `03-checkpoint` · `05-run-inner`(AGENT 委派)· `data-contracts`(blackboard)
