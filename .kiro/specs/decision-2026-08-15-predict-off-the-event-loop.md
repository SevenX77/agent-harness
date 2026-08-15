# 决议:predict 端点把引擎交给工作线程,不在事件循环上跑

- 日期:2026-08-15
- 范围:studio backend(`apps/studio/backend`)
- 状态:已实施
- 相关:同一天那批引擎缺陷(`decision-2026-08-15-engine-*.md`)。这一条不是引擎缺陷,
  是 Studio 的调用方式错误,但它把那批引擎修复的成果全部挡在了界面之外。

## 1. 问题

在桌面 app 里点 Predict,得到:

```
Error code: PREDICT_FAILED
Retry strategy: not_retryable
Backend message: asyncio.run() cannot be called from a running event loop
Backend details: { "engine_error_code": "llm.provider_invoke_failed", ... }
```

而**同一个 skill、同一份引擎代码,离线跑 `predict_skill(...)` 是 `success = True`**。
差别只在调用方。

## 2. 根因

`apps/studio/backend/app/routers/runs.py` 的 predict 端点是 `async def`,却直接调用
同步的 `predictor_service.dispatch_predict_job(...)`。该函数会把整个引擎跑完,而引擎的
批处理路径内部调用 `asyncio.run()`:

- `packages/graph-agent/src/graph_agent/core/graph_assembler.py` `_run_batch_iterate_payload`
  → `item_payloads = asyncio.run(_gather_indexed(items, concurrency, run_one))`
- 同文件的 subagent 批处理路径 → `return asyncio.run(_run_all())`

`asyncio.run()` 在**已有运行中事件循环的线程**上必然抛
`RuntimeError: asyncio.run() cannot be called from a running event loop`。
FastAPI 的 `async def` 路径操作正是在事件循环线程上执行的,于是:**任何用到
`iterate.mode=batch` 的 skill,从界面点 Predict 一定失败。**

**同一个函数的另一个调用方是对的**,这就是契约意图的证据 ——
`apps/studio/backend/app/services/copilot_tools.py`:

```python
result = await asyncio.to_thread(
    predictor.predictor_service.dispatch_predict_job, skill_id
)
```

所以 copilot 工具路径一直能 predict,界面按钮一直不能。两条路走同一个函数,一条包了
线程一条没包 —— 这是本次缺陷的完整解释。

## 3. 参考的成熟做法(以及借了什么、没借什么)

- **Starlette / FastAPI 自己的分工**:非 `async def` 的路径操作由框架自动丢进
  threadpool(`run_in_threadpool`);`async def` 则原样跑在循环上,阻塞调用会卡住
  整个进程。官方给 `async def` 里做阻塞工作的答案就是显式移交线程。
- **CPython 标准库 `asyncio.to_thread`**(3.9+):`await` 一个在 default executor
  里跑的同步可调用对象,异常照常沿 await 传回。**借的就是这一件**。
- **没借**"让引擎整条链变 async":那要把 LangGraph 的同步节点路径全部改写,
  影响面远大于收益,且引擎作为纯 SDK 保留同步入口是合理的。
- **没借** `nest_asyncio` 之类"让 `asyncio.run` 在循环里也能跑"的补丁:它靠给事件
  循环打猴子补丁实现,把一个明确的错误变成难以推理的隐式行为,与本仓
  「显式优于隐式」直接冲突。

## 4. 决定

predict 端点改为:

```python
result = await asyncio.to_thread(
    predictor_service.dispatch_predict_job,
    skill_id,
    request.mock_llm,
    input_data=request.input_data,
    current_hashes=request.current_hashes,
)
```

`try/except` 原样保留 —— `to_thread` 会把线程里的异常沿 `await` 抛回,
`PredictArtifactError` / `PredictDeadlockError` 的翻译逻辑不受影响。

## 5. 关键设计决定

- **修在 Studio,不修在引擎。** 引擎提供的是**同步** API;同步 API 内部用
  `asyncio.run` 做并发 IO 是正当实现。错的是"在事件循环线程上调用一个会跑满整个
  引擎的同步函数"——这在 `asyncio.run` 那条报错之外,本身也会把整个后端卡死到
  predict 结束为止。根因在调用方。
- **不改 `iterate.mode=batch` 的实现来绕开。** 那是拿产品功能迁就一个调用错误。
- **顺带记下一处误导性错误码**:这个 `RuntimeError` 被包装成
  `engine_error_code: "llm.provider_invoke_failed"`。它与 LLM provider 毫无关系,
  这个标签把排查方向指向了 gateway。错误码的归属修正不在本 PR 范围,单独记录。
- **本 PR 只改这一个调用点。** 同一路由里 `list_runs` / `get_run_detail` /
  `delete_run` 也是在 `async def` 里做同步文件读,量级小得多,属于另一类问题,
  不夹带进来(仓规:一个任务一个 PR)。

## 6. 验收判据

`apps/studio/backend/tests/routers/test_predict_runs_off_the_event_loop.py`:

1. `test_predict_endpoint_calls_the_engine_without_a_running_loop` —— 打桩的
   `dispatch_predict_job` 自己调 `asyncio.get_running_loop()`,必须抛 `RuntimeError`
   (即"我不在事件循环线程上")。修复前该断言为 `assert True is False`。
2. `test_predict_endpoint_still_surfaces_engine_errors` —— 移到线程之后,
   `PredictArtifactError` 仍然被端点翻译成 4xx,错误路径没被吞掉。

外加 backend 全量套件不回归,以及真机复验:在桌面 app 里点 Predict,
带 batch 相位的 skill 不再报 `asyncio.run() cannot be called from a running event loop`。
