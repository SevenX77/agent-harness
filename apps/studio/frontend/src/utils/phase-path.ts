import type { CallbackEvent } from "@/api/types"

// ————————————————————————————————————————————————————————————————————————————
// phase-path: the ONE answer to "which phase is this, in this run".
//
// A bare `phase_name` is not an identity. Two subgraphs may each own a phase
// called `review`, and keying on the bare name folds them into one — engine run
// `2026-08-19T01-56-15_d0733362` merged 13 llm_calls from two different `review`
// nodes into a single report row and lost a `setup` node entirely, which is why
// the engine now stamps `subgraph_path` on every event
// (`_EventBase.subgraph_path`). This module joins the two halves the engine
// emits into the one key every run projection and every canvas node uses.
// ————————————————————————————————————————————————————————————————————————————

const SEPARATOR = "."

/**
 * The phase path an event belongs to: the enclosing SUBGRAPH chain the engine
 * stamped, followed by the phase's own name. Root-level phases have no chain,
 * so their path IS their name — which is what makes this key change identity
 * for every existing root-level reader.
 *
 * Returns null for events that name no phase at all (`run_started`,
 * `run_ended`), so callers skip them rather than invent a key.
 */
export function phasePathOf(event: CallbackEvent): string | null {
  const phaseName = event.phase_name || event.current_phase
  if (typeof phaseName !== "string" || phaseName === "") return null
  const scope = event.subgraph_path
  if (typeof scope !== "string" || scope === "") return phaseName
  return `${scope}${SEPARATOR}${phaseName}`
}

/** The path of a phase running one level inside `containerPath`. */
export function childPhasePath(containerPath: string, phaseName: string): string {
  return `${containerPath}${SEPARATOR}${phaseName}`
}

/**
 * Whether this path names a phase of the ROOT graph.
 *
 * Resume anchors and "which phase is the run in" both have to answer at root
 * level: a phase inside a subgraph is not a node of the root graph, so it can
 * neither be resumed from nor describe where the run stands on the board.
 */
export function isRootPhasePath(path: string): boolean {
  return !path.includes(SEPARATOR)
}
