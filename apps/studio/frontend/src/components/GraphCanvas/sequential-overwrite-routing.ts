import type { CompileError, SkillDetail } from '@/api/types'
import type { GraphCanvasNode, SkillGraphNode } from '@/components/nodes'
import { parsePhaseFrontmatter } from '@/components/studio/panels/phase-frontmatter'
import { joinWorkspacePath, resolveSubgraphPath } from '@/components/studio/subgraph-path'

const SEQUENTIAL_OVERWRITE_CODE = 'F-v3-sequential-overwrite-unauthorized'
const OUTPUT_FIELD_PREFIX = 'io.outputs.properties.'
const PHASE_FILE_RE = /^(?:(?<prefix>.*)\/)?phases\/(?<phaseId>[A-Za-z0-9_-]+)\/(?:LOGIC|SUBGRAPH|SKILL)\.md$/

export interface SequentialOverwriteRoute {
  phaseId: string
  subgraphPaths: string[]
  error: CompileError
}

/**
 * One overwrite conflict as the canvas addresses it: the visible node that
 * would do the overwriting, the field, and the upstream phase that wrote it
 * first. All three come from the engine diagnostic — the canvas decides where
 * to draw the conflict, never whether there is one.
 */
export interface OverwriteConflict {
  nodeId: string
  fieldName: string
  ancestorNodeId: string
}

function normalizeComparablePath(value: string | null | undefined): string | null {
  if (!value) return null
  const normalized = value.trim().replace(/\\/g, '/').replace(/\/+$/, '')
  return normalized.length > 0 ? normalized : null
}

function normalizeErrorCode(value: string | null | undefined): string | null {
  if (!value) return null
  const trimmed = value.trim()
  if (!trimmed) return null
  return trimmed.replace(/^\[/, '').replace(/\]$/, '')
}

export function isSequentialOverwriteCompileError(error: CompileError): boolean {
  return normalizeErrorCode(error.error_code) === SEQUENTIAL_OVERWRITE_CODE
}

function resolveRoutePath(workspaceRoot: string | null | undefined, relativePath: string): string {
  const resolved = workspaceRoot ? joinWorkspacePath(workspaceRoot, relativePath) : relativePath
  return normalizeComparablePath(resolved) ?? relativePath
}

function subgraphPathChain(prefix: string | undefined, workspaceRoot: string | null | undefined): string[] {
  if (!prefix) return []
  const parts = prefix.split('/').filter(Boolean)
  const chain: string[] = []
  const current: string[] = []

  for (let index = 0; index < parts.length; index += 2) {
    if (parts[index] !== 'subgraph' || !parts[index + 1]) {
      break
    }
    current.push('subgraph', parts[index + 1])
    chain.push(resolveRoutePath(workspaceRoot, current.join('/')))
  }

  return chain
}

export function sequentialOverwriteRouteFromCompileError(
  error: CompileError,
  workspaceRoot: string | null | undefined,
): SequentialOverwriteRoute | null {
  if (!isSequentialOverwriteCompileError(error)) return null
  // `file` alone: the engine renders every diagnostic's path against the root
  // it was asked to compile, nested children included, so a conflict two
  // subgraphs deep already arrives as `subgraph/a/subgraph/b/phases/p/...`.
  // This used to fall back to a regex over the message because the engine
  // truncated that path; it stopped doing so, and the fallback with it.
  const file = normalizeComparablePath(error.file)
  if (!file) return null
  const match = PHASE_FILE_RE.exec(file)
  const phaseId = match?.groups?.phaseId
  if (!phaseId) return null

  return {
    phaseId,
    subgraphPaths: subgraphPathChain(match.groups?.prefix, workspaceRoot),
    error,
  }
}

/**
 * The overwrite conflicts a compile pass found, as routes the canvas can draw.
 *
 * The input is the diagnostic list, deliberately — not the per-node projection
 * the badges use. That projection answers "which ROOT node owns this file",
 * and a phase inside a child skill answers it with `null` by design
 * (`studio/diagnostic-paths.ts`): the root phase hosting the child is named by
 * its own `SUBGRAPH.md`, so the child's path cannot name it. Routing asks a
 * different question — which chain of subgraphs leads to the preview child
 * that should show the conflict — and the path answers that one itself. Reading
 * routes out of the node buckets meant every nested conflict was dropped before
 * it got here, which is exactly the case this whole module exists for (ledger
 * N6, measured 2026-08-21 on a two-level fixture).
 */
export function sequentialOverwriteRoutesFromCompileErrors(
  errors: readonly CompileError[],
  workspaceRoot: string | null | undefined,
): SequentialOverwriteRoute[] {
  const routes: SequentialOverwriteRoute[] = []
  const seen = new Set<string>()

  for (const error of errors) {
    const route = sequentialOverwriteRouteFromCompileError(error, workspaceRoot)
    if (!route) continue
    const key = `${route.subgraphPaths.join('\0')}\0${route.phaseId}`
    if (seen.has(key)) continue
    seen.add(key)
    routes.push(route)
  }

  return routes
}

function nodeSubgraphPathKeys(node: SkillGraphNode): string[] {
  const keys: string[] = []
  const resolved = normalizeComparablePath(resolveSubgraphPath(node.data.subgraphPath, node.data.workspaceRoot))
  if (resolved) keys.push(resolved)
  if (typeof node.data.subgraphPath === 'string') {
    const raw = normalizeComparablePath(node.data.subgraphPath)
    if (raw) keys.push(raw)
  }
  return keys
}

function findSubgraphNodeByPath(nodes: readonly GraphCanvasNode[], targetPath: string): SkillGraphNode | null {
  const target = normalizeComparablePath(targetPath)
  if (!target) return null

  for (const node of nodes) {
    if (node.type !== 'skill') continue
    if (nodeSubgraphPathKeys(node).some((candidate) => candidate === target)) {
      return node
    }
  }

  return null
}

function phaseIdForNode(node: SkillGraphNode): string {
  return typeof node.data.phaseId === 'string' && node.data.phaseId ? node.data.phaseId : node.id
}

function findRouteTerminalSubgraphNode(
  nodes: readonly GraphCanvasNode[],
  route: SequentialOverwriteRoute,
): SkillGraphNode | null {
  let terminal: SkillGraphNode | null = null
  for (const path of route.subgraphPaths) {
    const node = findSubgraphNodeByPath(nodes, path)
    if (!node) return null
    terminal = node
  }
  return terminal
}

function isPreviewChildOf(nodeId: string, parentId: string): boolean {
  return nodeId.startsWith(`__subpreview__::node::${parentId}::`)
}

function findRoutePhaseNode(
  nodes: readonly GraphCanvasNode[],
  route: SequentialOverwriteRoute,
): SkillGraphNode | null {
  const terminal = findRouteTerminalSubgraphNode(nodes, route)
  for (const node of nodes) {
    if (node.type !== 'skill') continue
    if (phaseIdForNode(node) !== route.phaseId) continue
    if (!terminal && !node.id.startsWith('__subpreview__::')) return node
    if (terminal && isPreviewChildOf(node.id, terminal.id)) return node
  }
  return null
}

function conflictDetailsFromError(error: CompileError): { fieldName: string; ancestorNodeId: string } | null {
  const fieldPath = typeof error.field === 'string' ? error.field.trim() : ''
  const ancestorNodeId = typeof error.conflicting_phase === 'string' ? error.conflicting_phase.trim() : ''
  if (!fieldPath.startsWith(OUTPUT_FIELD_PREFIX) || !ancestorNodeId) return null
  const fieldName = fieldPath.slice(OUTPUT_FIELD_PREFIX.length)
  if (!fieldName) return null
  return { fieldName, ancestorNodeId }
}

export function sequentialOverwriteConflictForVisibleNode(
  nodes: readonly GraphCanvasNode[],
  route: SequentialOverwriteRoute,
): { nodeId: string; fieldName: string; ancestorNodeId: string } | null {
  const node = findRoutePhaseNode(nodes, route)
  if (!node) return null
  const details = conflictDetailsFromError(route.error)
  if (!details) return null
  return { nodeId: node.id, ...details }
}

export function currentFileAllowsSequentialOverwrite(
  nodes: readonly GraphCanvasNode[],
  rootDetail: SkillDetail | null | undefined,
  conflict: { nodeId: string; fieldName: string },
): boolean {
  const node = nodes.find((candidate): candidate is SkillGraphNode => (
    candidate.type === 'skill' && candidate.id === conflict.nodeId
  ))
  if (!node) return false

  const detail = node.data.resolvedSkillDetail ?? rootDetail
  const filePath = node.data.filePath
  if (!detail || !filePath) return false

  const markdown = detail.files?.[filePath]
  if (!markdown) return false

  const parsed = parsePhaseFrontmatter(markdown)
  if (!parsed.ok) return false

  const allowSequentialOverwrite = parsed.frontmatter.allow_sequential_overwrite
  return Array.isArray(allowSequentialOverwrite)
    && allowSequentialOverwrite.includes(conflict.fieldName)
}

export function findNextSubgraphExpansionNode(
  nodes: readonly GraphCanvasNode[],
  expandedSubgraphs: ReadonlySet<string>,
  routes: readonly SequentialOverwriteRoute[],
): string | null {
  for (const route of routes) {
    for (const path of route.subgraphPaths) {
      const node = findSubgraphNodeByPath(nodes, path)
      if (!node) break
      if (!expandedSubgraphs.has(node.id)) {
        return node.id
      }
    }
  }
  return null
}
