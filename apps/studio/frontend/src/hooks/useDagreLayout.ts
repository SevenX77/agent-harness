import * as dagre from 'dagre'
import type { Edge, Node } from 'reactflow'

export interface DagreLayoutOptions {
  direction?: 'TB' | 'BT' | 'LR' | 'RL'
  nodeWidth?: number
  nodeHeight?: number
  rankSep?: number
  nodeSep?: number
}

const DEFAULT_NODE_WIDTH = 250
const DEFAULT_NODE_HEIGHT = 100
const DEFAULT_RANK_SEP = 80
const DEFAULT_NODE_SEP = 50

export function getLayoutedElements<T = unknown>(
  nodes: Node<T>[],
  edges: Edge[],
  options: DagreLayoutOptions = {},
): { nodes: Node<T>[]; edges: Edge[] } {
  if (nodes.length === 0) {
    return { nodes: [], edges }
  }

  const direction = options.direction ?? 'TB'
  const nodeWidth = options.nodeWidth ?? DEFAULT_NODE_WIDTH
  const nodeHeight = options.nodeHeight ?? DEFAULT_NODE_HEIGHT
  const rankSep = options.rankSep ?? DEFAULT_RANK_SEP
  const nodeSep = options.nodeSep ?? DEFAULT_NODE_SEP
  const graph = new dagre.graphlib.Graph()

  graph.setDefaultEdgeLabel(() => ({}))
  graph.setGraph({ rankdir: direction, ranksep: rankSep, nodesep: nodeSep })

  nodes.forEach((node) => {
    graph.setNode(node.id, { width: nodeWidth, height: nodeHeight })
  })
  edges.forEach((edge) => {
    graph.setEdge(edge.source, edge.target)
  })

  dagre.layout(graph)

  return {
    nodes: nodes.map((node) => {
      const layoutNode = graph.node(node.id)
      return {
        ...node,
        position: {
          x: layoutNode.x - nodeWidth / 2,
          y: layoutNode.y - nodeHeight / 2,
        },
      }
    }),
    edges,
  }
}
