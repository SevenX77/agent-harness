# llm-routing (engine) — MVP0 Alignment (V0.3.0 目标对齐逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-21
> **Scope**: Q9 决策落地; engine 只认 ModelResolverProtocol; Studio 持有具体 ModelResolver; GatewayChatModel 负责 fallback; V0.3.0 版本号 cutover
> **改造目标 engine 版本**: V0.3.0 (MVP0 落地后, 详见 [INDEX.md#engine-版本号约定-2026-05-21-pm-拍定](../../INDEX.md#engine-版本号约定-2026-05-21-pm-拍定))
> **配套**: 见 [INDEX.md](../../INDEX.md) 三时态模板 + cross-link 规则 + writing conventions。

## UI/UX

N/A — engine LLM routing 本身不新增前端 UI。

MVP0 后，Studio 的 LLM 配置仍由 Studio UI / backend 管理。engine 只消费一个 resolver 接口，不读取 Studio 页面状态，也不直接读用户 provider credential。

对用户可见的变化是：点击运行 V0.3.0 skill 时，`llm_role: analyst` 这类声明会走 Studio 的 routing 配置拿到真实模型，而不是只能靠 `mock_llm`。

## 前端逻辑

N/A — React 不直接实例化 resolver。

前端仍通过 Studio 后端触发运行。Studio 后端在 dispatch 前读取 roles 配置、credentials 和 provider 状态，实例化具体 resolver，再把 resolver 交给 engine。

## 后端功能

### 1. 主决策：engine 只暴露 ModelResolverProtocol

Q9 的主决策是：engine 只认 `ModelResolverProtocol`。Protocol 应放在 engine core 层，例如 `packages/graph-agent/src/graph_agent/core/model_resolver_protocol.py`。

现有旧 phase node 里已有一个同名思想的内部 Protocol：`ModelResolverProtocol` 定义在 `packages/graph-agent/src/graph_agent/core/phase_nodes/base.py:41`，`PhaseExecutor` 当前也引用它，见 `packages/graph-agent/src/graph_agent/core/phase_executor.py:46` 和 `packages/graph-agent/src/graph_agent/core/phase_executor.py:73`。

MVP0 不应复用 old phase_nodes 的 private 位置作为 V0.3.0 public engine contract。应抽到 core 独立文件，供 runner / graph_assembler / tests 引用。

Protocol 最小语义：接收 role name、phase name、callbacks、thinking / model override 等上下文，返回 LangChain `BaseChatModel` 或等价 chat model。engine 不关心它怎么查配置、怎么拿 API key、怎么选 provider。

### 2. 具体 ModelResolver 物理移出 graph-agent

当前 `ModelResolver` 在 `packages/graph-agent/src/graph_agent/models/resolver.py:43`，它直接读取 `llm_roles.yaml`，import `get_role_config()` 的位置是 `packages/graph-agent/src/graph_agent/models/resolver.py:21` 到 `packages/graph-agent/src/graph_agent/models/resolver.py:26`。

MVP0 WILL 把具体 `ModelResolver` 物理移出 graph-agent，目标位置按 PM 拍板为 `apps/studio/backend/services/model_resolver.py` 或同等 Studio backend service 路径。

原因：具体 resolver 需要知道 Studio 用户配置、provider credential、roles 文件位置和运行环境。这些都属于 Studio 后端职责，不属于 engine 图执行职责。

迁移时保留语义，不保留 engine import 路径。`graph_agent.models.resolver.ModelResolver` 不再作为 engine public API 暴露。现有 `packages/graph-agent/src/graph_agent/models/__init__.py:6` 到 `packages/graph-agent/src/graph_agent/models/__init__.py:12` 的 resolver export 需要清理。

### 3. GatewayChatModel 留在 engine

建议 `GatewayChatModel` 留在 engine。它定义在 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:54`，职责是 LangChain `BaseChatModel` adapter，并在 `_generate()` 内按 call chain 做 fallback，见 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:115` 到 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:192`。

它和 `ModelResolver` 不同。`ModelResolver` 决定 role 绑定哪个 call chain；`GatewayChatModel` 是 runtime 调用模型的统一 wrapper。engine 执行 SKILL phase 时需要一个 LangChain-compatible chat model，这一层适合留在 engine。

`LLMClientManager` 当前在 `packages/graph-agent/src/graph_agent/models/llm_client_manager.py:42`，负责 provider SDK client cache、usage stats、provider-down TTL 和 provider dispatch。它被 `GatewayChatModel` 直接 import，见 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:32`。若 Gateway 留 engine，LLMClientManager 也应暂留 engine，避免把一个 chat model wrapper 拆成跨包调用。

长期如果 Studio 要完全拥有 provider SDK，也可以再拍第二阶段迁移；MVP0 按 Q9 优先切出 resolver 物理边界。

### 4. Fallback 收敛在 GatewayChatModel._generate

Q9 决策指定 fallback 收敛在 `GatewayChatModel._generate` 内。现状已经接近这个方向：`_generate()` 遍历 `resolved_role.call_chain`，跳过 down provider，probe provider，调用 provider，失败时 mark down 并发 fallback event，全部失败后抛错，代码在 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:127` 到 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:192`。

MVP0 SHOULD 保持这个职责，不把 fallback 分散到 runner、graph_assembler 或 Studio dispatch 外壳。Studio resolver 只负责生成候选链；具体某次调用哪个 provider 成功、哪个 provider 503、哪个 provider 被 mark down，应由 GatewayChatModel 在真实 `_generate()` 中决定。

这样 trace 语义也清楚：engine 看到一次 `chat_model.invoke()`。如果内部 fallback 成功，phase 成功；如果所有候选失败，才向 runtime 抛模型错误。

### 5. `_run_v21_skill_dict` 签名 cutover

当前 `_run_v21_skill_dict()` 签名使用 `mock_llm`，见 `packages/graph-agent/src/graph_agent/core/runner.py:451` 到 `packages/graph-agent/src/graph_agent/core/runner.py:459`。内部 `chat_model = None if mock_llm is _NO_MOCK_LLM else mock_llm`，见 `packages/graph-agent/src/graph_agent/core/runner.py:467`。

MVP0 WILL 把签名从 `mock_llm` cutover 为 `resolver: ModelResolverProtocol`。运行 SKILL phase 时，engine 根据 phase 的 `llm_role` 向 resolver 请求 chat model，再把 chat model 传入 graph assembly 或 phase runtime。

如果某次运行完全没有 SKILL phase，resolver 可以为 None 或 lazy unused；如果存在 SKILL phase 但 resolver 缺失，应抛结构化错误，而不是等到 `chat_model is None` 才抛裸 RuntimeError。

Predict / test 不再通过 `mock_llm` 伪装 chat model，而是提供 `MockModelResolver(ModelResolverProtocol)`。

### 6. Studio LLMRolesService 联通 resolver

Studio 现有 `llm_roles.py` 只做 YAML round-trip 和引用校验。读入口是 `apps/studio/backend/app/services/llm_roles.py:24`，写入口是 `apps/studio/backend/app/services/llm_roles.py:38`，引用校验在 `apps/studio/backend/app/services/llm_roles.py:56` 到 `apps/studio/backend/app/services/llm_roles.py:80`。

MVP0 WILL 在 Studio 后端 dispatch run_skill 前读取 roles 配置和 credentials，实例化 Studio 侧 `ModelResolver`，并把它作为 resolver 参数传给 engine。当前 predictor 仍用 `run_skill(..., mock_llm=mock_param)`，位置是 `apps/studio/backend/app/services/predictor.py:71` 到 `apps/studio/backend/app/services/predictor.py:73`，需要同步 cutover。

Studio 后端的 run manager 也直接调用 `run_skill`，入口附近在 `apps/studio/backend/app/services/run_manager.py:230`。这类 dispatch 点都要统一改成 resolver 注入。

### 7. test 全清重写

按 PM 决策，MVP0 test 全部重新写。旧测试围绕 `mock_llm`、`get_model_resolver()` singleton、engine 内部 `ModelResolver` 的假设都要清理。

新的测试分三层：

1. engine unit：`_run_v3_skill_dict` 或同等入口只依赖 `ModelResolverProtocol`，传入 `MockModelResolver` 能运行 SKILL phase。
2. gateway unit：GatewayChatModel fallback 在 `_generate()` 内完成，单 provider fail 不让 runtime 误判整 phase fail。
3. Studio backend unit/integration：LLMRolesService 读写配置，Studio ModelResolver 从 roles 配置构造 call chain，并被 run dispatch 注入 engine。

### 8. V0.3.0 版本号同步 cutover

cache dir 当前是 `~/.cache/graph-agent-v21`，位置在 `packages/graph-agent/src/graph_agent/core/cache.py:18` 到 `packages/graph-agent/src/graph_agent/core/cache.py:19`。MVP0 / V0.3.0 cutover 要同步改成 `~/.cache/graph-agent-v3`，避免旧 V2.1 编译缓存污染 V0.3.0 contract。

错误码前缀当前多为 `[F-v21-*]`。例如 SKILL phase 缺模型是 `[F-v21-graph]`，位置在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:233` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:234`。MVP0 要统一切成 `[F-v3-*]`。

## API

### Engine 新 Protocol

新增文件：

`packages/graph-agent/src/graph_agent/core/model_resolver_protocol.py`

拟定契约：

```python
from typing import Protocol, Any

class ModelResolverProtocol(Protocol):
    def resolve(
        self,
        role_name: str | None = None,
        *,
        phase_name: str | None = None,
        callbacks: tuple[Any, ...] = (),
        thinking_enabled: bool | None = None,
        model_override: str | None = None,
    ) -> Any: ...
```

返回类型可收敛到 LangChain `BaseChatModel`，但 Protocol 层不应 import Studio 类型。

### Runner cutover

旧入口：

`_run_v21_skill_dict(..., mock_llm=...)`，位置 `packages/graph-agent/src/graph_agent/core/runner.py:451`。

新入口：

`_run_v3_skill_dict(..., resolver: ModelResolverProtocol | None = None, ...)`

若仍保留函数名过渡，也必须把参数改成 resolver，不能再把 `mock_llm` 作为正式 public path。

### MockModelResolver

测试新增 `MockModelResolver(ModelResolverProtocol)`。它按 role 返回 fake chat model，替代 `mock_llm`。

Predict 模式如果还需要 golden/copilot/heuristic_stub，应通过 Predict 专用 resolver 或 resolver wrapper 注入，而不是复用 `mock_llm` 参数。

## Data Model / State

MVP0 后，engine LLM routing 的关键 state 不再是全局 singleton resolver，而是一次运行传入的 resolver 实例。

`GatewayChatModel` 仍持有 `role_name`、`resolved_role`、tool binding metadata，字段在 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:59` 到 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:69`。

`LLMClientManager` 仍持有进程级 client cache / usage stats / down cache，字段在 `packages/graph-agent/src/graph_agent/models/llm_client_manager.py:51` 到 `packages/graph-agent/src/graph_agent/models/llm_client_manager.py:53`。

Studio `ModelResolver` 持有 roles config、credential resolver 和 provider policy。它不应该住在 graph-agent package。

## Cross-feature interaction

和 execution-runtime 的关系：runtime 在执行 SKILL phase 时需要 chat model。当前 `assemble_graph()` 接收 `chat_model`，位置 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:55`。MVP0 要从“整图传一个 chat_model”升级到“按 phase role 通过 resolver 拿 chat model”。

和 tracing 的关系：fallback 在 Gateway 内部完成。单 provider fail 可以发 LLM fallback 事件，但不应该直接触发 phase EXCEPTION。所有 provider fail 后，runtime 才发 EXCEPTION。

和 Studio 配置的关系：Studio LLMRolesService 负责配置读写；Studio ModelResolver 负责把配置变成 call chain；engine GatewayChatModel 负责真正调用和 fallback。

和 skill-compilation 的关系：phase `SKILL.md` 里的 `llm_role` 属于编译产物的一部分。compile 不解析真实模型，只保留 role 声明；runtime 拿 role 去问 resolver。

## 迁移步骤

1. engine 新建 `packages/graph-agent/src/graph_agent/core/model_resolver_protocol.py`，定义 `ModelResolverProtocol`。
2. engine runner cutover：`_run_v21_skill_dict` / V3 runner 参数从 `mock_llm` 改为 `resolver: ModelResolverProtocol`。
3. graph assembly / SKILL node cutover：不再依赖单个 `chat_model` 覆盖整图，而是按 phase `llm_role` resolve。
4. `git mv packages/graph-agent/src/graph_agent/models/resolver.py apps/studio/backend/services/model_resolver.py`，并修 Studio import。
5. `gateway_chat_model.py` 和 `llm_client_manager.py` 暂留 engine；resolver 移 Studio。
6. Studio 后端 `LLMRolesService` 和新 `ModelResolver` 联通；dispatch run_skill 前实例化 resolver。
7. Predict 和测试入口改为 `MockModelResolver(ModelResolverProtocol)`。
8. 删除 graph-agent `models.__init__` 对 `ModelResolver` / `get_model_resolver` / `reset_model_resolver` 的 export。
9. cache dir `graph-agent-v21` 改 `graph-agent-v3`。
10. 错误码前缀 `[F-v21-*]` 改 `[F-v3-*]`。
11. 全量重写相关 tests，旧 `mock_llm` 测试不作为兼容目标保留。

## MVP0 死代码清退

本模块 cutover 后，engine 内部具体 `ModelResolver` 不再保留 deprecated alias。

需要清理：

- `packages/graph-agent/src/graph_agent/models/resolver.py` 从 engine 包移走。
- `packages/graph-agent/src/graph_agent/models/__init__.py` 的 resolver exports 清理。
- `packages/graph-agent/src/graph_agent/core/harness.py` 中旧 `get_model_resolver()` 依赖会随 execution-runtime harness 清退一起删除，当前 import 在 `packages/graph-agent/src/graph_agent/core/harness.py:49`。
- `runner.py` 中 Predict 绑定旧 resolver 的逻辑要改写；当前基于 harness `_resolver` 的绑定在 `packages/graph-agent/src/graph_agent/core/runner.py:346` 到 `packages/graph-agent/src/graph_agent/core/runner.py:389`，不适合 V3 resolver 注入模型。

