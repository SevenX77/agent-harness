---
ws_id: WS-E4-v4-trace-events
task_type: implementation
implementer: Gemini
author: Codex
status: drafted
created: 2026-06-07
requirements: docs/engine/mvp1/_impl/requirements-ws-e4-v4-trace-events.md
related_plan: docs/engine/mvp1/_impl/IMPL_PLAN.md
related_backlog: docs/engine/mvp1/_impl-backlog.md
spec_ssot:
  - docs/engine/mvp1/02-mechanism/06-seam/02-observability/mvp1-alignment.md §2/§3/§5/§8
  - docs/engine/mvp1/02-mechanism/06-seam/02-observability/baseline.md 后端功能 §1/§4
approved_red_tests:
  - packages/graph-agent/tests/callbacks/test_ws_e4_v4_trace_events_red.py
  - packages/graph-agent/tests/test_public_api_contract.py::test_callback_event_union_contains_consumed_event_models
red_result: "uv run pytest packages/graph-agent/tests/callbacks/test_ws_e4_v4_trace_events_red.py packages/graph-agent/tests/test_public_api_contract.py::test_callback_event_union_contains_consumed_event_models -q -> 6 failed"
owns_files:
  - packages/graph-agent/src/graph_agent/callbacks/events.py
  - packages/graph-agent/src/graph_agent/callbacks/emit.py
  - packages/graph-agent/src/graph_agent/callbacks/base.py
  - packages/graph-agent/tests/callbacks/test_ws_e4_v4_trace_events_red.py
  - packages/graph-agent/tests/test_public_api_contract.py
forbidden_files:
  - packages/graph-agent/src/graph_agent/core/graph_assembler.py
  - packages/graph-agent/src/graph_agent/core/runner.py
  - packages/graph-agent/src/graph_agent/middleware/tracing.py
  - packages/graph-agent/src/graph_agent/middleware/tool_error.py
  - packages/graph-agent/src/graph_agent/middleware/loop_detection.py
  - packages/graph-agent/src/graph_agent/callbacks/tracing.py
  - packages/graph-agent/src/graph_agent/core/tracing_proxy.py
  - apps/studio/**
  - packages/graph-agent-gateway/**
---

# WS-E4 V4 Trace Events Task

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` while implementing. The RED tests are already written and approved by the contract gate. Do not weaken them. Implement task-by-task until the approved RED suite is GREEN.

**Goal:** Add the V4 trace event contract surface so Studio can consume agent micro-topology fields and graph edge-operation events from typed callback events and `trace.jsonl`.

**Architecture:** Keep this schema-only and callback-contract-only. The implementation should stay in `callbacks/events.py` plus any minimal default callback recognition in `callbacks/base.py`; `_TraceJsonlSink` in `callbacks/emit.py` should remain a generic one-line JSON object writer and may need no production edit if the new Pydantic events already serialize through it. Do not wire real runtime emission points.

**Tech Stack:** Python 3.12, Pydantic v2 discriminated unions, pytest, existing graph-agent callback event system.

---

## Phase 0: Grounding And Scope Lock

- [ ] Read the requirements file and SSOT pointers before editing.
  _Requirements: IR2 / IR5 grounding; WS-E4 requirements §2 / §12._
  Verify by reporting the current live symbols and behavior: `_EventBase`, `LLMCallEvent`, `ToolCallEvent`, `CallbackEvent`, `__all__`, `_typed_only_event_types`, and `_TraceJsonlSink.emit`.

- [ ] Confirm the implementation scope is limited to schema / union / JSONL / default callback / public contract.
  _Requirements: WS-E4 requirements §1 / §3 / §9._
  Verification command:
  `git status --short -- packages/graph-agent/src/graph_agent/callbacks/events.py packages/graph-agent/src/graph_agent/callbacks/emit.py packages/graph-agent/src/graph_agent/callbacks/base.py packages/graph-agent/src/graph_agent/core/graph_assembler.py packages/graph-agent/src/graph_agent/core/runner.py packages/graph-agent/src/graph_agent/middleware/tracing.py packages/graph-agent/src/graph_agent/middleware/tool_error.py packages/graph-agent/src/graph_agent/middleware/loop_detection.py`
  Expected before implementation: RED test files may be dirty; forbidden runtime files must have no WS-E4 implementation diff.

- [ ] Re-run the approved RED suite before implementing, and keep the failure shape contract-focused.
  _Requirements: TDD RED evidence; WS-E4 requirements §8._
  Verification command:
  `uv run pytest packages/graph-agent/tests/callbacks/test_ws_e4_v4_trace_events_red.py packages/graph-agent/tests/test_public_api_contract.py::test_callback_event_union_contains_consumed_event_models -q`
  Expected now: `6 failed`, caused by missing `parent_node_id` / `node_type`, missing edge event exports/classes, missing union variants, and missing public contract variants.

## Phase 1: Micro-Topology Fields On Existing Events

- [ ] Add additive `parent_node_id: str | None` and `node_type: str | None` fields to `LLMCallEvent`.
  _Requirements: WS-E4 requirements §5 / §6; observability alignment §2 / §8._
  The old constructor form must still work, and both new fields must default to `None`.
  Target tests:
  - `packages/graph-agent/tests/callbacks/test_ws_e4_v4_trace_events_red.py::test_v4_micro_topology_fields_are_available_on_llm_and_tool_events`
  - `packages/graph-agent/tests/callbacks/test_ws_e4_v4_trace_events_red.py::test_v4_micro_topology_fields_default_to_none_for_legacy_construction`
  Verification command:
  `uv run pytest packages/graph-agent/tests/callbacks/test_ws_e4_v4_trace_events_red.py::test_v4_micro_topology_fields_are_available_on_llm_and_tool_events packages/graph-agent/tests/callbacks/test_ws_e4_v4_trace_events_red.py::test_v4_micro_topology_fields_default_to_none_for_legacy_construction -q`

- [ ] Add the same additive fields and default behavior to `ToolCallEvent`.
  _Requirements: WS-E4 requirements §5 / §6; observability alignment §2 / §8._
  Keep existing legacy callback dispatch semantics unchanged: old `on_llm_call(...)` and `on_tool_call(...)` hooks should not receive the new fields.
  Verification command:
  `uv run pytest packages/graph-agent/tests/callbacks/test_ws_e4_v4_trace_events_red.py::test_v4_micro_topology_fields_are_available_on_llm_and_tool_events packages/graph-agent/tests/callbacks/test_ws_e4_v4_trace_events_red.py::test_v4_micro_topology_fields_default_to_none_for_legacy_construction packages/graph-agent/tests/callbacks/test_on_event_characterization.py -q`

## Phase 2: V4 Edge Operation Event Schemas

- [ ] Define `BlackboardReduceEvent` as a typed event in `graph_agent.callbacks.events`.
  _Requirements: WS-E4 requirements §5 / §6; observability alignment §8._
  Required contract:
  - `event_type` discriminates as `blackboard_reduce`.
  - Shared edge fields: `from_phase: str | None`, `to_phase: str`, `changed_keys: list[str]`, `blackboard_snapshot: dict[str, Any]`.
  - Dedicated field: `reducer: str`.
  - Extra fields remain forbidden through `_EventBase`.

- [ ] Define `InputDispatchEvent` as a typed event in `graph_agent.callbacks.events`.
  _Requirements: WS-E4 requirements §5 / §6; observability alignment §8._
  Required contract:
  - `event_type` discriminates as `input_dispatch`.
  - Shared edge fields: `from_phase`, `to_phase`, `changed_keys`, `blackboard_snapshot`.
  - Dedicated fields: `dispatched_keys: list[str]`, `branch_index: int | None`.
  - `branch_index=None` represents non-parallel dispatch.

- [ ] Define `InputFileInjectedEvent` as a typed event in `graph_agent.callbacks.events`.
  _Requirements: WS-E4 requirements §5 / §6; observability alignment §8._
  Required contract:
  - `event_type` discriminates as `input_file_injected`.
  - Shared edge fields: `from_phase`, `to_phase`, `changed_keys`, `blackboard_snapshot`.
  - Dedicated fields: `file_ref: str`, `target_field: str`.

- [ ] Verify the three new event classes exist and forbid extras.
  _Requirements: WS-E4 requirements §6._
  Verification command:
  `uv run pytest packages/graph-agent/tests/callbacks/test_ws_e4_v4_trace_events_red.py::test_v4_edge_operation_events_round_trip_through_union_and_jsonl -q`
  Expected before Phase 3 is complete: this may still fail at union validation if the classes exist but `CallbackEvent` has not been updated.

## Phase 3: Public Exports, Union, And JSONL Round Trip

- [ ] Add the three V4 edge operation event classes to `CallbackEvent`.
  _Requirements: WS-E4 requirements §5 / §6; observability alignment §3 / §8._
  Verification command:
  `uv run pytest packages/graph-agent/tests/callbacks/test_ws_e4_v4_trace_events_red.py::test_v4_edge_operation_events_round_trip_through_union_and_jsonl packages/graph-agent/tests/test_public_api_contract.py::test_callback_event_union_contains_consumed_event_models -q`

- [ ] Add the three V4 edge operation event classes to `graph_agent.callbacks.events.__all__`.
  _Requirements: WS-E4 requirements §5 / §6; public contract surface._
  Verification command:
  `uv run pytest packages/graph-agent/tests/callbacks/test_ws_e4_v4_trace_events_red.py::test_v4_edge_operation_events_are_publicly_exported -q`

- [ ] Keep `_TraceJsonlSink` one-line JSON object behavior for the new events.
  _Requirements: WS-E4 requirements §5 / §6; observability alignment §6._
  If `_TraceJsonlSink.emit` already passes the approved RED with the new Pydantic events, leave `callbacks/emit.py` untouched.
  Verification command:
  `uv run pytest packages/graph-agent/tests/callbacks/test_ws_e4_v4_trace_events_red.py::test_v4_edge_operation_events_round_trip_through_union_and_jsonl -q`

## Phase 4: Default Callback Recognition Without Legacy Hooks

- [ ] Make default `Callback().on_event(...)` recognize the three new events as typed-only events.
  _Requirements: WS-E4 requirements §3 / §5 / §6; observability alignment §3._
  Do not add `on_blackboard_reduce`, `on_input_dispatch`, or `on_input_file_injected` legacy hooks. Do not change existing legacy event dispatch behavior.
  Verification command:
  `uv run pytest packages/graph-agent/tests/callbacks/test_ws_e4_v4_trace_events_red.py::test_default_callback_accepts_v4_trace_events_without_warning packages/graph-agent/tests/callbacks/test_on_event_characterization.py -q`

## Phase 5: Full Verification And Regression Guard

- [ ] Run the approved WS-E4 RED suite to GREEN.
  _Requirements: WS-E4 requirements §8 hard exit._
  Verification command:
  `uv run pytest packages/graph-agent/tests/callbacks/test_ws_e4_v4_trace_events_red.py packages/graph-agent/tests/test_public_api_contract.py::test_callback_event_union_contains_consumed_event_models -q`
  Expected after implementation: all tests pass.

- [ ] Run existing callback schema and default callback characterization tests.
  _Requirements: backward compatibility._
  Verification command:
  `uv run pytest packages/graph-agent/tests/callbacks/test_events.py packages/graph-agent/tests/callbacks/test_on_event_characterization.py packages/graph-agent/tests/callbacks/test_emit.py -q`

- [ ] Run the baseline regression suite that was green before WS-E4 RED.
  _Requirements: no regression from Wave2 baseline._
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/e2e/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/core/test_purity_characterization.py packages/graph-agent/tests/core/validators/test_purity_le2.py packages/graph-agent/tests/runner/test_v030_error_contract_v2_diagnostics.py -q`
  Expected from baseline: `51 passed`.

- [ ] Confirm no real emit wiring or forbidden file work happened.
  _Requirements: WS-E4 requirements §3 / §9; IR1 / IR7._
  Verification command:
  `git diff -- packages/graph-agent/src/graph_agent/core/graph_assembler.py packages/graph-agent/src/graph_agent/core/runner.py packages/graph-agent/src/graph_agent/middleware/tracing.py packages/graph-agent/src/graph_agent/middleware/tool_error.py packages/graph-agent/src/graph_agent/middleware/loop_detection.py packages/graph-agent/src/graph_agent/callbacks/tracing.py packages/graph-agent/src/graph_agent/core/tracing_proxy.py`
  Expected: no diff.

- [ ] If `uv run` touches `uv.lock`, restore it unless this WS intentionally changed dependencies.
  _Requirements: WS-E4 requirements §8._
  Verification command:
  `git status --short -- uv.lock`
  If dirty: `git restore -- uv.lock`

- [ ] Run diff hygiene.
  _Requirements: implementation quality gate._
  Verification command:
  `git diff --check -- packages/graph-agent/src/graph_agent/callbacks/events.py packages/graph-agent/src/graph_agent/callbacks/emit.py packages/graph-agent/src/graph_agent/callbacks/base.py packages/graph-agent/tests/callbacks/test_ws_e4_v4_trace_events_red.py packages/graph-agent/tests/test_public_api_contract.py`

## Phase 6: Baseline Handoff After GREEN

- [ ] Do not update baseline before implementation is GREEN and Codex review accepts hard exit.
  _Requirements: IR6 / WS-E4 requirements §10._
  After GREEN, report the exact landed event count, edge-operation event status, micro-topology field status, and whether `callbacks/emit.py` required a real code diff so Codex can truthfully update:
  - `docs/engine/mvp1/02-mechanism/06-seam/02-observability/baseline.md`

## Hard Exit Checklist

- [ ] Approved WS-E4 RED suite is GREEN.
- [ ] `LLMCallEvent` and `ToolCallEvent` expose `parent_node_id` and `node_type`, with legacy construction defaulting both to `None`.
- [ ] `BlackboardReduceEvent`, `InputDispatchEvent`, and `InputFileInjectedEvent` exist with the required shared and dedicated fields.
- [ ] New event classes forbid extra fields.
- [ ] New event classes are included in `CallbackEvent` and `graph_agent.callbacks.events.__all__`.
- [ ] `_TraceJsonlSink` writes the new events as one JSON object per line.
- [ ] Default `Callback().on_event(...)` accepts the new typed-only events without "unrecognised event type" warnings.
- [ ] Existing callback schema/default-callback characterization tests still pass.
- [ ] Baseline regression suite still passes.
- [ ] No real emit wiring was implemented.
- [ ] Forbidden files have no diff, and `apps/studio/**` / `packages/graph-agent-gateway/**` were not edited by this WS.
- [ ] `uv.lock` is clean unless a separate approved dependency change exists.

## Gemini Report Format

When finished, report:

1. Files changed.
2. The exact tests run and pass/fail output summary.
3. Confirmation that forbidden files have no diff and `apps/studio/**` / `packages/graph-agent-gateway/**` were not edited by this WS.
4. Whether `callbacks/emit.py` needed any code diff or stayed unchanged because generic JSONL writing already worked.
5. Any remaining risk or reason a hard-exit item is not satisfied.
