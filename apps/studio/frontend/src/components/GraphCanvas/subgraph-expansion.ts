import type { Edge } from '@xyflow/react'
import type { GraphTopologyItem } from '@/api/types'
import type { ContextEdgeData } from '@/components/edges/ContextEdge'
import {
  buildEdges,
  INPUT_ID,
  OUTPUT_ID,
  type GraphCanvasNode,
  type SkillGraphNode,
  type SkillGraphNodeData,
  type SubgraphGroupNodeData,
} from '@/components/nodes'
import { buildNodesFromTopology } from './build-nodes'
import { CycleDetectedError, getAutoLayoutedElements } from '@/lib/layout'

// N2 atom #13 (subgraph-inline-preview): canvas-level inline expansion of a
// subgraph node. Clicking the node's expand toggle reveals the child graph
// INSIDE a dashed container anchored to the parent graph's far right (CANVAS-3 /
// F4 "inline content is real, not mock").
//
// Point 2 (PM 2026-06-23): the child is rendered with the SAME recursive pipeline
// the main canvas uses — `buildNodesFromTopology` (its own global input/output
// nodes + real phase nodes) + `buildEdges` (contextEdge connectors with the
// clickable midpoint dot) + `getAutoLayoutedElements` (dagre TB) — NOT a bespoke
// partial builder. We then offset every laid-out element into the container and
// namespace its id so the canvas interaction handlers skip the read-only preview.

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

// Namespace a child element id under its parent subgraph node so two expanded
// subgraphs (and the parent graph itself) never collide on ids like
// `__global_input__` or a shared phase name.
function previewId(parentNodeId: string, innerId: string): string {
  return `${PREVIEW_PREFIX}::${parentNodeId}::${innerId}`
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
  /** Absolute child path when resolved; '' / raw value for the recovery state. */
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
  /** Laid-out child nodes (global input/output + phases), CENTER positions normalised so the content top-left is (0,0). */
  nodes: GraphCanvasNode[]
  /** Child connector edges (contextEdge), ids/source/target still in child space. */
  edges: Edge<ContextEdgeData>[]
  contentWidth: number
  contentHeight: number
}

/**
 * Lay out the child graph with the EXACT pipeline the main canvas uses, so the
 * inline preview reads identically (own in/out nodes + dotted contextEdge). The
 * returned node positions are normalised so the content's top-left extent is
 * (0,0); the caller translates them into the container. Throws
 * CycleDetectedError (from the shared auto-layout) if the child is cyclic.
 */
function layoutChild(skillId: string, phases: string[], graphTopology: GraphTopologyItem[]): ChildLayout {
  const childNodes = buildNodesFromTopology(skillId, phases, graphTopology, {})
  const childPhaseNodes = childNodes.filter((node): node is SkillGraphNode => node.type === 'skill')
  const childEdges = buildEdges(childPhaseNodes)
  const laid = getAutoLayoutedElements(childNodes, childEdges)

  let minLeft = Number.POSITIVE_INFINITY
  let maxRight = Number.NEGATIVE_INFINITY
  let minTop = Number.POSITIVE_INFINITY
  let maxBottom = Number.NEGATIVE_INFINITY
  for (const node of laid.nodes) {
    const { width, height } = nodeSize(node.type)
    minLeft = Math.min(minLeft, node.position.x - width / 2)
    maxRight = Math.max(maxRight, node.position.x + width / 2)
    minTop = Math.min(minTop, node.position.y - height / 2)
    maxBottom = Math.max(maxBottom, node.position.y + height / 2)
  }
  if (!Number.isFinite(minLeft)) { minLeft = 0; maxRight = 0; minTop = 0; maxBottom = 0 }

  const normalizedNodes = laid.nodes.map((node) => ({
    ...node,
    position: { x: node.position.x - minLeft, y: node.position.y - minTop },
  }))

  return {
    nodes: normalizedNodes,
    edges: laid.edges,
    contentWidth: maxRight - minLeft,
    contentHeight: maxBottom - minTop,
  }
}

const BRIDGE_EDGE_STYLE = { stroke: 'var(--primary, #6366f1)', strokeOpacity: 0.8, strokeWidth: 1.5, strokeDasharray: '6 5' }

function bridgeEdge(id: string, source: string, target: string): Edge<ContextEdgeData> {
  return {
    id,
    source,
    target,
    // Built-in smoothstep dashed line: distinct from the child's interactive
    // contextEdge connectors — it marks the parent→child expansion relationship.
    type: 'smoothstep',
    selectable: false,
    focusable: false,
    deletable: false,
    style: BRIDGE_EDGE_STYLE,
  }
}

/**
 * Build the inline-expansion overlay (group containers + recursively-rendered
 * child graphs + bridge edges) for every expanded subgraph. Pure: positions
 * derive from the supplied parent-node layout, so the caller can layer the result
 * on top of the live (possibly user-dragged) canvas without re-running the main
 * layout.
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

    // Lay the child out first so the container sizes to it. A cyclic child (or any
    // layout failure) degrades to the recovery container instead of throwing.
    let child: ChildLayout | null = null
    let status: SubgraphGroupNodeData['status'] = request.view.status
    let message = request.view.status === 'error' ? request.view.message : undefined
    const childName = request.view.status === 'loaded' ? request.view.name : undefined
    if (request.view.status === 'loaded') {
      try {
        child = layoutChild(request.parentNodeId, request.view.phases, request.view.graphTopology)
      } catch (error) {
        if (error instanceof CycleDetectedError) {
          status = 'error'
          message = '子图存在依赖环，无法在画布内预览'
          child = null
        } else {
          throw error
        }
      }
    }

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
      status,
      childName,
      message,
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

    if (!child) continue

    const contentLeft = containerLeftEdge + CONTAINER_PADDING
    const contentTop = topEdge + CONTAINER_HEADER + CONTAINER_PADDING

    for (const node of child.nodes) {
      const { width: w, height: h } = nodeSize(node.type)
      const isSkill = node.type === 'skill'
      // Read-only preview: strip the live edit callbacks so a preview phase can
      // never mutate the real graph, and flag skill nodes so the canvas handlers
      // skip them. Explicit width/height is REQUIRED — preview nodes live outside
      // useNodesState, so React Flow drops their measurement changes and would
      // otherwise keep them `visibility: hidden` forever.
      const data = isSkill
        ? ({ ...(node.data as SkillGraphNodeData), isSubgraphPreview: true, onToggleSubgraph: undefined, onToggleSteps: undefined, onStepsSave: undefined } as SkillGraphNodeData)
        : node.data
      nodes.push({
        ...node,
        id: previewId(request.parentNodeId, node.id),
        position: { x: contentLeft + node.position.x, y: contentTop + node.position.y },
        data,
        width: w,
        height: h,
        draggable: false,
        selectable: false,
        connectable: false,
        deletable: false,
        zIndex: 1,
      } as GraphCanvasNode)
    }

    for (const edge of child.edges) {
      edges.push({
        ...edge,
        id: previewId(request.parentNodeId, edge.id),
        source: previewId(request.parentNodeId, edge.source),
        target: previewId(request.parentNodeId, edge.target),
        selectable: false,
        focusable: false,
        deletable: false,
        zIndex: 1,
      })
    }

    // Bridge edges thread the parent subgraph node THROUGH the child graph: the
    // node's single inbound/outbound slot maps to the child's own IN/OUT nodes.
    edges.push(bridgeEdge(
      `${PREVIEW_PREFIX}::bridge-in::${request.parentNodeId}`,
      request.parentNodeId,
      previewId(request.parentNodeId, INPUT_ID),
    ))
    edges.push(bridgeEdge(
      `${PREVIEW_PREFIX}::bridge-out::${request.parentNodeId}`,
      previewId(request.parentNodeId, OUTPUT_ID),
      request.parentNodeId,
    ))
  }

  return { nodes, edges }
}
