# V1 Reset 功能总结报告

日期: 2026-04-30

范围: 本报告总结 v1-reset 分支当前已经 ship 的 `graph_agent` 框架能力和 `graph_skill` 体系能力。它不是 release notes，不按提交流水账展开；重点是功能矩阵、实施现状、验证数据和边界范围。数据基于 `main..HEAD` 至 Phase 4 M3 commit `7064065`，以及本地验证结果。

## 1. 总览

v1-reset 的目标是把项目从 DeerFlow 1.0 fork 收敛成一个自研轻量 SKILL 引擎。当前交付物分为两层:

- `graph_agent`: SKILL 编译、LangGraph 执行、PhaseNode 多态执行、Pydantic schema 校验、中间件契约、状态不变量、LLM Gateway 和 CLI/runner。
- `graph_skill`: 以 `SKILL.md` 为入口的 Markdown/YAML DSL，覆盖 graph skill、persona skill、builtin agent skill、示例、归档快照和 v2 pending 草稿。

当前硬指标:

| 指标 | 当前值 |
| --- | --- |
| v1-reset commits | 72 commits (`git log main..HEAD`) |
| 相对 `main` 代码变化 | 217 files changed, +25,061 / -214,592 |
| 全量 deterministic pytest | 1,016 passed, 1 skipped |
| `tests/skills/` | 34 passed |
| integration smoke | 9 passed, 含真 LLM smoke |
| mypy strict | 0 errors, 95 source files |
| ruff | 0 errors |
| 全库覆盖率 | 79.39% (`--cov=src/core/graph_agent`) |
| `graph_agent.models` 覆盖率 | 95.02% |
| runtime `with_fallbacks` | `src/core/graph_agent` 下 0 hit |
| legacy `ValidationMiddleware` | runtime 0 hit；仅剩 `ProtocolValidationMiddleware` |

定位差异:

- 相比 DeerFlow 1.0: v1-reset 删除 vendored DeerFlow 目录，替换其旧执行/验证路径，建立 SKILL 编译期契约、业务/框架状态分离、PhaseNode 多态执行和单一 CognitiveFlow 校验路径。
- 相比 Story Forge: v1-reset 借鉴其 production-grade LLM client manager 机制，但保留 graph_agent 的 SKILL 编译器、LangGraph 执行和 LangChain `BaseChatModel` 适配边界。

## 2. graph_agent 框架功能矩阵

### 2.1 Loader / Parser

| 项 | 现状 |
| --- | --- |
| 功能 | 发现和读取 `SKILL.md`，解析 YAML frontmatter，支持 graph/persona/simple/agent skill，解析 phases、IO、tools、subgraph、persona、output schema。 |
| 关键路径 | `src/core/graph_agent/core/loader.py`, `skill_parser.py`, `manifest.py`, `skill_builder.py`, `compiler.py` |
| 测试 | loader smoke、manifest validation、hostile input/parser、18 个 `SKILL.md` inventory 检查 |
| DeerFlow 差异 | 不再依赖 DeerFlow 隐式包路径和运行期猜测；SKILL 文件变成明确编译输入。 |

已实现边界:

- 支持项目级 `skills/`、package examples、builtin package skills。
- 支持 active、builtin、example、archived、pending 多类 SKILL 文件，但报告中会区分它们是否属于 live runtime。
- `md-patch` 保持为 SKILL 资源目录，不再被 mypy 识别为非法 Python package。

### 2.2 Compiler / Compile-Time Validation

| 项 | 现状 |
| --- | --- |
| 功能 | structured `CompileIssue`、line location、`SkillCompileError`、Schema 2.0 strict gate、tool path 校验、persona 校验、validator/output_schema 一致性校验、hostile YAML 防御。 |
| 关键路径 | `src/core/graph_agent/core/skill_validator.py`, `compiler.py`, `exceptions.py`, `core/validators/` |
| 测试 | `tests/graph_agent/core/test_validate_manifest.py`、loader smoke、hostile compile tests |
| DeerFlow 差异 | 把错误 SKILL 从运行期失败前移到编译期拒绝。 |

已 ship 的规则:

- 声明 runtime validator 的 phase 必须提供 `output_schema` 或合法 schema 替代。
- `LogicPhase` 保持豁免，因为它不经过 LLM structured output。
- business validator 输入契约是 `list[dict[str, Any]]` payload，不是 framework ctx。
- archived snapshot 可作为历史记录存在，但 live SKILL 必须满足当前 schema gate。

### 2.3 State / Invariants

| 项 | 现状 |
| --- | --- |
| 功能 | `WorkflowState` 拆分 `BusinessData` / `FrameworkState`，checkpoint-safe state layout，状态不变量校验，协议边界检查。 |
| 关键路径 | `src/core/graph_agent/core/state.py`, `state_manager.py`, `middleware/protocol_validation.py` |
| 测试 | state invariant tests、MVP smoke、integration invariant tests |
| DeerFlow 差异 | 不再混放业务数据和框架数据。 |

已验证不变量:

- 业务输出只写业务字段。
- 框架控制信息只写框架字段。
- LLM/tool protocol message 满足 LangGraph/LangChain 要求。
- final output 通过 SKILL IO contract 产出。

### 2.4 PhaseExecutor / PhaseNode 多态

| 项 | 现状 |
| --- | --- |
| 功能 | `PhaseExecutor` 薄壳、`PhaseNode` ABC、`LLMPhaseNode` / `CodePhaseNode` / `ValidationPhaseNode`、`DependencyContainer` 注入、factory 分派。 |
| 关键路径 | `src/core/graph_agent/core/phase_executor.py`, `core/phase_nodes/base.py`, `llm_phase_node.py`, `code_phase_node.py`, `validation_phase_node.py`, `factory.py` |
| 测试 | `tests/graph_agent/core/test_phase_executor.py`、closure AST guard、routing regression tests |
| DeerFlow 差异 | 1130 行 god class 拆成 158 行薄壳和节点子类。 |

当前实测:

- `src/core/graph_agent/core/phase_executor.py`: 158 行。
- `src/core/graph_agent/core/phase_nodes/`: 7 个 Python 文件。

行为契约:

- LLM phase 走 `ProtocolValidationMiddleware` + `CognitiveFlowMiddleware`。
- Code phase 支持 dict business merge；带 `_` 前缀的保留字段在 Pydantic validate 之前拒绝。
- Validation phase 只接收业务 payload，不接收 framework ctx。

### 2.5 Middleware

| 项 | 现状 |
| --- | --- |
| 功能 | 协议校验、structured output 校验、retry feedback、business validator 调度、execution control。 |
| 关键路径 | `src/core/graph_agent/middleware/protocol_validation.py`, `cognitive_flow.py`, `execution_control.py` |
| 测试 | CognitiveFlow tests、live SKILL cognitive smoke、phase routing tests |
| DeerFlow 差异 | 旧 `ValidationMiddleware` 双系统已终结。 |

当前 runtime path:

- `ProtocolValidationMiddleware` 负责 state contract。
- `CognitiveFlowMiddleware` 负责 schema/Pydantic 校验、retry feedback 和 business validator。
- schema-backed live SKILL 统一进入新管道。
- schema-less/dynamic legacy fallback 已在 Phase 3 M7 后移除。

### 2.6 Schema / IO / ModuleSandbox

| 项 | 现状 |
| --- | --- |
| 功能 | Pydantic schema 解析、dynamic schema 支持、IO mapping、ModuleSandbox 加载、forward-ref/model rebuild、防 PydanticUserError 回归。 |
| 关键路径 | `src/core/graph_agent/core/schema_engine.py`, `io_manager.py`, `module_sandbox.py`, `tools/dynamic_schema.py`, `io/` |
| 测试 | ModuleSandbox tests、forward-ref regression、schema engine tests、live SKILL smoke |
| DeerFlow 差异 | 不再通过全局 `sys.path` hack 解决 skill script 加载。 |

关键修复:

- `ModuleSandbox` 在加载期间注册 `sys.modules`，支持 Pydantic forward references。
- `from __future__ import annotations` + `Literal` schema 有回归测试。
- phase 级 IOManager 和 harness 级 IOManager 明确分层。

### 2.7 LLM Gateway

| 项 | 现状 |
| --- | --- |
| 功能 | 原生 SDK client cache、provider usage stats、provider+model down-cache、active probe、OpenAI-compatible / Anthropic-compatible / WaveSpeed dispatch、WaveSpeed 5xx retry、LangChain adapter。 |
| 关键路径 | `src/core/graph_agent/models/llm_client_manager.py`, `gateway_chat_model.py`, `resolver.py` |
| 测试 | `tests/graph_agent/models/test_llm_client_manager.py`, `test_gateway_chat_model.py` |
| DeerFlow 差异 | 移除 LangChain `with_fallbacks` 作为 runtime fallback 机制。 |

已实现:

- `LLMClientManager` 负责 OpenAI/Anthropic 原生 client 创建和复用。
- provider down state 按 provider + model 组合键缓存。
- active probe 按 provider type 分派。
- WaveSpeed/any-LLM 502/503/504 有 bounded retry。
- usage stats 按 provider 记录。
- `GatewayChatModel` 实现 LangChain `BaseChatModel` 适配器。
- fallback event 只在真实 probe/call 失败后发出，不再预测式打点。

### 2.8 Model Config / Resolver

| 项 | 现状 |
| --- | --- |
| 功能 | `llm_roles.yaml` 三段式配置 (`models` / `providers` / `roles`)，role resolution，peer model groups，thinking config，resolver 输出 `GatewayChatModel`。 |
| 关键路径 | `src/core/graph_agent/config/llm_config.py`, `src/core/graph_agent/models/resolver.py`, `config/llm_roles.yaml` |
| 测试 | resolver tests、gateway tests、real LLM smoke role override |
| DeerFlow 差异 | 真 LLM smoke 不再硬编码 `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GRAPH_AGENT_API_KEY`。 |

当前配置包含的单模型测试 role:

- `test_sonnet46_jk`: Sonnet 4.6 via Jiekou。
- `test_opus47_ws`: Opus 4.7 Thinking via WaveSpeed。
- `test_dsv4`: DeepSeek-V4 Flash via DeepSeek 官方。

### 2.9 Tools / Agent Runtime Contract

| 项 | 现状 |
| --- | --- |
| 功能 | `finish_task`、`ask_clarification`、builtin tool、script tool、LLM phase agent tools、Markdown-to-JSON repair、builtin `md-patch` skill。 |
| 关键路径 | `src/core/graph_agent/tools/`, `tools/builtin/`, `tools/md_to_json.py`, `src/core/graph_agent/skills/builtin/md-patch/SKILL.md` |
| 测试 | tool loading、md-to-json、live SKILL smoke、md-patch compile |
| DeerFlow 差异 | 工具契约由 SKILL DSL 明确声明，不再依赖运行期隐式习惯。 |

runtime 规则:

- LLM phase 用 `finish_task` 提交 business output。
- 需要澄清时用 `ask_clarification`。
- code-only tool 返回 dict 时按 A3 contract merge/reject/no-op。
- `_` 前缀 key 被视为 framework-like reserved key，必须拒绝。

### 2.10 Callbacks / Tracing

| 项 | 现状 |
| --- | --- |
| 功能 | callback event、tracing proxy、prompt capture、model resolved event、LLM fallback event、usage/cost plumbing。 |
| 关键路径 | `src/core/graph_agent/callbacks/`, `core/tracing_proxy.py`, `models/gateway_chat_model.py` |
| 测试 | callback tests、fallback-event tests、gateway tests |
| DeerFlow 差异 | fallback 可观测性从构建期预测事件迁移到运行期真实失败事件。 |

关键边界:

- resolver 构建模型时不再发 fallback event。
- `GatewayChatModel` 在 probe/call 真实失败后发 fallback event。

### 2.11 Runner / CLI / Checkpoint

| 项 | 现状 |
| --- | --- |
| 功能 | Harness execution、graph runner、CLI entrypoint、thread-id checkpoint resume、unattended mode、checkpoint store。 |
| 关键路径 | `src/core/graph_agent/core/runner.py`, `harness.py`, `checkpointer.py`, `cli.py` |
| 测试 | MVP smoke、integration smoke、checkpoint/resume tests |
| DeerFlow 差异 | 保留 graph_agent 自己的 resume/checkpoint 语义，不继承 DeerFlow 项目假设。 |

用户入口:

- `graph-agent` CLI 由 root package metadata 暴露。
- thread id 支持 checkpoint resume。
- unattended mode 由 integration smoke 覆盖。

### 2.12 Engineering Gates / Security Baseline

| 项 | 现状 |
| --- | --- |
| 功能 | 全库 mypy、全库 ruff、pytest gate、coverage gate、Apache-2.0 license、Dependabot、pip-audit CI step。 |
| 关键路径 | `pyproject.toml`, `.github/workflows/ci.yml`, `.github/dependabot.yml`, `LICENSE`, `README.md` |
| 测试 | CI gate 对齐本地 full-suite gate。 |
| DeerFlow 差异 | 从部分文件级检查升级到仓库级质量门禁。 |

当前 gate:

- `ruff check src/ tests/`: pass。
- `mypy src/`: pass。
- `pytest tests/`: pass。
- `pytest tests/ --cov=src/core/graph_agent`: 79.39%，超过 73% gate。

## 3. graph_skill 体系功能

### 3.1 DSL Surface

当前 `SKILL.md` DSL 支持:

- `schema_version`, `name`, `description`, `type`。
- `io.inputs` / `io.outputs`。
- `context_mapping`。
- `phases`。
- phase 级 `llm_role`。
- `agent_tools` / script tool references。
- `output_schema`。
- `validation`。
- `subgraph` / `output_mapping`。
- `adopted_persona`。

### 3.2 Runtime Contract

已实现的运行期契约:

- LLM phase 通过 `finish_task` 完成。
- LLM phase 可通过 `ask_clarification` 请求澄清。
- parser/validator phase 操作纯 business payload。
- structured output 使用 Pydantic class 或 schema object。
- business validator 接收 `list[dict[str, Any]]`。
- subgraph phase 可委派子 SKILL 并把输出映射回父 state。
- persona SKILL 只注入角色视角，不作为 standalone graph 执行。

### 3.3 18 个 SKILL.md 清单

仓库当前有 18 个 `SKILL.md`。它们不是全部 live production SKILL；下表按 active、builtin/example、pending、archive 区分。

| 路径 | name | 类型/状态 | 功能 |
| --- | --- | --- | --- |
| `skills/text-segmentation/SKILL.md` | `text-segmentation` | active graph | 章节文本切分和复核。 |
| `skills/event-extraction/SKILL.md` | `event-extraction` | active graph | 从 segmentation output 生成 event timeline/settings。 |
| `skills/batch-analysis/SKILL.md` | `batch-analysis` | active graph | 批量事件分析和 accumulated context 更新。 |
| `skills/global-synthesis/SKILL.md` | `global-synthesis` | active graph | 汇总 batch output 成最终 story framework。 |
| `skills/examples/subgraph-sample/story-deconstruction/SKILL.md` | `story-deconstruction-subgraph` | active example graph | 演示四个 story-analysis SKILL 的 subgraph 编排。 |
| `skills/producer/SKILL.md` | `producer` | active persona | 给 LLM phase 注入制片人视角。 |
| `skills/producer/review/SKILL.md` | none | support markdown | 无 frontmatter 的 producer review 支撑文档。 |
| `src/core/graph_agent/examples/hello_world/SKILL.md` | `hello-world` | package example | 最小 simple SKILL 示例。 |
| `src/core/graph_agent/skills/builtin/md-patch/SKILL.md` | `md-patch` | builtin agent | Markdown validation repair skill。 |
| `skills/_v2_pending/story-deconstruction/SKILL.md` | `story-deconstruction` | pending graph | v2 story deconstruction 草稿。 |
| `skills/_v2_pending/adaptation_v1/SKILL.md` | `plan-scenes` | pending agent | 场景规划草稿。 |
| `skills/_v2_pending/adaptation_v1/subskills/beat_extractor/SKILL.md` | `beat-extractor` | pending agent | beat extraction 草稿。 |
| `skills/_v2_pending/adaptation_v1/subskills/producer_strategy/SKILL.md` | `producer-strategy` | pending agent | producer strategy 草稿。 |
| `skills/_v2_pending/adaptation_v1/subskills/writer_drafting/SKILL.md` | `writer-drafting` | pending agent | writer drafting 草稿。 |
| `skills/text-segmentation/versions/v0-main-baseline/SKILL.md` | `text-segmentation` | archived snapshot | 历史 baseline。 |
| `skills/text-segmentation/versions/v1-codex-attempt/SKILL.md` | `text-segmentation` | archived snapshot | 历史 Codex attempt。 |
| `skills/text-segmentation/versions/v2-gemini-rewrite-r1/SKILL.md` | `text-segmentation` | archived snapshot | 历史 Gemini rewrite r1。 |
| `skills/text-segmentation/versions/v3-gemini-rewrite-r2/SKILL.md` | `text-segmentation` | archived snapshot | 历史 Gemini rewrite r2。 |

当前可执行/被测试的主要 surface:

- 排除 `_v2_pending/` 和 `versions/` 后，`skills/` 下有 7 个非归档 SKILL 文件。
- 加上 package example 和 builtin `md-patch`，共有 9 个非归档 SKILL 文件。
- 仓库级 inventory 总数是 18 个 `SKILL.md`。

### 3.4 SKILL 测试覆盖

当前 SKILL 相关验证层:

- `tests/skills/test_loader_based_smoke.py`: active graph SKILL loader/compile smoke。
- `tests/skills/*/test_cognitive_flow_smoke.py`: representative live SKILL CognitiveFlow smoke。
- `tests/skills/*/test_validators_runtime.py`: live validator runtime contract。
- `tests/graph_agent/integration/test_mvp1_smoke.py`: integration smoke + invariant checks + real LLM smoke。

实测:

- `tests/skills/`: 34 passed。
- `tests/graph_agent/integration/test_mvp1_smoke.py`: 9 passed。

## 4. 与 DeerFlow 1.0 的差异

v1-reset 不是 DeerFlow 目录整理，而是 runtime 替换。

| 领域 | DeerFlow-era 状态 | v1-reset 状态 |
| --- | --- | --- |
| vendored code | 有 `deerflow/` vendored tree | `f5b3fa4` 删除 `deerflow/`，约 1.3M / 158 files |
| package metadata | 双 pyproject / 多 root 假设 | 根 `pyproject.toml` 统一 |
| import | `sys.path` startup hack | package layout + ModuleSandbox |
| state | business/framework 混写 | `BusinessData` / `FrameworkState` 分离 |
| schema | 缺 schema 可 runtime fallback | compile-time gate + live SKILL schema |
| validation | 旧 VM + 新管道双系统 | ProtocolValidation + CognitiveFlow 单路径 |
| phase execution | 1130 行 monolith | PhaseNode 多态 + 158 行 shell |
| code phase dict | 可能静默丢弃 | merge/no-op/reject 明确契约 |
| LLM fallback | LangChain `with_fallbacks` | `GatewayChatModel` 自主 fallback |
| LLM clients | LangChain wrapper 为主 | `LLMClientManager` 原生 SDK client/cache/stats |
| quality gates | Phase 1 初期部分 gate | mypy/ruff/pytest/coverage/CI/security gate |

已删除或终结的兼容路径:

- live LLM phase 的 `schema is None` 静默成功路径。
- 旧 `ValidationMiddleware` runtime 路径。
- resolver 构造期假网络 failover。
- peer fallback 预测式 tracing。
- `src/core/graph_agent` 下 LangChain `with_fallbacks`。

## 5. Ship 数据

### 5.1 关键里程碑 Commit

| commit | 里程碑 |
| --- | --- |
| `2348a7f` | Phase 1 audits + 工程卫生落库。 |
| `acf8d97` | Phase 2 A1: 砍 `schema is None`，加 `SkillCompileError`，修 validator payload contract。 |
| `61dd53f` | Phase 2 A3: code-only phase dict merge + reserved key contract。 |
| `dd6fa6a` | Phase 2 A2: 新 middleware pipeline routing。 |
| `b5a114f` | Phase 3 M7: 终结 legacy `ValidationMiddleware` 双系统。 |
| `8a5977c` | Phase 3 M6: `PhaseExecutor` 拆 PhaseNode 多态架构。 |
| `2ca3030` | Phase 4 M1: 引入 `LLMClientManager`。 |
| `4b37c09` | Phase 4 M2: 引入 `GatewayChatModel`。 |
| `7064065` | Phase 4 M3: resolver 输出 `GatewayChatModel`，18 SKILL 0 回归。 |

### 5.2 本地验证快照

| 命令/范围 | 结果 |
| --- | --- |
| `.venv/bin/pytest tests/ --tb=line -q` | 1,016 passed, 1 skipped |
| `.venv/bin/pytest tests/ --cov=src/core/graph_agent --cov-report=term -q` | 1,016 passed, 1 skipped, 79.39% coverage |
| `.venv/bin/mypy src/` | Success, 0 issues in 95 source files |
| `.venv/bin/ruff check src/ tests/` | All checks passed |
| `.venv/bin/pytest tests/skills/ -v` | 34 passed |
| `.venv/bin/pytest tests/graph_agent/integration/test_mvp1_smoke.py -v` | 9 passed |
| `.venv/bin/pytest tests/graph_agent/models/ --cov=graph_agent.models --cov-report=term -q` | 94 passed, 95.02% models coverage |
| `rg "with_fallbacks" src/core/graph_agent` | 0 hits |

真 LLM smoke:

- 入口: `tests/graph_agent/integration/test_mvp1_smoke.py`。
- provider 判断: 读取 `config/llm_roles.yaml` 的 `providers.*.api_key_env`，不再硬编码 DeerFlow-era env 名。
- 范围: 小输入章节 + invariant checks。
- 结果: integration smoke 9 passed。
- token/cost: 本报告未引用未落库的临时 trace；deterministic CI 不依赖真实 provider key。

### 5.3 阶段轨迹

| 阶段 | 代表状态 |
| --- | --- |
| Phase 1 | 856 passed / 2 skipped，部分 ruff/mypy gate，4 SKILL compile gate。 |
| Phase 2 | A1/A2/A3 schema、validation、code-phase contract 通过 iterative review ship。 |
| Phase 3 | mypy 0、ruff 0、CI/security/readme hygiene、旧 VM 删除、PhaseNode 架构 ship。 |
| Phase 4 | LLM Gateway engine、LangChain adapter、resolver 换核、18 SKILL 0 回归。 |

## 6. Out Of Scope

以下不作为 v1-reset 当前已 ship 功能声明。

### v1.1 候选

- ModuleSandbox ghost field / developer ergonomics 清理。
- 把 CognitiveFlow smoke 从 representative SKILL 扩到所有可提供 runtime fixture 的非归档 SKILL。
- 加可控成本的真 LLM CI lane。
- 加 SBOM，例如 `cyclonedx-py`。
- 继续收窄 PhaseNode dependency surface。

### v1.2 候选

- Pydantic v1/v2 完整解耦层。
- 原生 async client / `httpx.AsyncClient` / async LangGraph path。
- 分布式 provider usage/token counter。
- 多模态 provider 扩展和更细 telemetry。

## 7. 当前结论

Phase 4 M3 之后，v1-reset 已经 ship:

- strict compile-time SKILL validation。
- 明确的 state invariants。
- PhaseNode 多态执行架构。
- 单一 structured-output middleware 管道。
- 原生 SDK LLM Gateway 和真实 runtime fallback。
- LangChain-compatible `GatewayChatModel`，兼容现有 agent flow。
- active story-analysis SKILL、persona、examples、builtin、pending、archive 分层 inventory。
- 仓库级 typing、lint、pytest、coverage、license、dependency audit 门禁。

剩余工作主要是覆盖面扩展、真实 LLM CI 成本控制、未来 provider/runtime 扩展和工程债清理，不是当前基础 runtime 正确性缺口。
