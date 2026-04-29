# MVP-4 Tasks — A3 Phase Executor / A4 finish_task 子任务派发

> 整合 Gemini Part E 12 任务清单 + 主控调度优化 (新增 T0-prep, 修订依赖图)。

## 派发策略

- **a1 codex 主线**: T1 → T2 → T3 → T7 → T8 → T12 (重型: Node 接口 + finish_task 重画 + LLMPhaseNode + Nudge 重画 + 全量 e2e smoke)
- **a3 claude 副线**: T0-prep → T4 → T5 / T6 → T7a → T9 → T10 → T10a → T11 (短链 + 测试 + Compaction + ctx 残留迁移 + GraphBuilder + legacy 物理抹除 + 大批量测试更新)
- **a3 代码必须由 a1 codex review** (按 ccb-collaboration 角色铁律)
- **a2 gemini design review**: 本 spec 落盘后 PM 派 a2 审 design.md, 重点 review research D2 (ValidationPhaseNode 跟 ProtocolValidationMiddleware 职责区分) + D5 (interrupt + checkpoint 兼容方案), 30-60 min

每个 brief 必含**铁律 block**:
```
🚨 严禁 git mutate HEAD: git checkout/switch/reset/cherry-pick/merge/rebase/pull/stash. 只允许 read-only.
🚨 不要 commit / push / 创 PR / 派 ccb 给其他 agent.
```

## 关键路径

```
T0-prep (1.5h, a3) ─┐
                    ↓
T1 (1h, a1) ────────┴→ T2 (3h, a1) ──────────────────────┐
                       T3 (3h, a1) ──┐                   │
                       T4 (2h, a3) ──┤                   │
                       T7 (1h, a1) ←─┘                   │
                       T7a (3h, a3) ←─ T7 done ──────────┤
                       T5 (2h, a3) ←──┐                  │
                       T6 (2h, a3) ←──┤←─ T2+T3 done ────┤
                       T8 (2h, a1) ←──┘                  │
                       T9 (2h, a3) ←──── T3 done ────────┤
                       T10 (2h, a3) ←─── T3+T4 done ─────┤
                       T10a (2h, a3) ←── T8+T9+T7a done ─┤
                                                         ↓
                                                  T11 (4h, a3) → T12 (2h, a1)
```

最长链 = T0-prep + T1 + T2 + T6 + T11 + T12 = 1.5+1+3+2+4+2 = **13.5h** (a1+a3 紧密并行)。  
新增 T7a (3h, ctx 残留迁移) + T10a (2h, legacy 物理抹除) 可与主链上其他任务并行执行, 不延长关键路径。  
含 a2 design review + a1 cumulative review + CI/PR overhead, 总估 **22-26h** (≈ 3 工作日)。

## 子任务清单

### T0-prep — Baseline 数据测量

- **Owner**: a3 claude
- **依赖**: 无
- **估时**: 1.5h
- **产物**: `docs/v1-reset/mvp-4-baseline-snapshot.md` 含:
  - `phase_executor.py` 当前 SLOC + 每方法 SLOC 分布
  - `execute_llm_phase` 内 while 循环逻辑提炼 (Nudge 分支 / Compaction 触发 / 退出条件)
  - `NudgeInjector` 当前 API + 调用点完整清单
  - `_save_compaction_sidecar` 当前签名 + 触发点
  - `flow.finish_task_result` 在 MVP-1/2/3 后所有 read/write 站点 (file:line + 上下文)
  - 4 SKILL e2e smoke 当前 baseline (wall-time / token / nudge 触发次数 / compaction 触发次数, 各跑 3 次取中位数)
  - 4 SKILL persona 渲染 snapshot (跟 MVP-3 baseline 一样存 `tests/graph_agent/snapshots/persona_<skill>.txt`)
  - `state["data"]` 在 finish.py / nodes / middleware 之外的赋值站点 grep
  - **新增 (T7a/T10a 派单依据)**:
    - `cognitive/middlewares.py` 当前 SLOC + 类列表 (ValidationMiddleware / WorkingMemoryMiddleware / DeadEndPruningMiddleware / AgentLoopIterationMiddleware / UnattendedClarificationMiddleware 等) + 每类外部 caller 清单 (grep 'from .middlewares import' 全库)
    - `cognitive/clarification_middleware.py` 当前 SLOC + 类 + 外部 caller 清单
    - `core/state.py:legacy_context_from_state` (line 165) + `workflow_state_from_legacy_context` (line 214) 的所有外部 caller 清单 (grep 全库)
    - `ctx["_X"]` / `ctx.get("_X")` 残留点完整清单 (grep `'ctx\["_\|ctx\.get("_'` src/core/graph_agent/), 按文件分组列出 file:line + 含义解释 (是 read 还是 write)。预期分布在: `harness.py` (验证警告 / ambiguity 报告读取) / `cognitive/ambiguity.py` (写报告) / `cognitive/memory.py` (写 working_memory) / `cognitive/middlewares.py` (即将砍除, 不需迁移) / `tools/builtin/context_access.py` (读 working_memory / read_artifact) / `tools/md_to_json.py` (读 _md_schema / _md_schema_path) / `core/state.py` 桥函数本体 (40+ 处, 是 bridge 实现, 不算外部残留)
    - `io/manager.py` line 48 + line 336 的 `context["_io_errors"]` 注释残留 (T2/T7 落地后已无运行时引用, 仅 docstring)
    - `cognitive/test_*.py` 测试文件清单 (grep `tests/graph_agent/cognitive/test_*.py`) + 各文件 mock 的 middleware 类名 (确认 T11 + T10a 改造范围)
- **验收**:
  - `ls docs/v1-reset/mvp-4-baseline-snapshot.md` 存在
  - 文档含数字 (不允许占位符)
  - 不动任何 src/ tests/ 文件

### T1 — 定义 `BasePhaseNode` 及其子类骨架

- **Owner**: a1 codex
- **依赖**: T0-prep
- **估时**: 1h
- **产物**:
  - `src/core/graph_agent/core/nodes/__init__.py` 新文件 (导出 4 类)
  - `src/core/graph_agent/core/nodes/base.py` 新文件 (BasePhaseNode ABC, design §1.2)
  - `src/core/graph_agent/core/nodes/llm.py` 骨架 (类签名 + execute pass)
  - `src/core/graph_agent/core/nodes/logic.py` 骨架
  - `src/core/graph_agent/core/nodes/validation.py` 骨架
  - 单测 `tests/graph_agent/core/nodes/test_base.py` 含 ABC 强制 / 子类必须实现 execute / name property 等 5+ 测试
- **验收**:
  - `from graph_agent.core.nodes import BasePhaseNode, LLMPhaseNode, LogicPhaseNode, ValidationPhaseNode` 全部 import 成功
  - mypy strict 通过
  - 单测覆盖率 ≥ 95%
  - pytest 不退步 (此时旧 phase_executor.py 仍在, GraphBuilder 仍用旧路径)

### T2 — 重构 `finish_task` 工具签名 + ProtocolValidationMiddleware 拦截

- **Owner**: a1 codex
- **依赖**: T1
- **估时**: 3h
- **产物**:
  - `cognitive/finish.py` finish_task 函数签名改为 `(reasoning, diagnostics_md, business_data: BaseModel)` (design §2.1)
  - 工具实现仅返回 "task completed", 不写 ctx, 不做校验/hoist
  - `middleware/protocol_validation.py` (MVP-3 落地) 扩展 `intercept_tool_call(tool_name, args, state)` 含 finish_task 拦截路径 (design §5.2)
  - 校验失败返回 Command(goto="model"), 校验通过写 `flow.finish_task_result`
  - LangChain 工具注册改为绑定 `build_business_data_for_skill(manifest, schema_engine)` 生成的强类型类
  - 单测扩展含: 校验通过路径 + 校验失败路径 + checkpoint 恢复跳过校验路径
- **验收**:
  - `grep '_finish_task_result\|md_to_json' src/core/graph_agent/cognitive/finish.py` 0 hits
  - 4 SKILL e2e smoke 跑 1 chapter 不破裂 (LangChain 工具能正确注入强类型 business_data)
  - 单测覆盖率 ≥ 95%
  - pytest 不退步

### T3 — 实现 `LLMPhaseNode.execute` (去 while 循环 + Command 路由)

- **Owner**: a1 codex
- **依赖**: T1
- **估时**: 3h
- **可与 T2 部分并行 (T2/T3 同主线但内部并行可行)**
- **产物**:
  - `core/nodes/llm.py` 完整实现 (design §1.3)
  - **不**包含任何 `while True` 硬循环
  - Nudge / 重试 / 防环 通过 4 middleware (MVP-3) + Command(goto) 实现
  - LLMPhaseNode 出口调 `IOManager.resolve_hoist` 完成 hoist
  - 单测 `tests/graph_agent/core/nodes/test_llm.py` 含 5+ 测试 (基本路径 / Command 路由 / hoist / 归档 / 清空)
- **验收**:
  - `grep 'while True' src/core/graph_agent/core/nodes/llm.py` 0 hits
  - LLMPhaseNode.execute 返回 WorkflowState 或 Command
  - 单测覆盖率 ≥ 95%
  - 4 SKILL e2e smoke 跑 1 chapter 不破裂 (此时旧 phase_executor 仍在, GraphBuilder 还没切, T10 才切)

### T4 — 实现 `LogicPhaseNode` + `ValidationPhaseNode`

- **Owner**: a3 claude
- **依赖**: T1
- **估时**: 2h
- **可与 T2 / T3 并行**
- **产物**:
  - `core/nodes/logic.py` 完整实现 (design §1.4)
  - `core/nodes/validation.py` 完整实现 (design §1.5)
  - LogicPhaseNode 顺序调 phase.tools 的 nature: tool 接收 state 不是 ctx (跟 MVP-1 设计对齐)
  - ValidationPhaseNode 跑业务 validator + retry_target 路由 (Command(goto))
  - 单测 `tests/graph_agent/core/nodes/test_logic.py` + `test_validation.py` 各 5+ 测试
- **验收**:
  - 单测覆盖率 ≥ 95%
  - mypy strict 通过

### T5 — LangGraph interrupt 集成 Clarification

- **Owner**: a3 claude
- **依赖**: T1 + T3
- **估时**: 2h
- **产物**:
  - `middleware/cognitive_flow.py` (MVP-3 落地) 改造 `intercept_tool_call` 含 ask_clarification 分支 (design §5.1)
  - attended mode → LangGraph 原生 `interrupt({"question": ...})`
  - unattended mode → `_auto_resolve_clarification` (现有 UnattendedClarificationMiddleware 逻辑迁移)
  - ProtocolValidationMiddleware 加 checkpoint 恢复检测 (design §5.2)
  - 单测覆盖 attended interrupt 触发 / unattended auto-resolve / interrupt 恢复路径
- **验收**:
  - 4 SKILL attended + unattended 模式 e2e 不破裂
  - LangGraph interrupt + checkpoint 恢复跑 1 SKILL 通过 (验证 finish_task_result 恢复后不重复校验)
  - 单测覆盖率 ≥ 95%

### T6 — 迁移 IOManager Hoist 到 Node 出口 + 状态归档/清空

- **Owner**: a3 claude
- **依赖**: T2 + T3
- **估时**: 2h
- **产物**:
  - `core/nodes/llm.py` 出口逻辑 (design §1.3 step 5+6) 完整实现
  - `core/nodes/base.py:_archive_finish_task_result` 公共方法实现
  - LLMPhaseNode 入口清空 `flow.finish_task_result`
  - `core/state.py:FrameworkState` 加 `history_results: dict[str, dict[str, Any]]` 字段 (design §4)
  - 单测 `tests/graph_agent/core/nodes/test_finish_task_lifecycle.py` 含: 归档 / 清空 / hoist / 跨 phase 不污染 4 个场景
- **验收**:
  - phase 切换时 finish_task_result 正确归档 + 清空
  - history_results[phase_name] 含已完成 phase 的封存数据
  - 单测覆盖率 ≥ 95%

### T7 — 废弃 `route_finish_task` + 全局依赖更新

- **Owner**: a1 codex
- **依赖**: T2
- **估时**: 1h
- **产物**:
  - `StateManager.route_finish_task` 物理删除
  - `StateManager` 类整体废弃 (`state_manager.py` 文件物理删除, design §3.1)
  - `core/state_reducers.py` 新文件 (含 update_business + update_framework 纯函数, design §3.2)
  - 全局调用方迁移: `from .state_manager import StateManager` → `from .state_reducers import update_business, update_framework` (design §3.3)
- **验收**:
  - `grep 'route_finish_task\|class StateManager' src/core/graph_agent/` 0 hits
  - `ls src/core/graph_agent/core/state_manager.py` 不存在 (ENOENT)
  - `ls src/core/graph_agent/core/state_reducers.py` 存在
  - pytest 不退步

### T7a — ctx["_X"] 残留迁移到 FrameworkState 直接读写 + state.py 桥函数收口

- **Owner**: a3 claude
- **依赖**: T7
- **估时**: 3h
- **可与 T8 / T9 / T10 并行 (T7a 只动 cognitive/ 与 tools/ 与 harness.py 的具体 ctx 读写点, 不动 nodes/ 与 GraphBuilder)**
- **产物**: 把所有外部模块从 `ctx["_X"]` / `ctx.get("_X")` 形式直接读 framework 字段:
  - `harness.py` (验证警告 + ambiguity 报告) → 改为读 `state["flow"].validation_warnings` / `state["flow"].ambiguity_reports` (用 state_reducers.update_framework 写回)
  - `cognitive/ambiguity.py` (写 ambiguity 报告) → 改为返回 dict 让上游 phase_executor / Node 通过 update_framework 写入
  - `cognitive/memory.py:update_working_memory` (写 working_memory) → 同上, 改返回 dict 让 Node 出口通过 update_framework 写入
  - `tools/builtin/context_access.py:query_working_memory / read_artifact` (读 working_memory + business artifacts) → 直接读 `state["flow"].working_memory` 与 `state["data"].<artifact_name>`
  - `tools/md_to_json.py:535-543` (读 `_md_schema` / `_md_schema_path` schema 解析路径) → 改为 SchemaEngine 注入 (MVP-2 已就绪) 或 phase 注入参数, 不再从 ctx 读
  - **不动 `cognitive/middlewares.py`** (T10a 整体物理删除, 不在此 task 改)
  - 单测 `tests/graph_agent/cognitive/test_ambiguity.py` / `test_memory.py` / `tests/graph_agent/tools/test_context_access.py` / `test_md_to_json.py` 改造 (mock state["flow"] 字段 而非 mock ctx dict)
- **state.py 桥函数处置决定**: 默认在本 task 末尾把 `legacy_context_from_state` (state.py line 165) 与 `workflow_state_from_legacy_context` (line 214) 物理删除。若 T0-prep 发现仍有外部 caller 不在本 task 范围 (例如 phase_executor.py 仍在用), 桥函数推迟到 T12 跟 phase_executor.py 一起删, 本 task 仅清理桥函数内部 `_underscore` field 列表中本 task 已迁移的字段。
- **验收**:
  - `grep -rn 'ctx\["_\|ctx\.get("_' src/core/graph_agent/ --include="*.py" | grep -v "^src/core/graph_agent/core/state\.py"` 在 `cognitive/middlewares.py` 之外应为 0 hits (cognitive/middlewares.py 砍除前还会有, 在 T10a 一起处理)
  - 4 SKILL e2e smoke 不破裂 (跟 T0-prep baseline 比 wall-time / token ±10%)
  - pytest 不退步
  - 单测覆盖率 ≥ 95% (改造的 4 个工具 / cognitive 文件)

### T8 — NudgeInjector 重画为 LangGraph 路由

- **Owner**: a1 codex
- **依赖**: T3
- **估时**: 2h
- **产物**:
  - 旧 `NudgeInjector` (in execute_llm_phase) 逻辑提炼到 ExecutionControlMiddleware (MVP-3 落地)
  - Nudge 触发通过 LangGraph Command(goto="LLMPhaseNode") 重入实现 (design §6.2)
  - `core/state.py:FrameworkState` 加 `nudge_counts: dict[str, int]` 字段 (design §4 + research D5)
  - max_nudges 判定通过 ExecutionControlMiddleware 在 nudge_counts 累计超阈值时 Command(goto="phase_end")
- **验收**:
  - `grep 'class NudgeInjector\|NudgeInjector(' src/core/graph_agent/core/nodes/` 0 hits (NudgeInjector 类消失)
  - 4 SKILL e2e nudge 触发次数跟 baseline 相比 ±10% 内 (T0-prep 测的 baseline)
  - 死循环无限 nudge 测试通过 (跑 1 SKILL 故意触发 nudge, 验证 max_nudges 后退出)

### T9 — Checkpoint Compaction 脱离 while 循环

- **Owner**: a3 claude
- **依赖**: T3
- **估时**: 2h
- **产物**:
  - 旧 `_compact_messages` + `_save_compaction_sidecar` 触发逻辑 (in execute_llm_phase while 循环) 提炼到 ExecutionControlMiddleware (MVP-3 落地)
  - 触发条件 (working_memory 更新 + messages 累积) 在 middleware 内监控 (design §7)
  - LLMPhaseNode 不感知 compaction (透明)
- **验收**:
  - `grep '_compact_messages\|_save_compaction_sidecar' src/core/graph_agent/core/nodes/llm.py` 0 hits
  - 4 SKILL e2e compaction 触发次数跟 baseline ±10% 内
  - sidecar 文件路径 `_history/{run_id}/{idx}.json` 跟 baseline 一致

### T10 — 修改 `GraphBuilder` 对接新 Node 实例

- **Owner**: a3 claude
- **依赖**: T3 + T4
- **估时**: 2h
- **产物**:
  - `core/graph_builder.py` 不再创建闭包函数, 改为直接把 PhaseNode 实例的 `.execute` 方法作为 LangGraph node 注入
  - MVP-3 Loader 的 `build_graph_nodes(manifest)` 输出已经是 list[PhaseNode], 此处只是消费方改造
  - 旧 `_make_llm_node` / `_make_code_only_node` / `_make_validation_node` 闭包函数物理删除
  - 单测 `tests/graph_agent/core/test_graph_builder.py` 改造跟新接口 (Spy executor 改 Spy PhaseNode)
- **验收**:
  - `grep '_make_llm_node\|_make_code_only_node\|_make_validation_node' src/core/graph_agent/` 0 hits
  - 4 SKILL compile 状态不变
  - pytest tests/graph_agent/core/test_graph_builder.py 全过

### T10a — cognitive/middlewares.py + cognitive/clarification_middleware.py 物理抹除 + io/manager.py 注释清理

- **Owner**: a3 claude
- **依赖**: T8 + T9 + T7a (T8 把 NudgeInjector / DeadEnd / AgentLoopIteration 逻辑迁出, T9 把 Compaction 迁出, T7a 把 ctx 残留迁出 — 此时 cognitive/middlewares.py 内所有运行时逻辑均已搬走)
- **估时**: 2h
- **可与 T6 / T11 部分并行 (但 T11 测试更新需要 T10a 的删除结果, 推荐紧跟 T10a 跑)**
- **产物**:
  - `src/core/graph_agent/cognitive/middlewares.py` 文件物理删除 (前置: 全库 grep 'from .middlewares import' 与 'from ..cognitive.middlewares import' 应 0 hits, 即所有 caller 已在 T8/T9 等任务里迁移到 `graph_agent.middleware.execution_control` / `graph_agent.middleware.cognitive_flow` 路径)
  - `src/core/graph_agent/cognitive/clarification_middleware.py` 文件物理删除 (前置: T5 已经把 attended interrupt + unattended auto-resolve 逻辑迁到 CognitiveFlowMiddleware; 全库 grep 'from .clarification_middleware\|from ..cognitive.clarification_middleware' 应 0 hits)
  - `src/core/graph_agent/io/manager.py` 文件 line 48 + line 336 的 `context["_io_errors"]` docstring 注释清理 (改为引用 `state["flow"].io_errors` 并补充 "since MVP-2 T7" 标注)
  - `tests/graph_agent/cognitive/test_middlewares.py` (如存在) 物理删除 (因 cognitive/middlewares.py 已删, 测试无所测对象; 等价测试已经在 MVP-3 的 `tests/graph_agent/middleware/test_*.py` 里)
  - `tests/graph_agent/cognitive/test_clarification_middleware.py` 同上删除
  - `tests/graph_agent/cognitive/test_*.py` 中其他 mock `cognitive.middlewares.X` / `cognitive.clarification_middleware.X` 的测试改 mock 新路径 `graph_agent.middleware.cognitive_flow.X` / `graph_agent.middleware.execution_control.X` (如有)
- **验收**:
  - `ls src/core/graph_agent/cognitive/middlewares.py` ENOENT
  - `ls src/core/graph_agent/cognitive/clarification_middleware.py` ENOENT
  - `grep -rn 'from .middlewares\|from ..cognitive.middlewares\|from .clarification_middleware\|from ..cognitive.clarification_middleware' src/core/graph_agent/` 0 hits
  - `grep -rn 'cognitive.middlewares\|cognitive.clarification_middleware' tests/graph_agent/` 0 hits
  - `grep -rn 'context\["_io_errors"\]' src/core/graph_agent/io/manager.py` 0 hits (注释已清理)
  - pytest 不退步 (此时 T11 还没开始, 其他 cognitive/test_*.py 等价测试在 tests/graph_agent/middleware/ 下应保持 pass)
  - 4 SKILL e2e smoke 不破裂

### T11 — 批量更新测试以适配新 Node 接口

- **Owner**: a3 claude
- **依赖**: T4-T10 + T7a + T10a 全部完成
- **估时**: 4h
- **产物**:
  - `tests/graph_agent/core/test_phase_executor.py` + `test_phase_executor_validation.py` 物理删除 (phase_executor.py 已删)
  - 替代为 `tests/graph_agent/core/nodes/test_llm.py` / `test_logic.py` / `test_validation.py` (含原测试场景的等价用例)
  - 所有 mock state 测试改用 `state_reducers.update_business / update_framework` 而非 `StateManager.X`
  - **`tests/graph_agent/cognitive/test_*.py` 整体审计**: 把所有 mock `cognitive.middlewares` / `cognitive.clarification_middleware` 的测试改 mock `graph_agent.middleware.*` 新路径; 把所有 mock `ctx["_X"]` dict 的测试改 mock `state["flow"]` Pydantic 字段 (T7a 后接口已变)。残留无所测对象的测试文件 (例如纯测 ValidationMiddleware 而非整合 ProtocolValidationMiddleware 的) 物理删除。
  - 4 SKILL e2e mock test 改造跟新 Node 接口
  - LoopDetection / Nudge 边界测试通过新 Command 路由还原 (Gemini Part G 验收 #3)
- **验收**:
  - pytest 全过 (--ignore=tests/graph_agent/core/validators/test_strict_v2.py)
  - test_strict_v2 14 pre-existing failures 仍 isolated
  - LoopDetection 测试通过新 Command 路由仍能检测同一 phase 连续重复 N 次的场景
  - Nudge 边界测试 (planning / selfcheck / standard 三场景) 全过
  - `grep -rn 'cognitive.middlewares\|cognitive.clarification_middleware' tests/graph_agent/` 0 hits (T10a 已要求, T11 复核)
  - `grep -rn 'ctx\["_\|ctx\.get("_' tests/graph_agent/` 仅剩 `tests/graph_agent/core/test_state.py` 测桥函数本体 (允许), 其余测试 0 hits

### T12 — 端到端冒烟测试 (4 SKILL 全量回归)

- **Owner**: a1 codex
- **依赖**: T11
- **估时**: 2h
- **产物**:
  - `phase_executor.py` 物理删除 (此时所有调用方已迁移到 nodes/*.py)
  - 若 T7a 期间 `state.py:legacy_context_from_state` / `workflow_state_from_legacy_context` 桥函数当时尚有 phase_executor.py caller 没删干净, 在此 task 一并物理删除两个桥函数 (phase_executor.py 已删, 桥函数无 caller)
  - 4 SKILL 各跑 1 chapter e2e smoke (text-segmentation v0/v1/v2/v3 + md-patch + finish-validator + clarification 内置)
  - persona 渲染 snapshot byte-equal 验证 (跟 T0-prep baseline)
  - 4 SKILL e2e wall-time / token / nudge / compaction 触发次数跟 T0-prep baseline 比对, 文档化偏差 (±10% 内)
  - `docs/v1-reset/mvp-4-completion-report.md` 汇总指标
- **验收**:
  - `ls src/core/graph_agent/core/phase_executor.py` ENOENT
  - `ls src/core/graph_agent/cognitive/middlewares.py` ENOENT (T10a 已删, 此处 final 复核)
  - `ls src/core/graph_agent/cognitive/clarification_middleware.py` ENOENT (T10a 已删, 此处 final 复核)
  - `grep -rn 'legacy_context_from_state\|workflow_state_from_legacy_context' src/core/graph_agent/` 仅在 `core/state.py` 出现 (定义点) OR 全 0 hits (定义已删)
  - `grep -rn 'class StateManager\|route_finish_task' src/core/graph_agent/` 0 hits
  - `grep -rn 'while True:' src/core/graph_agent/core/nodes/` 0 hits
  - `grep -rn 'state\["data"\]\[' src/core/graph_agent/` 在 `core/nodes/` / `cognitive/finish.py` / `core/state_reducers.py` / `middleware/` 之外为 0 hits (single-write 路径验证)
  - 4 SKILL e2e 全过
  - persona snapshot byte-equal
  - 性能指标偏差 ≤ ±10%
  - 完成报告所有指标达标

## a1 review 节奏

- **每子任务 review** (针对 a3 的 T0-prep / T4 / T5 / T6 / T7a / T9 / T10 / T10a / T11): a3 完成后 a1 立刻 review
- **MVP-4 整体 review**: T12 done 后 a1 把所有 MVP-4 commits 整体过一遍 + cumulative spotcheck (重点验证 design §8 baseline diff 全部满足 + design §9 invariants 全过)

## 主控调度

派发顺序 (伪时间线):

```
t=0     spec 4 docs 落盘 commit; 派 a3 T0-prep + 同时派 a2 design review (30-60 min)
t=1.5h  a3 T0-prep done; a2 design review done; 主控整合 review 反馈; 派 a1 T1
t=2.5h  a1 T1 done → 主控 commit T1 → 派 a1 T2 + a1 T3 + a3 T4 (3 路并行)
t=4.5h  a3 T4 done → a1 review (10min) → 主控 commit T4
t=5.5h  a1 T2 done + a1 T3 done → 主控 commit T2+T3 → 派 a1 T7 + a1 T8 + a3 T5 + a3 T6 + a3 T9 (5 路并行)
t=6.5h  a1 T7 done → 主控 commit T7 → 派 a3 T7a (依赖 T7 done)
t=7.5h  a3 T5 done + a3 T9 done → a1 review (15min) → 主控 commit T5+T9
t=7.5h  a3 T6 done → a1 review (10min) → 主控 commit T6
t=8.5h  a1 T8 done → 主控 commit T8 → 派 a3 T10
t=9.5h  a3 T7a done → a1 review (20min, 重点验证 ctx 残留 grep 0 hits) → 主控 commit T7a
t=10.5h a3 T10 done → a1 review (15min) → 主控 commit T10 → 派 a3 T10a (依赖 T8+T9+T7a 均 done)
t=12.5h a3 T10a done → a1 review (15min, 重点验证 cognitive/* ENOENT) → 主控 commit T10a → 派 a3 T11
t=16.5h a3 T11 done → a1 review (30min) → 主控 commit T11 → 派 a1 T12
t=18.5h a1 T12 done → 主控 commit + a1 整体 review
t=20h   a1 整体 review done → 主控 squash + push + PR + CI green + merge
```

总估 = 22-26h wall-clock (含 a2 design review / a1 cumulative review / CI / PR 周转, ≈ 3 工作日)。

## Pre-flight checklist

派 T0-prep 前主控自检:
- [ ] MVP-1 + MVP-2 + MVP-3 已 merge 到 main
- [ ] BusinessData / FrameworkState / SchemaEngine / IOManager / 4 核心 middleware (ProtocolValidation / CognitiveFlow / ExecutionControl / Logging) / Bootstrap / Settings 在 main 可用
- [ ] PhaseNode 接口 (MVP-3 落地的 BasePhaseNode 框架) 可用
- [ ] spec 4 docs 落盘 (.kiro/specs/v1-reset-mvp-4-executor-finish/{requirements,research,design,tasks}.md)
- [ ] Gemini design 已审 (job_82a24b78ac71 reply 整合到 design.md)
- [ ] research D2 (ValidationPhaseNode 职责) + D5 (interrupt + checkpoint 兼容) 已派 a2 二轮确认
- [ ] orchestrator scope 起好 (MVP-4 涉及 5 路并行任务 + 大量子进程, **强烈建议** 起 dedicated scope, --tasks-max 800)
- [ ] a1 codex 当前状态 = idle (已 /clear)
- [ ] a3 claude 当前状态 = idle

## 跟 MVP-3 / MVP-5 的衔接

- **MVP-3 已就位 (前置依赖)**: Loader 三阶段 + 4 核心 middleware + ModuleSandbox + PhaseNode 框架 + Bootstrap/Settings
- **MVP-5 接口约定 (后置)**: 
  - PhaseExecutionError / ValidationInterrupt 异常体系稳定 (MVP-5 在 Runner 层 try/catch 聚合)
  - harness.run(state) → state 强类型边界稳定 (MVP-5 拆 .compile/.prepare_state/.invoke_graph/.persist_outputs 时不能改这个签名)
  - state_reducers.update_business / update_framework 接口稳定
  - 4 SKILL e2e baseline 性能指标稳定 (MVP-5 收紧 mypy strict / coverage 时不能引入性能退化)
  - cognitive/middlewares.py + cognitive/clarification_middleware.py 已物理删除 (T10a), MVP-5 不再处理这两个文件
  - state.py:legacy_context_from_state / workflow_state_from_legacy_context 桥函数已物理删除 (T7a 或 T12), MVP-5 不需关心 ctx dict 兼容
  - 全库 ctx["_X"] / ctx.get("_X") 形式残留 = 0 (T7a 已扫干净), MVP-5 工程门禁 ruff 全局拍平时不会撞 cognitive / tools 残留
  - cognitive/test_*.py 测试 mock 路径已收口到 graph_agent/middleware/* (T10a + T11), MVP-5 加 mypy strict 不会撞旧 mock 残留
