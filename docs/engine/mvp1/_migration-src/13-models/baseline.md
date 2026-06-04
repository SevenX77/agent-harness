---
module: 13-models
doc: baseline
status: drafted
last_verified: 2026-06-03
---

# 13-models — Baseline(现状)

Graph Agent 侧的 **LLM 接缝(很薄)**:真正的 resolver / `GatewayChatModel` 在 **gateway 包**(独立子系统,第1趴 `temp/2026-06-02-engine-gateway-interface-needs.md` 已设计);engine 侧只有"拿模型的接缝 + 兼容补丁"。

## 覆盖代码(file:line 已核)

| 件 | 现状 | 证据 |
|---|---|---|
| 唯一调用面 | `ModelResolverProtocol.resolve(role) -> BaseChatModel`(在 gateway 包) | `packages/graph-agent-gateway/src/graph_agent_gateway/protocol.py` |
| engine 接缝 | `_resolve_phase_chat_model`:`model_resolver.resolve(...)` 拿模型;`chat_model` 注入则短路 | `core/graph_assembler.py:581-603`(注入短路 :590-591) |
| reasoning 补丁 | `models/reasoning_patch.py`:OpenAI SDK + langchain 的 reasoning-content 4 个 patch | `models/reasoning_patch.py:25,45,69,96` |
| `GatewayChatModel` | 在 gateway 包(**非 engine**) | 第1趴 |
| 直连模式 `init_chat_model` | 全 src grep **无** → 未建 | — |

## Baseline / Alignment 差异
- 只有 role 模式(吃 GatewayChatModel)live;**D1 的直连/兼容模式未建**(`init_chat_model` 现造 ChatX);
- D1 双模目前只在 temp 第1趴,**未正式收进 mvp1**(本域补)。
