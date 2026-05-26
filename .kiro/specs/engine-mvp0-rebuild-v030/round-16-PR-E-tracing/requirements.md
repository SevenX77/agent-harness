# PR E 组 (tracing-and-observability) 需求 (验收标准)

本文档将架构设计转化为可验证的验收条件（Acceptance Criteria），以便于进行测试驱动（Tests-First）与后续代码审查。

## 1. E1: AMBIGUITY_LOGGED 投递
**验收条件**：
- [ ] 当模型调用 `log_ambiguity` 工具且逻辑执行成功时，必须触发一次 `AMBIGUITY_LOGGED` 事件投递。
- [ ] 该事件必须与现有 tool lifecycle trace 并存，不可互斥替换；当前 typed 形态为 `ToolCallEvent(event_type="tool_call")`。
- [ ] 投递的 payload 必须符合 `AmbiguityLoggedEvent` 结构，即包含确切的 `ambiguity_type`、`decision`、`reason` 以及可选的关联引用 `related_refs`/`related_protocols`。
- [ ] 现有测试需确保投递逻辑正确捕获，避免 `ambiguity_logged callback failed` 的静默吞噬。

## 2. E2 & E3: BUILTIN_SUBAGENT 装配期追踪与 Fallback
**验收条件**：
- [ ] 在 `_build_reference_reader_markdown` 执行前，必须触发 `BUILTIN_SUBAGENT_ENTER` 事件，标明 `builtin_name="reference_reader"`。
- [ ] 当 reference 读取正常结束时，触发 `BUILTIN_SUBAGENT_EXIT`。
- [ ] 当发生网络错误、超时 (`TimeoutError`)、无效输出或缺少配置时，捕获异常并抛出警告，同时必须触发 `BUILTIN_SUBAGENT_FALLBACK` 事件。
- [ ] **装配期无状态断言**：在上述三个事件中，`run_id` 必须合法地允许传递为 `None`，并且携带正确的装配期 `phase_name`。
- [ ] **Payload 体积控制**：Fallback 事件载荷中仅允许带有规范的 `fallback_reason`、`fallback_strategy`、`excerpt_token_limit` 及简短 `warning`，绝不允许包含 reference 原文内容片段。

## 3. E4: 测试用例同步与事件顺序验证
**验收条件**：
- [ ] 针对 Reference Reader Fallback 提供专门的追踪覆盖单元测试，断言事件的产生顺序必须严格遵循：`BUILTIN_SUBAGENT_ENTER` -> `BUILTIN_SUBAGENT_FALLBACK`。
- [ ] 提供针对序列化的回归测试，确保新启用的这几类 trace event 在转 JSON 或分发给下游 Callback 时，不会被拒收（鉴别器解析正常）。
- [ ] 包含针对 tool 触发的测试验证，确保普通工具追踪事件能够正常提取并赋予 `tool_name` 等元数据。
