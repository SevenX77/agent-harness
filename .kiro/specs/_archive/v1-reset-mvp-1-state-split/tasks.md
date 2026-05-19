# MVP-1 Tasks — A1 WorkflowState 拆分子任务派发

> 整合 Gemini Part D 子任务清单 + 主控调度优化（并行度 + a1/a3 分配）。

## 派发策略

- **a1 codex** 主线：T1 → T2 → T4 → T6（建模 + 状态接口 + 核心枢纽 + 工具元数据剥离）
- **a3 claude** 副线：T3 (并行 T4) → T5 → T7 → T8（runner / middleware / 测试 / smoke）
- **a3 代码必须由 a1 codex review**（按 ccb-collaboration 角色铁律）

每个 brief 必含**铁律 block**：
```
🚨 严禁 git mutate HEAD: git checkout/switch/reset/cherry-pick/merge/rebase/pull/stash. 只允许 read-only.
🚨 不要 commit / push / 创 PR / 派 ccb 给其他 agent.
```

## 关键路径

```
T1 (1h, a1) → T2 (2h, a1) → T4 (3h, a1) → T6 (1h, a1) ──┐
                            └─→ T5 (2h, a3) ──────────────→ T7 (4h, a3) → T8 (2h, a3)
                       T3 (1h, a3) ──────────────────────┘
```

最长链 = T1+T2+T4+T5+T7+T8 = 1+2+3+2+4+2 = **14h**（a1+a3 并行版）。
含 spec 写 + Gemini design + 主控 review + CI 修复 等 overhead，估总 18-22h（含其他人审查与 PR 周转）。

## 子任务清单

### T1 — 建 `BusinessData` + `FrameworkState` Pydantic 模型

- **Owner**: a1 codex
- **依赖**: 无
- **估时**: 1h
- **产物**:
  - `src/core/graph_agent/core/state.py` 重写（保留 WorkflowState TypedDict 但加 BusinessData / FrameworkState）
  - 33 行核心模型 + Pydantic ConfigDict + 字段定义见 design.md §1.1
- **验收**:
  - `python -c "from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState; bd = BusinessData(); fs = FrameworkState(); print(type(bd), type(fs))"` 不报错
  - `from graph_agent.core.state import StateManager` import 成功（先建空类，T4 才填充逻辑）
  - 单测: `tests/graph_agent/core/test_state_models.py` 含 6+ 测试
    - test_business_data_extra_allow（业务字段动态可加）
    - test_business_data_forbid_underscore（_ 前缀字段被框架自检拒绝 — 注意 Pydantic extra=allow 不直接拒，要在 StateManager.update_business 拒）
    - test_framework_state_extra_forbid（未声明字段被 Pydantic 拒）
    - test_framework_state_default_values（所有字段都有合理默认值）
    - test_workflow_state_typed_dict_compatible（WorkflowState 仍是 TypedDict，可在 LangGraph 用）
    - test_pydantic_serialization_round_trip（model_dump + model_validate round trip）
  - pytest 不退步（其他测试不该破，因为 T1 只加新 model，没改老 state.py 用户）
  - mypy strict 在 state.py 通过

### T2 — 修改 `WorkflowState` 类型 + LangGraph 初始化逻辑

- **Owner**: a1 codex
- **依赖**: T1
- **估时**: 2h
- **产物**:
  - `core/state.py` WorkflowState 改为 3 字段 (data / flow / messages)
  - `core/graph_builder.py` LangGraph StateGraph 初始化用新 schema（`StateGraph(WorkflowState)` schema 适配）
  - `core/state.py` 加 `update_business` / `update_framework` 工具函数 (StateManager 的 staticmethod 实现)
- **验收**:
  - 项目 import 全部通：`python -c "from graph_agent.core.harness import Harness"` 不报错
  - 编译 1 个 SKILL 测试: `python -c "from graph_agent.core.compiler import compile_skill; r = compile_skill('skills/text-segmentation/SKILL.md'); print(r.validation_status)"` —— 在 T2 阶段允许 runtime 跑不通（T3-T6 才接入 runtime），但 compile 必须不破
  - 旧 state.py 5 字段 (context/messages/current_phase/retry_counts/metrics) **彻底删除**
  - 单测: T1 的 test_state_models.py + 至少 3 个 LangGraph 集成测试

### T3 — 迁移 `runner.py` 状态初始化与加载逻辑

- **Owner**: a3 claude
- **依赖**: T2
- **估时**: 1h
- **可与 T4 并行**
- **产物**:
  - `core/runner.py` 把所有 `state["context"]["_X"]` 改为 `state["flow"].X`（参考 design.md §1.2 字段归属表）
  - 把 `final_state["context"]` 改为 `final_state["data"]` 并适配 `BusinessData.model_dump()`
  - `core/harness.py` 同样改造（initial_state / on_invoke 截获 state 部分）
- **验收**:
  - `runner.py` 含 0 处 `context\["_` 模式
  - `harness.py` 含 0 处 `context\["_` 模式
  - pytest tests/graph_agent/core/test_runner*.py 全过
  - pytest tests/graph_agent/core/test_harness*.py 全过

### T4 — 重构 `phase_executor.py` 状态读写逻辑（核心枢纽）

- **Owner**: a1 codex
- **依赖**: T2
- **估时**: 3h
- **产物**:
  - `core/phase_executor.py` 改造所有 `next_state["context"][...]` 读写为 `next_state["data"]` / `next_state["flow"]` 路由
  - 实现 `core/state.py` 里 StateManager.route_finish_task 完整逻辑（T1 时建空类）
  - phase_executor 在 finish_task 后调用 `StateManager.route_finish_task(state, llm_output)`
- **验收**:
  - phase_executor.py 含 0 处 `context\["_` 模式
  - StateManager 单测 4+ 测试（test_route_finish_task / test_update_business_rejects_underscore / test_update_framework_pydantic_forbid / test_messages_unchanged）
  - pytest tests/graph_agent/core/test_phase_executor*.py 全过

### T5 — 适配 `cognitive/middlewares.py` + `cognitive/clarification_middleware.py`

- **Owner**: a3 claude
- **依赖**: T4 (StateManager 完整后)
- **估时**: 2h
- **产物**:
  - ValidationMiddleware：`self.ctx["_finish_task_result"] = ...` → 通过 StateManager.update_framework
  - ClarificationMiddleware / UnattendedClarificationMiddleware：相同改造
  - middleware base class 接收 state 而非 ctx（如有 ctx 引用需重画接口）
- **验收**:
  - `grep "_finish_task_result" src/core/graph_agent/cognitive/` 含 0 hits
  - `grep "ctx\[" src/core/graph_agent/cognitive/middlewares.py` 含 0 hits（除非 ctx 是 LLM message 上下文不是 state）
  - pytest tests/graph_agent/cognitive/* 全过

### T6 — 修改 `cognitive/finish.py` + `tools/md_to_json.py` 元数据注入

- **Owner**: a1 codex
- **依赖**: T4
- **估时**: 1h
- **产物**:
  - `cognitive/finish.py`: 不再 `ctx["_finish_task_result"] = result`，改为 return result，由 phase_executor 路由
  - `tools/md_to_json.py`: 不再向 parsed dict 注入 `_md_id`；md_id 通过 ParsedBlock.meta 持有，由调用方读取后 update_framework
- **验收**:
  - finish.py 含 0 处 `_finish_task_result`
  - md_to_json.py 含 0 处 `"_md_id"` 字符串字面值
  - pytest tests/graph_agent/cognitive/test_finish*.py + tests/graph_agent/tools/test_md_to_json.py 全过

### T7 — 批量更新测试 mock state

- **Owner**: a3 claude
- **依赖**: T2-T6
- **估时**: 4h
- **产物**:
  - 全 `tests/graph_agent/` 下含 `WorkflowState` / `state[` / mock context 的测试改为新 schema
  - 推荐先 grep 找模式，写 sed 批量改，再手工修剩余
  - 受影响约 30-50 测试（baseline grep 5 文件 + 衍生改动）
- **验收**:
  - pytest tests/graph_agent/ --ignore=tests/graph_agent/core/validators/test_strict_v2.py → 全过（≥ 605 passed，新增 6+ T1 单测 + 4+ T4 单测）
  - 隔离的 test_strict_v2 14 failures 仍 isolated（不变）
  - coverage 不退步（≥ 65%）

### T8 — 全流程 e2e smoke (text-segmentation v3 跑 1 chapter)

- **Owner**: a3 claude
- **依赖**: T7
- **估时**: 2h
- **产物**:
  - 跑 `harness.run("skills/text-segmentation/v3/SKILL.md", input_chapter)` → 不抛错 + 输出非空
  - 检查 `final_state["data"]` 不含 `_` 前缀字段（invariant）
  - 检查 `final_state["flow"]` 通过 `model_validate(strict=True)`
  - 报告结果到主控（不 commit）
- **验收**:
  - smoke 跑通
  - invariants 全过
  - state["data"] / state["flow"] 内容快照存到 `tests/graph_agent/integration/test_mvp1_smoke.py` 作为 regression 测试

## a1 review 节奏

- **每子任务 review**（针对 a3 的 T3 / T5 / T6 / T7 / T8）：a3 完成后 a1 立刻 review，找出问题后 a3 修，主控 commit
- **MVP-1 整体 review**: T8 done 后 a1 把所有 MVP-1 commits 整体过一遍 + cumulative spotcheck 一致性

## 主控调度

派发顺序（伪时间线）：

```
t=0   spec 写完 commit; 派 a1 T1
t=1h  a1 T1 done; 主控 commit T1; 派 a1 T2
t=3h  a1 T2 done; 主控 commit T2; 派 a1 T4 + a3 T3 (并行)
t=4h  a3 T3 done → a1 review (15min); a1 fix → 主控 commit T3
t=6h  a1 T4 done; 主控 commit T4; 派 a1 T6 + a3 T5 (并行)
t=7h  a1 T6 done + a3 T5 也快好; a1 review T5 (20min); 主控 commit T5+T6
t=8h  派 a3 T7
t=12h a3 T7 done → a1 review (30min); a3 fix → 主控 commit
t=13h 派 a3 T8
t=15h a3 T8 done → 主控 commit + a1 整体 review
t=16h a1 整体 review done → 主控 squash + push + PR + CI green + merge
```

总估 = 16-22h wall-clock (含 review/CI/PR overhead)。

## Pre-flight checklist

派 T1 前主控自检：
- [x] spec 4 docs 落盘 (.kiro/specs/v1-reset-mvp-1-state-split/{requirements,research,design,tasks}.md)
- [x] baseline data 落盘 (docs/v1-reset/mvp-1-baseline-snapshot.md)
- [x] Gemini design 已审 (job_543e6152ff10 reply 整合到 design.md)
- [ ] orchestrator scope 起好（可选；MVP-0 没有强依赖；可走 default ccbd）
- [ ] a1 codex 当前状态 = idle (已 /clear)
- [ ] a3 claude 当前状态 = idle
