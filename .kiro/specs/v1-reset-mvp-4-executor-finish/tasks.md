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

### T2 — `finish_task` 工具签名简化 + agent_factory 动态注入 StructuredTool

- **Owner**: a1 codex
- **依赖**: T1
- **估时**: 3-4h (从原 3h 略增, 新增 agent_factory 动态包装层)
- **背景说明**: 原 brief "在 ProtocolValidationMiddleware 内拦截 finish_task 校验" **已由 MVP-3 cognitive_flow.py 完成** (CognitiveFlowMiddleware.intercept_tool_call 在 MVP-3 T8 已落地拦截 + 校验, 见 `src/core/graph_agent/middleware/cognitive_flow.py`). MVP-4 T2 不再做拦截层, 改做"agent_factory 动态注入强类型 finish_task tool"
- **产物**:
  - `cognitive/finish.py` finish_task 函数签名改为 `(reasoning: str, diagnostics_md: str, business_data: BaseModel) -> str` (design §2.1), 工具实现仅返回 "task completed", **不**写 ctx, **不**做校验, **不**做 hoist (校验 + hoist 全在 cognitive_flow.py middleware 已做)
  - **新模块/扩展**: `core/nodes/llm.py` 内 `agent_factory` 函数 (或 `core/agent_factory.py` 独立文件 — 实施时定) 在创建 LangChain agent 时, 用 `SchemaEngine.get_pydantic_model(phase.compiled_schema)` 生成的强类型 Pydantic 类作为 `finish_task` tool 的 `args_schema`, 而不是硬编码通用 `BusinessData` 父类。具体做法 (design §1.3 注释提示):
    ```python
    finish_tool = StructuredTool.from_function(
        func=finish_task,
        args_schema=schema_engine.get_pydantic_model(phase.compiled_schema),
    )
    ```
  - 4 SKILL 各自调 finish_task 时 LLM 看到的 args_schema 应该是 SKILL 自己 compiled_schema 的 Pydantic 子类 (e.g. `TextSegmentationFinishArgs` / `EventExtractionFinishArgs` 等), 而不是泛型 `BusinessData`. 这让 LLM 在 tool call 自动补齐时拿到 SKILL 特定字段提示, 提升遵循率
  - **不动 cognitive_flow.py 现有的拦截逻辑** (MVP-3 已落地, 改动属 scope leak)
  - 单测扩展含: (1) finish_task 函数签名校验; (2) agent_factory 用不同 phase compiled_schema 时 finish_tool.args_schema 是不同 Pydantic 类 (per-SKILL 强类型); (3) finish_tool 调用时 LangChain 能用 args_schema 校验 LLM 输出 (回到 Pydantic ValidationError 时机)
- **必读**:
  - `.kiro/specs/v1-reset-mvp-4-executor-finish/design.md` §1.3 (LLMPhaseNode 内动态 Tool Schema 绑定注释 line 96-101) + §2.1 (finish_task 工具签名)
  - `src/core/graph_agent/core/schema_engine.py` (`get_pydantic_model` 接口签名 + lru_cache 行为)
  - `src/core/graph_agent/middleware/cognitive_flow.py` (确认拦截 + hoist 已做, 不要重复实施)
- **验收**:
  - `grep '_finish_task_result\|md_to_json' src/core/graph_agent/cognitive/finish.py` 0 hits (finish.py 内已无 dict mutation / md 解析逻辑)
  - 4 SKILL 各自启动 LLMPhaseNode 时, `agent.tools` 中 finish_task 的 args_schema 检查 (e.g. via `tool.args_schema.__name__`) 等于该 SKILL compiled_schema 派生的类名, 而不是通用 `BusinessData`
  - 4 SKILL e2e smoke 跑 1 chapter 不破裂 (LangChain 工具能正确接受动态 args_schema 注入)
  - 单测覆盖率 ≥ 95%
  - pytest 不退步
- **边界**:
  - 不动 cognitive_flow.py / clarification_middleware 的拦截逻辑 (那是 MVP-3 范畴)
  - 不动 schema_engine.py 内部 (本任务只调 get_pydantic_model 接口)

### T3 — 实现 `LLMPhaseNode.execute` (去 while 循环 + Command 路由)

- **Owner**: a1 codex
- **依赖**: T1
- **估时**: 2h (从原 3h 减, **不再写 IOManager.resolve_hoist 调用** — cognitive_flow.py middleware 已做)
- **可与 T2 部分并行 (T2/T3 同主线但内部并行可行)**
- **背景说明**: 按 a2 修订后的 design.md §1.3 + §2.2, IO Hoist 已由 MVP-3 cognitive_flow.py 在 finish_task 拦截通过时一并完成, **LLMPhaseNode 出口不再调 IOManager.resolve_hoist** (避免 double Hoist 把 BusinessData 字段写两次). 出口仅做存在性检查 + 归档 + 清空.
- **产物**:
  - `core/nodes/llm.py` 完整实现 (design §1.3 line 90-125)
  - **不**包含任何 `while True` 硬循环
  - Nudge / 重试 / 防环 通过 4 middleware (MVP-3) + Command(goto) 实现
  - **execute 出口逻辑** (按 design §1.3 step 4-6):
    - step 4: 检查 `state["flow"].finish_task_result` 是否为 None — 是则返回 state (走 retry / nudge 由 ExecutionControlMiddleware 决定)
    - step 5: **(取消)** — 不再调 `IOManager.resolve_hoist` (cognitive_flow.py 已做, 见 design.md line 119-120 注释)
    - step 6: 调 `_archive_finish_task_result(state)` 归档到 `flow.history_results[phase_name]`, 然后返回 state
  - execute 入口逻辑: `update_framework(state, finish_task_result=None)` 清空上轮残留 (跨 phase 生命周期保护)
  - 单测 `tests/graph_agent/core/nodes/test_llm.py` 含 5+ 测试:
    - 基本路径 (finish_task_result 已被 middleware 写入 → 归档 → 清空)
    - Command 路由路径 (finish_task_result 为 None → 返回 state 让 middleware 决定 retry / nudge)
    - 归档检查 (history_results[phase_name] 内容跟 finish_task_result 一致)
    - 清空检查 (phase 入口 finish_task_result == None)
    - **不要测 IOManager.resolve_hoist 调用** (那是 cognitive_flow.py 单测的事)
- **验收**:
  - `grep 'while True' src/core/graph_agent/core/nodes/llm.py` 0 hits
  - **`grep 'resolve_hoist' src/core/graph_agent/core/nodes/llm.py` 0 hits** (确保没误调用 cognitive_flow.py 已做的逻辑)
  - LLMPhaseNode.execute 返回 WorkflowState 或 Command
  - 4 SKILL e2e smoke 跑 1 chapter 不破裂 — **重点验证 state["data"] 字段不被 double Hoist 重复合并** (跑 baseline 跟新版 4 SKILL e2e 后比对 state["data"] 内容, 应一致, 不能多写)
  - 单测覆盖率 ≥ 95%
- **边界**:
  - 不调 IOManager.resolve_hoist (那是 cognitive_flow.py 拦截时的职责, MVP-3 已落地)
  - 不动 cognitive_flow.py / IOManager.py (本任务只是 LLMPhaseNode 内部实现)

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
- **估时**: 1.5h (从原 2h 减, **不再写 ProtocolValidationMiddleware checkpoint 恢复检测**)
- **背景说明**: 按 a2 修订后的 design.md §5.2, "interrupt 恢复时不重复触发校验" 段已废弃 — `interrupt()` 挂起的 tool 由 LangGraph 原生在 resume 时直接返回人类输入给 LLM, 不会重新跑 finish_task 拦截, 因此**不需要任何 anti-double-check 设计**.
- **产物**:
  - `middleware/cognitive_flow.py` (MVP-3 落地) 改造 `intercept_tool_call` 含 ask_clarification 分支 (design §5.1)
  - attended mode → LangGraph 原生 `interrupt({"question": ...})`
  - unattended mode → `_auto_resolve_clarification` (现有 UnattendedClarificationMiddleware 逻辑迁移)
  - **(取消)** 原 brief "ProtocolValidationMiddleware 加 checkpoint 恢复检测 (design §5.2)" — 已废弃, LangGraph 原生 resume 不重复触发校验
  - 单测覆盖 attended interrupt 触发 / unattended auto-resolve (interrupt 恢复路径单测**改为**: 验证 LangGraph 原生 resume 后 LLM 直接收到人类输入, 不重新触发 finish_task 拦截)
- **验收**:
  - 4 SKILL attended + unattended 模式 e2e 不破裂
  - LangGraph interrupt + Clarification 恢复跑 1 SKILL 通过 (验证 resume 后 LLM 收到 human_response, 不二次拦截)
  - 单测覆盖率 ≥ 95%
- **边界**:
  - 不在 ProtocolValidationMiddleware 内加任何 checkpoint 恢复逻辑 (a2 修订后已声明该机制废弃)

### T6 — 实现状态归档/清空 + history_results 字段 (Hoist 部分已废弃)

- **Owner**: a3 claude
- **依赖**: T2 + T3
- **估时**: 1h (从原 2h 减, **删除原 "迁移 IOManager Hoist 到 Node 出口" 段** — cognitive_flow.py middleware 已做 Hoist)
- **背景说明**: 原 brief "迁移 IOManager Hoist 到 Node 出口" 跟 a2 修订后的 design.md §2.2 冲突 — Hoist 已在 CognitiveFlowMiddleware 完成 (MVP-3 落地). T6 重新定位为"实现 PhaseNode 出口归档 + 入口清空 + FrameworkState.history_results 字段", 不再写 Hoist 调用.
- **产物**:
  - `core/nodes/base.py:_archive_finish_task_result` 公共方法实现 — 把 `state["flow"].finish_task_result` 封存到 `state["flow"].history_results[phase_name]`
  - LLMPhaseNode 入口清空 `flow.finish_task_result` (跟 T3 step 1 协调一致)
  - `core/state.py:FrameworkState` 加 `history_results: dict[str, dict[str, Any]] = Field(default_factory=dict)` 字段 (design §4)
  - **(取消)** 原 brief "core/nodes/llm.py 出口逻辑 (design §1.3 step 5+6) 完整实现" 中 step 5 (resolve_hoist) — 已由 T3 边界声明不写
  - 单测 `tests/graph_agent/core/nodes/test_finish_task_lifecycle.py` 含 3 场景:
    - 归档 (phase 完成后 history_results[phase_name] 内容跟 finish_task_result 一致)
    - 清空 (下一 phase 入口 finish_task_result == None)
    - 跨 phase 不污染 (phase A 完成 → phase B 入口 → phase B 出口, history_results 含 A + B 两个 key, 不互相覆盖)
  - **(取消)** 原 brief 第 4 个 hoist 场景测试 — 不在 T6 测试范围 (那是 cognitive_flow.py 单测的事)
- **验收**:
  - phase 切换时 finish_task_result 正确归档 + 清空
  - history_results[phase_name] 含已完成 phase 的封存数据
  - 单测覆盖率 ≥ 95%
- **边界**:
  - 不写任何 IOManager.resolve_hoist 调用 (那是 cognitive_flow.py 拦截时的职责, MVP-3 已落地)

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
  - **`grep -rn 'resolve_hoist' src/core/graph_agent/core/nodes/` 0 hits** (确保 LLMPhaseNode 内没有错误重复调用 cognitive_flow.py 已做的 Hoist; 即不能 double Hoist)
  - **double Hoist regression check**: 跟 T0-prep 存的 4 SKILL state["data"] snapshot 比对, 字段不能多写 (例如 segments 字段被合并两次形成长度 × 2)
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

- **MVP-3 已就位 (前置依赖)**: Loader 三阶段 + 4 核心 middleware + ModuleSandbox + PhaseNode 框架 + Bootstrap/Settings + **CognitiveFlowMiddleware 已实施 finish_task 拦截 + 校验 + IO Hoist 全套** (MVP-3 T8 落地, MVP-4 T2/T3/T6 直接消费, 不重复实施)
- **MVP-5 接口约定 (后置)**: 
  - PhaseExecutionError / ValidationInterrupt 异常体系稳定 (MVP-5 在 Runner 层 try/catch 聚合)
  - harness.run(state) → state 强类型边界稳定 (MVP-5 拆 .compile/.prepare_state/.invoke_graph/.persist_outputs 时不能改这个签名)
  - state_reducers.update_business / update_framework 接口稳定
  - 4 SKILL e2e baseline 性能指标稳定 (MVP-5 收紧 mypy strict / coverage 时不能引入性能退化)
  - cognitive/middlewares.py + cognitive/clarification_middleware.py 已物理删除 (T10a), MVP-5 不再处理这两个文件
  - state.py:legacy_context_from_state / workflow_state_from_legacy_context 桥函数已物理删除 (T7a 或 T12), MVP-5 不需关心 ctx dict 兼容
  - 全库 ctx["_X"] / ctx.get("_X") 形式残留 = 0 (T7a 已扫干净), MVP-5 工程门禁 ruff 全局拍平时不会撞 cognitive / tools 残留
  - cognitive/test_*.py 测试 mock 路径已收口到 graph_agent/middleware/* (T10a + T11), MVP-5 加 mypy strict 不会撞旧 mock 残留

## MVP-4 启动前必须做的 Migration (Checkpoint 不兼容)

按 a2 修订后的 design.md §5.3, MVP-4 改图节点拓扑 (删 `phase_executor` 内联 while + 拆出 `LLMPhaseNode` / `LogicPhaseNode` / `ValidationPhaseNode`), LangGraph Checkpoint 强绑定 Node 名 + 执行步数, **旧 Checkpoint 在新图必硬 crash**, 无法做 backward-compat。

### 强制清理动作

MVP-4 实施期间和 4 SKILL e2e smoke 跑测试前, **必须**先做以下清理, 否则会因拓扑破裂出现"幽灵 Crash"和 假阴性 (测试失败但根因是 stale checkpoint, 不是新代码 bug):

```bash
# 1. 清本地默认 SQLite checkpoint (LangGraph 默认存储)
#    路径在 graph_agent.config.Settings 内的 checkpoint_dir 字段; 默认是
#    ~/.graph_agent/checkpoints/ 或类似. 需要按 Settings 实际位置确认
rm -rf ~/.graph_agent/checkpoints/

# 2. 清测试期间的临时 checkpoint
rm -rf /tmp/graph_agent_test_*.sqlite
rm -rf tests/graph_agent/.checkpoints/

# 3. 清本地 e2e smoke 跑过的 _history sidecar (compaction 副产物, 跨 schema 不兼容)
find . -name "_history" -type d -exec rm -rf {} +
```

### 哪些子任务期间需要清

- **T0-prep 之前**: 清一次, 确保 baseline 测量是干净的
- **T3 (LLMPhaseNode) 完成后**: 清一次, 因为这是新拓扑首次跑通, 旧 checkpoint 立即不兼容
- **T10 (GraphBuilder 对接新 Node) 完成后**: 清一次, 因为 GraphBuilder 切换后整张图节点名彻底变了
- **T12 (4 SKILL e2e smoke) 之前**: 必须清, 否则跟 T0-prep baseline 比对会得到误差很大的"性能退化" 假阴性

### Doc 同步声明

- `docs/v1-reset/RELEASE_NOTES.md` (Phase 2 升级版) Known Limitations 段必须明确写 "MVP-4 升级后旧 LangGraph checkpoint 不兼容, 升级时必须清空 checkpoint 存储"
- 跟 MVP-1 引入的 Pydantic state schema 不兼容声明 (MVP-1 RELEASE_NOTES 已声明 "升级后必须废弃旧 checkpoint") 累加, 不替换 — 都是 ship-blocker 警告

### 实施者风险提示

- 若 T3 或 T10 跑测试时报 LangGraph "node not found" / "step out of range" / "checkpoint version mismatch", **立即停下来检查是不是没清 checkpoint**, 别先怀疑代码写错
- 若 T12 比对 4 SKILL e2e baseline 性能指标偏差 > ±10%, 检查 `_history` sidecar 是不是有跨 schema 残留 (compaction 触发次数会因为旧 sidecar 误判为"已 compact" 而比 baseline 少)
