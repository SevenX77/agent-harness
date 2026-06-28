import type { Edge, NodeChange } from '@xyflow/react'
import type { ContextEdgeData } from '@/components/edges/ContextEdge'
import type { GraphCanvasNode } from '@/components/nodes'

export interface InitialViewportFitState {
  hasLayoutNodes: boolean
  hasFitView: boolean
  initialFitStarted: boolean
  viewportReady: boolean
}

export function shouldRunInitialViewportFit({
  hasLayoutNodes,
  hasFitView,
  initialFitStarted,
  viewportReady,
}: InitialViewportFitState): boolean {
  return hasLayoutNodes && hasFitView && !initialFitStarted && !viewportReady
}

export function layoutCanvasHeightForMode(canvasHeight: number, compactRatio: number): number {
  return compactRatio > 0 ? canvasHeight : 0
}

export function canvasLayoutSignature(
  nodes: readonly GraphCanvasNode[],
  _edges: readonly Edge<ContextEdgeData>[],
  options: { canvasHeight?: number; compactRatio?: number } = {},
): string {
  const nodeSignature = nodes
    .map((node) => `${node.id}:${node.type ?? ''}:${node.position.x},${node.position.y}`)
    .join('|')
  return [
    nodeSignature,
    `height=${options.canvasHeight ?? 0}`,
    `compact=${options.compactRatio ?? 0}`,
  ].join('::')
}

export function mergeLayoutPositions<TNode extends GraphCanvasNode>(
  renderNodes: readonly TNode[],
  layoutNodes: readonly GraphCanvasNode[],
): TNode[] {
  const positionsById = new Map(layoutNodes.map((node) => [node.id, node.position]))
  return renderNodes.map((node) => {
    const position = positionsById.get(node.id)
    return position ? { ...node, position } : node
  })
}

export function mergeStableLayoutPositions<TNode extends GraphCanvasNode>(
  renderNodes: readonly TNode[],
  layoutNodes: readonly GraphCanvasNode[],
  previousPositions: ReadonlyMap<string, GraphCanvasNode['position']>,
): { nodes: TNode[]; positions: Map<string, GraphCanvasNode['position']> } {
  const layoutPositionsById = new Map(layoutNodes.map((node) => [node.id, node.position]))
  const positions = new Map<string, GraphCanvasNode['position']>()
  const nodes = renderNodes.map((node) => {
    const position = previousPositions.get(node.id) ?? layoutPositionsById.get(node.id) ?? node.position
    positions.set(node.id, position)
    return { ...node, position }
  })
  return { nodes, positions }
}

export function updateStableLayoutPositionsFromNodeChanges(
  previousPositions: ReadonlyMap<string, GraphCanvasNode['position']>,
  changes: readonly NodeChange<GraphCanvasNode>[],
): Map<string, GraphCanvasNode['position']> {
  let nextPositions: Map<string, GraphCanvasNode['position']> | null = null
  for (const change of changes) {
    if (change.type === 'position' && change.position) {
      nextPositions ??= new Map(previousPositions)
      nextPositions.set(change.id, change.position)
    } else if (change.type === 'remove') {
      nextPositions ??= new Map(previousPositions)
      nextPositions.delete(change.id)
    }
  }
  return nextPositions ?? new Map(previousPositions)
}
