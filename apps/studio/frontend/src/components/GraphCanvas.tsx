import { Background, Controls, MarkerType, MiniMap, Panel, ReactFlow } from 'reactflow'
import type { Connection, Edge, Node, NodeTypes, OnEdgesChange, OnNodesChange } from 'reactflow'
import { useMemo } from 'react'
import type { KeyboardEvent } from 'react'
import { LayoutTemplate } from 'lucide-react'
import { AgentNode, SubgraphNode } from '../CustomNodes'
import type { StudioNodeData } from '../CustomNodes'
import { getEdgeColor } from '../hooks/useEdgeColoring'
import { errorMessage } from '../utils/errors'

const nodeTypes = {
  subgraph: SubgraphNode,
  agent: AgentNode,
} satisfies NodeTypes

interface GraphCanvasProps {
  currentSkillName: string
  skillDetailError: unknown
  nodes: Node<StudioNodeData>[]
  edges: Edge[]
  isDarkMode: boolean
  selectedPhaseId?: string | null
  onNodesChange: OnNodesChange
  onEdgesChange: OnEdgesChange
  onConnect: (connection: Connection) => void
  onResetLayout: () => void
  onPhaseSelect?: (phaseId: string) => void
  onPhaseDoubleClick?: (phaseId: string) => void
}

export function GraphCanvas({
  currentSkillName,
  skillDetailError,
  nodes,
  edges,
  isDarkMode,
  selectedPhaseId = null,
  onNodesChange,
  onEdgesChange,
  onConnect,
  onResetLayout,
  onPhaseSelect,
  onPhaseDoubleClick,
}: GraphCanvasProps) {
  const coloredEdges = useMemo(() => (
    edges.map((edge) => {
      const color = getEdgeColor(edge.source, isDarkMode)
      return {
        ...edge,
        type: 'smoothstep',
        style: { ...edge.style, stroke: color, strokeWidth: 2.5 },
        markerEnd: { type: MarkerType.ArrowClosed, color },
      }
    })
  ), [edges, isDarkMode])
  const visibleNodes = useMemo(() => (
    nodes.map((node) => ({
      ...node,
      selected: Boolean(selectedPhaseId && (node.id === selectedPhaseId || node.data.label === selectedPhaseId)),
    }))
  ), [nodes, selectedPhaseId])
  const selectedNodeIndex = useMemo(() => {
    if (!selectedPhaseId) {
      return -1
    }
    return visibleNodes.findIndex((node) => node.id === selectedPhaseId || node.data.label === selectedPhaseId)
  }, [selectedPhaseId, visibleNodes])

  const selectNodeAt = (index: number) => {
    const target = visibleNodes[index]
    if (!target) {
      return
    }
    onPhaseSelect?.(target.data.label)
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!['ArrowDown', 'ArrowRight', 'ArrowUp', 'ArrowLeft', 'Home', 'End', 'Enter', ' '].includes(event.key)) {
      return
    }
    if (visibleNodes.length === 0) {
      return
    }
    if (event.key === 'Enter' || event.key === ' ') {
      if (selectedNodeIndex >= 0) {
        event.preventDefault()
        onPhaseDoubleClick?.(visibleNodes[selectedNodeIndex].data.label)
      }
      return
    }
    event.preventDefault()
    if (event.key === 'Home') {
      selectNodeAt(0)
      return
    }
    if (event.key === 'End') {
      selectNodeAt(visibleNodes.length - 1)
      return
    }
    const direction = event.key === 'ArrowDown' || event.key === 'ArrowRight' ? 1 : -1
    const fallback = direction > 0 ? 0 : visibleNodes.length - 1
    const nextIndex = selectedNodeIndex < 0
      ? fallback
      : Math.min(visibleNodes.length - 1, Math.max(0, selectedNodeIndex + direction))
    selectNodeAt(nextIndex)
  }

  return (
    <div
      role="application"
      aria-label="Skill graph canvas"
      tabIndex={0}
      onKeyDown={handleKeyDown}
      className="relative flex-1 border-r border-gray-200 bg-slate-50 outline-none focus:ring-2 focus:ring-sky-300 dark:border-slate-800 dark:bg-slate-950 dark:focus:ring-sky-800"
    >
      <div className="absolute left-4 top-4 z-10 rounded-md border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-1.5 text-sm font-semibold text-gray-700 dark:text-gray-300 shadow-sm">
        {currentSkillName}
      </div>
      {skillDetailError ? (
        <div className="absolute inset-0 flex items-center justify-center p-8">
          <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">{errorMessage(skillDetailError)}</div>
        </div>
      ) : (
        <ReactFlow
          nodes={visibleNodes}
          edges={coloredEdges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={(_, node) => onPhaseSelect?.(node.data.label)}
          onNodeDoubleClick={(_, node) => onPhaseDoubleClick?.(node.data.label)}
          fitView
          minZoom={0.4}
        >
          <Panel position="top-right">
            <button
              type="button"
              onClick={onResetLayout}
              className="inline-flex items-center gap-2 rounded-md border border-gray-200 bg-white px-3 py-2 text-sm font-semibold text-gray-700 shadow-sm transition-colors hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-sky-300 dark:border-slate-700 dark:bg-slate-900 dark:text-gray-200 dark:hover:bg-slate-800 dark:focus:ring-sky-800"
              title="Reset layout"
              aria-label="Reset layout"
            >
              <LayoutTemplate className="h-4 w-4" aria-hidden="true" />
              Reset Layout
            </button>
          </Panel>
          <Controls />
          <MiniMap
            style={{ backgroundColor: isDarkMode ? '#0f172a' : '#fff' }}
            maskColor={isDarkMode ? 'rgba(0,0,0,0.4)' : 'rgba(240,240,240,0.6)'}
            nodeColor={isDarkMode ? '#334155' : '#e2e8f0'}
          />
          <Background gap={12} size={1} />
        </ReactFlow>
      )}
    </div>
  )
}
