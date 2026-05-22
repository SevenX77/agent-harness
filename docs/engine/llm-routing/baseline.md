# llm-routing (engine) — Baseline (当下代码实现逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-21
> **Scope**: V2.1 LLM role 解析、GatewayChatModel fallback、LLMClientManager provider 调用、Studio LLM roles round-trip 现状
> **配套**: 见 [INDEX.md](../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

Studio 侧已有 LLM roles 配置读写能力，但这不是 engine 内部 UI。Studio 后端的 roles 文件服务入口是 `apps/studio/backend/app/services/llm_roles.py:24` 的 `load_roles_file()` 和 `apps/studio/backend/app/services/llm_roles.py:38` 的 `save_roles_file()`。它们负责读写 `config/llm_roles.yaml`，并保留 YAML round-trip 信息。

当前 engine runtime 并不会因为用户在 Studio 配了 roles，就自动在 V2.1 `_run_v21_skill_dict()` 中解析真实模型。V2.1 runtime 只把 `mock_llm` 当作 `chat_model` 注入，代码在 `packages/graph-agent/src/graph_agent/core/runner.py:467` 到 `packages/graph-agent/src/graph_agent/core/runner.py:469`。

因此 UI 层现状可以概括为：Studio 能编辑 LLM roles 配置，但 V2.1 graph runner 的 public run path 还没把这份配置接成真实 model resolver。

## 前端逻辑

N/A — 本模块主要是 backend Python / Studio backend 服务逻辑。React 不直接实例化 `ModelResolver`、`GatewayChatModel` 或 provider SDK client。

前端能间接看到的东西是 roles 配置、provider 配置、模型选择、调用失败信息和 trace 中的 provider metadata。实际 provider fallback、token usage、provider down cache 都发生在 Python 后端。

## 后端功能

### V2.1 runner 的模型注入现状

V2.1 运行入口 `_run_v21_skill_dict()` 定义在 `packages/graph-agent/src/graph_agent/core/runner.py:451`。它的签名仍是 `mock_llm`，见 `packages/graph-agent/src/graph_agent/core/runner.py:454`。

它不会调用 `get_model_resolver()`，也不会读取 `llm_roles.yaml`。当前逻辑是：如果 `mock_llm` 没传，`chat_model = None`；如果传了，就把 `mock_llm` 当作 chat model，见 `packages/graph-agent/src/graph_agent/core/runner.py:467`。随后 `assemble_graph(compiled, chat_model=chat_model)`，见 `packages/graph-agent/src/graph_agent/core/runner.py:469`。

这就是 audit P0-1 的现状缺口：真实 LLM 没有被 public V2.1 runner 自动解析。SKILL phase 如果没有 chat model，会在 runtime 抛 `SKILL phase requires chat_model`，位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:233` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:234`。

### ModelResolver 现状

`ModelResolver` 定义在 `packages/graph-agent/src/graph_agent/models/resolver.py:43`。它的职责在文件头已经写清楚：读取 `llm_roles.yaml`，展开 role/model/provider fallback metadata，返回 LangChain-compatible `GatewayChatModel`，见 `packages/graph-agent/src/graph_agent/models/resolver.py:1` 到 `packages/graph-agent/src/graph_agent/models/resolver.py:7`。

`resolve()` 定义在 `packages/graph-agent/src/graph_agent/models/resolver.py:57` 到 `packages/graph-agent/src/graph_agent/models/resolver.py:66`。它接收 `role_name`、`thinking_enabled`、`model_override`、callbacks 和 `phase_name`。

resolver 通过 `get_role_config()` 读取配置，调用位置是 `packages/graph-agent/src/graph_agent/models/resolver.py:70`。然后 `_resolve_configured_role()` 解析 role 或 model override，调用位置是 `packages/graph-agent/src/graph_agent/models/resolver.py:71` 到 `packages/graph-agent/src/graph_agent/models/resolver.py:75`。

如果找不到配置，resolver 会走 `_fallback_to_minimal_factory()`，调用位置是 `packages/graph-agent/src/graph_agent/models/resolver.py:76` 到 `packages/graph-agent/src/graph_agent/models/resolver.py:81`，实现里动态 import `create_chat_model()`，见 `packages/graph-agent/src/graph_agent/models/resolver.py:221` 到 `packages/graph-agent/src/graph_agent/models/resolver.py:238`。

配置解析成功后，resolver 会追加 peer model fallback candidates，入口是 `packages/graph-agent/src/graph_agent/models/resolver.py:84` 到 `packages/graph-agent/src/graph_agent/models/resolver.py:89`，实现是 `packages/graph-agent/src/graph_agent/models/resolver.py:164` 到 `packages/graph-agent/src/graph_agent/models/resolver.py:215`。

最终非 Predict 模式返回 `GatewayChatModel`，代码在 `packages/graph-agent/src/graph_agent/models/resolver.py:117` 到 `packages/graph-agent/src/graph_agent/models/resolver.py:127`。Predict 模式会返回 `PredictGatewayChatModel`，代码在 `packages/graph-agent/src/graph_agent/models/resolver.py:100` 到 `packages/graph-agent/src/graph_agent/models/resolver.py:115`。

### GatewayChatModel 现状

`GatewayChatModel` 定义在 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:54`，继承 LangChain `BaseChatModel`，依赖 `ResolvedRole` 和 `LLMClientManager`。

它的 `_generate()` 是真实 fallback 主循环，定义在 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:115` 到 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:192`。它把 LangChain messages 转成 provider 请求消息，见 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:124`。

主循环遍历 `resolved_role.call_chain`，代码在 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:127`。如果 provider/model 已被 mark down，就跳过，见 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:129` 到 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:138`。

如果开启 probe，先调用 `LLMClientManager._probe_provider()`，失败后 mark down 并继续下一个候选，见 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:140` 到 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:147`。

真实调用发生在 `LLMClientManager._dispatch_provider_call()`，位置是 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:151` 到 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:166`。成功后记录 usage 并构造 `ChatResult`，见 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:167` 到 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:173`。

如果捕获 runtime failover 异常，Gateway 会 mark down 当前 provider，发 `LLMFallbackEvent`，然后继续下一个候选，见 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:174` 到 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:188`。所有候选都失败后抛 `RuntimeError`，见 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:189` 到 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:192`。

`bind_tools()` 返回携带 tool metadata 的 GatewayChatModel clone，定义在 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:194` 到 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:225`。这使它可以接入 SKILL phase 的 LangChain tool calling。

### LLMClientManager 现状

`LLMClientManager` 定义在 `packages/graph-agent/src/graph_agent/models/llm_client_manager.py:42`。它管理 SDK client cache、usage stats、provider-down TTL state，字段在 `packages/graph-agent/src/graph_agent/models/llm_client_manager.py:51` 到 `packages/graph-agent/src/graph_agent/models/llm_client_manager.py:56`。

OpenAI-compatible client 创建在 `packages/graph-agent/src/graph_agent/models/llm_client_manager.py:59` 到 `packages/graph-agent/src/graph_agent/models/llm_client_manager.py:101`；Anthropic-compatible client 创建在 `packages/graph-agent/src/graph_agent/models/llm_client_manager.py:103` 到 `packages/graph-agent/src/graph_agent/models/llm_client_manager.py:128`。

usage stats 的写入和读取分别在 `packages/graph-agent/src/graph_agent/models/llm_client_manager.py:143` 到 `packages/graph-agent/src/graph_agent/models/llm_client_manager.py:161`。

provider down cache 的 key、查询和 mark down 分别在 `packages/graph-agent/src/graph_agent/models/llm_client_manager.py:169`、`packages/graph-agent/src/graph_agent/models/llm_client_manager.py:174`、`packages/graph-agent/src/graph_agent/models/llm_client_manager.py:186`。

provider probe 支持 OpenAI-compatible、Anthropic-compatible 和 WaveSpeed any-llm 的不同策略，代码在 `packages/graph-agent/src/graph_agent/models/llm_client_manager.py:197` 到 `packages/graph-agent/src/graph_agent/models/llm_client_manager.py:250`。

provider 调用分发入口是 `_dispatch_provider_call()`，定义在 `packages/graph-agent/src/graph_agent/models/llm_client_manager.py:455` 到 `packages/graph-agent/src/graph_agent/models/llm_client_manager.py:519`。它根据 provider type 走 `_call_openai_compatible()`、`_call_anthropic_compatible()` 或 `_call_wavespeed_any_llm()`。

### Studio LLMRolesService 现状

Studio 后端的 roles service 当前主要是 YAML round-trip。`load_roles_file()` 读取文件、迁移 payload、Pydantic validate，并保存 raw/original snapshot，见 `apps/studio/backend/app/services/llm_roles.py:24` 到 `apps/studio/backend/app/services/llm_roles.py:35`。

`save_roles_file()` 会先 `validate_references(data)`，如果配置没变则保留原始文本，否则把模型、provider、role 写回 raw，再原子写文件，见 `apps/studio/backend/app/services/llm_roles.py:38` 到 `apps/studio/backend/app/services/llm_roles.py:47`。

引用校验在 `apps/studio/backend/app/services/llm_roles.py:56` 到 `apps/studio/backend/app/services/llm_roles.py:80`：role 的 active model 必须存在，role model 引用的 model 必须存在，provider 必须存在，并且 model 必须声明该 provider。

当前没有看到 Studio 后端在 dispatch `run_skill` 前实例化 `ModelResolver` 并传入 V2.1 runner。Studio predictor 仍通过 `run_skill(..., mock_llm=mock_param)` 调用，见 `apps/studio/backend/app/services/predictor.py:71` 到 `apps/studio/backend/app/services/predictor.py:73`。

## API

Engine 侧现状 API：

- `_run_v21_skill_dict(skill_root, *, mock_llm=..., trace_dir=None, thread_id=None, callbacks=None, **inputs)`，位置 `packages/graph-agent/src/graph_agent/core/runner.py:451` 到 `packages/graph-agent/src/graph_agent/core/runner.py:459`。
- `assemble_graph(compiled, *, chat_model=None, max_patch_attempts=3)`，位置 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:55` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:60`。
- `ModelResolver.resolve(...) -> BaseChatModel`，位置 `packages/graph-agent/src/graph_agent/models/resolver.py:57` 到 `packages/graph-agent/src/graph_agent/models/resolver.py:66`。
- `GatewayChatModel._generate(...) -> ChatResult`，位置 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:115` 到 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:121`。
- `LLMClientManager._dispatch_provider_call(...) -> CallResult`，位置 `packages/graph-agent/src/graph_agent/models/llm_client_manager.py:455` 到 `packages/graph-agent/src/graph_agent/models/llm_client_manager.py:465`。

Studio 侧现状 API：

- `load_roles_file(path) -> RolesData`，位置 `apps/studio/backend/app/services/llm_roles.py:24`。
- `save_roles_file(path, data) -> None`，位置 `apps/studio/backend/app/services/llm_roles.py:38`。
- `validate_references(data) -> None`，位置 `apps/studio/backend/app/services/llm_roles.py:56`。

## Data Model / State

`ResolvedRole` / `ResolvedProvider` 来自 `graph_agent.config.llm_config`，被 `ModelResolver` 读取并传给 `GatewayChatModel`，import 在 `packages/graph-agent/src/graph_agent/models/resolver.py:21` 到 `packages/graph-agent/src/graph_agent/models/resolver.py:26`。

`GatewayChatModel` 持有 `role_name`、`resolved_role`、`max_tokens`、`temperature`、`phase_name`、callbacks、tool metadata 等字段，定义在 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:59` 到 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:69`。

`LLMClientManager` 的 state 是进程级 class vars：SDK client cache、usage stats、provider down cache，定义在 `packages/graph-agent/src/graph_agent/models/llm_client_manager.py:51` 到 `packages/graph-agent/src/graph_agent/models/llm_client_manager.py:53`。

Studio roles service 的 `RolesData` 来自 `apps/studio/backend/app/models/llm_config.py`，service 在 `apps/studio/backend/app/services/llm_roles.py:14` import `RoleEntry` 和 `RolesData`。

## Cross-feature interaction

和 execution-runtime 的关系：V2.1 runtime 当前只接收一个 `chat_model`，入口在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:55`。SKILL phase 缺模型会失败，位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:233`。

和 tracing 的关系：Gateway fallback 会发 `LLMFallbackEvent`，构造位置是 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:273` 到 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:278`。但 V2.1 runner 当前删除 callbacks，见 `packages/graph-agent/src/graph_agent/core/runner.py:462`，所以 public V2.1 path 没有稳定把这些事件传给 trace。

和 Studio LLM 配置的关系：Studio 可以读写 roles 文件，但当前 ModelResolver 仍在 graph-agent 包内，且 V2.1 runner 不自动创建它。这就是 MVP0 Q9 要迁移的主要边界。

## 读代码主路径

1. 看 `_run_v21_skill_dict()`，确认 V2.1 runner 只认 `mock_llm`，位置 `packages/graph-agent/src/graph_agent/core/runner.py:451`。
2. 看 `assemble_graph()` 的 `chat_model` 参数如何传到 SKILL/SUBGRAPH/subagent，位置 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:55`、`packages/graph-agent/src/graph_agent/core/graph_assembler.py:141`、`packages/graph-agent/src/graph_agent/core/graph_assembler.py:177`。
3. 看 `ModelResolver.resolve()`，位置 `packages/graph-agent/src/graph_agent/models/resolver.py:57`。
4. 看 `GatewayChatModel._generate()`，位置 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:115`。
5. 看 `LLMClientManager._dispatch_provider_call()`，位置 `packages/graph-agent/src/graph_agent/models/llm_client_manager.py:455`。
6. 看 Studio `llm_roles.py` 的 round-trip 读写，位置 `apps/studio/backend/app/services/llm_roles.py:24` 和 `apps/studio/backend/app/services/llm_roles.py:38`。

