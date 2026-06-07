---
status: Ready for Gemini per user handoff; RED tests installed
created: 2026-06-06
updated: 2026-06-06
owner: Graph-Agent Gateway
ws_id: WS-4-fallback-event-code
modules: [13]
depends_on: [WS-1]          # gateway_chat_model.py shared lock; Phase 3 requires this file clean
blocks: []
contract_gate: user requested Gemini handoff after Codex RED tests
red_tests:
  files:
    - packages/graph-agent-gateway/tests/test_llm_fallback_event.py
    - packages/graph-agent-gateway/tests/test_gateway_package_boundary.py
    - packages/graph-agent/tests/runner/test_event_subscriber_cutover.py
    - apps/studio/backend/tests/services/test_run_manager_gateway_events.py
  command: uv run pytest packages/graph-agent-gateway/tests/test_llm_fallback_event.py packages/graph-agent-gateway/tests/test_gateway_package_boundary.py packages/graph-agent/tests/runner/test_event_subscriber_cutover.py apps/studio/backend/tests/services/test_run_manager_gateway_events.py -q
  result: 11 failed, 5 passed (expected RED: fallback event code is None/all-providers-failed; code= still accepted)
regression_guard:
  command: uv run pytest packages/graph-agent-gateway/tests/test_all_providers_failed_error.py packages/graph-agent-gateway/tests/test_gateway_integration.py::test_gateway_failure_path_emits_event_and_structured_exception -q
  result: 4 passed (all-providers-failed exception code remains correct)
owns_files:
  - packages/graph-agent-gateway/src/graph_agent_gateway/events.py
  - packages/graph-agent-gateway/src/graph_agent_gateway/tracing.py
  - packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py          # read-only regression object; do not change logic
  - packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py  # only delete three code= kwargs, and only after clean preflight
  - packages/graph-agent-gateway/tests/test_llm_fallback_event.py
  - packages/graph-agent-gateway/tests/test_gateway_package_boundary.py
  - packages/graph-agent/tests/runner/test_event_subscriber_cutover.py
  - apps/studio/backend/tests/services/test_run_manager_gateway_events.py
spec_ssot:
  - ../../../docs/graph-agent-gateway/mvp1/13-x-tracing-events-exceptions/mvp1-alignment.md # §F1 + gaps P4a=B
related_baseline:
  - ../../../docs/graph-agent-gateway/mvp1/13-x-tracing-events-exceptions/baseline.md
related_impl_input:
  - ../../../docs/graph-agent-gateway/mvp1/_impl/WS4-fallback-events.md
review_flow: Claude/Codex RED tests -> Gemini GREEN implementation -> Codex review to hard exit -> Codex baseline writeback -> Claude final review
---

# Graph-Agent Gateway MVP1 · WS-4 fallback event 专属 code — Implementation Tasks

> **给 agentic worker**：本文是 WS-4 的实施任务书。当前状态 = Codex 已写入 RED 测试，用户要求把任务交给 Gemini 实施。
>
> - **Gemini**：先执行 Phase 0 preflight。尤其 `gateway_chat_model.py` 必须 clean 才能删三处 `code=`；若不 clean，立即报告阻塞，不要改该文件。
> - **不要削弱测试**：现有 RED 测试就是目标契约。只能改生产代码让它们变绿，不能放松断言、删除 TypeError 检查、或把专属码断言改回旧码。
> - **git 纪律**：不要 `git commit`，不要 `git add .`。如后续被要求 stage，只能按文件名 stage 本 WS owns 文件。

## Requirements 映射

| 标签 | 含义 | SSOT 出处 |
|---|---|---|
| `13.F1-code` | fallback event code 恒为 `[F-v3-gateway-llm-fallback]` | 13 alignment §F1 + gaps P4a=B |
| `13.F1-init-false` | `LLMFallbackEvent.code` 是 init=False 固有常量，调用方不能传 | WS4 impl input §5/§7 |
| `13.F3-helper-signature` | `build_llm_fallback_event` / `emit_llm_fallback_event` 不再接收 `code` 参数 | WS4 impl input §5/§7 |
| `13.F1-three-paths` | probe exception / probe false / dispatch exception 三条 `_generate` fallback 路径都发专属码 | WS4 impl input §6 |
| `13.F2-exception-regression` | `AllProvidersFailedError.code` 仍是 `[F-v3-gateway-all-providers-failed]` | 13 alignment §F2 |

## 1. 目标与 SSOT 指针

**做什么**：把 Gateway fallback diagnostic event 的 `code` 从复用全灭异常码 `[F-v3-gateway-all-providers-failed]` 改为事件专属码 `[F-v3-gateway-llm-fallback]`。这个 code 是 `LLMFallbackEvent` 的固有属性，不再由调用点传入。

**为什么**：fallback event 表达的是“切换中”，`AllProvidersFailedError` 表达的是“候选链全灭”。两者复用同一个 code 会让 trace 无法区分诊断事件和终态错误。

**目标真理**：`docs/graph-agent-gateway/mvp1/13-x-tracing-events-exceptions/mvp1-alignment.md` §F1 和 gaps P4a=B。

**现状起点**：`docs/graph-agent-gateway/mvp1/13-x-tracing-events-exceptions/baseline.md` 仍记录 fallback event code 复用全灭码；实现落地后由 Codex 按真实代码回写 baseline。

## 2. 文件归属与锁

### 本 WS 可改

| 文件 | 改什么 |
|---|---|
| `packages/graph-agent-gateway/src/graph_agent_gateway/events.py` | `LLMFallbackEvent.code` 改为 init=False 固有常量，建议新增 `FALLBACK_EVENT_CODE` |
| `packages/graph-agent-gateway/src/graph_agent_gateway/tracing.py` | 删除两个 helper 的 `code` 参数，不再透传 code |
| `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py` | 仅删除三处 `code="[F-v3-gateway-all-providers-failed]"` 调用实参 |
| 四个 RED 测试文件 | 原则上不需要再改；若因实现细节需要，只能做机械同步，不得削弱断言 |

### 禁止触碰

- `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py` 的异常码逻辑：只读，保留 `AllProvidersFailedError.code == "[F-v3-gateway-all-providers-failed]"`。
- `packages/graph-agent/src/graph_agent/callbacks/events.py` 中 graph-agent 包的同名 `LLMFallbackEvent`：这是另一个 Pydantic 事件类，绝不修改。
- `from_provider` / `to_provider` 字段名：保留不改。
- fail-fast diagnostic event：不补。
- `gateway_chat_model.py` 除三处 `code=` kwarg 外的任何行。

## 3. Phase 0：preflight 与 RED 状态

- [ ] 0.1 读关键源码并回述现状
  - `events.py`：`LLMFallbackEvent` 现在有可传 `code: str | None = None`，`event_type` 是已有 `init=False` 范式。
  - `tracing.py`：`build_llm_fallback_event` 和 `emit_llm_fallback_event` 现在都接收 `code` 并透传。
  - `gateway_chat_model.py`：三条 fallback 路径仍传旧码，分别是 probe exception、probe false、dispatch exception。
  - `exceptions.py`：`AllProvidersFailedError` 仍用全灭码，本 WS 不改。
  - _Requirements: 13.F1-code, 13.F2-exception-regression_

- [ ] 0.2 确认 RED 测试仍按预期失败
  - Run:
    ```bash
    uv run pytest packages/graph-agent-gateway/tests/test_llm_fallback_event.py packages/graph-agent-gateway/tests/test_gateway_package_boundary.py packages/graph-agent/tests/runner/test_event_subscriber_cutover.py apps/studio/backend/tests/services/test_run_manager_gateway_events.py -q
    ```
  - Expected before implementation: failures show event code is `None` or `[F-v3-gateway-all-providers-failed]`, and `code=` is still accepted.
  - _Requirements: 13.F1-code, 13.F1-init-false, 13.F3-helper-signature, 13.F1-three-paths_

- [ ] 0.3 共享文件硬门：检查 `gateway_chat_model.py` 是否 clean
  - Run:
    ```bash
    git status --short packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py
    ```
  - Required: no output.
  - If there is any output, **do not edit `gateway_chat_model.py`**. Report blocked with the exact status and stop before Phase 3.
  - _Requirements: 13.F1-three-paths_

## 4. Phase 1：`events.py` 固有常量

- [ ] 1.1 新增 fallback event code 常量
  - In `packages/graph-agent-gateway/src/graph_agent_gateway/events.py`, add a module constant:
    ```python
    FALLBACK_EVENT_CODE = "[F-v3-gateway-llm-fallback]"
    ```
  - Keep the string in one place in production code.
  - _Requirements: 13.F1-code_

- [ ] 1.2 `LLMFallbackEvent.code` 改为 init=False 固有字段
  - Change the dataclass field from:
    ```python
    code: str | None = None
    ```
    to:
    ```python
    code: str = field(default=FALLBACK_EVENT_CODE, init=False)
    ```
  - Keep `event_type` as `field(default="llm_fallback", init=False)`.
  - Keep `model_dump()` returning a `"code"` key.
  - After this change, `LLMFallbackEvent(..., code=...)` must raise `TypeError`.
  - _Requirements: 13.F1-code, 13.F1-init-false_

## 5. Phase 2：`tracing.py` helper 签名收紧

- [ ] 2.1 删除 `build_llm_fallback_event` 的 `code` 参数
  - Remove `code: str | None = None` from the function signature.
  - Remove `code=code` from the `LLMFallbackEvent(...)` call.
  - Do not replace it with another default parameter. The event DTO owns the code.
  - _Requirements: 13.F3-helper-signature_

- [ ] 2.2 删除 `emit_llm_fallback_event` 的 `code` 参数
  - Remove `code: str | None = None` from the function signature.
  - Remove `code=code` from the internal `build_llm_fallback_event(...)` call.
  - Callback failure behavior must remain unchanged: one bad callback logs and later callbacks still receive the event.
  - _Requirements: 13.F3-helper-signature_

## 6. Phase 3：`gateway_chat_model.py` 只删三处调用实参

- [ ] 3.1 重新执行 clean preflight
  - Run:
    ```bash
    git status --short packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py
    ```
  - Required: no output. If not clean, stop and report blocked.
  - _Requirements: 13.F1-three-paths_

- [ ] 3.2 删除 probe exception 分支的 `code=` kwarg
  - In `gateway_chat_model.py`, remove only this kwarg from the `emit_llm_fallback_event(...)` call in the probe exception branch:
    ```python
    code="[F-v3-gateway-all-providers-failed]",
    ```
  - Do not change surrounding fallback context, classification, mark-down, reason, or route selection logic.
  - _Requirements: 13.F1-three-paths_

- [ ] 3.3 删除 probe false 分支的 `code=` kwarg
  - Remove only the same kwarg from the `emit_llm_fallback_event(...)` call where `reason="RuntimeError: probe failed"`.
  - This branch is mandatory coverage; do not miss it.
  - _Requirements: 13.F1-three-paths_

- [ ] 3.4 删除 dispatch exception 分支的 `code=` kwarg
  - Remove only the same kwarg from the dispatch exception fallback event call.
  - _Requirements: 13.F1-three-paths_

- [ ] 3.5 检查 `gateway_chat_model.py` diff 范围
  - Run:
    ```bash
    git diff -- packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py
    ```
  - Required for WS-4: diff contains only deletion of the three `code=` kwarg lines. If any unrelated diff exists, report it explicitly and do not hide it.
  - _Requirements: 13.F1-three-paths_

## 7. Phase 4：验证

- [ ] 4.1 Run WS-4 focused tests
  - Run:
    ```bash
    uv run pytest packages/graph-agent-gateway/tests/test_llm_fallback_event.py packages/graph-agent-gateway/tests/test_gateway_package_boundary.py packages/graph-agent/tests/runner/test_event_subscriber_cutover.py apps/studio/backend/tests/services/test_run_manager_gateway_events.py -q
    ```
  - Expected after implementation: all pass.
  - _Requirements: 13.F1-code, 13.F1-init-false, 13.F3-helper-signature, 13.F1-three-paths_

- [ ] 4.2 Run gateway package tests
  - Run:
    ```bash
    uv run pytest packages/graph-agent-gateway/tests -q
    ```
  - Expected: all pass. `AllProvidersFailedError` assertions must remain unchanged and green.
  - _Requirements: 13.F2-exception-regression_

- [ ] 4.3 Run cross-package affected tests
  - Run:
    ```bash
    uv run pytest packages/graph-agent/tests/runner/test_event_subscriber_cutover.py -q
    uv run pytest apps/studio/backend/tests/services/test_run_manager_gateway_events.py -q
    ```
  - Expected: all pass.
  - _Requirements: 13.F3-helper-signature_

- [ ] 4.4 Run mypy on changed production files
  - Run:
    ```bash
    uv run mypy packages/graph-agent-gateway/src/graph_agent_gateway/events.py packages/graph-agent-gateway/src/graph_agent_gateway/tracing.py packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py
    ```
  - Expected: 0 errors.
  - _Requirements: 13.F1-init-false, 13.F3-helper-signature_

## 8. 验收标准（硬退出）

- [ ] Focused RED tests now pass.
- [ ] `uv run pytest packages/graph-agent-gateway/tests -q` passes.
- [ ] `uv run pytest packages/graph-agent/tests/runner/test_event_subscriber_cutover.py -q` passes.
- [ ] `uv run pytest apps/studio/backend/tests/services/test_run_manager_gateway_events.py -q` passes.
- [ ] mypy command in Phase 4.4 has 0 errors.
- [ ] `LLMFallbackEvent(..., code=...)`, `build_llm_fallback_event(..., code=...)`, and `emit_llm_fallback_event(..., code=...)` raise `TypeError`.
- [ ] Real `_generate` fallback paths for probe exception, probe false, and dispatch exception emit `event.code == "[F-v3-gateway-llm-fallback]"`.
- [ ] `AllProvidersFailedError.code == "[F-v3-gateway-all-providers-failed]"` remains green.
- [ ] `gateway_chat_model.py` diff is limited to the three `code=` kwarg deletions.

## 9. 不做

- Do not rename `from_provider` / `to_provider`.
- Do not add fail-fast diagnostic events.
- Do not change `exceptions.py` logic or all-providers-failed code.
- Do not touch graph-agent package's separate `LLMFallbackEvent`.
- Do not update baseline or alignment in Gemini implementation. Codex does baseline writeback after review.
- Do not stage or commit.

## 10. Codex baseline writeback（Gemini 不执行）

After Gemini reports GREEN and Codex review confirms §8, Codex updates `docs/graph-agent-gateway/mvp1/13-x-tracing-events-exceptions/baseline.md` to reflect:

- fallback event code is now `[F-v3-gateway-llm-fallback]`;
- `LLMFallbackEvent.code` is an init=False constant;
- helper signatures no longer take `code`;
- all three `_generate` fallback event call sites no longer pass `code`, including the probe false branch;
- all-providers-failed exception code remains unchanged.
