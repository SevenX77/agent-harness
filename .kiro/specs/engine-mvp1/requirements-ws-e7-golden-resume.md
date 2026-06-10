---
ws_id: WS-E7-golden-resume
modules:
  - 03-api-contract
  - 02-mechanism/04-run-outer/03-checkpoint
  - 02-mechanism/05-run-inner/06-golden-eval
  - 01-contract/01-physical-layout
depends_on:
  - WS-E1
  - WS-E1-io
  - WS-E5
  - WS-E8
owns_files:
  - packages/graph-agent/src/graph_agent/core/runner.py
  - packages/graph-agent/src/graph_agent/core/checkpointer.py
  - packages/graph-agent/src/graph_agent/core/result.py
  - packages/graph-agent/src/graph_agent/core/_predict_internal/**
  - packages/graph-agent/src/graph_agent/__init__.py
  - packages/graph-agent/tests/core/test_ws_e7_resume_contract_red.py
  - packages/graph-agent/tests/core/test_ws_e7_golden_eval_red.py
  - packages/graph-agent/tests/e2e/test_ws_e7_golden_resume.py
spec_ssot:
  - docs/engine/mvp1/03-api-contract/mvp1-alignment.md §3.1/§3.2/§8
  - docs/engine/mvp1/02-mechanism/04-run-outer/03-checkpoint/mvp1-alignment.md §2/§6/§8
  - docs/engine/mvp1/02-mechanism/04-run-outer/03-checkpoint/baseline.md
  - docs/engine/mvp1/02-mechanism/05-run-inner/06-golden-eval/mvp1-alignment.md §2/§3/§6/§8
  - docs/engine/mvp1/02-mechanism/05-run-inner/06-golden-eval/baseline.md
  - docs/engine/mvp1/01-contract/01-physical-layout/mvp1-alignment.md §2.2/§3/§8
status: drafted
created: 2026-06-10
related_plan: docs/engine/mvp1/_impl/IMPL_PLAN.md
related_backlog: docs/engine/mvp1/_impl-backlog.md S5/S6
review_flow: Codex 回写 requirements + RED -> 契约门 -> task/Gemini prompt -> GREEN -> baseline 回写 -> 终审
---

# WS-E7 Golden / Resume Requirements

> 本需求书进入 Engine MVP1 最后功能阶段。当前只写需求与 RED 契约,不得实现生产代码。Engine 是通用库;Studio 只是调用者和调试界面,不得把 Studio-only DTO 或 route 形状写成 Engine 契约。

## 1. 目标

WS-E7 收口两个最后的 Engine 能力:

1. **Resume**: 把 resume 从 Studio HTTP 501 桩背后的目标契约落成 Engine 进程内 API。Engine 能按 `run_id` + checkpoint selector 找到历史 checkpoint,应用 context overrides 或 HITL human response,并继续执行同一 skill。
2. **Golden eval**: 把 `.workspace/golden` 从文档户型落成 Engine SDK。Engine 能读取 workspace golden baseline/cases,逐节点比较 actual output 与 expected output,写 `report.json`,并把 stale 判断放在 eval 期而不是 compile 期。

## 2. 边界

本 WS 做 Engine 通用能力,不做 Studio 产品层:

- 不改 `apps/studio/**`。Studio `POST /runs/{run_id}/resume`、golden UI、HTTP DTO、文件树 UI 由 Studio 后续薄接。
- 不改 `packages/graph-agent-gateway/**`。
- 不新增 gateway-only predict 拦截逻辑。
- 不把 golden 写进 skill 源码树;golden 只能在 `workspace_dir/golden/**`。
- 不把 `[F-v3-golden-stale-fields]` 重新定义为 compile-time fatal;stale 是 eval 报告项。
- 不做 Error Contract V2 P0-3/P1/P2。
- 不做 messages compaction、checkpoint data delta、复杂 HITL UI。

允许 Engine 新增小型内部模块,但必须保持 API surface 清楚,避免继续堆大 `runner.py`。若实现者需要扩大 owns 到其它生产文件,必须先停下回报。

## 3. Resume 契约

Engine 必须提供进程内 resume API,供 Studio/host 调用。RED 可以锁定具体函数名与签名,但至少满足:

本轮 RED 锁定的 Engine public API 名称为 `graph_agent.resume_skill` / `graph_agent.core.runner.resume_skill`:

```python
resume_skill(
    skill_path,
    *,
    workspace_dir: Path,
    run_id: str,
    checkpoint_id: str | None = None,
    checkpoint_ns: str | None = None,
    context_overrides: dict[str, Any] | None = None,
    human_response: dict[str, str] | None = None,
    skill_resolver: SkillResolverProtocol,
    model_resolver: Any | None = None,
    event_subscriber: Callable[[CallbackEvent], None] | None = None,
) -> RunResult
```

MVP1 resume artifact policy:RED 先锁定 **复用原 `run_id`**。同一个 `run_id` 也是 LangGraph `thread_id` 与 `workspace_dir/runs/<run_id>/` 追踪键;resume 调用返回的 `RunResult.run_id == run_id`,并把 resume 后的 `result.json` / `final_state.json` / `metrics.json` / `trace.jsonl` 写回同一 run 目录。后续如要派生 resume run id,必须另开需求变更。

- 调用方显式传入 `skill_path` / `workspace_dir` / `run_id` / `skill_resolver`。
- `workspace_dir` 必须复用 run/predict 的绝对路径校验,不得从 Studio 配置、环境变量或 skill root 猜测。
- selector 支持按 checkpoint id 或 phase/namespace 选择历史 checkpoint。最小可落地形式可以是 `checkpoint_id` 或 `checkpoint_ns` + latest。
- resume 必须使用同一 checkpointer backend/thread,通过 LangGraph `get_state_history` / `update_state` / invoke 语义恢复,不能简单重新跑完整 skill 假装 resume。
- `context_overrides` 必须只更新 business blackboard,不得把 runtime/callback/compiled graph 等不可持久化对象写进 state。
- HITL human response 入参必须是结构化 `{content: str, tool_call_id?: str}`。`content` 必填;`tool_call_id` 可选,省略时只能在唯一 pending interrupt/tool call 时自动解析;多 pending 时必须报稳定 Engine error。
- resume 返回 `RunResult`,并写入 `workspace_dir/runs/<run_id>/result.json` / `final_state.json` / `metrics.json` / `trace.jsonl`。本轮 RED 已锁定 resume 复用原 `run_id`;后续如要改为派生 resume run id,必须另开需求变更。
- 不破坏 WS-E5 已实现的 namespace:外层 `""`、AGENT `agent:<phase>`、graph iterate 内 `iter{k}.agent:<phase>` 都必须可区分。

## 4. Golden Eval 契约

Engine 必须提供 `evaluate_golden_baseline` 进程内 SDK,供 Studio/host 调用。RED 可以锁定具体签名,但至少满足:

本轮 RED 锁定的 Engine public API 名称为 `graph_agent.evaluate_golden_baseline` / `graph_agent.core.runner.evaluate_golden_baseline`:

```python
evaluate_golden_baseline(
    skill_path,
    *,
    workspace_dir: Path,
    baseline_id: str,
    skill_resolver: SkillResolverProtocol,
    model_resolver: Any | None = None,
) -> dict[str, Any]
```

返回值与 `workspace_dir/golden/<baseline_id>/report.json` 内容等价;若实现使用 Pydantic model,也必须能 `model_dump(mode="json")` 得到同形状 dict。

- 入口要求 `skill_path`、`workspace_dir`、`baseline_id`、`skill_resolver`。
- `workspace_dir` 必须是绝对路径;所有读写都限定在 `workspace_dir/golden/<baseline_id>/` 与 `workspace_dir/runs/**` 内。
- Engine 读取:
  - `workspace_dir/golden/<baseline_id>/baseline.json`
  - `workspace_dir/golden/<baseline_id>/cases/<case_id>.json`
- 最小 case schema 必须支持:
  - `case_id`
  - `phase_id`
  - `inputs`
  - `expected_output`
  - `source`
  - `updated_at`
- `phase_id` 是 case 与节点绑定键。不得使用 Studio run id、canvas node DTO 或 skill 源码内 `golden.json` 作为绑定。
- 对每个 case,Engine 执行目标 skill 并提取该 `phase_id` 的实际 output,与 `expected_output` 做字段级 diff。LOGIC-only deterministic skill 必须能作为 RED,不依赖真实 LLM。
- report 必须写入 `workspace_dir/golden/<baseline_id>/report.json`,并作为 SDK 返回值返回。
- report 至少包含:
  - `baseline_id`
  - `summary` (`total_cases`, `passed`, `failed`, `stale`)
  - `cases[]` (`case_id`, `phase_id`, `status`, `score`, `diff`, `stale_fields`)
- stale 判定在 eval 期:如果当前 phase `io.outputs.required` 新增字段而 `expected_output` 缺失,该 case 标 `stale`,不让 `compile_skill` 因 workspace golden 失败。
- golden 不进 skill 源码树。RED 必须 grep/断言 skill tree 下没有 `golden.json`。
- Predict 专用旧目录仍不得出现:`workspace_dir/predict/latest_predict.json` 不能被创建。

## 5. RED 测试要求

Codex 下一步写 RED,建议文件:

- `packages/graph-agent/tests/core/test_ws_e7_resume_contract_red.py`
- `packages/graph-agent/tests/core/test_ws_e7_golden_eval_red.py`
- `packages/graph-agent/tests/e2e/test_ws_e7_golden_resume.py`

Resume RED 至少覆盖:

- public import/API 当前不存在或未实现,RED 干净失败。
- 初始 run 生成 checkpoint 后,resume 从选定 checkpoint 应用 `context_overrides`,不是从头重跑。
- AGENT/iterate namespace 历史仍可区分;selector 不得错取其它 namespace。
- HITL response 结构 `{content, tool_call_id?}` 被接受;纯 string 入参不得成为 Engine SSOT。
- 相对 `workspace_dir` 被拒绝。

Golden RED 至少覆盖:

- `evaluate_golden_baseline` 当前不存在或 xfail drift 转 RED。
- `.workspace/golden/<baseline_id>/cases/<case_id>.json` 被读取,并写 `report.json`。
- deterministic LOGIC skill 的单 case exact match → passed。
- expected 缺字段或值不等 → failed + 字段级 diff。
- 当前 io.outputs required 缺字段 → stale,且 compile 不 fatal。
- skill 源码树没有 `golden.json`;旧 `workspace_dir/predict/latest_predict.json` 不出现。
- 相对 `workspace_dir` 被拒绝。

## 6. 验收标准

- requirements + RED 阶段只改 spec/test,不改生产代码。
- RED 失败形状必须干净:当前应失败在 public API 缺失 / resume 未实现 / evaluate 未实现,而不是环境错误。
- 实现后 WS-E7 suite 全绿,并回归:
  - WS-E5 checkpoint namespace suite
  - run/predict workspace-dir contract
  - E1/E1-io/E4 关键 runtime suite
- baseline 只在 GREEN 后回写:
  - `docs/engine/mvp1/_impl/IMPL_PLAN.md`
  - `docs/engine/mvp1/03-api-contract/baseline.md`
  - `docs/engine/mvp1/02-mechanism/04-run-outer/03-checkpoint/baseline.md`
  - `docs/engine/mvp1/02-mechanism/05-run-inner/06-golden-eval/baseline.md`
  - `docs/engine/mvp1/01-contract/01-physical-layout/baseline.md`

## 7. 终止条件

本阶段完成后,Engine MVP1 功能 WS 收口。剩余只应是:

- SonarCloud/main quality gate 修复。
- Studio thin integration / UI 消费。
- Gateway 独立 PR 清理。
- Error Contract V2 P0-3/P1/P2 等后续增强 backlog。
