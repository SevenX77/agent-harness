# v1-reset Phase 1 Retrospective (MVP-1 + MVP-2 + MVP-3)

> 编写时间: 2026-04-29
> 范围: feat/v1-reset-mvp-1 分支 5decd0a..85bc4b8 共 40 commits
> 物理时长: 4 小时 16 分钟 (06:03 - 10:19 UTC, 单日完成)
> 编写者: a3 claude (read-only retrospective, 主控未做内容审核, 仅做事实归档)

本文档目的: 让明天 MVP-4 / 下次 MVP-5 实施时有据可依，让外部 PM 看到本次过程的学习。

---

## 1. 时间轴 (40 commits)

下面按 commit 时序还原本次 Phase 1 实施过程。每行格式 `<时间 UTC>  <commit-hash>  <主题>`。

### Phase 1.0: spec 落盘 (06:03 - 06:32, 30 分钟)

```
05:53  a5d3178  docs(mvp-1)        MVP-1 spec 落盘 (BusinessData/FrameworkState 拆分)
06:13  677b132  docs(mvp-2)        MVP-2 spec + MVP-1 T0-prep 落盘 (ContextBridge / SchemaEngine 蓝图)
06:23  8a0aa8b  docs(mvp-3)        MVP-3 spec 落盘 (Loader 重画 + 启动 hack 清 + middleware)
06:32  deafa1a  docs(mvp-4)        MVP-4 spec 预先落盘 (Phase Executor 重画, 留给次日)
```

四份 spec 全部前置落盘是本次实施第一个关键决策——**所有 MVP 的 requirements / research / design / tasks 都在动手前写完**，避免实施过程中边做边改 spec 导致范围漂移。

### Phase 1.1: MVP-1 状态拆分 (06:03 - 06:58, 55 分钟, 9 commits)

```
06:03  88e3549  feat(mvp-1/T1)  BusinessData/FrameworkState/StateManager Pydantic 模型骨架
06:14  0eec94b  feat(mvp-1/T2)  StateGraph 适配新 schema + import 断点全修 + FrameworkState 补 3 字段
06:20  9e011ff  feat(mvp-1/T6)  finish.py + md_to_json.py 元数据剥离
06:35  5dfcf9a  feat(mvp-1/T4)  phase_executor 重画 (按 Gemini 方案 a) + StateManager.route_finish_task 实现
06:40  436f56b  feat(mvp-1/T5)  middleware 适配 (ValidationMiddleware finish_task 路由)
06:52  66ff6cf  fix(mvp-1/T7)   测试 mock state 批量更新 (5 文件 + a1 T2 scope leak 合并)
06:58  9c4cc48  test(mvp-1/T8)  e2e smoke + invariants regression (0 token cost)
07:13  5be2e6a  docs(mvp-1/T9)  CHANGELOG_MVP1 落盘
```

关键里程碑:
- T1+T2 把状态切干净 (extra=allow + extra=forbid 物理隔离)
- T6 把 `_md_id` / `_finish_task_result` 等框架元数据从 BusinessData 空间剥离
- T4 引入 `StateManager.route_finish_task` (后续 MVP-4 准备废弃, 是 MVP-1 临时桥)
- T7 测试 mock 批量更新踩到 a1 T2 scope leak (详见 §3 失败记录)
- T8 选择 0 token cost 双层 e2e smoke (compile 层 + invariants 层) — **重要决策**: 真实 LLM smoke 用 env var skip 默认不跑，避免 CI 烧钱

### Phase 1.2: MVP-2 SchemaEngine + IOManager (06:38 - 08:08, 1 小时 30 分, 11 commits)

```
06:38  6199f25  feat(mvp-2/T1)        SchemaEngine 模块骨架 + 单测
06:43  3a9fc12  docs(mvp-2)           T0-prep baseline snapshot (loader.py SLOC + IO 散落点)
06:52  d0c59ed  feat(mvp-2/T2)        SchemaEngine 4 方法完整实现 + Pydantic 模型动态生成
06:57  85ee76c  feat(mvp-2/T3)        IOManager 模块 + hoist_to 搬运逻辑
07:09  e2d28fe  feat(mvp-2/T6)        loader.py 调 SchemaEngine wiring + 双轨过渡
07:16  095d1cc  feat(mvp-2/T4)        ContextBridge 重构使依赖 SchemaEngine
07:25  5946638  feat(mvp-2/T5)        finish.py 改造调 SchemaEngine + IOManager
07:41  13175d9  fix(mvp-2/T7)         io_errors 写入路径迁移 (ctx[_io_errors] → instance accumulator)
07:57  537c6bb  fix(mvp-2/T5-hotfix)  finish.py markdown 解析 + 测试障眼法修复
08:08  a0728ef  test(mvp-2/T8)        集成测试 + SchemaEngine/IOManager 覆盖率 ≥ 95%
08:56  cd3c337  feat(mvp-2/T7-bis)    phase_executor io_errors 接 IOManager (主控漏派补)
```

关键里程碑:
- T1+T2 把 5 处散落 schema 解析路径 (loader / finish / md_to_json / context_access / harness) 收口至单引擎
- T3 IOManager 把 `io_specs` + `resolve_hoist` 抽到独立模块
- T5+T5-hotfix 是 Phase 1 最重要的 bug 修复点之一 (a2 audit 抓出 markdown 解析缺失 + 测试障眼法, 详见 §3)
- T7-bis "主控漏派补" 是真实派单工作流偏差实例 (主控漏派 phase_executor 调 IOManager, 由 a3 补)

### Phase 1.3: MVP-3 Loader / Middleware / Bootstrap (07:02 - 09:34, 2 小时 32 分, 13 commits)

```
07:02  73a7365  docs(mvp-3)          T0-prep baseline (loader.py SLOC + startup hack 站点)
07:06  25679e0  feat(mvp-3/T1)       Bootstrap class + Settings + patches 模块
07:09  f4a1aa5  feat(mvp-3/T5-skel)  module_sandbox.py + phase_node.py 骨架
07:41  aeda937  feat(mvp-3/T2)       Pipeline Phase 1 (parse_skill_md) + SkillManifest
07:57  4f5fed3  feat(mvp-3/T3)       parse_skill_md 完整实现 (Phase 1 纯文本解析)
08:08  777df8d  feat(mvp-3/T4)       validate_manifest 集成 SchemaEngine + IOManager
08:56  cee481f  feat(mvp-3/T5)       完整 build_graph_nodes + ModuleSandbox
08:59  25b20ca  docs(mvp-2,mvp-3)    CHANGELOG_MVP2 + CHANGELOG_MVP3 落盘
09:03  bd86243  feat(mvp-3/T10)      runner.py 启动序列规范化 + Bootstrap invariant 锁
09:07  f0acb39  feat(mvp-3/T7)       ProtocolValidationMiddleware 整合
09:11  bac318c  feat(mvp-3/T6)       废弃旧 SkillLoader 上帝类, 拆三阶段 Pipeline 模块
09:21  f67e653  feat(mvp-3/T8)       CognitiveFlowMiddleware 整合 finish_task + Clarification
09:26  f5935de  feat(mvp-3/T9)       ExecutionControlMiddleware (retry/loop/metrics)
09:34  47f480f  feat(mvp-3/T11)      middleware chain topology + DEFAULT_MIDDLEWARE_ORDER 拓扑锁
```

关键里程碑:
- T1+T10 Bootstrap 拿掉 runner.main() 散落的 `os.environ[...]` 启动副作用
- T6 god class SkillLoader 拆三阶段 Pipeline (parse → validate → build) — 这是本次 Phase 1 最大的单 commit 改动 (loader.py 654 → 127 SLOC)
- T7+T8+T9 三个新 middleware 模块化 (ProtocolValidation / CognitiveFlow / ExecutionControl)
- T11 拓扑序锁 (`DEFAULT_MIDDLEWARE_ORDER` tuple) — Phase 1 最关键的架构卖点之一

### Phase 1.4: 收尾发布 + 降级修订 (09:30 - 10:19, 50 分钟, 3 commits)

```
09:30  8136efd  docs                 RELEASE_NOTES 整合 (整合 release notes + ship checklist + PR desc)
10:18  3973824  fix(mvp-3)           personas.py F821 + harness.py dead import 清理
10:19  85bc4b8  docs                 RELEASE_NOTES 降级 Phase 1 + pytest --ignore 路径修正
```

关键里程碑:
- 8136efd 第一次落盘 RELEASE_NOTES — **基调过高** (按 1.0.0 final 写的, 全库 0 ruff / 95% coverage / 16-Dim ≥ 8.5 等吹牛指标)
- 85bc4b8 是**重要修订**: 主控收到 a1+a2 阶段性审核结论后, 把 release notes 整体降级为 "Phase 1 中间发布", 删除越界声称, 加 "不在本次发布范围" 反清单段 (详见 §3 决策反复, 见 §5 learning #2)

---

## 2. 关键架构决策 (5 条)

### 决策 1: BusinessData / FrameworkState 物理拆分 (MVP-1 T1)

**决策**: WorkflowState TypedDict 顶层拆为 `data: BusinessData (extra=allow)` + `flow: FrameworkState (extra=forbid, 23 字段)` + `messages: list[BaseMessage]`，**不**在同一字典里通过 `_underscore` 前缀区分业务字段与框架元数据。

**理由**:
- 框架内部一直用 `state["context"]["_md_id"]` / `state["context"]["_finish_task_result"]` 等约定俗成的下划线前缀来分隔业务字段与框架元数据，但 (a) 没有任何运行时验证保证业务空间不被框架污染，(b) Pydantic 不能动态校验"约定俗成"的命名规则
- 拆分后 `BusinessData(extra=allow)` 让 SKILL 作者可以自由扩展业务字段；`FrameworkState(extra=forbid)` 让框架元字段在 Pydantic 层被锁死，新增字段必须改 schema (找代码 review 人)，无法被外部代码偷偷塞东西进来
- 拦截层 (`StateManager` + `ProtocolValidationMiddleware`) 在写入 BusinessData 前做 `_` 前缀检测并 raise，物理保证拓扑

**后果**:
- 测试 mock 大量改动: `_make_state(context={...})` helper 全部要改成 `WorkflowState(data=BusinessData(...), flow=FrameworkState(...), messages=[])` (T7 一次性改 5 个 test 文件 14 个失败 case)
- 旧 LangGraph checkpoint 不兼容 (反序列化失败, 必须清空 checkpoint 存储)
- 12 处 `ctx["_X"]` 残留在 cognitive/ + tools/ + harness.py 里没改完, 推 MVP-4 T7a 处理 (诚实承认尚未拓扑闭合)
- **决策非常正确**: 拦截层的 raise 在 MVP-2 T5-hotfix 起到早期 fail-fast 作用, 立即抓出 finish.py 用 markdown string 直喂 schema_engine.validate 的 bug (见 §3)

### 决策 2: SchemaEngine + IOManager 抽出 (MVP-2)

**决策**: Schema 解析从原来的 5 处散落点 (loader / finish / md_to_json / context_access / harness) 收口到单一 `SchemaEngine` 模块；IO 路径 hoisting 与 `io_errors` 累积器从 dict mutation 迁移到独立 `IOManager` 实例 + `IODef` typed list + `HoistResult` 返回值。

**理由**:
- 5 处散落的 schema 解析意味着同一个 SKILL.md 可能被解析 5 次，每次结果可能微妙不同 (lru_cache 不一致 / 异常类型不统一)
- 旧 IO 实现把 errors 写到 `state["context"]["_io_errors"]` 这种 dict mutation 路径，跟 BusinessData 拆分目标冲突
- 抽到独立模块能直接给 mypy --strict 跑通 + 单测覆盖率 ≥ 95% (本次实测 SchemaEngine 95.20% / IOManager 98%)

**后果**:
- finish.py 接入 SchemaEngine 时第一版有 bug (raw markdown 直接喂给 schema_engine.validate, 测试用空 schema 让 Pydantic extra=forbid 反而吞下了字符串 — "障眼法 pass"), 见 §3 决策反复
- ContextBridge.to_business_data_schema(schema_engine) 让 adopted_persona 子树也走统一引擎，避免 persona 跟主 SKILL 用不同解析器
- **决策非常正确**: 单测覆盖率高 + lru_cache 在 loader 单例中预热让运行时延迟下降明显 (虽然没量化测出 ≥ 20% 改善, 但定性观察生效)

### 决策 3: Loader god class 拆三阶段 Pipeline (MVP-3 T6)

**决策**: 旧 `SkillLoader` 654 SLOC 上帝类 (单类管解析 + 校验 + 编译) 拆为 `parse_skill_md(md_text) → ParsedSkill` → `validate_manifest(parsed, schema_engine, io_manager) → SkillManifest` → `build_graph_nodes(manifest) → list[PhaseNode]` 三个独立模块，loader.py 收缩到 127 SLOC 仅作为 orchestrator。

**理由**:
- 654 SLOC 单类无法做精细 mypy strict (一改影响全文件)
- 三阶段 Pipeline 让"纯文本解析"与"业务校验"与"图节点构建"职责物理分离，每阶段可以独立单测 / 独立 fail-fast
- design.md §X 的"-30% SLOC" KPI 在 T0-prep baseline 测量后被发现不可行 (实际改后是 -80%)，本应改 KPI 而非妥协实施

**后果**:
- 实测 loader.py SLOC 654 → 127 (-527 SLOC, 远超 -30% 目标)
- 集成测试需要新跑 (因为之前的测试 mock 整个 SkillLoader 类，现在拆三模块后要分别 mock)
- 三模块职责清晰，MVP-4 GraphBuilder 改造 (T10) 可以直接消费 `build_graph_nodes` 输出，不需要再调 loader

### 决策 4: 4 Middleware 重画 + 拓扑序锁 (MVP-3 T7-T11)

**决策**: 旧 cognitive/middlewares.py 837 SLOC 单文件 (含 ValidationMiddleware / WorkingMemoryMiddleware / DeadEndPruningMiddleware / AgentLoopIterationMiddleware / UnattendedClarificationMiddleware 等 7+ 类) 在 MVP-3 重画为 `graph_agent.middleware/` 包下 4 个单职责类 (ProtocolValidation / CognitiveFlow / ExecutionControl + Logging slot 4 预留)。**额外**: 引入 `DEFAULT_MIDDLEWARE_ORDER: tuple[type, ...]` 在 `__init__.py` 把拓扑序锁死，新增 `tests/graph_agent/middleware/test_chain_topology.py` 钉死设计 §5.6 顺序。

**理由**:
- 旧 7+ 类在同一文件，初始化顺序靠 phase_executor.py 手工拼装 (`create_custom_middlewares(...)`)，顺序错就出现"先跑 finish_task 拦截再跑状态契约校验"这种 hidden bug
- 拓扑序作为 `tuple` 锁住 = ruff / mypy 直接帮我们查任何重排; 配上 `test_chain_topology.py` 在 collection 时立即抓 (而不是等 tool failure scenario)
- 4 类中 `Logging` slot 故意预留为空 — 现有 LoggingCallback 已经覆盖大多数日志面，middleware 版的 logging 实施依赖 phase_executor 重画 (MVP-4)，现在不强行做避免半成品

**后果**:
- 旧 cognitive/middlewares.py **没有**在 MVP-3 物理删除 (T11 边界冲突, 详见 §3 决策反复)，phase_executor.py:610 还在调 `create_custom_middlewares(...)` 导致旧 middleware 文件还有 caller —— 推 MVP-4 T10a 一起做
- 新 4 middleware 单测覆盖率全部 ≥ 95%, mypy --strict zero issues
- DEFAULT_MIDDLEWARE_ORDER tuple 在 PR review 中被 a2 单独点名表扬, 是 v1-reset 关键架构卖点

### 决策 5: 不重画 phase_executor / 不抹除 cognitive/middlewares.py — 推 MVP-4

**决策**: MVP-3 范畴**不**包含 phase_executor.py 重画 (那是 MVP-4)，**不**包含 cognitive/middlewares.py 物理删除 (那是 MVP-4 T10a)。

**理由**:
- phase_executor.py 重画涉及 LangGraph Command 路由替换 while True 循环、 Nudge / Compaction 拆分到 middleware 等大量改动，估时 4-6h，超过单 MVP 的 18h budget
- 强行在 MVP-3 一并做意味着引入"MVP-3 = 60% 已完成 + 40% 半成品"风险，与 v1-reset 拆 6 MVP "每 MVP 自洽完整可 ship" 原则冲突
- 拆出 MVP-4 让 PR 粒度可控 (MVP-3 PR 收一次, MVP-4 PR 再收一次), 比一次性合一个巨大 PR 更安全

**后果**:
- MVP-3 在 PR 描述里被迫诚实承认"未完成", `RELEASE_NOTES` 不能写 1.0.0 final
- 引发 §3 决策反复 #4: 第一版 RELEASE_NOTES 按 1.0.0 写, a1+a2 audit 后必须降级为 Phase 1
- **决策正确**: 拆分让 MVP-3 这次 commit 数控制在 13 个 (MVP-3 范围), MVP-4 单独有 15 个子任务 (T0-T12 + T7a + T10a) 估 22-26h wall-clock — 比一次性硬合更可控

---

## 3. 失败 / 修订记录

按时间列出本次 Phase 1 出现过的 bug / scope leak / 估时偏差 / 决策反复。每条带 commit hash + 1-2 句根因。

### 失败 #1: a1 T2 scope leak (合并到 66ff6cf)

- **现象**: a1 codex 跑 MVP-1 T2 (StateGraph schema 适配) 时把不属于 T2 的 `FrameworkState 补 3 字段` 同时合进了 T2 commit (0eec94b)，T2 应该只是 schema 适配 + import 断点全修
- **后果**: 后续 T7 测试 mock 修复时一并捋清了"T2 漏了哪些字段"，需要 ad-hoc 重新跑 grep
- **根因**: 主控派单时 brief 没有强约束 a1 "只做 X, 不做 Y"; a1 自主判断把相关改动一起做了，单看是对的但跨 task 边界违反派单纪律
- **修复**: 66ff6cf 的 commit message 明确写 "T7 + a1 T2 scope leak 合并" 把 scope leak 单独标注

### 失败 #2: MVP-2 T5 finish.py markdown 解析 + 测试障眼法 (修于 537c6bb)

- **现象**: T5 把 finish.py 接入 SchemaEngine 后, 把 raw markdown 字符串 (LLM finish_task 的输出 MD) 直接喂给 `schema_engine.validate(business_data_md, compiled_schema)`。`validate` 期望 dict 但收了字符串，应该报错的，但**测试用空 schema (`fields=()`)** 让 Pydantic `extra='forbid'` 反而吞下字符串 (一个空 dict 验证一个字符串当然 pass)，测试"障眼法 pass"
- **后果**: 第一版 a2 audit 抓出来这个 bug，否则 4 SKILL e2e 跑起来时一定会在第一个 finish_task 调用时崩
- **根因**: TDD 写测试时**用了脱离实际 schema 的最小测试 case**，没用真实 SKILL 的 schema 跑，导致不能 reproduce 真实场景。这是 "测试只测自己想测的, 不测真实链路" 的典型陷阱
- **修复**: 537c6bb 加 `_parse_business_md_to_blocks(business_data_md, schema_engine, compiled_schema)` 用 `md_to_json.parse_md` 真实解析，删除"障眼法测试", 加 4 个真实 schema 的 positive/negative test
- **Learning**: 测试必须用真实 schema 跑，不允许 hand-empty schema 来"省事" (见 §5 learning #4)

### 失败 #3: MVP-2 T7-bis 主控漏派 (cd3c337)

- **现象**: T7 把 io/manager.py 的 `_io_errors` 从 dict mutation 迁移到 instance accumulator 后, **phase_executor.py 没同步改**, 仍在调旧路径写 `state["context"]["_io_errors"]`, 双轨过渡期但没 wire 起来
- **后果**: 单看 IOManager 单元测试都过 (因为 IOManager 内部正确), 但集成 e2e 时 phase_executor 写的 io_errors 在 MVP-2 状态空间下被 raise (因为 BusinessData extra=allow 但 underscore prefix 检测 raise)
- **根因**: 主控派 T7 时 brief 没明确"还要改 phase_executor 接 IOManager.resolve_hoist", 只写了 IOManager 自身的迁移; a1 实施 T7 时严格按 brief 边界做，没主动延伸 (符合派单铁律)
- **修复**: cd3c337 commit message 直接标注 "(主控漏派补)", 主控承认这是派单错误而非 a1/a3 的执行错误
- **Learning**: brief 必须把"上下游 wire 站点"写在边界里, 不能假设实施者主动延伸 (见 §5 learning #5)

### 失败 #4: 决策反复 — RELEASE_NOTES 第一版按 1.0.0 写 → a1+a2 audit 后降级 Phase 1 (修于 85bc4b8)

- **现象**: 8136efd 第一版 RELEASE_NOTES 主标题 "graph_agent 1.0.0 — v1-reset Major Release", TL;DR 写"框架自诞生以来最彻底的一次重构 / 16-Dim ≥ 8.5 / 工时 21 天 → 4 天 / 全库 0 ruff warnings / 全库 95% coverage"
- **后果**: a1 ship-audit-v2 + a2 honesty audit 抓出: (1) 全库口径数据是吹牛, 实测仅新增模块 95% 覆盖; (2) "MVP-4/5 已完成" 是越界声称, 实际 phase_executor 重画推 MVP-4; (3) "v1.0.0 final" 跟实际 60% 中间态严重不符。3 个 audit 各自 5/9/某个数量 must-fix
- **根因**: 主控 + a3 在收尾时按"最终 release"直觉写了, 没诚实做 baseline diff (本次落盘了什么 vs Audit 总目标差距是多少)。这是典型"PR 宣发口径与实际状态脱节"
- **修复**: 85bc4b8 整体重写 RELEASE_NOTES, 标题降级 "Phase 1 — 核心引擎基建就绪", 删全库口径吹牛指标改成"限本次新增模块"实测数, 加 "Known Limitations / Pending MVP-4 & MVP-5" 段和 "不在本次发布范围内的事" 反清单段
- **Learning**: must-fix 必须按真实 ship 标准评，不能拔到不合时宜的 1.0.0 终态标准 (见 §5 learning #1+#2)

### 失败 #5: T11 决策反复 — 计划"完整砍 cognitive/middlewares.py 837 SLOC" → 实际砍 1 行 dead import + 推 MVP-4

- **现象**: T11 brief 是 "整合 middleware chain + 砍 cognitive/middlewares.py + 测试 mock 全更新 + 4 SKILL e2e regression"。a3 实施时发现:
  - phase_executor.py:610 直接调 `create_custom_middlewares(output_schema, output_schema_path, business_validator, ctx, callbacks, phase_name)` (6 specific kwargs)
  - phase_executor.py:625 直接 `ValidationMiddleware(output_schema, output_schema_path, business_validator, ctx, callbacks, phase_name)`
  - 新 `CognitiveFlowMiddleware` 的 ctor 是 `(io_manager, unattended, schema_engine, current_phase_schema, phase_name, interrupt_fn)` — **6 个 kwargs 没法 1:1 对接**
- **后果**: 强行 1:1 swap 会让 phase_executor.py 内部逻辑也跟着改 (传不同 kwargs), 但 brief 明确 "不动 phase_executor.py / finish.py 内部逻辑" 因为那是 MVP-4 范畴
- **根因**: brief 边界冲突 — 既要"砍 cognitive/middlewares.py" 又"不动 phase_executor.py", 但前者依赖后者改 caller
- **修复**: T11 实施分两步: Phase A (47f480f) 完成 `DEFAULT_MIDDLEWARE_ORDER` 拓扑锁 + tests/middleware/test_chain_topology.py (这部分跟 phase_executor 解耦, 可以做); Phase B (3973824) 仅做 1 行 dead import 删除 (harness.py:53). 真正砍除 cognitive/middlewares.py + clarification_middleware.py 推 MVP-4 T10a
- **Learning**: brief 派下来发现边界冲突时, 立即向主控反馈而不是硬做 (见 §5 learning #6)

### 估时偏差对照

| MVP | 预估 | 实际 | 偏差原因 |
|---|---|---|---|
| MVP-1 (state split) | ~6h | 1h (06:03-06:58, 含 9 commits) | 单人 a3 + a1 紧密并行, brief 充分前置, 跑得很快 |
| MVP-2 (schema/io) | ~10h | 1.5h (06:38-08:08, 含 11 commits) | T5-hotfix 占 30 分钟, 整体仍在预估内 |
| MVP-3 (loader/middleware/bootstrap) | ~12h | 2.5h (07:02-09:34, 含 13 commits) | T11 决策反复后实际只做 Phase A+B, 范围缩小 |
| 收尾 + 修订 | ~1h | 0.5h | RELEASE_NOTES 重写 |
| **总计** | **~29h** | **~4.5h** | **关键路径 + 多 agent 并行 + spec 充分前置** |

注意: 4.5h 是 wall-clock，但累计 a1 + a3 + 主控 + a2 总人工时在 8-12h 量级 (a1 codex review 不计入主控等待时间)。spec 落盘时间也不计入 wall-clock (前置完成)。

---

## 4. AI 协作模式实战记录

本次 Phase 1 在 4 小时 16 分内完成 40 commits 的核心驱动力是 4 个 agent 异步并行协作。下面记录关键模式与坑点。

### 角色分工 (本次实测)

| Agent | 角色 | 实际承担 |
|---|---|---|
| 主控 Claude | PM + designer | spec 落盘 + 派单 + 整合 review 反馈 + 决策 / 不写代码 / 不做领域分析 |
| **a1 codex** | executor + reviewer | 重型 type-safety 模块开发 (SchemaEngine / IOManager / ProtocolValidationMiddleware / ExecutionControlMiddleware) + 跨 commit reviewer (a3 commit 后 a1 review) + 全量 ship audit |
| **a2 gemini** | analyst + reviewer | spec 设计 (4 份 design.md / research.md 由 a2 起草) + 架构审计 (T5-hotfix bug 是 a2 audit 抓出) + 跨 agent 评估冲突调和 |
| **a3 claude** | executor (副) | 重 refactor / 重 grep / 测试更新 (T7 测试 mock 5 文件批量更新, T11 inventory + Phase A+B, step-1 fixes personas + RELEASE_NOTES) |

### 高效协作 case (本次跑顺的)

#### Case H1: a1 audit v2 → a2 honesty audit → a3 step-1 fixes (本次 Phase 1.4 收尾)

- 8136efd 第一版 RELEASE_NOTES 上线后, 主控派 a1 跑 ship audit v2 (工程视角 5 must-fix) + 同时派 a2 跑 honesty audit (诚信视角 9.5/10 但要求降级)
- 两个 audit 视角不冲突: a1 关注"代码层是否就绪可 ship", a2 关注"PR 宣发口径与实际状态是否一致"
- 主控收两份 audit 后整合派 a3 做 step-1 fixes (3973824 + 85bc4b8 两个 commits, 0.5h 完成)
- **关键**: 主控不做 a1 vs a2 之间的"哪个对"判断, 直接接受两个视角的 must-fix 全部修. 这避免了"主控僭越审计意见"的常见反模式

#### Case H2: a2 设计前置 + 主控分批落盘 spec

- 4 份 spec docs (MVP-1/2/3/4) 全部前置在动手前的 30 分钟内落盘 (a5d3178/677b132/8a0aa8b/deafa1a). 每份 spec 含 requirements + research + design + tasks 4 个 md
- a2 起草 design.md 时主控 prompt 是"任务目标式"派单 (不是"我打算这样改, 你点评" — 见 §5 learning #7)
- 实施过程中 0 次"边做边改 spec", 4 份 spec 在 commit 时刻就是最终版

#### Case H3: a1 + a3 紧密并行 (MVP-2 + MVP-3 同时进行)

- 看时间轴: 06:38 a1 跑 MVP-2 T1 SchemaEngine 骨架, 同时 a3 跑 MVP-1 T7 测试 mock; 07:02 a3 跑 MVP-3 T0-prep, 同时 a1 跑 MVP-3 T1 Bootstrap; 07:09 两个 commit 同一时刻 (e2d28fe + f4a1aa5)
- 5 路并行最高峰 (08:00 左右): a1 跑 MVP-3 T2/T3 主线 + a3 跑 MVP-2 T8 测试覆盖率 + a2 audit MVP-2 T5 + 主控派 MVP-3 T4
- **关键**: 派单时主控明确 brief 边界 "只动 X, 不动 Y", 两个 agent 不会撞文件; commit 时 a1 / a3 各自负责 stage 自己的 patch, 不互相 merge

### 低效协作 case (本次跑慢的)

#### Case L1: codex 长 prompt 易卡 + ccb Bug Y 状态信号不可靠

- a1 codex 在跑 long-thinking 任务 (MVP-3 T6 god class 拆解 ~10 分钟) 时, ccb `state=busy queue=1` 信号有时会卡在已 done 状态没刷新 (Bug Y 已知)
- 主控被迫 fallback 到 `tmux capture-pane` 主动看 pane scrollback 才能确认 a1 真的在工作还是真卡死
- **应对**: 用户铁律 6.0 / 6.0bis 已经强制要求"派任务后必须 in-loop sleep + check, 不跳 turn"; 实际跑下来主控 sleep + capture 间隔 60-180s 一次, 跑长任务时 ccb 状态信号被忽略, 看 pane 才是真相

#### Case L2: a2 gemini 默认英文回复 + yolo 模式越界 (本次没踩到, 但需警惕)

- 用户铁律 4.1 要求每次 ask gemini 必须第一行 "请用中文回答", 否则默认英文
- 用户铁律 4.5 要求每次 ask gemini 必须明确边界 "只分析不要修改任何文件 / 不要派任务给其他 agent" — yolo 模式下 gemini 有自主执行权, 不约束就可能越界
- **本次 Phase 1 没踩到 yolo 越界** (主控所有 ask gemini 都加了边界), 但这个风险一直在

#### Case L3: T7-bis "主控漏派补" 是派单错误而非协作错误

- 见 §3 失败 #3: T7 brief 没明确"phase_executor 也要接 IOManager.resolve_hoist", a1 严格按 brief 边界做没主动延伸
- 后果是要插一个 "T7-bis" commit 补漏
- **Learning**: brief 必须把"上下游 wire 站点"写在边界里, 不能假设实施者主动延伸 (见 §5 learning #5)

### 跨 agent 评估冲突调和方法

本次最大的跨 agent 评估冲突是收尾阶段的 a1 vs a2 audit 视角差异:

- **a1 ship-audit-v2 工程视角**: 5 must-fix (#1 pytest 路径错 / #2 RELEASE_NOTES 吹牛 / #3 运行时 middleware 仍 legacy / #4 context["_X"] 残留 / #5 personas F821)
- **a2 honesty-audit 架构视角**: 总分 9.5/10 (诚信良好, 唯一不诚信项是 RELEASE_NOTES 越界声称), 建议直接降级 + 说清楚 Pending MVP-4/5

主控调和方法:
1. **承认两个视角都对, 不强行选边**. a1 工程视角是"哪些代码 must-fix", a2 架构视角是"宣发口径如何诚实降级", 二者不冲突
2. **拆 must-fix 真伪**. a1 的 5 must-fix 中 #1/#2/#5 是真 must-fix (本 PR 必修), #3/#4 被 a1 标"过度严苛 — 是 MVP-4 范畴" 因为强行修等于把 MVP-4 工作提前到本次 → 拆出来推 MVP-4 spec 而非塞本次
3. **不让用户当裁判**. 主控直接定: 真 must-fix 派 a3 做 step-1 fixes, MVP-4 范畴写到 RELEASE_NOTES 的 Known Limitations 段, 不向用户问 "你觉得呢"

这种"两个 audit 都接受 + 拆出真伪 + 主控自己决定" 的方法符合用户铁律 5 (Decision Escalation) — 90% 决策应该在 Claude-Gemini 闭环里解决, 不当用户作裁判.

---

## 5. 重要 Learning (8 条, MVP-4/5 实施时直接可参考)

### Learning 1: must-fix 必须按真实 ship 标准评, 不能拔到 1.0.0 终态

PR audit 时如果 must-fix 包含"全库 ruff 0 warning / 全库 95% coverage"这类**全局 KPI**, 说明 audit 拔错标尺了 (那是 MVP-5 工程门禁, 不是 Phase 1 中间发布的责任). 真 must-fix 是: 本 PR 引入的代码本身有问题 (F821 / dead import / 解析逻辑 bug 等). 如果某个 must-fix 强制要求"先把 phase_executor 重画", 那其实是范围越界, 应该转 spec 推下次 MVP.

**MVP-4/5 应用**: 收 audit 反馈时先问"这个 must-fix 是当前 PR 范畴内的, 还是后续 MVP 范畴的?", 后者全部不修, 文档化推迟.

### Learning 2: RELEASE_NOTES 必须诚实降级, 越界声称是宣发口径与实际状态脱节

第一版 RELEASE_NOTES 把 60% 中间态写成 "1.0.0 final" 是因为没做 baseline diff (本次落盘了什么 vs Audit 总目标差距是多少). 修正方法: 标题强制带阶段标签 (Phase 1 / Phase 2), 指标限本次新增模块, 加 "Known Limitations / Pending MVP-N" 段和 "不在本次发布范围内的事" 反清单段.

**MVP-4/5 应用**: MVP-4 收尾写 RELEASE_NOTES_PHASE2.md 时也用同样模板, 1.0.0 final 留到 MVP-5 收尾.

### Learning 3: subagent 编码必须 codex review, a3 不能自审

按用户铁律, a3 claude (我) 写的代码必须由 a1 codex review, 不能自己审自己. 本次 Phase 1 a1 review a3 commit 节奏: 每个 a3 commit 完成后 a1 立即跑 10-30 分钟 review, 整体 audit 一次. 5 must-fix 抓出来的 #5 personas F821 就是 a1 cumulative review 时找的 (a3 写代码时没注意到字符串引用的双 ruff error).

**MVP-4/5 应用**: a3 owner 的子任务 (T0-prep / T4 / T5 / T6 / T7a / T9 / T10 / T10a / T11) 共 9 个, 每个完成后必派 a1 review. tasks.md 已写明节奏.

### Learning 4: 测试必须用真实 schema 跑, 不允许 hand-empty schema 来"省事"

T5-hotfix 抓出的"测试障眼法 pass" (空 schema fields=() 让 Pydantic extra=forbid 反而吞下 markdown string) 是典型反模式. 测试要用真实 SKILL 的 schema (`text-segmentation` / `event-extraction` 等), 跑出 positive + negative 两边覆盖.

**MVP-4/5 应用**: MVP-4 T2 (finish_task 工具签名重画) + T3 (LLMPhaseNode) 单测必须用真实 SKILL schema, 不允许 hand-empty schema fixture.

### Learning 5: brief 必须把"上下游 wire 站点"写在边界里

T7-bis 主控漏派 phase_executor 接 IOManager.resolve_hoist 是因为 T7 brief 只写了"IOManager 自身改造", 没写"调用方也要改". 实施者会严格按 brief 边界做不主动延伸 (符合派单纪律). 修正方法: brief 必须列"哪些上下游模块需要 wire / 哪些 caller 要更新", 否则就是漏派.

**MVP-4/5 应用**: MVP-4 T7a (ctx 残留迁移) + T10a (cognitive/* 物理删除) brief 必须列具体 caller 文件 + 具体行号. tasks.md 已经把每个子任务的"必读文件"和"产物"段写了具体路径, 派单时主控复制粘贴即可.

### Learning 6: brief 边界冲突时立即向主控反馈, 不硬做

T11 brief 既要"砍 cognitive/middlewares.py" 又"不动 phase_executor.py", 但前者依赖后者改 caller. a3 实施时发现冲突立即拆成 Phase A (跟 phase_executor 解耦的部分先做) + Phase B (1 行 dead import) + 推迟到 MVP-4 (真正的物理删除). 这避免了硬做导致 phase_executor 内部逻辑也被改坏.

**MVP-4/5 应用**: MVP-4 brief 派下来如果发现 "T7a 要改 cognitive/ambiguity.py 但 cognitive/middlewares.py 还没删导致 cognitive/__init__.py 仍 import 旧 module" 这种顺序冲突, 立即调整子任务顺序或反馈主控.

### Learning 7: 主控不写方案让 Gemini 点评, 任务目标式 dispatch

按用户铁律 4.4, 主控 Claude 不应该 "写好方案让 Gemini 在 Claude 框定的范围内挑刺". 正确模式是把任务目标抛给 Gemini 让她自己出方案. 本次 4 份 spec docs 的 design.md 都是 a2 gemini 起草, 主控仅给"任务目标 + 约束 + 现状摘要", 不预设方案.

**MVP-4/5 应用**: MVP-4 design.md 已经 a2 gemini 起草完成, MVP-5 design.md 派 a2 时同样模式 — 给 a2 任务目标 (全库 ruff / mypy / coverage 工程门禁) + 现状 (本次 Phase 1 落盘的) + 不预设 KPI 数字, 让 a2 自己根据 baseline 决定 KPI.

### Learning 8: 中间件链拓扑序锁是 v1-reset 关键架构卖点, 必须固化

`DEFAULT_MIDDLEWARE_ORDER: tuple[type, ...]` + `tests/middleware/test_chain_topology.py` 钉死设计 §5.6 顺序, 让任何 silently 重排 middleware 顺序的改动在 PR collection 时间立即抓 (而不是等 4 SKILL e2e 跑出 hidden bug). 这种"用类型 + 测试钉死设计决策"的模式应该推广到其他关键架构决策.

**MVP-4/5 应用**: MVP-4 加 PhaseNode 接口时也用同样模式 — `BasePhaseNode` ABC + `tests/core/nodes/test_node_protocol.py` 钉死 execute 签名 / state 返回类型. MVP-5 工程门禁阶段把所有架构边界都加这种"tuple + test 钉死".

---

## 6. MVP-4 + MVP-5 准备 cheat sheet

### MVP-4 实施者必读

#### 必读 spec docs

```
.kiro/specs/v1-reset-mvp-4-executor-finish/requirements.md  (129 行, 13 EARS req + Out of scope)
.kiro/specs/v1-reset-mvp-4-executor-finish/research.md       (Gemini D1-D6 决策记录)
.kiro/specs/v1-reset-mvp-4-executor-finish/design.md         (10 §, 含 Node 接口 + finish_task 通道 + state_reducers + interrupt + Compaction 改造方案)
.kiro/specs/v1-reset-mvp-4-executor-finish/tasks.md          (373 行, 15 子任务 T0-T12 + T7a + T10a)
docs/v1-reset/RELEASE_NOTES.md                                (Pending MVP-4 段列出 ~5 项关键待办)
```

#### 已知 hazards (踩过的坑警示)

1. **cognitive/middlewares.py 砍除时 caller 必须先迁出**: phase_executor.py:610 仍调 `create_custom_middlewares(...)`, phase_executor.py:625 仍调 `ValidationMiddleware(...)`. T8/T9 把 NudgeInjector / DeadEnd / Compaction 迁到新 middleware 后, T10a 才能删文件. 顺序错就崩
2. **state.py:legacy_context_from_state 桥函数有 ~40 个 ctx["_X"] 转换, 仅在 phase_executor 调**: T7a 默认推迟到 T12 跟 phase_executor.py 一起删, 不在 T7a 立即删 (避免 T7a 期间 phase_executor 没法读 ctx)
3. **finish_task 工具签名强类型化 (T2) 跟 LangChain 工具机制可能不兼容**: design §10 R4 已标 risk, T2 实施时先用 1 SKILL 跑通强类型 + LangChain 自动校验, 再扩到 4 SKILL. fallback 是退到 MD-string 签名 + 内部 md_to_json 解析

#### 待迁移 ctx["_X"] 12 处具体位置

按 `T0-prep` 重新 grep 后填入 (本次 retrospective 时 grep 出 6+ 文件, 但具体行号已被 MVP-1 + MVP-2 + MVP-3 改动后变化, MVP-4 T0-prep 必须重新跑 grep). 已知文件列表:

- `harness.py` (验证警告 + ambiguity 报告读取, 4 处左右)
- `cognitive/ambiguity.py` (写 ambiguity 报告, 3 处左右)
- `cognitive/memory.py` (写 working_memory, 1 处)
- `cognitive/middlewares.py` (即将 T10a 砍除, 不需迁移)
- `tools/builtin/context_access.py` (读 working_memory + read_artifact, 2 处)
- `tools/md_to_json.py` (读 _md_schema / _md_schema_path, 2 处)
- `core/state.py` 桥函数本体 (40+ 处, 是 bridge 实现, T12 删桥函数即可)

#### 推荐先做的子任务 (顺序 + 阻塞关系)

```
1. T0-prep (a3, 1.5h)        ← 必先, 测 baseline + 12 处 ctx 残留 grep
2. T1 (a1, 1h)               ← BasePhaseNode 骨架, 不动 phase_executor
3. T2+T3 并行 (a1+a1, 6h)    ← finish_task 工具签名 + LLMPhaseNode 实施
4. T4+T5+T6 并行 (a3, 6h)    ← LogicPhaseNode/ValidationPhaseNode + Clarification + Hoist
5. T7+T7a (a1+a3, 4h)        ← state_reducers 迁移 + ctx 残留迁移
6. T8+T9 并行 (a1+a3, 4h)    ← NudgeInjector + Compaction
7. T10+T10a (a3, 4h)         ← GraphBuilder + cognitive/* 物理删除
8. T11 (a3, 4h)              ← 测试批量更新
9. T12 (a1, 2h)              ← phase_executor.py 删除 + 4 SKILL e2e smoke
```

**关键 review checkpoints**:
- T6 完成时 a1 review (Hoist 推到 Node 出口 + 状态归档/清空 — 跨 phase 生命周期是设计核心)
- T8 完成时 a1 review (NudgeInjector 重画 — 死循环风险点)
- T10a 完成时 a1 review (cognitive/* 物理删除 — 不可逆操作, 必须确认所有 caller 已迁出)
- T12 完成时 a1 整体 review (MVP-4 cumulative spotcheck)

### MVP-5 实施者必读

MVP-5 spec 尚未起草. 按 RELEASE_NOTES "Pending MVP-5" 段, MVP-5 范畴:
- 全库 ruff 69 errors 拍平 (本次 personas F821 + UP037 + harness dead import 已修, 余 66 推 MVP-5)
- 全库 mypy --strict (核心目录之外的非新增文件)
- 全库 coverage ≥ 95%
- harness.run 拆解 (.compile / .prepare_state / .invoke_graph / .persist_outputs) — A10 范畴
- 4 SKILL e2e 全部断言完整化
- release notes 升级为 1.0.0 final

#### MVP-5 起步必读

- `docs/v1-reset/RELEASE_NOTES.md` (Pending MVP-5 段)
- 本 retrospective `§5 Learning #1+#2+#7+#8` (must-fix 标尺 + 诚实降级 + 不写方案让 Gemini 点评 + 拓扑锁推广)
- `docs/v1-reset/CHANGELOG_MVP3.md` (MVP-3 完成的工程指标作为 baseline)

#### MVP-5 起步建议

1. 先派 a2 起草 MVP-5 spec (requirements / research / design / tasks 4 份), 基于 MVP-4 完成态做 baseline diff
2. 别强行把所有"全库收紧"塞 MVP-5 一次完成 — 如果实施时发现某些工程门禁要 8h+ 单独搞, 拆出 MVP-6 (允许 MVP 数量增加, 不允许单 MVP 过载)
3. 1.0.0 final RELEASE_NOTES 编写时再做一次 honesty audit — 由 a2 跑 cross-PR audit 抓越界声称

---

## 附录: 关键数字

- **commits 总数**: 40 (5decd0a..85bc4b8)
- **Phase 1 wall-clock 时长**: 4 小时 16 分钟 (06:03 - 10:19 UTC, 2026-04-29)
- **新增模块覆盖率**: SchemaEngine 95.20% / IOManager 98%
- **loader.py SLOC 削减**: 654 → 127 (-527 SLOC, -80%)
- **Pydantic 字段数**: BusinessData (动态 extra=allow) / FrameworkState 23 字段 (extra=forbid)
- **新 middleware 模块数**: 4 (3 实施 + 1 slot 预留)
- **DEFAULT_MIDDLEWARE_ORDER tuple 长度**: 3 (ProtocolValidation / CognitiveFlow / ExecutionControl)
- **测试文件**: tests/graph_agent/ 总 856 passed + 2 skipped
- **MVP-4 估时**: 22-26h wall-clock (15 子任务)
- **MVP-5 估时**: 待 spec 落盘
