import { Background, Controls, MiniMap, ReactFlow } from 'reactflow'
import type { Connection, Edge, Node, NodeTypes, OnEdgesChange, OnNodesChange } from 'reactflow'
import { AgentNode, SubgraphNode } from '../CustomNodes'
import type { StudioNodeData } from '../CustomNodes'
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
  onNodesChange: OnNodesChange
  onEdgesChange: OnEdgesChange
  onConnect: (connection: Connection) => void
}

export function GraphCanvas({
  currentSkillName,
  skillDetailError,
  nodes,
  edges,
  isDarkMode,
  onNodesChange,
  onEdgesChange,
  onConnect,
}: GraphCanvasProps) {
  return (
    <div className="relative flex-1 border-r border-gray-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-950">
      <div className="absolute left-4 top-4 z-10 rounded-md border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-1.5 text-sm font-semibold text-gray-700 dark:text-gray-300 shadow-sm">
        {currentSkillName}
      </div>
      {skillDetailError ? (
        <div className="absolute inset-0 flex items-center justify-center p-8">
          <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">{errorMessage(skillDetailError)}</div>
        </div>
      ) : (
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          fitView
          minZoom={0.4}
        >
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
