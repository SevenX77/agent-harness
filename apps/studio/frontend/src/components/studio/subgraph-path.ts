import type { GraphTopologyItem } from "@/api/types"
import { parsePhaseFrontmatter } from "@/components/studio/panels/phase-frontmatter"
import { isAbsolutePath } from "@/components/studio/workspace-identity"

export type SubgraphReferenceStatus = "resolved" | "missing" | "migration-required"

export interface SubgraphReferenceState {
  path: string | null
  legacyTargetSkill: string | null
  status: SubgraphReferenceStatus
}

export function normalizeAbsoluteSubgraphPath(value: unknown): string | null {
  if (typeof value !== "string") {
    return null
  }
  const trimmed = value.trim()
  if (!trimmed || !isAbsolutePath(trimmed)) {
    return null
  }
  return trimmed
}

export function legacySubgraphTargetSkill(markdown: string | undefined): string | null {
  if (!markdown) {
    return null
  }
  const parsed = parsePhaseFrontmatter(markdown)
  if (!parsed.ok) {
    return null
  }
  return normalizedLegacyTargetSkill(parsed.frontmatter.target_skill ?? parsed.frontmatter.targetSkill)
}

export function resolveSubgraphReference(
  row: Pick<GraphTopologyItem, "id" | "src" | "path">,
  files: Record<string, string> | undefined,
): SubgraphReferenceState {
  const path = normalizeAbsoluteSubgraphPath(row.path)
  if (path) {
    return { path, legacyTargetSkill: null, status: "resolved" }
  }

  const legacyTargetSkill = legacySubgraphTargetSkill(files?.[subgraphFilePath(row)])
  if (legacyTargetSkill) {
    return { path: null, legacyTargetSkill, status: "migration-required" }
  }

  return { path: null, legacyTargetSkill: null, status: "missing" }
}

export function invalidSubgraphPathMessage(path: string): string {
  return `Subgraph preview requires an absolute path. Legacy child reference ${path} must be migrated from target_skill to path.`
}

function normalizedLegacyTargetSkill(value: unknown): string | null {
  if (typeof value !== "string") {
    return null
  }
  const trimmed = value.trim()
  return trimmed.length > 0 ? trimmed : null
}

function subgraphFilePath(row: Pick<GraphTopologyItem, "id" | "src">): string {
  const trimmedSrc = row.src.trim()
  if (!trimmedSrc) {
    return `phases/${row.id}/SUBGRAPH.md`
  }
  if (trimmedSrc.endsWith("/SUBGRAPH.md")) {
    return trimmedSrc
  }
  return `${trimmedSrc.replace(/\/+$/, "")}/SUBGRAPH.md`
}
