---
doc: _impl-backlog
status: backlog（2026-06-06;设计内容已齐,把各模块"impl 归 kiro"的 Gap 工单化,待 CCB 恢复后委派 codex）
owns: engine mvp1 实施任务清单(分层 + 依赖 + 落点),codex/kiro 执行入口
audience: 架构师(派单)+ codex(执行);待 daemon 恢复
related: INDEX.md（设计单元台账）· 各模块 mvp1-alignment.md §8（impl-target 来源）· _api-handshake-audit.md（studio 协同）
---

# Engine MVP1 实施 Backlog(工单化)

> 设计文档内容已齐(12/12 模块 A 达标);本文把各模块 `§8 impl 归 kiro` 的 Gap 拆成**可派 codex 的任务**,按**依赖分层**排。CCB daemon 恢复后从 Tier 0 起派单。
> **不在此锁文档**:codex 跑通骨架前不扩大 audited-ready 哈希锁(防"设计未验证就锁死→改一行测试就挂"的返工摩擦;且 engine 文档现无并发改动、防漂收益≈0)。
> 每条:**模块 · 做什么 · 落点(file:line)· 依赖**。

## Tier 0 — keystone(先做;middleware/checkpoint 内层/tool binding 全挂它)
| # | 模块 | 任务 | 落点 | 依赖 |
|---|---|---|---|---|
| K1 | `01-agent-loop` | 手写 ReAct loop → `create_agent(model, tools, middleware, checkpointer)` 一次构造 + 一次 invoke | `graph_assembler.py:483-576`(待替换) | — |
| K2 | `03-assemble` | `_build_skill_node` 收口 create_agent 构造;tools 直接交 `create_agent`(不再手动 `bind_tools`) | `graph_assembler.py:437-562` | K1 |

## Tier 1 — 挂 create_agent(K1/K2 后)
| # | 模块 | 任务 | 落点 | 依赖 |
|---|---|---|---|---|
| A1 | `02-middleware` | 6 槽 `build_middleware_chain` 接进 live AGENT(现只接单槽);后 3 槽 Tracing/ToolError/LoopDetection no-op → 实现 | `factory.py:29`/`:68`;`tracing.py`/`tool_error.py`/`loop_detection.py`(各 16 行) | K1 |
| A2 | `04-tools` | ToolError:工具异常 → error ToolMessage 喂回 LLM、不崩 phase(逻辑本域,实现在 middleware 槽 5) | `middleware/tool_error.py`(no-op) | A1 |
| A3 | `03-checkpoint`(内层) | AGENT 经 `ns="<id>/agent"` 挂外层共享 base checkpointer(现 AGENT 分支不传 checkpointer) | `graph_assembler.py:201` | K1 |
| A4 | `03-cognitive` | rich 三态校验接 live(结构错→md-patch / 语义错→打回 / 业务错→validator);退役简化版 `cognitive/md2json` | `tools/md_to_json.py:515`;`cognitive/md2json.py` | K1 |

## Tier 2 — 独立轨(不依赖 create_agent,可并行)
| # | 模块 | 任务 | 落点 | 依赖 |
|---|---|---|---|---|
| I1 | `graph-exec`(LOGIC) | 干净契约 LE1-3:砍 Context mutation(纯返回)、`run_skill`→声明式 iterate/SUBGRAPH、FS/sys.path 硬禁 | `graph_assembler.py:_build_logic_node:325`;11 action drift | — |
| I2 | `01-compile`/`compile-rules` | purity 扫描器扩展硬禁 `run_skill`/FS/`sys.path`/import 越界(CR2/LE2) | `purity.py:44` | I1(契约) |
| I3 | `02-iterate` | 节点级 loop(accumulate)/ 图级 batch(`Send`)/ 图级 loop=B(引擎包 loop-body)/ range / 统一 `iterate` 配置 | `graph_assembler.py:240-300`(现仅节点级 batch) | A3(loop 累积 checkpoint) |
| I4 | `05-exit-control` | `after_agent` 退出闸(phase 不静默成功);finish_task 写 marker、闸放行 | `nudge_injector.py`;`cognitive_flow.py:511` | K1 |
| I5 | `graph-exec`(11-io) | 子图 io 放宽(删 inputs 1:1)/ 文件导入→黑板 lazy / io.outputs artifact 路径标注 | `loader.py:528`;`_wrap_phase_runtime_node:287` | — |
| I6 | `compile-rules` | 注册待加码进 `ERROR_REGISTRY`:`[F-v3-golden-stale-fields]`/`[F-v3-iterate-*]`(带全四轴) | `error_registry.py:15` | — |

## Tier 3 — 错误契约 V2(分期;权威 `compile-rules §3.1/§3.1.1`)
| # | 阶段 | 任务 | 落点 |
|---|---|---|---|
| V2a | P0-1 | `ErrorPayload.details`(+ 序列化异常 `context`)+ `RunResult.diagnostics`(有界:limit/truncated/counts)+ `DiagnosticEmittedEvent` | `exceptions.py:21`/`result.py:68`/`events.py` |
| V2b | P0-2 | `ErrorCodeMetadata` 改 dataclass + 加 `remediation`/`doc_ref`/`doc_url`/`details_schema`/`schema_version`;`GET /errors` 信封 | `error_registry.py:8` |
| V2c | P0-3 | 运行期码细分(tool/state-transform/persistence/provider),消 catch-all | `error_registry.py` |
| V2d | P1/P2 | `source_span`/`phase_path`/`location_requirements`(逐码软校验);i18n(`message_key`/`template_vars`);码生命周期 | — |

## Tier 4 — studio 协同(需 daemon / studio session)
| # | 项 | 任务 | 落点 |
|---|---|---|---|
| S1 | **[P0] studio run 路径** | 传 skill **root**(非 `SKILL.md`) | `apps/studio/.../run_manager.py:184` |
| S2 | **[P0] workspace_dir 双层** | 传 workspace 根(别 `run_dir.parent`)→ trace 落对 | `run_manager.py:97` |
| S3 | **[P0] worker 假成功** | 按 `result.success` 置 status、失败落 `result.error` | `run_manager.py:95→111` |
| S4 | U10 双边会签 | `03-api-contract` 与 studio 敲定(尤其 Error V2 payload);B baseline 补深 | `03-api-contract` |
| S5 | resume | Engine `resume_skill` 已实现;剩余 Studio `resume_run`(501→thin route):投影请求→选 checkpoint→调用 Engine API | `runs.py:69`;`runner.py` |
| S6 | per-node golden | Engine `evaluate_golden_baseline` 已实现;剩余 Studio F5 消费 report + 空 template / predict 拦截搬引擎后续 | `06-golden-eval`;Studio UI/API |
| S7 | V4 trace 事件 | `parent_node_id`/`node_type`(微观)/ 3 边操作事件 / `phase_execution_id`+`iteration`(逐轮)/ subagent lifecycle | `events.py`;middleware Tracing 槽 |

## Tier 5 — 收尾 / 死代码
| # | 模块 | 任务 |
|---|---|---|
| C1 | `07-runtime` | bootstrap 文档化;死簇 `GraphAgentHarness` 引用清净(`core/harness.py` 已删) |
| C2 | `data-contracts` | 物理抽 `core/` → 零依赖 L0 叶 |
| C3 | `02-resolver` | `LocalWorkspaceResolver` 函数体改绝对 path 边界/合法性校验(退 registry 旧语义) |
| C4 | `01-compile` | 死簇清理(`code_phase_node`/`phase_executor` 等) |
| C5 | done 2026-06-28 | 历史迁移源已删除；正式模块文档和 `skill-spec/00-FORMAT-GROUND-TRUTH.md` 为当前入口 |

## 派单序(daemon 恢复后)
K1→K2(keystone)→ 并行 [Tier 1 挂 create_agent] + [Tier 2 独立轨] → Tier 3 错误 V2(P0-1 起)→ Tier 4 需 studio 协同(S1-S3 现在就可路由)→ Tier 5 收尾。
> Tier 4 的 S1-S3(3 个 P0)= studio 侧、**现在就能路由**,不必等 daemon。
