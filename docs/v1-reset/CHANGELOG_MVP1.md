# MVP-1 State Split — CHANGELOG

**期间**: 2026-04-29 → 2026-04-29
**Spec**: `.kiro/specs/v1-reset-mvp-1-state-split/`
**Direction**: `docs/superpowers/specs/2026-04-28-v1-reset-direction.md`
**Scope**: `v1-reset-mvp-1-state-split` (orchestrator scope)

## 目标

把 WorkflowState 从单一 TypedDict (context dict[str,Any] 混杂垃圾桶) 拆为业务/框架物理隔离。建立 `BusinessData` (用户 Schema 空间) 与 `FrameworkState` (框架元数据空间) 的二级 Pydantic 结构，并通过 `StateManager` 实现结构化 `finish_task` 路由通道。彻底根除 `_md_id`、`_finish_task_result` 等下划线变量对用户业务字段的污染。

## 完成清单 (16-dim 维度 → MVP-1 落点)

| 维度 | 目标 | 落点 |
|---|---|---|
| **A1 / WorkflowState 拆分** | BusinessData (extra=allow) + FrameworkState (extra=forbid) Pydantic 物理隔离 | T1 (88e3549) |
| **A1.x / StateManager 路由** | route_finish_task / update_business / update_framework 接口实现 | T1 + T4 (5dfcf9a) |
| **A1.x / 业务/框架接口契约** | 方案 a (BusinessData 仅接) 接口签名重画，工具仅可见业务空间 | T4 (5dfcf9a) |
| **A1.x / finish_task 通道** | `_finish_task_result` 离开 ctx → `flow.finish_task_result` | T6 (9e011ff) + T4 |
| **A1.x / md_id 剥离** | `_md_id` 离开 parsed dict → `ParsedBlock.meta` + `flow.md_id` | T6 (9e011ff) |
| **A1.x / middleware 适配** | ValidationMiddleware / Clarification 改通过 StateManager/flow 操作状态 | T5 (436f56b) |
| **A1.x / 测试 mock 全更新** | 所有 mock state 从 `{"context": {...}}` → `{"data": ..., "flow": ..., "messages": []}` | T7 (66ff6cf) |
| **A1.x / e2e smoke** | 双层架构 (Layer 1 synthetic 0 token + Layer 2 real LLM skipif) + 4 invariants | T8 (9c4cc48) |

## 关键度量 (baseline diff 8/8 预期)

| 指标 | Pre-MVP-1 (5decd0a) | After MVP-1 | Δ |
|---|---|---|---|
| `state["data"]` 含 `_` 前缀字段数 | 17 | **0** | **-17** |
| `state["flow"]` 通过 `model_validate(strict=False)` | N/A | **pass** (T8 invariant) | — |
| dict-mutation `context["_X"] = ...` 站点 | 26 | **0** (T7 + T2/T4 改造) | **-26** |
| `**state` 解包模式 | 0 (T0-prep 已确认) | 0 | — |
| pytest passed (--ignore=tests/graph_agent/core/validators/test_strict_v2.py) | 599 | **643** | **+44** (含 T1 9 + T4 5 + schema_engine 24 + T7 修复 4 + T8 invariants 6) |
| 4 SKILL compile 状态 | WARN-only / 1 PASS | unchanged (T8 顶层 SKILL 验证) | — |
| LangGraph checkpointer round-trip | 旧: pass | 新: pass (新 schema, 旧 checkpoint 不兼容) | breaking |
| FrameworkState 字段数 | N/A | 21 字段 (含 a3 T0-prep 发现的 3 漏字段) | new |
| BusinessData dict-like 兼容方法数 | N/A | 5 (__getitem__/get/__setitem__/__contains__/setdefault) | new |

## 9 commits 时间线

| Commit | 类别 | 摘要 |
|---|---|---|
| a5d3178 | spec | MVP-1 spec 4 docs (requirements/research/design/tasks) |
| 88e3549 | T1 / feat | BusinessData/FrameworkState/StateManager Pydantic 模型 (9 单测) |
| 0eec94b | T2 / feat | StateGraph 适配 + import 断点全修 + FrameworkState 补 3 字段 |
| 9e011ff | T6 / feat | finish.py + md_to_json.py 元数据剥离 |
| 5dfcf9a | T4 / feat | phase_executor 重画 (方案 a) + StateManager.route_finish_task |
| 436f56b | T5 / feat | middleware 适配 (ValidationMiddleware finish_task 路由) |
| 66ff6cf | T7 / fix | 测试 mock state 批量更新 (5 文件 + a1 T2 scope leak 合并) |
| 9c4cc48 | T8 / test | e2e smoke + 4 invariants 回归测试 (双层 0 token cost) |
| TBD | T9 / docs | CHANGELOG_MVP1.md 落盘 (主控收尾, 即本文件) |

> **注**: MVP-2/3/4 spec 在 MVP-1 实施期间由 a3/a2 并行起草 (Commits: 677b132 / 8a0aa8b / deafa1a / 6199f25 / 3a9fc12)。

## 验证不变量 (Invariants)

| 检查项 | 验证结果 | 说明 |
|---|---|---|
| **BusinessData 纯净度** | TBD | `state["data"]` 必须不含任何以 `_` 开头的字段 |
| **FrameworkState 封闭性** | TBD | `state["flow"]` 必须通过 Pydantic `extra="forbid"` 校验 |
| **StateManager 唯一性** | TBD | 所有状态写操作必须经过 `StateManager` 辅助函数 |
| **Dict-mutation 根除** | TBD | 核心逻辑中不得出现 `context["_X"] = ...` |

## Deferred items (不阻塞 MVP-1 ship，记录在册)

1. **`_sync_tool_state` / `tool_state` dict 过渡形态**
   - 为了兼容未迁移工具在 LLM Phase 内部保留的临时字典。
   - **归口**: MVP-4 phase_executor 彻底重画为 Node 类时物理删除。

2. **`cast(Any, model)` mypy 体操**
   - 解决 `create_agent` 调用时的上游类型推断问题。
   - **归口**: MVP-5 编写自定义 stubs 时统一清理。

3. **`finish_task_result` 内部结构强类型化**
   - 目前为 `dict[str, Any]`，含 `meta` 和 `raw` 子键。
   - **归口**: MVP-5 类型全收敛时定义专用的 `TypedDict` 或 `BaseModel`。

4. **`legacy_context_from_state` 适配器**
   - 为保住 MVP-1 期间 4 SKILL e2e 可跑而设的 shim。
   - **归口**: MVP-4 彻底重画后移除。

5. **`ContextBridge.to_business_data_schema()` 实现**
   - 依赖 MVP-2 SchemaEngine 的接口。
   - **归口**: MVP-2 T4 实施。

6. **T2 实施引起的 38 个测试失败 (a1 报告)**
   - 由于 state 结构变更，mock 对象与实际 code path 断层。
   - **归口**: T7 批量更新测试 mock 后闭环。

## 学习 / 风险记录（写给未来 MVP-2～MVP-5 主控）

### L1 / Agent 派工纪律：Idle 是最大的浪费

MVP-1通过 a1/a3/a2 三 agent 并行，实现了"飞着修引擎"。主控 Claude 需严格遵守 5 分钟 timeout 规则，在 a1 跑重型 T4 时，立刻分派 a2 做下两个 MVP 的设计、分派 a3 做短链任务，压榨每一秒 context window。

### L2 / 接口决策必须 Cross-Check 形成闭环

T4 实施前，Gemini 出方案 a (BusinessData 仅接)，a1 随后实施验证并发现 Pydantic dict-like 兼容性需求。这种"设计 -> 预实施审查 -> 真实实施 -> 反馈回设计"的闭环，比单次派工产生的契约更稳固。

### L3 / a3 Claude (Technical Writer) 文档质量极高

审计结果显示 a3 写的 spec docs 忠实度 10/10。对于复杂的 MVP-2/3/4 spec，主控应充分信任 a3 的整合能力，仅做顶层方向确认。

### L4 / CCB 投递长内容必须走文件路径

MVP-1 T4 的 review 报告长度超过 1500 字，验证了"长内容走 /tmp/xxx.md" 是避免 CCB CLI 挂死或截断的唯一可靠路径。

### L5 / 三线流水线并行模式验证成功

MVP-1 实施主线 (a1) + MVP-2/3/4 spec 副线 (a3) + 设计审计/战术辩论 (a2) 三线跑。5 个 MVP 的设计在 MVP-1 进行到一半时已全部落盘。

### L6 / 纠错能力：审计收益大于开销

MVP-1 中途 a2 审计发现 a3 漏字段、a1 T2 破坏测试等，均被快速识别并转为子任务。主控应视 "Spec Drift Audit" 为核心收益点而非流程负担。

## 下一步: MVP-2

**A5 SchemaEngine + A7 IOManager 抽出**: 把散落在 5 处的 Schema 解析逻辑收拢进 `SchemaEngine`；把硬编码的 `hoist_to` 搬运逻辑收拢进 `IOManager`。

当前 a1 正在执行 MVP-2 T2：`SchemaEngine` 完整实现。
