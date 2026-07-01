import type { Edge } from '@xyflow/react'
import type { GraphTopologyItem, SkillDetail } from '@/api/types'
import type { ContextEdgeData } from '@/components/edges/ContextEdge'
import {
  SUBGRAPH_BRIDGE_EDGE_TYPE,
  SUBGRAPH_BRIDGE_SOURCE_HANDLE_ID,
  SUBGRAPH_BRIDGE_TARGET_HANDLE_ID,
  SUBGRAPH_EXPAND_TOGGLE_RADIUS_PX,
} from '@/components/nodes/subgraph-bridge-handles'
import {
  buildEdges,
  type GraphCanvasNode,
  type SkillGraphNode,
  type SkillGraphNodeData,
  type SubgraphGroupNodeData,
} from '@/components/nodes'
import { CycleDetectedError, getAutoLayoutedElements } from '@/lib/layout'
import { buildNodes, buildNodesFromTopology } from './build-nodes'

const SKILL_NODE_WIDTH = 260
const SKILL_NODE_HEIGHT = 120

const CONTAINER_PADDING = 28
const CONTAINER_HEADER = 44
const SUBGRAPH_BRIDGE_LENGTH = 92
const GROUP_Z_INDEX = 0
const CHILD_NODE_Z_INDEX = 3
const PREVIEW_EDGE_Z_INDEX = 2

const PREVIEW_PREFIX = '__subpreview__'

export function isSubgraphPreviewId(id: string): boolean {
  return id.startsWith(PREVIEW_PREFIX)
}

/** The inline-preview GROUP container node id for an expanded subgraph node —
 * the box that holds the child topology (sits to the right of the subgraph chip). */
export function subgraphGroupNodeId(parentNodeId: string): string {
  return `${PREVIEW_PREFIX}::group::${parentNodeId}`
}

export function subgraphPreviewChildNodeId(parentNodeId: string, childId: string): string {
  return `${PREVIEW_PREFIX}::node::${parentNodeId}::${childId}`
}

/**
 * Resolve a root→leaf phase-id chain into the canvas node id at every depth
 * (root-first). `phaseChain[0]` is a root-canvas phase id (its node id equals the
 * phase id); each subsequent element nests one inline-preview level deeper.
 *
 * Example: ["event_timeline", "event_extraction"] →
 *   ["event_timeline", "__subpreview__::node::event_timeline::event_extraction"]
 */
export function subgraphNodeIdChain(phaseChain: string[]): string[] {
  if (phaseChain.length === 0) return []
  let current = phaseChain[0]
  const chain = [current]
  for (let index = 1; index < phaseChain.length; index += 1) {
    current = subgraphPreviewChildNodeId(current, phaseChain[index])
    chain.push(current)
  }
  return chain
}

/**
 * Resolve a root→leaf phase-id chain pointing at a CHILD node into the ids needed
 * to reveal it: every subgraph ancestor to expand (root-first, `expandIds`) plus
 * the final preview child node id to select (`selectId`). Null when the chain is
 * too short to point at a child (needs ≥1 ancestor + leaf).
 *
 * Example: ["event_timeline", "event_extraction", "review"] →
 *   expandIds: ["event_timeline", "__subpreview__::node::event_timeline::event_extraction"]
 *   selectId:  "__subpreview__::node::__subpreview__::node::event_timeline::event_extraction::review"
 */
export function subgraphRevealNodeIds(
  phaseChain: string[],
): { expandIds: string[]; selectId: string } | null {
  if (phaseChain.length < 2) return null
  const chain = subgraphNodeIdChain(phaseChain)
  return { expandIds: chain.slice(0, -1), selectId: chain[chain.length - 1] }
}

function childEdgeId(parentNodeId: string, edgeId: string): string {
  return `${PREVIEW_PREFIX}::edge::${parentNodeId}::${edgeId}`
}

function bridgeEdgeId(parentNodeId: string): string {
  return `${PREVIEW_PREFIX}::bridge::${parentNodeId}`
}

export type ExpandedSubgraphView =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'loaded'; name?: string; phases: string[]; graphTopology: GraphTopologyItem[]; detail?: SkillDetail }

export interface SubgraphExpansionRequest {
  parentNodeId: string
  parentLabel: string
  path: string
  childSkillId?: string
  topologyOwnerSkillId?: string
  view: ExpandedSubgraphView
}

export interface SubgraphExpansionOptions {
  expandedSubgraphs?: ReadonlySet<string>
  onToggleSubgraph?: (nodeId: string) => void
  expandedSteps?: ReadonlySet<string>
  onToggleSteps?: (nodeId: string) => void
  onStepsSave?: (
    nodeId: string,
    filePath: string,
    currentBody: string,
    nextBody: string,
    parentNodeId: string,
  ) => void
}

export interface SubgraphExpansionResult {
  nodes: GraphCanvasNode[]
  edges: Edge<ContextEdgeData>[]
}

export interface PositionedParentNode {
  id: string
  type?: string
  position: { x: number; y: number }
  width?: number
  height?: number
}

function nodeSize(node?: GraphCanvasNode): { width: number; height: number } {
  if (typeof node?.width === 'number' && typeof node?.height === 'number') {
    return { width: node.width, height: node.height }
  }
  if (node?.type === 'globalInput' || node?.type === 'globalOutput') {
    return { width: 220, height: 80 }
  }
  return { width: SKILL_NODE_WIDTH, height: SKILL_NODE_HEIGHT }
}

function positionedNodeSize(node: PositionedParentNode): { width: number; height: number } {
  if (typeof node.width === 'number' && typeof node.height === 'number') {
    return { width: node.width, height: node.height }
  }
  if (node.type === 'globalInput' || node.type === 'globalOutput') {
    return { width: 220, height: 80 }
  }
  return { width: SKILL_NODE_WIDTH, height: SKILL_NODE_HEIGHT }
}

export function positionedParentNodes(nodes: GraphCanvasNode[]): PositionedParentNode[] {
  const byId = new Map(nodes.map((node) => [node.id, node]))
  const centerCache = new Map<string, { x: number; y: number }>()

  function absoluteCenter(node: GraphCanvasNode): { x: number; y: number } {
    const cached = centerCache.get(node.id)
    if (cached) return cached
    if (!node.parentId) {
      centerCache.set(node.id, node.position)
      return node.position
    }
    const parent = byId.get(node.parentId)
    if (!parent) {
      centerCache.set(node.id, node.position)
      return node.position
    }
    const parentCenter = absoluteCenter(parent)
    const parentSize = nodeSize(parent)
    const center = {
      x: parentCenter.x - parentSize.width / 2 + node.position.x,
      y: parentCenter.y - parentSize.height / 2 + node.position.y,
    }
    centerCache.set(node.id, center)
    return center
  }

  return nodes.map((node) => {
    const size = nodeSize(node)
    return {
      id: node.id,
      type: node.type,
      position: absoluteCenter(node),
      width: size.width,
      height: size.height,
    }
  })
}

interface ChildLayout {
  nodes: GraphCanvasNode[]
  edges: Edge<ContextEdgeData>[]
  contentWidth: number
  contentHeight: number
}

const childLayoutCache = new Map<string, ChildLayout>()

function childLayoutCacheKey(
  skillId: string,
  workspaceRoot: string | null,
  phases: string[],
  graphTopology: GraphTopologyItem[],
  detail?: SkillDetail,
): string {
  const topologySignature = graphTopology
    .map((row) => [
      row.id,
      row.mode ?? '',
      row.path ?? '',
      Array.isArray(row.depends_on) ? row.depends_on.join(',') : '',
    ].join(':'))
    .join('|')
  const detailSignature = detail
    ? [
        JSON.stringify(detail.manifest),
        JSON.stringify(detail.graph_topology ?? []),
        Object.entries(detail.files ?? {})
          .sort(([left], [right]) => left.localeCompare(right))
          .map(([path, content]) => `${path}:${content}`)
          .join('\0'),
      ].join('\0')
    : 'topology-only'
  return `${skillId}\0${workspaceRoot ?? ''}\0${phases.join(',')}\0${topologySignature}\0${detailSignature}`
}

function layoutChild(
  skillId: string,
  workspaceRoot: string | null,
  phases: string[],
  graphTopology: GraphTopologyItem[],
  detail?: SkillDetail,
): ChildLayout {
  const cacheKey = childLayoutCacheKey(skillId, workspaceRoot, phases, graphTopology, detail)
  const cached = childLayoutCache.get(cacheKey)
  if (cached) {
    return cached
  }

  const childDetail = detail ? { ...detail, graph_topology: graphTopology } : undefined
  const childNodes = childDetail
    ? buildNodes(skillId, childDetail, new Set(), () => undefined, {}, {}, {}, {}, {}, workspaceRoot)
    : buildNodesFromTopology(skillId, phases, graphTopology, {}, {}, workspaceRoot)
  const childPhaseNodes = childNodes.filter((node): node is SkillGraphNode => node.type === 'skill')
  const childEdges = buildEdges(childPhaseNodes)
  const laid = getAutoLayoutedElements(childNodes, childEdges)

  let minLeft = Number.POSITIVE_INFINITY
  let maxRight = Number.NEGATIVE_INFINITY
  let minTop = Number.POSITIVE_INFINITY
  let maxBottom = Number.NEGATIVE_INFINITY
  for (const node of laid.nodes) {
    const { width, height } = nodeSize(node)
    minLeft = Math.min(minLeft, node.position.x - width / 2)
    maxRight = Math.max(maxRight, node.position.x + width / 2)
    minTop = Math.min(minTop, node.position.y - height / 2)
    maxBottom = Math.max(maxBottom, node.position.y + height / 2)
  }
  if (!Number.isFinite(minLeft)) {
    minLeft = 0
    maxRight = 0
    minTop = 0
    maxBottom = 0
  }

  const nodes = laid.nodes.map((node) => ({
    ...node,
    position: { x: node.position.x - minLeft, y: node.position.y - minTop },
  })) as GraphCanvasNode[]
  const layout = {
    nodes,
    edges: laid.edges,
    contentWidth: maxRight - minLeft,
    contentHeight: maxBottom - minTop,
  }
  childLayoutCache.set(cacheKey, layout)
  return layout
}

function inlineChildNode(
  parentNodeId: string,
  groupId: string,
  childSkillId: string,
  childWorkspaceRoot: string | null,
  topologyOwnerSkillId: string | undefined,
  childDetail: SkillDetail | undefined,
  node: GraphCanvasNode,
  options: SubgraphExpansionOptions,
): GraphCanvasNode {
  const id = subgraphPreviewChildNodeId(parentNodeId, node.id)
  const nodeStyle = node.style ? { ...node.style } : undefined
  if (nodeStyle) {
    delete nodeStyle.width
    delete nodeStyle.height
  }
  const base = {
    ...node,
    id,
    parentId: groupId,
    position: {
      x: CONTAINER_PADDING + node.position.x,
      y: CONTAINER_HEADER + CONTAINER_PADDING + node.position.y,
    },
    width: undefined,
    height: undefined,
    style: node.style ? nodeStyle : undefined,
    zIndex: CHILD_NODE_Z_INDEX,
  }

  if (node.type !== 'skill') return base as GraphCanvasNode
  const data = node.data as SkillGraphNodeData
  const isSubgraphNode = data.mode === 'subgraph' || Boolean(data.subgraphPath)
  const isAgentNode = data.mode === 'agent' || data.mode === 'skill' || data.mode === 'llm'
  const canEditSteps = isAgentNode && typeof data.agentBody === 'string'
  return {
    ...base,
    data: {
      ...data,
      skillId: childSkillId,
      workspaceRoot: childWorkspaceRoot,
      topologyOwnerSkillId,
      resolvedSkillDetail: childDetail,
      phaseId: data.phaseId ?? node.id,
      isExpanded: isSubgraphNode ? options.expandedSubgraphs?.has(id) === true : false,
      onToggleSubgraph: isSubgraphNode && options.onToggleSubgraph
        ? () => options.onToggleSubgraph?.(id)
        : undefined,
      isStepsExpanded: canEditSteps ? (options.expandedSteps?.has(id) ?? false) : false,
      onToggleSteps: canEditSteps && options.onToggleSteps
        ? () => options.onToggleSteps?.(id)
        : undefined,
      onStepsSave: canEditSteps && options.onStepsSave && data.filePath
        ? (nextBody: string) => options.onStepsSave?.(id, data.filePath!, data.agentBody!, nextBody, parentNodeId)
        : undefined,
    },
  } as GraphCanvasNode
}

function inlineChildEdge(parentNodeId: string, edge: Edge<ContextEdgeData>): Edge<ContextEdgeData> {
  const source = subgraphPreviewChildNodeId(parentNodeId, edge.source)
  const target = subgraphPreviewChildNodeId(parentNodeId, edge.target)
  return {
    ...edge,
    id: childEdgeId(parentNodeId, edge.id),
    source,
    target,
    type: 'contextEdge',
    zIndex: PREVIEW_EDGE_Z_INDEX,
    data: {
      ...edge.data,
      hasTraceData: false,
      sourcePhaseId: source,
      targetPhaseId: target,
      showContextControl: edge.data?.showContextControl !== false,
    },
  }
}

function visualBridgeEdge(parentNodeId: string, groupId: string): Edge<ContextEdgeData> {
  return {
    id: bridgeEdgeId(parentNodeId),
    source: parentNodeId,
    target: groupId,
    sourceHandle: SUBGRAPH_BRIDGE_SOURCE_HANDLE_ID,
    targetHandle: SUBGRAPH_BRIDGE_TARGET_HANDLE_ID,
    type: SUBGRAPH_BRIDGE_EDGE_TYPE,
    selectable: false,
    focusable: false,
    deletable: false,
    reconnectable: false,
    zIndex: PREVIEW_EDGE_Z_INDEX,
    data: {
      hasTraceData: false,
      sourcePhaseId: parentNodeId,
      targetPhaseId: groupId,
      showContextControl: false,
    },
  }
}

interface Rect {
  left: number
  right: number
  top: number
  bottom: number
}

function rectsOverlap(a: Rect, b: Rect): boolean {
  return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top
}

function nodeRect(node: PositionedParentNode): Rect {
  const size = positionedNodeSize(node)
  return {
    left: node.position.x - size.width / 2,
    right: node.position.x + size.width / 2,
    top: node.position.y - size.height / 2,
    bottom: node.position.y + size.height / 2,
  }
}

function groupRect(left: number, top: number, width: number, height: number): Rect {
  return {
    left,
    right: left + width,
    top,
    bottom: top + height,
  }
}

function alignedGroupTop(expandOriginY: number, parentHeight: number): number {
  // Place the frame so the header's vertical center lands on the parent button Y
  // (→ a horizontal bridge). groupNode positions the frame relative to the parent
  // CENTER, but React Flow's center node-origin renders its top-left parentHeight/2
  // lower, so subtract that back out together with the header half-height.
  return expandOriginY - CONTAINER_HEADER / 2 - parentHeight / 2
}

function chooseGroupPlacement(
  parentNodes: PositionedParentNode[],
  parentNodeId: string,
  expandOrigin: { x: number; y: number },
  parentHeight: number,
  width: number,
  height: number,
): { left: number; top: number } {
  const top = alignedGroupTop(expandOrigin.y, parentHeight)
  // Nearest avoidance: start just past the parent's expand toggle, then step
  // right past ONLY the nodes that actually overlap this row band — never past
  // every node on the canvas. Clearing one blocker can reveal another further
  // right, so re-check until the band is clear (guarded against cycles).
  let left = expandOrigin.x + SUBGRAPH_BRIDGE_LENGTH
  for (let guard = 0; guard <= parentNodes.length; guard += 1) {
    const rect = groupRect(left, top, width, height)
    let blockerRight = Number.NEGATIVE_INFINITY
    for (const node of parentNodes) {
      if (node.id === parentNodeId) continue
      const candidate = nodeRect(node)
      if (rectsOverlap(rect, candidate)) {
        blockerRight = Math.max(blockerRight, candidate.right)
      }
    }
    if (!Number.isFinite(blockerRight)) break
    left = blockerRight + SUBGRAPH_BRIDGE_LENGTH
  }
  return { left, top }
}

function groupNode(
  request: SubgraphExpansionRequest,
  parent: PositionedParentNode,
  left: number,
  top: number,
  width: number,
  height: number,
  status: SubgraphGroupNodeData['status'],
  childName?: string,
  message?: string,
): GraphCanvasNode {
  const parentSize = positionedNodeSize(parent)
  const parentLeft = parent.position.x - parentSize.width / 2
  const parentTop = parent.position.y - parentSize.height / 2
  return {
    id: subgraphGroupNodeId(request.parentNodeId),
    type: 'subgraphGroup',
    parentId: request.parentNodeId,
    position: {
      x: left + width / 2 - parentLeft,
      y: top + height / 2 - parentTop,
    },
    data: {
      parentLabel: request.parentLabel,
      path: request.path,
      status,
      childName,
      message,
    },
    width,
    height,
    style: { width, height },
    draggable: true,
    dragHandle: '.subgraph-group-drag-handle',
    selectable: false,
    connectable: false,
    deletable: false,
    zIndex: GROUP_Z_INDEX,
  } as GraphCanvasNode
}

export function buildSubgraphExpansion(
  parentNodes: PositionedParentNode[],
  expansions: SubgraphExpansionRequest[],
  options: SubgraphExpansionOptions = {},
): SubgraphExpansionResult {
  if (expansions.length === 0) {
    return { nodes: [], edges: [] }
  }

  const parentById = new Map(parentNodes.map((node) => [node.id, node]))
  const nodes: GraphCanvasNode[] = []
  const edges: Edge<ContextEdgeData>[] = []

  for (const request of expansions) {
    const parent = parentById.get(request.parentNodeId)
    if (!parent) continue

    const parentSize = positionedNodeSize(parent)
    const expandOrigin = {
      x: parent.position.x + parentSize.width / 2 + SUBGRAPH_EXPAND_TOGGLE_RADIUS_PX,
      y: parent.position.y,
    }
    let status: SubgraphGroupNodeData['status'] = request.view.status
    let message = request.view.status === 'error' ? request.view.message : undefined
    const childName = request.view.status === 'loaded' ? request.view.name : undefined

    if (request.view.status !== 'loaded') {
      const width = 300
      const height = 132
      const { left, top } = chooseGroupPlacement(
        parentNodes,
        request.parentNodeId,
        expandOrigin,
        parentSize.height,
        width,
        height,
      )
      const group = groupNode(request, parent, left, top, width, height, status, childName, message)
      nodes.push(group)
      edges.push(visualBridgeEdge(request.parentNodeId, group.id))
      continue
    }

    let child: ChildLayout
    try {
      child = layoutChild(
        request.childSkillId ?? request.parentNodeId,
        request.path,
        request.view.phases,
        request.view.graphTopology,
        request.view.detail,
      )
    } catch (error) {
      if (!(error instanceof CycleDetectedError)) {
        throw error
      }
      status = 'error'
      message = 'Subgraph contains a dependency cycle and cannot be previewed inline.'
      const width = 360
      const height = 132
      const { left, top } = chooseGroupPlacement(
        parentNodes,
        request.parentNodeId,
        expandOrigin,
        parentSize.height,
        width,
        height,
      )
      const group = groupNode(request, parent, left, top, width, height, status, childName, message)
      nodes.push(group)
      edges.push(visualBridgeEdge(request.parentNodeId, group.id))
      continue
    }

    const width = child.contentWidth + CONTAINER_PADDING * 2
    const height = child.contentHeight + CONTAINER_HEADER + CONTAINER_PADDING * 2
    const { left: groupLeft, top: groupTop } = chooseGroupPlacement(
      parentNodes,
      request.parentNodeId,
      expandOrigin,
      parentSize.height,
      width,
      height,
    )
    const group = groupNode(request, parent, groupLeft, groupTop, width, height, status, childName, message)
    nodes.push(group)
    edges.push(visualBridgeEdge(request.parentNodeId, group.id))
    nodes.push(...child.nodes.map((node) => inlineChildNode(
      request.parentNodeId,
      group.id,
      request.childSkillId ?? request.parentNodeId,
      request.path,
      request.topologyOwnerSkillId,
      request.view.status === 'loaded' ? request.view.detail : undefined,
      node,
      options,
    )))
    edges.push(...child.edges.map((edge) => inlineChildEdge(request.parentNodeId, edge)))
  }

  return { nodes, edges }
}
