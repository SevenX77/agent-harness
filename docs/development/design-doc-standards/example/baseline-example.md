---
module: <示例>mechanism/retry-policy
doc: baseline
status: drafted（现状对齐 pinned 代码 <commit>；固定 3 次、无退避、不分错误类型）
binds_alignment: ./alignment-example.md
binds_code: core/retry.py:retry_call
units: [retry-policy]        # 轴③ 设计单元切面(锁态以 INDEX 为准,不在本文 frontmatter)
---

# retry-policy — Baseline(当下代码实现逻辑)

> ⓘ **这是符合 [`01-writing-standard.md`](../01-writing-standard.md) baseline 模板的范例**;模块名 / `文件:符号名` 为格式示意,非真实代码。
> **Scope**: LLM 调用失败时的重试现状。
> **现状一句话**:`retry_call`(`core/retry.py:retry_call`)**固定重试 3 次、无退避、不分错误类型**——任何异常一律立即重试,3 次耗尽抛最后一次异常。

## UI/UX
N/A —— 纯后端。

## 前端逻辑
N/A。

## 后端功能
### 1. 重试循环(`core/retry.py:retry_call`)
- `retry_call(fn)`:`for _ in range(3)` 调 `fn`;任何异常 catch 后**立即**重试;3 次耗尽抛最后一次异常。
  > **退避(backoff)首次出现需定义**:重试间隔逐次拉长(如 1/2/4s)以防雪崩。**现状无退避**。
- 错误分类:**无**——`except Exception` 一把抓,4xx / 5xx 一视同仁。

## API
- `retry_call(fn: Callable) -> Any`(`core/retry.py:retry_call`)。

## Data Model / State
无状态;重试次数不落 state。

## 当前边界(这个模块现在不是什么)
- 无退避、无错误分类、次数硬编码 3、无耗尽标记。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | 目标(alignment) |
|---|---|---|
| 退避 | 无(立即重试) | 指数退避 1/2/4s、cap 60s |
| 错误分类 | `except Exception` 一把抓 | 只重试 429/5xx,4xx 立即抛 |
| 次数 | 硬编码 3 | 可配 `max_retries` |
| 耗尽 | 抛裸异常 | 抛 `RetryExhausted`(含 attempts) |
> **验"是否按目标改了"**:① 间隔指数拉长且 cap;② 4xx 不重试;③ `max_retries` 可配;④ 耗尽抛 `RetryExhausted`。

## 读代码主路径提示
`core/retry.py:retry_call` → `except` 块 → `range(3)`。

## 交叉引用(链接, 不复制)
[alignment](./alignment-example.md)（目标,双向）· `06-seam/01-models`(谁调用 retry)
