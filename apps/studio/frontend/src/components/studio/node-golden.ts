import type { GoldenBaseline, GraphTopologyItem, PredictDiagnosticExport } from "@/api/types"

/**
 * Per-node golden state channel (N4 golden-design atom #30: golden-tristate).
 *
 * Golden is a per-node acceptance signal, a SEPARATE visual channel from a node's
 * run status and its compile health. The design's three states are
 * 🔘 untested → 🟡 logic-OK (predict ran this node, no golden yet) → 🟢 has-golden.
 *
 * Two contract-backed data sources drive the tri-state:
 *  - 🟢 has-golden: the node_id appears in a `GoldenBaseline.cases` entry (a backend
 *    field projected from baseline.json). This is the authoritative golden truth.
 *  - 🟡 logic-OK: the node ran in the most-recent predict. We read that from the
 *    predict endpoint's `PredictDiagnosticExport.phases` — a phase is recorded only on
 *    completion (the engine writes a PhaseRecord on `on_phase_end`), so presence in
 *    `phases` means the node executed without throwing. We filter to AGENT nodes
 *    (`type === 'llm'`) because logic nodes never get golden (design g-c).
 *
 * Precedence: 🟢 > 🟡 > 🔘. A node absent from the map is 🔘 untested (undefined).
 * Both inputs are pure projections of backend data — no client-side re-derivation of
 * golden coverage or staleness. The 🟡 ran-set is session-memory only (the caller
 * caches the most-recent predict response and clears it on predict-fail).
 */

export type GoldenNodeState = "has-golden" | "logic-ok"

export function goldenStateByNode(
  baselines: readonly GoldenBaseline[] | null | undefined,
): Record<string, GoldenNodeState> {
  const byNode: Record<string, GoldenNodeState> = {}
  for (const baseline of baselines ?? []) {
    for (const goldenCase of baseline.cases ?? []) {
      const nodeId = goldenCase?.node_id
      if (typeof nodeId !== "string" || nodeId === "") {
        continue
      }
      byNode[nodeId] = "has-golden"
    }
  }
  return byNode
}

/**
 * Tri-state projection: 🟢 has-golden takes precedence over 🟡 logic-ok; nodes that are
 * neither golden nor ran stay 🔘 untested (absent from the map).
 */
export function goldenTriStateByNode(
  baselines: readonly GoldenBaseline[] | null | undefined,
  ranAgentNodes: ReadonlySet<string>,
): Record<string, GoldenNodeState> {
  const byNode: Record<string, GoldenNodeState> = {}
  // 🟡 first, then let 🟢 overwrite so has-golden always wins precedence.
  for (const nodeId of ranAgentNodes) {
    if (typeof nodeId === "string" && nodeId !== "") {
      byNode[nodeId] = "logic-ok"
    }
  }
  for (const [nodeId, state] of Object.entries(goldenStateByNode(baselines))) {
    byNode[nodeId] = state
  }
  return byNode
}

/**
 * N4 atom #33 create-path B gating: the agent node ids eligible for a manual golden
 * template — AGENT nodes (graph_topology mode === 'agent') that do NOT yet have golden.
 * Logic/subgraph nodes are excluded (they never get golden); 🟢 has-golden nodes are
 * excluded (template-fill is for non-🟢 agent nodes). Pure projection of backend data.
 */
export function templatableAgentNodeIds(
  graphTopology: readonly GraphTopologyItem[] | null | undefined,
  baselines: readonly GoldenBaseline[] | null | undefined,
): string[] {
  const goldenByNode = goldenStateByNode(baselines)
  return (graphTopology ?? [])
    .filter((item) => item.mode === "agent")
    .map((item) => item.id)
    .filter((nodeId) => goldenByNode[nodeId] !== "has-golden")
}

/**
 * Extract the set of AGENT node ids that ran in a predict response. A phase is in
 * `phases` only if it completed; we keep `type === 'llm'` (agent) phases and drop
 * logic phases (which never get golden). Returns an empty set for null/empty payloads
 * (e.g. after a predict-fail clear), which collapses every node back to 🔘/🟢.
 */
export function ranAgentNodesFromPredict(
  predict: PredictDiagnosticExport | null | undefined,
): Set<string> {
  const ran = new Set<string>()
  for (const phase of predict?.phases ?? []) {
    if (phase?.type === "llm" && typeof phase.phase_name === "string" && phase.phase_name !== "") {
      ran.add(phase.phase_name)
    }
  }
  return ran
}
