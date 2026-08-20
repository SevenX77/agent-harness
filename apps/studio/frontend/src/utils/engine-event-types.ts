/**
 * Every event type the engine can emit, mirroring the `CallbackEvent` union in
 * `packages/graph-agent/src/graph_agent/callbacks/events.py`.
 *
 * It exists so the trace can PROVE it has a reading for all of them. Before,
 * anything the panel had no reading for fell silently through to
 * `JSON.stringify` of the raw event — which looks like a rendering, so a new
 * engine event could ship and degrade the trace with nobody noticing (ledger
 * T4: "只有结果没有过程").
 *
 * The copy is kept honest by a backend test that reads BOTH this file and the
 * Python union and requires them to match
 * (`apps/studio/backend/tests/test_engine_event_types_are_mirrored.py`), so
 * adding an event to the engine turns CI red until the trace can read it.
 */
export const ENGINE_EVENT_TYPES = [
  'agent_loop_iteration',
  'ambiguity_logged',
  'artifact_saved',
  'blackboard_reduce',
  'builtin_subagent_enter',
  'builtin_subagent_exit',
  'builtin_subagent_fallback',
  'compaction',
  'dead_end_pruned',
  'edge_end',
  'edge_start',
  'finish_task_verdict',
  'input_dispatch',
  'input_file_injected',
  'interrupted',
  'llm_call',
  'llm_call_settings',
  'llm_delta',
  'llm_route_decision',
  'loop_detected',
  'nudge',
  'parallel_map_group_ended',
  'parallel_map_group_started',
  'phase_end',
  'phase_start',
  'predict_chain_start',
  'prompt_captured',
  'protocol_violation',
  'resumed',
  'run_ended',
  'run_started',
  'runtime_input_injected',
  'tool_call',
  'tool_call_started',
  'tool_error_handled',
  'tool_history_repaired',
  'working_memory_update',
] as const
