# PR-C Design: LLM 配置一刀切搬 Gateway

本文是 Round 31 PR-C 的实施蓝图，供 SOP-08 tests-first 直接写红灯使用。权威基线为 `decisions.md` §1 / §6 / §11 / §12 与 `tasks.md` §4。

## §0 目标与一刀切原则

PR-C 目标：将 LLM yaml 加载、schema 验证、provider/role/model 解析、fallback、熔断、热加载、provider runtime 从 SDK 一刀切搬到 `graph-agent-gateway`。SDK 不再拥有 LLM 配置，只消费 Gateway 提供的 `model_resolver` protocol。

权威约束：

- `decisions.md` §1 明确 “SDK 不管 LLM 配置；Gateway 是独立完整的 LLM 配置管家；SDK 只接收 Gateway 提供的 `model_resolver` 协议”，并列出 Gateway 拥有 yaml 加载、schema 验证、provider/role/model 解析、fallback、熔断、热加载：`.kiro/specs/engine-mvp0-rebuild-v030/round-31-api-surface-rightsizing/decisions.md:16-28`。
- `decisions.md` §6 明确一个 cutover PR 内完成整体搬迁、Studio import rename、SDK 老代码删除；不保留 SDK/Gateway 双栈，不做 SDK -> Gateway compatibility proxy：`.kiro/specs/engine-mvp0-rebuild-v030/round-31-api-surface-rightsizing/decisions.md:138-150`。
- `decisions.md` §11 要求旧 API 假设 tests 在 cutover PR 内删除或重写，新 tests 覆盖 Gateway LLM config ownership：`.kiro/specs/engine-mvp0-rebuild-v030/round-31-api-surface-rightsizing/decisions.md:268-277`。
- `decisions.md` §12 明确 Gateway 不 import Studio，不拥有 predict cache / golden / ABC / skill workspace 业务决策，只负责 provider/model/role 与 chat/predict model facade：`.kiro/specs/engine-mvp0-rebuild-v030/round-31-api-surface-rightsizing/decisions.md:287-300`。
- `tasks.md` §4 PR-C scope 与 src tasks 明确 SDK 老 config/provider runtime 搬迁，Gateway schema 主导 Resolver Schema 契约，不用 SDK dataclass 机械覆盖：`.kiro/specs/engine-mvp0-rebuild-v030/round-31-api-surface-rightsizing/tasks.md:189-223`。

一刀切含义：

- 删除 SDK `graph_agent.config.llm_config` 的配置所有权；SDK 不提供 compatibility proxy。
- Gateway 成为 `ProviderDef` / `ResolvedProvider` / `ResolvedRole` / `ModelResolver` / `ModelResolverProtocol` / `LLMClientManager` 的唯一真相源。
- Studio 同一时刻只能 import Gateway config/resolver 入口，不允许同时 import SDK `graph_agent.config.llm_config` 与 Gateway config。
- Predict mock 反向依赖 `resolver.py:74` 属 PR-E 边界，PR-C 不处理，见 §8。

## §1 搬迁清单与 Single Source

### §1.1 SDK 老 LLM config 全量剥离

现状 SDK config 文件承担数据结构、yaml 加载、验证、解析、热加载：

- SDK `ModelDef` / `ProviderDef` / `RoleModelEntry` / `RoleDef` / `ResolvedProvider` / `ResolvedRole` / `CircuitBreakerConfig` 定义在 `packages/graph-agent/src/graph_agent/config/llm_config.py:39-121`。
- SDK `RoleConfigData.resolve_role()` 与 `resolve_model()` 保留 provider/role/model/fallback 展开能力：`packages/graph-agent/src/graph_agent/config/llm_config.py:176-205`、`packages/graph-agent/src/graph_agent/config/llm_config.py:235-279`。
- SDK `_load_config_file()` / `load_config()` 负责 yaml 读取和验证：`packages/graph-agent/src/graph_agent/config/llm_config.py:515-656`。
- SDK `_RoleConfigHolder` / `get_role_config()` / `reset_role_config()` 负责热加载单例和测试重置：`packages/graph-agent/src/graph_agent/config/llm_config.py:678-755`。

PR-C 后：

- `packages/graph-agent/src/graph_agent/config/llm_config.py` 不再存在于 SDK 配置所有权内；不保留 SDK proxy。
- `packages/graph-agent/src/graph_agent/config/__init__.py` 不再 re-export `RoleConfigData/get_role_config/load_config/reset_role_config`。
- SDK 内部不得 import `graph_agent.config.llm_config`。

### §1.2 Gateway public nouns

Gateway 当前已有 Pydantic schema：

- `ModelEntry` / `ProviderEntry` / `RoleModelEntry` / `RoleEntry` / `RolesData`：`packages/graph-agent-gateway/src/graph_agent_gateway/llm_config.py:10-74`。
- `ModelDef` / `ProviderDef` / `ResolvedProvider` / `ResolvedRole`：`packages/graph-agent-gateway/src/graph_agent_gateway/llm_config.py:77-132`。

PR-C 要求 Gateway public noun 明确化：

- `ProviderDef`、`ResolvedProvider`、`ResolvedRole` 作为 Gateway public noun 保留并导出。
- `ModelResolver.resolve_role(role_name: str | None) -> ResolvedRole` 与 `ModelResolver.resolve_model(model_code: str) -> ResolvedRole` 作为 Gateway provider 检视能力公开保留。
- `ModelResolver.resolve()` 仍返回 LangChain-compatible `BaseChatModel`，用于 SDK runtime 消费。
- `ModelResolver.get_role_prefix(role_name: str | None) -> str` 作为 SDK prompt assembly 唯一小口子。

保留 provider 检视能力是黄金原则防丢功能：Studio Copilot 当前通过 SDK `load_config().resolve_role("copilot_chat")` 或 `resolve_model(model_override)` 取 provider，再查 credentials：`apps/studio/backend/app/services/copilot.py:370-399`。搬 Gateway 后该能力必须迁移到 Gateway，而不是删除。

### §1.3 LLMClientManager 搬入 Gateway

现状：

- SDK `LLMClientManager` 位于 `packages/graph-agent/src/graph_agent/models/llm_client_manager.py:43`，直接 import SDK `ProviderDef` / `ResolvedProvider`：`packages/graph-agent/src/graph_agent/models/llm_client_manager.py:24`。
- 它维护进程级 client cache、usage stats、provider down cache 与锁：`packages/graph-agent/src/graph_agent/models/llm_client_manager.py:52-58`。
- 它负责 probe / mark down / dispatch provider call / token escalation / api key resolution：`packages/graph-agent/src/graph_agent/models/llm_client_manager.py:196-220`、`packages/graph-agent/src/graph_agent/models/llm_client_manager.py:412-526`。

PR-C 后：

- 新增 Gateway 内部 runtime module，例如 `packages/graph-agent-gateway/src/graph_agent_gateway/llm_client_manager.py`。
- `LLMClientManager` 使用 Gateway `ProviderDef` / `ResolvedProvider`，不得保留 SDK dataclass 第二套真相。
- `graph_agent_gateway.gateway_chat_model` 默认 client manager 从 Gateway 本地导入，不再 lazy import SDK：当前反向 lazy import 在 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:240-243`。
- `graph_agent_gateway.resolver` 默认 client manager 从 Gateway 本地导入，不再 lazy import SDK：当前反向 lazy import 在 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:228-231`。

依赖声明同步：

- Gateway 当前依赖只有 `langchain-core`、`langchain-openai`、`langchain-anthropic`、`pydantic`：`packages/graph-agent-gateway/pyproject.toml:6-11`。
- 搬 `LLMClientManager` 后 Gateway 必须拥有 `httpx`、`openai`、`anthropic`、`pyyaml` 等运行时依赖，不再靠 SDK `pyproject.toml` 兜底；SDK 当前依赖这些在 `packages/graph-agent/pyproject.toml:22-27`。

### §1.4 Gateway loader/validator/热加载

Gateway 当前 `ModelResolver.__init__()` 直接使用 `_load_default_roles_data()` 或传入 `roles_data`：`packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:38-47`；默认加载只是 `yaml.safe_load(...llm_roles.yaml)` 后 `RolesData.model_validate()`：`packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:220-225`。这不足以覆盖 decisions §1 的 loader/validator/热加载职责。

PR-C 要求：

- Gateway 新增可测试的内部 loader/validator module，例如 `graph_agent_gateway.config_loader`。
- 内部入口覆盖：
  - 显式 path 加载。
  - `GRAPH_AGENT_ROLES_PATH` 或等价 env path。
  - repo `config/llm_roles.yaml` 默认定位。
  - yaml 顶层结构校验。
  - role -> model -> provider 交叉引用校验。
  - `peer_model_groups`、`single_model_roles`、`circuit_breaker` 解析。
- 不暴露全局 `load_config()` / `get_role_config()` 单例给 SDK/Studio 乱调。外部入口是 `ModelResolver(roles_path=...)`、`ModelResolver(roles_data=...)` 与实例方法。
- `ModelResolver.resolve()`、`resolve_role()`、`resolve_model()`、`get_role_prefix()` 调用前静默触发 `_refresh_if_needed()`：检查 path mtime + lock；加载失败且有上次有效配置时继续使用旧配置并记录 warning；首次加载失败则抛 Gateway error。
- `roles_data` 注入模式下 `_refresh_if_needed()` 必须是 no-op：当前 Studio `build_gateway_model_resolver()` 先 `load_roles_file(roles_path)`，再 `GatewayRolesData.model_validate(...)`，最后 `ModelResolver(roles_data=gateway_roles)`：`apps/studio/backend/app/services/gateway_resolver.py:16-23`。这种模式没有 resolver path，Studio 热加载归 Studio 重建 resolver 那层负责，不由 Gateway resolver 对 `roles_data` 猜 mtime。
- `ModelResolver` 需要独立的 config lock，不能复用 stats lock；当前只有 `_stats_lock` 统计 resolve 次数：`packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:46-61`。

## §2 ModelResolverProtocol 扩充与统一

### §2.1 现状问题

当前有两份同名 protocol：

- Gateway `ModelResolverProtocol` 定义在 `packages/graph-agent-gateway/src/graph_agent_gateway/protocol.py:10-24`。
- SDK phase node base 也定义 `ModelResolverProtocol`，供 `DependencyContainer.resolver` 使用：`packages/graph-agent/src/graph_agent/core/phase_nodes/base.py:41-54`、`packages/graph-agent/src/graph_agent/core/phase_nodes/base.py:81-83`。
- `PhaseExecutor` 从 SDK `phase_nodes` 导入这份 protocol：`packages/graph-agent/src/graph_agent/core/phase_executor.py:43-47`，构造时接收 `resolver`：`packages/graph-agent/src/graph_agent/core/phase_executor.py:67-74`。

如果只改 Gateway protocol，会留下 SDK 旧形状，LLMPhaseNode 对 `get_role_prefix()` 的调用无法被类型/测试覆盖。

### §2.2 设计方案

PR-C 采用“Gateway protocol 为 canonical，SDK 不再本地定义同名 Protocol”的方案：

- `packages/graph-agent/src/graph_agent/core/phase_nodes/base.py` 删除本地 `ModelResolverProtocol` 定义，改为 `from graph_agent_gateway.protocol import ModelResolverProtocol`。
- `packages/graph-agent/src/graph_agent/core/phase_nodes/__init__.py` 继续可 re-export `ModelResolverProtocol` 供现有 SDK 内部 import 过渡，但来源必须是 Gateway protocol，不是本地第二套。
- Gateway `ModelResolverProtocol` 增加：

```python
def get_role_prefix(self, role_name: str | None = None) -> str:
    """Return system_prompt_prefix for one logical role; empty string when unset."""
```

- `ModelResolver` 实现 `get_role_prefix()`，基于当前/热加载后的 `RolesData.roles[role_name].system_prompt_prefix`；未知 role 的错误域归 Gateway。
- `ModelResolverProtocol.resolve()` 维持现有签名兼容，见 `packages/graph-agent-gateway/src/graph_agent_gateway/protocol.py:14-24`。

Tests-first 红灯：

- Gateway protocol signature test 增加 `get_role_prefix`。
- SDK phase node base 不能再定义本地 `class ModelResolverProtocol`。
- `isinstance(ModelResolver(...), ModelResolverProtocol)` 为真。
- Fake resolver fixtures 必须实现 `get_role_prefix` 或由 tests 显式说明空 prefix。

## §3 SDK Rewire

### §3.1 cognitive/prompt.py 去全局配置

现状：

- `packages/graph-agent/src/graph_agent/cognitive/prompt.py` 直接 import `get_role_config`：`packages/graph-agent/src/graph_agent/cognitive/prompt.py:17`。
- `resolve_role_prefix_from_llm_role()` 调 `get_role_config().resolve_role(llm_role).system_prompt_prefix`：`packages/graph-agent/src/graph_agent/cognitive/prompt.py:28-40`。
- SDK tests 直接 patch `get_role_config`：`packages/graph-agent/tests/cognitive/test_prompt.py:31`。

PR-C 后：

- `cognitive/prompt.py` 不 import Gateway concrete resolver，也不 import SDK config。
- 保留纯 prompt formatter `apply_cognitive_template()` / `apply_v030_cognitive_template()` 接收 `role_prefix: str`；它们已经有参数：`packages/graph-agent/src/graph_agent/cognitive/prompt.py:51-58`、`packages/graph-agent/src/graph_agent/cognitive/prompt.py:132-147`。
- 删除或重写 `resolve_role_prefix_from_llm_role()`；如保留 helper，只允许传入 `model_resolver` 参数：`resolve_role_prefix_from_llm_role(llm_role, model_resolver)`，内部调用 `model_resolver.get_role_prefix(llm_role)`。
- 不允许 helper 内部 fallback 到 SDK `get_role_config()`。

### §3.2 LLMPhaseNode role_prefix 改为 resolver 注入

现状：

- `LLMPhaseNode._resolved_tracing_model()` 已从 `self.container.resolver` 调 `resolve()`：`packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py:171-178`。
- 但 `_role_prefix_for_phase()` 仍调用全局 helper：`packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py:473-482`。

PR-C 后：

- `_role_prefix_for_phase(phase, resolver)` 从 `phase.llm_role or phase.tier or "balanced"` 得到 role，再调用 `resolver.get_role_prefix(role)`。
- 缺 resolver 时继续抛 Gateway resolver missing error；现有缺 resolver 路径在 `packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py:133-137`。
- `LLMPhaseNode.execute()` 中 role prefix 与 model resolve 使用同一个 `self.container.resolver`，避免 compile/run 使用不同配置。

### §3.3 graph_assembler compile-time role_prefix

现状：

- `assemble_graph()` 签名没有 `model_resolver`，只接收 `chat_model`：`packages/graph-agent/src/graph_agent/core/graph_assembler.py:90-99`。
- `_agent_system_prompt()` 在组装期直接调用 `resolve_role_prefix_from_llm_role(phase_ast.llm_role)`：`packages/graph-agent/src/graph_agent/core/graph_assembler.py:639-665`。
- `_run_v030_skill_dict()` 在调用 `assemble_graph()` 时没有传 `model_resolver`：`packages/graph-agent/src/graph_agent/core/runner.py:347-353`。

设计决定：

- PR-C 采用 compile/assembly 期注入 resolver 的方案，不把 role prefix 延后到 LLM call runtime。原因：`_agent_system_prompt()` 在 `assemble_graph()` 构建 node closure 时已经生成 agent prompt，现有结构不是每次 LLM call 再查 prefix。
- `assemble_graph()` 增加 keyword-only `model_resolver: ModelResolverProtocol | None = None`。
- `_build_phase_node()`、`_build_skill_node()`、`_agent_system_prompt()`、subgraph / subagent assembly helper 全链路透传 `model_resolver`。
- `_agent_system_prompt()` 调 `model_resolver.get_role_prefix(phase_ast.llm_role)`；无 resolver 时返回空 prefix 只允许用于没有 LLM/Agent 模型依赖的测试 fixture，真实 run path 必须从 `run_skill` 传入。
- `_run_v030_skill_dict()` 调 `assemble_graph(..., model_resolver=model_resolver)`。
- 递归 subgraph assembly 必须同步透传，否则子图 role prefix 会回落旧全局读取。当前递归调用位于 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:279-286` 和 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:1000-1005`。
- `load_workflow_from_md()` 是 live/public 入口，当前只把 `chat_model`、`callbacks`、`skill_resolver` 传给 `assemble_graph()`，没有透传 `model_resolver`：`packages/graph-agent/src/graph_agent/core/loader.py:294-303`。PR-C 必须把这里纳入透传清单，否则通过 loader 入口组装的 workflow 会静默丢 role prefix，违反黄金原则。
- `tools/builtin/parallel_map.py` 每个子运行会 fresh `run_skill()`：`packages/graph-agent/src/graph_agent/tools/builtin/parallel_map.py:12-14`、`packages/graph-agent/src/graph_agent/tools/builtin/parallel_map.py:306-313`。PR-C 需要把 parent resolver 或等价 provider 注入能力透传到子运行，避免 fan-out 子 skill role prefix 与父 run 配置脱节。

Tests-first 红灯：

- `graph_assembler.py` 不再 import `resolve_role_prefix_from_llm_role`。
- `assemble_graph()` 签名包含 `model_resolver`。
- root graph、subgraph、subagent 内的 agent prompt 均调用同一个 fake resolver 的 `get_role_prefix()`。
- `load_workflow_from_md(..., model_resolver=fake)` 经 `assemble_graph()` 生成的 agent prompt 也调用同一个 fake resolver 的 `get_role_prefix()`。
- 删除 SDK 全局 `get_role_config` 后，V0.3 agent prompt assembly 仍包含 role prefix。

### §3.4 run_skill 注入链

现状：

- `run_skill()` 已接收 `model_resolver` 并传给 `_run_skill_dict()`：`packages/graph-agent/src/graph_agent/core/runner.py:61-99`。
- `_run_skill_dict()` 继续传给 `_run_v030_skill_dict()`：`packages/graph-agent/src/graph_agent/core/runner.py:141-194`。
- `_run_v030_skill_dict()` 当前先用 `model_resolver.resolve(...phase_name="<workflow>")` 得到 workflow chat model，再 assemble graph：`packages/graph-agent/src/graph_agent/core/runner.py:316-353`。

PR-C 后：

- 现有 run path 继续是 SDK 消费 Gateway resolver 的主入口。
- `_run_v030_skill_dict()` 必须同时把 resolver 交给 graph assembly，用于 role prefix。
- SDK 不再自己读取 Studio settings、provider API key、role config。

## §4 Gateway resolver 行为

### §4.1 resolve / resolve_role / resolve_model

当前 `_resolve_role()` 内部已能根据 role/model_override 产出 `ResolvedRole`，并设置 `system_prompt_prefix`：`packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:100-125`、`packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:151-205`。

PR-C 后：

- 将当前返回三元组的 `_resolve_role(role_name, model_override) -> tuple[ResolvedRole, float, int]` 拆出 public `resolve_role(role_name: str | None = None) -> ResolvedRole` 与 `resolve_model(model_code: str) -> ResolvedRole`，但必须保留内部三元组路径用于 `resolve()` 构造 chat model。现状 `resolve()` 依赖 `resolved, temperature, max_tokens = self._resolve_role(...)`：`packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:62-65`，并把 `temperature` / `max_tokens` 传给 `GatewayChatModel` 或 `PredictGatewayChatModel`：`packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:76-97`。
- 内部 helper 可命名为 `_resolve_role_runtime(...) -> tuple[ResolvedRole, float, int]`；public `resolve_role()` / `resolve_model()` 只返回 `ResolvedRole`。不能为了公开 API 简化而丢失 `role_model.temperature`、`role.temperature`、provider/model/role `max_tokens` 计算路径；当前计算在 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:151-169`，三元组返回在 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:197-205`。
- `resolve()` 调用内部三元组 helper 后构造 `GatewayChatModel`。
- `get_role_prefix()` 可调用 `resolve_role()` 或直接读 role entry，但必须经过热加载刷新。
- `GatewayRoleNotConfiguredError` 覆盖未知 role/model_override。
- `ResolvedRole.system_prompt_prefix` 是 Gateway public contract，不是 SDK 内部字段。

### §4.2 fallback / 熔断 / runtime

当前 `GatewayChatModel._generate()` 在 candidate chain 上执行 probe、dispatch、mark down、fallback event、all providers failed：`packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:92-159`。默认 manager 仍反向 import SDK：`packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:240-293`。

PR-C 后：

- `GatewayChatModel` 使用 Gateway 本地 `LLMClientManager`。
- `LLMClientManager` 使用 Gateway `ResolvedProvider`，并保留 client cache、usage stats、provider down cache、probe、dispatch、token escalation、API key env 解析。
- 所有 provider/model/role 错误归 Gateway error domain。

### §4.3 Gateway exceptions 解耦

现状 Gateway exceptions 尝试 import SDK `ModelProviderError`，失败 fallback 到 `RuntimeError`：`packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:7-10`；但 `GatewayError.__init__()` 无条件调用 `super(..., context=...)`，standalone fallback 到 `RuntimeError` 时存在 `context` kwarg 风险：`packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:13-27`。

PR-C 后：

- Gateway exceptions 不得 import SDK error family。
- Gateway 自己定义 `GatewayError(Exception)` base，保留 `.code` / `.context`。
- SDK boundary 如需映射到 SDK `ModelProviderError`，由 SDK 捕获 Gateway error 并包装/转 payload，不让 Gateway 反向依赖 SDK。
- `AllProvidersFailedError`、`GatewayResolverMissingError`、`GatewayRoleNotConfiguredError` 继续作为 Gateway public errors。

## §5 Studio Cutover

### §5.1 Copilot provider 检视改 Gateway

现状：

- Studio Copilot import SDK `ProviderDef` / `ResolvedProvider` / `load_config`：`apps/studio/backend/app/services/copilot.py:36`。
- `_resolve_copilot_provider()` 调 `load_config().resolve_model()` 或 `load_config().resolve_role("copilot_chat")`：`apps/studio/backend/app/services/copilot.py:370-379`。

PR-C 后：

- `copilot.py` 改 import Gateway `ProviderDef` / `ResolvedProvider` / `ModelResolver` 或调用 `build_gateway_model_resolver()`。
- `_resolve_copilot_provider()` 使用 Gateway resolver public `resolve_model()` / `resolve_role()`，返回 `ResolvedProvider`。
- `_resolve_provider_runtime()` 保持 Studio credential lookup 业务逻辑在 Studio；Gateway 不 import Studio models/services。

### §5.2 Studio resolver builder

现状：

- `build_gateway_model_resolver()` 从 Studio `llm_roles.load_roles_file()` 转成 Gateway `RolesData`，再 `ModelResolver(roles_data=...)`：`apps/studio/backend/app/services/gateway_resolver.py:7-23`。
- Run path 已注入 resolver：`apps/studio/backend/app/services/run_manager.py:56`、`apps/studio/backend/app/services/run_manager.py:237`。
- Predict path 已注入 resolver：`apps/studio/backend/app/services/predictor.py:32`、`apps/studio/backend/app/services/predictor.py:78`。

PR-C 后：

- Builder 可继续负责 Studio persisted roles -> Gateway resolver，但 schema 类型以 Gateway 为准。
- Settings / LLM roles / Copilot tests 的 SDK config imports 全部 cutover 到 Gateway entry。
- 不允许 Studio 同时 import `graph_agent.config.llm_config` 与 `graph_agent_gateway.llm_config`。

## §6 冻结契约对齐清单

这些变更属于 decisions §1/§6 已批的 A 类 [BREAKING] cutover，不需要停下来问 PM；但治理必须同步：feature map / public API docs / contract hash / exemption 证据随 PR-C 更新。

### §6.1 feature-compliance-checklist

`docs/engine/feature-compliance-checklist.md` 当前仍把 LLM execution / model configuration 锚在 SDK：

- `F-llm-execution` core path 指向 `packages/graph-agent/src/graph_agent/models/__init__.py`：`docs/engine/feature-compliance-checklist.md:139-144`。
- `F-model-configuration` core paths 指向 `packages/graph-agent/src/graph_agent/config/llm_config.py` 与 `packages/graph-agent/src/graph_agent/models/llm_client_manager.py`：`docs/engine/feature-compliance-checklist.md:195-200`。

PR-C 后 re-anchor：

- `F-llm-execution` core path 指向 Gateway `gateway_chat_model.py` / `llm_client_manager.py` / `resolver.py`。
- `F-model-configuration` core path 指向 Gateway `llm_config.py` / config loader / `resolver.py`。
- Coverage 指向 Gateway tests。

### §6.2 features.yaml

`packages/graph-agent/spec/features.yaml` 当前冻结位置：

- `F-llm-execution` 在 `packages/graph-agent/spec/features.yaml:529-545`，core path 仍是 SDK `models/__init__.py`：`packages/graph-agent/spec/features.yaml:538-539`。
- `F-model-configuration` 在 `packages/graph-agent/spec/features.yaml:701-715`，core paths 仍是 SDK `config/llm_config.py` 与 `models/llm_client_manager.py`：`packages/graph-agent/spec/features.yaml:710-712`。

PR-C 后：

- 更新 source-map core paths 到 Gateway。
- 更新 targeted tests 到 Gateway package tests。
- 如 round28 invariant guard 需要 schema hash 重锁，PR-C 同步走治理流程。

### §6.3 public-api-contract.md

`docs/engine/public-api-contract.md` 当前冻结 4 个 SDK LLM symbols：

- `LLMClientManager` 来源 `graph_agent.models.llm_client_manager`，消费者为 Gateway lazy import：`docs/engine/public-api-contract.md:436-444`。
- `ProviderDef` 来源 `graph_agent.config.llm_config`，消费者为 Studio Copilot：`docs/engine/public-api-contract.md:573-581`。
- `ResolvedProvider` 来源 `graph_agent.config.llm_config`，消费者为 Studio Copilot：`docs/engine/public-api-contract.md:583-590`。
- `load_config` 来源 `graph_agent.config.llm_config`，消费者为 Studio Copilot：`docs/engine/public-api-contract.md:695-703`。

PR-C 后：

- `LLMClientManager` 从 SDK public/known external contract 删除或 repoint 到 `graph_agent_gateway.llm_client_manager.LLMClientManager`。
- `ProviderDef` / `ResolvedProvider` repoint 到 `graph_agent_gateway.llm_config`。
- `load_config` 不作为 Gateway public singleton 入口保留；迁移路径写为 `ModelResolver(roles_path=...).resolve_role()` / `.resolve_model()` / `.get_role_prefix()`。
- 标记 A 类 [BREAKING]，指向 decisions §1/§6。

## §7 测试迁移清单

### §7.1 删除/迁移 SDK config tests

以下 tests 当前直接 import SDK `graph_agent.config.llm_config`，PR-C 后删除或迁到 Gateway tests：

- `packages/graph-agent/tests/config/test_llm_config.py` import `_parse_models`：`packages/graph-agent/tests/config/test_llm_config.py:1-5`。
- `packages/graph-agent/tests/config/test_llm_config_characterization.py` import `ModelDef/ProviderDef/RoleDef/RoleModelEntry/_validate_cross_references`：`packages/graph-agent/tests/config/test_llm_config_characterization.py:1-9`。
- `packages/graph-agent/tests/config/test_llm_config_resolve_role.py` import SDK model/provider/role config classes：`packages/graph-agent/tests/config/test_llm_config_resolve_role.py:1-13`。

Gateway 新测试覆盖：

- yaml loader 顶层非 dict / missing refs / role active_model / provider mapping error。
- `resolve_role()` active model first + declared fallback order。
- `resolve_model()` provider chain。
- `get_role_prefix()` known role / unknown role / empty prefix。
- 热加载 mtime + lock + failed reload fallback。

### §7.2 LLMClientManager tests 迁移

现状：

- `packages/graph-agent/tests/models/test_llm_client_manager.py` import SDK config + SDK `LLMClientManager`：`packages/graph-agent/tests/models/test_llm_client_manager.py:11-12`。
- tests patch 旧模块路径 `graph_agent.models.llm_client_manager.httpx.post` / `time.sleep`：`packages/graph-agent/tests/models/test_llm_client_manager.py:505-516`。

PR-C 后：

- 迁到 `packages/graph-agent-gateway/tests/test_llm_client_manager.py` 或等价 Gateway tests。
- patch 路径改为 `graph_agent_gateway.llm_client_manager.httpx.post` / `time.sleep`。
- 覆盖 client cache、probe、mark down TTL、usage stats、openai/anthropic/wavespeed dispatch、token escalation。

### §7.3 Gateway resolver/chat model tests

现有 Gateway tests：

- `test_model_resolver_protocol.py` 覆盖 protocol 签名和 SDK 注入点：`packages/graph-agent-gateway/tests/test_model_resolver_protocol.py:25-85`。
- `test_gateway_integration.py` 覆盖 resolver 参数与 fallback error：`packages/graph-agent-gateway/tests/test_gateway_integration.py:37-89`。

PR-C 后补充：

- Gateway package import 不依赖 SDK `graph_agent.models.llm_client_manager`。
- `GatewayChatModel` 默认 manager 来自 Gateway。
- `ModelResolver.resolve_role()` / `resolve_model()` / `get_role_prefix()` public API tests。
- Gateway standalone import exceptions 不需要 SDK。

### §7.4 SDK public API contract tests

`packages/graph-agent/tests/test_public_api_contract.py` 当前把 `LLMClientManager`、`ProviderDef`、`ResolvedProvider`、`load_config` 作为 known missing vendor-only symbols 或 expected signatures：`packages/graph-agent/tests/test_public_api_contract.py:55-82`、`packages/graph-agent/tests/test_public_api_contract.py:197-213`、`packages/graph-agent/tests/test_public_api_contract.py:259-263`、`packages/graph-agent/tests/test_public_api_contract.py:533-550`。

PR-C 后：

- SDK contract red light：这些 SDK symbol 不再可 import。
- Gateway contract tests 增加这些 Gateway public nouns。
- `graph_agent.__all__` 不新增 Gateway concrete classes。

### §7.5 Studio Copilot tests

现状：

- `apps/studio/backend/tests/routers/test_copilot_ws_endpoint.py` import SDK `ModelDef/ProviderDef/ResolvedProvider/ResolvedRole`：`apps/studio/backend/tests/routers/test_copilot_ws_endpoint.py:18-23`。
- 多处 patch `copilot_service.load_config`：`apps/studio/backend/tests/routers/test_copilot_ws_endpoint.py:150-157`、`apps/studio/backend/tests/routers/test_copilot_ws_endpoint.py:188-193`、`apps/studio/backend/tests/routers/test_copilot_ws_endpoint.py:228-232`。

PR-C 后：

- fake config 改为 fake Gateway resolver 或 patch `build_gateway_model_resolver()`。
- 类型 import 改 Gateway `graph_agent_gateway.llm_config`。
- 覆盖 no override -> `resolve_role("copilot_chat")`、model override -> `resolve_model(model_code)`、missing provider credentials error。

### §7.6 PR-E 边界测试不在 PR-C 改

`packages/graph-agent/tests/core/test_predict_internal_imports.py` 当前验证 Gateway resolver 绑定 predict strategy 后返回 SDK `PredictGatewayChatModel`：`packages/graph-agent/tests/core/test_predict_internal_imports.py:94-118`。`tasks.md` §6 PR-E 明确 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:74` 是 PR-E 影响点：`.kiro/specs/engine-mvp0-rebuild-v030/round-31-api-surface-rightsizing/tasks.md:305-314`。

PR-C 不改这条 predict mock 反向 import 测试；除非 PR-C 为了搬 client manager 需要调整 imports，不能改变 predict mock 归属。

### §7.7 live/public 入口 role prefix 透传红灯

PR-C 必须补齐 loader 与 parallel_map 的 role prefix 透传红灯，避免只覆盖 `run_skill()` 主路径而漏 live/public 入口：

- `load_workflow_from_md(..., model_resolver=fake)` 必须把 resolver 继续传给 `assemble_graph()`；当前入口在 `packages/graph-agent/src/graph_agent/core/loader.py:268-303`，只在 `packages/graph-agent/src/graph_agent/core/loader.py:294-303` 解析 `chat_model` 并调用 `assemble_graph(..., chat_model=chat_model, callbacks=callbacks, skill_resolver=resolver)`。
- `parallel_map()` / `_submit_parallel_map_items()` / `_run_one_item()` / `run_skill()` 子运行链路必须有 parent resolver 或等价 provider 注入能力；当前 `parallel_map()` 签名无 `model_resolver` 参数：`packages/graph-agent/src/graph_agent/tools/builtin/parallel_map.py:43-54`，submit/worker 只传 `skill_resolver`：`packages/graph-agent/src/graph_agent/tools/builtin/parallel_map.py:218-244`、`packages/graph-agent/src/graph_agent/tools/builtin/parallel_map.py:275-313`。
- 红灯应证明 parallel_map 子 skill 的 agent prompt 使用同一个 fake resolver 的 `get_role_prefix()`，而不是回落 SDK 全局 config 或空 prefix。

## §8 切法顺序

PR-C 在一个 PR 内完成，一刀切不保留双栈；但提交内实现顺序按以下步骤控制断链。

### Step 1: Gateway 地基补齐

- 在 Gateway 建立唯一 schema/public noun：`ProviderDef`、`ResolvedProvider`、`ResolvedRole`、`RolesData`。
- 新增 Gateway `llm_client_manager.py`，从 SDK 搬 `LLMClientManager` 并改为 Gateway schema 类型。
- Gateway `pyproject.toml` 增加 `httpx/openai/anthropic/pyyaml` 依赖。
- 新增 Gateway loader/validator/热加载内部入口，但不暴露全局 singleton。

断链检查：

- `import graph_agent_gateway` 不需要 SDK provider runtime。
- Gateway tests 能直接构造 `ModelResolver(roles_data=...)` 和 `LLMClientManager`。

### Step 2: Gateway concrete self-contained

- `resolver.py:229` 改 Gateway 本地 `LLMClientManager`。
- `gateway_chat_model.py:241` 改 Gateway 本地 `LLMClientManager`。
- `exceptions.py:7-27` 去 SDK error family import 与 `RuntimeError(context=)` 风险。
- 保留 `resolver.py:74` PredictGatewayChatModel 反向 import，标注 PR-E scope，不在 PR-C 改。

断链检查：

- Gateway resolver/chat model 不再 import `graph_agent.models.llm_client_manager`。
- Gateway exceptions standalone import 成功。

### Step 3: Protocol + SDK rewire

- Gateway protocol 加 `get_role_prefix()`。
- SDK phase_nodes/base 改用 Gateway protocol，不再定义第二份同名 protocol。
- `LLMPhaseNode` role prefix 改从 resolver 注入。
- `assemble_graph()` 全链路加 `model_resolver` 参数，root/subgraph/subagent assembly 都透传。
- `cognitive/prompt.py` 删除全局 config 读取。

断链检查：

- `rg "graph_agent.config.llm_config" packages/graph-agent/src` 无结果。
- root graph 和 subgraph prompt prefix 都来自 fake resolver。

### Step 4: Studio cutover

- `apps/studio/backend/app/services/copilot.py:36` 改 Gateway imports。
- `_resolve_copilot_provider()` 改用 Gateway resolver public `resolve_role()` / `resolve_model()`。
- Settings / LLM roles / tests 不再 import SDK config。

断链检查：

- `rg "graph_agent.config.llm_config" apps/studio/backend` 无结果。
- Studio run/predict 继续通过 `build_gateway_model_resolver()` 注入。

### Step 5: Tests + frozen contracts cutover

- 旧 SDK config/client manager/public API 快照 tests 删除或重写。
- Gateway tests 增加 loader/validator/hot reload/resolver/client manager/standalone error coverage。
- 更新 `docs/engine/feature-compliance-checklist.md`、`packages/graph-agent/spec/features.yaml`、`docs/engine/public-api-contract.md` 的 A 类 [BREAKING] re-anchor 与治理证据。

断链检查：

- SDK public/API contract 不再暴露 `load_config` / `LLMClientManager` / SDK `ProviderDef` / SDK `ResolvedProvider`。
- Gateway public contract 覆盖 Gateway nouns。

## §9 风险与边界

### §9.1 Data race

热加载必须用 dedicated lock。现 SDK `_RoleConfigHolder` 已用 lock + mtime + 上次有效配置 fallback：`packages/graph-agent/src/graph_agent/config/llm_config.py:678-735`。Gateway 需要等价语义；只用当前 `_stats_lock` 不足，因为它只保护 `stats.total_resolves`：`packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:46-61`。

### §9.2 Provider 检视能力不能丢

a2 “不长全局 load_config/get_role_config” 只禁止全局单例入口，不是砍掉 `resolve_role` / `resolve_model` 能力。Studio Copilot 当前依赖该能力：`apps/studio/backend/app/services/copilot.py:370-399`。PR-C 必须通过 Gateway resolver public API 保留。

### §9.3 Two Protocol drift

两份 `ModelResolverProtocol` 是实际风险：Gateway 在 `packages/graph-agent-gateway/src/graph_agent_gateway/protocol.py:10`，SDK 在 `packages/graph-agent/src/graph_agent/core/phase_nodes/base.py:41`。PR-C 必须统一来源，否则 `get_role_prefix()` 只改一边会留下假绿。

### §9.4 Predict mock 越界

a2 step2 原本建议清理 `resolver.py:74` 对 SDK `PredictGatewayChatModel` 的依赖；收敛后这项退回 PR-E。PR-C 只解 client manager 和 exceptions 反向依赖，不改 predict mock 行为。PR-E 影响点明确列 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:74`：`.kiro/specs/engine-mvp0-rebuild-v030/round-31-api-surface-rightsizing/tasks.md:313`。

### §9.5 API 快照与治理工作量

SDK public API contract 和 feature map 仍冻结旧 LLM 符号，见 §6 / §7。PR-C 是 A 类 [BREAKING]，不停下来问 PM，但必须同步治理文件，否则 contract hash / invariant guard 会把实现打回。

### §9.6 Standalone Gateway

Gateway 当前有多处依赖 SDK 才能完整工作：client manager lazy import、exceptions import SDK error family、predict mock reverse import。PR-C 只解除 client manager 与 exceptions 两项；predict mock reverse import 留 PR-E。设计上 Gateway package import 必须 standalone；predict mock 例外需在 PR-E 前作为已知边界记录。

## §10 PR-C 完成定义

PR-C 完成时必须同时满足：

- `rg "graph_agent.config.llm_config" packages/graph-agent/src apps/studio/backend/app` 无结果。
- `rg "graph_agent.models.llm_client_manager" packages/graph-agent-gateway/src` 无结果。
- Gateway exports/contract 覆盖 `ProviderDef`、`ResolvedProvider`、`ResolvedRole`、`ModelResolver`、`ModelResolverProtocol`、Gateway `LLMClientManager`。
- SDK graph assembly 和 LLM phase runtime 的 role prefix 均来自 injected resolver。
- Studio Copilot provider 检视走 Gateway resolver。
- SDK old config tests 已删除或迁 Gateway；Gateway loader/validator/hot reload/client manager tests 覆盖通过。
- 冻结契约三件套完成 A 类 [BREAKING] re-anchor：`docs/engine/feature-compliance-checklist.md`、`packages/graph-agent/spec/features.yaml`、`docs/engine/public-api-contract.md`。
- `resolver.py:74` Predict mock reverse import 未被 PR-C 顺手改掉，作为 PR-E scope 保留。
