# graph_agent v1-reset (Phase 1) — 核心引擎基建就绪

## TL;DR

本次发布 (`feat/v1-reset-mvp-1` 分支, `5decd0a..HEAD` 共 38 commits) 落盘了 v1-reset 6-MVP roadmap 中的 **MVP-1 + MVP-2 + MVP-3** 三个阶段，对应"状态拆解 / 独立基础设施 / 加载与中间件模块边界"。这是一次**架构过渡期 (Phase 1)** 的中间发布——核心类型安全组件已就绪并就位，但执行控制流仍由 legacy `phase_executor` 驱动。**v1.0.0 的全盘替换将在 MVP-4 + MVP-5 完成**。

请将本次发布理解为"地基稳了，上层结构未半"，不要按终态 1.0.0 期待。

---

## 本次落盘的工作

### MVP-1: WorkflowState 物理拆分

- 引入 `BusinessData` (extra=allow，承载 SKILL 业务字段) 与 `FrameworkState` (extra=forbid，23 字段，承载 finish_task_result / io_errors / retry_feedback / nudge_counts / history_results 等框架元数据)，与 `messages` 共同组成新的 3-key `WorkflowState` TypedDict
- `StateManager` 提供 `update_business / update_framework / route_finish_task` 三类型化 helper 替代直接 `state["context"][...] = ...` dict mutation
- 拦截层（`StateManager` + `ProtocolValidationMiddleware`）已就位，保证 `state["data"]` 内不再夹带 `_` 前缀的框架元数据

### MVP-2: SchemaEngine + IOManager 抽出

- `SchemaEngine.parse_from_md` → `SchemaObject` → `get_pydantic_model` / `validate` / `get_json_schema` 收口（lru_cache 128，`SchemaParseError` 统一异常出口）
- `IOManager.io_specs` + `resolve_hoist` → `HoistResult`，`io_errors` 改为实例级累积器（替代之前散落在 `context["_io_errors"]` 的写法）
- `ContextBridge.to_business_data_schema(schema_engine)` 让 `adopted_persona` 子树也走统一引擎
- `finish.py` 接入 `SchemaEngine` + `IOManager`，`md_to_json.parse_md` 区分"格式合法的空"vs"解析失败"，`business_data_parsed: list[dict]` 取代之前直接把 markdown 字符串塞进 validator 的旧路径

### MVP-3: Loader 三阶段 Pipeline + 4 middleware 模块化

- `SkillLoader` god class 拆为三阶段 Pipeline (`parse_skill_md` → `validate_manifest` → `build_graph_nodes`)
- 引入 `Bootstrap` 模块统一 `apply_patches() / load_settings()` / `Settings.from_env()`，`runner.main()` 启动期不再调散落的 `os.environ[...]` 副作用
- 新增 `graph_agent.middleware` 包含 4 个单职责中间件类：
  - `ProtocolValidationMiddleware` (T7) — 状态契约守卫 (BusinessData / FrameworkState / SchemaEngine.validate)
  - `CognitiveFlowMiddleware` (T8) — finish_task 拦截 + Clarification 路由
  - `ExecutionControlMiddleware` (T9) — 迭代计数 / dead-end pruning / 轻量 loop 检测 / metrics 聚合
  - Logging slot 4 预留 (设计 §5.6)
- `DEFAULT_MIDDLEWARE_ORDER: tuple[type, ...]` 拓扑序锁住 (`tests/graph_agent/middleware/test_chain_topology.py` 钉死)

---

## 真实指标 (限本次新增模块)

| 指标 | 数据 | 备注 |
| :--- | :--- | :--- |
| `SchemaEngine` 单测覆盖率 | **95.20%** | `tests/graph_agent/core/test_schema_engine.py` 51+ tests |
| `IOManager` 单测覆盖率 | **98%** | `tests/graph_agent/io/test_io_manager.py` 11 新 tests |
| `BusinessData` / `FrameworkState` 物理拆分 | **完成** | 拦截层（StateManager + ProtocolValidationMiddleware）0 污染回退 |
| Loader 三阶段拆分 | **完成** | `parse_skill_md / validate_manifest / build_graph_nodes` 三模块就位 |
| 中间件 4-模块化 | **3/4 就位 + 1 slot 预留** | `DEFAULT_MIDDLEWARE_ORDER` 拓扑序锁住 |
| 新增模块 mypy --strict | **zero issues** | 仅适用本次新增的 16 文件（`schema_engine.py` / `state.py` / `middleware/*.py` / `loader pipeline 三模块` 等） |
| MVP-2 集成测试 | **14 tests** | `tests/graph_agent/integration/test_mvp2_schema_io.py` |
| MVP-1 e2e smoke (compile + invariants 层) | **9 tests pass** | `tests/graph_agent/integration/test_mvp1_smoke.py` |

> 这里的指标**只针对本次新增 / 重画的模块**。**全库 ruff / mypy / coverage 统计仍有历史 baseline 残留**，未在本次清零，不在此声称。

---

## Known Limitations / Pending MVP-4 & MVP-5

当前版本为架构过渡期 (Phase 1)。新引擎的类型安全组件已就绪并处于影子/并行校验模式，实际控制流暂由 legacy `phase_executor` 驱动。v1.0.0 的全盘替换将在 MVP-4 + MVP-5 完成：

### MVP-4 待办
- 重画 `phase_executor.py` while 循环消费新 `PhaseNode` + Middleware
- 物理抹除 `cognitive/middlewares.py` 与 `cognitive/clarification_middleware.py` (当前仍被 `phase_executor.py:610/625` 直接 import 使用，是 T11 砍除被推迟到 MVP-4 的根因)
- `context["_X"]` 残留 12 处（分布在 `harness.py` / `cognitive/ambiguity.py` / `cognitive/memory.py` / `tools/builtin/context_access.py` / `tools/md_to_json.py` 等）随 phase_executor 重画一并迁移到 `FrameworkState`
- T12 集成压测：4 SKILL e2e (text-segmentation / event-extraction / batch-analysis / global-synthesis) + Loop detection 边界 + 启动延迟 ≥ 20% 改善

### MVP-5 待办
- 全库 ruff 69 errors 拍平（`personas.py` F821 + UP037 已在本 PR 修，余 68 推 MVP-5）
- 全库 mypy --strict (核心目录之外的非新增文件)
- coverage 提升至全库 ≥ 95% 的目标
- 最终 release notes 升级为 1.0.0，正式宣发"v1-reset 完整 ship"

---

## 不在本次发布范围内的事

为避免误读，明确声明本次**没有**做以下事情，不要按 1.0.0 终态指标审核：

- ❌ "全库 0 ruff warnings" — 全库 ruff 仍有 baseline warning，未清零
- ❌ "全库 95% coverage" — 仅新增模块达标
- ❌ "全库 0 `context['_X']` 残留" — 仍有 12 处残留，分布在 cognitive / tools / harness
- ❌ "MVP-4 / MVP-5 已完成" — phase_executor 重画推 MVP-4
- ❌ "1.0.0 final release" — 本次为 Phase 1 中间发布

---

## Migration Guide (本次落盘部分)

### 1. SKILL.md 升级路径
```yaml
# v0/v1/v2 (Legacy)
mode: code_only
output_schema: ... # 散装解析

# v3 (本次落盘版本可消费的 schema_version 2.0)
schema_version: "2.0"
skill_type: graph
phases:
  - name: my_logic
    mode: logic  # 更名
```

### 2. 调用方升级 (Harness API)

`Harness.run` 签名在本次重画中**未**最终锁定（这是 MVP-5 的工作）。当前调用方继续按既有 signature 使用即可，1.0.0 正式发布时会一次性宣发 API 契约。

### 3. 数据迁移警告

由于 `WorkflowState` 顶层字段从 `context` 拆分为 `data` (业务) + `flow` (框架) + `messages`，旧版本 LangGraph checkpoint 在新模型下反序列化将失败。Phase 1 阶段建议清空旧 checkpoint 存储后再使用。

---

## AI 协作模式致谢

本次 38 commits 由 a1 (codex executor) / a2 (gemini analyst+reviewer) / a3 (claude executor 副) / 主控 Claude (orchestrator+designer) 通过 CCB 异步协作完成。

`v1-reset (Phase 1)` 是首个完全通过 **多 Agent 异步并行流水线** 重构的 graph_agent 大版本。在 Phase 2 (MVP-4 + MVP-5) 完成后，将发布 1.0.0 final 时再做完整效能数据复盘。
