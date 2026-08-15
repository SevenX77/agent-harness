/**
 * Every event type the engine emits today — one entry per `event_type:
 * Literal[...]` variant of the typed union in
 * `packages/graph-agent/src/graph_agent/callbacks/events.py`.
 *
 * It exists to answer exactly one question: is this an event this build KNOWS,
 * or one it has never heard of? That line is what lets a name-shaped guess
 * ("does the type contain 'error'?") stay a fallback for FUTURE events instead
 * of overruling what a known event actually means. `tool_error_handled` is the
 * case that forced it: its name contains "error", but the event reports an
 * error the engine turned into model feedback and ran on from — reading it as a
 * phase failure paints a node red on a run that never failed.
 *
 * Falling behind the engine is a survivable failure mode, deliberately: a type
 * missing here is treated as unknown, which is exactly how every type was
 * treated before this set existed.
 */
export const ENGINE_EVENT_TYPES: ReadonlySet<string> = new Set([
  'agent_loop_iteration',
  'ambiguity_logged',
  'artifact_saved',
  'blackboard_reduce',
  'builtin_subagent_enter',
  'builtin_subagent_exit',
  'builtin_subagent_fallback',
  'compaction',
  'dead_end_pruned',
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
])
