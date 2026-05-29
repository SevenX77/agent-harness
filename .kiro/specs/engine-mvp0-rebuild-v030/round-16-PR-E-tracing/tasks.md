---
spec: engine-mvp0-rebuild-v030/round-16-PR-E-tracing
phase: PR E tracing-and-observability tasks
owner: a1 tasks / a2 design+requirements+research / a3 gate
scope: E1+E2+E3+E4, tests-first, no new event schema
---

# PR E: Tracing And Observability Tasks

## §0 Scope / PR Structure / Workflow

本 PR 只做 tracing 接线范围: E1, E2, E3, E4。a2 已完成 `design.md` / `requirements.md` / `research.md`; 本文件把这些设计拆成可实施 tests-first 任务序列。

真相源:

- 本轮 design: `.kiro/specs/engine-mvp0-rebuild-v030/round-16-PR-E-tracing/design.md`
- 本轮 requirements: `.kiro/specs/engine-mvp0-rebuild-v030/round-16-PR-E-tracing/requirements.md`
- 本轮 research: `.kiro/specs/engine-mvp0-rebuild-v030/round-16-PR-E-tracing/research.md`
- 主任务定义: `.kiro/specs/engine-mvp0-rebuild-v030/tasks.md` §E lines 450-509。
- 事件 schema: `packages/graph-agent/src/graph_agent/callbacks/events.py`

PR 结构: 1 个统一 PR, 内部 4 commit。

- Commit 1: E1 runtime ambiguity emission 接线, 保证现有 tool lifecycle trace 与 `AMBIGUITY_LOGGED` 并列投递。
- Commit 2: E2 builtin reference reader assembly-time callbacks 通道 + ENTER / EXIT / FALLBACK 事件投递。
- Commit 3: E3 fallback payload 瘦身和 reason 映射, 不让原始 reference markdown 进入 trace event。
- Commit 4: E4 serializer / tracing tests sync, CI scans, docs-free closure。

合并工作流:

- feature branch 完成后用 `git merge --no-ff` 合入 `stage/engine-v030`。
- 不直接进 `main`。
- 每个 commit 必须保持本 PR 局部测试可解释; 最终 PR 必须通过 CI gate checklist。

SOP-06 字段继承结论:

| 字段/事件 | 类型 | 状态 | 备注 |
|---|---|---|---|
| `AmbiguityLoggedEvent` | Pydantic Event | [继承] | `events.py` 已有, 本 PR 只接线投递。 |
| `BuiltinSubagentEnterEvent` | Pydantic Event | [继承] | `events.py` 已有, 装配期 `run_id=None`。 |
| `BuiltinSubagentExitEvent` | Pydantic Event | [继承] | `events.py` 已有, 装配期 `run_id=None`。 |
| `BuiltinSubagentFallbackEvent` | Pydantic Event | [继承] | `events.py` 已有, payload 严格用现有字段。 |
| `fallback_reason` | Literal | [继承] | 采用现有 Literal, 不新增 enum。 |
| `CallbackEvent` union | Pydantic discriminated union | [继承] | 目标事件已在 union 内。 |

Implementation guardrails:

- 不新增 `TraceEventKind` enum; 当前事件用 Pydantic `Literal` 鉴别器。
- 不引入全局 Tracer 单例。优先通过 `callbacks: list[Any] | None` 显式传参打通装配期通道。
- 装配期 builtin reference reader 事件允许 `run_id=None`; `phase_name` 必须有值。
- 红灯纯度: tests-first task 只改 tests/fixtures, 禁止 skip/xfail 假绿。

## §1 依赖图

```text
e16.1 Tests-first red suite
  ├─> e16.2 E1 ambiguity runtime emission
  │     └─> e16.5 E4 serializer / callback sync
  └─> e16.3 E2 assembly-time builtin reference reader events
        └─> e16.4 E3 fallback payload slim mapping
              └─> e16.5 E4 serializer / callback sync
                    └─> e16.6 CI gate + scans
```

## §2 e16.1: Tests-first red suite (first task)

**目标**: 先写失败测试锁定 E1-E4 的 trace event emission、payload、顺序和序列化契约。此 task 只改 tests/fixtures, 不改 src。后续实施必须让这些红灯转绿。

**Files**:

- 新增 `packages/graph-agent/tests/callbacks/test_pr_e_tracing_emission_red.py`
- 更新 `packages/graph-agent/tests/callbacks/test_v030_trace_events.py`
- 更新 `packages/graph-agent/tests/core/test_reference_reader_assembly_fallback.py`
- 可新增 `packages/graph-agent/tests/e2e/test_tracing_runtime_v030.py`

**Red tests**:

- E1 ambiguity runtime emission:
  - 通过 Agent runtime 或 tool wrapper 路径触发 `log_ambiguity`, 不手工塞 `_callbacks` 到 ctx。
  - 断言标准 tool trace 仍有现有 `ToolCallEvent(event_type="tool_call")` 或等价 tool lifecycle event。
  - 断言额外并列出现一次 `AMBIGUITY_LOGGED`, 不替换 tool lifecycle trace。
  - 断言 payload: `phase_name`, `ambiguity_type`, `question`, `decision`, `reason`, `related_refs`, `related_protocols`。
  - 断言 callback 抛异常时不阻断工具返回, 且不会吞掉后续正常 callback。
- E2 builtin reference reader success:
  - `assemble_graph(..., callbacks=[collector])` 或等价装配入口传入 callbacks。
  - reference reader 成功时事件顺序为 `BUILTIN_SUBAGENT_ENTER` -> `BUILTIN_SUBAGENT_EXIT`。
  - 两个事件 `builtin_name == "reference_reader"`, `phase_name == current phase`, `run_id is None`。
  - EXIT payload 只包含短 metadata, 如 reference ids / used reference ids / duration 等, 不含原文 markdown。
- E2/E3 builtin reference reader fallback:
  - mock reader timeout / exception / invalid output。
  - 断言事件顺序为 `BUILTIN_SUBAGENT_ENTER` -> `BUILTIN_SUBAGENT_FALLBACK`。
  - Fallback payload 必含 `fallback_reason`, `fallback_strategy`, `excerpt_token_limit`, `warning`。
  - `fallback_reason` 映射覆盖 `remote_timeout`, `remote_error`, `invalid_output`, `config_missing`, `local_io_error`。
  - `warning` 只含短错误说明; 断言不包含 reference 原文、不包含 fallback markdown、不包含 3000 token 文本。
- E4 serializer sync:
  - `TypeAdapter(CallbackEvent)` 能 round-trip `AmbiguityLoggedEvent` 和三个 `BuiltinSubagent*Event`。
  - `TracingCallback` 写 JSONL 时保留 event discriminator 和关键 payload。
  - 无需新增 enum snapshot; 断言当前 Literal discriminator 即可。

**依赖**: none。

**验收**:

- 当前实现下红灯必须真实失败:
  - runtime ambiguity path 因 ctx 缺 `_callbacks` 不投递 `AMBIGUITY_LOGGED`。
  - `_build_reference_reader_markdown` 未接收 callbacks, 不投递 builtin subagent events。
  - fallback event payload 未产生, 体积控制无法验证。
- 不允许通过 skip/xfail/quarantine 获得假绿。

**风险点**:

- 现有 `test_v030_trace_events.py` 只覆盖直接传 `_callbacks` 的低层 helper, 不能证明 runtime 接线。红灯必须走真实 runtime/tool path。
- Tool lifecycle event 名称若现有系统用旧 `ToolCallEvent` 表达, 测试应断言语义字段而不是强绑未来 enum 名称。

## §3 e16.2: E1 AMBIGUITY_LOGGED runtime emission (Commit 1)

**目标**: `log_ambiguity` 成功记录后, 在真实 runtime/tool 调用链中投递 `AmbiguityLoggedEvent`, 同时保留普通 tool lifecycle 事件。

**Files / verified lines**:

- `packages/graph-agent/src/graph_agent/cognitive/ambiguity.py:29`
- `packages/graph-agent/src/graph_agent/cognitive/ambiguity.py:63`
- `packages/graph-agent/src/graph_agent/cognitive/ambiguity.py:75`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
- `packages/graph-agent/src/graph_agent/core/callback_bridge.py`
- `packages/graph-agent/src/graph_agent/callbacks/events.py:165`
- `packages/graph-agent/src/graph_agent/callbacks/events.py:450`

**WHAT**:

- 将活跃 callbacks 注入 `log_ambiguity` 的 runtime ctx, 不要求技能作者手动传 `_callbacks`。
- 保留 `_emit_ambiguity_logged(ctx, record)` 的非阻塞语义: 单个 callback 失败只 warning, 不影响工具结果或后续 callback。
- 保证 `log_ambiguity` 作为普通 tool 的 start/end lifecycle 仍正常投递; `AMBIGUITY_LOGGED` 是业务事件并列追加, 不替换 tool event。
- 事件字段:
  - `phase_name`: 当前 Agent phase。
  - `ambiguity_type`: 工具入参类型。
  - `question`: 工具入参 question。
  - `decision`: 工具入参 decision。
  - `reason`: 工具入参 reason。
  - `related_refs`: 从 question + reason 抽取 `@reference:<id>`。
  - `related_protocols`: 从 question + reason 抽取 `@protocol:<id>`。

**依赖**: e16.1。

**测试影响**:

- `test_pr_e_tracing_emission_red.py` E1 部分转绿。
- 保留 `test_v030_trace_events.py::test_log_ambiguity_emits_v030_ambiguity_logged_event` 作为 helper-level 回归, 但新增 runtime-level 覆盖。
- 更新 callback bridge/tool wrapper tests, 断言并列投递顺序。

**风险点**:

- 不要把 `AMBIGUITY_LOGGED` 作为 tool end 的替代品; 前端 timeline 仍需要 tool duration。
- 不要把 callback list 存进共享全局; 每次 run/phase 必须使用当前调用链 callbacks。
- ctx 注入要避免污染业务输入和输出字段。

**错误码**: none; callback emit failure 只 warning。

## §4 e16.3: E2 builtin reference reader ENTER / EXIT / FALLBACK (Commit 2)

**目标**: 装配期 reference reader 触发 typed builtin subagent trace events, 事件通过显式 callbacks 通道投递。

**Files / verified lines**:

- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:80`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:259`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:450`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:485`
- `packages/graph-agent/src/graph_agent/core/builtin_subagents/reference_reader.py:13`
- `packages/graph-agent/src/graph_agent/core/runner.py:495`
- `packages/graph-agent/src/graph_agent/core/loader.py:257`
- `packages/graph-agent/src/graph_agent/callbacks/events.py:178`
- `packages/graph-agent/src/graph_agent/callbacks/events.py:188`
- `packages/graph-agent/src/graph_agent/callbacks/events.py:198`

**WHAT**:

- 扩展 `assemble_graph(...)` 签名, 增加 `callbacks: list[Any] | None = None`。
- 将 callbacks 从 runner / loader / tests 的 graph assembly call sites 显式传入。
- `core/runner.py:495` 的 `_run_v21_skill_dict()` 必须把当前 callbacks 传给 `assemble_graph(...)`。
- `core/loader.py:245` 当前 `del callbacks` 的入口必须停止丢弃 callbacks, 并在 `load_workflow_from_md()` 调 `assemble_graph(...)` 时继续透传。
- 扩展 `_build_skill_node(...)`, `_agent_system_prompt(...)` 或 `_build_reference_reader_markdown(...)` 调用链, 让装配期 reader 能拿到 callbacks。
- 在 `_build_reference_reader_markdown` 中:
  - references 为空时不 emit builtin reader events。
  - reader 调用前 emit `BuiltinSubagentEnterEvent`。
  - reader 成功且 markdown 非空时 emit `BuiltinSubagentExitEvent`。
  - reader 超时 / ordinary exception / empty output / invalid output fallback 时 emit `BuiltinSubagentFallbackEvent`。
  - path invalid `[F-v3-resource-reference-path-invalid]` 仍 re-raise FATAL; 可 emit ENTER, 不 emit fallback 降级。
- 装配期 event 字段:
  - `run_id=None`。
  - `phase_name=<current phase id>`。
  - `builtin_name="reference_reader"`。
  - `payload` 仅放短 metadata, 如 `reference_ids`, `used_reference_ids`, `duration_ms`, `warnings`。

**依赖**: e16.1。

**测试影响**:

- `test_reference_reader_assembly_fallback.py` 增加 collector callback。
- 新增 success order test: ENTER -> EXIT。
- 新增 fallback order test: ENTER -> FALLBACK。
- 更新 `runner` / `loader` / `assemble_graph` 既有 tests 中直接调用处, 如需要传 `callbacks=[]` 保持签名兼容。

**风险点**:

- 不要引入全局 singleton tracer; design 明确优先 callbacks list DI。
- `assemble_graph` call sites 很多; 签名新增参数必须有默认值避免大范围破坏。
- 装配期没有 `run_id`, 不要制造 fake run id。
- path fatal 不可被 fallback 事件误表达成 WARN 降级。

**错误码**:

- `[F-v3-reference-reader-failed]` remains WARN/fallback reason source。
- `[F-v3-resource-reference-path-invalid]` remains FATAL re-raise。

## §5 e16.4: E3 fallback payload slim mapping (Commit 3)

**目标**: Fallback trace event 严格使用现有 Pydantic model, 映射短字段, 不把 reference 原文或 fallback markdown 放进 trace。

**Files / verified lines**:

- `packages/graph-agent/src/graph_agent/callbacks/events.py:198`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:481`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:493`
- `packages/graph-agent/src/graph_agent/core/builtin_subagents/reference_reader.py:41`
- `packages/graph-agent/src/graph_agent/callbacks/serialize.py`
- `packages/graph-agent/src/graph_agent/callbacks/tracing.py`

**WHAT**:

- 为 reader failure 建立小型 reason mapper:
  - timeout / `[F-v3-reference-reader-failed] timeout` -> `remote_timeout`。
  - generic exception -> `remote_error`。
  - empty markdown / non-dict / missing markdown -> `invalid_output`。
  - missing config / missing reference path -> `config_missing`。
  - local IO fallback 失败可用现有 `local_io_error`。
- `fallback_strategy` 固定为 `raw_excerpt_3000_tokens`。
- `excerpt_token_limit=3000`。
- `warning` 只放短字符串, 必须截断到固定上限, 建议 <= 500 chars。
- 严禁在 event 中放:
  - reference body。
  - generated fallback markdown。
  - prompt `<knowledge_base>` 内容。
  - 大型 exception traceback。
- 继续允许 fallback markdown 进入 Agent prompt; 体积限制只针对 trace event payload。

**依赖**: e16.3。

**测试影响**:

- Snapshot / JSONL tests 断言 fallback event key set。
- 构造包含 sentinel 长 reference 文本的 fallback, 断言 tracer JSONL 不含 sentinel。
- Pydantic validation tests 断言 wrong reason 被拒绝, existing Literal accepted。

**风险点**:

- 不要为了“方便调试”把 fallback markdown 塞入 `payload` 或 `warning`。
- `warning` 截断必须保留错误码前缀, 方便 Studio 展示。
- 不新增 enum; 使用 `events.py` 已有 Literal。

**错误码**:

- `[F-v3-reference-reader-failed]` warning source。
- `[F-v3-resource-reference-path-invalid]` not fallback.

## §6 e16.5: E4 tests sync + serializer stability (Commit 4)

**目标**: 将已启用事件纳入 callbacks/tracing 回归, 确保 Pydantic union、JSONL tracer、tool metadata、事件顺序长期稳定。

**Files / verified lines**:

- `packages/graph-agent/tests/callbacks/test_events.py`
- `packages/graph-agent/tests/callbacks/test_serialize.py`
- `packages/graph-agent/tests/callbacks/test_v030_trace_events.py`
- `packages/graph-agent/tests/core/test_tracing_proxy.py`
- `packages/graph-agent/src/graph_agent/callbacks/events.py:450`
- `packages/graph-agent/src/graph_agent/callbacks/tracing.py`
- `packages/graph-agent/src/graph_agent/callbacks/serialize.py`

**WHAT**:

- 保留并扩展 `CallbackEvent` union round-trip tests。
- 确认 `TracingCallback` 能写出:
  - `ambiguity_logged`
  - `builtin_subagent_enter`
  - `builtin_subagent_exit`
  - `builtin_subagent_fallback`
- Tool event metadata:
  - `tool_name` 必须存在并等于真实 tool 名。
  - `log_ambiguity` 普通 tool lifecycle 与 `ambiguity_logged` 同 run/phase 可关联。
- Reference reader event order:
  - success: ENTER -> EXIT。
  - fallback: ENTER -> FALLBACK。
- 不新增 enum snapshot; 当前 discriminated union 用 `Literal`。
- 将 `AmbiguityLoggedEvent` 与 `BuiltinSubagentEnterEvent` / `BuiltinSubagentExitEvent` / `BuiltinSubagentFallbackEvent` 纳入 `Callback.on_event` 默认 typed-only 分支，或新增测试证明普通 `Callback().on_event(...)` 收到这些事件不会走 unrecognised warning。

**依赖**: e16.2, e16.3, e16.4。

**测试影响**:

- `pytest packages/graph-agent/tests/callbacks -q`
- `pytest packages/graph-agent/tests/core/test_reference_reader_assembly_fallback.py -q`
- `pytest packages/graph-agent/tests/core/test_tracing_proxy.py -q`
- PR E target suite 全绿。

**风险点**:

- 旧 callback tests 可能直接比对 event list; 添加事件后需只更新 PR E 相关路径, 不放宽其他事件断言。
- JSONL snapshot 不应固定 timestamp/run duration。
- 如果 callback raises, 其他 callback 仍应收到事件。

## §7 e16.6: CI gate + risk scans

**目标**: PR E 完成后跑全量测试和专门 scan, 确认事件不再只是定义而未投递, fallback payload 不含大文本, 无全局 tracer 反模式。

**Files**:

- 不强制改 src; 允许只更新 tests 若 scan 暴露遗漏。

**Commands / scans**:

- Target:
  - `pytest packages/graph-agent/tests/callbacks/test_v030_trace_events.py -q`
  - `pytest packages/graph-agent/tests/callbacks -q`
  - `pytest packages/graph-agent/tests/core/test_reference_reader_assembly_fallback.py -q`
  - `pytest packages/graph-agent/tests/e2e/test_tracing_runtime_v030.py -q` if added。
- Full:
  - `pytest packages/graph-agent/tests -q`
- Scans:
  - `rg -n "BuiltinSubagentEnterEvent|BuiltinSubagentExitEvent|BuiltinSubagentFallbackEvent|AmbiguityLoggedEvent" packages/graph-agent/src/graph_agent`
  - `rg -n "global.*Tracer|GLOBAL.*TRACER|singleton.*tracer|dispatch_custom_event" packages/graph-agent/src/graph_agent || true`
  - `rg -n "fallback_markdown|knowledge_base_markdown|reference body|raw reference" packages/graph-agent/src/graph_agent/callbacks packages/graph-agent/src/graph_agent/core/graph_assembler.py || true`
  - `rg -n "logger.warning\\(\"\\[F-v3-reference-reader-failed\\]" packages/graph-agent/src/graph_agent/core/graph_assembler.py`
  - `rg -n "callbacks=.*assemble_graph|assemble_graph\\(" packages/graph-agent/src/graph_agent packages/graph-agent/tests -g '*.py'`

**验收**:

- Full pytest green。
- Event class scan shows both definitions and real emit sites.
- No global tracer singleton or hidden global event bus introduced.
- Fallback event payload scan has no raw markdown fields.
- Reference reader still logs warning, but now also emits typed fallback event when callbacks are provided.

**风险点**:

- Some paths legitimately call `assemble_graph` without callbacks; default `None` must preserve behavior.
- Do not make tracing mandatory for successful runtime execution.

## §8 Definition of Done

- e16.1 红灯 suite 先落且真实失败。
- e16.2-e16.4 实施后目标红灯逐项转绿。
- e16.5 serializer/tracing tests 同步完成。
- e16.6 全量测试通过。
- 不改 PR E 范围外 spec/doc/src 行为。
- 不新增事件 schema / enum; 只接线已定义事件。
- 不引入全局 Tracer 单例。
