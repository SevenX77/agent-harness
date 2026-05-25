---
spec: engine-mvp0-rebuild-v030/round-9-PR-alpha-gateway-llm-roles
phase: PR α (Gateway + llm-roles Phase 1)
owner: a2 主笔 / a1 audit / 主控复核
依赖: PR #90 已 close, 新 branch feat/pr-alpha-gateway-llm-roles-phase1
后续: γ0 (契约补丁 14h) → PR β (middleware 34h) → γ1 (compile-schema 50h) → γ1.5 (preflight 38h) → γ2 (state-io 40h) → γ3 (cleanup 44h)
---

# PR α: Gateway & LLM-Roles Phase 1 Design

## §0.5 继承字段表 (Round 9 默认不动)
- **Engine `ModelResolverProtocol`**: 继承 `def resolve(role_name: str, thinking_enabled: bool, model_override: BaseChatModel | None, callbacks: Callbacks | None, phase_name: str, **kwargs) -> BaseChatModel` 的核心语义结构，不改变引擎侧调用方法。
- **`AllProvidersFailedError`**: 继承基础结构，仅扩展标准 payload 格式。
- **BREAKING CHANGE**: 删除 `RoleEntry.temperature` 顶层冗余字段，将其下推至 `RoleModelEntry.temperature`。此变更需包含自动迁移逻辑。

## §1 Gateway 抽独立 package 设计契约

### 1.1 物理目录布局
新建独立 Python Package：
```
packages/graph-agent-gateway/
├── pyproject.toml
├── src/
│   └── graph_agent_gateway/
│       ├── __init__.py
│       ├── exceptions.py       # AllProvidersFailedError
│       ├── models.py           # Provider SDK wrappers
│       ├── protocol.py         # ModelResolverProtocol 定义
│       └── resolver.py         # Concrete Resolver 实现
└── tests/
```

### 1.2 DI 与跨包 Boundary 契约
- **引擎侧 (graph-agent)**:
  - 核心执行流如 `run_skill` 以及 `graph_assembler` 必须显式接收 `model_resolver: ModelResolverProtocol` 参数。
  - `graph-agent` 的 `pyproject.toml` **不能**硬依赖 `graph-agent-gateway`（实现倒置依赖）。
- **Gateway 侧 (graph-agent-gateway)**:
  - 负责维护所有的 LangChain provider 依赖 (`langchain_openai`, `langchain_anthropic` 等)。
  - `ModelResolverProtocol` 被放置在 Gateway，Studio backend 从 Gateway 导入此协议并注入到 Engine 调用中。

### 1.3 错误 Payload 契约
`AllProvidersFailedError` 将升级为标准结构化错误，携带明确的 `provider_errors` 数组（例如：`[{"provider": "anthropic", "reason": "rate_limit"}, ...]`），保证 Studio 能展示完整的 Fallback 失败瀑布。

## §2 LLM-Roles Phase 1 Data 层设计契约

### 2.1 核心 Schema 重构
在 `llm_roles.yaml` 的数据模型定义中：
- 废除顶层全局 `temperature`。
- 在 `RoleModelEntry` 中新增 `temperature: Optional[float] = None` 与 `max_tokens: Optional[int] = None`。
- **自动迁移逻辑**: `llm_roles.yaml` 加载器会在初始化时，将遗留的顶层 `temperature` 自动向下拷贝到所有的 `RoleModelEntry` 内，并移除顶层键值。

### 2.2 ModelResolverProtocol 对接点
Gateway 中的 `resolver` 在接收到 Studio backend 传入的特定 Role 请求时，直接读取 `RoleModelEntry` 中配置的 `temperature` 和 `max_tokens` 参数，用于实例化 `ChatOpenAI` / `ChatAnthropic` 客户端，做到精准模型定制。

## §3 Test 覆盖矩阵

| 测试模块 | 测试类型 | 覆盖目标 | 依赖点 |
|---|---|---|---|
| `test_gateway_resolver.py` | Unit | 验证 Gateway 能正确将 RoleModelEntry 转化为具有对应 temp/max_tokens 的 ChatModel | LLM-Roles Data 层 |
| `test_gateway_fallback.py` | Unit | 模拟主 Provider 失败，验证 fallback 逻辑和 `AllProvidersFailedError` payload 结构 | Gateway exceptions |
| `test_role_migration.py` | Unit | 验证旧格式 `llm_roles.yaml` 顶层 temp 能正确下推并清理 | Studio Backend Config |
| `test_run_skill_di.py` | Integration | 验证 `run_skill` 注入 `ModelResolverProtocol` 后能正常驱动简单 Agent 循环 | Engine + Gateway |

## §4 边界划分 (不属于 PR α)
为确保 PR α 能够干净利落合入：
- ❌ **Middleware Runtime Refactor (PR β)**: 不包含关于 `CognitiveFlowMiddleware` 的改造，不处理全引擎级别的 trace schema 清扫。
- ❌ **Compile Schema (PR γ1)**: 不包含 `GRAPH.md` body XML 回归。
- ❌ **Preflight / Validator (PR γ1.5)**: **明确不在 α 实施**任何 DAG predict 期静态阻断或 Compile 期 LLM 提醒功能。同时明确 `[F-v3-graph-phase-name-mismatch]` 和 validator 相关的三个错误码属于后续环节，不应塞入 α。
- ❌ **State-IO / Cleanup (PR γ2 / γ3)**: 不包含 smart reducer，V2.1 残留代码清理。
- ❌ **Ambiguity Feedback**: 明确列为非目标，防止后续 audit 误判遗漏。e 期 LLM 提醒功能。
- ❌ **State-IO / Cleanup (PR γ2 / γ3)**: 不包含 smart reducer, isolation，以及 V2.1 残留代码清理。