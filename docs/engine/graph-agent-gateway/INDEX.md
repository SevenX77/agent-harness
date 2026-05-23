# graph-agent-gateway (engine)

`graph-agent-gateway` 是 Engine 的模型网关子模块。它负责把逻辑 `llm_role` / tier 解析成 LangChain 兼容的 `BaseChatModel`, 并承接 provider fallback、工具绑定、Predict mock 短路和模型调用相关事件。它和 `skill-resolution` 平行: 一个解析模型能力, 一个解析 graph skill 资源。

## 文档入口

- [baseline.md](./baseline.md): V2.1 现状, 覆盖 `ModelResolver`, `GatewayChatModel`, `ResolvedRole/ResolvedProvider`, `PredictGatewayChatModel` 和当前 fallback/error/tracing 边界。
- [mvp0-alignment.md](./mvp0-alignment.md): V0.3.0 三个改造点: GW-1 ModelResolverProtocol DI, GW-2 gateway 错误结构化, GW-3 fallback 事件总线对齐。
- [logic-explained.md](./logic-explained.md): V0.3.0 完整功能模块代码翻译, 后续 G1-T6 补写。

## 跨模块边界导航

| 相关模块 | 关系 | 入口 |
|---|---|---|
| skill-resolution | 平行 DI 模块; `SkillResolverProtocol` 解析 `target_skill -> Path`, gateway 解析 `llm_role -> BaseChatModel` | [skill-resolution baseline](../skill-resolution/baseline.md) |
| execution-runtime | runtime 调用 `model_resolver.resolve(...)`, 拿到模型后执行 Agent / LLM phase | [execution-runtime mvp0-alignment](../execution-runtime/mvp0-alignment.md) |
| skill-compilation | 编译期读取 `llm_role` 字段并做静态校验; 不实例化真实模型 | [skill-compilation mvp0-alignment](../skill-compilation/mvp0-alignment.md) |
| tracing-and-observability | gateway fallback / call event 最终进入统一 trace 底座 | [tracing mvp0-alignment](../tracing-and-observability/mvp0-alignment.md) |
| skill-spec error code | `[F-v3-gateway-*]` 需要补入统一错误码表 | [Error Code Spec](../skill-spec/11-error-code-spec.md) |
