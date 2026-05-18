import { graphlib, layout as dagreLayout } from 'dagre'
import type { Edge, Node } from '@xyflow/react'

export class CycleDetectedError extends Error {
  constructor() {
    super('SKILL contains a cyclic dependency - cannot auto-layout')
    this.name = 'CycleDetectedError'
  }
}

const DEFAULT_NODE_WIDTH = 260
const DEFAULT_NODE_HEIGHT = 120
const IO_NODE_WIDTH = 180
const IO_NODE_HEIGHT = 80

function nodeSize(node: Node): { width: number; height: number } {
  if (node.type === 'globalInput' || node.type === 'globalOutput') {
    return { width: IO_NODE_WIDTH, height: IO_NODE_HEIGHT }
  }
  return { width: DEFAULT_NODE_WIDTH, height: DEFAULT_NODE_HEIGHT }
}

export function getAutoLayoutedElements<TNode extends Node, TEdge extends Edge>(
  nodes: TNode[],
  edges: TEdge[],
  options: { bottomReservedHeight?: number } = {},
): { nodes: TNode[]; edges: TEdge[] } {
  const graph = new graphlib.Graph()
  graph.setDefaultEdgeLabel(() => ({}))
  graph.setGraph({
    rankdir: 'LR',
    nodesep: 80,
    ranksep: 100,
    marginx: 24,
    marginy: 24,
  })

  for (const node of nodes) {
    graph.setNode(node.id, nodeSize(node))
  }
  for (const edge of edges) {
    graph.setEdge(edge.source, edge.target)
  }

  if (!graphlib.alg.isAcyclic(graph)) {
    throw new CycleDetectedError()
  }

  dagreLayout(graph)

  return {
    nodes: nodes.map((node) => {
      const position = graph.node(node.id)
      const size = nodeSize(node)
      return {
        ...node,
        position: {
          x: position.x - size.width / 2,
          y: position.y - size.height / 2 - (options.bottomReservedHeight ?? 0),
        },
      }
    }),
    edges,
  }
}
