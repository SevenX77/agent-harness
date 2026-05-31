# tracing-and-observability (engine) — Baseline (Round 31 event_subscriber 切轨)

> **Status**: Updated by a1 (Codex), 2026-05-31 — T3 event_subscriber cutover synced
> **Scope**: Engine 执行观测性、默认 trace 落盘、实时事件订阅。
> **配套**: workspace 写入规范见 [workspace-spec](../workspace-spec/baseline.md)。

## 1. 观测性架构变迁

V0.3 当前主线不再暴露 public `trace_dir`，也不再暴露 public `callbacks` list。run-scoped trace 目录强制由 `workspace_dir` 推导；实时事件桥接参数是 `event_subscriber`：

- `run_skill(..., workspace_dir=..., event_subscriber=...)` 当前签名：`packages/graph-agent/src/graph_agent/core/runner.py:65-79`
- `_prepare_v030_event_sink()` 会创建 `_TraceJsonlSink` 并按需包装 subscriber / legacy callback：`packages/graph-agent/src/graph_agent/core/runner.py:237-248`
- `_run_v030_skill_dict()` 当前根据 `workspace_dir / "runs" / run_id` 推导 trace 输出。
- 当前主线把 event sink 传给 graph assembly；resolver 需要 callback 形对象时由 `_EventSinkCallbackAdapter` 桥接。

历史 bug 是：`_run_v030_skill_dict()` 曾经忘挂自动 tracing，导致 `run_skill()` 只返回 trace path 形状而不保证主线事件完整落盘。Round 31 / V4 目标是由 `run_skill()` 内部自动初始化 trace writer，修复这类调用方忘挂 callback 的问题。

V4 目标 API：

```python
event_subscriber: Callable[[CallbackEvent], None] | None = None
```

`event_subscriber` 是实时出口，不是落盘出口。用户不需要、也不能再通过 public API 创建 callback class 来决定 trace 文件写在哪里。

## 2. 默认落盘机制：黑匣子出口

调用 `run_skill` 时，即使不传任何 event subscriber，SDK 也必须自动向本次 run 目录写 trace：

```text
<workspace_dir>/runs/<run_id>/trace.jsonl
```

关键契约：

- `workspace_dir: Path` 必传。
- `run_id` 决定本次输出目录。
- 用户无法篡改 trace 路径。
- Predict 与 Run 同形，同写 `<workspace_dir>/runs/<run_id>/`。
- `trace.jsonl` 每行是一个可序列化 `CallbackEvent`。T3 已把旧 `tracing.jsonl` / summary JSON 主线替换为该单文件。

这相当于飞行黑匣子：只要引擎起飞，就必须留下可回放的事件记录。

现状实证：

- 当前 `_TraceJsonlSink` 写固定 typed stream `trace.jsonl`：`packages/graph-agent/src/graph_agent/callbacks/emit.py:15-26`
- 当前 `_CompositeEventSink` fan-out 到 trace sink、subscriber sink 和内部 callback sink：`packages/graph-agent/src/graph_agent/callbacks/emit.py:48-65`
- 当前 Studio run worker 传 `workspace_dir=run_dir.parent` 与 `thread_id=run_dir.name`，并用 `_queue_event_subscriber` 作为 Studio 实时状态桥接。

Round 31 后，trace 目录 setup 已降为 SDK internal 行为；Studio 只负责传 `workspace_dir` 和 run id。

## 3. 事件订阅机制：仪表盘出口

同一份内部事件源有两个出口：

- 默认出口：SDK 写 `<workspace_dir>/runs/<run_id>/trace.jsonl`
- 可选出口：SDK 调用 `event_subscriber(event)`

实时 UI、WebSocket、进度条、Timeline 首选 `event_subscriber`。它像飞行仪表盘：黑匣子照常落盘，仪表盘只负责把同源事件实时显示给前端。

目标签名：

```python
def run_skill(
    compiled_skill: CompiledSkill,
    inputs: dict,
    model_resolver: ModelResolverProtocol,
    workspace_dir: Path,
    event_subscriber: Callable[[CallbackEvent], None] | None = None,
) -> RunResult: ...
```

`predict_skill` 使用同样的 `event_subscriber` 参数。

现状实证：

- `CallbackEvent` 已是 Pydantic discriminated union：`packages/graph-agent/src/graph_agent/callbacks/events.py:450`
- `_SubscriberSink` 当前以函数形式调用 `event_subscriber(event)`：`packages/graph-agent/src/graph_agent/callbacks/emit.py:29-34`
- `_CallbackSink` 仅作为内部兼容调用 `callback.on_event(event)`：`packages/graph-agent/src/graph_agent/callbacks/emit.py:37-45`
- Studio 现有 queue bridge 是 `_queue_event_subscriber(process_queue)` 函数闭包：`apps/studio/backend/app/services/run_manager.py:74-78`

## 4. 遗留适配与清理

### 4.1 Public callback class 降级

Round 31 后，具体 callback class 不再是 public SDK setup API。

废除或隐藏：

- `AgentCallback` / `Callback` base class 继承体系对外暴露
- `TracingCallback(trace_dir=...)` 作为用户配置 trace 的方式
- `PredictTracingCallback` 作为外部可实例化 Predict API
- `EventStreamCallback` 作为独立 public class

当前 `PredictTracingCallback` 仍在 private predict 模块中：

- `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:76`

这类 class 可以作为 SDK internal 实现细节保留或迁移，但不能继续被描述为外部调用方应使用的 API。

### 4.2 StudioQueueCallback 纯函数化迁移

当前 Studio 后端已迁移：

- `_queue_event_subscriber(process_queue)` 返回函数闭包：`apps/studio/backend/app/services/run_manager.py:74-78`
- run worker 把闭包作为 `event_subscriber` 传给 `run_skill`：`apps/studio/backend/app/services/run_manager.py:95-104`

目标迁移为一个函数适配器：

```python
def enqueue_event(event: CallbackEvent) -> None:
    process_queue.put(event.model_dump(mode="json"))
```

然后调用：

```python
run_skill(
    compiled_skill,
    inputs,
    model_resolver=model_resolver,
    workspace_dir=workspace_dir,
    event_subscriber=enqueue_event,
)
```

### 4.3 同源双出口不变式

- 内部只有一个事件源。
- 默认落盘和实时订阅必须看到同一批 `CallbackEvent`。
- 写入 `trace.jsonl` 的事件必须能 replay 成 UI timeline。
- `event_subscriber` 抛错不能破坏默认 trace 落盘；SDK 应把订阅器错误归入运行期错误处理策略。

## 5. 与 workspace spec 的协同铁律

- Trace 路径只写 `<workspace_dir>/runs/<run_id>/trace.jsonl`。
- SDK 动作只写 `run_skill` / `predict_skill` / `evaluate_golden_baseline`。
- 不把 `trace_dir`、callback 实例、Predict tracing class 描述为 V4 public API。
