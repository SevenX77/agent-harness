# 决议 2026-08-19:红掉的必需门禁,必须说得出它抓到了什么

状态:已实施(本 PR)
影响模块:Studio backend 测试(`apps/studio/backend/tests`)
发现方式:PR #856 的对抗复核席在 `cross-platform-smoke (windows-latest)` 上撞到,
并作为遗留上报

---

## 一、决策

`test_runtime_state_store_multiprocess_first_acquire_allows_only_one_owner` 及其
孪生用例 `..._expired_takeover_...` 在失败时**只报得出一个 `None`**。本 PR 让它们
在失败时点名它们实际抓到的异常。

**本 PR 不修那条 flaky 的根因,也不假装修了。** 它修的是另一件独立成立的事:
一道坐在必需门禁上、红了却说不出为什么红的检查,与没有检查等价(同一条理由已在
台账 W2-23 立过账)。

---

## 二、论据

### 2.1 现场(operator 从 CI 日志原样取出)

`cross-platform-smoke (windows-latest)`,run 32227500016,分支
`test/parse-gap-tests-pin-delivery`:

```
apps\studio\backend\tests\core\adapters\test_productization_local_providers.py:886:
    assert {error_code for _, error_code, _ in errors} == {"state.lease_conflict"}
E   AssertionError: assert {None, 'state.lease_conflict'} == {'state.lease_conflict'}
1 failed, 1733 passed, 4 skipped in 321.29s
```

同一分支的另一次 CI(run 32229357832)成功。被咬的 PR 一行 `apps/studio/backend`
都没碰。

### 2.2 它到底说了什么 —— 与用例名给人的印象相反

886 行**之前**的断言全部通过:

```python
assert acquired == [(lease_data["owner_id"], 1)]   # 恰好一个拿到
assert len(errors) == worker_count - 1             # 恰好七个失败
```

所以**互斥没有被打破**。红的是第八个断言:七个失败者里有一个的 `error_code` 是
`None`,而不是 `state.lease_conflict`。

`_error_code`(同文件 `:1587-1588`)取的是 `getattr(exc, "error_code", None) or
getattr(exc, "code", None)`,而 `acquire_lease`
(`app/core/adapters/runtime_state_store_local.py:90-124`)里每一处 `StudioAdapterError`
都带码 —— `:114` 的 `state.lease_conflict`、`:102` 的 `_lease_fenced_error`。
**所以 `None` 意味着抛出来的根本不是 `StudioAdapterError`,是一个裸异常。**

那条路径上的 Windows 专属代码有两处:`_run_file_lock:415-422` 的
`open(lock_file, "a+b")`,以及 `_platform_lock_file:35-49`。后者的
`except PermissionError` 是**刻意收窄**的,注释原话:

> Someone else holds it. Any other OSError is about this handle rather than about
> contention, and must not be retried into a silent hang.

即:除 `PermissionError` 外的 OSError 会原样穿出这一层。**这是一条线索,不是结论** ——
没有证据指认具体是哪一句,本决议不宣称。

### 2.3 为什么下一次红了还是查不出来

用例确实记了异常类型 —— `results.put(("error", owner_id, _error_code(exc),
type(exc).__name__))` —— 但检查它的那条断言在 `:887`,**排在失败的 `:886` 之后,
永远跑不到**。于是每次咬中,现场留下的全部信息就是一个 `None`。

---

## 三、修法

三个 worker 多带一项 `repr(exc)`,两处消费端不再把它丢掉,两处断言原样保留严格度、
只加上 `, errors` 让消息带出全部四元组。

**验证过它确实有效,不是只写在注释里**:临时让 `worker-7` 抛
`PermissionError(13, "synthetic windows lock failure")`,失败消息变为

```
E   AssertionError: [('worker-7', None, 'PermissionError',
    "PermissionError(13, 'synthetic windows lock failure')"), ('worker-0',
    'state.lease_conflict', 'StudioAdapterError', "StudioAdapterError(...)"), ...]
```

注入随即撤除,`git diff` 为证;撤除后该文件 `70 passed`。

**拒绝**把断言改成"允许 `None`":那把一个说不清的失败改称预期。
**拒绝**给它加 `windows` skipif 或 `flaky` 标记:`cross-platform-smoke
(windows-latest)` 是必需门禁,而它是唯一在 Windows 上跑测试的作业(AGENTS.md 记着
它 2026-08-12 才被提为必需,理由正是"一道不能拦的门禁不是门禁")。
**拒绝**顺手去改 `_platform_lock_file` 的异常收窄:那句注释是有意为之且理由成立,
在没有证据指认它之前改它是猜。

借 `pytest` 自己的取舍:断言消息是**给下一个读到红的人**的,不是给写测试的人的;
以及 Erlang/OTP 的 crash report 传统 —— 崩溃时把导致崩溃的那个值原样带出来,
而不是只带一个分类。

---

## 四、验收判据与实测

| # | 判据 | 结果 |
|---|---|---|
| a | 失败消息里出现导致失败的那个异常的 repr | 已用合成故障实测(§三) |
| b | 断言严格度不变(仍要求全部为 `state.lease_conflict` / `StudioAdapterError`) | 两条断言表达式未改,只加消息 |
| c | 该文件整体通过 | `70 passed` |
| d | 工作区不残留合成故障 | `git diff` 只剩本 PR 的改动 |

---

## 五、已知遗留(明写,不装作解决)

1. **根因未查。** 本 PR 不知道那个裸异常是什么,只保证下一次它会自报家门。
   在拿到一次带 repr 的红之前,任何"修复"都是猜。
2. **本机复现未做。** 该 flaky 只在 Windows CI 上见过两次(6 次里 2 次,由
   #856 复核席统计),本机 `70 passed` 不构成证伪 —— 它本来就是低频的。
3. **孪生用例 `..._expired_takeover_...` 一并改了,但它没有被观测到咬中过。**
   改它的理由是同一处信息丢失,不是它也在红。
