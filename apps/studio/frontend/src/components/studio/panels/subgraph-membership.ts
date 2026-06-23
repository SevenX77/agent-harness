import type { SkillDetail } from "@/api/types"
import { resolveSubgraphReference, type SubgraphReferenceStatus } from "@/components/studio/subgraph-path"

/**
 * Real subgraph membership for the Assets panel.
 *
 * Membership is derived from the skill's actual subgraph phases as surfaced by
 * the backend topology (R4): each `graph_topology` row with `mode === "subgraph"`
 * carries an absolute child `path` read from that phase's SUBGRAPH.md. A row with
 * a usable `path` is `resolved`; a row whose `path` is null/blank is `missing`
 * (the SUBGRAPH.md declared no path, so the child graph is unresolvable).
 *
 * This replaces the former in-memory `registeredSubgraphsCache`, which faked
 * "registered" state in the browser instead of reflecting real path-based
 * references. The view is read-only: it reports what the skill actually
 * references, never fabricated membership.
 */
export type SubgraphMembershipStatus = SubgraphReferenceStatus

export interface SubgraphMembership {
  /** Phase id of the subgraph phase (its label in the topology). */
  id: string
  /** Display label — the subgraph phase name. */
  label: string
  /** The parent skill's phase file that stores the subgraph path. */
  filePath: string
  /** Absolute child-graph path, or null when the phase declares none. */
  path: string | null
  /** Legacy registry id still present in SUBGRAPH.md before migration. */
  legacyTargetSkill?: string | null
  /** `resolved` when a usable path is present, else `missing`. */
  status: SubgraphMembershipStatus
}

/**
 * Project the skill's topology into the list of subgraphs it actually
 * references, by path. Subgraph phases are identified by `mode === "subgraph"`;
 * their `path` (from R4) determines resolved-vs-missing. Pure and side-effect
 * free so it is unit-testable and renderable synchronously.
 */
export function subgraphMembership(skillDetail?: SkillDetail): SubgraphMembership[] {
  const topology = skillDetail?.graph_topology ?? []
  const memberships: SubgraphMembership[] = []
  for (const row of topology) {
    if (row.mode !== "subgraph") continue
    const reference = resolveSubgraphReference(row, skillDetail?.files)
    memberships.push({
      id: row.id,
      label: row.id,
      filePath: subgraphFilePath(row),
      path: reference.path,
      ...(reference.legacyTargetSkill ? { legacyTargetSkill: reference.legacyTargetSkill } : {}),
      status: reference.status,
    })
  }
  return memberships
}

function subgraphFilePath(row: Pick<NonNullable<SkillDetail["graph_topology"]>[number], "id" | "src">): string {
  const trimmedSrc = row.src.trim()
  if (!trimmedSrc) {
    return `phases/${row.id}/SUBGRAPH.md`
  }
  if (trimmedSrc.endsWith("/SUBGRAPH.md")) {
    return trimmedSrc
  }
  return `${trimmedSrc.replace(/\/+$/, "")}/SUBGRAPH.md`
}
