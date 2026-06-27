import type { Edge } from '@xyflow/react'
import type { GraphTopologyItem, SkillDetail } from '@/api/types'
import type { ContextEdgeData } from '@/components/edges/ContextEdge'
import {
  SUBGRAPH_BRIDGE_EDGE_TYPE,
  SUBGRAPH_BRIDGE_SOURCE_HANDLE_ID,
  SUBGRAPH_BRIDGE_TARGET_HANDLE_ID,
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
const EXPAND_TOGGLE_RADIUS = 10
const SUBGRAPH_BRIDGE_LENGTH = 92
const CONTAINER_GAP = SUBGRAPH_BRIDGE_LENGTH + CONTAINER_PADDING
const GROUP_Z_INDEX = 0
const CHILD_NODE_Z_INDEX = 3
const PREVIEW_EDGE_Z_INDEX = 2

const PREVIEW_PREFIX = '__subpreview__'

export function isSubgraphPreviewId(id: string): boolean {
  return id.startsWith(PREVIEW_PREFIX)
}

function groupNodeId(parentNodeId: string): string {
  return `${PREVIEW_PREFIX}::group::${parentNodeId}`
}

export function subgraphPreviewChildNodeId(parentNodeId: string, childId: string): string {
  return `${PREVIEW_PREFIX}::node::${parentNodeId}::${childId}`
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
  anchorCenter: { x: number; y: number }
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
  const anchor = nodes.find((node) => node.type === 'skill')

  const layout = {
    nodes,
    edges: laid.edges,
    contentWidth: maxRight - minLeft,
    contentHeight: maxBottom - minTop,
    anchorCenter: anchor?.position ?? { x: 0, y: 0 },
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
  const { width, height } = nodeSize(node)
  const base = {
    ...node,
    id,
    parentId: groupId,
    position: {
      x: CONTAINER_PADDING + node.position.x,
      y: CONTAINER_HEADER + CONTAINER_PADDING + node.position.y,
    },
    width,
    height,
    style: { ...node.style, width, height },
    zIndex: CHILD_NODE_Z_INDEX,
  }

  if (node.type !== 'skill') return base as GraphCanvasNode
  const data = node.data as SkillGraphNodeData
  const isSubgraphNode = data.mode === 'subgraph' || Boolean(data.subgraphPath)
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
      onToggleSteps: undefined,
      onStepsSave: undefined,
    },
  } as GraphCanvasNode
}

function readonlyChildEdge(parentNodeId: string, edge: Edge<ContextEdgeData>): Edge<ContextEdgeData> {
  const source = subgraphPreviewChildNodeId(parentNodeId, edge.source)
  const target = subgraphPreviewChildNodeId(parentNodeId, edge.target)
  return {
    ...edge,
    id: childEdgeId(parentNodeId, edge.id),
    source,
    target,
    type: 'contextEdge',
    selectable: false,
    focusable: false,
    deletable: false,
    reconnectable: false,
    zIndex: PREVIEW_EDGE_Z_INDEX,
    data: {
      ...edge.data,
      hasTraceData: false,
      sourcePhaseId: source,
      targetPhaseId: target,
      showContextControl: true,
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
    id: groupNodeId(request.parentNodeId),
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
      bridgeTargetOffsetY: parent.position.y - top,
    },
    width,
    height,
    style: { width, height },
    draggable: false,
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
  const parentGraphRight = parentNodes.reduce((right, node) => {
    const { width } = positionedNodeSize(node)
    return Math.max(right, node.position.x + width / 2)
  }, Number.NEGATIVE_INFINITY)
  const nodes: GraphCanvasNode[] = []
  const edges: Edge<ContextEdgeData>[] = []

  for (const request of expansions) {
    const parent = parentById.get(request.parentNodeId)
    if (!parent) continue

    const parentSize = positionedNodeSize(parent)
    const expandOrigin = {
      x: parent.position.x + parentSize.width / 2 + EXPAND_TOGGLE_RADIUS,
      y: parent.position.y,
    }
    const contentLeft = Math.max(
      expandOrigin.x + CONTAINER_GAP,
      (Number.isFinite(parentGraphRight) ? parentGraphRight : expandOrigin.x) + CONTAINER_GAP,
    )
    let status: SubgraphGroupNodeData['status'] = request.view.status
    let message = request.view.status === 'error' ? request.view.message : undefined
    const childName = request.view.status === 'loaded' ? request.view.name : undefined

    if (request.view.status !== 'loaded') {
      const width = 300
      const height = 132
      const left = contentLeft - CONTAINER_PADDING
      const top = parent.position.y - height / 2
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
      const left = contentLeft - CONTAINER_PADDING
      const top = parent.position.y - height / 2
      const group = groupNode(request, parent, left, top, width, height, status, childName, message)
      nodes.push(group)
      edges.push(visualBridgeEdge(request.parentNodeId, group.id))
      continue
    }

    const contentTop = parent.position.y - child.anchorCenter.y
    const groupLeft = contentLeft - CONTAINER_PADDING
    const groupTop = contentTop - CONTAINER_HEADER - CONTAINER_PADDING
    const width = child.contentWidth + CONTAINER_PADDING * 2
    const height = child.contentHeight + CONTAINER_HEADER + CONTAINER_PADDING * 2
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
    edges.push(...child.edges.map((edge) => readonlyChildEdge(request.parentNodeId, edge)))
  }

  return { nodes, edges }
}
