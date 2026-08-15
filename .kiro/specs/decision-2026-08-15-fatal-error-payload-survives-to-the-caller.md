# 决议:引擎已经给自己定过性的错误,不许在出口被压回「不明」

- 日期:2026-08-15
- 范围:engine(`core/runner.py`)
- 状态:已实施
- 相关:`decision-2026-08-15-engine-unclassified-error-code.md`(#819)。
  **这一条修的是那一条自己留下的洞**——#819 把兜底码从 `llm.provider_invoke_failed`
  改成 `engine.unexpected_error` 是对的,但它读错了属性,于是把**本来分好类的**
  引擎致命错误也一起压成了「不明」。

## 1. 现场

真机点 Predict,界面错误抽屉里的原文:

```
Backend message: phase output schema validation failed: 'raw_settings_markdown' is a required property
Backend details: { "engine_error_code": "engine.unexpected_error",
                   "engine_error_payload": { "error_code": "engine.unexpected_error",
                     "message": "phase output schema validation failed: 'raw_settings_markdown' is a required property",
                     "details": { "exception_type": "GraphAgentFatalError" }, "retryable": false },
                   "retryable": false, "run_id": "predict-2026-08-15T12-33-43_513fb04d" }
```

读者能看到的只有:出了个 fatal,有个字段名。**看不到是哪个相位**,也**看不到
是哪一道校验**。而 `io.outputs` 这份 schema 在运行期被校验**三次**——
`finish_task` 校验模型的提交、`state_mapper.py:255` 校验相位节点的原始输出、
`state_mapper.py:389` 校验 validator 的返回值——三者的修法完全相反:
第一道要改提示词/schema,第三道要改 validator。少了「是哪一道」,只能靠试。

## 2. 根因:出口只认 provider 形状的属性

抛出这个错的代码**已经把这些都填好了**(`runtime/state_mapper.py:396-411`):

```python
def _phase_mapping_fatal(detail, *, code, phase_id, field_path=None):
    raise GraphAgentFatalError(
        detail,
        payload=make_error_payload(code, detail, phase_id=phase_id, field_path=field_path),
    )
```

`GraphAgentError.__init__`(`core/exceptions.py:128-160`)把这份 payload 挂到
`self.payload` / `self.error_payload`,并把 `phase_id` / `field_path` 提成实例属性。
**没有** `error_code`,**没有** `details` ——那两个名字是 `LLMProviderError` 的形状。

而出口 `core/runner.py` `_artifact_error_result` 当时这样读:

```python
    error_code = str(getattr(exc, "error_code", "") or "engine.unexpected_error")
    details = _safe_provider_error_details(getattr(exc, "details", {}))
    details.setdefault("exception_type", type(exc).__name__)
```

两个 `getattr` 对 `GraphAgentFatalError` **全部落空**。于是:一个带着
`[F-v3-runtime-state-mapping-failed]`、相位名 `settings`、字段名
`raw_settings_markdown` 的错误,到了调用方手里只剩
`engine.unexpected_error` + `exception_type`。**信息是被产生了又被丢掉的**,
不是从来没有。

这正是 #819 的盲区:那次的判据是「没有 `error_code` 的异常按定义不是 provider 错误」
——判据本身对,但它默认了「没有 `error_code` = 没有分类」。引擎自己的 fatal 恰恰是
**有分类、但分类放在另一个字段里**的那一类。

## 3. 参考的成熟做法(借了什么、拒了什么)

- **借:本仓自己的既有约定。** `ErrorPayload` 就是本仓的结构化错误载体,
  `make_error_payload` 是它唯一的构造入口,`compile` 链路一直按 `payload.code`
  读诊断。出口改成先读 `error_payload`,是**回到本仓已有的那条通路**,不是新发明。
- **借:Python 标准库 `OSError.errno` / `subprocess.CalledProcessError.returncode`
  的取舍**——异常自带的结构化字段优先于调用方的推断,调用方只在异常什么都没说时
  才填默认值。这次的顺序与之相同:有 payload 用 payload,没有才落 `engine.unexpected_error`。
- **拒:给 `GraphAgentError` 补一个 `error_code` 属性别名去迎合出口的读法。**
  那会让同一个概念有两个名字(`payload.code` 与 `error_code`),违反仓规
  「同一业务规则只允许一个权威定义」;而且别名一旦存在,下一处出口会随机挑一个读。
  该改的是读的人,不是被读的人。
- **拒:把 `[F-v3-*]` 码转换成 `engine.*` 形状的码。** 转换表是另一份要维护的真相,
  而 `[F-v3-*]` 已经是本仓诊断的通用码制(compile 诊断、相位事件里到处是它)。
  出口原样透出即可。

## 4. 决定(一处)

`core/runner.py`:

1. 新增 `_engine_error_payload(exc)` —— 只做一件事:异常若自带非空 `code` 的
   `error_payload`,把它交出来,否则 `None`。
2. `_artifact_error_result` 先问它:
   - 有 payload → `error_code` 取 `payload["code"]`,`details` 取 `payload["details"]`
     并把 `phase_id` / `field_path` / `skill_id` / `source_path` 里非空的补进去;
   - 没有 → 保持 #819 的既有行为(`getattr(exc, "error_code", ...)`,
     兜底 `engine.unexpected_error`)。
3. `exception_type` 两条路都补,它是「异常本身是什么」,与分类无关。

`retryable` 不变:`ErrorPayload` 里没有这个概念,它仍旧只从异常属性读。

## 5. 验收判据

`packages/graph-agent/tests/core/test_fatal_error_payload_survives.py`,
用真机上那个 fatal 的原样构造(`[F-v3-runtime-state-mapping-failed]` +
`phase_id="settings"` + `field_path="raw_settings_markdown"`):

1. `test_a_fatal_keeps_the_code_it_raised_itself_with` —— `error_code` 必须是
   `[F-v3-runtime-state-mapping-failed]`。修复前实测:`engine.unexpected_error`。
2. `test_a_fatal_keeps_where_it_happened` —— `details` 里必须有 `phase_id`
   与 `field_path`。修复前实测:`KeyError: 'phase_id'`,整个 details 只有
   `exception_type` 一项。
3. `test_an_exception_with_no_payload_still_reads_unclassified` —— 一个裸
   `RuntimeError` 仍须报 `engine.unexpected_error`,证明这次改动没有把 #819
   的兜底一起换掉。

`test_unclassified_run_error_code.py`(#819 的三条)与
`test_error_payload_contract.py` 一并跑绿,共 29 条。
