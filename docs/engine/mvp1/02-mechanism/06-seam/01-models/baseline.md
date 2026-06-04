---
module: 02-mechanism/06-seam/01-models
doc: baseline
status: drafted（现状对齐 pinned 代码 7cd4b9c；GatewayChatModel 接缝 + PredictGatewayChatModel mock 短路）
---

# 01-models — Baseline(当下代码实现逻辑)

> **Scope**: engine ↔ LLM 的接缝现状:`_resolve_phase_chat_model`(模型解析)、`model_resolver`、`PredictGatewayChatModel`(predict-mock 短路)。
> **现状一句话**:引擎只见 `GatewayChatModel`(编排外壳),provider 差异(OpenAI/Anthropic/qiniu 等)全由独立 **gateway** 吸收——`_resolve_phase_chat_model`(`graph_assembler.py:581`)经 `model_resolver.resolve(...)` 拿模型。**predict 模式**在 model 接缝短路:`PredictGatewayChatModel`(`_predict_internal/interception.py:29`)的 `_generate`(`:61`)返回 mock、不调真 provider。

## UI/UX
N/A。

## 前端逻辑
N/A —— gateway 是独立子系统;引擎只对接其调用面,不渲染。

## 后端功能

### 1. 模型解析(graph_assembler.py)
`_resolve_phase_chat_model(phase_id, phase_ast, *, chat_model, model_resolver, ...)`(`:581`)经 `model_resolver.resolve(...)` 拿该 phase 的模型。引擎拿到的是 `GatewayChatModel`——**不自己分 provider**(核心决策:编排不被 provider 格式统一推翻)。
> **GatewayChatModel 第一次出现需定义**:引擎侧统一的 LLM 编排外壳;OpenAI/Anthropic 等 provider 差异全在独立 gateway 子系统里吸收,引擎只调一个接口。

### 2. predict-mock 短路(interception.py)
`PredictGatewayChatModel(GatewayChatModel)`(`interception.py:29`):`_generate`(`:61`)调 `resolve_generation` 返回 mock、**不调真 provider**;`bind_tools`(`:107`)保持 predict 子类(绑工具后仍拦截)。这是 **predict 执行模式**在 model 接缝处的短路(predict 非独立域,mock 机械附着在 model 接缝;内容来自 `06-golden-eval`)。

## API
- `_resolve_phase_chat_model(...)`(`graph_assembler.py:581`)→ `model_resolver.resolve(...)`——engine↔gateway 唯一调用面。
- `PredictGatewayChatModel._generate`/`bind_tools`(`interception.py:61/107`)——predict mock。

## Data Model / State
模型对象 = `GatewayChatModel`(usage/thinking blocks/tool-call metadata 经它流转);predict mock 的 usage 归零(`PredictTracingCallback`,→ `02-observability`)。

## 当前边界(这个模块现在不是什么)
- **不碰 gateway 代码/文档**:gateway 是独立子系统,本域只定 engine 侧消费契约。
- **不自己分 provider**:引擎只见 `GatewayChatModel`,provider 分支全在 gateway。
- **predict 非独立域**:它是 run/predict 两执行模式之一,mock 在 model 接缝短路(入口归 `07-runtime`、内容归 `06-golden-eval`)。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标 |
|---|---|---|
| 模型解析 | `model_resolver.resolve`(`:581`) | 直连 `init_chat_model` 实现补全 |
| predict mock | `PredictGatewayChatModel`(`interception.py:29`) | 搬回引擎、纠 D2 stale(删 predict_context) |
| D1 双模 | thinking/非 | 接缝层建模 |

> **验"是否按 mvp1 改了"**:① `create_agent(model=GatewayChatModel)` 端到端,gateway usage/thinking/tool-call metadata 不丢;② `PredictGatewayChatModel` bind_tools 后仍保持 predict interception、usage 归零。

## 读代码主路径提示
`_resolve_phase_chat_model`(`graph_assembler.py:581`)→ `model_resolver.resolve` → predict 短路 `_predict_internal/interception.py:29/61/107`。

## 交叉引用(链接, 不复制)
mvp1-alignment(目标)· `05-run-inner/01-agent-loop`(用 model)· `05-run-inner/06-golden-eval`(predict 回放)· `03-api-contract` · `02-observability`(predict trace)
