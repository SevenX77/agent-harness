# MVP-1 T0 prep report

> 派发: a3 claude (T0-prep, 纯 read-only 调研, 配合 a1 codex 跑 T1).
> 输入: design.md §1.2 / §6, tasks.md T7, baseline-snapshot.md.
> 输出: 给 T3 / T5 / T7 提供数据 + 估时回归 + 发现 design.md 没考虑的 case.
> 注: 仅做 grep + read-only 分析, 没动任何 src/tests 文件.

---

## 1. `**state` 隐藏耦合排查 (D6)

### 命令

```bash
grep -rn '\*\*state\b' src/ tests/ --include="*.py"
```

### 结果

**0 hits**.

### 解读

`**state` dict-unpack 模式在 `src/core/graph_agent/` 和 `tests/graph_agent/` 全量代码里都不存在. design.md §6.1 预期 "0-3 处" 是保守估计, 实际为 0. 这是 MVP-1 拆分的好消息: 不存在 "把 state 整个 dict 摊开传给某个函数" 这种隐式耦合, T2 切换 WorkflowState 顶层字段时不会有暗 cane. 这条 D6 风险可以从 design.md §7 "After 验证清单" 直接打勾为 **已 0**.

附注: 排查范围只覆盖了 `src/` + `tests/`. 用户领域代码 (`skills/*/`) 不在 MVP-1 拆分目标内, 无需统计.

---

## 2. `state["context"]` 站点详细分析

### 站点总数复核

baseline-snapshot.md 报 26 站点; 实际 grep `\(state\|next_state\|initial_state\|final_state\)\["context"\]` 在 `src/core/graph_agent/` 内得到 **25 处**. baseline 多 1 是因为 baseline 用了更宽的 grep (含纯 `state["context"]` 子串包括 docstring). 本节按 25 个真实代码站点逐行分析, 含归属判定.

### 25 站点详表

| 序号 | 文件 | 行号 | 上下文摘要 | 操作 (R/W/Mut) | 涉及 _ 字段 | 归属子任务 |
|---|---|---|---|---|---|---|
| 1 | core/runner.py | 277 | `ctx = final_state["context"]` 取最终 ctx 给输出聚合 | R | `_trace_path` (281 pop) | T3 |
| 2 | core/harness.py | 313 | `cloned_ctx = copy.deepcopy(state["context"])` (在 _clone_state 里 deepcopy 整个 ctx) | R+Mut(深拷) | (整体) | T3 (helper 重画) |
| 3 | core/harness.py | 317 | `context={"field": "context", "type": type(state["context"]).__name__}` 异常上下文打日志 | R | (类型探测) | T3 |
| 4 | core/harness.py | 484 | docstring `into ``initial_state["context"]``` 引用 | (文字) | (文档) | T3 (改 docstring) |
| 5 | core/harness.py | 547 | `initial_state["context"]["_thread_id"] = tid` | W | `_thread_id` | T3 |
| 6 | core/harness.py | 548 | `initial_state["context"]["_run_id"] = run_id` | W | `_run_id` | T3 |
| 7 | core/harness.py | 549 | `initial_state["context"]["_unattended"] = bool(unattended)` | W | `_unattended` | T3 |
| 8 | core/harness.py | 555 | `initial_state["context"]["_persistent_runtime_inputs"] = dict(persistent_runtime_inputs)` | W | `_persistent_runtime_inputs` | T3 |
| 9 | core/harness.py | 565 | `initial_state["context"]["_persistent_storage_config"] = effective_storage_config` | W | `_persistent_storage_config` | T3 |
| 10 | core/harness.py | 608 | `initial_context=_safe_jsonable_dict(initial_state["context"])` 传给 RunStartEvent | R | (整体) | T3 |
| 11 | core/harness.py | 1024 | `effective_thread_id = thread_id or state["context"].get("_thread_id")` resume 路径读 thread_id | R | `_thread_id` | T3 |
| 12 | core/harness.py | 1039 | `raw = state["context"].get("_run_id") if isinstance(state.get("context"), dict) else None` resume 路径读 run_id | R | `_run_id` | T3 |
| 13 | core/harness.py | 1050 | `state_context = state.get("context") if isinstance(state.get("context"), dict) else {}` | R | (整体) | T3 |
| 14 | core/harness.py | 1055 | `persisted = state_context.get("_persistent_runtime_inputs") if state_context else None` | R | `_persistent_runtime_inputs` | T3 |
| 15 | core/harness.py | 1060 | `persisted_sc = state_context.get("_persistent_storage_config") if state_context else None` | R | `_persistent_storage_config` | T3 |
| 16 | core/harness.py | 1096 | `unattended=bool(state_context.get("_unattended"))` | R | `_unattended` | T3 |
| 17 | core/retry_router.py | 36 | docstring `state["context"]` 引用 | (文字) | (文档) | T4 (改 docstring) |
| 18 | core/retry_router.py | 43 | `if "_retry_feedback" in state["context"]:` retry 路径判定 | R | `_retry_feedback` | T4 |
| 19 | core/phase_executor.py | 130 | `cb.on_phase_start(phase.name, dict(next_state["context"]))` 给 callback 喂 ctx 快照 (code-only) | R | (整体) | T4 |
| 20 | core/phase_executor.py | 139 | `result = fn(next_state["context"])` 给 code-only tools 传 ctx | R+Mut(by tool) | (整体) | T4 (**接口契约重画**) |
| 21 | core/phase_executor.py | 141 | `next_state["context"]["_last_output"] = result` code-only tool 返回值落 ctx | W | `_last_output` | T4 |
| 22 | core/phase_executor.py | 143 | `next_state["context"].pop("_retry_feedback", None)` code-only 退出前清 retry feedback | Mut(pop) | `_retry_feedback` | T4 |
| 23 | core/phase_executor.py | 149 | `dict(next_state["context"])` 给 callback on_phase_end 喂 ctx 快照 (code-only) | R | (整体) | T4 |
| 24 | core/phase_executor.py | 177 | `if next_state["context"].pop("_validation_middleware_phase", None) == phase.name:` validation 节点判定上轮 middleware 已校验 | Mut(pop) | `_validation_middleware_phase` | T4 |
| 25 | core/phase_executor.py | 186 | `passed, errors = phase.validator(next_state["context"])` 把 ctx 整体喂给 validator 函数 | R | (整体) | T4 (**接口契约重画**) |
| 26 | core/phase_executor.py | 207 | `next_state["context"].pop("_validation_warnings", None)` 校验通过后清 warnings | Mut(pop) | `_validation_warnings` | T4 |
| 27 | core/phase_executor.py | 235 | `next_state["context"]["_validation_warnings"] = errors` 重试耗尽时把 errors 写为 warnings | W | `_validation_warnings` | T4 |
| 28 | core/phase_executor.py | 238 | `next_state["context"]["_retry_feedback"] = errors` 还可重试时把 errors 写为 retry feedback | W | `_retry_feedback` | T4 |
| 29 | core/phase_executor.py | 274 | `ctx = state["context"]` LLM phase 提取 ctx 引用 (后续大量本地 mut) | R+Mut | (整体) | T4 |

(注: phase_executor 内还有约 30 处直接通过本地变量 `ctx` 访问 _ 字段, 实际是站点 #29 的下游, 都归 T4 改造范围.)

### 操作分布

- W (赋值新值): 站点 5/6/7/8/9/21/27/28 = 8 处
- Mut (pop / 修改): 站点 22/24/26 (+ phase_executor 内大量 ctx pop) = 3 处直接 + 多处下游
- R (读取): 其他 = 多处
- 文档/字符串引用: 站点 4/17 = 2 处, 改 docstring 即可

### 子任务归属分布

| 子任务 | 直接负责站点 | 累计修改行数估 |
|---|---|---|
| T3 (runner.py + harness.py) | 1, 2, 3, 4, 5-16 = 14 站点 | 60-100 行修改 (含 docstring + try/except 容错) |
| T4 (phase_executor.py + retry_router.py) | 17, 18, 19-29 = 13 站点 + 下游 30+ | 200-300 行修改 (核心枢纽, 含 helper `_ctx_text` `_ctx_reports` `_append_validation_warning` 全部改造为 read flow.X) |
| T5 (middlewares.py) | (不在 state["context"] 直接路径, 但 ctx 通过 context_ref 间接传入, 见第 5 节) | 80-150 行 |
| T6 (finish.py + md_to_json.py + memory.py + ambiguity.py) | (同 T5, ctx dict 间接传入) | 50-80 行 |

### 关键发现 (站点 20 + 25 — 接口契约级 risk)

#### 站点 20: `result = fn(next_state["context"])` (phase_executor.py:139)

**当前**: code-only phase 的工具 `fn` 接收 `state["context"]` 整个 dict 并可任意 mutate.

**T2/T4 后矛盾**: state 拆成 `data` (BusinessData Pydantic) + `flow` (FrameworkState Pydantic). 工具不能再接收一个 plain dict 任意写, 否则就违反 BusinessData 的 `extra="allow"` 但是又无法绕过 FrameworkState 的 `extra="forbid"`.

**design.md 没明确**: 工具接口的迁移路径. 三种可能:
- a) 给工具一个合并的 plain dict 视图 (read-only? read-write?), 出 phase 后自动路由回 data/flow
- b) 把工具签名改成 `fn(data: BusinessData, flow: FrameworkState) -> ...` (大改, 影响所有 SKILL 作者代码)
- c) 工具接收 state, 自己判断写哪边 (依赖工具作者纪律, 风险高)

**建议**: T4 实施时跟 a1 codex 当场决, 或先 ask Gemini 做接口契约设计, 不能在 T4 做完才发现.

#### 站点 25: `passed, errors = phase.validator(next_state["context"])` (phase_executor.py:186)

**当前**: validator 函数接收 `state["context"]` 整个 dict, 既能读业务字段也能读 `_X` 框架字段.

**T2/T4 后矛盾**: 业务 validator (用户写的) 应该只看 `data` (BusinessData). 但部分内置 validator (例如检查 `_validation_warnings`) 需要看 `flow`.

**design.md 没明确**: validator 签名迁移路径. 推荐方案:
- 把 validator 签名改成 `validator(data: BusinessData) -> tuple[bool, list[str]]` — 统一只能看业务数据
- 框架内部自检逻辑 (warnings 累积, retry feedback) 跟业务 validator 解耦, 不通过 validator 接口

T4 改造时必须跟 T7 测试 mock 一起改, 否则会导致业务 SKILL 的 validator 函数全部 break.

---

## 3. 测试 mock state 受影响清单

### 范围扫描

baseline 报 "5 个文件". 实际 `grep -rln 'WorkflowState\|state\[\|"context":\s*{\|{"context"' tests/graph_agent/ --include="*.py"` 返回 **10 个 core/tools 文件 + 3 个 cognitive 文件 = 13 文件**. baseline 的 "5 文件" 可能只统计了 `state["context"]` 直接 grep, 不含通过 `_make_state(context=...)` helper 间接 mock 的文件.

### 13 文件分组详表

#### Group A — Heavy refactor (`_make_state` helper-based, 90%+ 测试需改) — 2 文件

| 文件 | 行数 | 测试数 | "context" 出现 | 需改测试估 | 改动量 |
|---|---|---|---|---|---|
| tests/graph_agent/core/test_phase_executor.py | 346 | 16 | 5 | **16 (全部, 因为 _make_state helper 是共用入口)** | LARGE |
| tests/graph_agent/core/test_phase_executor_validation.py | 202 | 8 | 9 | **8 (全部, 同理)** | LARGE |

helper 模式:
```python
def _make_state(context=None, ...) -> WorkflowState:
    return {
        "context": dict(context or {}),
        "messages": [],
        "current_phase": "",
        "retry_counts": {},
        "metrics": {},
    }
```
T7 必须改为:
```python
def _make_state(business=None, flow=None, ...) -> WorkflowState:
    return {
        "data": BusinessData(**(business or {})),
        "flow": FrameworkState(**(flow or {})),
        "messages": [],
    }
```
helper 内只是声明改造, 但每个调用点的 `assert state_out["context"] == {...}` 断言行需逐一改成 `state_out["data"].model_dump() == {...}` 或类似, 这部分是逐 assert 改.

#### Group B — Medium refactor (cognitive 中间件 ctx 字面量, 10-15 测试改) — 3 文件

| 文件 | 行数 | 测试数 | "_finish_task_result" 等出现 | 需改测试估 | 改动量 |
|---|---|---|---|---|---|
| tests/graph_agent/cognitive/test_finish_v2.py | 570 | 23 | 11 (heavy use of `ctx={...}` 直接 dict mock) | **15-20** | LARGE (T6 finish.py 接口变更需要这里全改) |
| tests/graph_agent/cognitive/test_middlewares.py | 268 | 18 | 2 (`context_ref={...}`) | **2-4** (主要是 unattended 相关) | SMALL |
| tests/graph_agent/cognitive/test_agent_loop_iteration_middleware.py | 105 | 8 | 0 | **0** | NONE |

test_finish_v2.py 是改造大头. 它直接用 `ctx = {...}` plain dict 作 finish_task 的输入参数 mock, T6 改 finish_task 的 contract (改返回结构而非写 ctx) 后这里大改.

#### Group C — Small refactor (单一 inline state 字面量, 1-2 测试改) — 7 文件

| 文件 | 行数 | 测试数 | "context" 出现 | 需改测试估 | 改动量 |
|---|---|---|---|---|---|
| tests/graph_agent/core/test_graph_builder.py | 227 | 14 | 2 | **2** (line 169-175 + line 194-200 inline state literals) | SMALL |
| tests/graph_agent/core/test_retry_router.py | 116 | 9 | 1 | **5-6** (`_make_state(context={...})` helper 共用 → 多数测试 affected, 但 assert 改动浅) | SMALL-MEDIUM |
| tests/graph_agent/core/test_harness_phase_b_invariants.py | 287 | 16 | 1 | **1-2** (line 268 inline state for resume) | SMALL |
| tests/graph_agent/core/test_harness_state_machine_resources.py | 220 | 8 | 5 | **4-6** (多个 inline state literals) | MEDIUM |
| tests/graph_agent/core/test_harness_awaiting_input_no_completion.py | 118 | 2 | 1 | **1** | SMALL |
| tests/graph_agent/core/test_harness_save_outputs_failure.py | 118 | 2 | 1 | **1** | SMALL |
| tests/graph_agent/core/test_runner_silent_failures.py | 133 | 3 | 1 | **1** | SMALL |
| tests/graph_agent/tools/test_md_to_json.py | 166 | 6 | 1 | **1** (mock `run_skill` 返回值含 `"context": {...}`, 这是 sub-skill 调用的返回结构, 跟 state 拆分有关) | SMALL |

### 总改动量估算

总测试: **125** (10 core + 3 cognitive 测试文件)
预计需改: **57-72** (47-58% 测试)
分布:
- Group A: 24 测试全改 (2 文件 helper 入口共用)
- Group B: 17-24 测试全/部分改 (3 文件 cognitive)
- Group C: 16-24 测试逐 inline 改 (8 文件零散 inline state)

T7 实施建议:
1. 优先把 Group A 两个文件的 `_make_state` helper 改造成新 schema, 让 helper 的 default 字段名匹配 (`data` / `flow`)
2. Group B 的 test_finish_v2.py 必须等 T6 (finish.py 改造) 完成后才能批量改, 否则 mock 跟实际 fn 签名错位
3. Group C 的 inline state literals 用 sed 批量替换基础结构 (`"context": {` → `"data": BusinessData(`), 然后逐个手工修
4. 顺序: A 先改 helper → B 改 cognitive (跟 T5/T6 强耦合, 可由 a1 codex review 时一起跑) → C 收尾

**风险**: 测试改动跟 a1 codex 的 T2/T4/T6 改动强耦合, T7 不能在 T2-T6 全部 commit 前启动, 否则 import 不通 / Pydantic 报错. tasks.md 的 T7 依赖 "T2-T6" 写得对.

---

## 4. `_underscore` 字段映射表 (基于 design.md §1.2 + 实际代码站点)

baseline 报 17 个 `_` 字段 (含 `_md_id` 但实际 `_md_id` 仅出现在 ParsedBlock 内部, 不在 state 字典里; 加上 `_retry_feedback` `_trace_path` 实际是 18+ 字段在 ctx).

### 完整映射 + 站点

| 旧字段 (state["context"][...]) | 新归属 | design.md §1.2 字段名 | 实际代码站点 (file:line) |
|---|---|---|---|
| `_md_id` | flow.md_id (但物理隔离到 ParsedBlock, 不再进 state) | flow.md_id | (无 src/ ctx 站点; 见 ParsedBlock 实现) |
| `_finish_task_result` | flow.finish_task_result | flow.finish_task_result | finish.py:79,87 / phase_executor.py:518,560,564,699 / middlewares.py:438 |
| `_io_errors` | flow.io_errors | flow.io_errors | io/manager.py:326,329 |
| `_validation_warnings` | flow.validation_warnings | flow.validation_warnings | phase_executor.py:207,235 / harness.py:300,305,307 |
| `_thread_id` | flow.thread_id | flow.thread_id | harness.py:547,1024 / phase_executor.py:476 |
| `_run_id` | flow.run_id | flow.run_id | harness.py:548,1039 |
| `_unattended` | flow.unattended | flow.unattended | harness.py:549,1096 / middlewares.py:792 |
| `_persistent_runtime_inputs` | flow.persistent_runtime_inputs | flow.persistent_runtime_inputs | harness.py:555,987,1055 |
| `_persistent_storage_config` | flow.persistent_storage_config | flow.persistent_storage_config | harness.py:565,993,1060 |
| `_sub_run_id` | flow.sub_run_id | flow.sub_run_id | phase_executor.py:364 / tools/builtin/parallel_map.py:215 |
| `_ambiguity_reports` | flow.ambiguity_reports | flow.ambiguity_reports | harness.py:292 / cognitive/ambiguity.py:45,48 |
| `_last_output` | flow.last_output | flow.last_output | phase_executor.py:122,141,697 |
| `_group_key` | flow.group_key | flow.group_key | phase_executor.py:365 / tools/builtin/parallel_map.py:216 |
| `_md_schema` | flow.md_schema | flow.md_schema | tools/md_to_json.py:527,536,538,543 |
| `_md_schema_path` | flow.md_schema_path | flow.md_schema_path | tools/md_to_json.py:528,536,547 / phase_executor.py:283 |
| `_md_type_dict` | flow.md_type_dict | flow.md_type_dict | phase_executor.py:285 |
| `_working_memory` | flow.working_memory | flow.working_memory | phase_executor.py:287,524,570,728 / cognitive/memory.py:13 / cognitive/middlewares.py:111 / tools/builtin/context_access.py:25 |
| `_validation_middleware_phase` | flow.current_phase (合并) ⚠️ | flow.current_phase | phase_executor.py:177 (pop), 276 (set) |
| `_current_phase` | flow.current_phase | flow.current_phase | phase_executor.py:275 / cognitive/ambiguity.py:52 |
| `_retry_feedback` | (design.md 没列出) ⚠️ | flow.retry_feedback (新增) | retry_router.py:43 / phase_executor.py:143,238,291,292 |
| `_trace_path` | (design.md 没列出) ⚠️ | flow.trace_path (新增) | runner.py:281 |

### ⚠️ design.md §1.2 漏掉的字段 (需 a1 codex 在 T1 模型里补)

1. **`_retry_feedback`**: 跨 phase 通信用, retry_router 用它判定是否要回到 retry_target. design.md FrameworkState 模型里**没有** `retry_feedback: list[str] | None` 字段. **必须加**, 否则 T2 后 retry_router.py:43 编译就过, runtime 就因为 Pydantic forbid 抛 ValidationError.

2. **`_trace_path`**: runner.py 取 final 时弹出. 仅用于把内部框架元数据冒泡给最外层调用者. design.md 没列, 需在 FrameworkState 加 `trace_path: str | None = None`.

3. **`_validation_middleware_phase` 合并到 `flow.current_phase` 的语义错位**: 当前两个 _字段是不同语义:
   - `_current_phase`: 当前正在跑的 phase 名字
   - `_validation_middleware_phase`: 标记 "上轮 LLM phase 已经被 ValidationMiddleware 内部跑过 validator 了, validation 节点不要重复跑"
   
   合并到 `flow.current_phase` 等价于 "phase 名字本身就是已校验标记", 但其实是: 即使是同一 phase 名, validator 可能已被 middleware 跑过 (LLM phase) 或没被跑过 (code-only / validation 节点入口). 这个语义信号丢了, 会导致 phase_executor.py:177 行的 "if pop == phase.name" 判定逻辑无法正确还原.
   
   **建议**: 拆出 `flow.last_validated_phase: str | None`, 跟 `flow.current_phase` 不合并. 否则改造后 ValidationMiddleware 跑过的 phase, validation 节点会重复跑一次 validator, 重复 retry, 浪费时间且可能导致 false negative.

### `_md_id` 注

design.md §4.2 说 `_md_id` 已迁移到 ParsedBlock.meta, "底层仍混" — 但 `grep -rn '"_md_id"' src/` 在当前 baseline 的 src/ 里 **0 hits**, 表明 `_md_id` 已经物理消失, MVP-1 不需要再处理. baseline-snapshot.md 的 17 个 _ 字段表里没有 `_md_id`, 表示 baseline 编写者已正确反映此事实.

---

## 5. ContextBridge 当前实现 + 改造点

### 当前实现

文件: `src/core/graph_agent/core/manifest.py` 行 138-150.

```python
class ContextBridge(BaseModel):
    """Input/output wiring between parent and child skills.

    Retained for the upcoming A8 ContextBridge merge (T10), which will
    consolidate this Pydantic version with the dataclass mirror in
    ``core/types.py``. The 1.x DelegatePhase consumer was removed in
    MVP-0 B1; new V2 delegation will reuse this same model.
    """

    model_config = ConfigDict(extra="forbid")

    inputs: dict[str, str] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)
```

### 当前接口

- 字段类型: 两个 `dict[str, str]` (inputs / outputs), key 是子 skill 的 ctx 字段名, value 是父 skill 的 ctx 字段名 (字符串路径).
- 行为: 仅作 schema 占位; 1.x 的 DelegatePhase consumer 已删, V2 复用未启动.
- 没有方法, 仅 model_config + 两个字段.

### 当前 ContextBridge 跟 MVP-1 的关系

design.md §5.1 写 "ContextBridge 演化 (T10 已收敛到 Pydantic 版的延续)", 意思是 ContextBridge 在未来 V2 跨 skill 委派中的角色: **把父 skill 的字段 mapping 到子 skill 的字段, 涉及业务数据传递**. 在 MVP-1 阶段 ContextBridge 不直接出现在 state 拆分核心路径, 但 **它将成为 BusinessData 的字段 schema 来源** (跟 SchemaEngine / output_schema 类似).

### 按 design.md §5.1 的演化要求

design.md §5.1 要求: ContextBridge 加 `to_business_data_schema()` 方法.

#### 接口设计建议 (待 a1 codex 实施)

```python
class ContextBridge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inputs: dict[str, str] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)

    def to_business_data_schema(self) -> dict[str, type]:
        """Return a {field_name: field_type} dict suitable for dynamic
        BusinessData field definition.

        当前 inputs / outputs 的 value 是 'parent.field.path' 字符串, 
        类型信息丢失. MVP-1 实施有两个选择:
        
        a) 简化版 (推荐 MVP-1): 全部映射为 Any, 保 extra='allow' 兼容性,
           运行时由 SKILL 作者决定具体类型. 
        b) 完整版 (MVP-2 SchemaEngine 之后): 从 SKILL.md output_schema 取真实
           Pydantic 类型, 跟 ContextBridge 一起组成 BusinessData 子模型.
        """
        return {field_name: Any for field_name in self.inputs}
```

#### MVP-1 阶段建议

design.md §5.1 现行措辞 "现存 ContextBridge 类增加 to_business_data_schema() 方法" 是 **方向声明** 不是 MVP-1 必跑要求. 我建议:
- MVP-1 阶段: ContextBridge 不动 (现在 V2 还没启动用它)
- MVP-1 只在 BusinessData 上靠 `extra="allow"` 容纳动态字段
- T10 正式启动 V2 跨 skill 委派时, 同步启用 `to_business_data_schema()`

如果 a1 codex 强行在 T1 加这个方法, 会因为没有调用方而成为死代码, 跟 MVP-1 "只做 state 拆分" 的最小集合违背. **建议 T1 / T7 验收都不要求 ContextBridge 改动.**

---

## 整体评估

### 估时回归 (vs Gemini design 估时)

| 子任务 | Gemini 估 | 本调研估 | 差距原因 |
|---|---|---|---|
| T3 (runner+harness ctx 迁移) | 1h | **1.5-2h** | harness.py 含 14 个 ctx 站点, 多处是 try/except + isinstance 容错, 不是简单 search-replace; resume 路径跨函数引用. 含 docstring 改写. |
| T5 (middlewares) | 2h | **3-4h** | ValidationMiddleware 的 ctx[] 写入跟 finish_task 强耦合, 需配合 T6 一起改; ClarificationMiddleware 通过 `context_ref` 间接持 ctx; UnattendedClarification 在 line 792 inline read `_unattended`. 加上 test_finish_v2.py 23 测试要全改. |
| T7 (test mock 批量) | 4h | **4-5h** | 13 文件 (baseline 报 5 文件低估), 125 测试, 57-72 测试要改, 含 `_make_state` helper 改 + 逐个 assert 改 + cognitive ctx mock 改. 大概率超 4h. |

总体: 关键路径从 14h 估到 **17-19h** (含调研期已发现的 risks 缓冲). 跟 tasks.md 的 18-22h 总估时一致, 没有惊吓.

### 风险点 (design.md 没充分考虑的 case)

1. **`_retry_feedback` 字段在 design.md FrameworkState 缺失** — 必须 T1 时补, 否则 T2 后 retry_router.py:43 一跑就 Pydantic ValidationError. **优先级: 阻塞 T1 验收.**

2. **`_trace_path` 字段同上** — runner.py 出口要弹出. T1 必须补到 FrameworkState. 优先级同上.

3. **`_validation_middleware_phase` 合并到 `flow.current_phase` 语义错位** — 当前两字段语义不同, 合并会破坏 ValidationMiddleware 已校验标记. **建议: 拆出 `flow.last_validated_phase: str | None`, 不要合并.**

4. **code-only phase 工具接口 (phase_executor.py:139)** — 工具签名 `fn(ctx)` 在 state 拆分后没明确迁移路径. design.md 没说工具接收 plain dict / Pydantic / state 哪种. **建议 T4 启动前先就这个接口做小型 ask Gemini 设计 review.**

5. **validator 接口 (phase_executor.py:186)** — `validator(ctx)` 同上, 业务 validator 应该只看 BusinessData 还是看整个 state, 没明确. **建议 T4 启动前确定签名.**

6. **`md_to_json` 工具读 ctx 的迁移路径** — md_to_json.py:543 `ctx.get("_md_schema")` 读取一个 Pydantic 类对象 (不是字符串). 这个类对象当前直接放在 ctx, T2 后必须放到 `flow.md_schema`. 但 FrameworkState `extra="forbid"` + `md_schema: dict[str, Any] | None = None` 的类型签名 (design.md §1.1) 跟 "Pydantic 类对象" 不匹配 — 应改成 `md_schema: type | None = None`. **优先级: T1 模型定义时确定类型.**

7. **`parallel_map` 通过 `inputs` dict 注入 `_sub_run_id` / `_group_key`** (parallel_map.py:215-216) — 这是 sub-run 启动期把元数据注入到 sub-skill initial_state 的路径. 改造后 sub-skill 启动时这两字段必须从 `inputs` (sub-skill 业务输入) 移到 `flow.sub_run_id` / `flow.group_key`. design.md 没追踪这条路径. **建议 T3 兼带处理 sub-skill 启动逻辑.**

8. **callbacks ctx 快照 (phase_executor.py:130, 149, 304, 553)** — callbacks 接收 `dict(ctx)` 快照. 改造后是给 `dict(state["data"])` (业务) 还是 merged dict (业务+框架) 还是只给 BusinessData.model_dump? 这关系到 TracingCallback / MetricsCallback 的现有事件 schema. **建议 T4 时跟 a1 codex 当场决, 默认建议 merged dict 保后向兼容**.

### 派发建议 (给主控调度)

- **T1 派发前**: 把上面 risk 1+2+3+6 (FrameworkState 字段定义补 retry_feedback / trace_path + last_validated_phase 拆字段 + md_schema 类型定义) **加到 T1 brief**, 否则 T2 跑一半 a1 codex 会自己再问一遍, 浪费一轮 review.
- **T4 派发前**: risk 4+5+8 (工具接口 / validator 接口 / callbacks 快照) 单独 ask Gemini 做 30min 设计 review, 避免 T4 改一半才发现接口契约模糊.
- **T7 派发前**: 把本节 Group A/B/C 文件分组 + sed 批量替换思路写进 T7 brief, 减少 a3 自由发挥成本.
- **T3 跟 T7 并行**: tasks.md 已给出 T3 跟 T4 并行, 但 T3 的 harness.py 改动跟 T7 (test_harness*) 必须同 commit, 否则 PR 间隔过大测试不过. 建议 T3 + 对应 T7 子集合并 commit.

完结. 本报告 100% read-only, 未触动任何 src/tests 文件.
