/**
 * Every event type the engine can emit, mirroring the `CallbackEvent` union in
 * `packages/graph-agent/src/graph_agent/callbacks/events.py`.
 *
 * Two questions are asked of this list, and until 2026-08-20 each had its own
 * copy of it — `engine-event-types.ts` and `engine-events.ts`, same exported
 * name, same contents, one gate test each. Adding an event to the engine meant
 * editing two files and satisfying two gates that were checking the same fact.
 * One list, two readings:
 *
 * 1. **Is every event readable?** The trace proves it has a reading for all of
 *    them (`utils/trace.test.ts`). Before that proof existed, anything with no
 *    reading fell silently through to `JSON.stringify` of the raw event — which
 *    looks like a rendering, so a new engine event could ship and quietly
 *    degrade the trace (ledger T4: "只有结果没有过程").
 * 2. **Is this event one this build KNOWS?** `isEngineEventType` draws that
 *    line, which is what lets a name-shaped guess ("does the type contain
 *    'error'?") stay a fallback for FUTURE events instead of overruling what a
 *    known event actually means. `tool_error_handled` forced it: its name
 *    contains "error", but it reports an error the engine turned into model
 *    feedback and ran on from — reading it as a phase failure paints a node red
 *    on a run that never failed.
 *
 * The copy is kept honest by a backend test that reads BOTH this file and the
 * Python union and requires them to match
 * (`apps/studio/backend/tests/test_engine_event_types_are_mirrored.py`), so
 * adding an event to the engine turns CI red until the trace can read it.
 */
export const ENGINE_EVENT_TYPES = [
  'agent_exit_decision',
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

const KNOWN: ReadonlySet<string> = new Set(ENGINE_EVENT_TYPES)

/**
 * Whether this build has heard of an event type at all.
 *
 * Falling behind the engine is a survivable failure mode here, deliberately: an
 * event this build does not know is treated as unknown, which is how every type
 * was treated before the list existed. The mirror gate is what keeps that
 * fallback from becoming the normal case.
 */
export function isEngineEventType(eventType: string): boolean {
  return KNOWN.has(eventType)
}
