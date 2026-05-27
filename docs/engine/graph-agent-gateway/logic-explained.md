# Graph-Agent Gateway Logic Explained

本文是 PR alpha 后 `graph-agent-gateway` 当下代码蓝图的字段级翻译。它不描述一个理想设计，而是把当前源码逐项翻成自然语言：字段是什么、谁写入、谁消费、为什么这么切。

## 1. 包边界

`packages/graph-agent-gateway/src/graph_agent_gateway/__init__.py:5-20` 是 Gateway 包的公开门面。它只导出六个名字：`AllProvidersFailedError`、`GatewayResolverMissingError`、`GatewayRoleNotConfiguredError`、`GatewayChatModel`、`ModelResolver`、`ModelResolverProtocol`。这个列表的决策含义是：Engine 和 Studio 可以依赖 Gateway 的稳定入口，但不需要知道内部 helper 函数、配置解析细节或 provider 调度细节。

`packages/graph-agent-gateway/src/graph_agent_gateway/models.py:1-9` 目前没有真实 class/function，只保留 `__all__: list[str] = []`。它是 provider SDK wrapper 的预留边界。决策上先不把 OpenAI、Anthropic 等具体 SDK 泄漏到 Engine；未来新增 provider wrapper 时，也应留在 Gateway 包内。

## 2. 协议层：protocol.py

`ModelResolverProtocol` 位于 `packages/graph-agent-gateway/src/graph_agent_gateway/protocol.py:10-24`。它是 Engine 认识模型世界的唯一协议。

字段和参数翻译：

- `role_name: str | None` (`protocol.py:16`): 逻辑角色名，例如 `balanced`、`coding`。为 `None` 时由 resolver 使用默认角色。这样 Engine 不需要知道具体模型名。
- `thinking_enabled: bool | None` (`protocol.py:18`): 是否启用 reasoning/thinking。放在协议里是因为 Agent runtime 可能按 phase 控制推理能力，但 provider 细节仍由 Gateway 解释。
- `model_override: str | None` (`protocol.py:19`): 临时指定某个模型代码，绕过 role 的 active model。这个字段用于 predict、调试或 Studio 预览，但未命中时必须结构化失败。
- `callbacks: tuple[Any, ...]` (`protocol.py:20`): runtime callback 通道。Gateway fallback trace 通过这里回到 graph-agent 的 tracing 体系。
- `phase_name: str | None` (`protocol.py:21`): 当前 phase 名称。错误和 trace 都需要它，否则 Studio 只能看到一段 provider 失败文本。
- `**kwargs: Any` (`protocol.py:22`): 兼容未来 runtime 传入额外上下文，但当前 resolver 明确 `del kwargs`，避免悄悄引入隐式行为。
- 返回值 `BaseChatModel` (`protocol.py:23`): Engine 只拿 LangChain chat model surface，不直接持有 provider client。

这个协议像电器插座：Engine 只要求插头形状一致，不关心墙后面接的是哪家发电厂。

## 3. 配置模型：llm_config.py

`llm_config.py` 分成两层：可编辑 YAML schema 和运行时解析后的 schema。

### ModelEntry

`ModelEntry` 在 `packages/graph-agent-gateway/src/graph_agent_gateway/llm_config.py:10-21`，表示配置文件里的一个模型。

- `model_config = ConfigDict(extra="forbid")` (`llm_config.py:13`): 禁止未知字段，防止 PR #90 式自创字段进入 Gateway。
- `name: str` (`llm_config.py:15`): provider 实际调用的模型显示名或基础名。
- `reasoning: bool = False` (`llm_config.py:16`): 模型是否默认支持 reasoning。
- `min_max_tokens: int | None = None` (`llm_config.py:17`): 模型级默认输出 token 下限/默认值来源；resolver 会在没有 role/model 级 `max_tokens` 时使用它。
- `max_input_tokens: int | None = None` (`llm_config.py:18`): 输入上下文上限，当前主要保存在 schema 中，后续 preflight 可消费。
- `fc_supported: bool = False` (`llm_config.py:19`): function calling 能力标记。
- `providers: dict[str, str]` (`llm_config.py:20`): provider code 到 provider 侧模型名的映射。
- `provider_options: dict[str, dict[str, Any]] | None = None` (`llm_config.py:21`): provider 专属参数，例如某 provider 的 `max_max_tokens`。

### ProviderEntry

`ProviderEntry` 在 `llm_config.py:24-38`，表示配置文件里的 provider。

- `model_config = ConfigDict(extra="forbid")` (`llm_config.py:27`): provider 配置不允许未知字段。
- `name: str` (`llm_config.py:29`): provider 展示名。
- `type: str` (`llm_config.py:30`): provider 类型，例如 OpenAI compatible 或 Google GenAI。
- `api_key_env: str | None`、`api_key_env_fallback: str | None` (`llm_config.py:31-32`): API key 环境变量名和 fallback 名。
- `base_url: str | None`、`llm_base_url: str | None` (`llm_config.py:33-34`): provider endpoint。保留两个字段是为了兼容现有配置来源，但 Gateway 仍把它们当 provider 属性。
- `proxy_env: str | None` (`llm_config.py:35`): 代理环境变量。
- `timeout: int | None` (`llm_config.py:36`): 请求超时。
- `trust_env: bool | None` (`llm_config.py:37`): 是否信任系统环境代理。
- `retry_strategy: str | None` (`llm_config.py:38`): provider 自身重试策略标记。

### RoleModelEntry

`RoleModelEntry` 在 `llm_config.py:41-48`，表示某个 role fallback 链中的一个模型槽位。

- `providers: list[str] = Field(default_factory=list)` (`llm_config.py:46`): 这个 role 使用该模型时允许尝试的 provider 顺序。
- `temperature: float | None = None` (`llm_config.py:47`): PR alpha 的核心字段，从 role 顶层下推到 model 槽位。这样同一个 role 的不同模型可以有不同采样温度。
- `max_tokens: int | None = None` (`llm_config.py:48`): 同样下推到 model 槽位，避免 fallback model 被迫共用一个输出长度。

### RoleEntry

`RoleEntry` 在 `llm_config.py:51-61`，表示一个逻辑角色。

- `temperature: float | None = None`、`max_tokens: int | None = None` (`llm_config.py:56-57`): 当前 Gateway schema 仍保留读取能力，作为迁移期输入兜底；Studio 保存时会把它们下推并排除顶层旧字段。
- `model_fallback: bool = False` (`llm_config.py:58`): 是否允许 active model 失败后继续尝试 role.models 里其他模型。
- `active_model: str` (`llm_config.py:59`): 首选模型代码。
- `system_prompt_prefix: str | None = None` (`llm_config.py:60`): role 级系统提示前缀。
- `models: dict[str, RoleModelEntry]` (`llm_config.py:61`): role 下所有模型槽位配置。

### RolesData

`RolesData` 在 `llm_config.py:64-74`，表示完整 `llm_roles.yaml`。

- `model_config = ConfigDict(extra="allow")` (`llm_config.py:67`): 顶层允许额外字段，是为了不破坏现有配置里的非 Gateway 字段。
- `models`、`providers`、`roles` (`llm_config.py:69-71`): 三张主表。
- `single_model_roles: list[str]` (`llm_config.py:72`): 即使 role 配置了 fallback，也强制只用单模型的角色列表。
- `peer_model_groups: dict[str, list[str]]` (`llm_config.py:73`): 模型分组元数据，当前 Gateway 不主动调度。
- `circuit_breaker: dict[str, Any] | None` (`llm_config.py:74`): 熔断配置入口，当前主要传给后续 provider manager。

### ModelDef

`ModelDef` 在 `llm_config.py:77-89`，是运行时消费的模型定义。

- `code: str = ""` (`llm_config.py:82`): 配置键名被复制进实体，方便 error/trace 直接携带。
- `name`、`reasoning`、`min_max_tokens`、`max_input_tokens`、`fc_supported` (`llm_config.py:83-87`): 从 `ModelEntry` 归一化后的模型能力。
- `providers: dict[str, str]` (`llm_config.py:88`): provider 到 provider 模型名映射。
- `provider_options: dict[str, dict[str, Any]]` (`llm_config.py:89`): provider 级参数，默认空 dict，运行时不再处理 `None`。

### ProviderDef

`ProviderDef` 在 `llm_config.py:92-107`，是运行时消费的 provider 定义。

- `code: str = ""` (`llm_config.py:97`): provider 配置键名。
- `name`、`type` (`llm_config.py:98-99`): provider 展示名和类型。
- `api_key_env`、`api_key_env_fallback`、`base_url`、`llm_base_url`、`proxy_env`、`retry_strategy` 默认空字符串 (`llm_config.py:100-104,107`): 运行时不再区分缺失和空值，减少 provider client 分支。
- `timeout: int = 120` (`llm_config.py:105`): 默认超时。
- `trust_env: bool = False` (`llm_config.py:106`): 默认不隐式信任环境代理。

### ResolvedProvider

`ResolvedProvider` 在 `llm_config.py:110-119`，表示 fallback 链中的一个候选。

- `provider_code: str` (`llm_config.py:115`): provider 键名。
- `provider_def: ProviderDef` (`llm_config.py:116`): provider 的完整运行时配置。
- `model_name: str` (`llm_config.py:117`): provider 侧真实模型名。
- `model_def: ModelDef` (`llm_config.py:118`): 模型能力定义。
- `provider_options: dict[str, Any]` (`llm_config.py:119`): 当前候选的 provider 专属参数。

### ResolvedRole

`ResolvedRole` 在 `llm_config.py:122-132`，表示 resolver 已经把 role 展开成可执行 fallback 链。

- `role_name: str` (`llm_config.py:127`): 实际解析出的 role 名；model override 会变成 `_model_override::<code>`。
- `temperature: float` (`llm_config.py:128`): 首个候选的采样温度。
- `system_prompt_prefix: str` (`llm_config.py:129`): 空值归一成空字符串。
- `active_model_code: str` (`llm_config.py:130`): 首选模型代码。
- `model_fallback: bool` (`llm_config.py:131`): role 是否允许 fallback。
- `call_chain: list[ResolvedProvider]` (`llm_config.py:132`): 最终 provider/model 尝试顺序。

## 4. 结构化错误：exceptions.py

`GatewayError` 在 `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:13-27`，是 Gateway 错误基类。它优先继承 `graph_agent.core.exceptions.ExecutionError`，独立导入 Gateway 包时退化为 `RuntimeError` (`exceptions.py:7-10`)。这个设计让 Gateway 可以独立安装，也能在 Engine 内保留统一错误序列化。

字段翻译：

- `code: str` (`exceptions.py:16`): 稳定错误码。
- `message: str` (`exceptions.py:20`): 给人看的错误摘要。
- `context: dict[str, Any] | None` (`exceptions.py:23`): 给 Studio 和 trace 解析的机器字段。
- `super().__init__(f"{code} {message}", context=self.context)` (`exceptions.py:27`): 错误字符串带 code，但真正结构化数据放在 context。

三个 `[F-v3-gateway-*]` 错误码完整字典如下：

```python
{
    "code": "[F-v3-gateway-all-providers-failed]",
    "message": "All providers failed for role=<role_name>: <n> provider candidates failed",
    "context": {
        "role_name": "逻辑角色名",
        "phase_name": "phase 名；缺省为 <gateway>",
        "failed_provider_codes": ["provider/model", "..."],
        "last_error_chain": [
            {
                "provider": "provider/model",
                "error_type": "异常类名",
                "message": "异常消息",
            }
        ],
        "...": "调用方附加 context",
    },
}
```

该错误由 `AllProvidersFailedError` 构造 (`exceptions.py:30-57`)。决策点是把所有失败候选放进 `last_error_chain`，Studio 不再解析自由文本。

```python
{
    "code": "[F-v3-gateway-resolver-missing]",
    "message": "model_resolver is required for LLM/Agent phases",
    "context": {
        "phase_name": "phase 名；缺省为 <unknown>",
        "required_dependency": "model_resolver",
    },
}
```

该错误由 `GatewayResolverMissingError` 构造 (`exceptions.py:60-71`)。它表达的不是 provider 失败，而是 DI 契约没满足。

```python
{
    "code": "[F-v3-gateway-role-not-configured]",
    "message": "gateway role/model is not configured",
    "context": {
        "role_name": "请求的 role；可以为 None",
        "model_override": "请求的模型覆盖；可以为 None",
    },
}
```

该错误由 `GatewayRoleNotConfiguredError` 构造 (`exceptions.py:74-91`)。role 未注册、model override 未注册、provider/model 映射缺失都归到这个稳定 code。

## 5. Resolver：resolver.py

`ModelResolverStats` 在 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:28-32`。字段只有 `total_resolves: int = 0`，表示 resolver 被调用次数。它是运行时观测点，不参与调度决策。

`ModelResolver` 在 `resolver.py:35-218`。它把 `RolesData` 解析成 `GatewayChatModel`。

### __init__

`__init__` 在 `resolver.py:38-48`。

- `roles_data: RolesData | None` (`resolver.py:41`): 外部注入的完整角色配置。为空时读取默认 `config/llm_roles.yaml`。
- `client_manager: Any` (`resolver.py:42`): provider 调用管理器。测试可注入 fake，生产可使用默认 `LLMClientManager`。
- `self._stats_lock = threading.Lock()` (`resolver.py:46`): `total_resolves` 递增需要线程安全。
- `self.stats = ModelResolverStats()` (`resolver.py:47`): 暴露统计对象。

### resolve

`resolve` 在 `resolver.py:49-98`，实现 `ModelResolverProtocol`。

- `role_name`、`thinking_enabled`、`model_override`、`callbacks`、`phase_name` (`resolver.py:51-56`): 与协议同名，保证 Engine 传入什么，Gateway 能直接解释。
- `del kwargs` (`resolver.py:59`): 当前不接受隐式扩展。
- `self.stats.total_resolves += 1` (`resolver.py:60-61`): 每次解析计数。
- `resolved, temperature, max_tokens = self._resolve_role(...)` (`resolver.py:62-65`): 把配置树展开成运行时链。
- `if not resolved.call_chain` (`resolver.py:66-71`): 没有任何候选时直接抛 `[F-v3-gateway-all-providers-failed]`。
- `_graph_agent_predict_mock_strategy` (`resolver.py:72-87`): predict 模式的内部钩子；存在时返回 `PredictGatewayChatModel`，避免真实 provider 请求。
- 默认返回 `GatewayChatModel` (`resolver.py:88-98`): 把 role、温度、max_tokens、callbacks、phase、thinking、client manager 都塞进 LangChain model。

### _resolve_role

`_resolve_role` 在 `resolver.py:100-205`，是配置解释中心。

- `effective_role = role_name or os.environ.get("GRAPH_AGENT_DEFAULT_ROLE", "balanced")` (`resolver.py:106`): 没传 role 时用环境默认，再退到 `balanced`。
- role 未命中抛 `GatewayRoleNotConfiguredError` (`resolver.py:107-112`)。
- `model_override` 未命中同样抛 `GatewayRoleNotConfiguredError` (`resolver.py:114-118`)。
- 有 `model_override` 时只解析指定模型，并把 role 名改成 `_model_override::<code>` (`resolver.py:120-123`)。
- 无 override 时从 `role.active_model` 开始 (`resolver.py:124-127`)。
- `role.model_fallback` 且不在 `single_model_roles` 时，追加其他 role.models (`resolver.py:129-134`)。
- `first_temperature` 默认 `0.7`，`first_max_tokens` 默认 `4096` (`resolver.py:136-138`)。
- `role_model.temperature` 优先，其次 legacy `role.temperature`，最后 `0.7` (`resolver.py:151-156`)。
- `role_model.max_tokens` 优先，其次 provider option 的 `max_max_tokens`，再到 legacy `role.max_tokens`、`model_entry.min_max_tokens`、`4096` (`resolver.py:157-169`)。
- 每个 provider 生成一个 `ResolvedProvider` (`resolver.py:170-195`)。
- 最终生成 `ResolvedRole` (`resolver.py:197-204`)。

这个函数的难点是优先级。可以把它看成发车表：role 先决定首班车，fallback 决定后续班次；`RoleModelEntry` 是每班车自己的温度和载客上限，role 顶层字段只作为旧站牌迁移期参考。

### mark_provider_down

`mark_provider_down` 在 `resolver.py:207-218`。它手动把某个 provider/model 标为 down。

- 优先使用注入的 `client_manager`，否则用默认 manager (`resolver.py:209-213`)。
- 如果 manager 有新接口 `mark_provider_down`，调用新接口 (`resolver.py:214-215`)。
- 否则调用旧内部接口 `_mark_provider_down` (`resolver.py:216-217`)。

### 模块级 helper

- `_load_default_roles_data` (`resolver.py:220-225`): 从仓库根的 `config/llm_roles.yaml` 读取 YAML，并用 `RolesData` 校验。
- `_default_client_manager` (`resolver.py:228-231`): 延迟导入 `graph_agent.models.llm_client_manager.LLMClientManager`，避免 Gateway import 时立刻拉起 provider manager。
- `_provider_max_tokens` (`resolver.py:234-242`): 按 provider 顺序找第一个正整数 `max_max_tokens`。

## 6. LangChain 适配器：gateway_chat_model.py

`ToolSpec` 在 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:26`，表示 `bind_tools` 接受 dict、class、callable 或 LangChain `BaseTool`。决策是兼容 LangChain 工具输入，同时内部统一成 OpenAI tool 格式。

`GatewayChatModel` 在 `gateway_chat_model.py:29-233`，继承 `BaseChatModel`，把 Gateway fallback 逻辑包成 LangChain 可调用模型。

### 字段

- `role_name: str` (`gateway_chat_model.py:34`): 当前逻辑 role。
- `resolved_role: ResolvedRole` (`gateway_chat_model.py:35`): resolver 展开的 fallback 链。
- `max_tokens: int = 4096` (`gateway_chat_model.py:36`): 默认输出 token。
- `temperature: float = 0.7` (`gateway_chat_model.py:37`): 默认采样温度。
- `phase_name: str | None` (`gateway_chat_model.py:38`): trace/error 归属 phase。
- `event_callbacks: tuple[Any, ...]` (`gateway_chat_model.py:39`): fallback event 发送目标。
- `probe_before_call: bool = True` (`gateway_chat_model.py:40`): 调 provider 前是否探活。
- `thinking_enabled: bool | None` (`gateway_chat_model.py:41`): 覆盖模型 reasoning 默认值。
- `bound_tools: tuple[dict[str, object], ...]` (`gateway_chat_model.py:42`): 已绑定工具。
- `tool_choice: str | None` (`gateway_chat_model.py:43`): 工具选择策略。
- `tool_kwargs: dict[str, object]` (`gateway_chat_model.py:44`): bind_tools 的附加参数。
- `client_manager: Any` (`gateway_chat_model.py:45`): provider dispatch/probe/usage 后端。

### __init__

`__init__` 在 `gateway_chat_model.py:47-78`。它把 sequence/mapping 输入全部归一化成 tuple/dict (`gateway_chat_model.py:70-76`)，因为 Pydantic model 字段需要稳定、可比较、可复制的形态。

### _llm_type 和 _identifying_params

- `_llm_type` (`gateway_chat_model.py:80-82`): 固定返回 `graph_agent_gateway`，给 LangChain 识别模型类型。
- `_identifying_params` (`gateway_chat_model.py:84-90`): 暴露 `role_name`、`active_model_code`、`candidates`。这让 trace/cache 能看到当前 model 是哪条候选链。

### _generate

`_generate` 在 `gateway_chat_model.py:92-159`，是真正执行 provider fallback 的地方。

- `_langchain_messages_to_dict(messages)` (`gateway_chat_model.py:100`): 先把 LangChain message 转成 provider manager 能理解的 dict。
- `failures: list[dict[str, Any]] = []` (`gateway_chat_model.py:101`): 收集失败链。
- 遍历 `resolved_role.call_chain` (`gateway_chat_model.py:103`): 按 resolver 决定的顺序尝试 provider/model。
- `_is_marked_down` 跳过已熔断候选 (`gateway_chat_model.py:105-106`)。
- `probe_before_call` 为真时先 `_probe`，失败就 `_mark_down` 并继续 (`gateway_chat_model.py:107-109`)。
- `_dispatch` 发起 provider 调用 (`gateway_chat_model.py:112-126`)。传入字段包括消息、max_tokens、temperature、reasoning、tools、tool_choice。
- `_usage_total_calls` 前后对比 (`gateway_chat_model.py:111,127-135`): 如果 manager 没有自己记录 usage，就从 response 里补记。
- 成功时 `_build_chat_result` (`gateway_chat_model.py:136`)。
- 失败时写入 `provider`、`error_type`、`message` (`gateway_chat_model.py:137-143`)，标记 down (`gateway_chat_model.py:144`)，并发 `LLMFallbackEvent` (`gateway_chat_model.py:145-153`)。
- 全部失败后抛 `AllProvidersFailedError` (`gateway_chat_model.py:155-159`)。

### bind_tools

`bind_tools` 在 `gateway_chat_model.py:161-192`。它返回一个新的 `GatewayChatModel`，保留原 role、fallback 链、温度、callbacks、client manager 和 LangChain 元数据 (`gateway_chat_model.py:168-191`)，只替换 `bound_tools`、`tool_choice` 和 `tool_kwargs`。决策是遵守 LangChain model 不可变风格，工具绑定不污染原模型实例。

### _build_chat_result

`_build_chat_result` 在 `gateway_chat_model.py:194-227`。它把 provider manager 的 response dict 翻成 LangChain `ChatResult`。

- `usage` 来自 `_usage_from_response` (`gateway_chat_model.py:199`)。
- `finish_reason` 通过 `_optional_text` 归一 (`gateway_chat_model.py:200`)。
- `AIMessage.content` 使用 `_coerce_text` (`gateway_chat_model.py:201-203`)。
- `response_metadata` 带 `provider`、`model`、`finish_reason`、`usage` (`gateway_chat_model.py:204-209`)。
- `generation_info` 和 `llm_output` 也保留 provider/model/usage (`gateway_chat_model.py:211-227`)。

### _next_candidate_id

`_next_candidate_id` 在 `gateway_chat_model.py:229-233`。它从某个 index 后找下一个未 down 候选，找不到返回 `<none>`。fallback trace 的 `to_provider` 用它，避免 trace 误报一个已经熔断的目标。

### 模块级 helper

- `_candidate_id` (`gateway_chat_model.py:236-237`): 把候选显示成 `provider/model`。
- `_default_client_manager` (`gateway_chat_model.py:240-243`): 延迟导入默认 `LLMClientManager`。
- `_manager` (`gateway_chat_model.py:246-247`): 注入 manager 优先，否则默认 manager。
- `_is_marked_down` (`gateway_chat_model.py:250-254`): 兼容新旧 manager 熔断查询接口。
- `_probe` (`gateway_chat_model.py:257-261`): 兼容新旧 provider 探活接口。
- `_dispatch` (`gateway_chat_model.py:264-285`): 兼容新旧 provider 调用接口；非 mapping response 会包成 `{"content": str(response), "usage": {}}`。
- `_mark_down` (`gateway_chat_model.py:288-293`): 兼容新旧标记 down 接口。
- `_usage_from_response` (`gateway_chat_model.py:296-309`): 从 response usage 里读 prompt/completion/total，缺失时补 0。
- `_int_value` (`gateway_chat_model.py:312-317`): 非负 int/float/数字字符串转 int。
- `_int_kwarg` (`gateway_chat_model.py:320-327`): runtime kwargs 的正数 token override 校验，bool 不算数字。
- `_float_kwarg` (`gateway_chat_model.py:330-336`): runtime kwargs 的 temperature override 校验，解析失败回默认。
- `_bool_kwarg` (`gateway_chat_model.py:339-340`): 只有 bool 才覆盖默认。
- `_optional_text` (`gateway_chat_model.py:343-344`): 可空文本转换。
- `_coerce_text` (`gateway_chat_model.py:347-348`): content 统一成字符串。
- `_additional_kwargs_from_response` (`gateway_chat_model.py:351-360`): 透传 `additional_kwargs`、`tool_calls`、`reasoning_content`。
- `_langchain_messages_to_dict` (`gateway_chat_model.py:363-394`): System/Human/AI/Tool message 转 provider dict，同时保留 name、tool_call_id、tool_calls、reasoning_content。
- `_normalise_tool` (`gateway_chat_model.py:397-405`): dict function tool 原样归一；其他工具走 LangChain `convert_to_openai_tool`，并补默认 description/parameters。
- `_message_role` (`gateway_chat_model.py:408-417`): LangChain message class 到 provider role 字符串。
- `_usage_total_calls` (`gateway_chat_model.py:420-432`): 从 manager usage stats 读取 provider 总调用次数。
- `_record_usage` (`gateway_chat_model.py:435-444`): manager 支持 `record_usage` 时补写 usage。

## 7. Tracing：tracing.py

`logger = logging.getLogger(__name__)` 在 `packages/graph-agent-gateway/src/graph_agent_gateway/tracing.py:10`，只用于 callback 失败日志。

`build_llm_fallback_event` 在 `tracing.py:13-30`。

- `phase_name` (`tracing.py:15`): fallback 发生在哪个 phase。
- `from_provider`、`to_provider` (`tracing.py:16-17`): 从哪个 provider/model 切到哪个 provider/model。
- `reason` (`tracing.py:18`): 切换原因。
- `code` (`tracing.py:19`): 当前使用 `[F-v3-gateway-all-providers-failed]`。
- `context` (`tracing.py:20`): 附加上下文，当前至少包含 role。
- 返回 `LLMFallbackEvent` (`tracing.py:23-30`): 复用 graph-agent callback schema，不在 Gateway 自造 trace 文件格式。

`emit_llm_fallback_event` 在 `tracing.py:33-59`。

- 先构造 event (`tracing.py:44-51`)。
- 遍历 callbacks 并调用 `callback.on_event(event)` (`tracing.py:52-54`)。
- callback 失败只记录日志，不遮盖 provider 原始失败 (`tracing.py:55-59`)。

## 8. Predict 占位：predict_interception.py

`PredictGatewayChatModel` 在 `packages/graph-agent-gateway/src/graph_agent_gateway/predict_interception.py:15-40`。它继承 `GatewayChatModel`，但不会打真实 provider。

- `mock_strategy: Any` (`predict_interception.py:23`): predict mock 策略对象。
- `self.mock_strategy = mock_strategy` (`predict_interception.py:26`): 保存策略，保持与 Engine predict 钩子兼容。
- `_generate` (`predict_interception.py:29-40`): 忽略 messages、stop、run_manager、kwargs，返回 content 为 `predict mock` 的 `ChatResult`，`llm_output` 标记 provider 为 `predict`。

当前 Engine 内更完整的 predict 子类位于 `graph_agent.core._predict_internal.interception`，Gateway 包内这个文件主要承担包边界占位和导出语义。

## 9. Engine DI 入口

`GraphAgentHarness.__init__` 在 `packages/graph-agent/src/graph_agent/core/harness.py:338-358` 接受 `model_resolver`。当 `model_resolver is None` 时，它抛 `GatewayResolverMissingError(phase_name="<harness>")` (`harness.py:355-358`)。这就是 PR alpha 的关键切换：生产 runtime 不再偷偷调用 `get_model_resolver()` 单例。

`run_skill` 在 `packages/graph-agent/src/graph_agent/core/runner.py:59-127` 接收 `model_resolver: Any | None = None` 并传入 `_run_skill_dict`。

`_run_skill_dict` 在 `runner.py:130-196` 只接受包含 `GRAPH.md` 的 V0.3 skill root。合法 root 会把 `model_resolver` 继续传给 `_run_v030_skill_dict`；非 root 入口直接走 `[F-v3-graph-root-missing]` 失败返回，不再进入 legacy `load_workflow_from_md` 分支。

`_run_v030_skill_dict` 在 `runner.py:217-283` 中，如果没有显式 `mock_llm` 且传入了 `model_resolver`，就调用 `model_resolver.resolve(callbacks=tuple(active_callbacks), phase_name="<workflow>")`，然后把 `chat_model` 交给 graph assembly。显式传入 `mock_llm` 时优先使用 `mock_llm`，即使值是 `None` 也不会再调用 `model_resolver`。

Studio backend 在 `apps/studio/backend/app/services/gateway_resolver.py:16-23` 通过 `build_gateway_model_resolver` 从 `config/llm_roles.yaml` 构造 `ModelResolver`。`run_manager.py:231-236` 和 `predictor.py:72-76` 都显式传入这个 resolver。决策上，Studio 是配置拥有者，所以 resolver 也应由 Studio 注入，而不是 Engine 自己读取全局单例。

## 10. LLM Roles Phase 1 迁移

Studio 的迁移逻辑在 `apps/studio/backend/app/services/migrations.py:27-58`。

- `migrate_roles_payload(payload: Any)` (`migrations.py:27`): 直接 walk 原始 YAML payload。
- provider type 旧值会通过 `migrate_provider_type_value` 归一 (`migrations.py:32-40`)。
- 每个 role 的 `temperature` 和 `max_tokens` 会被 `pop` 掉 (`migrations.py:46-47`)。
- 每个 `role.models[*]` 如果缺字段，则用 `setdefault` 写入旧顶层值 (`migrations.py:51-57`)。

这里用 `setdefault` 是关键：旧顶层值像整栋楼的旧恒温器；每个房间已经有自己的温度时，不该被旧恒温器覆盖。

`load_roles_file` 在 `apps/studio/backend/app/services/llm_roles.py:27-45` 读取 YAML 后先转 plain dict，再调用迁移 (`llm_roles.py:30-35`)。`data.migration_required = migrated` (`llm_roles.py:37`) 标记是否发生内存迁移；迁移过的文件不保留 `_original_text` 和 `_original_snapshot` (`llm_roles.py:42-44`)，下一次保存会写成新格式。

`save_roles_file` 在 `llm_roles.py:48-57` 先 `validate_references`，再决定保留原文或 dump 新 payload。`_dump_synced_raw` 在 `llm_roles.py:93-114` 序列化时 `exclude={"migration_required"}` (`llm_roles.py:94-98`)，并把 `models`、`providers`、`roles`、`single_model_roles`、`peer_model_groups`、`circuit_breaker` 写回 raw (`llm_roles.py:101-109`)。

Gateway 侧 `RoleModelEntry.temperature/max_tokens` 在 `llm_config.py:46-48` 接住迁移结果，`ModelResolver._resolve_role` 在 `resolver.py:151-169` 按优先级消费它们。这样数据层和运行层形成闭环：加载时下推，保存时不吐旧字段，调用时从 model 槽位读取。
