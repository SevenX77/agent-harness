# Round 31 Decisions (authoritative, PM 拍板清单)

> **本文档是 round-31 实施期间所有歧义的唯一权威源**.
> 后续实施期间, 任何 spec / design / docs / code 内跟本文档冲突的地方, 一律以本文档为准.
> 旧文档冲突就地加 banner `[OBSOLETE 看 round-31/decisions.md §X]`.

## §0 元规则

- 本文档是 PM 拍板 + 收敛的最终目标 + 大方向 + 原则策略.
- 主控 + a1 + a2 + a3 实施期间用本文档做 audit baseline.
- 任何看到旧文档跟本文档冲突的人, 一律以本文档为准.
- 每条决策都标记"以本文为准"; 实施中不得用旧 design / research / baseline 反向覆盖本文.
- 砍功能必须有去向; 真砍未在本文档拍板范围内的能力, 必停下来 escalate PM.
- 旧文档冲突的处理方式不是沉默忽略, 而是在冲突位置加 `[OBSOLETE 看 round-31/decisions.md §X]`.

## §1 Q3 LLM 配置归 Gateway

**结论: 以本文为准.** SDK 不管 LLM 配置; Gateway 是独立完整的 LLM 配置管家. Studio 调 LLM 只能找 Gateway. SDK 只接收 Gateway 提供的 `model_resolver` 协议.

**PM 拍板原话 (2026-05-30):** "之前把 gateway 拆出来没拆干净, 我当然想要拆干净"

**字段级技术约束:**

- Gateway 拥有 yaml 加载、schema 验证、provider/role/model 解析、fallback、熔断、热加载.
- SDK 不再导出或维护 `configure_llm_environment`, `LLMEnvironment`, `ChatResponse`, `ChatStream`.
- SDK 不读取 Studio settings, 不读 provider API key, 不读 role config.
- SDK `run_skill` / `predict_skill` / `evaluate_golden_baseline` 只接收 `model_resolver` protocol.
- Studio Copilot / Settings / LLM roles 侧 import 必须切到 Gateway 入口.

**实施影响点:**

- `packages/graph-agent/src/graph_agent/config/llm_config.py:40-753`
- `packages/graph-agent/src/graph_agent/models/llm_client_manager.py:1-5`
- `packages/graph-agent/src/graph_agent/models/llm_client_manager.py:24`
- `packages/graph-agent-gateway/src/graph_agent_gateway/llm_config.py:10-122`
- `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:151-188`
- `apps/studio/backend/app/services/copilot.py:36`
- `apps/studio/backend/tests/routers/test_copilot_ws_endpoint.py:22`

## §2 Q4 tracing 默认自动落

**结论: 以本文为准.** 废除用户创建 `TracingCallback(trace_dir=...)` 来决定 trace 输出的反模式. SDK 默认自动落盘到 `<workspace_dir>/runs/<run_id>/trace.jsonl`.

**PM 拍板原话:** "怎么可能让用户去创建? tracing 就应该放在 .workspace 里面每一次的 run_id 下面"

**字段级技术约束:**

- `workspace_dir: Path` 必传.
- SDK 内部创建 `<workspace_dir>/runs/<run_id>/`.
- SDK 内部创建 trace writer; public API 不接收 `trace_dir`.
- 用户不能指定 trace 文件名、trace 目录或旁路写盘位置.
- `run_skill` 和 `predict_skill` 都必须自动写 trace.
- trace 文件名固定为 `trace.jsonl`, one JSON `CallbackEvent` per line.

**实施影响点:**

- `packages/graph-agent/src/graph_agent/core/runner.py:59-73`
- `packages/graph-agent/src/graph_agent/core/runner.py:198-214`
- `packages/graph-agent/src/graph_agent/core/runner.py:235-239`
- `packages/graph-agent/src/graph_agent/callbacks/tracing.py:58-85`
- `apps/studio/backend/app/services/run_manager.py:226-241`

## §3 Q4 tracing + eventstream 同源出口

**结论: 以本文为准.** tracing 和 eventstream 是同一事件源的两个出口, 不是两个独立 Callback 类体系.

**PM 拍板原话:** "tracing 不能和 eventstream callback 放一起吗?"

**字段级技术约束:**

- Engine 内部只有一份 `CallbackEvent` 事件源.
- 默认出口: SDK 写 `<workspace_dir>/runs/<run_id>/trace.jsonl`.
- 可选出口: SDK 调用 `event_subscriber(event)`.
- Public API 参数名使用 `event_subscriber: Callable[[CallbackEvent], None] | None = None`.
- `EventStreamCallback` 不作为 public class 存在.
- Studio WebSocket / queue bridge 改成 callable adapter, 不继承 callback class.

**实施影响点:**

- `packages/graph-agent/src/graph_agent/callbacks/events.py:450`
- `packages/graph-agent/src/graph_agent/callbacks/base.py:139`
- `packages/graph-agent/src/graph_agent/callbacks/tracing.py:113`
- `apps/studio/backend/app/services/run_manager.py:89-95`
- `apps/studio/backend/app/services/run_manager.py:230-235`

## §4 Q4 predict 定位 = Copilot 协作迭代 prompt 工程入口

**结论: 以本文为准.** Predict 是 Copilot 协作迭代 prompt 工程入口. Predict 和 Run 输出同形: `RunResult + source` 字段.

**PM 拍板原话:** "predict 是模拟器也要有模拟报告啊, 最终记录结果应该和真的 run 是一样的, llm 大模型调用的部分也要有 predict, 只不过是用 copilot 的接口去预测结果"

**字段级技术约束:**

- 新 public verb: `predict_skill(..., workspace_dir: Path, event_subscriber=None) -> RunResult`.
- `PredictResult` 删除; Studio 读 `RunResult(source="predict")`.
- `RunResult` 必含 `source: "run" | "predict"`.
- Predict 逻辑节点真实执行.
- Predict 的 LLM 节点通过 Gateway predict chat model 调 Studio 注入的 Copilot callable 预测输出.
- 协作链固定为: predict -> copilot 模拟 -> golden 转化 -> run -> golden 对比 -> copilot 建议 -> 迭代.
- Golden 转化属于 Studio HTTP 编排, 不新增 SDK verb.

**实施影响点:**

- `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:24-52`
- `packages/graph-agent/src/graph_agent/core/_predict_internal/interception.py:11`
- `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:76-86`
- `packages/graph-agent/src/graph_agent/core/result.py:46-60`
- `apps/studio/backend/app/services/predictor.py:65-90`
- `apps/studio/backend/app/routers/runs.py:32-40`
- `apps/studio/backend/app/services/golden_diff.py:34-64`

## §5 Q5 workspace 路径

**结论: 以本文为准.** App 给 root 绝对路径, Engine 按规范写子目录. `<workspace_dir>` 是必传参数.

**PM 拍板原话:** "文件怎么建是 engine 写的, 写在哪个路径是 studio 定的"

**字段级技术约束:**

- Studio / CLI / runner 决定 `workspace_dir` 的绝对路径.
- Engine 不知道 Studio 默认目录, 不读 `~/.studio`.
- Engine 规定 `<workspace_dir>/runs`, `<workspace_dir>/golden`, `<workspace_dir>/test_inputs`.
- `run_skill`, `predict_skill`, `evaluate_golden_baseline` 必须校验 `workspace_dir`.
- 顶层 `<workspace_dir>/predict` 废除.
- Predict 输出写 `<workspace_dir>/runs/<run_id>/`, 由 `RunResult.source = "predict"` 区分.

**实施影响点:**

- `packages/graph-agent/src/graph_agent/core/runner.py:59-73`
- `packages/graph-agent/src/graph_agent/core/runner.py:235-239`
- `apps/studio/backend/app/services/skills.py:734-747`
- `apps/studio/backend/app/services/skills.py:754-755`
- `apps/studio/backend/app/services/skills.py:962-964`
- `apps/studio/backend/app/services/predictor.py:114-119`
- `apps/studio/backend/app/services/git_local.py:21-26`
- `apps/studio/backend/app/services/git_local.py:320-323`

## §6 阻塞点 1: LLM 配置一刀切搬 Gateway

**结论: 以本文为准.** 不做两层迁移过渡期. 一个 cutover PR 内完成整体搬迁、Studio import rename、SDK 老代码删除.

**PM 拍板原话 (2026-05-30):** "阻塞点 1: 一刀切"

**字段级技术约束:**

- 不保留 SDK 老 `llm_config` 与 Gateway 新 config 双栈同时工作的过渡期.
- 不做 SDK -> Gateway compatibility proxy.
- 不允许 Studio 同时 import `graph_agent.config.llm_config` 和 Gateway config.
- Gateway schema 不能机械复制 SDK dataclass 后留下两套真相.
- 删除 SDK provider runtime 后, 所有 provider/model/role 错误归 Gateway error domain.

**实施影响点:**

- `packages/graph-agent/src/graph_agent/config/llm_config.py:40-753`
- `packages/graph-agent/src/graph_agent/models/llm_client_manager.py:24`
- `packages/graph-agent-gateway/src/graph_agent_gateway/llm_config.py:10-122`
- `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:151-188`
- `apps/studio/backend/app/services/copilot.py:36`

## §7 阻塞点 2: predict cache 在 SDK + 链式失效

**结论: 以本文为准.** Predict 整体业务决策在 SDK 内: 跑 graph、cache 决策、ABC 选择都归 SDK. Gateway 不存 cache, 不做业务决策.

**PM 拍板原话:** "predict 的 abc 选择应该是在 sdk 内选择, 这是业务逻辑, 不应该是 Gateway 的逻辑, 只有 sdk 发现没有 cache 要调用 copilot 进行预测才与 Gateway 交互"

**字段级技术约束:**

- SDK 拥有 predict cache 读写与命中判断.
- SDK 拥有 ABC 选择逻辑.
- Gateway 只提供 predict chat model / callable bridge.
- 只有 cache miss 且需要 Copilot 预测时, SDK 通过 `model_resolver` 走到 Gateway.
- cache key = `(phase_id, prompt_hash, input_hash)`.
- **input_hash 作用域**: 仅哈希该 phase 在 `io.inputs` 中声明的输入字段, **不哈希全量 `BlackboardState`**.
  - 理由 (a2 R1): 严格遵循节点沙箱隔离性. 全量 state 算 hash 会让任意无关兄弟节点写入 scratch/输出垃圾数据时触发整链 cache miss, 缓存形同虚设.
  - file:line 实证: `packages/graph-agent/src/graph_agent/runtime/state.py:15-20` 定义 `BlackboardData` 三区 (`inputs` / `phase_outputs` / `scratch`); `packages/graph-agent/src/graph_agent/core/manifest.py:31-38` 定义 `PhaseIOSchema.inputs` / `outputs`.
- 上游 output 变化导致下游 input 变化; 下游 `input_hash` 随之变化, 形成链式失效.
- Gateway 不保存 predict cache, 不判断 golden, 不判断 ABC, 不判断链式失效.
- 如果旧 design 与本节"SDK 不保留 predict 业务决策"冲突, 以本文为准.

**实施影响点:**

- `packages/graph-agent/src/graph_agent/core/_predict_internal/strategy.py:14-194`
- `packages/graph-agent/src/graph_agent/core/_predict_internal/interception.py:42-54`
- `packages/graph-agent/src/graph_agent/core/_predict_internal/interception.py:122`
- `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:21`
- `apps/studio/backend/app/services/predictor.py:65-90`
- `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:74`

## §8 阻塞点 3: V0.3 trace bug 设计含, 实施单独 PR

**结论: 以本文为准.** V0.3 主线 `_run_v030_skill_dict()` 不自动写 trace 是真实 bug. design 必须一起覆盖, 但实施单独拆 PR-trace-bug.

**PM 拍板原话:** "设计得一起设计, 因为与 API 关联很深"

**字段级技术约束:**

- Round 31 API design 必须描述 trace 默认落盘的最终目标.
- 实施排期上, trace bug 可以独立 PR, 但不得从 design 中删掉.
- PR-trace-bug 必须接到新 `workspace_dir` / `event_subscriber` 方向, 不复活 public `trace_dir`.
- 验收必须覆盖不传任何 callback 时仍写 trace.

**实施影响点:**

- `packages/graph-agent/src/graph_agent/core/runner.py:198-214`
- `packages/graph-agent/src/graph_agent/core/runner.py:217-275`
- `packages/graph-agent/src/graph_agent/callbacks/tracing.py:78-85`
- `packages/graph-agent/src/graph_agent/callbacks/tracing.py:434`
- `apps/studio/tests-e2e/test_run_flow.py:4`

## §9 阻塞点 4: e2e scope = 修改边界 + 实现目的, 不扩外部 app

**结论: 以本文为准.** Round 31 e2e 只覆盖 engine + Gateway scope, mock app 端. 不跑 Studio backend/frontend/Tauri.

**PM 拍板来源:** 已抽象写到 `~/.claude/rules/10-sop-e2e-scope.md`.

**字段级技术约束:**

- e2e fixture 提供 mock `workspace_dir`.
- e2e fixture 提供 mock Copilot callable.
- e2e fixture 提供最小 skill fixture.
- 不启动 Studio FastAPI.
- 不启动 Studio frontend.
- 不启动 Tauri.
- 需要验证的目的: 新 SDK/Gateway API 边界能跑通, cache miss 能经 Gateway callable 调 Copilot, trace 能默认写盘.

**实施影响点:**

- `packages/graph-agent/tests/`
- `packages/graph-agent-gateway/tests/`
- `apps/studio/tests-e2e/test_run_flow.py:4`
- `apps/studio/tauri/README.md`

## §10 阻塞点 5: cache 累积 + golden 锁定 + 链式豁免 + 结构调整警告

**结论: 以本文为准.** Predict cache 多版本累积. Golden 是用户标记锁定的阶段性目标, 不被链式失效覆盖.

**PM 拍板原话:** "golden 应该不受上面说的链式反应的影响, golden 应该是一个阶段性的结果目标, 除非 golden 前面的节点进行了结构性的大调整, 从逻辑上推理不可能得到 golden 的结果"

**字段级技术约束:**

- cache 按 prompt/input 变化自然累积多版本.
- golden 是用户标记锁定的"最后一版"目标, 不被新 predict 自动覆盖.
- golden 不受链式失效影响; 它不是普通 transient cache entry.
- 当 golden 前节点发生结构性大调整时, predict 触发 Copilot 轻量预测.
- 若轻量预测判断偏差大, 返回 warning, 不静默复用 golden.
- warning 需要能进入 `RunResult` / diagnostics, 供 Studio 展示.

**结构性大调整 = 3 类信号 (任一触发, prompt 纯文本微调不触发):**

1. **IO Schema 突变**: 字段增 / 删 / 改名 (数据血液断供).
2. **拓扑结构重排**: 前序依赖节点删除 / 类型异变 (`LOGIC` ↔ `LLM` ↔ `SUBGRAPH`).
3. **Role 变更**: 差异极大角色定位变, 例如"前端画图角色 → SQL 专家".

**warning 字段挂载**: `RunResult.path_diff.structural_mismatch` (扩展 `PathDiff` 现有 `missing` / `extra` / `order_mismatch`).

- file:line 实证: `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:37-44` 当前定义 `PathDiff.expected_path` / `actual_path` / `missing` / `extra` / `order_mismatch`.

**实施影响点:**

- `packages/graph-agent/src/graph_agent/core/_predict_internal/strategy.py:108-194`
- `apps/studio/backend/app/services/predictor.py:138-160`
- `apps/studio/backend/app/services/golden_diff.py:34-64`
- `apps/studio/backend/app/models/golden.py:10-20`
- `apps/studio/frontend/src/hooks/useGoldenDiff.ts:39-49`

## §11 阻塞点 6: 旧 tests 砍 + 写新 tests

**结论: 以本文为准.** Round 31 cutover 后, round-29/30 旧 API 假设 tests 已过时. Cutover PR 内一起写新 tests、砍过时旧 tests.

**PM 拍板原话:** "旧 tests 砍 + 写新 tests"

**字段级技术约束:**

- 不允许旧 API 假设 tests 与新代码长期并存.
- 删除或重写仍断言 `trace_dir`, callback class inheritance, `PredictResult`, `.workspace/predict`, SDK LLM config 的 tests.
- 新 tests 以本文档为断言基线.
- 新 tests 必须覆盖: Gateway LLM config ownership, `workspace_dir` 必传, trace 默认落盘, `event_subscriber`, predict cache 链式失效, golden 锁定.

**实施影响点:**

- `packages/graph-agent-gateway/tests/test_model_resolver_protocol.py:240`
- `packages/graph-agent/tests/core/test_predict_internal_imports.py:20`
- `apps/studio/backend/tests/test_skill_git_p0.py:40-44`
- `apps/studio/backend/tests/test_api.py:167-170`
- `apps/studio/tests-e2e/test_run_flow.py:4-101`

## §12 Gateway 不管业务

**结论: 以本文为准.** Gateway 不拥有业务决策. callable 注入不算 import 依赖. Gateway 包绝不能 import Studio 任何东西.

**PM 拍板原话:** Gateway 不管业务.

**字段级技术约束:**

- Gateway 不 import `apps.studio`.
- Gateway 不 import Studio models, services, routers, settings store.
- Gateway 可接收 Studio 传入的 callable.
- Gateway 只知道 callable signature 和返回 payload contract.
- Gateway 不拥有 predict cache, golden, ABC, skill workspace 业务决策.
- Gateway 只负责 provider/model/role 与 chat/predict model facade.

**实施影响点:**

- `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:74`
- `packages/graph-agent-gateway/src/graph_agent_gateway/protocol.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py`
- `apps/studio/backend/app/services/copilot.py:188-228`

## §13 黄金原则 — round-31 演进版

**结论: 以本文为准.** 砍 API 符号 OK, 但能力必有去向 (`error_code` / Gateway / facade / internal implementation). 真砍 user 可见能力必 PM 拍板, 按本文 §16 真砍清单执行.

round-31 任务目标 = "API catalog rightsizing 60+ -> 浓缩到优雅", 本质是砍 API. 5-27 立"功能一个都不能少"黄金原则是上一阶段优化评分时的保护规则, round-31 立项要调整 API 时不适用.

**字段级技术约束:**

- API symbol 删除不等于能力删除; 必须写清能力迁往 Gateway、Studio HTTP、SDK internal 或新 facade.
- Round-31 任务目标是 API catalog rightsizing, 允许在本文 §16 拍板范围内真砍 API; "功能一个都不能少" 黄金原则不适用于 round-31 已立项的 API 浓缩项.
- 真正用户能力消失只能发生在 §16.1、§16.2、§16.3.
- 发现未列入 §16 的用户可见能力被删除, PR 必须停止 escalate PM.
- 旧 internal import 被封装不是砍能力, 前提是有 facade 替代.
- Round-31 实施完成后的后续 round 仍适用黄金原则: 新增砍项必须有去向并重新 PM 拍板.

**实施影响点:**

- `.kiro/specs/engine-mvp0-rebuild-v030/round-31-api-surface-rightsizing/research.md:1-88`
- `.kiro/specs/engine-mvp0-rebuild-v030/round-31-api-surface-rightsizing/design.md:1-429`
- `docs/engine/public-api-contract.md:20-515`

## §14 copilot 接口在 Studio (业务)

**结论: 以本文为准.** Copilot 接口属于 Studio 业务. Gateway 通过 callable 注入使用它.

**PM 拍板原话:** copilot 接口在 Studio (业务).

**字段级技术约束:**

- Studio 启动 predict 时给 Gateway 传一个"模拟用 callable"当工具.
- Gateway 内部 predict chat model 调这个 callable.
- callable 注入不产生 Gateway -> Studio import.
- Gateway 不持久化 Copilot 输出; SDK 决定是否写 predict cache.
- Studio 可继续拥有 Copilot WebSocket、system prompt、tool allowlist、UI context.

**实施影响点:**

- `apps/studio/backend/app/services/copilot.py:65-228`
- `apps/studio/backend/app/models/copilot.py:9-21`
- `apps/studio/frontend/src/hooks/useCopilot.ts:25-119`
- `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:74`
- `packages/graph-agent/src/graph_agent/core/_predict_internal/interception.py:42-54`

## §15 decisions.md 是唯一权威源

**结论: 以本文为准.** 所有 audit / review / 实施 / 排查歧义以本文档为准.

**PM 拍板原话:** "现在的这些决策点需要写明确的决策文档, 实施后要对齐"

**字段级技术约束:**

- 旧文档冲突就地标 `[OBSOLETE 看 round-31/decisions.md §X]`.
- `design.md` 后续修订必须对齐本文.
- `tasks.md` 后续拆任务必须引用本文对应 §.
- code review 发现实现与本文冲突, 按 bug 处理.
- 本文只由 PM 新拍板或主控明确指令修订.

**实施影响点:**

- `.kiro/specs/engine-mvp0-rebuild-v030/round-31-api-surface-rightsizing/decisions.md`
- `.kiro/specs/engine-mvp0-rebuild-v030/round-31-api-surface-rightsizing/design.md`
- `.kiro/specs/engine-mvp0-rebuild-v030/round-31-api-surface-rightsizing/research.md`

### §15.1 R3 已知冲突清单

以下冲突实施时必须就地加 `[OBSOLETE 看 round-31/decisions.md §X]` 或按处置建议删除/替换:

| # | 冲突位置 | 冲突内容 | 处置建议 |
|---|---|---|---|
| 1 | `docs/engine/tracing-and-observability/baseline.md:92` | `TracingCallback(trace_dir=...)` 作为用户配置 trace 的方式 | 加 OBSOLETE banner, 指向 §2 / §3 / §16.1 / §16.3 |
| 2 | `docs/engine/public-api-contract.md:155-160` | `TracingCallback.__init__(trace_dir=...)` 仍作为 public API | 整段 OBSOLETE, 改为 `event_subscriber` callable |
| 3 | `docs/engine/public-api-contract.md:498` | `PredictResult` 仍作为 public entity | 整段 OBSOLETE, 改为 `RunResult(source="predict")` |
| 4 | `docs/studio/system-level/workspace-file-system/baseline.md:365-368` | 旧 `.workspace/predict/` 顶层子目录 | 删除旧目标态; 当前文档应只引用 Engine workspace spec 与 `<workspace_dir>/runs/<run_id>/` |
| 5 | `docs/architecture/prod-dev-separation/baseline.md:61` | Studio/Engine tracing callback 缠绕仍按旧 callback class 描述 | 局部 OBSOLETE, 指向 §3 / §16.3 |
| 6 | `.kiro/specs/_archive/predict-v2/design.md:105` | `PredictResult` schema | 文件顶加 OBSOLETE banner, 指向 §4 / §7 / §16 |

## §16 round-31 用户能力调整清单

**结论: 以本文为准.** Round 31 真砍用户能力包括 §16.1 trace 路径自定义、§16.2 Exception API 浓缩、§16.3 Callback class 继承. §16.2 supersedes f00d4d0 ADD-only framing.

### 16.1 trace 路径自定义

**PM 拍板:** Q4.

**砍掉什么:** 用户不能再选 trace 写哪, 不能传 `trace_dir`, 不能通过 `TracingCallback(trace_dir=...)` 指定路径.

**目标去向:** SDK 强制写 `<workspace_dir>/runs/<run_id>/trace.jsonl`.

**影响点:**

- `packages/graph-agent/src/graph_agent/core/runner.py:63`
- `packages/graph-agent/src/graph_agent/core/runner.py:235-239`
- `packages/graph-agent/src/graph_agent/callbacks/tracing.py:61-85`
- `apps/studio/backend/app/services/run_manager.py:230-235`

### 16.2 Exception API 浓缩 24 -> 5 public

> **[SUPERSEDES f00d4d0 ADD-only — round-31 任务目标 = 砍 + 黄金原则不适用]**

**PM 拍板:** PM (2026-05-30) 澄清 round-31 真任务是 API catalog rightsizing, 60+ -> 浓缩到优雅, 本质是砍 API; 5-27 "API 一个不能少" 黄金原则不适用于 round-31 已立项 API 浓缩.

**砍掉什么:** Exception public catalog 从约 24 个公开 class 浓缩为 5 个 public class. 约 22 个细粒度具体 class 从 `graph_agent.__init__` de-export, 不再作为 public isinstance catch 面承诺.

**最终 public class:**

- `GraphAgentError`
- `GraphCompileError`
- `GraphExecutionError`
- `ModelProviderError`
- `ResourceNotFoundError`

**family 映射:**

- `GraphCompileError`: `SkillCompilationError` / `SkillLoadError` / `SkillParseError` / `SkillModuleLoadError` / `PhaseBuildError` / `SkillCompileError` / `ValidationError` / `SchemaValidationError` / `ContractValidationError` / `LoaderError` / `TemplateRenderError`.
- `GraphExecutionError`: `ExecutionError` / `PhaseExecutionError` / `StateTransformError` / `ToolExecutionError` / `PersistenceError` / `CheckpointError` / `TraceWriteError` / `ArtifactError` / `MaxRetriesExceededError` / `GraphAgentFatalError`.
- `ModelProviderError`: `GatewayError` / `AllProvidersFailedError` / `GatewayResolverMissingError` / `GatewayRoleNotConfiguredError`.
- `ResourceNotFoundError`: `SkillResolutionError` 与 resource-not-found payload errors.

**字段级技术约束:**

- 4 个 family class 全部直接继承 `GraphAgentError`.
- 约 22 个具体 class 内部实现可保留并继续用于 internal raise/wrap, 但从 public `graph_agent.__init__` de-export.
- 细粒度去向不是 leaf class, 而是 `ErrorPayload.code` + `ERROR_REGISTRY` 中的 `[F-v3-*]` code.
- `RunResult.error` / `WorkflowResult.error` 必须升级为承载 `ErrorPayload` 或等价字段组 (`error_code`, `error_context`), 至少包含 `code` / `level` / `stage` / `field_path` / `doc_link`, 否则 run-result 路径拿不到被砍 leaf class 的颗粒度.
- Studio backend catch tuple 从 `SkillLoadError` / `SkillCompilationError` 迁到 `GraphCompileError` / `ResourceNotFoundError` 等 family class; Studio 不依赖具体 class 做控制流分流.
- Gateway `GatewayError` 改继承 `ModelProviderError`; Gateway 4 个 provider 子类可保留 internal, public 面由 Gateway 包另行决定, SDK public catalog 不导出这些 leaf.
- 现有 tests 中依赖具体 class 的 `pytest.raises` / `except` / `isinstance` 迁到 family class + `ErrorPayload.code` 断言.

**目标去向:** 用户从 catch 细粒度 leaf class 改为 catch 4 个责任归属 family class; 子颗粒度通过 `ErrorPayload.code` + `ERROR_REGISTRY` 读取.

**影响点:**

- `packages/graph-agent/src/graph_agent/core/exceptions.py:82-338`
- `packages/graph-agent/src/graph_agent/core/error_registry.py`
- `packages/graph-agent/src/graph_agent/core/result.py:57`
- `packages/graph-agent/src/graph_agent/__init__.py:37-39`
- `packages/graph-agent/src/graph_agent/__init__.py:68-70`
- `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:7-13`
- `apps/studio/backend/app/services/skills.py:20,304,327,1152`

### 16.3 Callback class 继承

**PM 拍板:** Q4.

**砍掉什么:** 用户不能继承 `AgentCallback` / `Callback` / `TracingCallback` / `EventStreamCallback` 类做自定义事件处理类.

**目标去向:** 传 callable 函数 `event_subscriber(event: CallbackEvent) -> None`.

**影响点:**

- `packages/graph-agent/src/graph_agent/callbacks/base.py:139`
- `packages/graph-agent/src/graph_agent/callbacks/tracing.py:58`
- `packages/graph-agent/src/graph_agent/__init__.py:31-34`
- `apps/studio/backend/app/services/run_manager.py:89-95`
- `apps/studio/backend/app/services/run_manager.py:230-235`
