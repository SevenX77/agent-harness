---
module: 01-contract/04-data-contracts
doc: mvp1-alignment
status: drafted（形状成段 + mvp1 A1 拆分）
aligns_with: ../../00-architecture-overview.md（§2 契约层 A）
---

# 04-data-contracts — 契约 A · 数据形状(我们的, 建在 langgraph 上)

> **Tier**: 契约层 A(L0 共享词汇) | **Owns**: 类型 · 异常树 · 错误码契约 · state schema · result 类 · validator 签名 | **关键**: **我们定义的形状**,建在 langgraph 原语上(原语是底座,不是我们的契约) | **现状**: A 成段;B baseline 待成段 | **Related**: `03-checkpoint`(state 存储)· `01-graph-exec`(blackboard)· `03-api-contract`(result)· Task3(错误码)

## 1. 定义
data-contracts = Graph Agent 的**共享数据词汇**:所有模块 import 它、它不 import 任何内部模块(L0 叶,去 `core` 上帝包环的基石)。**这些形状是我们设计的**(`state.py`/`result.py`/`exceptions.py`);它们**建在 langgraph 原语上**(`StateGraph` state、`AgentState.messages`、`DeltaChannel` reducer、checkpointer)——**原语是机制底座,不是我们拥有的契约**。

## 2. 我们的形状 vs langgraph 底座
| 我们的形状(契约) | 实证 | langgraph 底座(机制,引用不复制) |
|---|---|---|
| `BusinessData`/`FrameworkState`/`WorkflowState` | `state.py:79/156/203` | `WorkflowState=TypedDict` 含 `data` 通道 + `messages` 通道(后者用 `DeltaChannel`) |
| `RunResult`/`PhaseRecord`/`PathDiff` | `result.py` | — |
| 异常树 `GraphAgentError…` + `ErrorPayload` | `exceptions.py:21` | — |
| validator 契约(签名 + 码) | `core/validator_contract.py` | — |
> `WorkflowState` 是**混血**:字段形状是我们的(契约);`data`/messages 通道的 reducer 接线是 langgraph 的(机制,归 `03-checkpoint`/`08-messages-state`)。

## 3. 接口契约
result 类(`RunResult` 等)显式契约 → `03-api-contract` §2(consumer studio 读 RunResult);`ErrorPayload` 形状跨 compile+runtime 共用(Task3 核心,加 `line` 定位轴)。
> **错误契约 V2(目标,规则见 `compile-rules` §3.1)**:`ErrorPayload` 现状扁平(`exceptions.py:21`:code/level/stage/message/doc_link + 可选 skill_id/phase_id/field_path/source_path),异常 `GraphAgentError.context`(`exceptions.py:100`)转 payload 时丢弃。V2 加 `details: dict[str,Any]`(序列化异常 context + 每码结构化键)、`remediation: str | None`(注册表回填);`RunResult` 加 `diagnostics: list[ErrorPayload]`(FATAL+WARN 全集,`error` 仍为主致命)。形状归本域,规则/码注册归 `compile-rules`,API 暴露归 `03-api-contract`(三处双向)。

## 4. 设计决策基础(用户原话)
> 完整记录(2026-06-03 PM):"mvp1 不应该只是部分优化的文档,而是完整记录整个 engine 设计决策的文档,不变的地方可以复用 mvp0,但是不能不写。"

> data-contracts 归属(2026-06-03 PM):"data-contracts 是我们设计约定的, 还是 langgraph 自带的?" → 我们的形状,建在 langgraph 原语上。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| DC1 | data-contracts = L0 叶,**零内部依赖** | 去 `core` 循环依赖的基石 |
| DC2 | **我们的形状** vs langgraph 原语(底座);原语引用不复述 | 分清"我们的契约"和"依赖的机制" |
| DC3 | A1:`WorkflowState` 拆 `BusinessData`(用户业务)/`FrameworkState`(框架元数据) | 物理隔离用户字段与框架字段 |
| DC4 | `ErrorPayload` 加 `line` 轴(Task3)+ golden/iterate domain | 前端精准放标记 + mvp1 新码 |
| DC5 | **错误契约 V2 形状(细化见 `compile-rules` §3.1.1)**:`ErrorPayload` 加 `source_span`/`phase_path[]`/`stage_id`/`details`(+每码 `details_schema`)/`remediation`/`message_key`;`RunResult` 加 `diagnostics: list[ErrorPayload]` + `diagnostics_limit`/`diagnostics_truncated`/`diagnostic_counts` | 通用消费者要结构化诊断 + 有界全集;分期落地(P0-1 details+diagnostics,P1 source_span/phase_path) |

## 6. 测试关键点
1. **acyclicity guard**:本模块 import 图不含任何 engine 内部模块。
2. `BusinessData` 拒 `_` 前缀字段(`state.py:137` 已校验)。
3. `ErrorPayload.code` ∈ ERROR_REGISTRY;公开 `__all__` 稳定(`test_public_api_contract`,surface 归 `07-runtime`)。

## 7. 涉及 region / platform
engine 全权;公开 `__all__` surface + RunResult 被 studio/外部消费者依赖。

## 8. gaps / 待设计
1. 物理抽出 `core/`(模块重排,kiro)。
2. `data` 通道 delta reducer(blackboard delta,见 `03-checkpoint`)。
3. **错误契约 V2 形状**(`ErrorPayload.details/remediation`、`RunResult.diagnostics`,见 `compile-rules` §3.1)——impl 归 kiro。

## 交叉引用(链接, 不复制)
00-architecture-overview §2 · `02-mechanism/04-run-outer/03-checkpoint`(state 存储)· `05-run-inner/08-messages-state`(messages 通道)· `03-api-contract`(result)· Task3 错误码审计
