# 决议:引擎无法归类的异常不再冒充 LLM provider 失败

- 日期:2026-08-15
- 范围:engine(`packages/graph-agent/src/graph_agent/core/runner.py`)
- 状态:已实施

## 1. 问题

真机点 Predict 失败时,界面给出的诊断是:

```
Backend details: { "engine_error_code": "llm.provider_invoke_failed",
                   "message": "asyncio.run() cannot be called from a running event loop" }
```

错误码说"调用 LLM provider 失败",而真正发生的事情是引擎自己在事件循环线程上调了
`asyncio.run()`。这个标签把排查方向指向 gateway 和模型配置——那里什么问题都没有。
一个**自信、具体、错误**的归因比没有归因更贵:它让人往错的方向查。

## 2. 根因:这个默认值只可能是错的

`runner.py` 两处 `except Exception` 用同一行兜底:

```python
error_code = getattr(exc, "error_code", "llm.provider_invoke_failed")
```

而**每一个真正的 provider 异常都自带 error_code**:

- `core/llm_provider.py:62-68` —— `LLMProviderError.__init__(self, error_code: str, ...)`,
  `error_code` 是必填构造参数;
- `core/llm_provider.py:71-73` —— `LLMProviderMissingError` 在类级写死
  `error_code = "llm.provider_missing"`。

所以 `getattr(exc, "error_code", ...)` 对 provider 异常**永远取不到兜底值**。
兜底分支只在"异常没有自己的 error_code"时执行,而那**恰恰意味着它不是 provider 异常**。
这个默认值每次生效都是错的,没有例外。

**同一个函数里三行之外就有正确的判据**(`runner.py:1048-1051`):

```python
def _safe_provider_error_message(exc: Exception) -> str:
    error_code = str(getattr(exc, "error_code", ""))
    if isinstance(exc, LLMProviderError) or error_code.startswith("llm."):
        return "Provider invocation failed"
```

对同一个异常,message 那半边判定"这不是 provider 错误,原文放行";code 这半边判定
"这是 provider 调用失败"。两半在同一次异常处理里互相矛盾。

## 3. 这两处兜底和 `adapters/engine.py:392` 那处的区别(后者不改)

`apps/studio/backend/app/core/adapters/engine.py:388-396` 也有同一行默认值,但它包的是
`model.stream(...)` **内部**抛出的异常——那真的是一次 provider 调用,
`llm.provider_invoke_failed` 在那里是诚实的默认。**不改。**

`runner.py` 的两处包的是 `_execute_run_artifact_outputs(...)` /
`_run_compiled_artifact_predict_graph(...)`,也就是**整张图的一次执行**。
compile、assembler、state、IO 的任何异常都从这里出去。范围完全不同。

## 4. 决定

新增诚实的兜底码 `engine.unexpected_error`,并把两处重复的六行收敛成一个函数:

```python
def _artifact_error_result(exc: Exception, *, run_id: str) -> RunArtifactErrorResult:
    error_code = str(getattr(exc, "error_code", "") or "engine.unexpected_error")
    details = _safe_provider_error_details(getattr(exc, "details", {}))
    details.setdefault("exception_type", type(exc).__name__)
    ...
```

`details["exception_type"]` 照抄 `adapters/engine.py:390` 已有的做法:换掉错误的标签之后,
必须补上真实的类型,否则诊断信息只是从"错的"变成"空的"。

抽函数的理由:同一条规则的两份拷贝,且规则本身刚刚变复杂(判据 + 兜底 + 类型注记)。
两份而不是三份就抽,是因为它们是**同一条业务规则**的字面重复,不是"看起来像"的相似代码。

## 5. 参考的成熟做法

- **CPython `traceback` / PEP 3134 的取向**:异常链保留真实原因,不用上层的分类覆盖下层
  的事实。这里对应的是"没有归类就说没有归类",不用一个具体的下游原因去顶替。
- **gRPC 状态码规范**:`UNKNOWN` 是一个**显式**的码,专门表示"服务端没能把这个错误
  归到已知类别"。它没有把未知错误塞进某个具体码里。`engine.unexpected_error` 就是这个
  位置的等价物。**借的是"未知要有自己的名字"这一件事。**
- **没借** OpenTelemetry 那种把异常类型/堆栈整包塞进 attributes 的做法:本仓的
  `_contains_sensitive_error_text` 明确要拦 `traceback` 字样,泄漏面比诊断收益大。
  只取 `type(exc).__name__` 这一层。

## 6. 验收判据

`packages/graph-agent/tests/core/test_unclassified_run_error_code.py`:

1. `test_an_engine_fault_is_not_reported_as_a_provider_failure` —— executor 抛裸
   `RuntimeError`,error_code 必须是 `engine.unexpected_error`(修复前实测为
   `llm.provider_invoke_failed`)。
2. `test_an_unclassified_fault_keeps_what_actually_happened` —— 原始 message 保留,
   `details["exception_type"] == "RuntimeError"`,`retryable is False`。
3. `test_a_provider_failure_keeps_its_own_code` —— 抛 `LLMProviderError` 时
   `llm.provider_invoke_failed` 与 `retryable=True` 原样保留(这条修复前就绿,
   是防止改动越界的护栏)。
