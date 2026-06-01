# execution-runtime (engine) — MVP0 Alignment (V0.3.0 graph_skill)

> **Status**: PR C 契约 + 已实现部分, synced 2026-05-26；部分目标态与当前源码差异见文末“与当前源码的差异”。
> **Scope**: Graph runtime 装配、ModelResolver / SkillResolver DI、Agent cognitive template 渲染、builtin reference reader / tools、LOGIC ActionRegistry、SUBGRAPH / subagent 隔离调用、运行期错误归一化。
> **配套**: 见 [skill-spec README](../skill-spec/README.md), [skill-compilation alignment](../skill-compilation/mvp0-alignment.md), [state-and-io-contract alignment](../state-and-io-contract/mvp0-alignment.md)。

## V0.3.0 改造摘要

本文件从 V2.1 runtime 对齐计划改写为 V0.3.0 graph_skill runtime / assembly 计划。以下旧段落被推翻:

| 旧语义 | V0.3.0 新语义 | 决议来源 |
|---|---|---|
| `ExitContractRegistry` 每轮 inject / strip | `exit_contract` 在 cognitive template 末尾 inline, 内嵌 `output_schema` | [Cognitive Template](../skill-spec/06-cognitive-template-spec.md#7-大插槽布局拓扑) |
| 轻量单节点 subagent | subagent / subgraph 统一通过 `SkillResolverProtocol.resolve_skill()` 寻址完整 graph skill | [Skill Resolver DI](../skill-spec/10-skill-resolver-protocol-spec.md#依赖注入-di-边界) |
| `call_subgraph(child_graph_path)` | `target_skill` registry id + resolver DI + IO 1:1 校验 | [SUBGRAPH target_skill](../skill-spec/04-subgraph-md-spec.md#target_skill-寻址规则) |
| document example / reference 混入普通 prompt 文本 | reference reader 装配期预读, examples inline/document 双模式 | [Resource Mechanisms](../skill-spec/08-resource-mechanisms-spec.md#reference-三机制生命周期) |
| LOGIC action 多路径加载 | Skill Global `<skill_root>/actions/<name>.py` 一级寻址 | [LOGIC Actions](../skill-spec/03-logic-md-spec.md#actions-1-级寻址与执行契约) |
| `[F-v21-*]` runtime 错误 | `[F-v3-*]` 错误码 + trace payload | [Error Code Spec](../skill-spec/11-error-code-spec.md#错误码速查全表) |

Runtime 不重新解析 Markdown 字段。Markdown / YAML / XML 的强校验属于 skill-compilation; execution-runtime 消费已编译的 AST、resolver、tool registry 和 cognitive prompt 装配结果。

## UI/UX

N/A — 此模块为纯 backend Python library, 无 UI / 无前端调用面。

Studio Run 按钮、Trace 面板和 History 只消费 runtime 返回值与 trace event。Runtime 的职责是执行已编译 graph, 在可预期失败时返回结构化 `[F-v3-*]` 错误, 并保证子图 / 子 Agent / tool 调用不越过状态隔离边界。

## 前端逻辑

N/A — 此模块为纯 backend Python library, 无 React 逻辑。

前端相关要求通过结构化事件体现: subgraph 未注册对应 `[F-v3-skill-not-registered]`, reference reader 降级对应 WARN trace, ambiguity feedback 通过 `log_ambiguity` 事件进入 TracePanel。前端如何渲染不在本文件范围。

## 后端功能

### 1. ModelResolverProtocol 真实 LLM 注入 (P0-1 保留)

MVP0 MUST 继续补齐真实 LLM 注入路径。Agent phase 的 `llm_role` 由编译期校验存在, runtime 负责把 role 解析成 LangChain `BaseChatModel`。

| 字段 / 参数 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `llm_role` | string | Agent phase 必填或继承 graph | graph `llm_role`, 再无为 `analyst` | 必须存在于 roles registry | `[F-v3-agent-llm-role-unknown]` | 选择模型路由 |
| `model_resolver` | ModelResolverProtocol | 运行 Agent 时必填 | 无 | 当前接口为 `resolve(role_name=None, *, thinking_enabled=None, model_override=None, callbacks=(), phase_name=None, **kwargs) -> BaseChatModel` | `[F-v3-runtime-phase-failed]` | 从配置生成真实模型 |
| `mock_llm` | BaseChatModel | 否 | `None` | 仅测试入口; 优先级高于 resolver | — | 单测 / sandbox 注入 |
| resolved model | BaseChatModel | 是 | 无 | 必须可被 LangGraph / LangChain 调用 | `[F-v3-runtime-phase-failed]` | Agent ReAct 执行 |

ModelResolver 与 SkillResolver 都是 DI 边界: Engine 定义协议, Studio / CLI / 测试环境提供实现。模型解析失败不应再抛裸 `RuntimeError`, 应包装为 GraphAgent runtime error 并写入 trace。

### 1.1 PR-5 shipped: LLMClientManager 并发安全与生命周期补强

这是运行期资源管理补强，不改变 Agent phase 的业务 API。

字段 / 机制级状态：

| 机制 | 当前行为 | 业务作用 |
|---|---|---|
| `_clients: ClassVar[dict]` | 进程级缓存 OpenAI / Anthropic SDK client | 复用底层 httpx 连接池 |
| `_lock: ClassVar[threading.Lock]` | 包住 `_clients.get`、client 构造、`_clients[key] = client` 的完整 check-then-act | 防止高并发首次请求重复构造 client |
| OpenAI cache key | `openai:{provider_code}`，有 probe timeout 时追加 `:timeout:{value}` | 默认调用和 probe 调用可隔离 timeout |
| Anthropic cache key | `anthropic:{provider_code}` | 同 provider 复用同一 SDK client |
| `close_all()` | 加锁遍历缓存，逐个调用 SDK client `.close()`，per-client 异常 warning 后继续，最后清空 `_clients` | 长驻 CLI / Studio / server reload 释放 TCP 连接，避免连接池积累 |

锁的边界必须覆盖“查缓存、构造、写缓存”的整段。只锁写入会让两个线程都看到 miss 并各自创建 client，最终虽然 dict 里只剩一个值，但已经浪费连接池并可能让调用方拿到不同对象。

`close_all()` 是生命周期钩子，不是每次 LLM call 后的清理动作。宿主在退出、配置重载或 watcher reset 时调用它，释放 SDK client 持有的 httpx 资源。

### 1.5 SkillResolverProtocol DI 注入边界 (C10, NEW-D)

MVP0 MUST 在 runtime / assembly 主入口注入 `SkillResolverProtocol`, 与 Q9 ModelResolverProtocol 同款单方法 DI。它只允许:

```python
def resolve_skill(skill_id: str) -> str | Path: ...
```

| 参数 / 返回 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `skill_resolver` | SkillResolverProtocol | 含 SUBGRAPH / subagent / Agent `subgraphs` 时必填 | 无 | 必须只有 `resolve_skill(skill_id) -> str | Path` 语义 | `[F-v3-resolver-missing]` / `[F-v3-resolver-interface-invalid]` | 子 skill registry 寻址 |
| `skill_id` | string | 是 | 无 | `^[a-z][a-z0-9_-]*$` | `[F-v3-resolver-skill-id-invalid]` | registry key |
| return `str | Path` | str 或 Path | 是 | 无 | 会被 runtime 转成 `Path`; 路径存在、是目录、含 `GRAPH.md` | `[F-v3-skill-not-registered]` / `[F-v3-resolver-path-invalid]` | 子 graph skill root |

实现差异:

| 环境 | Resolver 实现 | 行为 |
|---|---|---|
| Studio sandbox | `StudioSkillResolver` 查本地 skill registry; 未注册时把 `[F-v3-skill-not-registered]` 传给前端 | Assets Panel 标红并触发导入 |
| 生产 Registry 模式 | 后端服务或部署配置查只读 registry | 未注册直接 FATAL, 不弹本地文件选择 |
| 单测 | InMemorySkillResolver / fixture resolver | 用临时目录映射 skill id |

Runtime 不允许回退到 `_resolve_subagent_root` 或相对路径扫描。规范终点见 [SkillResolverProtocol DI 边界](../skill-spec/10-skill-resolver-protocol-spec.md#依赖注入-di-边界)。

### 2. Child flow subagent_depth 状态透传与下发

MVP0 MUST 把影响执行逻辑的深度状态写入 child `BlackboardState.flow`, 不只放在 `RunnableConfig.metadata`。

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `flow.subagent_depth` | integer | 子调用时必填 | parent depth + 1 | `>= 0`; 超限制时中断 | `[F-v3-runtime-phase-failed]` | 防止无限递归 |
| `child.flow` | dict | 是 | `{}` | 必须 deep copy parent flow 后写入 depth | `[F-v3-runtime-state-mapping-failed]` | 避免父子 flow 双向污染 |
| `child.data` | dict | 是 | 无 | 只来自显式 `io.inputs` 映射, 不继承父图全量 data | `[F-v3-runtime-state-mapping-failed]` | 黑板隔离 |
| `child.messages` | list | 是 | `[]` | 子图 / 子 Agent 从空消息历史开始 | — | 防止跨 Agent prompt 污染 |

这条规则同时约束 subagent、SUBGRAPH phase 和 Agent runtime 主动调用的 subgraph-like 能力。状态隔离细节与 [state-and-io-contract](../state-and-io-contract/mvp0-alignment.md#后端功能) 对齐。

### 3. ExitContractRegistry 退役与 exit_contract inline (C9)

MVP0 MUST 删除 `ExitContractRegistry` 的 per-turn inject / strip 设计。`exit_contract` 不再作为临时消息反复塞进 ReAct 历史, 而是在 Agent system prompt 装配时 inline 到 cognitive template 末尾, 并内嵌 `io.outputs` schema。

| 旧组件 / 字段 | V0.3.0 状态 | 替代物 | 校验规则 | 错误码 | 业务作用 |
|---|---|---|---|---|---|
| `ExitContractRegistry` | 退役 | `<exit_contract>` 尾置模板 | runtime 不再 inject/strip messages | — | 避免历史堆积 |
| `AgentNodeAST.exit_contract` | 退役 | `V030_AGENT_EXIT_CONTRACT_TEXT` 系统默认字符串 | Agent body 不再提供 `<exit_contract>` | `[F-v3-cognitive-output-schema-render-failed]` | 最终输出规则 |
| `<exit_contract>` body tag | 禁止 | PR G / round-18 已删除 repo 内 codemod; live loader 看到 Agent body 顶层 `<exit_contract>` 直接 FATAL | `[F-v3-agent-body-tag-unknown]` | 防止旧契约继续进入 runtime |
| `output_schema` 独立插槽 | 退役 | 追加到 exit_contract 末尾 | 序列化失败 FATAL | `[F-v3-cognitive-output-schema-render-failed]` | recency bias |
| ReAct `messages` | 不存 exit contract 临时副本 | 只保存真实对话 / tool 消息 | 不允许重复注入 contract | `[F-v3-runtime-phase-failed]` | 控制上下文体积 |

这样做的原因是输出契约属于 Agent prompt 的固定系统约束, 不是每轮 runtime 临时补丁。规范终点见 [Cognitive Template 8 大插槽](../skill-spec/06-cognitive-template-spec.md#8-大插槽布局拓扑) 与 [Agent Body XML](../skill-spec/05-agent-md-spec.md#body-xml-扁平化容器)。

### 4. Subagent 全局寻址与轻量单节点抽象退役 (C11)

MVP0 MUST 取消“轻量单节点 subagent”分支。Agent `subagents:` registry 中的每个 `target_skill` 都表示一个完整 graph skill, 由 `SkillResolverProtocol` 解析。

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `subagents[].name` | string | 是 | 无 | Agent frontmatter 内唯一 | `[F-v3-agent-subagent-invalid]` | `@subagent:NAME` 和动态 tool 名 |
| `subagents[].target_skill` | string | 是 | 无 | resolver 可解析 | `[F-v3-skill-not-registered]` | 子 Agent graph skill |
| `subagents[].description` | string | 是 | 无 | 非空 | `[F-v3-agent-subagent-invalid]` | LLM tool 描述 |
| child input schema | JSON Schema object | 是 | 无 | 来自 child `GRAPH.md io.inputs` | `[F-v3-graph-io-schema-invalid]` | 动态 tool 参数 schema |

Runtime 注入的 subagent tool 名可以继续是 `call_subagent_<name>`, 但 tool 内部只能按 `target_skill` 调 resolver, 编译子 skill, 再用显式输入启动隔离 child graph。

### 5. SUBGRAPH target_skill 运行期调用与 IO 强映射 (C12)

V0.3.0 的 SUBGRAPH 是物理 phase 节点: `phases/<id>/SUBGRAPH.md`, frontmatter 声明 `target_skill` 和 `io`。Runtime 不接收 `child_graph_path` 参数, 只消费编译期已 resolve / 已校验的 target metadata。

| 字段 / 输入 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `target_skill` | string | 是 | 无 | 编译 / 装配期已通过 resolver | `[F-v3-skill-not-registered]` | 目标子图 |
| parent `io.inputs` | JSON Schema object | 是 | 无 | 与 child root `io.inputs` 字段 1:1 | `[F-v3-subgraph-io-mismatch]` | 子图入参映射 |
| parent `io.outputs` | JSON Schema object | 是 | 无 | 与 child root `io.outputs` 字段 1:1 | `[F-v3-subgraph-io-mismatch]` | 子图返回映射 |
| `phase_input` | dict | 是 | 无 | 只含 parent `io.inputs` 字段 | `[F-v3-runtime-state-mapping-failed]` | 运行期隔离输入 |
| `child_output` | dict | 是 | 无 | 必须满足 parent `io.outputs` | `[F-v3-runtime-state-mapping-failed]` | 回写父图黑板 |

SUBGRAPH 节点像函数调用: 父图按声明传参, 子图按根 IO 接收, 返回值再按父 phase outputs 回写。规范终点见 [SUBGRAPH target_skill 寻址](../skill-spec/04-subgraph-md-spec.md#target_skill-寻址规则) 与 [IO 严格映射](../skill-spec/04-subgraph-md-spec.md#io-严格-11-映射校验-strict-mapping)。

### 6. 执行器异常捕获与 V0.3.0 错误码归一 (C13)

MVP0 MUST 把运行期可预期失败归一到 `[F-v3-*]`。本文件新增关注以下 runtime / assembly 错误:

| 错误码 | 阶段 | 触发条件 | 处理 | Spec |
|---|---|---|---|---|
| `[F-v3-skill-not-registered]` | 装配期 / 运行期 | resolver 查不到 `target_skill` | FATAL; Studio 可标红导入 | [Error Code Spec](../skill-spec/11-error-code-spec.md#错误码速查全表) |
| `[F-v3-reference-reader-failed]` | 装配期 | builtin reference reader 超时、普通异常或输出非法 | WARN; fallback 原文摘录继续装配 | [Error Code Spec](../skill-spec/11-error-code-spec.md#错误码速查全表) |
| `[F-v3-resource-reference-path-invalid]` | 编译期 / 装配期 / tool 运行期 | reference path 为空、绝对路径、逃逸 skill root、不可读，或 reader 遇到 path fatal | FATAL; 不允许 fallback 静默降级 | [Error Code Spec](../skill-spec/11-error-code-spec.md#错误码速查全表) |
| `[F-v3-cognitive-output-schema-render-failed]` | 装配期 | `io.outputs` 无法 inline 到 exit_contract | FATAL | [Error Code Spec](../skill-spec/11-error-code-spec.md#错误码速查全表) |
| `[F-v3-runtime-state-mapping-failed]` | 运行期 | StateMapper 切片 / 回写失败 | FATAL; 不回写脏数据 | [Error Code Spec](../skill-spec/11-error-code-spec.md#错误码速查全表) |
| `[F-v3-runtime-phase-failed]` | 运行期 | phase 执行异常且无法归入更细错误 | FATAL; trace 原始异常 | [Error Code Spec](../skill-spec/11-error-code-spec.md#错误码速查全表) |
| `[F-v3-tool-argument-invalid]` | 运行期 | builtin tool 参数非法 | tool error message 返回 Agent 或 FATAL | [Error Code Spec](../skill-spec/11-error-code-spec.md#错误码速查全表) |

未知 Python 异常仍可保留原始 traceback 到 trace debug payload, 但对外 code 必须是 `[F-v3-runtime-phase-failed]`。

### 7. Builtin Reference Reader Subagent 装配期调用 (NEW-A)

MVP0 MUST 在 Agent cognitive template 渲染前主动调用 builtin reference reader subagent。它读取 Agent frontmatter `references` 注册表, 输出 Markdown 作为 `knowledge_base_markdown` 注入 `<knowledge_base>`。

| 输入 / 输出 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `skill_id` | string | 是 | 无 | 当前 graph skill id | `[F-v3-reference-reader-input-invalid]` | trace 定位 |
| `phase_id` | string | 是 | 无 | 当前 Agent phase id | `[F-v3-reference-reader-input-invalid]` | trace 定位 |
| `references` | list[ReferenceSpec] | 是 | `[]` | 每项 id/path/summary 已编译期校验 | `[F-v3-resource-reference-invalid]` | reader 输入资料 |
| `markdown` | string | 是 | fallback markdown | reader 输出非空 | `[F-v3-reference-reader-output-invalid]` / `[F-v3-reference-reader-failed]` | knowledge_base 内容 |
| `warnings` | list[string] | 否 | `[]` | WARN trace | `[F-v3-reference-reader-failed]` | 降级说明 |

失败策略:

1. reader 超时 / 抛异常 / 输出非法: 发 WARN `[F-v3-reference-reader-failed]`。
2. Runtime 截取每份 reference 原文前 3000 token, 生成 fallback markdown。
3. fallback 填入 `<knowledge_base>` 插槽, Agent run 不阻塞。
4. 若失败码是 `[F-v3-resource-reference-path-invalid]`, 必须 FATAL 透传, 不进入 fallback。

规范终点见 [Builtin Reference Reader Subagent 签名](../skill-spec/09-builtin-modules-spec.md#builtin-reference-reader-subagent-签名) 与 [Reference 三机制生命周期](../skill-spec/08-resource-mechanisms-spec.md#reference-三机制生命周期)。

### 8. Builtin Tools 运行期注入 (NEW-B)

MVP0 MUST 给每个 Agent runtime 注入 `read_reference` 与 `read_example` builtin tools。即使 frontmatter `tools:` 未列这两个名字, Agent 也可以按 cognitive template 提示主动调用。工具必须先查当前 phase registry, 未声明 id 要在文件 IO 前短路, 不能尝试访问同名外部文件。

| Tool | 参数 | 类型 | 必填 | 默认值 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `read_reference` | `reference_id` | string | 是 | 无 | `[F-v3-resource-reference-not-found]` | 读取注册 reference |
| `read_reference` | `query` | string | 否 | `""` | — | 指定查阅问题 |
| `read_reference` | `mode` | string | 否 | `excerpt` | `[F-v3-tool-argument-invalid]` 仅用于 `reference_id` 类型错误；当前实现接收但忽略 `mode` | 预留读取模式 |
| `read_example` | `example_id` | string | 是 | 无 | `[F-v3-resource-example-not-found]` | 读取 inline 或 document example |
| `read_example` | `query` | string | 否 | `""` | — | 指定对照问题 |

Builtin tools 的权限域只能看到当前 Agent phase 注册的 `references` / `examples`, 不能跨 phase 或跨 skill 读取未注册资源。路径读取统一用 `relative_to(root_resolved)` 拦截逃逸；reference path 错误码是 `[F-v3-resource-reference-path-invalid]`, example path 错误码是 `[F-v3-resource-example-path-invalid]`。实现位置与签名见 [按需调取 Tools](../skill-spec/09-builtin-modules-spec.md#按需调取-tools-read_reference--read_example)。

### 9. Cognitive Template 8 容器装配 (NEW-C)

Execution-runtime 的装配层 MUST 消费 `AgentNodeAST` 和资源预处理结果, 渲染最终 Agent system prompt。当前 live 代码使用 8 个固定 XML 容器；`<exit_contract>` 固定尾置但不计入 8 个认知容器。

| 容器 / 字段 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `<role>` / `role` | string | 是 | 无 | 来自 Agent AST role | `[F-v3-agent-role-missing]` | 身份 |
| `<goal>` / `goal` | string | 是 | 无 | 来自 Agent AST goal | `[F-v3-agent-goal-missing]` | 目标 |
| `<thinking_style>` / `steps_md` | markdown | 否 | `"无显式步骤"` | `steps` 平铺为 `- [id] name: content` | `[F-v3-agent-step-invalid]` | 思考规则 + 行动步骤 |
| `<knowledge_base>` / `knowledge_base_markdown`, `reference_registry_listing` | markdown | 否 | `"无预读取参考资料"` / `"无注册 Reference"` | NEW-A 输出 + reference id/summary 清单 | `[F-v3-reference-reader-failed]` WARN / `[F-v3-resource-reference-path-invalid]` FATAL | 领域知识 |
| `<examples>` / `inline_examples`, `example_registry_listing` | markdown | 否 | `"无内联示范"` / `"无扩展案例"` | inline 正文 + document example id/summary 清单 | `[F-v3-resource-example-invalid]` | 示例 |
| `<ambiguity_feedback>` | 固定文本 | 是 | 固定存在 | 模板内置 | — | 不清晰时记录 ambiguity |
| `<protocol_citation>` / `protocols_md` | markdown | 否 | `"无显式协议"` | protocols 平铺为 `- [protocol:id] content` | `[F-v3-agent-protocol-invalid]` | 协议依据 |
| `<critical_reminders>` | 固定文本 | 是 | 固定存在 | 模板内置 | `[F-v3-agent-output-schema-invalid]` 等运行期反馈 | finish 前自检 |
| `<exit_contract>` / `V030_AGENT_EXIT_CONTRACT_TEXT`, `schema_md` | 系统默认字符串 + schema | 是 | `schema_md="{}"` | 系统默认字符串 + `io.outputs` schema | `[F-v3-cognitive-output-schema-render-failed]` | 输出契约末尾 recency bias |

渲染完成后, Agent ReAct 循环只接收一个稳定 system prompt, 不再在每轮 message history 动态注入 exit contract。规范终点见 [Cognitive Template 8 大插槽](../skill-spec/06-cognitive-template-spec.md#8-大插槽布局拓扑)。

### 10. LOGIC Actions 运行时一级寻址 ActionRegistry (C14)

MVP0 MUST 在运行期继续执行编译期已校验的一级 action 寻址, 并通过 ActionRegistry 固定作用域。

| 字段 / 对象 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `ActionRegistry.skill_root` | Path | 是 | 无 | 当前 graph skill root | `[F-v3-logic-action-dir-missing]` | action 寻址根 |
| `actions_dir` | Path | actions 非空时必填 | `<skill_root>/actions` | 不允许跨 skill | `[F-v3-logic-action-dir-missing]` | skill-global action 目录 |
| `action_name` | string | 是 | 无 | 不得为空、不得包含 `/`、`\`、`.`、不得为绝对路径 | `[F-v3-logic-action-name-invalid]` | action key |
| `action_path` | Path | 是 | 无 | 必须等于 `<skill_root>/actions/<name>.py` | `[F-v3-logic-action-not-found]` | action 文件 |
| `run` | callable | 是 | 无 | 返回 dict | `[F-v3-logic-action-entrypoint-missing]` / `[F-v3-logic-action-return-invalid]` | runtime 执行入口 |

Sandbox 模式必须禁止跨 skill action 引用: action 名不能包含 `/`, `\`, `.`, Python module path 或绝对路径；`..` 已被“包含 `.`”覆盖。Action 返回非 dict 抛 `[F-v3-logic-action-return-invalid]`；返回 dict 或 `Context` 就地突变写入未声明字段都归一抛 `[F-v3-logic-output-field-undeclared]`。规范终点见 [LOGIC Actions 1 级寻址](../skill-spec/03-logic-md-spec.md#actions-1-级寻址与执行契约)。

## API

### 1. ModelResolverProtocol 接口声明

```python
class ModelResolverProtocol(Protocol):
    def resolve(
        self,
        role_name: str | None = None,
        *,
        thinking_enabled: bool | None = None,
        model_override: str | None = None,
        callbacks: tuple[Callback, ...] = (),
        phase_name: str | None = None,
        **kwargs: Any,
    ) -> BaseChatModel:
        ...
```

| 参数 / 返回 | 类型 | 必填 | 默认值 | 校验规则 | 错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `role_name` | string | 否 | `None` | phase 可传已校验 role；graph_skill runner 当前可传空 | `[F-v3-agent-llm-role-unknown]` | 模型路由 key |
| `thinking_enabled` | bool | 否 | `None` | resolver 自行解释 | — | 思考模式开关 |
| `model_override` | string | 否 | `None` | resolver 自行解释 | — | 单次模型覆盖 |
| `callbacks` | tuple[Callback, ...] | 否 | `()` | resolver / gateway 内部仍期望 callback 形对象；T3 会把 event sink 包成 `_EventSinkCallbackAdapter(on_event -> emit)` | `TypeError` 用于未知 callbacks 对象 fail-loud | gateway fallback 观测桥接 |
| `phase_name` | string | 否 | `None` | 当前 graph_skill runner 用 `"<workflow>"` | — | resolver / trace 定位 |
| return | BaseChatModel | 是 | 无 | 可被 LangChain 调用 | `[F-v3-runtime-phase-failed]` | Agent LLM |

### 1.5 SkillResolverProtocol DI 注入边界

```python
class SkillResolverProtocol(Protocol):
    def resolve_skill(self, skill_id: str) -> str | Path:
        ...
```

该接口由 Engine 定义, Studio / production registry / tests 注入实现。字段表见 [后端功能 §1.5](#15-skillresolverprotocol-di-注入边界-c10-new-d), 规范终点见 [SkillResolverProtocol Interface](../skill-spec/10-skill-resolver-protocol-spec.md#protocol-interface-定义)。

### 2. run_skill V0.3.0 入口参数

```python
def run_skill(
    skill_path: str | Path,
    *,
    mock_llm: Any = _NO_MOCK_LLM,
    workspace_dir: Path,
    thread_id: str | None = None,
    unattended: bool = False,
    event_subscriber: Callable[[CallbackEvent], None] | None = None,
    artifact_saver: Any | None = None,
    initial_context: dict[str, Any] | None = None,
    cleanup_checkpoints_on_finish: bool = True,
    skill_resolver: SkillResolverProtocol,
    model_resolver: Any | None = None,
    **inputs: Any,
) -> RunResult:
    ...
```

| 参数 | 类型 | 必填 | 默认值 | 校验规则 | 错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `skill_path` | str 或 Path | 是 | 无 | V0.3.0 skill root, 必须包含 `GRAPH.md`; legacy root `SKILL.md` corpus 属 §10 Deferred 迁移范围 | `[F-v3-graph-root-missing]` 等编译错误 | 主图入口 |
| `**inputs` | Any kwargs | 否 | `{}` | 当前 graph_skill path 会写入初始 `data=dict(inputs)`；根级 strict input gate 仍是目标态 | `[F-v3-runtime-state-mapping-failed]` | 初始黑板 |
| `model_resolver` | Any | 否 | `None` | graph_skill path 有参；无 `mock_llm` 时在 Agent phase 装配中按 `llm_role or "graph_agent"` 调 `model_resolver.resolve(callbacks=..., phase_name=phase_id)` | `[F-v3-runtime-phase-failed]` | LLM 注入 |
| `skill_resolver` | Protocol | 是 | 无 | 实现 `resolve_skill` | `[F-v3-resolver-missing]` | 子 skill 寻址 |
| `mock_llm` | Any | 否 | sentinel `_NO_MOCK_LLM` | 优先于 `model_resolver` | — | 测试覆盖 |
| `workspace_dir` | Path | 是 | 无 | 必须是绝对路径 | `ValueError` / Python missing kwarg `TypeError` | `<workspace_dir>/runs/<run_id>/` 输出根 |
| `thread_id` | string | 否 | `None` | graph_skill path 无值时生成 UUID run id | — | run/thread 定位 |
| `unattended` | bool | 否 | `False` | legacy/harness 路径消费 | — | 无人值守运行 |
| `event_subscriber` | Callable[[CallbackEvent], None] | 否 | `None` | **[BREAKING]** T3 public 实时事件出口；不决定落盘路径；异常由 event sink 记录并隔离 | — | Studio timeline / 外部实时观测 |
| `artifact_saver` | Any | 否 | `None` | legacy/harness 路径消费 | — | artifact 保存 |
| `initial_context` | dict[str, Any] | 否 | `None` | legacy/harness 路径消费 | — | 初始上下文 |
| `cleanup_checkpoints_on_finish` | bool | 否 | `True` | run 结束后清理线程 checkpoint | — | 存储清理 |

### 3. ExitContractRegistry 删除说明

不再提供 `ExitContractRegistry.inject()` / `strip()` API。runtime 若仍需要兼容旧调用, 应在 V0.3.0 cutover 中直接删除旧路径或让旧 API 抛清晰迁移错误, 不能继续写入 message history。

### 4. Builtin tool 注册 API

```python
def _agent_resource_tools(
    phase_doc: PhaseDocument,
    phase_ast: AgentNodeAST,
    compiled: CompiledSkill,
) -> list[Any]:
    ...
```

| 输入 / 输出 | 类型 | 必填 | 默认值 | 校验规则 | 错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `phase_doc` | PhaseDocument | 是 | 无 | 含 phase path 和 phase name | — | tool metadata / skill root 反推 |
| `phase_ast.references` | list[ReferenceSpec] | 否 | `[]` | 编译期已校验 | `[F-v3-resource-reference-invalid]` | `read_reference` 闭包 registry |
| `phase_ast.examples` | list[ExampleSpec] | 否 | `[]` | 编译期已校验 | `[F-v3-resource-example-invalid]` | `read_example` 闭包 registry |
| `compiled` | CompiledSkill | 是 | 无 | 当前实现签名保留此参数；函数体未直接读取 | — | 预留装配上下文 |
| return | list[Any] | 是 | 无 | 包含 `_structured_tool(ToolDef(...))` 后的 `read_reference` / `read_example` | `[F-v3-tool-argument-invalid]` 等 tool 内错误 | Agent tool 域 |

## Data Model / State

### 1. BlackboardState 隔离模型

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `data` | dict | 是 | `{}` | phase 只能看到 StateMapper 切片 | `[F-v3-runtime-state-mapping-failed]` | 业务数据黑板 |
| `flow` | dict | 是 | `{}` | 控制字段 deep copy 下发 | `[F-v3-runtime-state-mapping-failed]` | 深度 / retry / run 控制 |
| `messages` | list | Agent phase 必填 | `[]` | 不保存 exit_contract 临时副本 | `[F-v3-runtime-phase-failed]` | ReAct 历史 |
| `run_id` | string | 是 | generated | trace 全局唯一 | — | observability |

### 2. AST 与 Cognitive Slot 映射联调模型 (NEW-E)

Runtime / assembly 消费编译期产出的 `AgentNodeAST`, 不直接解析 SKILL.md 文本。

| AgentNodeAST 字段 | 来源 | 目标插槽 / 组件 | 必填 | 错误码 | 业务作用 |
|---|---|---|---|---|---|
| `role` | body `<role>` | `{skill_role}` | 是 | `[F-v3-agent-role-missing]` | 身份 |
| `goal` | body `<goal>` | `{skill_goal}` | 是 | `[F-v3-agent-goal-missing]` | 目标 |
| `steps` | body `<step>` AST | `{skill_steps_splat}` | 否 | `[F-v3-agent-step-invalid]` | workflow 指引 |
| `protocols` | body `<protocol>` AST | `{skill_protocols_splat}` | 否 | `[F-v3-agent-protocol-invalid]` | 协议引用 |
| `references` | frontmatter | reference reader + `read_reference` | 否 | `[F-v3-resource-reference-invalid]` | 知识资料 |
| `examples` | frontmatter | examples slots + `read_example` | 否 | `[F-v3-resource-example-invalid]` | 案例 |
| `exit_contract` | 系统默认字符串 | `<exit_contract>` 尾置模板 | 是 | `[F-v3-cognitive-output-schema-render-failed]` | 输出规则 |
| `io.outputs` | frontmatter | `<output_schema>` 中的 `schema_md` | 是 | `[F-v3-cognitive-output-schema-render-failed]` | 输出结构 |

Body XML 的顶层业务标签与解析规则见 [Agent Body XML 扁平化容器](../skill-spec/05-agent-md-spec.md#body-xml-扁平化容器)。`knowledge_base` 和 `examples` 是 cognitive template 容器, 不是 Agent body 自定义标签。

## Cross-feature Interaction

### 1. State 黑板数据的严格沙盒隔离

SUBGRAPH、subagent tool 和未来 subgraph-like builtin tool 都必须只传显式 inputs, 不继承父图全量 data。编译期已证明 IO 对齐, runtime 负责按 schema 切片和回写。细节见 [state-and-io-contract](../state-and-io-contract/mvp0-alignment.md#后端功能)。

### 2. 运行时全维度事件发射

Runtime SHOULD 在 phase start/end、LLM call、tool call、reference reader fallback、subagent enter/exit、SUBGRAPH enter/exit、exception 位置发 typed event。T3 live path 通过 `_CompositeEventSink` 写 `trace.jsonl` 并可选调用 `event_subscriber`; 旧 public callbacks list 已被 **[SUPERSEDED by V0.3.0 event_subscriber cutover]** 替代。事件 payload 使用当前 live 字段 `phase_name` / `tool_name` / `event_type`; 目标态里的 `phase_id` 命名不能混入 live API 文档。

### 3. Ambiguity feedback 链路

Cognitive template 固定包含 ambiguity feedback 提示。Runtime 必须提供或透传 `log_ambiguity` 能力, 让 Agent 在规则不清晰时记录问题、决策和理由。Studio TracePanel 的展示需求来自 [V0.3.0 New Requirements](../../studio/V0.3.0-NEW-REQUIREMENTS--DO-NOT-DELETE-DURING-CLEANUP.md)。

### 4. RunnableConfig 边界

`RunnableConfig` 只承载 tags、callbacks、run id 等调度 / 观测信息。深度、重试次数、隔离输入输出不应依赖 RunnableConfig metadata, 必须进入 `BlackboardState.flow` 或显式 child state。

## 与当前源码的差异

本文件描述的是目标收敛方向；经过 V0.3.0 PR-3 的演进，目前 runtime 的状态为：

| 本文件目标态 | 当前源码事实 |
|---|---|
| `run_skill` 入口按根级 `io.inputs` 校验输入并拒绝非合法目录 | **已对齐 (PR-3)**: `_run_skill_dict` 入口已实现 Fail-loud 守卫。传入非 `GRAPH.md` 目录、普通文件或旧单文件将立即返回 `RunResult(success=False, error=...)`，且含有标准 `[F-v3-graph-root-missing]` 错误码。 |
| 彻底清除与 Persona 关联的执行层依赖和旧引擎历史包袱 | **已对齐 (PR-3)**: Persona 死码簇（含 `build_graph_nodes`, `_inject_persona` 等）已彻底拔除；`_run_skill_dict` 内部用于非 GRAPH root fallback 的旧版 182 行 `load_workflow_from_md` 及 `harness/.run_id` 续传等死分支均已干净拆除。 |
| Context 面向 Action 的可变暴露与工具沙盒防线 | **已对齐 (PR-3)**: Context Facade 已向齐基础的字典协议 (`__getitem__`, `__setitem__` 等 4 个方法)，以向后兼容现有 LOGIC。同时 `md_to_json.py` 内增加了针对 `md-patch` 的 deferred path 结果校验，严防 `KeyError("final_results")` 裸露。 |
| Agent phase 通过 per-role model resolver 解析真实模型 | 当前 `run_skill` 有 `model_resolver: Any | None = None` 参数；Agent phase 装配在无 `mock_llm` 时调用 `model_resolver.resolve(role_name=phase_ast.llm_role or "graph_agent", callbacks=_callback_tuple(event_sink), phase_name=phase_id)`。 |
| callbacks / trace 接回 graph runtime 主线 | **已被 T3 event_subscriber cutover 替代并完成主线接线**: V0.3 引擎自动派发 run start/end、common wrapper phase start/end、Agent LLM/tool 事件，并单写 `<workspace>/runs/<run_id>/trace.jsonl`。 |
| runtime 根级状态数据流隔离 | 当前初始 state 依然直接使用 `dict(inputs)`。 |
| GraphAgentError 以外异常也结构化返回 | 当前 public runner 只捕获 GraphAgentError；普通 RuntimeError 等可能直接冒泡。 |
