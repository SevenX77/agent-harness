---
doc: impl-plan
status: living（2026-06-10 回写:WS-E1/E1-io/E2/E3/E4/E5/E6/E7/E8 首批 Engine 功能链均已实现;剩余为 CI/质量门、Studio 消费接线与后续 backlog）
applies_standard: ../../../development/task-spec-standard.md
binds_design: ../INDEX.md · ../_impl-backlog.md（Gap 清单源）· ../_api-handshake-audit.md（studio 协同）· ./WS-E1-create-agent-core.md
---

# Graph-Agent (Engine) MVP1 实施计划(大模块 + 并发分区)

> **原则**(同 `task-spec-standard`):大模块按**依赖**串,小模块按**文件归属**并发(IR1);baseline 实施后回写(IR6);目标机制以各 `alignment` 为唯一真理(IR5)——本计划只排**顺序 + 并发 + 文件锁**,Gap 明细见 [`_impl-backlog.md`](../_impl-backlog.md)。
> **当前事实(2026-06-10)**:WS-E1 串行链、WS-E1-io、WS-E2、WS-E3 P0-1/P0-2、WS-E4、WS-E5、WS-E6、WS-E8 已合入 `main`;WS-E7 golden/resume 已在 Engine 侧实现为通用 public API。Engine MVP1 首批功能 WS 已收敛,剩余是 CI/质量门、Studio 薄接线以及 P0-3/P1/P2 等后续 backlog。
> **跨模块依赖(与 gateway 不冲突)**:`create_agent`(WS-E1)绑 `model=GatewayChatModel` → 依赖 gateway 保住该类(gateway `IMPL_PLAN §五` 已承诺"本批不碰 engine、保 GatewayChatModel 稳");**可并行**,gateway 核心(WS-1)先落更稳。

## 一、为什么不是全并发:engine 核心耦合在 graph_assembler.py
`core/graph_assembler.py` 是**共享热点文件**——create_agent 构造(`:437-576`)、节点级 batch(`:240-300`)、11-io 接线(`:287`)、LOGIC 节点(`:325`)、subagent 派发(`:1057+`)**全在它里面**。所以真正能并发的是**碰不同文件**的工作(错误契约 V2 / V4 事件 / purity / 中间件槽 / 退出闸),`graph_assembler.py` 的改动只能当**一条串行链**(WS-E1)。这与 gateway 把 `call/chat_model.py`/`call/clients.py` 当串行热点同构。

## 二、依赖图
```
WS-E1 create_agent 核心(graph_assembler.py 串行链:create_agent+运行边界(state_schema/finish_task/thread_id-ns/max_iter)→subagent重接→LOGIC-runtime→iterate→子图io放宽)
  ├─→ WS-E2 中间件后3槽(tracing/tool_error/loop_detection no-op→实现;链在 E1 接好) ✅
  ├─→ WS-E5 checkpoint 内层(ns/agent 挂共享 base;create_agent 传 checkpointer 后) ✅
  ├─→ WS-E8 退出闸(after_agent 闸接 create_agent) ✅
  └─→ (gateway WS-1 GatewayChatModel 稳 ── soft 依赖,可并行)
WS-E1-io 11-io 文件导入lazy(E2)+ artifact business_data_md(E3)── 依赖 E4(InputFileInjectedEvent)+E5(StateManager.update_business);跨 read_file/storage/runner(从 E1 拆出,IR1) ✅
WS-E3 错误契约 V2(exceptions/error_registry/result)──────── P0-1/P0-2 已完成;P0-3/P1/P2 后续 backlog
WS-E4 V4 trace 事件(events.py/emit.py)──────────────────── runtime edge events 已完成 ✅
WS-E6 purity 扩展(purity.py;run_skill 扫描码;注册码与 E3 协调)─ 已完成 ✅
WS-E7 golden / resume(runner.py + golden SDK)──────────── Engine public API 已实现 ✅;Studio HTTP/UI 薄接线后续
```

## 三、工作流分区(按文件归属,IR1;exact owns_files 在各 WS 任务书 pin)
| WS | 名 | backlog | owns_files(主) | 依赖 | 并发性 | 优先级 |
|---|---|---|---|---|---|---|
| **WS-E1** | create_agent 核心 | K1/K2/I1/I3/I5(子图io) | `core/graph_assembler.py` · `middleware/factory.py`/`__init__.py` · `middleware/cognitive_flow.py`/`cognitive/finish_task.py` · `core/loader.py` | gateway WS-1(soft)· E6 run_skill | 已完成 | ✅ |
| **WS-E1-io** | 11-io 文件导入/artifact | I5(E2/E3) | `graph_assembler.py` · `tools/builtin/read_file.py` · `io/manager.py`/`io/storage.py` · `core/runner.py` | WS-E4 + WS-E5 + E1 | 已完成 | ✅ |
| **WS-E2** | 中间件后 3 槽 | A1/A2 | `middleware/tracing.py`/`tool_error.py`/`loop_detection.py` | WS-E1 | 已完成 | ✅ |
| **WS-E3** | 错误契约 V2 | V2a-b 已落;V2c-d 后续 | `core/exceptions.py`/`error_registry.py`/`result.py` | 无 | P0-1/P0-2 已完成 | ✅/后续 |
| **WS-E4** | V4 trace/runtime edge events | S7 + runtime edge events | `callbacks/events.py`/`emit.py`/`core/graph_assembler.py` | 与 E1-io 协调 | 已完成 | ✅ |
| **WS-E5** | checkpoint 内层 | A3/A4 | `core/checkpointer.py`/`state.py`/`graph_assembler.py` | WS-E1 | 已完成 | ✅ |
| **WS-E6** | purity 扩展 | I2/I6 | `core/purity.py` | 无 | 已完成 | ✅ |
| **WS-E8** | 退出闸 | I4 | exit-control middleware · `graph_assembler.py` | WS-E1 | 已完成 | ✅ |
| **WS-E7** | golden/resume(Engine-first) | S5/S6 | `core/runner.py` resume API · `core/_predict_internal/golden_eval.py` · public API/tests | 已合 E1/E5/E1-io/E4;Studio 作为消费者后续薄接线 | 已实现 | ✅ |

## 四、WS-E1 内部子步骤(graph_assembler.py 严格串行)
0. (前置)gateway `GatewayChatModel` 可用(gateway WS-1 保稳)。
1. **create_agent 构造**(K1/K2):手写 ReAct loop(`graph_assembler.py:483-576`)→ `create_agent(model,tools,middleware,checkpointer)` 一次构造 + invoke;`_build_skill_node`(`:437`)收口,tools 直接交 create_agent(不手动 bind_tools)。
2. **6 槽中间件接线**(A1):`build_middleware_chain` 6 槽接进 AGENT(现单槽 `:300`/`factory.py:68`)。
3. **LOGIC 运行时契约**(I1/LE1-3,scope 降级):`_build_logic_node`(`:325`)纯返回 / 砍 Context mutation / **FS·import 越界 FATAL(现成)**;**`run_skill` 禁令归 E6**(ordering:E6 先于本步,或本步显式降级、不声明完整 LOGIC 干净——见 WS-E1 §8)。
4. **iterate 执行**(I3):节点级 loop(accumulate)/ 图级 batch(`Send`)/ 图级 loop=B(`:240-300` 扩)。
5. **11-io 子图 io 放宽**(I5,收敛):仅子图 io 放宽(`loader.py:528` 删 inputs 1:1)。**文件导入→黑板 lazy(E2)+ artifact business_data_md(E3)拆出 → WS-E1-io**(跨 read_file/state.py(E5)/events(E4)/storage/runner,owns 必相交违 IR1)。

## 五、本批不做(范围锁定)
- **studio 侧 3 个 P0**(run 路径:SKILL.md→root / workspace 双层 / 假成功)= studio 团队,本计划只**路由**(见 `_api-handshake-audit` B1)。
- **U10 api-contract HTTP 路由** = studio owns;engine 侧契约已成段(`03-api-contract`)。
- **错误 V2 P1/P2**(i18n / 生命周期 / 分页)= 后续,不进首批(P0-1→P0-3 先)。
- **gateway 内部** = gateway IMPL_PLAN,本计划不碰(只依赖 GatewayChatModel 接口)。

## 六、执行波次(当前)
- **Wave 1-3**:已完成并合入 `main`。覆盖 WS-E1、WS-E1-io、WS-E2、WS-E3 P0-1/P0-2、WS-E4、WS-E5、WS-E6、WS-E8。
- **Wave 4**:WS-E7 golden/resume 已实现。Engine 侧以通用 SDK/API 为主:resume checkpoint 寻址续跑、`workspace_dir/golden` 逐节点读取/评估/报告。Studio 只消费 Engine 契约,不得反向定义 Engine。
- **非功能收尾**:main SonarCloud Quality Gate 聚合失败、#126 stale CI unblock PR 清理、旧 planning worktree 清理。这些是工程卫生项,不算新的 Engine 功能 WS。
- 每 WS 完成 = 测试绿 + 验收清单逐条勾 + 回写 baseline + 终审,再进入下一依赖链。

## 七、产物状态(2026-06-10)

- 任务书标准:`../../../development/task-spec-standard.md`(沿用 gateway 已建)。
- Gap 清单:`../_impl-backlog.md`(各模块 §8 refactor-target → 任务)。
- 本实施计划:本文件。
- WS-E1 任务书:`./WS-E1-create-agent-core.md`(已按 codex round-1/round-2 findings 返工;round-2/round-3 复核 prompt 已存档)。

| WS | 任务书 | 实现 | 状态 |
|---|---|---|---|
| **WS-E1** | `_impl/WS-E1-create-agent-core.md` + step requirements/tasks | 已合入 `main` 至 Step5 子图 IO 放宽 | ✅ |
| **WS-E1-io** | `.kiro/specs/engine-mvp1/requirements-ws-e1-io-runtime.md` | 已合入 `main`:file input lazy + `InputFileInjectedEvent` + file/artifact output + `business_data_md` | ✅ |
| **WS-E2** | `.kiro/specs/engine-mvp1/requirements-ws-e2-middleware-tail-slots.md` / task / prompt | 已合入 `main`:Tracing/ToolError/LoopDetection 后 3 槽 | ✅ |
| **WS-E3** | P0-1/P0-2 requirements/tasks | 已合入 `main`:diagnostics snapshot + purity hard bans同批历史;error catalog metadata export | ✅ P0-1/P0-2;P0-3/P1/P2 后续 |
| **WS-E4** | `.kiro/specs/engine-mvp1/requirements-ws-e4-runtime-edge-events.md` / task / prompt | 已合入 `main`:InputDispatch/BlackboardReduce/InputFileInjected runtime edge events | ✅ |
| **WS-E5** | `.kiro/specs/engine-mvp1/requirements-ws-e5-checkpoint-inner.md` / task / prompt | 已合入 `main`:AGENT 内层 checkpoint namespace + graph iterate namespace 组合 | ✅ |
| **WS-E6** | `.kiro/specs/engine-mvp1/requirements-ws-e6-purity-extensions.md` / task / prompt | 已合入 `main`:compile-time purity hard bans | ✅ |
| **WS-E8** | `.kiro/specs/engine-mvp1/requirements-ws-e8-exit-gate.md` / task / prompt | 已合入 `main`:ExitControl gate + iteration leak fix | ✅ |
| **WS-E7** | `.kiro/specs/engine-mvp1/requirements-ws-e7-golden-resume.md` / task / prompt | 已实现:public `resume_skill(...)` + `evaluate_golden_baseline(...)`;`workspace_dir/golden/<baseline_id>` 逐节点评估报告 | ✅ |

> 派单入口仍以本计划 §六 的波次为准;每个 WS 落地时,先按 `task-spec-standard` 写任务书,再执行 RED→GREEN→baseline 回写→终审。
