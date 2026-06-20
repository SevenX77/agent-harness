import type { GoldenBaseline } from "@/api/types"

/**
 * Per-node golden state channel (N4 golden-design atom #30: golden-tristate).
 *
 * Golden is a per-node acceptance signal, a SEPARATE visual channel from a node's
 * run status and its compile health (a node can be 🟢 has-golden regardless of
 * whether it has ever run or compiled). This pure helper projects the backend's
 * already-shipped `GoldenBaseline.cases` (each case carries the `node_id` it
 * fixes, projected from baseline.json) into a per-node state map.
 *
 * Design note on the deferred middle state: the design's three states are
 * 🔘 untested → 🟡 logic-OK (predict passed, no golden) → 🟢 has-golden. Only the
 * has-golden boolean has a contract-backed data source today — the 🟡 "predict
 * passed for this node" predicate has no DTO (PhaseRecord has no per-node status,
 * and the predict trigger does not cache its result). So this map only emits
 * 'has-golden'; a node absent from the map is "not yet golden" (could be untested
 * or logic-OK — the badge does NOT claim which, to avoid faking the 🟡/🔘 split).
 * This is a pure projection of a backend field, not a client-side re-derivation of
 * golden coverage or staleness.
 */

export type GoldenNodeState = "has-golden"

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
