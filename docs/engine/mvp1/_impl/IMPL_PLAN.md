---
doc: impl-plan
status: drafted（2026-06-06;mvp1 设计对账完成后建立,待 CCB 恢复后开跑）
applies_standard: ../../../development/task-spec-standard.md
binds_design: ../INDEX.md · ../_impl-backlog.md（Gap 清单源）· ../_api-handshake-audit.md（studio 协同）
---

# Graph-Agent (Engine) MVP1 实施计划(大模块 + 并发分区)

> **原则**(同 `task-spec-standard`):大模块按**依赖**串,小模块按**文件归属**并发(IR1);baseline 实施后回写(IR6);目标机制以各 `alignment` 为唯一真理(IR5)——本计划只排**顺序 + 并发 + 文件锁**,Gap 明细见 [`_impl-backlog.md`](../_impl-backlog.md)。
> **前置**:实施 = 写代码 = Codex/Gemini;**当前 CCB 桥接断**,需先恢复。
> **跨模块依赖(与 gateway 不冲突)**:`create_agent`(WS-E1)绑 `model=GatewayChatModel` → 依赖 gateway 保住该类(gateway `IMPL_PLAN §五` 已承诺"本批不碰 engine、保 GatewayChatModel 稳");**可并行**,gateway 核心(WS-1)先落更稳。

## 一、为什么不是全并发:engine 核心耦合在 graph_assembler.py
`core/graph_assembler.py` 是**共享热点文件**——create_agent 构造(`:437-576`)、节点级 batch(`:240-300`)、11-io 接线(`:287`)、LOGIC 节点(`:325`)、subagent 派发(`:1057+`)**全在它里面**。所以真正能并发的是**碰不同文件**的工作(错误契约 V2 / V4 事件 / purity / 中间件槽 / 退出闸),`graph_assembler.py` 的改动只能当**一条串行链**(WS-E1)。这与 gateway 把 `gateway_chat_model.py`/`client_manager.py` 当串行热点同构。

## 二、依赖图
```
WS-E1 create_agent 核心(graph_assembler.py 串行链:create_agent→6槽接线→LOGIC-clean→iterate→11-io)
  ├─→ WS-E2 中间件后3槽(tracing/tool_error/loop_detection no-op→实现;链在 E1 接好)
  ├─→ WS-E5 checkpoint 内层(ns/agent 挂共享 base;create_agent 传 checkpointer 后)
  ├─→ WS-E8 退出闸(after_agent 闸接 create_agent)
  └─→ (gateway WS-1 GatewayChatModel 稳 ── soft 依赖,可并行)
WS-E3 错误契约 V2(exceptions/error_registry/result)──────── 并发(独立文件)
WS-E4 V4 trace 事件(events.py/emit.py)──────────────────── 并发(与 E2 共享 tracing.py → 协调)
WS-E6 purity 扩展(purity.py;注册码与 E3 协调)──────────── 并发
WS-E7 golden / resume(runner.py + golden SDK)──────────── 需 studio 协同,最后
```

## 三、工作流分区(按文件归属,IR1;exact owns_files 在各 WS 任务书 pin)
| WS | 名 | backlog | owns_files(主) | 依赖 | 并发性 | 优先级 |
|---|---|---|---|---|---|---|
| **WS-E1** | create_agent 核心 | K1/K2/I1/I3/I5 | `core/graph_assembler.py` · `middleware/factory.py`/`__init__.py` | gateway WS-1(soft) | **内部串行**(热点) | P0 关键路径 |
| **WS-E2** | 中间件后 3 槽 | A1/A2 | `middleware/tracing.py`/`tool_error.py`/`loop_detection.py` | WS-E1(链接好) | 并发(E1 后) | P1 |
| **WS-E3** | 错误契约 V2 | V2a-d | `core/exceptions.py`/`error_registry.py`/`result.py` | 无 | **全并发** | P0-1→P2 |
| **WS-E4** | V4 trace 事件 | S7 + V2a(DiagnosticEmitted) | `callbacks/events.py`/`emit.py` | 与 E2 共享 `tracing.py`→协调 | 并发 | P1 |
| **WS-E5** | checkpoint 内层 | A3/A4 | `core/checkpointer.py`/`state.py`(data delta) | WS-E1 | 串行,E1 后 | P1 |
| **WS-E6** | purity 扩展 | I2/I6 | `core/purity.py`(+ `error_registry` 注册码→与 E3 协调) | 无 | **全并发** | P1 |
| **WS-E8** | 退出闸 | I4 | `middleware/nudge_injector.py` + exit-control middleware | WS-E1 | 并发(E1 后) | P1 |
| **WS-E7** | golden/resume(studio 协同) | S5/S6 | `core/runner.py`(resume)· golden 逐节点 SDK | **studio**(3 P0 + U10 + C2) | 最后 | P2 |

## 四、WS-E1 内部子步骤(graph_assembler.py 严格串行)
0. (前置)gateway `GatewayChatModel` 可用(gateway WS-1 保稳)。
1. **create_agent 构造**(K1/K2):手写 ReAct loop(`graph_assembler.py:483-576`)→ `create_agent(model,tools,middleware,checkpointer)` 一次构造 + invoke;`_build_skill_node`(`:437`)收口,tools 直接交 create_agent(不手动 bind_tools)。
2. **6 槽中间件接线**(A1):`build_middleware_chain` 6 槽接进 AGENT(现单槽 `:300`/`factory.py:68`)。
3. **LOGIC 干净契约**(I1/LE1-3):`_build_logic_node`(`:325`)纯返回 / 砍 Context mutation / 硬禁 run_skill·FS。
4. **iterate 执行**(I3):节点级 loop(accumulate)/ 图级 batch(`Send`)/ 图级 loop=B(`:240-300` 扩)。
5. **11-io 接线**(I5):子图 io 放宽(`loader.py:528`)/ 文件导入→黑板(`:287` 前置步)/ artifact 路径标注。

## 五、本批不做(范围锁定)
- **studio 侧 3 个 P0**(run 路径:SKILL.md→root / workspace 双层 / 假成功)= studio 团队,本计划只**路由**(见 `_api-handshake-audit` B1)。
- **U10 api-contract HTTP 路由** = studio owns;engine 侧契约已成段(`03-api-contract`)。
- **错误 V2 P1/P2**(i18n / 生命周期 / 分页)= 后续,不进首批(P0-1→P0-3 先)。
- **gateway 内部** = gateway IMPL_PLAN,本计划不碰(只依赖 GatewayChatModel 接口)。

## 六、执行波次(CCB 恢复后)
- **Wave 1(并发起步)**:WS-E1 步骤1(create_agent)+ WS-E3(错误 V2 P0-1)+ WS-E6(purity)同开(碰不同文件)。
- **Wave 2**:WS-E1 步骤2→3→4→5(串行,关键路径)+ WS-E4(events)挂旁边并发。
- **Wave 3**:WS-E2 / WS-E5 / WS-E8(均依赖 E1 链)。
- **Wave 4**:WS-E7(studio 协同:P0 修完 + U10 对齐 + resume/golden)。
- 每 WS 完成 = 测试绿 + 验收清单逐条勾 + 回写 baseline + Claude 终审,再进依赖它的 WS。

## 七、CCB 恢复前已就绪产物
- 任务书标准:`../../../development/task-spec-standard.md`(沿用 gateway 已建)。
- Gap 清单:`../_impl-backlog.md`(各模块 §8 refactor-target → 任务)。
- 本实施计划:本文件。
- WS 任务书:**WS-E1(keystone)待产**(对标 gateway `WS1-chatx-core.md`);WS-E2…E8 同模板待产。
