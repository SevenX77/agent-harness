import type { SkillDetail } from "@/api/types"
import {
  legacySubgraphTargetSkill,
  normalizeAbsoluteSubgraphPath,
  resolveSubgraphReference,
  type SubgraphReferenceStatus,
} from "@/components/studio/subgraph-path"
import { parsePhaseFrontmatter } from "./phase-frontmatter"

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
  /** 1-based recursive nesting level for indentation and level tags. */
  level: number
  /** The parent skill's phase file that stores the subgraph path. */
  filePath: string
  /** Absolute parent workspace root that owns `filePath`, when known. */
  workspaceRoot?: string | null
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
      level: subgraphLevel(row),
      filePath: subgraphFilePath(row),
      path: reference.path,
      ...(reference.legacyTargetSkill ? { legacyTargetSkill: reference.legacyTargetSkill } : {}),
      status: reference.status,
    })
  }
  return memberships
}

export interface RecursiveSubgraphReadResult {
  content: string
}

export type RecursiveSubgraphReader = (
  workspaceRoot: string,
  relativePath: string,
) => Promise<RecursiveSubgraphReadResult>

export async function loadRecursiveSubgraphMembership(
  topLevel: SubgraphMembership[],
  readFile: RecursiveSubgraphReader,
  options: { maxDepth?: number } = {},
): Promise<SubgraphMembership[]> {
  const maxDepth = options.maxDepth ?? 8
  const seenRoots = new Set<string>()
  const result: SubgraphMembership[] = []

  for (const member of topLevel) {
    result.push(member)
    const children = await nestedSubgraphMembership(member, readFile, maxDepth, seenRoots)
    result.push(...children)
  }

  return result
}

async function nestedSubgraphMembership(
  parent: SubgraphMembership,
  readFile: RecursiveSubgraphReader,
  maxDepth: number,
  seenRoots: Set<string>,
): Promise<SubgraphMembership[]> {
  if (!parent.path || parent.level >= maxDepth) {
    return []
  }

  const rootKey = normalizeWorkspaceKey(parent.path)
  if (seenRoots.has(rootKey)) {
    return []
  }
  seenRoots.add(rootKey)

  let graphMarkdown: string
  try {
    graphMarkdown = (await readFile(parent.path, "GRAPH.md")).content
  } catch {
    return []
  }

  const result: SubgraphMembership[] = []
  for (const phaseId of phaseIdsFromGraph(graphMarkdown)) {
    const filePath = `phases/${phaseId}/SUBGRAPH.md`
    let markdown: string
    try {
      markdown = (await readFile(parent.path, filePath)).content
    } catch {
      continue
    }

    const child = subgraphMembershipFromPhaseFile({
      parent,
      phaseId,
      filePath,
      markdown,
    })
    result.push(child)
    const nested = await nestedSubgraphMembership(child, readFile, maxDepth, seenRoots)
    result.push(...nested)
  }

  return result
}

function subgraphMembershipFromPhaseFile({
  parent,
  phaseId,
  filePath,
  markdown,
}: {
  parent: SubgraphMembership
  phaseId: string
  filePath: string
  markdown: string
}): SubgraphMembership {
  const parsed = parsePhaseFrontmatter(markdown)
  const frontmatter = parsed.ok ? parsed.frontmatter : {}
  const label = stringField(frontmatter.name) ?? phaseId
  const rawPath = stringField(frontmatter.path)
  const absolutePath = rawPath
    ? normalizeAbsoluteSubgraphPath(rawPath) ?? joinWorkspacePath(parent.path ?? "", rawPath)
    : null
  const legacyTargetSkill = legacySubgraphTargetSkill(markdown)

  return {
    id: `${parent.id}/${phaseId}`,
    label,
    level: parent.level + 1,
    filePath,
    workspaceRoot: parent.path,
    path: absolutePath,
    ...(legacyTargetSkill ? { legacyTargetSkill } : {}),
    status: absolutePath ? "resolved" : legacyTargetSkill ? "migration-required" : "missing",
  }
}

function phaseIdsFromGraph(markdown: string): string[] {
  const ids: string[] = []
  const seen = new Set<string>()
  for (const match of markdown.matchAll(/<phase\b[^>]*>([\s\S]*?)<\/phase>/gi)) {
    const id = match[1]?.trim()
    if (!id || seen.has(id)) {
      continue
    }
    seen.add(id)
    ids.push(id)
  }
  return ids
}

function stringField(value: unknown): string | null {
  if (typeof value !== "string") {
    return null
  }
  const trimmed = value.trim()
  return trimmed.length > 0 ? trimmed : null
}

function joinWorkspacePath(root: string, relativePath: string): string {
  const trimmedRoot = root.replace(/[\\/]+$/, "")
  const trimmedRelative = relativePath.replace(/^[\\/]+/, "")
  if (trimmedRoot.includes("\\")) {
    return `${trimmedRoot}\\${trimmedRelative.replace(/\//g, "\\")}`
  }
  return `${trimmedRoot}/${trimmedRelative.replace(/\\/g, "/")}`
}

function normalizeWorkspaceKey(path: string): string {
  return path.replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase()
}

type TopologyRowWithLevel = NonNullable<SkillDetail["graph_topology"]>[number] & {
  depth?: unknown
  level?: unknown
  recursive_level?: unknown
  subgraph_level?: unknown
}

function subgraphLevel(row: TopologyRowWithLevel): number {
  if (typeof row.level === "number" && Number.isFinite(row.level) && row.level >= 1) {
    return Math.floor(row.level)
  }
  if (typeof row.subgraph_level === "number" && Number.isFinite(row.subgraph_level) && row.subgraph_level >= 1) {
    return Math.floor(row.subgraph_level)
  }
  if (typeof row.recursive_level === "number" && Number.isFinite(row.recursive_level) && row.recursive_level >= 1) {
    return Math.floor(row.recursive_level)
  }
  if (typeof row.depth === "number" && Number.isFinite(row.depth) && row.depth >= 0) {
    return Math.floor(row.depth) + 1
  }
  return 1
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
