---
module: 02-mechanism/06-seam/01-models
doc: mvp1-alignment
status: drafted（机制·接缝;主体迁自 13-models;predict_context 透传 / usage 归零 / structured-output mock 约束已迁(源 uncovered #1)）
aligns_with: ../../../00-architecture-overview.md（§3 机制层 B·接缝）
---

# 01-models — 机制 B · LLM 接缝(跨层接缝)

> **Tier**: 机制层 B · 跨层接缝 | **Owns**: LLM 接缝(`GatewayChatModel`)· model_resolver · D1 双模 · **predict-mock chat model** | **现状**: 主体迁入;predict_context 透传/usage 归零/structured-output mock 约束已迁(源 uncovered #1) | **Related**: `05-run-inner/01-agent-loop`(用 model)· `05-run-inner/06-golden-eval`(predict 回放)· gateway(独立子系统,只对接)

## 1. 定义
models = engine ↔ LLM 的**唯一接缝**:引擎只见 `GatewayChatModel`(编排外壳),provider 差异(OpenAI/Anthropic/qiniu 等)全由独立 **gateway** 吸收,引擎不自己分 provider。AGENT phase 的 `create_agent(model=...)` 从这里拿模型(**目标态**;live 现状仍手写 ReAct loop `graph_assembler.py:510`,见 `01-agent-loop`)。

## 2. 数据流 / 机制
`_resolve_phase_chat_model` 经 `model_resolver.resolve(...)` 拿模型;含 D1 双模(thinking/非)。**predict-mock chat model**(`PredictGatewayChatModel`,`_generate` 调 `resolve_generation` 返回 mock、不调真 provider;`bind_tools` 保持 predict 子类)在此——这是 **predict 模式**在 model 接缝处的短路(predict 非独立域,内容来自 `06-golden-eval`)。

## 3. 接口契约
`GatewayChatModel` 编排契约(usage/thinking blocks/tool-call metadata 不丢)→ `03-api-contract`;**不碰 gateway 代码/文档**(独立子系统),本域只定 engine 侧消费契约;`model_resolver.resolve(...)` = engine↔gateway 唯一调用面(第1趴)。

## 4. 设计决策基础(用户原话)
> predict 是模式(2026-06-03 PM):"predict不是跳过 inner直接mock吗?…predict只是一个无情的机器" → predict mock 在 model 接缝短路,非独立域。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| MD1 | provider 差异归 gateway,引擎只见 `GatewayChatModel` | 核心决策:编排不被 provider 格式统一推翻 |
| MD2 | predict-mock chat model 在 model 接缝(predict 模式短路) | predict 非域;mock 机械附着在 model 接缝 |
| MD3 | D1 双模(thinking/非)收进 mvp1 接缝视野 | 弱模型/thinking 路径差异在接缝层建模 |

## 6. 测试关键点
1. D-test:`create_agent(model=GatewayChatModel)` 端到端,gateway usage/thinking/tool-call metadata 不丢(与 `01-agent-loop`)。
2. PredictGatewayChatModel `bind_tools` 后仍保持 predict interception;usage 归零(`PredictTracingCallback`,→ `02-observability`)。
3. **predict_context 透传**(源 uncovered #1):create_agent 迁移测试须覆盖 predict path,证明 `predict_context` 仍经 `_resolve_phase_chat_model`(`graph_assembler.py`,predict_context 一路串入)传到 resolver。
4. **predict usage 归零不可被改**:TracingMiddleware 迁移后不得把 predict usage 从 0 改成真实 token——`PredictTracingCallback.on_llm_call` 现强制归零(`_predict_internal/tracing.py:146-158`,`_zero_usage_values`)。

## 7. 涉及 region / platform
engine ↔ gateway 边界;gateway 独立子系统。

## 8. gaps / 待设计
1. 直连 `init_chat_model` 实现(kiro)。
2. predict mock 搬回引擎(纠 D2 stale:删 predict_context;与 `06-golden-eval` 协同)。
3. **structured-output mock payload 约束**(源 uncovered #1):若开 structured-output 实验,`PredictGatewayChatModel` 的 mock payload 必须能模拟 finish_task/tool-call 形态,否则 predict 验不了 exit gate(与 `06-golden-eval` 协同)。

## 交叉引用(链接, 不复制)
00-architecture-overview §3 · `05-run-inner/01-agent-loop` · `05-run-inner/06-golden-eval`(predict 回放)· `03-api-contract` · `02-observability`(predict trace)
