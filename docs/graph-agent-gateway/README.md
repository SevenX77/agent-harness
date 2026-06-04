# Graph Agent Gateway — 文档(独立模块)

> 文档里程碑 **MVP1**(取代 MVP0)。代码包 `graph-agent-gateway` v1.0.0 + studio 后端 LLM 服务层。
> 本目录 2026-06-02 从旧 engine 文档目录移出,作为独立模块。

## 心智模型:编排 → [route] → 调用

```
编排(准备期·动脑·原 studio 合并)   ── route ──►   调用(实际执行·动手·原 gateway)
role → 解析出该用哪条 route                          • graph-agent: RouteChatModelFactory + 原生 ChatX
(不调模型)                          交接接口          • copilot: 交回 studio 自己的 claude_agent_sdk
```

- **编排**只回答「该用哪条 route」(含 fallback 顺序、熔断/probe 决策),不调模型。
- **route**(`ResolvedRoute`/`ResolvedRole`)= 编排↔调用唯一接口。
- **调用**拿 route 真正执行;两个消费方共用同一 route 契约。
- 架构决策(client 层 A' 重设计 D1/D2/D3/F1/F2/M4/M5)+ 证据已**分散留底进各模块** `mvp1-alignment.md` §4(用户原话)/§5(决策+动机),不再引用外部临时文件;归属判据见 [`mvp1/module-disposition-revised.md`](./mvp1/module-disposition-revised.md)。

## 目录结构

```
docs/graph-agent-gateway/
  README.md                     # 本文
  mvp0/                         # 旧里程碑归档(baseline / mvp0-alignment / logic-explained / matrix / INDEX)
  mvp1/
    README.md                   # 模块 manifest + 写作 brief + 覆盖率(42 文件 100%)
    01-handoff-interface/       # 每个模块文件夹 = baseline.md(现状)+ mvp1-alignment.md(目标)
    02-orch-role-resolution/
    03-orch-credentials-endpoints/
    04-orch-registry-schema/
    05-orch-capabilities-and-models/
    06-orch-error-classification/
    07-orch-fallback-circuit-probe/
    08-orch-test-status-ssot/
    09-inv-invocation-runtime/
    10-inv-route-chat-model-factory/   # MVP1 新建
    11-inv-provider-profiles/          # MVP1 新建
    13-x-tracing-events-exceptions/
    predict-migration-to-engine.md     # predict 移交 engine(单独)
```

- 命名前缀:`orch-`=编排,`inv-`=调用,`x-`=横切。
- **2026-06-03 边界收紧**：原模块 `12-inv-copilot-invocation`（copilot SDK 调用）和 `14-api-router`（HTTP 适配壳）按判据属 **③a Studio 应用加工**（copilot 的实际调用方式 / HTTP 端点形状·存储介质），不是 ③b gateway 公共内核，已移出本文件夹归 studio：copilot SDK 调用 → `docs/studio/mvp1/02_capabilities/copilot-assist/` + `01_workflows/00_settings-ux-spec.md` §3.8；HTTP 适配壳 → `docs/studio/mvp1/04_platform/llm-copilot-http-api/`。gateway 对 copilot 的唯一职责 = 把 `copilot_chat` 当普通 role 解析成 route（[[01-handoff-interface]] 的 route 级 API），**库不感知 copilot**。
- 每个模块文件夹内:`baseline.md`(现状证据 + 覆盖代码 + 覆盖率)、`mvp1-alignment.md`(目标设计 + 流程 + 已实现/差异 + 决策原因 + 代码索引 + 覆盖率)。

## 移动断链(已修)

本目录 2026-06-02 从 `engine/` 移出后,已把指定文件里的旧 Gateway 文档路径改为新的 `docs/graph-agent-gateway/mvp0/...` 归档入口。`docs/INDEX.md` 当前未发现旧路径引用。

## 阅读顺序
本 README(心智模型)→ `mvp1/README.md`(模块 manifest)→ `01-handoff-interface`(接口)→ 编排各篇 → 调用各篇。
