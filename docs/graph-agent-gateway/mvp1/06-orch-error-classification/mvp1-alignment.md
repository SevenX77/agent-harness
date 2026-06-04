---
module: 06-orch-error-classification
doc: mvp1-alignment
status: drafted
---

# 06 — Error Classification（错误分类）· MVP1 设计

> **Tier**：③b gateway 公共能力内核（`registry/error_classification.py` 已在包内；**纯 ③b，本轮无反转**）
> **Owns**：把 HTTP 状态码 / provider error payload / 异常链映射成"该 **retry** 同 route / 该 **fallback** 下一 route / 该 **fail request**"的结构化分类；产出 legacy `decision`（旧 fallback loop 消费）+ v1.1 `action/scope`（细粒度）；**不调模型、不持状态**
> **Status**：设计定稿（MVP1 **不改分类语义**，只纠正多处历史文档"401/403/404 → fail-fast"的过时简写）；代码 = 不动，A' 换 ChatX 后补确定性测试确认 ChatX 异常仍可被 `_status_code`/`_provider_error_payload`/`_exception_chain` 识别
> **Related**：[[07-orch-fallback-circuit-probe]]（fallback loop 消费 `decision`）· [[02-orch-role-resolution]]（过滤后空链 vs 运行期全失败的边界）· [[09-inv-invocation-runtime]]（ChatX invoke 抛的异常进本分类器）· [[13-x-tracing-events-exceptions]]（`AllProvidersFailedError`/fallback event）
> **决策日志**：`.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md` M5（真实语义表，纠正 401/403/404）+ D1（保留 `GatewayChatModel` 编排壳）
> **现状**：见同目录 `baseline.md`

## 1. 定义

MVP1 目标**不是重写错误分类**，而是在调用层 A' 迁移到原生 ChatX 时**保护当前分类语义**。最重要的纠正：**401/402/403/404 与 capability 型 400 是 fallback（不是 fail-fast）；非 capability 400/413/422 是 fail request；未知异常 fail with route context**。

判据归属：错误分类是 gateway 把"HTTP 状态码 / provider payload / 异常"映射成"该 fallback / 该 fail-fast / 该重试"的标准能力——**应用也可以只要这个错误码语义、自己决定怎么处理**（README §3.F），不依赖任何应用加工四件事（UI / 产品策略 / 调用方式 / 存储介质）→ **③b 公共**（disposition 表行 36：原 review 已判对 ③b ✓，本轮不变）。本文只写文档目标，不改代码。

## 2. 数据流 / 机制（目标；现状逐步见 `baseline.md`）

**上下游**：① 调用层（[[09-inv-invocation-runtime]]，ChatX invoke）或 probe 层（[[07-orch-fallback-circuit-probe]]，`probe_provider`）捕获异常 → `classify_exception(exc, route_id)` → 内部调 `classify_error_context(context)` → 提取 status_code / provider_error_payload / 异常链 → 按分支产出 v1.1 `action/scope` → 映射回 legacy `decision` → ② `GatewayChatModel._generate` 看 `decision`：`fallback_allowed` → mark_down + emit fallback event + 试下一 route；`fail_fast` / `fail_fast_with_route_context` → 立刻抛 `AllProvidersFailedError`。

### 2.1 目标语义表（**保留原表全部，这是源码真实语义，状态码不可改坏**）

| 输入情况 | `classify_error_context` 目标 action/scope | `classify_exception` 目标 decision | 证据 |
|---|---|---|---|
| 网络连接错误或 timeout | `retry_same_route` / `route` | `fallback_allowed` | `registry/error_classification.py:122-132`, `:83-84` |
| 429 | `retry_same_route` / `bucket` | `fallback_allowed` | `registry/error_classification.py:133-143` |
| 500/502/503/504/529 | `retry_same_route` / `endpoint` | `fallback_allowed` | `registry/error_classification.py:133-143` |
| **401/402/403** | `fallback_route` / `credential` | `fallback_allowed`（**不是 fail-fast**） | `registry/error_classification.py:144-154` |
| **404** | `fallback_route` / `route` | `fallback_allowed`（**不是 fail-fast**） | `registry/error_classification.py:144-154` |
| **400 + capability 标记**（unsupported/not supported/unknown parameter/invalid model/model not found） | `fallback_route` / `route` | `fallback_allowed` | `registry/error_classification.py:155-168`, `:272-290` |
| **非 capability 400 / 413 / 422** | `fail_request` / `request` | `fail_fast` | `registry/error_classification.py:169-178`, `:87-88` |
| 未知异常 | `fail_request` / `unknown`, `unclassified_default=True` | `fail_fast_with_route_context` | `registry/error_classification.py:179-188`, `:85-86` |
| 200 后 SSE 中断 | `fallback_route` / `stream` | 直接 action 语义；legacy 映射为 fallback | `registry/error_classification.py:111-121`, `:83-84` |

> ⚠️ **状态码语义铁律（写代码/改文档必守）**：401/402/403/404 → **fallback**（不是 fail-fast）；400+capability → **fallback**；400非capability/413/422 → **fail_fast**；429/5xx/网络错 → retry(`fallback_allowed`)；未知 → `fail_fast_with_route_context`。历史 mvp0 文档把 401/403/404/422 写成 fail-fast 是**过时简写、已被决策记录 M5 纠正**，以源码 + 决策记录为准。

### 2.2 编号执行流程（**保留原"编号执行流程"全部**）

1. 调用层或 probe 层捕获异常后，把异常交给 `classify_exception`（把异常映射为 legacy `decision` 以及 v1.1 action/scope 的函数）；它用于为当前 Gateway fallback loop 产出旧 decision（`registry/error_classification.py:75-98`，`gateway_chat_model.py:123-124`，`gateway_chat_model.py:237-238`）。
2. `classify_exception` 内部调用 `classify_error_context`（把异常和 route/endpoint/stream 上下文映射为结构化 retry/fallback/fail action 的函数）；它用于产出更细的 action/scope，方便未来区分同 route retry、跨 route fallback 和请求失败（`registry/error_classification.py:81`，`:101-105`）。
3. `classify_error_context` 先从 context 或异常链提取 status code 和 provider error payload；这一步要兼容 SDK 直接挂 `status_code` 和 httpx response 两种形态（`registry/error_classification.py:107-109`，`:223-269`）。
4. 分类器先处理 stream after 200 和网络错误，再处理 retryable status、fallback status、capability 400、fail request status，最后才走 unknown 默认失败（`registry/error_classification.py:111-188`）。**顺序固定**：stream/网络优先于状态码分支，避免把"200 后断流"误判成普通 5xx retry。
5. `classify_exception` 把 `retry_same_route` / `fallback_route` 统一映射为 `fallback_allowed`；当前 `GatewayChatModel._generate`（gateway 编排外壳的生成入口）看到这个 decision 才会 mark down、发 fallback event、继续下一 route（`registry/error_classification.py:83-84`，`gateway_chat_model.py:129-152`，`:243-255`）。
6. 如果 decision 是 `fail_fast` 或 `fail_fast_with_route_context`，当前 `GatewayChatModel._generate` 会立刻抛 `AllProvidersFailedError`（全部 provider 失败异常），不会继续试后面的 route（`gateway_chat_model.py:129-134`，`:243-248`）。

## 3. 接口契约

> 跨边界签名 / schema / 错误 / 归属，单独成段。`ErrorContext`/`ErrorActionClassification`/`ErrorClassification` schema 权威源 = `registry/error_classification.py`（本模块自有数据结构，非 registry/schema）；状态码三组常量是契约的一部分。

| 边界 | 契约 |
|---|---|
| **公共入口①（legacy）** | `classify_exception(exc: Exception, route_id: str | None = None, *, unclassified_default: bool = ...) -> ErrorClassification`（`:75-98`）。输出 `ErrorClassification`{ `decision`: `Decision`（`fallback_allowed`/`fail_fast`/`fail_fast_with_route_context` 三态枚举）, `action`, `scope`, `status`, `message` }（`:60-73`）。**当前 fallback loop 只消费 `decision`**。 |
| **公共入口②（v1.1 细粒度）** | `classify_error_context(context: ErrorContext) -> ErrorActionClassification`（`:101-188`）。输出 `ErrorActionClassification`{ `action`: `ErrorAction`（`retry_same_route`/`fallback_route`/`fail_request`）, `scope`: `ErrorScope`（request/route/endpoint/credential/bucket/stream/unknown）, `status`, `fallback_eligible`, `retryable`, `unclassified_default` }（`:38-58`）。 |
| **输入上下文** | `ErrorContext`{ `route_id`, `endpoint_id`, `credential_ref`, `method_id`, `request_mapper_id`, `runtime_settings`, `provider_error`, `stream_phase` }（`:20-36`）。`stream_phase=="after_200_sse"` 是判"200 后断流 → fallback/stream"的唯一信号。 |
| **状态码三组常量（契约）** | `RETRYABLE_STATUS_CODES={429,500,502,503,504,529}`、`FALLBACK_STATUS_CODES={401,402,403,404}`、`FAIL_REQUEST_STATUS_CODES={400,413,422}`（`:15-17`）。**400 双向**：默认在 fail_request 组，但命中 capability marker 时改判 fallback（`:155-168`）。 |
| **异常识别 helper（A' 兼容关键）** | `_status_code(exc)`（从异常 `status_code` 或 `response.status_code` 提取，`:223-232`）；`_provider_error_payload(exc)`（读 provider JSON error payload，`:254-269`）；`_looks_like_route_capability_error(...)`（识别 400 capability 类，匹配 unsupported/not supported/unknown parameter/invalid model/model not found，`:272-290`）；`_exception_chain(exc)` / `_has_network_failure(exc)`（沿 `__cause__`/`__context__` 检查包装异常，`:293-301`、`:235-239`）。**A' 换 ChatX 后这些 helper 必须仍能识别 ChatX/SDK 抛出的异常形态**。 |
| **错误（本模块产出的语义）** | 不抛异常，**产出分类结论**；`fail_fast_with_route_context` 要求带 route context 暴露未知错误，而不是静默 fallback（`:85-86`）。下游 `GatewayChatModel` 据 `decision` 决定是否抛 `AllProvidersFailedError`（归 [[13-x-tracing-events-exceptions]]）。 |
| **归属 / 稳定性** | 纯 ③b 公共（disposition 表行 36，本轮不变）；MVP1 **不改语义**，A' 只需保证 ChatX 异常仍走上表。 |

## 4. 设计决策基础（用户原话）

> 跨边界判据 verbatim，从决策记录 + ux-spec 抄，不改一字。

> **判据（通用，每模块引）· README §2 行 44 / ux-spec §6.0 行 334（verbatim）**：
> "判定一个逻辑归谁，只问一句：**换一个完全不同的应用装上 gateway，这个能力还原样能用吗？** 能 → 公共（gateway）；不能（因为它绑死了上面四件事之一）→ 应用。"
> → 错误分类（status 码 → fallback/fail-fast/retry 语义）换任何调模型 app 都原样要 → **③b 公共**。

> **保留编排壳 = 保留分类语义 · 决策记录 D1 用户原话（verbatim）**：
> "不用留A, 这是错误判断, 正确的是A'"（`client-layer-decision-record.md:41`）
> → 否决"resolver 裸返回 ChatX + 删 `GatewayChatModel` + 用 `with_fallbacks()`"；`with_fallbacks()` 只按异常类型，**表达不了"按 HTTP status + provider payload 组合分类"**，所以必须保留 `GatewayChatModel` 编排壳 + 本分类器。

> **真实语义纠正 · 决策记录 M5（verbatim 表，纠正多处文档错误简写）**：
> "**401 / 402 / 403 / 404** | **fallback**（credential/route scope） | `fallback_allowed`（**不是 fail-fast!**）"
> "**文档错误（待更正）**：`temp` option-a task 第 44 行、本 spec **`design.md:142`** 都把它写成「`400/401/403/404/422 → fail-fast`」，错（401/403/404 实为 fallback）。"（`client-layer-decision-record.md:164,169`）

> **A' 验证清单（头号风险）· 决策记录 §5 / §M6 验证项（verbatim）**：
> "**异常分类（头号风险）**：fake 401 / 400 / 网络错 喂 `classify_exception` → 分别 fallback / fail-fast / fallback；且 ChatX 瞬时重试耗尽后的异常仍可分类。"（`client-layer-decision-record.md:268`）

## 5. 决策 + 动机

> 保留原"决策原因"全部条目。

1. **保留 `GatewayChatModel` 编排壳，才能保留本分类语义**：`with_fallbacks()` 只按异常类型，表达不了 HTTP status 和 provider payload 组合出来的分类语义（`.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md:30-38`）。
2. **401/402/403/404 fallback** 能保住 route/credential scope 的恢复机会；当前源码已把 404 视为 route scope，把 401/402/403 视为 credential scope（`registry/error_classification.py:144-154`）。
3. **非 capability 400/413/422 fail request** 可以防止错误请求形状被 fallback 掩盖；这与"未知不当作模型选择信号"的原则一致（`registry/error_classification.py:169-188`，`docs/graph-agent-gateway/mvp0/mvp0-alignment.md:172`）。
4. **capability 400 fallback** 是为 provider/route 能力差异留出口，例如 unsupported parameter 或 invalid model 说明当前 route/mapper 不合适，但不代表整个用户请求非法（`registry/error_classification.py:155-168`，`:272-290`）。
5. **未知异常 fail with route context**：不能把未分类错误当作模型选择信号；这与 mvp0"无法分类时带 route context 暴露错误"的要求一致（`registry/error_classification.py:179-188`，`docs/graph-agent-gateway/mvp0/mvp0-alignment.md:172`）。
6. **ChatX 瞬时重试可保留，但重试耗尽后的异常仍必须进入本分类器**：这样同 route 防抖动 retry（[[09-inv-invocation-runtime]] F2）与跨 route fallback 不会混在一起（`.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md:187-193`）。

## 6. 测试关键点

> 每决策"测试验证什么"。状态码语义是回归头号风险，逐条必测。

- **401/402/403 → fallback（不 fail-fast）**：fake 401 喂 `classify_exception` → `decision == fallback_allowed`、`scope == credential`（**这是头号回归点，绝不能退回 fail-fast**）。
- **404 → fallback**：fake 404 → `fallback_allowed`、`scope == route`。
- **400 capability → fallback**：400 + "unsupported parameter"/"invalid model"/"model not found" 等 marker → `fallback_allowed`、`scope == route`（`:272-290`）。
- **400 非 capability → fail_fast**：400 无 capability marker → `fail_fast`、`scope == request`（与 capability 400 区分开）。
- **413 / 422 → fail_fast**：payload 过大 / schema 校验 → `fail_fast`（不 fallback 掩盖调用方错误）。
- **429 / 5xx / 网络错 → retry(`fallback_allowed`)**：429→`bucket`、500/502/503/504/529→`endpoint`、ConnectError/Timeout→`route`+`retryable=True`。
- **未知异常 → `fail_fast_with_route_context`**：无 status、无可识别 payload → `unclassified_default=True` → 映射 `fail_fast_with_route_context`（带 route context 暴露，不静默 fallback）。
- **200 后 SSE 断流 → fallback/stream**：`stream_phase=="after_200_sse"` → `fallback_route`/`stream`（优先于普通状态码分支）。
- **A' 异常识别兼容（换 ChatX 后必补）**：ChatX/SDK 抛的 401、400-unsupported、400-non-capability、413、422、wrapped network error 都仍被 `_status_code`/`_provider_error_payload`/`_exception_chain` 正确识别 → 仍走上表（决策记录 §5 头号风险、`:250`/`:268`）。
- **瞬时重试耗尽后仍可分类**：ChatX 有界瞬时重试（F2）耗尽后抛出的异常进 `classify_exception` 仍产出正确 decision（同 route retry 与跨 route fallback 不混）。

## 7. 涉及 region / platform

- **③b** `packages/graph-agent-gateway`：`registry/error_classification.py`（分类器 + 状态码常量 + helper）——纯 ③b，已在包内，本轮不动。
- **③b 消费方** `packages/graph-agent-gateway`：`gateway_chat_model.py`（`_generate` probe/dispatch 异常分类调用点）、`client_manager.py`（`probe_provider` route probe 复用分类器）。
- **③a / 调用层（A' 后）**：调用适配层（[[10-inv-route-chat-model-factory]] / [[11-inv-provider-profiles]]）需保证 ChatX/SDK 异常对象暴露可分类上下文（status_code / response payload），但**不改本模块语义**。
- **② Rust**：N/A。

## 8. gaps / 待设计

> 保留原"待办/疑点"全部条目。

- **待办（原 #1）**：A' 引入 ChatX 后，需新增或保留 fake exception 测试，确认 ChatX 的 401、400 unsupported、400 non-capability、413、422、wrapped network error 都仍走 §2.1 表格（`.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md:250`）。
- **疑点（原 #2）**：若 ChatX/provider SDK 的错误对象不暴露 `response.json()` 或 `status_code`，需在调用适配层保留可分类上下文，但**不应改变 06 的目标语义**（`registry/error_classification.py:223-269`）。
- **疑点（原 baseline #2）**：当前 capability 400 识别依赖字符串 marker（unsupported/not supported/unknown parameter/invalid model/model not found）；若 provider 返回本地化或新字段，可能需扩展 marker，但 MVP1 不应改现有分类语义（`registry/error_classification.py:272-290`）。

## 已实现 / 与 baseline 差异

> 保留原"已实现/差异"全部条目。

1. **已实现**：baseline 源码已经按最新决策分类 401/402/403/404 为 fallback status，不是 fail-fast（`registry/error_classification.py:16`，`:144-154`）。
2. **已实现**：capability 400 通过 provider error type/message marker 识别后 fallback；非 capability 400 与 413/422 仍 fail request（`registry/error_classification.py:155-178`，`:272-290`）。
3. **已实现**：未知异常设置 `unclassified_default=True`，经 `classify_exception` 映射为 `fail_fast_with_route_context`（`registry/error_classification.py:179-188`，`:85-98`）。
4. **已实现**：测试已覆盖 401/402 fallback、413 fail_fast、未知 fail_fast_with_route_context、provider status_code 404 fallback、wrapped network fallback、stream after 200 fallback、400 unsupported fallback（`packages/graph-agent-gateway/tests/test_registry_error_classification.py:8-105`）。
5. **与 baseline 差异**：MVP1 不改分类模块，只要求调用层 A' 迁移后继续把 ChatX 抛出的异常送进同一个分类器（`.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md:136-153`）。
6. **与历史 mvp0 文档差异**：`docs/graph-agent-gateway/mvp0/mvp0-alignment.md:146-148` 的旧句子把 401/403/404 写成 fail fast，与当前源码和最新决策记录冲突；本模块以源码和决策记录为准。

## 覆盖率

覆盖率：1/1 个指定文件 100% 映射；公共入口 2/2 已解释；公开模型 `ErrorContext`、`ErrorActionClassification`、`ErrorClassification` 3/3 已解释；关键 runtime 调用点 4 处已索引。本文没有提出生产代码修改。

## 代码索引（clues）

> 保留原代码索引全部条目。

- `.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md:136-153` — 最新权威错误分类语义，明确纠正 401/403/404。
- `.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md:158-171` — M5 真实语义表（401/402/403/404 = fallback）+ 文档错误纠正点。
- `.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md:250` — A' 验证清单要求 fake 401/400/网络错覆盖 fallback/fail-fast/fallback。
- `docs/graph-agent-gateway/mvp1/README.md:31` — 本模块 brief，要求 mvp1 不改分类，只纠正语义。
- `docs/graph-agent-gateway/mvp1/module-disposition-revised.md:36` — 06 错误分类 = 纯 ③b 公共（原 review 已判对，本轮不变）。
- `docs/graph-agent-gateway/mvp0/mvp0-alignment.md:146-148` — 历史过时说法，需在阅读时标记为已被纠正。
- `registry/error_classification.py:15-17` — status code 分组（401/402/403/404 属 fallback status）。
- `registry/error_classification.py:75-98` — `classify_exception`（legacy decision 映射的函数）。
- `registry/error_classification.py:101-188` — `classify_error_context`（action/scope 分类的函数）。
- `registry/error_classification.py:223-301` — status/payload/capability marker/exception chain helpers。
- `gateway_chat_model.py:123-152` — probe 异常分类和 fallback event 使用点。
- `gateway_chat_model.py:237-255` — dispatch 异常分类和 fallback event 使用点。
- `client_manager.py:407` / `client_manager.py:433` — route probe 复用分类器判断是否继续。
- `packages/graph-agent-gateway/tests/test_registry_error_classification.py:25-54` — 测试保护 401/402 fallback、413 fail_fast、unknown route context。
- `packages/graph-agent-gateway/tests/test_registry_error_classification.py:82-105` — 测试保护 stream fallback 和 capability 400 fallback。

## 交叉引用（链接，不复制）

- [[07-orch-fallback-circuit-probe]]：fallback loop 消费 `decision`；probe 复用分类器
- [[02-orch-role-resolution]]：过滤后空链（配置错误）vs 运行期全失败（`AllProvidersFailedError`）的边界
- [[09-inv-invocation-runtime]]：ChatX invoke 抛的异常进本分类器；F2 瞬时重试耗尽后仍须可分类
- [[13-x-tracing-events-exceptions]]：`AllProvidersFailedError` / fallback event payload（含 from/to route 诊断）
- 决策日志：`client-layer-decision-record.md` M5（真实语义）+ D1（保留编排壳）· `module-disposition-revised.md:36`
