/**
 * Run-focus-follow target selection (run-verify N4 atom #9).
 *
 * During a real run the canvas should auto-center on whichever node is currently
 * executing. The "currently running node" is the `activeTracePhase` Workspace
 * already derives from the live run stream (`statusByNodeId`, the node whose
 * status is `running`) — this helper does NOT re-derive it. It only answers the
 * pure question "given that running phase id, is there a matching node on the
 * canvas to center on?", returning the id to focus or null.
 *
 * Pure + dependency-free so the focus DECISION is unit-testable without a React
 * Flow instance or a DOM (the effect that owns the fitView side effect feeds the
 * result of this function straight into `reactFlowInstance.fitView`).
 */
export function nodeToFocus(
  activeTracePhase: string | null | undefined,
  nodeIds: readonly string[],
): string | null {
  if (!activeTracePhase) {
    return null
  }
  return nodeIds.includes(activeTracePhase) ? activeTracePhase : null
}
