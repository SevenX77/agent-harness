# PR-2 (T4) 携带项 — 从 PR-1 收尾结转的已知输入

> 主控落盘 (事实校验类, 非设计内容)。PR-2 design 阶段 (SOP-08 step-1 7 步細分) 的 a2 research + a1/a3 audit 必须把这些作为显式输入复核。

## SN4: design.md:430 关于嵌套 run_skill 的事实错误 (已物理实证)

**design.md:430 原文声称**: SDK 内部 3 处嵌套 `run_skill` 调用 (`skill_tool_factory.py:110`、`md_to_json.py:578`、`parallel_map.py:306`) "**当前不传 `callbacks`，不受 PR-1 删除 public `callbacks` 参数直接影响**"。

**物理实证 (git verify)**:
- `git show HEAD~1:.../parallel_map.py` (PR-1 之前) → `parallel_map.py:306` **确实传了** `callbacks=callbacks` 给嵌套 `run_skill`。
- PR-1 (c83cab6) **已直接迁移**它 → 现状 `event_subscriber=_legacy_callback_subscriber(callbacks)` (parallel_map.py 当前 ~308 行)。
- 所以 design.md:430 的断言 **双重失真**: (1) parallel_map 当时确实传 callbacks; (2) PR-1 确实直接动了它。

**PR-2 必须做**:
1. 复核另外 2 处 (`skill_tool_factory.py:110`、`md_to_json.py:578`) 当前 (PR-1 后) 到底传不传 callbacks / event_subscriber — 不要照抄 design.md:430 的过时断言, grep 实证当前状态。
2. 把 design.md:430 这段改写成 PR-1 后的真相 (parallel_map 已迁 event_subscriber; 其余按实证)。
3. tasks.md:152 提到 parallel_map.py:22/107 注释里的 `tracing.jsonl` — 确认 PR-1 docs-sync 是否已覆盖 (PR-1 step-6 改的是 docs/, 不一定动 src 注释), PR-2 若动 nested trace 透传需同步这些 src 注释。

## 其他 PR-1 结转 (非阻塞, a3 src-audit 记录)
- `run_manager._result_context/_result_metrics/_result_wall_time` 里 `isinstance(result, dict)` 防御分支在 PR-1 永不命中 (WorkflowResult 非 dict), 留作 PR-2 `WorkflowResult→RunResult` 收敛时清理或复用。
- `predictor._predict_trace_subscriber` 只显式挂 4 个 hook (PhaseStart/PhaseEnd/LLMCall/ToolCall) — by-design 临时桥, PR-2 (T4 `predict_skill` public verb) 替换。
