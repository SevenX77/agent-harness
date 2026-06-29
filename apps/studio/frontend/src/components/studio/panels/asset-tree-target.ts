import type { SkillGraphNodeData } from "@/components/GraphCanvas"
import type { SubgraphMembership } from "./subgraph-membership"

/**
 * Where the Assets panel should reveal + highlight the file for the currently
 * selected canvas node.
 *
 * - `section: "skill"` → the node belongs to the open skill, so its file lives in
 *   the top "Skill Files" tree.
 * - `section: "subgraph"` → the node belongs to a nested child graph (its
 *   skillId/workspaceRoot differs from the open skill, the same signal Panels.tsx
 *   uses for `selectedNodeUsesDifferentSkill`), so its file lives under a
 *   "Subgraphs Files" block keyed by that child root.
 *
 * `filePath` is relative to the node's own skill root; `ancestorDirs` are the
 * directory paths (root-first, including the "" root) that must be expanded to
 * reveal it.
 */
export interface AssetTreeTarget {
  section: "skill" | "subgraph"
  filePath: string
  ancestorDirs: string[]
  /** Absolute child workspace root to match a Subgraphs Files block (subgraph only). */
  subgraphRoot: string | null
}

const PHASE_FILE_PATTERN = /^phases\/([^/]+)\/(?:SKILL|LOGIC|SUBGRAPH)\.md$/

/**
 * Reverse of the node→file mapping: the phase id a node-definition file belongs
 * to, or null when the path is not a `phases/<id>/{SKILL,LOGIC,SUBGRAPH}.md`
 * node file. Lets a file click in the Assets tree select its canvas node.
 */
export function phaseIdFromFilePath(path: string): string | null {
  const match = PHASE_FILE_PATTERN.exec(path.replace(/\\/g, "/"))
  return match ? match[1] : null
}

/** The directory paths that must be expanded to reveal `filePath`, root ("") first. */
export function ancestorDirsForFile(filePath: string): string[] {
  const parts = filePath.replace(/\\/g, "/").split("/").filter(Boolean)
  const dirs = [""]
  for (let i = 0; i < parts.length - 1; i += 1) {
    dirs.push(parts.slice(0, i + 1).join("/"))
  }
  return dirs
}

function normalizePath(value: string | null | undefined): string | null {
  const trimmed = value?.trim()
  if (!trimmed) return null
  return trimmed.replace(/\\/g, "/").replace(/\/+$/, "")
}

/**
 * Find the deepest subgraph whose folder (its absolute `path`, made root-relative)
 * contains `filePath`, and the part of the file path BELOW that folder. Skill
 * Files paths are relative to the OPEN skill root (e.g.
 * `subgraph/event-timeline/phases/extract/SKILL.md`), unlike the Subgraphs Files
 * blocks whose paths are already child-root-relative. External subgraphs (outside
 * the open root) never appear in the Skill Files tree, so they are skipped.
 */
function findOwningSubgraph(
  filePath: string,
  rootAbs: string | null,
  subgraphs: readonly SubgraphMembership[],
): { id: string; remainder: string } | null {
  const file = normalizePath(filePath)
  const root = normalizePath(rootAbs)
  if (!file || !root) return null

  const fileLower = file.toLowerCase()
  const rootLower = root.toLowerCase()

  let best: { relFolder: string; id: string } | null = null
  for (const subgraph of subgraphs) {
    const abs = normalizePath(subgraph.path)
    if (!abs) continue
    const absLower = abs.toLowerCase()
    if (!absLower.startsWith(`${rootLower}/`)) continue
    const relFolder = absLower.slice(rootLower.length + 1)
    if (fileLower !== relFolder && !fileLower.startsWith(`${relFolder}/`)) continue
    if (!best || relFolder.length > best.relFolder.length) {
      best = { relFolder, id: subgraph.id }
    }
  }
  if (!best) return null
  return { id: best.id, remainder: file.slice(best.relFolder.length + 1) }
}

/** The phase-id chain ("a/b/c" → ["a","b","c"]) a subgraph id encodes. */
function phaseChainFromSubgraphId(id: string): string[] {
  return id.split("/").filter(Boolean)
}

/**
 * Map a skill-root-relative file path (Skill Files tree) to the root→leaf
 * phase-id chain of the subgraph CHILD node it defines, or null when the file is
 * not a `phases/<id>/{SKILL,LOGIC,SUBGRAPH}.md` node file under a known subgraph.
 * The chain is the owning subgraph's id chain plus the leaf phase id — exactly
 * what GraphCanvas needs to expand ancestors + select the node.
 */
export function subgraphChildPhaseChainForFile(
  filePath: string,
  rootAbs: string | null,
  subgraphs: readonly SubgraphMembership[],
): string[] | null {
  const owner = findOwningSubgraph(filePath, rootAbs, subgraphs)
  if (!owner) return null
  const childPhaseId = phaseIdFromFilePath(owner.remainder)
  if (!childPhaseId) return null
  return [...phaseChainFromSubgraphId(owner.id), childPhaseId]
}

/**
 * Map a skill-root-relative file path to the phase-id chain of the subgraph whose
 * OWN `GRAPH.md` it is (e.g. `subgraph/event-timeline/GRAPH.md` → the subgraph's
 * chain), or null when the file is not a subgraph root GRAPH.md. Used to expand a
 * subgraph's inline topology when its GRAPH.md is clicked.
 */
export function subgraphGraphChainForFile(
  filePath: string,
  rootAbs: string | null,
  subgraphs: readonly SubgraphMembership[],
): string[] | null {
  const owner = findOwningSubgraph(filePath, rootAbs, subgraphs)
  if (!owner) return null
  if (owner.remainder.toLowerCase() !== "graph.md") return null
  return phaseChainFromSubgraphId(owner.id)
}

function normalizeRoot(value: string | null | undefined): string | null {
  const trimmed = value?.trim()
  if (!trimmed) return null
  return trimmed.replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase()
}

export function assetTreeTargetForNode(
  selectedNode: { id: string; data: SkillGraphNodeData } | null,
  context: { rootTarget: string | null; skillId: string | null },
): AssetTreeTarget | null {
  const data = selectedNode?.data
  const filePath = data?.filePath?.trim()
  if (!data || !filePath) {
    return null
  }

  const nodeSkillId = data.skillId ?? null
  const nodeRoot = data.workspaceRoot ?? null
  // Same "different skill" test Panels.tsx applies: a node whose skill id or
  // workspace root diverges from the open skill is a nested child-graph node.
  const isSubgraphChild = Boolean(
    (nodeSkillId && nodeSkillId !== context.skillId)
    || (nodeRoot && normalizeRoot(nodeRoot) !== normalizeRoot(context.rootTarget)),
  )

  return {
    section: isSubgraphChild ? "subgraph" : "skill",
    filePath,
    ancestorDirs: ancestorDirsForFile(filePath),
    subgraphRoot: isSubgraphChild ? nodeRoot ?? null : null,
  }
}
