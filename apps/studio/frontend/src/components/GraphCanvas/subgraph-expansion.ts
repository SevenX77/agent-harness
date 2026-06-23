import type { Edge, Node } from '@xyflow/react'
import type { GraphTopologyItem } from '@/api/types'
import type { ContextEdgeData } from '@/components/edges/ContextEdge'
import type { GraphCanvasNode, SkillGraphNodeData, SubgraphGroupNodeData } from '@/components/nodes'
import { getAutoLayoutedElements } from '@/lib/layout'

// N2 atom #13 (subgraph-inline-preview): canvas-level inline expansion of a
// subgraph node. Clicking the node's expand toggle reveals the child graph's
// REAL phases as canvas nodes + edges inside a dashed container anchored to the
// parent graph's far right (CANVAS-3 / F4 "inline content is real, not mock").
// This module is the pure geometry/topology builder — given the laid-out parent
// nodes and each expanded child's resolved topology, it produces the group
// container node, the child phase nodes (positioned with the SAME dagre TB
// layout the main canvas uses), the child intra-dependency edges, and the
// bridge edges that thread the parent expand node through the revealed subgraph.

// Node sizes mirror lib/layout.ts so the parent bounding box / child sub-layout
// agree with what dagre produced for the main canvas.
const SKILL_NODE_WIDTH = 260
const SKILL_NODE_HEIGHT = 120
const IO_NODE_WIDTH = 180
const IO_NODE_HEIGHT = 80

const CONTAINER_PADDING = 28
const CONTAINER_HEADER = 44
// Gap between the parent graph's right edge and the container's left edge.
const CONTAINER_GAP = 160
// Vertical gap kept between two stacked containers (multiple subgraphs expanded).
const CONTAINER_STACK_GAP = 56

// Shared prefix that marks every node/edge this module emits as a read-only
// preview element, so the canvas interaction handlers (select / drill / edge
// context menu) can cheaply skip them without threading extra flags around.
const PREVIEW_PREFIX = '__subpreview__'

export function isSubgraphPreviewId(id: string): boolean {
  return id.startsWith(PREVIEW_PREFIX)
}

function childNodeId(parentNodeId: string, phase: string): string {
  return `${PREVIEW_PREFIX}::node::${parentNodeId}::${phase}`
}

function groupNodeId(parentNodeId: string): string {
  return `${PREVIEW_PREFIX}::group::${parentNodeId}`
}

export type ExpandedSubgraphView =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'loaded'; name?: string; phases: string[]; graphTopology: GraphTopologyItem[] }

export interface SubgraphExpansionRequest {
  parentNodeId: string
  parentLabel: string
  path: string
  view: ExpandedSubgraphView
}

export interface PositionedParentNode {
  id: string
  type?: string
  position: { x: number; y: number }
}

function nodeSize(type: string | undefined): { width: number; height: number } {
  if (type === 'globalInput' || type === 'globalOutput') {
    return { width: IO_NODE_WIDTH, height: IO_NODE_HEIGHT }
  }
  return { width: SKILL_NODE_WIDTH, height: SKILL_NODE_HEIGHT }
}

function parentBoundingBox(nodes: PositionedParentNode[]): { right: number; top: number; bottom: number } {
  let right = 0
  let top = Number.POSITIVE_INFINITY
  let bottom = Number.NEGATIVE_INFINITY
  for (const node of nodes) {
    const { width, height } = nodeSize(node.type)
    right = Math.max(right, node.position.x + width / 2)
    top = Math.min(top, node.position.y - height / 2)
    bottom = Math.max(bottom, node.position.y + height / 2)
  }
  if (!Number.isFinite(top)) top = 0
  if (!Number.isFinite(bottom)) bottom = 0
  return { right, top, bottom }
}

interface ChildLayout {
  /** Local (container-relative, pre-translate) center for each child phase. */
  localCenters: Map<string, { x: number; y: number }>
  contentWidth: number
  contentHeight: number
  intraEdges: { source: string; target: string }[]
  entryPhases: string[]
  terminalPhases: string[]
}

/**
 * Lay out the child phases with the SAME dagre TB layout the main canvas uses,
 * and derive the entry phases (no dependency) and terminal phases (no dependent)
 * the parent bridge edges connect to. `phases` is the authoritative presence/
 * order list; a phase the child graph did not declare is never invented.
 */
function layoutChild(phases: string[], graphTopology: GraphTopologyItem[]): ChildLayout {
  const depsById = new Map(graphTopology.map((row) => [row.id, (row.depends_on ?? []).filter((dep) => dep && dep !== 'input')]))
  const present = new Set(phases)

  const intraEdges: { source: string; target: string }[] = []
  const dependents = new Map<string, number>()
  for (const phase of phases) {
    for (const dep of depsById.get(phase) ?? []) {
      if (!present.has(dep)) continue
      intraEdges.push({ source: dep, target: phase })
      dependents.set(dep, (dependents.get(dep) ?? 0) + 1)
    }
  }

  const entryPhases = phases.filter((phase) => (depsById.get(phase) ?? []).filter((dep) => present.has(dep)).length === 0)
  const terminalPhases = phases.filter((phase) => (dependents.get(phase) ?? 0) === 0)

  // Reuse the canvas auto-layout (dagre TB) on minimal skill nodes so the inline
  // preview reads exactly like the main graph.
  const layoutNodes: Node[] = phases.map((phase) => ({
    id: phase,
    type: 'skill',
    position: { x: 0, y: 0 },
    data: {},
  }))
  const layoutEdges: Edge[] = intraEdges.map((edge) => ({
    id: `${edge.source}->${edge.target}`,
    source: edge.source,
    target: edge.target,
  }))
  const laid = getAutoLayoutedElements(layoutNodes, layoutEdges)

  const localCenters = new Map<string, { x: number; y: number }>()
  let minLeft = Number.POSITIVE_INFINITY
  let maxRight = Number.NEGATIVE_INFINITY
  let minTop = Number.POSITIVE_INFINITY
  let maxBottom = Number.NEGATIVE_INFINITY
  for (const node of laid.nodes) {
    localCenters.set(node.id, { x: node.position.x, y: node.position.y })
    minLeft = Math.min(minLeft, node.position.x - SKILL_NODE_WIDTH / 2)
    maxRight = Math.max(maxRight, node.position.x + SKILL_NODE_WIDTH / 2)
    minTop = Math.min(minTop, node.position.y - SKILL_NODE_HEIGHT / 2)
    maxBottom = Math.max(maxBottom, node.position.y + SKILL_NODE_HEIGHT / 2)
  }
  // Normalise so the content's top-left local extent is (0,0).
  const normalized = new Map<string, { x: number; y: number }>()
  for (const [id, center] of localCenters) {
    normalized.set(id, { x: center.x - minLeft, y: center.y - minTop })
  }

  return {
    localCenters: normalized,
    contentWidth: maxRight - minLeft,
    contentHeight: maxBottom - minTop,
    intraEdges,
    entryPhases,
    terminalPhases,
  }
}

const PREVIEW_EDGE_STYLE = { stroke: 'var(--primary, #6366f1)', strokeOpacity: 0.55, strokeWidth: 1.5 }
const BRIDGE_EDGE_STYLE = { stroke: 'var(--primary, #6366f1)', strokeOpacity: 0.8, strokeWidth: 1.5, strokeDasharray: '6 5' }

function previewEdge(id: string, source: string, target: string, style: Record<string, unknown>): Edge<ContextEdgeData> {
  return {
    id,
    source,
    target,
    // Built-in smoothstep renderer: a clean read-only line, distinct from the
    // interactive contextEdge (which would render a meaningless trace button for
    // these synthetic ids).
    type: 'smoothstep',
    selectable: false,
    focusable: false,
    deletable: false,
    style,
  }
}

function previewChildNode(
  request: SubgraphExpansionRequest,
  phase: string,
  mode: string,
  dependsOn: string[],
  absoluteCenter: { x: number; y: number },
): GraphCanvasNode {
  const data: SkillGraphNodeData = {
    skillId: request.parentNodeId,
    label: phase,
    mode,
    status: 'idle',
    dependsOn,
    isSubgraphPreview: true,
  }
  return {
    id: childNodeId(request.parentNodeId, phase),
    type: 'skill',
    position: absoluteCenter,
    data,
    // Explicit dimensions are REQUIRED: these preview nodes are layered on top of
    // the useNodesState-backed canvas, so they never appear in that state and
    // React Flow's measurement changes for them are dropped by onNodesChange.
    // Without a known size React Flow keeps an unmeasured node `visibility:
    // hidden`, so the dashed container would size correctly (the group node DOES
    // carry explicit dims) yet render empty. Stating the size up front skips the
    // measurement React Flow can never apply here.
    width: SKILL_NODE_WIDTH,
    height: SKILL_NODE_HEIGHT,
    draggable: false,
    selectable: false,
    connectable: false,
    deletable: false,
    zIndex: 1,
  }
}

/**
 * Build the inline-expansion overlay (group containers + child nodes + edges)
 * for every expanded subgraph. Pure: positions derive from the supplied
 * parent-node layout, so the caller can layer the result on top of the live
 * (possibly user-dragged) canvas without re-running the main layout.
 */
export function buildSubgraphExpansion(
  parentNodes: PositionedParentNode[],
  expansions: SubgraphExpansionRequest[],
): { nodes: GraphCanvasNode[]; edges: Edge<ContextEdgeData>[] } {
  if (expansions.length === 0) {
    return { nodes: [], edges: [] }
  }

  const parentById = new Map(parentNodes.map((node) => [node.id, node]))
  const bbox = parentBoundingBox(parentNodes)
  const containerLeftEdge = bbox.right + CONTAINER_GAP

  const nodes: GraphCanvasNode[] = []
  const edges: Edge<ContextEdgeData>[] = []

  // Track the bottom edge of the last placed container so multiple simultaneously
  // expanded subgraphs stack downward without overlapping.
  let nextFreeTop = bbox.top

  for (const request of expansions) {
    const parent = parentById.get(request.parentNodeId)
    if (!parent) continue

    const loaded = request.view.status === 'loaded' ? request.view : null
    const child = loaded ? layoutChild(loaded.phases, loaded.graphTopology) : null

    const contentWidth = child?.contentWidth ?? 240
    const contentHeight = child?.contentHeight ?? 56
    const width = contentWidth + CONTAINER_PADDING * 2
    const height = contentHeight + CONTAINER_HEADER + CONTAINER_PADDING * 2

    // Vertically align the container with its expand node, but never above the
    // already-placed containers (keeps multiple expansions non-overlapping).
    const preferredTop = parent.position.y - height / 2
    const topEdge = Math.max(preferredTop, nextFreeTop)
    nextFreeTop = topEdge + height + CONTAINER_STACK_GAP

    const groupData: SubgraphGroupNodeData = {
      parentLabel: request.parentLabel,
      path: request.path,
      status: request.view.status,
      childName: loaded?.name,
      message: request.view.status === 'error' ? request.view.message : undefined,
    }
    nodes.push({
      id: groupNodeId(request.parentNodeId),
      type: 'subgraphGroup',
      position: { x: containerLeftEdge + width / 2, y: topEdge + height / 2 },
      data: groupData,
      width,
      height,
      style: { width, height },
      draggable: false,
      selectable: false,
      connectable: false,
      deletable: false,
      zIndex: 0,
    } as GraphCanvasNode)

    if (!loaded || !child) continue

    const modeByPhase = new Map((loaded.graphTopology ?? []).map((row) => [row.id, row.mode]))
    const depsByPhase = new Map((loaded.graphTopology ?? []).map((row) => [row.id, (row.depends_on ?? [])]))
    const contentLeft = containerLeftEdge + CONTAINER_PADDING
    const contentTop = topEdge + CONTAINER_HEADER + CONTAINER_PADDING

    for (const phase of loaded.phases) {
      const local = child.localCenters.get(phase)
      if (!local) continue
      const absoluteCenter = { x: contentLeft + local.x, y: contentTop + local.y }
      const mode = modeByPhase.get(phase) ?? 'logic'
      const dependsOn = (depsByPhase.get(phase) ?? []).map((dep) => childNodeId(request.parentNodeId, dep))
      nodes.push(previewChildNode(request, phase, mode, dependsOn, absoluteCenter))
    }

    for (const edge of child.intraEdges) {
      const source = childNodeId(request.parentNodeId, edge.source)
      const target = childNodeId(request.parentNodeId, edge.target)
      edges.push(previewEdge(`${PREVIEW_PREFIX}::intra::${source}->${target}`, source, target, PREVIEW_EDGE_STYLE))
    }

    // Bridge edges thread the parent expand node THROUGH the revealed subgraph:
    // expand -> each child entry node, each child terminal node -> expand.
    for (const entry of child.entryPhases) {
      const target = childNodeId(request.parentNodeId, entry)
      edges.push(previewEdge(`${PREVIEW_PREFIX}::bridge-in::${request.parentNodeId}->${target}`, request.parentNodeId, target, BRIDGE_EDGE_STYLE))
    }
    for (const terminal of child.terminalPhases) {
      const source = childNodeId(request.parentNodeId, terminal)
      edges.push(previewEdge(`${PREVIEW_PREFIX}::bridge-out::${source}->${request.parentNodeId}`, source, request.parentNodeId, BRIDGE_EDGE_STYLE))
    }
  }

  return { nodes, edges }
}
