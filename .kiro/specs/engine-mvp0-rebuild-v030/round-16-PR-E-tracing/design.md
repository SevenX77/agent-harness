# PR E 组 (tracing-and-observability) 架构设计

本文档针对 PR E 组提出的 E1-E4 tracing 接线任务进行架构层面的策略收敛与设计决策。

## 1. 核心设计决策 (Architectural Decisions)

### 1.1 AMBIGUITY_LOGGED 的分离投递机制 (E1)
**决策**：**并列投递，不替换。**
- `log_ambiguity` 作为 LangChain 工具被调用，其既有 tool lifecycle trace 必须正常运转；当前 typed 形态是 `ToolCallEvent(event_type="tool_call")`。
- 在 `cognitive/ambiguity.py` 的工具逻辑内部，当判定反馈记录成功后，沿用现有 callback `on_event` 协议投递 `AmbiguityLoggedEvent`。真实缺口是 runtime ctx 当前未注入 `_callbacks`，导致 `_emit_ambiguity_logged` 在无 callbacks list 时静默返回。
- **关联键**：`AmbiguityLoggedEvent` 使用现有字段 `phase_name`，并保留 tool trace 的 `tool_name` / 时间序列语义。这样使得前端既能在 Timeline 中看到耗时块，又能在专有的 Ambiguity Feedback 面板路由到结构化的业务反馈。

### 1.2 Builtin Subagent 装配期无 `run_id` 投递策略 (E2)
**决策**：**允许 `run_id=None`，注入装配期 Tracer。**
- `graph_assembler._build_reference_reader_markdown` 执行于装配期，此时图尚未 `invoke`，因此没有 `run_id` 状态。
- 设计上，强制规定在触发 `BUILTIN_SUBAGENT_ENTER` / `EXIT` / `FALLBACK` 时，将 `run_id` 显式设为 `None`。
- 为了能够 emit 事件，`assemble_graph` 以及 `_build_reference_reader_markdown` 将需要接收可选的 `callbacks` 列表，从而打通底层 `events.py` 与序列化队列；不引入全局 Tracer 单例。
- callback 透传范围必须覆盖装配入口：`runner.py:495` 的 `_run_v21_skill_dict()` 调用以及 `loader.py:245` 当前丢弃 `callbacks` 的路径，都要把 callbacks 继续传给 `assemble_graph(...)`。

### 1.3 Fallback Payload 的严格体积控制 (E3)
**决策**：**严格映射 Pydantic Model，切断 Raw Text 传入。**
- 发生超时或错误产生 Fallback 时，直接实例化 `BuiltinSubagentFallbackEvent`。
- `fallback_reason` 映射为 Literal: `remote_timeout`, `remote_error`, `config_missing`, `invalid_output`, 或 `local_io_error`。
- `fallback_strategy` 固定或映射为类似 `raw_excerpt_3000_tokens`。
- **绝不**将组装后的 fallback raw markdown 存入 Event payload，只允许短警告 `warning`，通过 Pydantic 强校验彻底杜绝大体积载荷流入追踪系统。

### 1.4 测试用例的同步与验证 (E4)
**决策**：**利用 Pydantic 联合类型鉴别器确保序列化稳定。**
- `events.py` 已使用 `Literal` 鉴别器，因此无独立 Enum 需更新。测试重点在于针对 `log_ambiguity` 工具和装配期 Fallback 阶段增加单元测试，捕获 callback `on_event` 收到的 typed event，断言特定 `event_type` 确实存在且事件顺序严格符合：`ENTER` -> (`FALLBACK`|`EXIT`)。

## 2. 字段继承与变更表 (SOP-06 规范)

本次 PR E 不包含破坏性更新（BREAKING），也不增加全新的 Pydantic 事件定义，主要是将已悬空定义的事件落地触发（接线）。

| 字段/事件 | 类型 | 状态 | 备注 |
|---|---|---|---|
| `AmbiguityLoggedEvent` | Pydantic Event | **[继承]** | `events.py` 已有，本次仅添加触发点。 |
| `BuiltinSubagentEnterEvent` | Pydantic Event | **[继承]** | `events.py` 已有，`run_id` 使用 `None` 兜底。 |
| `BuiltinSubagentExitEvent` | Pydantic Event | **[继承]** | `events.py` 已有，`run_id` 使用 `None` 兜底。 |
| `BuiltinSubagentFallbackEvent` | Pydantic Event | **[继承]** | `events.py` 已有，强类型控制 payload 瘦身。 |
| `fallback_reason` | Literal 枚举 | **[继承]** | 采用已定义的 `remote_timeout`, `remote_error`, `config_missing`, `invalid_output`, `local_io_error`。 |

*判断：所有涉及的 Pydantic Event 均在此前代码骨架中存在，本次属于功能完善与接线，没有任何现有运行态被打破（无需 [BREAKING] 标记）。*
