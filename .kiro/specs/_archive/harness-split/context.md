# harness-split — 独立 session 接手上下文文档

> **写给谁**：一个刚 `/clear` 过、没有任何对话历史的新 Claude 主控 session。
> **目的**：读完这份文档就能开始干活，不需要回看之前的对话。

---

## 一、目标（一句话）

把 `src/core/graph_agent/core/harness.py`（当前 1580 行的 `GraphAgentHarness` 巨类）按职责拆成 4 个独立的合作者类：`GraphBuilder` / `PhaseExecutor` / `RetryRouter` / `NudgeInjector`。保留 `GraphAgentHarness` 作为公共入口的 facade，内部把构图、节点执行、重试路由、nudge 注入四条职责委派给这四个合作者。

**独立分支**：`refactor/harness-split`（尚未创建，你从 `main`（PR #1 合并后）创建）。

**预计时间**：2-3 天。

---

## 二、你是谁、项目是什么

你是主控 Claude（CCB 多 agent 协作中的 `designer` + `executor` 双角色，规则见 `~/.claude/rules/ccb-collaboration.md`）。

项目是 `graph_agent` —— 一个基于 SKILL.md + LangGraph 的工作流 harness 框架，vendored 了 DeerFlow（ByteDance 的 deer-flow 项目）。它用 SKILL.md 作为 PM 可读的工程 DSL，让 PM 通过 Copilot 对话驱动工作流（不直接编辑 SKILL.md）。

项目根：`/home/sevenx/coding/agent-harness`
主分支：`main`
你要工作的分支：`refactor/harness-split`（从 main 新建）

---

## 三、前置条件（开工前必须确认）

### 3.1 PR #1 是否已合
- URL：https://github.com/SevenX77/agent-harness/pull/1
- 分支：`feat/graph-agent-optimizations` → `main`
- **必须先合**。如果还没合，停手去问用户"是要先 review PR #1 再开 D，还是直接在 feat/graph-agent-optimizations 上起 D？"
- 为什么必须先合：D 的所有拆分要基于 RunContext（由 PR #1 的 P0-1 commit `32bb7f0` 落地）。基于 feat 分支开 D 也行，但合并链会乱。

### 3.2 本地环境
```bash
cd /home/sevenx/coding/agent-harness
source .venv/bin/activate
pytest tests/ -q    # 必须 197 passed（或者合并 PR #1 之后的更新数字）
```

### 3.3 开新分支
```bash
git checkout main
git pull origin main
git checkout -b refactor/harness-split
```

---

## 四、当前 harness.py 结构快照（开工基准）

**文件**：`src/core/graph_agent/core/harness.py`，1580 行。

### 4.1 顶层
- `class _HeartbeatPulser` (L128-184)：小辅助类，不动它，已经被 A 阶段单测覆盖（`tests/graph_agent/core/test_heartbeat_pulser.py`）
- `class GraphAgentHarness` (L334-1580)：**要拆的主角**，~1246 行

### 4.2 GraphAgentHarness 当前方法清单（拆分目标）

| Line | 方法 | 职责 | 拆到哪 |
|------|------|------|--------|
| 359 | `__init__` | 构造：加载 skill、解析 checkpointer、设置 callbacks、准备 config | **留在 Harness facade** |
| 388 | `_resolve_checkpointer` (static) | 把 `checkpointer="auto"` 等字符串解析成 langgraph 实例 | **留在 Harness facade** |
| 428 | `run` | 公共入口：构建 RunContext、调 graph.invoke、保存输出 | **留在 Harness facade**（但内部把构图/节点执行委派出去） |
| 619 | `_get_active_run_options` | 从 RunContext 投影回 legacy dict shape | **留在 Harness facade** |
| 638 | `_save_compaction_sidecar` (static) | 写 compaction 侧车 JSON | **留在 Harness facade**（已被 A 阶段单测覆盖） |
| 674 | `_build_context_from_io` | 从 io_config 构造 initial_context | **留在 Harness facade** |
| 701 | `_save_outputs_via_io` | 通过 IOManager 自动保存输出 | **留在 Harness facade** |
| 724 | `get_thread_status` | HITL：查询 thread 状态（AWAITING_INPUT / COMPLETED 等） | **留在 Harness facade** |
| 807 | `resume` | HITL：恢复挂起的 thread | **留在 Harness facade** |
| 894 | `_build_graph` | 构建 LangGraph StateGraph | → **GraphBuilder** |
| 933 | `_build_subgraph_node` | 为 subgraph phase 造 node 函数 | → **GraphBuilder**（调用 PhaseExecutor 执行） |
| 937 | `_build_phase_node` | **1246 行里最大的一块**（L937-1438，约 502 行），包含 LLM phase 执行 + nudge 注入 + validation 调度 | → **PhaseExecutor**（核心执行部分）+ **NudgeInjector**（nudge 相关） |
| 1439 | `_build_validation_node` | 构建 validation node | → **PhaseExecutor** 或 **GraphBuilder**（按调用点决定） |
| 1510 | `_build_code_only_node` | 纯代码 phase 的 node 函数 | → **PhaseExecutor** |
| 1544 | `_should_retry` | 路由函数：判断 retry / next phase / END | → **RetryRouter** |
| 1556 | `_get_next_phase_node` | 查找下一个 phase 名 | → **RetryRouter** |
| 1566 | `_calc_recursion_limit` | 计算 recursion limit | → **GraphBuilder** |

### 4.3 Nudge 逻辑在哪

Nudge 相关逻辑**不是独立方法**，而是散在 `_build_phase_node` (L937-1438) 内部的 while-loop 里：
- L1171-1174：counter 初始化（`planning_nudge_count` / `selfcheck_nudge_count` / `standard_nudge_count` / `total_nudge_count`）
- L1183-1189：`_emit_nudge` inner helper
- L1228-1236：selfcheck nudge 条件 + 注入
- L1257-1259：planning nudge 条件 + 注入
- 常量：从 `src/core/graph_agent/cognitive/nudges.py` import（`_PLANNING_NUDGE` / `_SELFCHECK_NUDGE` / `_build_standard_nudge_text`）

**拆分策略**：NudgeInjector 接手 counter 状态 + 三种 nudge 的判断/注入逻辑，PhaseExecutor 内的 while-loop 调用 `NudgeInjector.should_inject_planning(...)` / `.inject_selfcheck(...)` 等方法。

---

## 五、4 合作者设计

全部 4 个合作者都接受 `RunContext` 作为构造参数，所以不再通过 `self._runtime_local.*` 读运行态（P0-1 已经干掉了这个）。

### 5.1 GraphBuilder —— `src/core/graph_agent/core/graph_builder.py`（新）

**职责**：接受 compiled skill + RunContext，产出可以 `.invoke()` 的 `StateGraph` 实例。

**搬过来的代码**：
- `_build_graph()` 主体
- `_build_subgraph_node()`（但节点的实际执行委派给 PhaseExecutor）
- `_calc_recursion_limit()`

**不搬**：构图时调用的 per-phase node factory（那些返回给 LangGraph 的回调函数本体由 PhaseExecutor 拥有）

**公共 API 建议**：
```python
class GraphBuilder:
    def __init__(self, skill: CompiledSkill, run_context: RunContext, *,
                 phase_executor: PhaseExecutor, retry_router: RetryRouter):
        ...
    def build(self) -> StateGraph: ...
    def recursion_limit(self) -> int: ...
```

### 5.2 PhaseExecutor —— `src/core/graph_agent/core/phase_executor.py`（新）

**职责**：给定一个 phase 定义 + RunContext，执行这个 phase 一次（不包括 retry；retry 由外层 router 触发重入）。

**搬过来的代码**：
- `_build_phase_node()` (L937-1438) 内部的 LLM phase 执行主循环
- `_build_code_only_node()` (L1510-1543)
- `_build_validation_node()` 的执行部分（构图部分仍可由 GraphBuilder 调）

**公共 API 建议**：
```python
class PhaseExecutor:
    def __init__(self, run_context: RunContext, *,
                 nudge_injector: NudgeInjector):
        ...
    def execute_llm_phase(self, phase: Phase, state: WorkflowState) -> WorkflowState: ...
    def execute_code_only_phase(self, phase: Phase, state: WorkflowState) -> WorkflowState: ...
    def execute_subgraph_phase(self, phase: Phase, state: WorkflowState) -> WorkflowState: ...
```

### 5.3 RetryRouter —— `src/core/graph_agent/core/retry_router.py`（新）

**职责**：给定当前 phase 执行后的 WorkflowState，决定下一步是重试当前 phase、跳到下一个 phase、还是结束。

**搬过来的代码**：
- `_should_retry()` (L1544-1555)
- `_get_next_phase_node()` (L1556-1565)

**公共 API 建议**：
```python
class RetryRouter:
    def __init__(self, skill: CompiledSkill, run_context: RunContext): ...
    def route(self, phase: Phase, state: WorkflowState) -> Literal["retry", "next", "end"]: ...
    def next_phase_name(self, phase: Phase) -> str: ...
```

### 5.4 NudgeInjector —— `src/core/graph_agent/core/nudge_injector.py`（新）

**职责**：拥有一个 phase 的 nudge counter 状态机 + 判断何时注入何种 nudge。

**搬过来的代码**：
- 从 `_build_phase_node()` 内部抠出来的 L1171-L1259（counter + `_emit_nudge` + selfcheck/planning 判断）
- `cognitive/nudges.py` 里的常量通过 import 使用（不搬）

**公共 API 建议**：
```python
class NudgeInjector:
    def __init__(self, phase: Phase, run_context: RunContext): ...
    def maybe_inject_before_invoke(self, state: WorkflowState) -> list[HumanMessage]:
        """Returns messages to prepend to state['messages'] for this turn."""
    def on_llm_response(self, response: AIMessage) -> None:
        """Update internal counters based on what the LLM did (or didn't do)."""
    def should_exit(self) -> bool:
        """True when total_nudge_count >= phase.max_nudges * 2."""
```

具体 API 形状可能要根据把代码真正搬过去的时候再调整，但核心是：**nudge 状态不再散在 while-loop 的局部变量里，而是一个对象的实例属性**。

---

## 六、工作流程（推荐的 TDD + 保守策略）

### 6.1 为什么要保守

Golden baseline（对拆分前后的 `tracing.jsonl` 做字节级 diff）**目前缺失**（D-Golden-Baseline 还没跑，因为需要真实 API key + 干净 shell 环境，这是 E 任务）。用户明确选择 **D 先于 E** 做，因此你无法用 trace diff 来保证"重构前后行为完全一致"。

补偿策略：**每个合作者抽出前，先补单元测试锁住行为**，抽出后再跑一遍，确保单测仍绿。

### 6.2 推荐顺序

1. **先建基础骨架**（半天）
   - 新建 4 个空的合作者文件：`graph_builder.py` / `phase_executor.py` / `retry_router.py` / `nudge_injector.py`
   - 每个文件只放 class 定义 + public API 签名，实现全部 `raise NotImplementedError`
   - commit：`feat(harness): scaffold GraphBuilder / PhaseExecutor / RetryRouter / NudgeInjector`

2. **先抽 RetryRouter**（最小体积，最独立）—— 半天
   - 把 `_should_retry` 和 `_get_next_phase_node` 搬过去
   - 写单测 `tests/graph_agent/core/test_retry_router.py`
   - `GraphAgentHarness._should_retry` 改为委派：`return self._retry_router.route(phase, state)`
   - 跑 `pytest tests/ -q`，必须绿
   - commit：`refactor(harness): extract RetryRouter (D-7.3)`

3. **再抽 NudgeInjector**（状态机，中等复杂度）—— 半天到一天
   - 把 `_build_phase_node` 里的 nudge counter 抠出来
   - 写单测 `tests/graph_agent/core/test_nudge_injector.py`（覆盖 3 种 nudge 的触发条件、max_nudges 边界、total cap）
   - `_build_phase_node` 内部改为 `nudge_injector = NudgeInjector(phase, ctx)`，while-loop 里调用它
   - 跑测试，必须绿
   - commit：`refactor(harness): extract NudgeInjector (D-7.4)`

4. **再抽 PhaseExecutor**（最大一块）—— 一天
   - 把 `_build_phase_node` / `_build_code_only_node` / `_build_validation_node` 的执行部分搬过去
   - 这一步 diff 最大；如果可能，**先抽一个方法（比如 code_only），跑测试绿，再抽下一个**
   - commit：按方法拆成 3-4 个 commit（`refactor(harness): extract PhaseExecutor.execute_code_only`, etc.）

5. **最后抽 GraphBuilder**（几乎只剩它了）—— 半天
   - 把 `_build_graph` 和 `_calc_recursion_limit` 搬过去
   - `GraphAgentHarness.__init__` 里改为 `self._graph = GraphBuilder(...).build()`
   - commit：`refactor(harness): extract GraphBuilder (D-7.1)`

6. **收尾**（半天）
   - 验证 `GraphAgentHarness` 最终瘦身到 ~300-400 行
   - 跑全测试
   - 更新 `.kiro/specs/graph-agent-optimizations/deferred-items.md`：勾掉 D-7.1 / D-7.2 / D-7.3 / D-7.4
   - 开 PR 到 main

### 6.3 跳过 D-7.5 回归 / D-7.6 物理重组

- **D-7.5**（拆分前后 trace diff 回归）：**跳过**。原计划依赖 golden baseline，但那是 E 任务。你做完 D 之后，等 E 跑完，再做 D-7.5 作为回归验证。
- **D-7.6**（`src/core/graph_agent/` → `packages/graph-agent/`）：**跳过**。这是物理目录重组，和 D-7.1-7.4 解耦，单独一个 PR 更清晰。建议 E 做完、D-7.5 回归过了之后再做。

---

## 七、验证方式

### 7.1 每次 commit 前必跑
```bash
pytest tests/ -q    # 必须保持 197+ passed
```

### 7.2 保守验证（手动）

因为没有 golden baseline，**额外跑一次 compiler 冒烟**（验证 loader + compiler 的 E2E 路径没被打断）：

```bash
pytest tests/compiler/ -v        # 所有 compiler 测试
pytest tests/graph_agent/ -v     # 所有 graph_agent 测试
```

### 7.3 不应该退化的接口

- `GraphAgentHarness.run(...)` 签名不变
- `GraphAgentHarness.resume(...)` 签名不变
- `GraphAgentHarness.get_thread_status(...)` 签名不变
- `RunContext` 字段不变（就是当前 `src/core/graph_agent/core/run_context.py` 的那 6 个字段）

---

## 八、不变量 / 碰不得的东西

1. **不改 vendored DeerFlow 的文件**（`src/core/graph_agent/deerflow/` 下的）除非更新 `deerflow/NOTICE.md`
2. **不改 PR #1 已经落地的 RunContext 设计**（保留 frozen=True，6 个字段）
3. **不改 `callbacks/events.py`** 里的 17 个 CallbackEvent 类型（这是 Studio 对接的契约）
4. **不动 DeerFlow subagent 线程池相关的 conftest 和 FIXME**（B 阶段做过完整分析，记录在 `tests/conftest.py` docstring 里——daemon=True 不解决问题，真解法是 upstream asyncio，非本次任务范围）
5. **不写 markdown 文档给 PM 看**（记忆：`feedback_markdown_as_engineering_dsl.md`——SKILL.md 是工程 DSL，PM 通过 Copilot 对话抛问题，不直接读代码）
6. **不引入新的 tracing 字段**（trace schema 是 Studio 对接契约，改动需要先和 Studio 团队对齐）
7. **沟通要说清楚、不省略**（记忆：`~/.claude/rules/communication.md`——指代不明会严重误导用户）
8. **Gemini 协作**：业务/设计决策必须先 `ask gemini`（`command ccb ask --wait --timeout 600 a2 <<EOF ... EOF`），发给他完整背景不要精简

---

## 九、接手第一步（你 `/clear` 后第一条 tool call）

```bash
cd /home/sevenx/coding/agent-harness
git status
git log --oneline -5
gh pr view 1 --json state,mergedAt
```

三件事判断：
- 工作目录有没有遗留改动（应该是干净的）
- 最近提交是不是 `feat/graph-agent-optimizations` 的 HEAD
- PR #1 是否已经 merged（`state: MERGED`）

**如果 PR #1 没合**，停下来，问用户："PR #1 还没合，是要先 review 合并，还是直接在 feat/graph-agent-optimizations 分支上起 refactor/harness-split？" 不要自作主张。

**如果 PR #1 已合**：
```bash
git checkout main
git pull origin main
git checkout -b refactor/harness-split
pytest tests/ -q    # 锁住起点的测试数
```

然后按 §六 的"推荐顺序"第一步（scaffold 4 个空文件）开工。

---

## 十、参考文档

- **本次拆分的原始设计**：`.kiro/specs/graph-agent-optimizations/deferred-items.md` §三 `D-7.0 / D-7.1 - D-7.4 / D-7.5 / D-7.6`
- **原 task 描述**：`.kiro/specs/graph-agent-optimizations/tasks.md` 的 7.1 / 7.2 / 7.3 / 7.4
- **设计原则**（为什么要拆）：`.kiro/specs/graph-agent-optimizations/design.md`（architecture 章节）
- **RunContext 结构**：`src/core/graph_agent/core/run_context.py`
- **harness.py 本体**：`src/core/graph_agent/core/harness.py`（1580 行，开工前建议整体过一遍）
- **CCB 协作规则**（什么时候 ask gemini）：`~/.claude/rules/ccb-collaboration.md`
- **编码规范**：`~/.claude/rules/code-style.md`
- **测试规范**：`~/.claude/rules/testing.md`
- **git 工作流**：`~/.claude/rules/git-workflow.md`

---

## 十一、Gemini 对本轮的评审（留给你参考）

PR #1 合并前，本次 branch 让 Gemini 做了一次完整评审。评审的完整结论写在 `.kiro/specs/graph-agent-optimizations/deferred-items.md` §六。关键几条对你 D 的执行有影响：

1. **HeartbeatEvent 用 threading 而非 asyncio** — Gemini 判定"接受"（因为 harness.run 是同步），你拆 harness 的时候 Heartbeat 启停逻辑要保留在 `GraphAgentHarness.run()` 的 try/finally 里，别搬到 PhaseExecutor。
2. **RunContext frozen=True 只阻 rebind、不阻内部 dict mutation** — Gemini 判定"待观察"。拆分时你要约定：**每个合作者只读 RunContext**，不 mutate `runtime_inputs` / `callbacks` 列表内容。如果业务需要 mutation，加方法到 RunContext 自己身上，不要合作者直接改。
3. **AgentLoopIterationMiddleware 挂 before_model** — Gemini 判定"接受"。这个中间件是 `cognitive/middlewares.py` 的，**不在你要拆的范围内**，但 PhaseExecutor 的 LLM 执行路径会用到它，抽的时候注意不要把它搬错位置。
4. **Golden baseline 只录了 1/3** — 这就是你没法做 D-7.5 回归的原因。用保守的单元测试补救（见 §六）。

---

## 十二、合并 PR #1 之前的 review-findings 补丁（commit `28e2ae6`，已推到 PR #1 分支）

PR #1 合并前，Claude + Gemini 做了一轮辩论（1 轮收敛）并打了一个补丁。新 session 开工前必须知道这些**已改动**和**留给 D 的 TODO**：

### 12.1 已修（你不用再修）

- **`run_id` NameError**：`src/core/graph_agent/core/harness.py` L1295 之前写的是 `run_id=run_id`、`storage_manager=storage_manager`，bare name 在 execute 闭包的 scope 里根本不存在，compaction 一触发就 NameError。现在改为从 `harness._active_run_context.run_id` / `.storage_manager` 读。
- **`RunContext` 加了 `run_id: str = ""` 字段**：位置在 `src/core/graph_agent/core/run_context.py` L20，`thread_id` 之后。默认空字符串是为了老测试 fixtures 不用改。
- **`resume()` 继承 `_run_id`**：从 `state["context"]["_run_id"]` 读出来放进 RunContext，保证 pre-pause 和 post-resume 的 sidecar 落在同一个 `_history/{run_id}/` 目录。
- **regression test**：`tests/graph_agent/core/test_compaction_closure_scope.py`（3 cases，AST 级别守住）。这个测试里的 `_find_save_compaction_sidecar_call()` 限定了"harness.py 里只能有一处 `_save_compaction_sidecar` 调用"。**D 拆分后如果新的 PhaseExecutor 里也有一处调用，这个 assert 会触发。你要更新测试的 `assert len(matches) == 1`，或者把检测逻辑改为"每一处 call site 都 check"**。

### 12.2 留给 D 的 TODO（Gemini 明确标记延后到 D-7.2 解决）

- **Subgraph child 实例并发 race**：`src/core/graph_agent/core/subgraph.py` 已经在 `subgraph_start = _time.monotonic()` 上方加了一段 FIXME 注释，指明"child harness 实例级别的 `_active_heartbeat` / `_active_run_context` 在并发 `child.run()` 调用时会互相覆盖，D-7.2 移到 per-run PhaseExecutor 后消失"。
- **你在 D 拆 PhaseExecutor 时的具体动作**：
  1. `_active_heartbeat` 不再挂在 `GraphAgentHarness` 实例上（当前 `harness.py` L520 `self._active_heartbeat = heartbeat`），改为每次 `run()` 新建一个 PhaseExecutor，Heartbeat 挂在它身上
  2. `_active_run_context` 同上，也搬进 PhaseExecutor
  3. `subgraph.py` 里那段 FIXME 注释删掉（bug 此时消失）
  4. `harness.py` L972 `harness._active_heartbeat.current_phase = phase.name` 这一行的读取点要跟着迁移（改成 `phase_executor._heartbeat.current_phase = ...` 或类似）
- **两个测试缺口**（Gemini 指出、本次没补）：
  1. `TracingClientProxy.PromptCapturedEvent` 没单测——你拆 PhaseExecutor 时 LLM 调用路径要覆盖
  2. `get_thread_status` 对 `AWAITING_INPUT`（Clarification 挂起）全流程只有字典级 mock，没有 LangGraph interrupt 的真实触发——这个跟 PhaseExecutor 抽象无关，但 D 阶段顺便补掉最好

### 12.3 本轮测试计数变化

- A 阶段补单测之前：182 passed
- A 阶段之后（heartbeat / sidecar / middleware）：197 passed
- review-findings commit 之后（scope 回归测试）：**200 passed**

你开工时 `pytest tests/ -q` 应该看到 200+。
