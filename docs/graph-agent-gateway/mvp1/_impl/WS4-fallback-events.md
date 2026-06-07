---
ws_id: WS-4-fallback-event-code
modules: [13]
depends_on: [WS-1]   # 仅最后一步:删 gateway_chat_model.py 三处 code= 实参,须在 WS-1 提交、该文件脱离 dirty 之后
blocks: []
owns_files:
  # 生产代码
  - packages/graph-agent-gateway/src/graph_agent_gateway/events.py              # 改:LLMFallbackEvent.code → init=False 固有常量
  - packages/graph-agent-gateway/src/graph_agent_gateway/tracing.py             # 改:build/emit_llm_fallback_event 删 code 参数
  - packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py          # 本轮不改(回归断言对象,列入仅为边界完整 + 防误改全灭码)
  - packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py  # 仅删 :143/:181/:257 三处 code= 实参(排 WS-1 提交后)
  # 连带必改测试(因 DTO/helper 签名变更而 break,不改则套件红;跨 3 包)
  - packages/graph-agent-gateway/tests/test_llm_fallback_event.py
  - packages/graph-agent-gateway/tests/test_gateway_package_boundary.py
  - packages/graph-agent/tests/runner/test_event_subscriber_cutover.py
  - apps/studio/backend/tests/services/test_run_manager_gateway_events.py
spec_ssot:
  - ../13-x-tracing-events-exceptions/mvp1-alignment.md §F1 / gaps 第 1 条(PM 2026-06-04 P4a=B:拆专属 fallback event code)
status: drafted
---

# WS-4 fallback event 专属 code — 需求书(给 Codex)

> **流程定位**:本文是「给 Codex 的需求书」(`_impl/` 任务书),**不是**最终 kiro `tasks.md`。链路:
> **Claude 写本需求书 → Codex 写失败测试(RED) → 契约门(Claude 审「测试是否忠实编码目标」) → Codex 写 `.kiro/specs/graph-agent-gateway-mvp1/tasks-ws4-fallback-events.md` → Gemini 实现 → Codex 审到 §8 硬退出 → Codex 回写 baseline → Claude 终审**。
> **Codex 第一步**:请据本文 §6 写 RED 测试(此时实现尚未动,测试应红)。§12 是写测试 + 后续 tasks.md 时要一并处理的注意事项。
> **本需求书已做的核实**(Claude 已全仓 grep + 读源码,Codex 可信但仍应自验):载荷事实、影响面、下游消费、新码占用 —— 见 §4。

## 1. 目标(intent + why)

fallback event(`LLMFallbackEvent`,网关记录「一次 route 切换」诊断的事件 DTO)当前 `code` 字段复用 `[F-v3-gateway-all-providers-failed]`(候选链「全灭」的终态错误码)。**目标**:fallback event 改用专属码 `[F-v3-gateway-llm-fallback]`,让 trace 能分清「切换中」(fallback)与「全灭」(all-providers-failed)两种语义。

**为什么用 `init=False` 固有常量,而不是「可传参数 + 默认值」**:核实发现三处调用点传的 code 值**完全相同**(见 §4),说明 code 对 fallback event 根本不是变量,而是事件类型的固有属性。做成 `init=False`(dataclass 字段不进 `__init__`、调用方无法传值)能从类型层**物理根治**「调用点传错码」这一类 bug——留成可传默认值则这类 bug 没关死。目标机制细节以 spec_ssot 为唯一真理,本文不复制。

## 2. SSOT 指针(grounding,IR2/IR5)

- **目标(怎么做)**:`../13-x-tracing-events-exceptions/mvp1-alignment.md` §F1(fallback 事件 payload)、**gaps 第 1 条**(PM 2026-06-04,P4a=B:fallback event 拆专属 event code,不再复用全灭码)。
- **现状(起点)**:`../13-x-tracing-events-exceptions/baseline.md` §「fallback event payload(现状)」`code` 行、§「待办/疑点」第 1 条。
- **实现前必读源码(先读并向我确认读到的关键符号,再动手,IR2)**:
  - `events.py` 全文 —— `LLMFallbackEvent`(dataclass);`code: str | None = None` 在 `:17`;**已有 `init=False` 范式**参照物 `event_type` 在 `:19`;`model_dump`(序列化方法)`:24-34`。
  - `tracing.py` 全文 —— `build_llm_fallback_event`(事件构造 helper)`:13-30` 带 `code` 参数;`emit_llm_fallback_event`(逐 callback 发射 helper)`:33-59` 带 `code` 参数,内部 `:44-51` 把 code 透传给 build。
  - `gateway_chat_model.py` 三处 emit 调用 —— `:137-149`(probe 异常分支,code 实参 `:143`)、`:175-187`(probe 返回 false 分支,code 实参 `:181`)、`:251-263`(dispatch 异常分支,code 实参 `:257`)。
  - `exceptions.py` `:33-60` —— `AllProvidersFailedError`(候选链全灭异常),`code="[F-v3-gateway-all-providers-failed]"` 在 `:58`:**本 WS 不动,它是回归保护对象**。

## 3. 文件归属(并发锁,IR1)

- **本 WS owns**:见 frontmatter。
- **禁止触碰**:
  - ⚠️ **graph-agent 包里另有一个同名 `LLMFallbackEvent`**(`packages/graph-agent/src/graph_agent/callbacks/events.py:240`,是 Pydantic `_EventBase` 子类,与 gateway 的 dataclass **不同实现、不同类**)→ **绝不碰**。本 WS 只改 gateway 包的 `events.py`。
  - `gateway_chat_model.py` 除三处 `code=` 行以外的一切 → 归 **WS-1**。
  - fallback event 的 `from_provider`/`to_provider` 字段名 → **保留不改**(P4b=A 已定:改名跨 gateway+graph-agent+studio 三个订阅方,违背「事件结构不变」)。
  - 不补 fail-fast diagnostic event → P5=A 已定不补。
- **共享文件协调**:`gateway_chat_model.py` 与 WS-1 共享 → **WS-4 排 WS-1 提交之后串行**;动手删那三行前,`git status --short packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py` 必须为空(已脱离 WS-1 dirty)。
- **跨包测试纳入说明**:graph-agent 与 studio 的两个测试(见 frontmatter)因本 WS 的 DTO/helper 签名变更而 break,属直接连带,故纳入 owns。WS-4 排在最后(WS-1 之后),届时并发的 WS-3(studio projection)应已完成,与本 WS 改 `test_run_manager_gateway_events.py` 串行无撞;Codex 写测试时仍应核对该文件未被其它在跑 WS 占用。

## 4. 现状锚点(baseline + 本 WS 已核实事实)

fallback event 的 code 由**三处调用点**(`gateway_chat_model.py:143/181/257`)硬编码传同一个全灭码;`events.py`/`tracing.py` 只透传不带值。Claude 已全仓核实:

1. 三处传的 code 字面量**完全相同**(全灭码)→ 印证「code 对 fallback 是常量非变量」。
2. **无任何生产代码按 code 值做分支**(grep `F-v3-gateway-*` 在所有 `src/` 下,只命中要删的三处 + `exceptions.py:58`,无 `if event.code == ...` 消费)→ **改 code 值是纯标签变更,零行为副作用**。
3. 读 fallback event code 的生产代码只有 `events.py:32`(DTO 自身的 model_dump)→ 无外部消费方依赖具体值。
4. 新码串 `[F-v3-gateway-llm-fallback]` 全仓**未被占用**,可用。
5. 无注册表/枚举要改 —— 这族码全是 `exceptions.py` 内联字面量。

详见 baseline §「fallback event payload(现状)」「编号执行流程」「待办/疑点」。

## 5. 目标行为(可测的契约)

- **fallback event code 恒为专属码**:任何 fallback event(经 `build_llm_fallback_event` / `emit_llm_fallback_event` / 真实 `_generate` 三分支触发)的 `code` 字段 == `[F-v3-gateway-llm-fallback]`。
- **code 不可由调用方传**:`LLMFallbackEvent` 构造不接受 `code` 关键字(`init=False`);`build_llm_fallback_event` / `emit_llm_fallback_event` 签名**无 `code` 参数**。传入 `code=` 应抛 `TypeError`。
- **model_dump 不变**:`model_dump()` 仍含 `"code"` 键,值为专属码;其余键(event_type/phase_name/from_provider/to_provider/reason/context)不变。
- **异常码不变(回归)**:`AllProvidersFailedError.code` 仍 == `[F-v3-gateway-all-providers-failed]`。
- **payload 其它一切不变**:from/to route 诊断、`effective_runtime_settings`、`from_provider`/`to_provider` 字段名,全不动。

## 6. 测试要求(Codex 必须覆盖,RED 先行,IR3/IR4)

**新增/改写覆盖**:
- **① 专属码生效(三触发路径)**:
  - (a) `build_llm_fallback_event(...)`(不传 code)→ `event.code == "[F-v3-gateway-llm-fallback]"`;
  - (b) `emit_llm_fallback_event(...)`(不传 code)→ callback 收到的 `event.code == 专属码`;
  - (c) **真实 e2e**:构造最小 `GatewayChatModel`,真实走 `_generate` 的 fallback 路径,断言 emit 出的 `event.code == 专属码`(不许 mock 掉 emit / classify 逻辑)。
- **② probe-false 分支(:181)不漏**:三条触发路径(probe 异常 `:143` / **probe-false `:181`** / dispatch 异常 `:257`)都要有 event.code 断言覆盖。`:181` 是 baseline/alignment 漏记过的分支,**必须专测**,确认它也发专属码。
- **③ 回归保护(异常码不被误改)**:`AllProvidersFailedError.code` 仍 == 全灭码。现有 `test_all_providers_failed_error.py:31`、`test_gateway_integration.py:261` 应**继续绿且断言不改**。
- **④ init=False 契约**:`LLMFallbackEvent(..., code=...)` 抛 `TypeError`(code 不可传)。

**同步修正(因签名变更而 break 的现存测试 —— 必须改,否则套件红)**:
- 本包:
  - `test_llm_fallback_event.py`:`:29-42`(build 删 code 实参 + **event** code 断言改专属码)、`:51-57` 与 `:72-78`(emit 删 code 实参)。
  - `test_gateway_package_boundary.py`:`:14-28`(build 删 code 实参 + **event** code 断言改专属码)。
- 跨包:
  - graph-agent `test_event_subscriber_cutover.py`:`:57,63`(emit 删 code 实参 + 相关断言若有)。
  - studio `test_run_manager_gateway_events.py`:`:19`(`LLMFallbackEvent(...)` 删 code 实参)、`:24/:41`(dump 的 code 断言改专属码)。
- **⚠️ 分清两条 code 线(最易错)**:断言 **`exc.code`**(异常 `AllProvidersFailedError`)== 全灭码的 → **保留不改**(回归保护);断言 **`event.code`**(`LLMFallbackEvent`)== 全灭码的 → **改专属码**。别把回归断言误改成专属码。

## 7. 内部子步骤顺序

1. `events.py`:`LLMFallbackEvent.code` → `field(default="[F-v3-gateway-llm-fallback]", init=False)`(建议同时提一个模块级常量 `FALLBACK_EVENT_CODE` 承载字面量,更清晰)。注意 dataclass 字段顺序:`init=False` 字段不进 `__init__`,合法;改后 `__init__` 形参为 phase_name/from_provider/to_provider/reason/context。
2. `tracing.py`:`build_llm_fallback_event` / `emit_llm_fallback_event` **删 `code` 参数**;`emit` 内调 `build` 时不再传 code。`build` 的 docstring「shared graph-agent callback schema」措辞按需澄清(非强制)。
3. **等 WS-1 提交、`gateway_chat_model.py` 脱离 dirty 后**:删 `:143/:181/:257` 三处 `code=...` 实参(各一行)。
4. 同步修正 §6 列出的现存测试(本包 + 跨包)。

> 说明:步骤 1/2/4(events/tracing/测试)可在 WS-1 进行中并行准备(不依赖 gateway_chat_model.py);仅步骤 3(删调用点实参)硬卡 WS-1 提交后。

## 8. 验收标准(硬退出,IR4)

- [ ] §6 新增测试全绿(①②③④)。
- [ ] `uv run pytest packages/graph-agent-gateway/tests -q` 全绿。
- [ ] `uv run pytest packages/graph-agent/tests/runner/test_event_subscriber_cutover.py -q` 全绿。
- [ ] `uv run pytest apps/studio/backend/tests/services/test_run_manager_gateway_events.py -q` 全绿。
- [ ] `uv run mypy packages/graph-agent-gateway/src/graph_agent_gateway/events.py packages/graph-agent-gateway/src/graph_agent_gateway/tracing.py packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py` 0 error。
- [ ] `AllProvidersFailedError` 回归断言未改、仍绿(③)。
- [ ] 至少一条真实 e2e(经 `_generate` 触发 fallback)断言 `event.code == 专属码`(①c/②)。
- [ ] `git diff packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py` 仅含删 3 行 `code=` 实参,无其它改动。

## 9. 不做(范围锁定,IR7)

- 不改 `from_provider`/`to_provider` 字段名(P4b=A 已定保留)。
- 不补 fail-fast diagnostic event(P5=A 已定不补)。
- 不动 `AllProvidersFailedError` 的全灭码 / `exceptions.py` 任何逻辑。
- 不碰 graph-agent 的同名 `LLMFallbackEvent`(`callbacks/events.py:240`)。
- 不动 `gateway_chat_model.py` 除三处 `code=` 外任何行(那是 WS-1)。
- 范围外问题 → 记 `docs/deferred-items.md`,不顺手改。

## 10. baseline 回写指令(IR6,实现落地后由 Codex 照真实代码写)

改 `../13-x-tracing-events-exceptions/baseline.md`:
- §「fallback event payload(现状)」`code` 行:`复用全灭码` → `专属码 [F-v3-gateway-llm-fallback],init=False 固有常量,调用点不再传`;代码依据更新为 events.py 新行 + 三处调用点已删 code= 实参。
- §「编号执行流程」涉及 emit 的描述:原文只点 `:142/:256`,更新为**三处**(含 `:181`)且不再传 code。
- §「待办/疑点」第 1 条(code 复用全灭码)→ 标记为**已解决(WS-4 落地)**。
- 同步把 alignment gaps 第 1 条由「已定待实现」→「已实现」(由 Claude 终审确认后改 alignment §gaps,或先在 baseline 注明已落地)。

## 11. 评审检查点

- **契约门(Claude 审测试,放 Gemini 前)** 重点查:① 三触发路径(`:143/:181/:257`)是否都被 `event.code` 断言覆盖(尤其漏记过的 `:181`);② 回归断言(`exc.code == 全灭码`)是否被误改成专属码(不该改);③ 是否有真实 e2e(非纯 helper mock);④ `init=False` 的 `TypeError` 契约是否有测。
- **Codex 审查退出** = §8 全满足。
- **Claude 终审**:① code 真理确实内聚到 `events.py`(`init=False`),无第二处可传;② `gateway_chat_model.py` 只删 3 行、无越界;③ 跨包测试(graph-agent/studio)已同步且绿;④ `AllProvidersFailedError` 全灭码未被波及;⑤ baseline 回写诚实(含 `:181`)。

## 12. 给 Codex 注意(写测试 + 后续 tasks.md 照此办)

1. **code 用 `init=False` 固有常量,不是可传默认值** —— 调用点物理上不能再传 code(传则 TypeError)。
2. **删 helper 的 code 参数前先 grep 确认调用方**:Claude 已全仓 grep,传 `code=` 的**不止生产 3 处**,还有跨 3 包的测试(见 §6「同步修正」清单):本包 2 个测试文件、graph-agent 1 个、studio 1 个,**全部要同步改**,否则套件红。**别按「只有 3 处」去删。**
3. **测试必须覆盖**:① fallback event code == `[F-v3-gateway-llm-fallback]`;② probe-false 分支(`:181`)也发专属码,不漏;③ 回归:`AllProvidersFailedError.code` 仍 == `[F-v3-gateway-all-providers-failed]`,不被误改;④ `LLMFallbackEvent(code=...)` TypeError。
4. **分清两条 code 线**:异常码(`AllProvidersFailedError`)保留全灭码、其断言不动;事件码(`LLMFallbackEvent`)改专属码、其断言要更新。
5. **三处调用点删 `code=` 必须排在 WS-1 提交之后**;动手前 `git status --short packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py` 确认已脱离 WS-1 dirty。
6. **baseline 回写含 `:181` 漏记**(原 baseline/alignment 只记 `:142/:256`,实际三处)。
7. **不碰 graph-agent 的同名 `LLMFallbackEvent`**(`callbacks/events.py:240`,另一个类)。
8. **git 纪律**:只 stage WS-4 owns 文件,绝不 `git add .`;你和 Claude 都不 `git commit`(用户 `::git-stage` 外部管提交)。
