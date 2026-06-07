---
module: <示例>mechanism/retry-policy
doc: milestoneN-alignment
status: drafted（目标:指数退避 + 错误分类 + 可配次数）
binds_baseline: ./baseline-example.md
units: [retry-policy]        # 轴③ 设计单元切面(锁态以 INDEX 为准,不在本文 frontmatter)
aligns_with: ../00-three-axes.md（示例占位:实际指架构总览§x）
---

# retry-policy — milestoneN Alignment

> ⓘ **这是符合 [`01-writing-standard.md`](../01-writing-standard.md) alignment 模板的范例**(展示"设计细节颗粒度",非只方向)。
> **Tier**: 机制 | **Owns**: LLM 调用重试策略 | **现状**: ⏳ | **Related**: [baseline](./baseline-example.md)（双向）· `06-seam/01-models`

## 1. 定义
重试策略 = LLM 调用失败时,**按 error code + 指数退避**决定是否 / 何时重试。

## 2. 数据流 / 机制(设计细节,非只方向)
- **签名**:`retry_call(fn, *, max_retries=3, backoff_base=1.0, backoff_cap=60.0, retryable={429,500,502,503})`。
- **流程**:调 `fn` → 成功即返回;失败 → 取 error code →
  - **不在 `retryable`(如 4xx)→ 立即抛**(不浪费配额);
  - 在 `retryable` → `sleep(min(backoff_base * 2**attempt, backoff_cap))`(**指数退避 + cap**)→ 重试;
  - `attempt` 达 `max_retries` → 抛 `RetryExhausted(attempts, last_error)`。
- **不碰全局 state**:重试纯局部,不写黑板。

## 3. 接口契约
`retry_call(fn, *, max_retries, backoff_base, backoff_cap, retryable) -> Any`;耗尽抛 `RetryExhausted`(含 `attempts` / `last_error`),供上游观测。

## 4. 设计决策基础(用户原话)
> (示例)"4xx 别重试,纯浪费;429 / 5xx 才退避重试,而且间隔要拉开防雪崩。"

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| RP1 | 指数退避 + cap(非立即) | 防雪崩;cap 防单次等太久 |
| RP2 | 按 error code 分类,4xx 立即抛 | 4xx 重试无意义、浪费配额 |
| RP3 | `max_retries` 可配 | 不同场景容忍度不同 |

## 6. 测试关键点
1. 4xx 立即抛、零重试;429 / 5xx 退避重试。
2. 间隔指数拉长且 `cap` 封顶。
3. 耗尽抛 `RetryExhausted` 且含 `attempts`。

## 7. 涉及 region / platform
engine 全权。

## 8. gaps / 报警
- `retryable` 是否纳入 408 / 409 —— 待定。
- (实施:具体 `sleep` / 时钟注入归 kiro,不进本设计文档。)

## 交叉引用(链接, 不复制)
[baseline](./baseline-example.md)（现状,双向）· `06-seam/01-models`(调用方)
