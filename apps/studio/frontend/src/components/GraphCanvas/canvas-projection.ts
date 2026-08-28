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
  options: { canvasHeight?: number; compactRatio?: number; arrangeTick?: number } = {},
): string {
  const nodeSignature = nodes
    .map((node) => `${node.id}:${node.type ?? ''}:${node.position.x},${node.position.y}`)
    .join('|')
  return [
    nodeSignature,
    `height=${options.canvasHeight ?? 0}`,
    `compact=${options.compactRatio ?? 0}`,
    // Auto-arrange re-lays-out the SAME topology, so the tick is the only
    // signature input that moves — without it the layout cache would answer
    // the arrange request with the identical cached result.
    `arrange=${options.arrangeTick ?? 0}`,
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

export const FIT_VIEW_PADDING_BASE_PX = 32

// 取景选项(用户裁决 2026-08-27「启动时改为100%,不要放大」):fit 只负责把
// 大图缩小装进可视区,绝不把小图放大过 100%——启动看到的是 1:1 的画布,不是
// 被放大的特写。手动「适应视图」与整理后的重新取景走同一条规则,行为一致。
type FitViewPaddingPx = `${number}px`

export function canvasFitViewOptions(insets: { left: number; right: number; top: number }): {
  maxZoom: number
  padding: {
    top: FitViewPaddingPx
    left: FitViewPaddingPx
    right: FitViewPaddingPx
    bottom: FitViewPaddingPx
  }
} {
  return {
    maxZoom: 1,
    padding: {
      top: `${insets.top + FIT_VIEW_PADDING_BASE_PX}px`,
      left: `${insets.left + FIT_VIEW_PADDING_BASE_PX}px`,
      right: `${insets.right + FIT_VIEW_PADDING_BASE_PX}px`,
      bottom: `${FIT_VIEW_PADDING_BASE_PX}px`,
    },
  }
}
