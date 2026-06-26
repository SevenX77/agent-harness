import type { Edge } from '@xyflow/react'
import type { GraphTopologyItem } from '@/api/types'
import type { ContextEdgeData } from '@/components/edges/ContextEdge'
import {
  buildEdges,
  INPUT_ID,
  SUBGRAPH_PREVIEW_INPUT_TARGET_HANDLE_ID,
  type GlobalNodeData,
  type GraphCanvasNode,
  type SkillGraphNode,
  type SkillGraphNodeData,
  type SubgraphGroupNodeData,
} from '@/components/nodes'
import { CycleDetectedError, getAutoLayoutedElements } from '@/lib/layout'
import { buildNodesFromTopology } from './build-nodes'

const SKILL_NODE_WIDTH = 260
const SKILL_NODE_HEIGHT = 120
const IO_NODE_WIDTH = 180
const IO_NODE_HEIGHT = 80

const CONTAINER_PADDING = 28
const CONTAINER_HEADER = 44
const CONTAINER_GAP = 120
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

function childNodeId(parentNodeId: string, childId: string): string {
  return `${PREVIEW_PREFIX}::node::${parentNodeId}::${childId}`
}

function childEdgeId(parentNodeId: string, edgeId: string): string {
  return `${PREVIEW_PREFIX}::edge::${parentNodeId}::${edgeId}`
}

function bridgeEdgeId(parentNodeId: string, targetId: string): string {
  return `${PREVIEW_PREFIX}::bridge::${parentNodeId}::${targetId}`
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

interface ChildLayout {
  nodes: GraphCanvasNode[]
  edges: Edge<ContextEdgeData>[]
  contentWidth: number
  contentHeight: number
  inputCenter: { x: number; y: number }
}

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
  const input = nodes.find((node) => node.id === INPUT_ID)

  return {
    nodes,
    edges: laid.edges,
    contentWidth: maxRight - minLeft,
    contentHeight: maxBottom - minTop,
    inputCenter: input?.position ?? { x: IO_NODE_WIDTH / 2, y: IO_NODE_HEIGHT / 2 },
  }
}

function bridgeEdge(
  id: string,
  source: string,
  target: string,
  targetHandle?: string,
): Edge<ContextEdgeData> {
  return {
    id,
    source,
    target,
    targetHandle,
    type: 'contextEdge',
    selectable: false,
    focusable: false,
    deletable: false,
    reconnectable: false,
    style: { strokeWidth: 1.5 },
    zIndex: PREVIEW_EDGE_Z_INDEX,
    data: {
      hasTraceData: false,
      sourcePhaseId: source,
      targetPhaseId: target,
    },
  }
}

function readonlyChildNode(parentNodeId: string, node: GraphCanvasNode, left: number, top: number): GraphCanvasNode {
  const id = childNodeId(parentNodeId, node.id)
  const { width, height } = nodeSize(node.type)
  const base = {
    ...node,
    id,
    position: {
      x: left + node.position.x,
      y: top + node.position.y,
    },
    width,
    height,
    style: { ...node.style, width, height },
    draggable: false,
    selectable: false,
    connectable: false,
    deletable: false,
    zIndex: CHILD_NODE_Z_INDEX,
  }

  if (node.type === 'skill') {
    return {
      ...base,
      data: {
        ...(node.data as SkillGraphNodeData),
        isSubgraphPreview: true,
        isExpanded: false,
        onToggleSubgraph: undefined,
        onToggleSteps: undefined,
        onStepsSave: undefined,
      },
    } as GraphCanvasNode
  }

  return {
    ...base,
    data: {
      ...(node.data as GlobalNodeData),
      isSubgraphPreview: true,
    },
  } as GraphCanvasNode
}

function readonlyChildEdge(parentNodeId: string, edge: Edge<ContextEdgeData>): Edge<ContextEdgeData> {
  const source = childNodeId(parentNodeId, edge.source)
  const target = childNodeId(parentNodeId, edge.target)
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
    },
  }
}

function groupNode(
  request: SubgraphExpansionRequest,
  left: number,
  top: number,
  width: number,
  height: number,
  status: SubgraphGroupNodeData['status'],
  childName?: string,
  message?: string,
): GraphCanvasNode {
  return {
    id: groupNodeId(request.parentNodeId),
    type: 'subgraphGroup',
    position: { x: left + width / 2, y: top + height / 2 },
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
): { nodes: GraphCanvasNode[]; edges: Edge<ContextEdgeData>[] } {
  if (expansions.length === 0) {
    return { nodes: [], edges: [] }
  }

  const parentById = new Map(parentNodes.map((node) => [node.id, node]))
  const nodes: GraphCanvasNode[] = []
  const edges: Edge<ContextEdgeData>[] = []

  for (const request of expansions) {
    const parent = parentById.get(request.parentNodeId)
    if (!parent) continue

    const parentSize = nodeSize(parent.type)
    const expandOrigin = {
      x: parent.position.x + parentSize.width / 2,
      y: parent.position.y,
    }
    const contentLeft = expandOrigin.x + CONTAINER_GAP
    let status: SubgraphGroupNodeData['status'] = request.view.status
    let message = request.view.status === 'error' ? request.view.message : undefined
    const childName = request.view.status === 'loaded' ? request.view.name : undefined

    if (request.view.status !== 'loaded') {
      const width = 300
      const height = 132
      const left = contentLeft - CONTAINER_PADDING
      const top = parent.position.y - height / 2
      const group = groupNode(request, left, top, width, height, status, childName, message)
      nodes.push(group)
      edges.push(bridgeEdge(bridgeEdgeId(request.parentNodeId, group.id), request.parentNodeId, group.id))
      continue
    }

    let child: ChildLayout
    try {
      child = layoutChild(request.parentNodeId, request.view.phases, request.view.graphTopology)
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
      const group = groupNode(request, left, top, width, height, status, childName, message)
      nodes.push(group)
      edges.push(bridgeEdge(bridgeEdgeId(request.parentNodeId, group.id), request.parentNodeId, group.id))
      continue
    }

    const contentTop = parent.position.y - child.inputCenter.y
    const groupLeft = contentLeft - CONTAINER_PADDING
    const groupTop = contentTop - CONTAINER_HEADER - CONTAINER_PADDING
    const width = child.contentWidth + CONTAINER_PADDING * 2
    const height = child.contentHeight + CONTAINER_HEADER + CONTAINER_PADDING * 2
    const group = groupNode(request, groupLeft, groupTop, width, height, status, childName, message)
    nodes.push(group)
    nodes.push(...child.nodes.map((node) => readonlyChildNode(request.parentNodeId, node, contentLeft, contentTop)))
    edges.push(...child.edges.map((edge) => readonlyChildEdge(request.parentNodeId, edge)))

    edges.push(bridgeEdge(
      bridgeEdgeId(request.parentNodeId, childNodeId(request.parentNodeId, INPUT_ID)),
      request.parentNodeId,
      childNodeId(request.parentNodeId, INPUT_ID),
      SUBGRAPH_PREVIEW_INPUT_TARGET_HANDLE_ID,
    ))
  }

  return { nodes, edges }
}
