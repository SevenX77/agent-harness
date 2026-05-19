# Handoff — next session context for post-D-harness-split work

> **贴给下一个 session 的完整上下文。** 读完这份就能接手后续任务，不用翻聊天记录。

## TL;DR

D 任务（refactor/harness-split）全线完成并已 **merged 进 main**（PR #2，merge commit `c7a3fef`，2026-04-24）。`GraphAgentHarness` 从 1580 → 935 行，拆成 4 个合作者（GraphBuilder / PhaseExecutor / RetryRouter / NudgeInjector）。并发 race 消除。**main 当前 `pytest tests/ -q` = 264 passed**。双审阅者（Codex / Gemini）均 PASS。

## 当前工程现状

- **main**：已合入 PR #2 的 12 个 commit（harness-split）。branch `refactor/harness-split` 可删。
- **pytest**：`pytest tests/ -q` 应该是 **264 passed** 起步。再少就是回归。
- **harness.py**：~935 行，只剩 facade 责任（`__init__` / `run` / `resume` / `get_thread_status` / `_build_context_from_io` / `_save_outputs_via_io` / `_save_compaction_sidecar` 等 IO / HITL / checkpointer 解析）。4 个合作者在 `src/core/graph_agent/core/{graph_builder,phase_executor,retry_router,nudge_injector}.py`。
- **RunnableConfig 透传链**：`run()` / `resume()` 构造 `PhaseExecutor(callbacks, run_context=..., heartbeat=..., resolver=..., save_compaction_sidecar=...)`，放进 `config["configurable"]["_phase_executor"]` + `["_run_context"]`。graph node closure 从 config 反解 executor。subgraph.py 的 `(state, config)` 新签名 LangGraph 按位置注入 config，已通过测试验证。

## 未完成 / 延后的项（都在 `.kiro/specs/graph-agent-optimizations/deferred-items.md`）

| 项 | 状态 | 下一步 |
|---|---|---|
| **D-7.5** trace golden-baseline 回归 | 延后 | 需要真实 API key + 干净 shell 环境。等 E 任务录好 baseline 后跑 `scripts/snapshot_diff.py` 对 PR #2 merge 前后字节级对比 |
| **D-7.6** `src/core/graph_agent/` → `packages/graph-agent/` 物理重组 | 延后 | 独立 PR。步骤：`git mv` + 写 `pyproject.toml` + 替换 import 路径 + 留 re-export shim |
| **D-Resume-RuntimeInputs** | 延后（pre-existing，非 D 引入） | `resume()` 的 `runtime_inputs={}` 在中断恢复跨进程场景下会丢原始 `runtime_inputs_map`。Gemini 建议：持久化到 `WorkflowState["context"]` 或强制 `resume()` 接口要求重传。等 E 的 Golden Baseline 跑 HITL + subgraph 复合场景验证真会触发再修 |
| **E 任务** Golden Baseline 录制 | 未启动 | 独立分支。预计 1-2 天。是 D-7.5 的前置依赖 |

## 用户要求 / 协作铁律（已写进全局 CLAUDE.md）

1. **不准问"要不要继续"类问题**。所有规划内任务做完前不停。唯一例外：和 Gemini 辩论同一具体决策满 3 轮仍未对齐才升级给用户。
2. **决策问题先 Gemini 闭环**。设计/选型/代码审查都先走 Codex + Gemini 二审，自己判断够的别打扰用户。
3. **Gemini 发 prompt 必带完整背景**（不精简结论让他背书）。第一行 `请用中文回答。`。
4. **工程规范**：每次迁移前补单测锁行为；保留原行为 quirk 不顺手清理；commits 小步 + 测试绿。
5. **ccb 用法**：`command ccb ask --wait --timeout 300-600 <agent>` 同 turn 拿回复；async 只在 >8 分钟 / 并行多个 / 用户明示后台时用；`.ccb/ccb.config` 里 `a1=codex`, `a2=gemini`, `a3=claude`。

## 本次 session 的高亮决策记录（供参考，不必回溯聊天历史）

1. **RetryRouter / GraphBuilder 不吃 RunContext**：compile-time collaborator，graph 编译时 RunContext 还没创建（lifecycle mismatch）。第一轮 Gemini 建议有效。
2. **NudgeInjector Option β**（NudgeOutcome + try_* 方法）而非 context.md §5.4 的 `maybe_inject_before_invoke(state)` 单 hook——三种 nudge 触发条件不一样没法统一。`_has_structured_selfcheck` 搬进去作 private。
3. **保留 NudgeInjector 的 increment-before-check quirk**（planning/standard 分支）：第二轮和 Gemini 辩论时我用具体场景（max_nudges=1 + selfcheck→planning）证明"fix"会多注入 1 个 planning nudge，Gemini 收回建议同意保留 + 加 FIXME。
4. **NudgeInjector 接 explicit `callbacks` 非 RunContext**：我偏离 Gemini Q3 建议，理由是保留 nudge event 作用域 = `harness.callbacks`（不含 subgraph 转发的 extra_callbacks）。Gemini 对 RunContext.callbacks 的 widening 建议在 refactor 里不适用。
5. **Phase B 用 `RunnableConfig["configurable"]` 透传 PhaseExecutor**（Gemini 的 Option D）：比方案 A（instance slot 晚绑定，race 没解决）、B（每次 recompile graph，成本）、C（contextvars，pregel 边界不明确）都好。是真正消除并发 race 的选择。
6. **Phase A → Phase B 两阶段拆 PhaseExecutor**：step 4.1-4.3 只搬方法保行为（PhaseExecutor 临时 hold `self._harness`）；step 4.4 一次性改状态归属 + 删 `_harness` scaffolding + 删 subgraph FIXME。

## Review 记录

- **Codex (a1) 代码审查**：CONDITIONAL PASS，零 must-fix。第一次 ask (3334 行 diff + 重勉强 prompt) 47 min 挂死、tmux/provider 层卡住；cancel + 改窄焦点 prompt（只看 3 个关键文件 + 给判决不打分）2 min 完成。Codex 提 2 个疑点，经我独立核验后**都是非问题**：
  - 疑点 A "subgraph race 是否消除"：Codex 担心 `PhaseExecutor.execute_subgraph_phase` 是 NotImplementedError。**实际**：那是死代码（无调用者），subgraph 走的是 `harness._build_subgraph_node()` → `build_subgraph_node()` 闭包 → 从 config 读 `_run_context` 调 `harness._get_active_run_options(parent_run_context)`。race 真正消除
  - 疑点 B "extra_callbacks dedup 是 D 引入的行为变化"：grep `main:harness.py` 确认 **pre-existing**，不是 refactor 改的
  - Codex 的 2 个 should-fix（`hasattr(self,'callbacks')` 冗余 guard + `type(self)._save_compaction_sidecar` 的写法"有点绕"）都是风格瑕疵，不值得一个额外 commit
- **Gemini (a2) 设计符合性审查**：PASS，9.5+10+10+10 四项评分。[严重] 问题（`_executor_from_config` 缺测）已在 b24c2da 修补。其他两项 pre-existing，列入 deferred-items（一个记录到 D-Resume-RuntimeInputs 新条目；一个 callbacks reference 分化风险是未来担忧，不记录）。

## 下一个 session 最可能被问的事

1. **做 E 任务 Golden Baseline**：独立分支 `feat/golden-baseline`，调 `scripts/snapshot_diff.py`，录一次完整 run 的 `tracing.jsonl`，做 timestamp + UUID 归一化 baseline。
2. **做 D-7.6 物理目录重组**：独立 PR，机械 `git mv` + pyproject.toml + shim。
3. **从 deferred-items.md 挑一条继续**：P1 级别的项（D-Compactor-Sidecar-Async、D-TraceDir-Resolution 等）。
4. **对接 Studio 新 event**（如果产品方向变了）：先和 Studio 对齐 trace schema 再动。

不要预设用户必然做 #1；直接问"下一步目标是什么"比自作主张更合理。但注意：按用户铁律，**这不是"要不要继续"提问**——在没有已规划任务时问方向是合理的。

## 工作区残留（可忽略）

分支 / 工作目录里有几个**非本任务**的 dirty 文件，全 session 未处理也不关 harness-split 事：

- `.claude/sessions/*`（session 日志）
- `config/llm_roles.yaml`（某时刻被其他进程改了，和 DeepSeek model 命名相关）
- `tests/graph_agent/callbacks/test_events.py`（同上，`from_provider` 字符串被改了）
- `.kiro/specs/graph-agent-studio/` + `docs/superpowers/plans/2026-04-22-graph-agent-studio.md`（是另一个 spec，不是 harness-split）

下个 session 开工前 `git status` 先 check 这几条要不要 stage 进别的分支或 discard。不要误把它们当成 harness-split 的遗留。
