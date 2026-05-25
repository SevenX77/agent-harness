---
spec: engine-mvp0-rebuild-v030/round-9-PR-alpha-gateway-llm-roles
phase: PR α (Gateway + llm-roles Phase 1)
owner: a1 主笔 / a2 audit / 主控复核
工程量: 54h (6.75d) + audit/e2e/CI buffer 1.25d
依赖: PR #90 已 close, 新 branch feat/pr-alpha-gateway-llm-roles-phase1
后续: γ0 (契约补丁 14h) → PR β (middleware 34h) → γ1 (compile-schema 50h) → γ1.5 (preflight 38h) → γ2 (state-io 40h) → γ3 (cleanup 44h)
---

# PR α: Gateway + LLM Roles Phase 1 Tasks

## §0 Scope 和边界

PR α 只做两件底座事:

1. **Gateway 抽独立 package**: 从 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:54`、`models/resolver.py:43`、`config/llm_config.py:90`、`core/_predict_internal/interception.py:29`、`core/exceptions.py:256`、`core/phase_nodes/base.py:41` 相关 gateway 能力抽到 `packages/graph-agent-gateway/`, 并让 Engine 只消费 `ModelResolverProtocol`。
2. **LLM Roles Phase 1 data 层**: 按 `llm-roles-setting/tasks.md` Phase 1 完成 `RoleEntry.temperature` 删除、`RoleModelEntry.temperature/max_tokens` 新增、`llm_roles.yaml` 自动迁移、`ModelInfo.capabilities: dict[str, Any]` 和调用默认值回退。

明确不做:

- 不做 **γ0**: Agent AST/loader `exit_contract` 删除、validator 字段扩展、middleware order 契约补丁。
- 不做 **PR β**: `CognitiveFlowMiddleware` / 手写 ReAct loop 替换 / Agent semantic tracing 重构。
- 不做 **γ1**: compile-schema、GRAPH.md body XML、7 类 mention 静态校验补完。
- 不做 **γ1.5**: predict/preflight 阻断、compile 期 LLM 提醒、DAG 静态检查。
- 不做 **γ2**: StateMapper / state-io / subgraph isolation。
- 不做 **γ3**: V2.1 schema cleanup、全 engine trace/error contract 清扫。
- 不做 LLM Roles Phase 2-5 UI: 双栏布局、DND、Test Chain、Tauri shell 和人工 UI 验收属于后续或 PM 并行。
- 不整合 PR #90 整体分支; PR #90 已 close, 只允许 clean port 符合本 PR 范围的局部代码思路。

## §1 依赖图

```text
α1 package skeleton
  ├─> α2 ModelResolverProtocol DI
  │     ├─> α3 structured gateway failure
  │     └─> α4 fallback tracing alignment
  └─> α5 llm-roles Phase 1 data layer

α6 tests/docs/CI depends on α1-α5
```

可并行:

- α3 和 α4 在 α2 接口稳定后可并行。
- α5 可在 α1 package skeleton 后并行推进, 但最终 resolver 构造参数必须和 α2 汇合。

必须串行:

- α1 先于 α2, 因为协议和 import 边界先落地。
- α6 最后, 因为它负责测试矩阵、文档同步和 ship gate。

## §2 Task 列表

### α1 Gateway independent package extraction (10h)

**WHY**: `graph-agent` 当前直接拥有 provider SDK、role config 和 fallback runtime, 与 "Studio 注入, Engine 只跑图" 的 MVP0 边界冲突。独立 package 先切物理边界, 后续 DI 才有干净方向。

**WHAT**:

- 新建 `packages/graph-agent-gateway/pyproject.toml`。
- 新建 `packages/graph-agent-gateway/src/graph_agent_gateway/__init__.py`。
- 新建 `packages/graph-agent-gateway/src/graph_agent_gateway/protocol.py`。
- 新建 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py`。
- 新建 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py`。
- 新建 `packages/graph-agent-gateway/src/graph_agent_gateway/llm_config.py`。
- 新建 `packages/graph-agent-gateway/src/graph_agent_gateway/predict_interception.py`。
- 新建 `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py`。
- 调整引用点: `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:54`, `models/resolver.py:43`, `config/llm_config.py:90`, `_predict_internal/interception.py:29`, `core/exceptions.py:256`。

**HOW**:

- 先复制现有 gateway 运行面到新 package, 保留 public API 名称, 再让旧路径变成薄导入或被 engine import 替换。
- `graph-agent` 不能反向硬编码 concrete resolver; 只消费 protocol 和 `BaseChatModel` surface。
- Predict mock 保持不打真实 provider, 但物理位置跟随 gateway package, 避免 runtime 内部再次耦合 provider 细节。

### α2 ModelResolverProtocol DI and singleton cutover (10h)

**WHY**: `get_model_resolver()` singleton 位于 `packages/graph-agent/src/graph_agent/models/resolver.py:286`, `GraphAgentHarness` 仍可在 `core/harness.py:373` 生产路径隐式创建 resolver。MVP0 要求外部显式注入。

**WHAT**:

- 在 `graph_agent_gateway.protocol` 定义正式 `ModelResolverProtocol`。
- 协议签名覆盖 `role_name`, `thinking_enabled`, `model_override`, `callbacks`, `phase_name`, `**kwargs`, 对齐 `packages/graph-agent/src/graph_agent/models/resolver.py:57-66`。
- 修改 `run_skill` / graph assembly / Agent runtime 入口, 增加必填 `model_resolver`。
- 更新 `packages/graph-agent/src/graph_agent/core/phase_nodes/base.py:41` 的旧 protocol 声明或导入。
- 删除或隔离生产路径 `get_model_resolver()`; tests 只能显式 fake resolver。

**HOW**:

- 测试先写 "未传 model_resolver 且图含 LLM/Agent phase 时结构化失败"。
- 对不含 LLM/Agent phase 的纯 logic/builtin 图, 不要求 resolver。
- role 未命中、model_override 未命中不得 silent fallback 到 minimal factory; 默认报 gateway 结构化错误。

### α3 Structured gateway failure payload (6h)

**WHY**: 当前 `GatewayChatModel._generate()` 在 `gateway_chat_model.py:190` 抛纯文本 `RuntimeError`, Studio 只能截字符串。MVP0 error contract 要稳定 code 和 metadata。

**WHAT**:

- 升级 `AllProvidersFailedError` 或新增 gateway exception, source 起点为 `packages/graph-agent/src/graph_agent/core/exceptions.py:256`。
- 标准 payload 包含 `code`, `role_name`, `phase_name`, `failed_provider_codes`, `last_error_chain`, `message`, `context`。
- 错误码固定为 `[F-v3-gateway-all-providers-failed]`。
- resolver 缺失固定为 `[F-v3-gateway-resolver-missing]`。
- role/model 未注册固定为 `[F-v3-gateway-role-not-configured]`。

**HOW**:

- 在 fallback loop 中把每个 candidate 的 provider/model、异常类型、异常消息追加为结构化 item。
- 最终失败时抛结构化异常, 人类可读 message 只作为摘要, UI 判断只看 `code/context`。
- 更新 error-code spec 和 logic-explained 报告入口, 不引入旧 `[F-v21-*]` alias。

### α4 Fallback tracing alignment (6h)

**WHY**: gateway 当前在 `gateway_chat_model.py:263` 直接构造 `LLMFallbackEvent` 并遍历 callback, 与 V0.3.0 tracing 底座并行。PR α 只做 gateway fallback 事件归口, 不做 γ3 全 engine tracing cleanup。

**WHAT**:

- 保留 `packages/graph-agent/src/graph_agent/callbacks/events.py:240` 的 `LLMFallbackEvent` 语义字段。
- fallback payload 对齐 `phase_name`, `from_provider`, `to_provider`, `reason`, `code/context`。
- Predict mock 不产生真实 provider fallback event。
- callback 分发走统一 runtime/tracing callback adapter, 不在 gateway 内自建第二套 trace 文件格式。

**HOW**:

- 在 `_generate()` 捕获 provider failover 后仍同步发事件, 但事件构造交给统一 adapter。
- callback 失败只能记录 tracing failure, 不覆盖原 provider 异常链。
- β/γ3 边界写清: α4 只处理 gateway fallback; γ3 再做全 engine trace schema 清扫。

### α5 LLM Roles Phase 1 data layer (14h)

**WHY**: Gateway resolver 读取 role/model/provider 配置; `RoleEntry.temperature` 顶层字段会让 fallback model 共用同一个生成参数, 与 LLM Roles Phase 1 的 model 级控制冲突。

**WHAT**:

- 修改 `apps/studio/backend/app/models/llm_config.py`: 删除 `RoleEntry.temperature`。
- 修改 `RoleModelEntry`: 新增 `temperature: float | None = None`, `max_tokens: int | None = None`。
- 确认 `ModelInfo.capabilities: dict[str, Any]`。
- 新增后端启动或配置读取时的 `llm_roles.yaml` 迁移: 外层 role `temperature` 下推到每个 `models[*].temperature`, 然后删除外层键。
- 调用侧 `temperature/max_tokens is None` 时回退系统默认, temperature 默认 `0.7`。
- 更新前后端共享类型或 API snapshot, 保证 `GET /api/llm/roles` 不再返回外层 temperature。

**HOW**:

- 先写 migration golden test: 旧 YAML 输入 -> 新 YAML 输出。
- Pydantic `extra="forbid"` 保持严格; 迁移只接受旧数据入口, 新写回不再保留旧字段。
- Phase 1 不实现 Settings 双栏 UI, 只保证现有 UI/API 不因 schema 变更崩溃。

### α6 Tests, docs, CI and ship gate (8h)

**WHY**: PR α 是后续 β/γ 系列的底座。没有测试先行、偏移 audit 和文档同步, 后续 PR 会反复返工。

**WHAT**:

- 补 `packages/graph-agent-gateway/tests/` 单测。
- 补 engine integration tests: `run_skill(..., model_resolver=...)` 正常与缺失两条路径。
- 补 Studio backend llm roles migration/API tests。
- 更新 `docs/engine/graph-agent-gateway/{mvp0-alignment.md,logic-explained.md}` 中 PR α 已完成段。
- 更新 `.kiro/specs/engine-mvp0-rebuild-v030/round-9-PR-alpha-gateway-llm-roles/{requirements.md,design.md,research.md}` 若 implementation 发现字段偏移。

**HOW**:

- SOP-05: cutover test first, src 服测试, 不为保旧行为加 fallback。
- SOP-08: a1 实施后交 a2 drift audit, 再跑 CI/e2e buffer。
- 所有文档变更与源码同 PR, 不把契约修正留到后续 PR。

## §3 Test 覆盖矩阵

| Task | Unit tests | Integration tests | E2E / ship checks |
|---|---|---|---|
| α1 | package import, public API export, old/new import no cycle | engine imports only protocol, gateway package owns concrete model | `uvx ruff check packages/graph-agent-gateway packages/graph-agent/src` |
| α2 | fake `ModelResolverProtocol` signature, missing resolver error | `run_skill` LLM phase uses injected resolver; pure logic graph does not require resolver | pytest graph-agent runtime suite |
| α3 | `AllProvidersFailedError` payload fields and code | all providers fail produces structured exception through runtime | Studio/API error serialization snapshot |
| α4 | fallback event payload fields; callback failure does not mask provider failure | one provider fails then next succeeds emits one fallback event | trace fixture includes gateway fallback item |
| α5 | Pydantic schema, YAML migration, default fallback | `GET /api/llm/roles` returns model-level params only | backend route test with legacy YAML fixture |
| α6 | docs link lint if available | full pytest selected suites | a2 drift audit PASS, main CI three green |

最低命令集:

```bash
uvx ruff check packages/graph-agent/src packages/graph-agent/tests packages/graph-agent-gateway apps/studio/backend/app apps/studio/backend/tests
uvx mypy packages/graph-agent/src packages/graph-agent-gateway/src apps/studio/backend/app
pytest packages/graph-agent/tests packages/graph-agent-gateway/tests apps/studio/backend/tests
cargo test --manifest-path apps/studio/tauri/Cargo.toml
```

如 PR α 没有 Tauri 代码 diff, `cargo test` 仍作为 ship gate 记录结果或明确不可运行原因。

## §4 PR #90 cherry-pick / clean port 清单

原则: PR #90 已 close, 不整段合并旧分支。所有可复用内容只按本 PR 契约 clean port, 不带入旧 schema、旧 allowlist、旧 fallback 或自创字段。

| Commit | 处理 | 理由 / fix scope |
|---|---|---|
| `07ad1bc feat(studio): add v030 skill resolver registry` | 手工参考, 不 cherry-pick | 可参考 metadata helper 写法; SkillResolver registry 不属于 PR α, 不移植业务逻辑。 |
| `9fc551f feat(studio): add v030 skill import endpoint` | 舍弃 | Studio skill import endpoint 属于 SkillResolver/Studio flow, 非 Gateway/llm-roles Phase 1。 |
| `0336b42 feat(studio): inject v030 skill resolver into engine calls` | 手工参考, 不 cherry-pick | 只参考 "外部 resolver 注入 engine 调用" 的 wiring 思路; 目标改为 `ModelResolverProtocol`。 |
| `023f279 feat(studio): add tauri pick folder command` | 舍弃 | Tauri folder picker 非 PR α scope。 |
| `dba6141 feat(studio): surface subgraph skill imports in assets panel` | 舍弃 | Frontend assets panel 非 PR α scope。 |
| PR #90 中 engine A-G cutover commits | 舍弃 | 多数属于 γ0/β/γ1/γ2/γ3, 强行移植会带入 exit_contract、SkillNodeAST 或 V2.1 cleanup 偏移。 |

Whole cherry-pick 推荐: **无**。

Manual clean port 推荐:

- `AllProvidersFailedError` payload 相关片段若存在, 只移植字段级结构和测试思路。
- resolver 注入 wiring 只移植模式, 不移植 SkillResolver 或旧 Studio endpoint。
- 任何旧 `<exit_contract>` allowlist、`TraceEventKind` 枚举、旧 `[F-v21-*]` 字符串、V2.1 compatibility shim 一律不移植。

## §5 工程量

| Task | 工时 |
|---|---:|
| α1 Gateway independent package extraction | 10h |
| α2 ModelResolverProtocol DI and singleton cutover | 10h |
| α3 Structured gateway failure payload | 6h |
| α4 Fallback tracing alignment | 6h |
| α5 LLM Roles Phase 1 data layer | 14h |
| α6 Tests, docs, CI and ship gate | 8h |
| **合计** | **54h = 6.75d** |

额外 wall-clock buffer:

- a2 drift audit: 0.5d。
- a3 e2e / smoke: 0.5d。
- CI/rebase/main 三连绿: 0.25d。
- 合计: 1.25d, 不计入 54h 实施工时。

## §6 Ship 验收

PR α 合入前必须同时满足:

- `packages/graph-agent-gateway/` 是独立 package, Engine 生产路径不再依赖 gateway singleton。
- `run_skill` / assembly / Agent runtime 对含 LLM/Agent phase 的图强制接收 `model_resolver`。
- `[F-v3-gateway-*]` 三个错误码进入结构化 payload, Studio 不再解析 gateway 自由文本。
- fallback event 通过统一 tracing callback 底座发出, Predict mock 不伪造真实 provider fallback。
- `GET /api/llm/roles` 返回 model-level `temperature/max_tokens`, 外层 `RoleEntry.temperature` 消失。
- legacy `llm_roles.yaml` 自动迁移测试通过, 新写回不保留旧字段。
- `ruff` / `mypy` / `pytest` / `cargo test` 按 §3 命令集通过或记录明确环境阻断。
- a2 drift audit PASS: implementation 与 `requirements.md` / `design.md` / gateway mvp0 alignment 字段一致。
- main 三连绿 CI。
- logic-explained report 字段级完整: baseline 变化、contract 变化、测试证据、剩余非目标项、后续 γ0/β/γ 边界。

## §7 风险点

- `graph-agent` 与 `graph-agent-gateway` import cycle 是最高风险; α1 必须先用 package import tests 卡住。
- LLM Roles migration 写回真实配置文件有数据风险; 必须用临时 fixture 和原子写测试覆盖。
- `ModelResolverProtocol` 放置位置若 design.md 后续调整, 需要同步 tasks/design/research 三件套, 但工程推荐仍是 protocol 可由 Engine 轻依赖、concrete resolver 留在 gateway。
- β/γ3 tracing 容易重复改; PR α 只允许 gateway fallback event 归口, 不顺手清全 engine trace schema。
