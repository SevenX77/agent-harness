# Section 1: Overview

Graph-Agent State Management Optimization 落实 R0 决策 A-D：以严格 shallow reducer 解决 fan-out 并发写冲突，以 actions 返回 key 契约阻断无声明黑板覆写，并只复原 `batch-analysis` 作为 reference skill，不为旧行为留 feature flag/backdoor。执行基准为 V2.1 Hard Cutover commit `a53e72c`，spec 落盘分支为 `feat/state-mgmt-optimization-spec`。总工时方向 32-46 工时：Phase A=S(8-10h)、Phase B=M(10-14h)、Phase C=M(10-14h)、Phase D=S(4-8h)。Critical Path：T1.1 → T1.2 → T2.1 → T2.2 → T2.3 → T3.1 → T3.2。

# Section 2: 任务总表

| ID | Tier | Phase | 任务名 | 涉及文件 | DoD | 工时 | 依赖 |
|---|---|---|---|---|---|---|---|
| T1.1 | Tier 1 | A | 实现 `shallow_dict_merge` reducer | `packages/graph-agent/src/graph_agent/runtime/state.py:14`; `packages/graph-agent/tests/runtime/test_state_reducer.py` | `data` 改为 `Annotated[dict[str, Any], shallow_dict_merge]`; 单测覆盖无交集合并、`None` 输入、冲突抛 `GraphAgentFatalError` 且含 `[F-v21-state-conflict]` + key; `pytest packages/graph-agent/tests/runtime/test_state_reducer.py -q` 通过 | S | 无 |
| T1.2 | Tier 1 | A | reducer 接入 LangGraph fan-out 执行 | `packages/graph-agent/tests/core/test_v21_graph_assembly.py:36-67`; `packages/graph-agent/src/graph_agent/core/graph_assembler.py:64-75` | 新增 fan-out fixture：`branch_a`/`branch_b` 写不同 key 成功合并；冲突 key 执行期 FATAL; `pytest packages/graph-agent/tests/core/test_v21_graph_assembly.py -q` 通过 | S | T1.1 |
| T2.1 | Tier 2 | B | 提取 `outputs.schema.json` 顶层声明 key | `packages/graph-agent/src/graph_agent/core/loader.py`; `packages/graph-agent/src/graph_agent/core/graph_assembler.py:183-189`; `packages/graph-agent/tests/core/test_v21_actions_keys.py` | loader/compiled metadata 可取得 outputs schema `properties` keys; 缺/非 object schema 按现有 IO FATAL 语义处理; 单测断言 declared keys 与 fixture schema 一致 | S | T1.1 |
| T2.2 | Tier 2 | B | LOGIC Action 返回 key 契约校验 | `packages/graph-agent/src/graph_agent/core/graph_assembler.py:109-115`; `packages/graph-agent/tests/core/test_v21_actions_keys.py` | `_build_logic_node` 包装 action 返回 dict；未声明 key 抛 `[F-v21-actions-keys]`，错误含 action file:line 与 key；声明 key 正常写入；`pytest packages/graph-agent/tests/core/test_v21_actions_keys.py -q` 通过 | M | T2.1 |
| T2.3 | Tier 2 | C | Canvas fan-out / fan-in fixture 验收 | `packages/graph-agent/tests/core/test_v21_graph_assembly_fanout.py`; `packages/graph-agent/tests/fixtures/fake_canvas_fanout/` | fake Canvas GRAPH 覆盖一出多、多入汇聚；执行断言 `{"a_out":1,"b_out":2}` 合并成功；冲突 fixture 抛 `[F-v21-state-conflict]`; `pytest packages/graph-agent/tests/core/test_v21_graph_assembly_fanout.py -q` 通过 | M | T1.2/T2.2 |
| T3.1 | Tier 3 | D | `batch-analysis` fan-out 复原 | `skills/batch-analysis/GRAPH.md:10-14`; `packages/graph-agent/tests/e2e/test_batch_analysis_v21.py`; `packages/graph-agent/tests/core/test_v21_graph_assembly_fanout.py` | 只改 GRAPH depends_on：三路从 `prepare` fan-out，并入 `assemble`; 断言多入 edge 存在；运行时三路各自 namespace 合并不冲突；不要求业务级输出语义正确 | S | T2.3 |
| T3.2 | Tier 3 | D | 反例 corpus 与 all-skills smoke 调整 | `packages/graph-agent/tests/e2e/test_v21_all_skills_smoke.py:23-48`; `skills/text-segmentation/phases/setup/actions/prepare_chapter.py:13-18`; `skills/event-extraction/phases/setup/actions/format_segments_for_prompt.py:17-22` | `text-segmentation`、`event-extraction` 触发 `[F-v21-actions-keys]` 标 `xfail(strict=True)` 并备注“原型阶段 broken skill, 反例 corpus”；naturally-compliant/reference skill smoke 继续编译装配 | S | T2.2/T3.1 |

# Section 3: 各 task 详细

## T1.1 — 实现 `shallow_dict_merge` reducer

**背景**: 对齐 requirements R1.1/R2.2/R3.1 与 design §2。当前 `packages/graph-agent/src/graph_agent/runtime/state.py:14` 为裸 `data: dict[str, Any]`，LangGraph fan-out 下等同 LWW，存在整字典覆盖风险。

**改动文件 + file:line**: `state.py:5` 已导入 `Annotated, Any, TypedDict`; `state.py:14` 注入 reducer；新增 `packages/graph-agent/tests/runtime/test_state_reducer.py`。

**实施步骤**: 1. test-first 写 reducer 单测：left/right 无交集、left/right 为 `None`、同 key 冲突。2. 在 `state.py` 新增 `shallow_dict_merge`，冲突 raise `GraphAgentFatalError("[F-v21-state-conflict] ...")`。3. 将 `BlackboardState.data` 改为 `Annotated[dict[str, Any], shallow_dict_merge]`。4. 跑 `pytest packages/graph-agent/tests/runtime/test_state_reducer.py -q`。

**验收标准**: R3.1 中冲突 fixture 能 catch；错误包含 key；复杂度保持 O(K)，不做 deep merge。

**风险 + Fallback**: 若 LangGraph reducer 对初始 `None`/空 dict 传参不稳定，fallback 只在 reducer 内 normalize，不改变合并策略；禁止 LWW/feature flag。

## T1.2 — reducer 接入 LangGraph fan-out 执行

**背景**: 对齐 R1.1/R1.4/R3.1 与 design §5。`graph_assembler.py:64-75` 已按 `depends_on` 建边，需验证 reducer 在真实 fan-out 中生效。

**改动文件 + file:line**: 复用 `packages/graph-agent/tests/core/test_v21_graph_assembly.py:36-67` 的 `_base/_logic` fixture 或新增局部 helper；装配边逻辑位于 `graph_assembler.py:64-75`。

**实施步骤**: 1. test-first 构造 `start → branch_a/branch_b → merge`，两个 LOGIC action 分别 return `{"a_out":1}`/`{"b_out":2}`。2. 增加冲突版本：两个分支 return `{"shared":...}`。3. 执行 graph.invoke 验证合并成功与冲突 FATAL。4. 跑 `pytest packages/graph-agent/tests/core/test_v21_graph_assembly.py -q`。

**验收标准**: R3.1 fan-out conflict fixture 抛 `[F-v21-state-conflict]`; R1.4 Canvas 多入/多出拓扑至少一条执行链路通过。

**风险 + Fallback**: 若同测试文件膨胀，fallback 将 fixture 拆到 T2.3 专用文件，但不改变生产代码。

## T2.1 — 提取 `outputs.schema.json` 顶层声明 key

**背景**: 对齐 R1.2 与 design §3。action key 校验需要当前 skill outputs schema 的 `properties` 作为允许集合。

**改动文件 + file:line**: `loader.py` 负责填充 `compiled.raw["io"]["outputs"]`; `graph_assembler.py:183-189` 现已读取 terminal output schema 给 finish_task，可复用 schema 获取路径；新增 `test_v21_actions_keys.py`。

**实施步骤**: 1. test-first 生成 fake skill `io/outputs.json` 含 `properties: {"a_out":{}}`。2. 在编译产物或 graph assembler helper 中提取 declared keys。3. 非 object/missing properties 走空集合或现有 IO schema FATAL，行为写清单测。4. 跑 `pytest packages/graph-agent/tests/core/test_v21_actions_keys.py -q`。

**验收标准**: declared key 集合与 schema 一致；不引入 YAML/XML IO 回塞；为 T2.2 提供稳定输入。

**风险 + Fallback**: 若 compiled dataclass 不宜扩字段，fallback 在 `graph_assembler.py` 内从 `compiled.raw["io"]["outputs"]` 即时提取，避免扩大 loader API。

## T2.2 — LOGIC Action 返回 key 契约校验

**背景**: 对齐 R1.2/R3.1 与 design §3/§6。当前 `graph_assembler.py:109-115` 中 LOGIC action 返回 dict 后直接 `data.update(result)`，未声明 key 会静默污染黑板。

**改动文件 + file:line**: `graph_assembler.py:107` 可取得 action callable；`graph_assembler.py:112-115` 包装返回结果；action 文件路径可从 ActionRegistry 元数据或 loader discovery 侧补充。

**实施步骤**: 1. test-first 写 fake LOGIC action `return {"undeclared_key":"val"}`，outputs schema 不声明该 key。2. 实现 `_validate_logic_action_keys`，命中抛 `GraphAgentFatalError("[F-v21-actions-keys] ... file:line ...")`。3. 写 declared key 正例。4. 跑 `pytest packages/graph-agent/tests/core/test_v21_actions_keys.py -q`。

**验收标准**: R3.1 undeclared key fixture 在 parser/assembly/runtime 首次执行前后任一可控阶段被 FATAL catch；错误含 key + file:line。

**风险 + Fallback**: Python AST 无法完美推导动态 dict；fallback 采用运行时首跑校验，但错误仍必须指向 action source file:line。

## T2.3 — Canvas fan-out / fan-in fixture 验收

**背景**: 对齐 R1.4/R3.1 与 design §5。Canvas-v1 依赖 `depends_on` 作为多入多出唯一真相，Engine 侧需要最小 fixture 固化行为。

**改动文件 + file:line**: 新增 `packages/graph-agent/tests/core/test_v21_graph_assembly_fanout.py`; 可复用 `test_v21_graph_assembly.py:31-67` helper 形态；必要时新增 `packages/graph-agent/tests/fixtures/fake_canvas_fanout/`。

**实施步骤**: 1. test-first 建 `start`, `branch_a`, `branch_b`, `merge` 四 phase。2. 正例断言汇聚后 data 同时含 `a_out` 和 `b_out`。3. 反例把 branch_b 改为返回 `a_out`，断言 `[F-v21-state-conflict]`。4. 跑 `pytest packages/graph-agent/tests/core/test_v21_graph_assembly_fanout.py -q`。

**验收标准**: R1.4 编译成功且执行触发 R1.1 reducer；R3.1 冲突与非冲突路径均覆盖。

**风险 + Fallback**: 若真实 LangGraph 并发调度顺序不稳定，assert 只检查集合语义和 FATAL code，不依赖分支执行顺序。

## T3.1 — `batch-analysis` fan-out 复原

**背景**: 对齐 R1.3/R3.2 与 design §4/§8。当前 `skills/batch-analysis/GRAPH.md:10-14` 是串行链，需恢复 `prepare` 后三路 fan-out，并入 `assemble`。

**改动文件 + file:line**: `skills/batch-analysis/GRAPH.md:12-14` 改 depends_on；`tests/e2e/test_batch_analysis_v21.py` 增拓扑断言；可在 fanout 测试中断言 `entity_and_characters` / `parallel_analysis` / `continuity` 三路进入 `assemble`。

**实施步骤**: 1. test-first 断言当前 topology 目标形态，先失败。2. 修改 GRAPH.md：`parallel_analysis`/`continuity` depends_on `prepare`; `assemble` depends_on 三路。3. 跑 batch compile/assemble + reducer 合并测试。4. 命令：`pytest packages/graph-agent/tests/e2e/test_batch_analysis_v21.py packages/graph-agent/tests/core/test_v21_graph_assembly_fanout.py -q`。

**验收标准**: R3.2 reference 改对：多入 edge 存在，三路各自 namespace 合并正确；不强求业务级输出语义正确。

**风险 + Fallback**: 若 batch action 返回 key 未声明而 FATAL，按 D 决策修 batch skill 自身 schema/namespace；不改 reducer 宽松化。

## T3.2 — 反例 corpus 与 all-skills smoke 调整

**背景**: 对齐 R3.3 与 design §8。`text-segmentation`、`event-extraction` 是负例 corpus，不应为了整体通过而修掉；它们触发 FATAL 是验收内容。

**改动文件 + file:line**: `test_v21_all_skills_smoke.py:23-48` 当前动态遍历所有 `GRAPH.md`; `text-segmentation` 违规点为 `prepare_chapter.py:13-18`; `event-extraction` 违规点为 `format_segments_for_prompt.py:17-22`。

**实施步骤**: 1. 在 all-skills smoke 中识别 negative-corpus skill id。2. 对负例参数化用例加 `xfail(strict=True, reason="原型阶段 broken skill, 反例 corpus")`，并断言 FATAL code 是 `[F-v21-actions-keys]`。3. 保持 naturally-compliant/reference skill 的 compile/assemble 正例。4. 跑 `pytest packages/graph-agent/tests/e2e/test_v21_all_skills_smoke.py -q`。

**验收标准**: R3.3 反例 FATAL 是预期；不要求 all-skills 全部通过；reference `batch-analysis` 不应被 xfail。

**风险 + Fallback**: 若负例后续被业务 spec 修复，应删除 xfail 并更新本 spec；本轮不主动修复 text/event skill。

# Section 4: 测试矩阵

| 测试文件 | 测试函数命名 | Assertion 类型 | 跑通命令 |
|---|---|---|---|
| `packages/graph-agent/tests/runtime/test_state_reducer.py` | `test_shallow_dict_merge_disjoint_keys`, `test_shallow_dict_merge_none_inputs`, `test_shallow_dict_merge_conflict_fatal` | dict equality; `pytest.raises(GraphAgentFatalError, match="[F-v21-state-conflict].*key")`; O(K) 不递归 | `pytest packages/graph-agent/tests/runtime/test_state_reducer.py -q` |
| `packages/graph-agent/tests/core/test_v21_graph_assembly.py` | `test_fanout_disjoint_data_keys_merge`, `test_fanout_same_data_key_conflict_fatal` | graph.invoke 后 data 包含双 key; conflict FATAL code | `pytest packages/graph-agent/tests/core/test_v21_graph_assembly.py -q` |
| `packages/graph-agent/tests/core/test_v21_actions_keys.py` | `test_logic_action_return_declared_key_ok`, `test_logic_action_return_undeclared_key_fatal`, `test_logic_action_key_error_reports_file_line` | declared key 正常; undeclared key `[F-v21-actions-keys]`; message 含 file:line | `pytest packages/graph-agent/tests/core/test_v21_actions_keys.py -q` |
| `packages/graph-agent/tests/core/test_v21_graph_assembly_fanout.py` | `test_canvas_fanout_fanin_disjoint_merge`, `test_canvas_fanout_fanin_conflict_fatal`, `test_batch_analysis_reference_edges` | Canvas 一出多/多入编译执行; conflict FATAL; batch 多入 edge 集合 | `pytest packages/graph-agent/tests/core/test_v21_graph_assembly_fanout.py -q` |
| `packages/graph-agent/tests/e2e/test_batch_analysis_v21.py` | `test_batch_analysis_v21_compile_and_assemble`, `test_batch_analysis_v21_reference_fanout_topology` | manifest depends_on 精确匹配; assembled graph 非空; 三路 namespace 合并不冲突 | `pytest packages/graph-agent/tests/e2e/test_batch_analysis_v21.py -q` |
| `packages/graph-agent/tests/e2e/test_v21_all_skills_smoke.py` | `test_v21_all_skills_compile_assemble_and_cache_hit` | compliant/reference skill 正例; negative corpus `xfail(strict=True)` 且 FATAL code 为 `[F-v21-actions-keys]`; cache hit ≤200ms 保持 | `pytest packages/graph-agent/tests/e2e/test_v21_all_skills_smoke.py -q` |
| V2.1 scope 聚合 | existing V2.1 tests + above | reducer/actions/fanout 不破坏 V2.1 基础契约；允许 R3.3 反例 xfail | `pytest packages/graph-agent/tests/runtime/test_state_reducer.py packages/graph-agent/tests/core/test_v21_actions_keys.py packages/graph-agent/tests/core/test_v21_graph_assembly_fanout.py packages/graph-agent/tests/e2e/test_batch_analysis_v21.py packages/graph-agent/tests/e2e/test_v21_all_skills_smoke.py -q` |

# Section 5: Critical Path + 并行机会

串行 Critical Path 为 7 步：T1.1 reducer 单元行为 → T1.2 LangGraph fan-out 接入 → T2.1 outputs schema key 提取 → T2.2 action 返回 key FATAL → T2.3 Canvas fan-out/fan-in fixture → T3.1 `batch-analysis` reference fan-out 复原 → T3.2 反例 corpus xfail/smoke 调整。

并行机会：T1.1 完成后，T1.2 fan-out 执行测试与 T2.1 schema key 提取可并行；T2.2 完成后，T2.3 Canvas fixture 与 T3.1 的 batch topology 断言可并行起步，但 T3.1 真正落地必须等 T2.3 证明 reducer 行为；T3.2 可在 T2.2 FATAL code 稳定后提前准备 xfail 标记，最终等 T3.1 确认 reference skill 不属于 xfail。

# Section 6: 完成标准 (Final DoD)

- R3.1 对齐：fan-out 冲突 fixture 抛 `[F-v21-state-conflict]`，错误含 key 与 branch/phase 提示；undeclared action key fixture 抛 `[F-v21-actions-keys]`，错误含 action file:line。
- R3.2 对齐：`batch-analysis` GRAPH 复原为 `prepare` 后三路 fan-out、`assemble` 多入；装配产出多入 edge；运行时三路各自 namespace 后可被 reducer 正确 shallow merge；不强求业务级输出语义正确。
- R3.3 对齐：`text-segmentation` 与 `event-extraction` 触发 FATAL 是预期，不修复；`test_v21_all_skills_smoke.py` 对这些反例加 `xfail(strict=True)`，备注“原型阶段 broken skill, 反例 corpus”。
- Design §7 对齐：Phase A-D 全部完成，且每个 phase 有对应测试文件和 pytest 命令。
- PR 合并前 checklist：`pytest packages/graph-agent/tests/runtime/test_state_reducer.py packages/graph-agent/tests/core/test_v21_actions_keys.py packages/graph-agent/tests/core/test_v21_graph_assembly_fanout.py packages/graph-agent/tests/e2e/test_batch_analysis_v21.py packages/graph-agent/tests/e2e/test_v21_all_skills_smoke.py -q` 通过；V2.1 core/e2e 关键套件通过或仅包含 R3.3 预期 xfail；`ruff`/typing 如项目 CI 启用则通过；requirements/research/design/tasks 术语同步；无 LWW loose mode、deep merge、feature flag/backdoor；无前端/Studio 改动。
