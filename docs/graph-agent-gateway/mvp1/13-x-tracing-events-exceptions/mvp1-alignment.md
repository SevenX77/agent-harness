---
module: 13-x-tracing-events-exceptions
doc: mvp1-alignment
status: drafted
verified_at: 2026-08-11
binds_code: packages/graph-agent-gateway/src/graph_agent_gateway/events.py:LLMRouteDecisionEvent/LLMCallSettingsEvent/RouteDecision/ROUTE_DECISION_EVENT_CODE/CALL_SETTINGS_EVENT_CODE/model_dump · packages/graph-agent-gateway/src/graph_agent_gateway/errors.py:GatewayError/AllProvidersFailedError/GatewayResolverMissingError/GatewayRoleNotConfiguredError · packages/graph-agent-gateway/src/graph_agent_gateway/call/tracing.py:build_route_decision_event/emit_route_decision_event/emit_call_settings_event · packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:GatewayChatModel/_decided/_said_what_happened · packages/graph-agent-gateway/src/graph_agent_gateway/call/outcome.py:SettingOutcome/judge_settings · packages/graph-agent-gateway/src/graph_agent_gateway/resolve/error_classification.py:classify_exception/ErrorClassification
units: [tracing-events-exceptions]
aligns_with: ../README.md · ../DESIGN_UNITS_INDEX.md
---

# 13 — Tracing / Events / Exceptions（横切：网关说出自己做了什么）· MVP1 设计

> **组织方式**：**以每个功能为索引** —— 每个功能（F1–F4）一段，把它的机制/数据流·决策+动机·原话·测试点·status·归属（region/platform）**全收在自己段里**；仅「定义」「接口契约」是模块级总览，模块级证据附录（已实现/差异、覆盖代码、代码索引）放在文末。现状基线见同目录 `baseline.md`。
> **Tier**：③b gateway 公共能力内核（事件 DTO / 异常类 / 发射 helper 全在 `packages/graph-agent-gateway` 包内，**无反转、无下沉**）
> **Owns**：**路由决策事件**（这次调用挑了谁、跳过谁、为什么换、最后谁答的）、**调用设置事件**（这次调用要求了哪些设置、每一项落到什么下场）、**三类结构化异常**（语义 + 触发点）、**发射边界**（听众自己出错，不许盖住这次运行本身的错）
> **Status**：设计定稿（2026-08-11 按 `docs/design/2026-08-09-streaming-tracing-architecture-decision.md` D10 重写：**原来的 fallback 事件已被路由决策事件取代并删除**；调用设置事件按 `docs/design/2026-08-10-runtime-settings-are-preferences-decision.md` 落地）；代码 = 已实现并有测试覆盖。逐句差异见文末「原文与今天的差别」。
> **Related**：[[01-handoff-interface]]（`ResolvedRoute` 契约，事件的路由身份直接取自它）· [[06-orch-error-classification]]（`classify_exception` 语义源，本模块只触发不重定义）· [[07-orch-fallback-circuit-probe]]（候选循环本体，本模块是它的可观测输出 + 异常出口）· [[09-inv-invocation-runtime]]（一次调用怎么发出去、答案怎么读回来）
> **决策日志**：`docs/design/2026-08-09-streaming-tracing-architecture-decision.md` **D10**（路由决策是一件事不是七件；`llm_fallback` 被取代并删除；作废是决策的字段不是第八种决策；这一族是步骤帧走既有 `CallbackEvent` 通道；两处定义是依赖方向的结果）+ **D9-b**（重试作废已流出的片段）· `docs/design/2026-08-10-runtime-settings-are-preferences-decision.md`（设置是偏好；每项设置的下场怎么判）· 早期 client 层 A' 重设计决策 **D1**（保留编排外壳，不删 `GatewayChatModel`）+ **M5**（401/402/403/404 = fallback 非 fail-fast，权威源 [[06-orch-error-classification]]）· 归属表 `docs/graph-agent-gateway/mvp1/module-disposition-revised.md`（13 = 纯 ③b 公共，不变）。
> **现状**：见同目录 `baseline.md`

## 定义

本模块是 Gateway 的横切观测/异常底座。它不决定任何事，只负责**把已经决定了的事说出去**，以及**把说不下去的情况表达成可读的异常**。四个 ③b 公共能力（即下文 F1–F4）：

- **路由决策事件**（`LLMRouteDecisionEvent`，见 **F1**）：网关为一个角色取答案的过程里，每一次跳过、探问失败、丢设置重试、同路由重试、加预算重来、换路由、终止、答出、全灭，都是**同一类事实的不同取值**，用一个封闭枚举字段 `decision` 表达。**判据归属 ③b 公共**——任何调模型的 app 都需要"这次到底走了哪条路、为什么改路"的可观测输出，不依赖应用加工四件事（① UI ② 产品策略 ③ 调用方式 ④ 存储介质）。
- **调用设置事件**（`LLMCallSettingsEvent`，见 **F4**）：这次调用**要求**了哪些设置，每一项的下场是"生效 / 发了但无从确认 / 被挪过 / 这条协议根本带不了 / 被 provider 拒了 / 答案与要求相矛盾"。它回答的是与 F1 不同的问题——F1 说"谁答的"，它说"在什么参数下答的"。
- **结构化异常**（`GatewayError` 基类 + 三个子类，见 **F2**）：把"role 没配 / DI 缺 resolver / 候选链全失败"表达成带稳定 `code` 和机器可读 `context` 的异常，供 Studio/trace 读字段，而不是解析自由文本。
- **发射边界**（`emit_route_decision_event` / `emit_call_settings_event`，见 **F3**）：逐个调听众的 `on_event`；某个听众自己抛异常只记日志，**不向上传播**——观测层是旁路，不该让一个坏听众把真实的模型调用错误吞掉或顶替。

**上下游总览（跨 F1–F4 的同一条脊柱）**：候选循环 `GatewayChatModel._answer`（[[07-orch-fallback-circuit-probe]]）每走到一个可观察的时刻 → 调 `classify_exception`（[[06-orch-error-classification]]）拿到分类 → 调本模块的 `_decided(...)` 发一条路由决策事件（F1，经 F3 的发射边界）；答案收口时另调 `_said_what_happened(...)` 发一条调用设置事件（F4）；走不下去时抛 `AllProvidersFailedError`（带 `failed_provider_codes` + `last_error_chain`，F2）。

## 接口契约（模块级，跨功能共享）

| 边界 | 契约 |
|---|---|
| **③b → tracing 底座（发射）** | `emit_route_decision_event(*, callbacks, phase_name, decision, route=None, reason=None, provider_status_code=None, next_route_id=None, voided_streamed_answer=False)` 与 `emit_call_settings_event(*, callbacks, phase_name, route, outcomes)`：逐个调 `callback.on_event(event)`；单个听众抛异常 → 仅 `logger.exception`（`phase=gateway_tracing action=callback_failed`），继续发给后续听众，**不向上传播**。`emit_call_settings_event` 在 `outcomes` 为空时直接返回——没有用户选过的设置就没有话要说。 |
| **`LLMRouteDecisionEvent` payload** | `phase_name` · `decision`（**封闭枚举**，见 F1 九种取值）· `route_id`/`endpoint_id`/`provider_model_id`/`protocol`（路由身份，由 `build_route_decision_event` 直接从 `ResolvedRoute` 上取，**不含密钥**）· `reason`（异常类型+消息，或人话说明）· `provider_status_code`（分类器读到的 HTTP status；404 与 503 读起来完全不是一回事，光看 `reason` 得让读者自己去解析）· `next_route_id`（要换到哪条）· `voided_streamed_answer`（这次决策是否还丢弃了**已经流出去的**内容）· `code` = `[F-v3-gateway-llm-route-decision]`、`event_type` = `llm_route_decision`（两者都 `init=False`，调用方不能传）。`model_dump()` 序列化以上全部。 |
| **`LLMCallSettingsEvent` payload** | `phase_name` · `settings`（每项一个 `SettingOutcome.model_dump()`：`setting`/`requested`/`verdict`/`reason`）· `route_id`/`provider_model_id`/`protocol` · `code` = `[F-v3-gateway-llm-call-settings]`、`event_type` = `llm_call_settings`（`init=False`）。 |
| **异常对外契约（③b → Studio/trace）** | 三类异常均继承 `GatewayError`（稳定 `code` + 机器可读 `context`）：① `GatewayRoleNotConfiguredError`{`role_name`,`model_override`} = 编排期 role/route override 不可解析；② `GatewayResolverMissingError`{`phase_name`,`required_dependency=model_resolver`} = LLM phase 缺 DI；③ `AllProvidersFailedError`{`role_name`,`phase_name`,`failed_provider_codes`,`last_error_chain`} = 执行期候选链全失败 / 不可回退分类的包装。上层读字段，不解析自由文本。 |
| **事件形状在两侧各有一份，这是依赖方向的结果** | `packages/graph-agent-gateway/pyproject.toml` 的依赖只有 langchain-core / langchain-openai / langchain-anthropic / pydantic——**网关不依赖引擎**，因此它无法引用引擎的事件契约。网关侧是自带 `model_dump` 的 dataclass，引擎侧是进入 `CallbackEvent` 判别联合的 Pydantic 变体，两份形状**靠人工保持同步**。这不是待消除的重复（D10-d）。 |
| **归属 / 稳定性** | 事件/异常/发射 helper 全在 `packages/graph-agent-gateway`（③b 公共），**无下沉项**；错误分类语义（哪个 status → 回退/终止）权威源 = [[06-orch-error-classification]]，本模块只触发不重定义；每项设置判成什么 verdict 的语义归 `call/outcome.py`（决策见 2026-08-10 偏好决议），本模块只负责把判完的结果发出去。 |

---

## 功能逐项（每个功能为索引）

### F1 路由决策事件（`LLMRouteDecisionEvent`：一种事件，九种取值）

- **机制 / 数据流**：候选循环 `GatewayChatModel._answer` 遍历 `resolved_role.routes`，每到一个可观察的时刻就调 `self._decided(...)`（`call/chat_model.py:557`），后者把这次模型的 `phase_name` 和听众绑上去，交给 F3 发射。九种取值与各自的触发点（坐标为 `call/chat_model.py`）：

  | `decision` | 说的是哪件事 | 触发点 |
  |---|---|---|
  | `skipped_circuit_open` | 这条候选**先前**已被熔断，这次连试都不试 | `:300` |
  | `probe_failed` | 前置探问没答上来，这条候选出局并熔断 | `:341` |
  | `dropped_rejected_settings` | provider 拒的是**某项设置**而不是这条路由，去掉它再问同一条 | `:352`（探问侧）、`:469`（调用失败侧） |
  | `retried_same_route` | 分类判定为"同一条再来一次" | `:444` |
  | `escalated_budget` | 答案被 `max_tokens` 截断，预算加倍重来 | `:405` |
  | `fell_back` | 这条失败且允许回退，换下一条 | `:496` |
  | `failed_terminal` | 分类判定不可回退，当场抛 | `:328`（探问侧）、`:482`（调用侧） |
  | `answered` | 最终由这条路由答出来了 | `:433` |
  | `exhausted` | 候选全部失败 | `:507` |

  路由身份不是调用点一个个填的：`build_route_decision_event`（`call/tracing.py:20`）直接从 `ResolvedRoute` 上取 `route_id`/`endpoint_id`/`provider_model_id`/`protocol`，所以事件里的路由与真正被调用的路由不可能对不上。
- **决策 + 动机**：
  - **一种事件，不是七种**：D10-a 逐条以代码坐实过——除"跨路由回退"外，跳过熔断、熔断本身、同路由重试、升配重试、内容作废、最终落点、全灭，当时**一个事件都没有**。这六项不是六件事，是同一件事的六种取值；各加一种事件会让前端为同一族事实写六处渲染，而且第七种决策出现时还得再改一次契约。所以判别字段是**封闭枚举**（呼应 AGENTS.md「让非法状态不可表示」）。
  - **作废不是一种决策，是决策的后果**：升配会作废、回退会作废，而"作废"本身不是一个独立时刻。所以它是决策事件上的一个布尔字段 `voided_streamed_answer`，不是第八种取值。**读的顺序有要求**：`attempt.void()` 会清标志，所以升配那一处先把 `attempt.streamed` 读进 `voided`（`call/chat_model.py:403`），发完事件才调 `void()`（`:411`）。
  - **`llm_fallback` 是被取代，不是被并存**：依 AGENTS.md「No backward compatibility」，同一个变更里删掉它在网关与引擎的两处定义、以及前端对它的专门分支，不留双读、不留别名。
  - **这一族是步骤帧，不是增量帧**：低频、有界、且**运行结束后回看仍然提供信息**（这次在哪条路由上重试过、熔断过什么、最终由谁回答），所以走引擎既有的 `CallbackEvent` 通道，落盘、占 seq、进 `report.md` 与取证查询。
- **原话**：
  > **D10-b**（`docs/design/2026-08-09-streaming-tracing-architecture-decision.md:571-583`，本文留底）："上面缺的六项不是六件事，是**同一件事的六种取值**：gateway 在这次调用里做了一个路由决策。为每一项各加一种事件，会让前端为同一族事实写六处渲染，并且第七种决策出现时还要再改一次契约。因此定义**一种**事件，用一个判别字段说明是哪种决策，取值是一个封闭枚举……`llm_fallback` 是这一族里已经实现的那一种取值。依「No backward compatibility」，新事件**取代**它：同一个变更里删掉 `llm_fallback` 的两处定义与前端对它的专门分支，不留双读、不留别名。**「作废」不是一种决策，是决策的后果。**"

  > **D9-b**（同文件 `:529-539`，本文留底）："**gateway 在重试之前，先发出一片「作废」标记；累积答案的一方收到它就丢弃已累积的内容。**……作废标记是**显式的类型化字段**，不是元数据里的魔法键。"
- **测试点**：
  - **每一种取值都能被构造出来并断言到**：D10-a 表中标为"没有"的六项，每一项都能在一次运行的事件流里找到对应的决策事件（验收判据 2-d）。
  - **最终落点可读**：一次真实运行的 trace 里能读出"这次回答最终由哪条路由 / 哪个端点给出"（验收判据 2-f）——即 `answered` 那一条带完整路由身份。
  - **取代干净**：`llm_fallback` 在 `packages/graph-agent-gateway/src`、`packages/graph-agent/src`、`apps/studio/frontend/src` 三处全域 grep 为零（验收判据 2-e）。
  - **作废标志属于造成它的那次决策**：升配与回退发出的事件带 `voided_streamed_answer=True`，且升配那一处读到的是**清标志之前**的值。
- **status**：已实现（`events.py:LLMRouteDecisionEvent` + `call/tracing.py:build_route_decision_event`），九种取值全部有触发点。
- **归属**：③b `packages/graph-agent-gateway`：`events.py`（事件 DTO）、`call/tracing.py`（构造）、`call/chat_model.py:_decided`（触发点）。region/platform N/A（本模块无 ③a 应用加工成分；② Rust N/A）。

### F2 异常类型语义（各 exception 类型与触发点）

- **机制 / 数据流**：与 F1 共享同一条候选循环。分类判定不可回退时 → 先发 `failed_terminal`，再 `_raise_all_providers_failed(...)` 抛 `AllProvidersFailedError`（`call/chat_model.py:328-350`、`:482-494`）；候选走完仍无答案 → 发 `exhausted` 再抛同一个异常（`:507-512`）。异常本体在 `errors.py`：`GatewayError:13`（基类，持稳定 `code` + `context`）· `AllProvidersFailedError:33`（带 `failed_provider_codes` + `last_error_chain`）· `GatewayResolverMissingError:63` · `GatewayRoleNotConfiguredError:77`。
- **决策 + 动机**：
  - **结构化异常替代纯文本 `RuntimeError`**，是为了 Studio/trace 能读 `last_error_chain` 而不是解析自由文本。
  - **异常与事件不重复**：不可回退分支既抛异常又发一条 `failed_terminal` 事件——两者不是重复：**事件说"发生了这一步"，异常说"这次调用到此为止"**。事件进事件流供回看，异常沿调用栈把结果交给调用方。
  - **异常分类不变**：M5 明确 `classify_exception` 沿用，并纠正 401/402/403/404 是回退不是 fail-fast（原话见下）。分类语义本身归 [[06-orch-error-classification]]，本模块只在分类结果上发事件/抛异常。
- **原话**：
  > **M5 — 错误分类真实语义**（client 层 A' 重设计决策，纠正多处文档错误简写，本文留底）。**真实语义**：**401 / 402 / 403 / 404 = fallback（credential/route scope），不是 fail-fast！**（429/500/502/503/504/529、网络错、400+capability 标记同为 `fallback_allowed`；400 非 capability / 413 / 422 才 `fail_fast`；未知 → `fail_fast_with_route_context`）。写测试时必须按真实语义验证，不能沿用旧简写。**M5 是跨模块共享决策，权威语义源 [[06-orch-error-classification]]**（`resolve/error_classification.py`）。
- **测试点**：
  - **结构化异常 payload**：`AllProvidersFailedError` 暴露 `failed_provider_codes` 和 `last_error_chain`（上层读字段，非解析文本）。
  - **异常仍可分类**：provider SDK 抛出的异常仍能被 `classify_exception` 读到 status code 与 chained exception，否则回退/终止判定失准。
  - **真实语义防回归**：401/402/403/404 → 发 `fell_back` 并试下一条；400（非 capability）/413/422 → 发 `failed_terminal` 并抛。
- **status**：三类结构化异常已实现（`errors.py`）；语义保留，只是触发点旁边多了一条对应的决策事件。
- **归属**：③b `packages/graph-agent-gateway`：`errors.py`（异常类）、`call/chat_model.py:_answer`（抛异常触发点）。region/platform N/A。

### F3 发射边界（听众出错不许盖住这次运行的错）

- **机制 / 数据流**：两个发射 helper 同一个形状（`call/tracing.py:45` 与 `:76`）：逐个 `callback.on_event(event)`，用 `try/except Exception` 包住，失败只 `logger.exception("phase=gateway_tracing action=callback_failed callback=%s", ...)`，继续发给下一个听众。网关自己调它们，**不让 provider SDK 直接接触网关的 callback**。
- **决策 + 动机**：
  - **观测层是旁路**。一个坏听众可以让自己收不到事件，但不能让这次真实的模型调用失败被它顶替或吞掉——否则读 trace 的人看到的是观测层的错，真正的失败反而不见了。
  - **只吞听众自己的异常**：`except` 落在**单个听众**这一圈里，不是包住整个发射；所以一个听众炸了，后面的听众照收。
- **原话**：本条的边界要求由 D1（保留编排外壳、发射归编排层）与 D10-c（这一族事件走引擎既有 `CallbackEvent` 通道）共同支撑；无独立的额外用户原话。
- **测试点**：
  - **一个听众抛异常，后面的听众仍然收到同一个事件**（回归点 `packages/graph-agent-gateway/tests/test_route_decision_events.py:test_a_failing_listener_does_not_stop_the_others_from_hearing`）。
  - **事件码不是调用点能选的**：`code` / `event_type` 是 `init=False` 的固有常量，构造时传它会 `TypeError`（回归点同文件 `test_the_event_code_is_not_something_a_call_site_chooses`）。
- **status**：已实现，两个 helper 共用同一条发射语义。
- **归属**：③b `packages/graph-agent-gateway`：`call/tracing.py`。事件的订阅者与持久化是消费方的事，不在本模块。

### F4 调用设置事件（`LLMCallSettingsEvent`：这次调用在什么参数下答的）

- **机制 / 数据流**：答案收口后（不是请求发出时）调 `_said_what_happened(...)`（`call/chat_model.py:427` 触发、`:536` 定义），把这次调用**实际报出的设置**交给 `judge_settings`（`call/outcome.py`）判成一串 `SettingOutcome`，再由 F3 的 `emit_call_settings_event` 发出去。**发在收口而不是发出时**，是因为其中一种判定——"要了推理却一个字都没推"——只有读到答案才知道。
- **决策 + 动机**：
  - **与 F1 分开，是因为它们回答不同的问题**：F1 说"用了哪条路由、为什么改"，F4 说"在什么参数下答的"。两个问题，两个各自独立的改动理由。
  - **只判用户选过的**：provider 的默认值没人挑过，不算偏好；一张大半是默认值的表，会把真正重要的那几行淹掉。
  - **`sent` 是诚实的答案**：很多设置的效果，响应里根本没有任何东西能证实；报成"已生效"是没人核过的断言，报成"被忽略"是没人拿得出证据的指控。`ignored` 只留给**答案本身与要求相矛盾**的那一种。
- **原话**：
  > `call/outcome.py` 文件头（本文留底）："``sent`` is the honest answer for the many settings whose effect nothing in the response can confirm: reporting them as applied would be a claim nobody checked, and reporting them as ignored would be an accusation nobody can support. ``ignored`` is reserved for the case where the answer actively contradicts the request."
- **测试点**：
  - **一项设置都没人选过时，不发这条事件**（`emit_call_settings_event` 对空 `outcomes` 直接返回）。
  - **判定发生在能读到答案之后**：要了推理而答案里没有推理内容 → `ignored`；答案无从证实的设置 → `sent`。
- **status**：已实现（`events.py:LLMCallSettingsEvent` + `call/tracing.py:emit_call_settings_event` + `call/outcome.py:judge_settings`）。
- **归属**：③b `packages/graph-agent-gateway`：`events.py`（DTO）、`call/tracing.py`（发射）、`call/outcome.py`（判定语义，权威决策 = 2026-08-10 偏好决议）。

---

## gaps / 待设计

- **疑点**：`AllProvidersFailedError` 同时承载"全候选失败"和"不可回退分类后的结构化包装"，命名是否需要细化，待主控判断。
- **核实项**：网关侧 dataclass 与引擎侧 Pydantic 变体是**人工保持同步**的两份形状（D10-d）。今天没有任何门禁会在两边形状漂开时报警——这一条是已知的、被决议接受的代价，不是遗漏；要不要为它加一道形状比对门禁，属于三模块架构范围，本模块不自行决定。

## 交叉引用（双向链接，不复制）

- [[01-handoff-interface]]：`ResolvedRoute`/`ResolvedRole` 契约（事件的路由身份直接取自同一份 route）
- [[06-orch-error-classification]]：`classify_exception` 真实语义（401/402/403/404 = 回退），本模块只触发不重定义
- [[07-orch-fallback-circuit-probe]]：候选循环本体（本模块是它的可观测输出 + 异常出口）
- [[09-inv-invocation-runtime]]：一次调用怎么发出、答案怎么读回（决策事件的时刻由它划出）
- **流式/取证决议 D9 / D10**：`docs/design/2026-08-09-streaming-tracing-architecture-decision.md`；**设置即偏好决议**：`docs/design/2026-08-10-runtime-settings-are-preferences-decision.md`；归属表 `docs/graph-agent-gateway/mvp1/module-disposition-revised.md`

---

## 模块级证据附录

### 已实现 / 与 baseline 差异

| 项 | baseline 现状 | MVP1 alignment | 功能 |
|---|---|---|---|
| 事件 DTO | 曾是 `LLMFallbackEvent`（只说"回退"这一种时刻）。 | 已被 `LLMRouteDecisionEvent` 取代并删除：同一族事实一种事件、九种取值。 | F1 |
| 决策覆盖面 | 只有跨路由回退发事件；跳过熔断、熔断、同路由重试、升配重试、内容作废、最终落点、全灭都静默。 | 九种取值全部有触发点，静默项清零。 | F1 |
| 作废已流出的内容 | 不存在（流式引入后才成为问题）。 | 决策事件上的布尔字段 `voided_streamed_answer`，不是独立事件。 | F1 |
| 设置可见性 | 无。 | 新增 `LLMCallSettingsEvent`，答案收口时报每项设置的下场。 | F4 |
| 发射 helper | `emit_llm_fallback_event` 逐听众调 `on_event`，听众失败只记日志。 | 语义原样保留，落到 `emit_route_decision_event` / `emit_call_settings_event` 两个 helper 上。 | F3 |
| 异常 | 三类 Gateway 结构化异常（曾记为 `exceptions.py`）。 | 语义不变，文件是 `errors.py`；不可回退分支旁边多发一条 `failed_terminal` 事件。 | F2 |
| 错误分类 | 用 `classify_exception` 决定回退或终止。 | 继续沿用；分类语义权威源在 06，本模块只消费。 | F2 |

### 覆盖代码

| 覆盖项 | MVP1 目标 | 功能 |
|---|---|---|
| `packages/graph-agent-gateway/src/graph_agent_gateway/events.py:LLMRouteDecisionEvent`（路由决策事件 DTO：phase、决策取值、路由身份、原因、provider status、下一条、作废标志、固有事件码） | 继续作为网关自有的路由决策事件契约。 | F1 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/events.py:LLMCallSettingsEvent`（调用设置事件 DTO：phase、每项设置的下场、路由身份、固有事件码） | 继续作为"在什么参数下答的"的契约。 | F4 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/call/tracing.py:build_route_decision_event`（从 `ResolvedRoute` 取身份构造事件） | 路由身份不由调用点手填。 | F1 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/call/tracing.py:emit_route_decision_event` · `:emit_call_settings_event`（逐听众发射，听众自身异常只记日志） | 继续作为唯一发射边界，听众失败不影响主流程。 | F3 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:GatewayChatModel._decided` · `:_said_what_happened`（把 phase 与听众绑上去的两个触发点） | 触发点留在编排层，不下放给 provider SDK。 | F1/F4 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/call/outcome.py:judge_settings`（每项设置判成 applied/sent/adjusted/unsupported/rejected/ignored） | 判定语义归此处，本模块只发。 | F4 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/errors.py:GatewayError/AllProvidersFailedError/GatewayResolverMissingError/GatewayRoleNotConfiguredError` | 继续作为稳定 code/context 的结构化异常。 | F2 |

### 代码索引（clues）

- `events.py:ROUTE_DECISION_EVENT_CODE` = `[F-v3-gateway-llm-route-decision]`：路由决策事件专属码。（F1）
- `events.py:CALL_SETTINGS_EVENT_CODE` = `[F-v3-gateway-llm-call-settings]`：调用设置事件专属码。（F4）
- `events.py:RouteDecision`：九种取值的封闭枚举。（F1）
- `call/tracing.py:build_route_decision_event` / `:emit_route_decision_event` / `:emit_call_settings_event`：构造与发射。（F1/F3/F4）
- `call/chat_model.py:GatewayChatModel._answer`：候选循环，九个触发点都在里面。（F1/F2）
- `call/chat_model.py:GatewayChatModel._decided` / `:_said_what_happened`：两个触发入口。（F1/F4）
- `call/outcome.py:SettingOutcome` / `:judge_settings`：设置下场的判定。（F4）
- `errors.py:GatewayError` / `:AllProvidersFailedError` / `:GatewayResolverMissingError` / `:GatewayRoleNotConfiguredError`：结构化异常。（F2）
- `packages/graph-agent-gateway/tests/test_route_decision_events.py`：决策事件序列、听众失败不遮蔽、事件码不可由调用点选。（F1/F3）

---

## 原文与今天的差别

本节保留本文 2026-06-06 版的核心说法，并逐条写明今天为什么不是那样——**留底是为了让读者看得见改动本身**，不是为了兼容旧写法。

| 原文怎么写 | 今天怎么回事 |
|---|---|
| 标题与 Owns 写"**fallback 事件**"，全文以 `LLMFallbackEvent` 为主角，`code` 为 `[F-v3-gateway-llm-fallback]`。 | 该事件已被**取代并删除**（D10-b：`llm_fallback` 是这一族里已经实现的那一种取值）。今天是 `LLMRouteDecisionEvent`，回退只是它 `decision` 的九种取值之一（`fell_back`）。 |
| "事件/异常**字段结构**不改，只把 dispatch 那一步的'异常来源'从自研 dispatch 换成 ChatX invoke。" | 字段结构**整个换了**：`from_provider`/`to_provider`/`context` 字典这一套没有了，今天是扁平的 `route_id`/`endpoint_id`/`provider_model_id`/`protocol`/`next_route_id` + `provider_status_code` + `voided_streamed_answer`。D10 是在那句话之后两个月做的决定。 |
| gaps 里"✅ 已定（PM 2026-06-04，P4b=A）：`from_provider`/`to_provider` 字段名**保留**……留待未来事件 schema 版本升级再统一"。 | 那次"升级"就是 D10。字段名不再是"值是 route id 却叫 provider"，直接就叫 `route_id` / `next_route_id`。 |
| F3 段名为 `emit_llm_fallback_event`，回归点写 `test_llm_fallback_event.py:test_callback_failure_does_not_mask_fallback_event_delivery`。 | helper 是 `emit_route_decision_event` / `emit_call_settings_event`；该测试随事件一起搬进 `test_route_decision_events.py`，改名 `test_a_failing_listener_does_not_stop_the_others_from_hearing`（那份文件里留了原因注释：它是"宣布一个决策"的性质，不是"回退"这一种结果的性质）。 |
| 多处写异常在 `exceptions.py`。 | 文件叫 `errors.py`，类名与语义不变。 |
| 全文没有"调用设置"这回事。 | 2026-08-10「设置即偏好」决议之后新增 `LLMCallSettingsEvent`（F4）：这次调用要求了什么、每项落到什么下场，答案收口时报一次。 |
| "MVP1 只在调用层迁 ChatX 后保留触发位置"——触发点只有三处（探问异常、探问 false、dispatch 异常）。 | 触发点九处，且多出来的六处正是 D10-a 当年逐条坐实"今天没有"的那六项。 |
